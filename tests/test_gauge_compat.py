"""Native bridge regression tests; no live BLE or system changes."""
import json
import os
from pathlib import Path
import unittest
import asyncio
import shutil
import tempfile
from gauge_compat import Core, Rules, Vehicle

UPSTREAM = Path(os.environ.get('MI4_COMPAT_UPSTREAM', Path(__file__).parent.parent / 'obd-rebuild'))


class NativeCompatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = Core()

    def test_all_17_catalog_profiles_compile_unchanged(self):
        paths = sorted((UPSTREAM / 'vehicles/catalog').glob('*.vehicle.json'))
        self.assertEqual(len(paths), 17)
        for path in paths:
            with self.subTest(profile=path.name):
                raw = json.loads(path.read_text())
                with Vehicle(raw, self.core) as vehicle:
                    self.assertTrue(vehicle.report['ok'])
                    self.assertEqual(vehicle.report['errors'], 0)
                    self.assertEqual(vehicle.report['warnings'], 0)
                    self.assertEqual(vehicle.report['id'], raw['id'])

    def test_minimal_inherits_and_disabled_signal_does_not_return(self):
        raw = dict(schema='skygauge.vehicle/1', id='custom.mi4', rev=1, name='MI4')
        with Vehicle(raw, self.core) as vehicle:
            self.assertEqual(vehicle.report['signals'], 9)
        raw['signals'] = [{'id': 'obd.oil_temp', 'disabled': True}]
        with Vehicle(raw, self.core) as vehicle:
            self.assertEqual(vehicle.report['signals'], 8)

    def test_forbidden_vehicle_commands_never_reach_transport(self):
        raw = dict(schema='skygauge.vehicle/1', id='unsafe', rev=1, name='Unsafe',
                   signals=[dict(id='obd.oil_temp', src=[dict(req='2E1234', len=1, rpn=[['A', 0]])])])
        with self.assertRaisesRegex(ValueError, 'E_SERVICE'):
            Vehicle(raw, self.core)
        raw.pop('signals')
        raw['bus'] = {'init': ['ATPP00SVFF']}
        with self.assertRaisesRegex(ValueError, 'E_AT'):
            Vehicle(raw, self.core)

    def test_rule_priority_reset_and_invalidation(self):
        page = dict(elements=[dict(id='rpm', kind='arc')], rules=[dict(
            id='hot', when=dict(source='obd.rpm', op='>', value=4000, hysteresis=200),
            apply=[dict(target='rpm', set=dict(color='#ff0000'))])])
        with Rules(page, core=self.core) as rules:
            self.assertEqual(rules.tick({'obd.rpm': 5000}, 0)['overrides']['rpm']['color'], '#ff0000')
            self.assertEqual(rules.tick({'obd.rpm': 3900}, 10)['activeRules'], ['hot'])
            self.assertEqual(rules.tick({'obd.rpm': 3700}, 20)['overrides'], {})
            rules.reset()
            self.assertEqual(rules.tick({}, 30)['overrides'], {})
        with self.assertRaises(RuntimeError):
            rules.tick({}, 40)

    def test_strict_import_does_not_hide_unknown_target(self):
        page = dict(elements=[], rules=[dict(id='r', when={}, apply=[dict(target='missing', set=dict(text='x'))])])
        with self.assertRaisesRegex(ValueError, 'unknown_targets'):
            Rules(page, core=self.core)

    def test_upstream_rule_golden_vectors_through_python_ffi(self):
        vectors = json.loads((UPSTREAM / 'contracts/fixtures/rules/vectors.json').read_text())
        count = 0
        for case in vectors:
            page = case.get('page', dict(elements=[], rules=[case.get('rule')]))
            shared = None
            try:
                if case.get('runtime') == 'shared':
                    shared = Rules(page, core=self.core, strict=False)
                for index, step in enumerate(case['steps']):
                    with self.subTest(case=case['name'], step=index):
                        rules = shared or Rules(page, core=self.core, strict=False)
                        try:
                            result = rules.tick(step.get('values', {}), step.get('elapsedMs', 0), step.get('changed', []))
                            expected = step['expect']
                            if 'active' in expected:
                                self.assertEqual(bool(result['activeRules']), expected['active'])
                            for key in ('activeRules', 'overrides'):
                                if key in expected:
                                    self.assertEqual(result[key], expected[key])
                            count += 1
                        finally:
                            if not shared:
                                rules.close()
            finally:
                if shared:
                    shared.close()
        self.assertEqual(count, 79)

    def test_engine_fake_adapter_and_disconnect(self):
        raw = dict(schema='skygauge.vehicle/1', id='custom.mi4', rev=1, name='MI4', bus={'proto': 6})
        commands = []
        with Vehicle(raw, self.core) as vehicle:
            vehicle.link(True, 0)
            for now in range(0, 10000, 5):
                _, command = vehicle.run(now)
                if command is None:
                    continue
                commands.append(command)
                response = {'ATZ': 'ELM327 v1.5', 'ATI': 'ELM327 v1.5', 'ATRV': '12.6V',
                            '0100': '41 00 BE 3F A8 13', '010C': '41 0C 1F 40',
                            '0105': '41 05 7B', '010D': '41 0D 32',
                            '0142': '41 42 31 38'}.get(command, 'OK' if command.startswith('AT') else 'NO DATA')
                packet = (response + '\r\r>').encode()
                vehicle.rx(packet[:3], now)
                vehicle.rx(packet[3:], now)
            snapshot = vehicle.snapshot()
            self.assertEqual(snapshot['values']['obd.rpm'], 2000)
            self.assertEqual(snapshot['values']['obd.coolant_temp'], 83)
            self.assertEqual(snapshot['values']['obd.speed'], 50)
            self.assertEqual(snapshot['link'], 2)
            self.assertIn('ATSH7E0', commands)
            vehicle.link(False, 10001)
            self.assertIsNone(vehicle.snapshot()['values']['obd.rpm'])
            vehicle.close()
            with self.assertRaises(RuntimeError):
                vehicle.run(10002)

    def test_settings_accepts_original_profiles_without_converting_pid_numbers(self):
        from gauge_settings import Config
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'pid-profiles'
            target.mkdir()
            for path in (UPSTREAM / 'vehicles/catalog').glob('*.vehicle.json'):
                shutil.copyfile(path, target / path.name)
            config = Config(root)
            self.assertEqual(len(config.profiles), 19)
            original = next(p for p in config.profiles if p['id'] == 'bmw.g.obd')
            self.assertIn('_native_profile', original)
            config.data['profile'] = original['id']
            config.save()
            self.assertEqual(Config(root).profile['_native_profile']['id'], original['id'])

    def test_native_ble_transport_cancels_and_releases_connection(self):
        from gauge_compat_ble import run_vehicle_ble
        async def scenario():
            finished = asyncio.Event()
            clients = []
            class FakeClient:
                def __init__(self, address):
                    self.is_connected = False
                    self.callback = None
                    self.unsubscribed = False
                    self.commands = []
                    clients.append(self)
                async def connect(self):
                    self.is_connected = True
                async def start_notify(self, uuid, callback):
                    self.callback = callback
                async def write_gatt_char(self, uuid, data, response=False):
                    cmd = data.decode().strip()
                    self.commands.append(cmd)
                    answer = {'ATRV': '12.6V', 'ATZ': 'ELM327 v1.5',
                              '0100': '4100BE3FA813', '010C': '410C1F40'}.get(
                                  cmd, 'OK' if cmd.startswith('AT') else 'NO DATA')
                    packet = (answer + '\r\r>').encode()
                    self.callback(None, packet[:2])
                    self.callback(None, packet[2:])
                async def stop_notify(self, uuid):
                    self.unsubscribed = True
                async def disconnect(self):
                    self.is_connected = False
            def publish(values, status):
                if values.get('obd.rpm') == 2000:
                    finished.set()
            raw = dict(schema='skygauge.vehicle/1', id='custom.mi4', rev=1, name='MI4', bus={'proto': 6})
            task = asyncio.create_task(run_vehicle_ble('02:00:00:00:00:01', raw, publish, FakeClient))
            try:
                await asyncio.wait_for(finished.wait(), 8)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self.assertFalse(clients[0].is_connected)
            self.assertTrue(clients[0].unsubscribed)
            self.assertIn('ATSH7E0', clients[0].commands)
        asyncio.run(scenario())


if __name__ == '__main__':
    unittest.main()

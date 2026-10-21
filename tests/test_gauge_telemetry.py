import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from types import SimpleNamespace

from gauge_telemetry import Telemetry, CHANNELS
from gauge_settings import Config, TouchSettings


class TelemetryTests(unittest.TestCase):
    def test_raw_acceleration_logged_without_calibration(self):
        log = Telemetry(enabled=False)
        imu = dict(ready=True,calibrated=False,measurement_mode='accelerometer_raw',
                   includes_gravity=True,display_g=[.4,-.7],accel_g=[.4,-.7,.8],
                   accel_ms2=[3.92,-6.86,7.84],total_g=1.14)
        log.sample(1,{}, {}, {'imu':imu})
        row = log.history[-1]
        self.assertEqual(row['channels']['gx'],.4)
        self.assertEqual(row['channels']['gy'],-.7)
        self.assertTrue(row['acceleration']['includes_gravity'])
        self.assertEqual(row['acceleration']['accel_g'][2],.8)

    def test_track_channels_keep_unavailable_pedals_unknown(self):
        self.assertEqual([c[0] for c in CHANNELS], ['speed','rpm','throttle','gx','gy'])
        log = Telemetry(enabled=False)
        log.sample(1, {'rpm':2000,'speed':65,'coolant':91,'oil':105},
                   {'obd.gear':3,'obd.throttle':28,'obd.brake_temp':120}, {})
        channels = log.history[-1]['channels']
        self.assertEqual(channels['gear'], 3)
        self.assertEqual(channels['coolant'], 91)
        self.assertEqual(channels['oil'], 105)
        self.assertNotIn('brake', channels)
        self.assertIsNone(channels['gx'])
        log.sample(2, {}, {}, {})
        self.assertIsNone(log.history[-1]['channels']['gear'])

    def test_raw_missing_throttle_g_and_strict_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Telemetry(tmp)
            log.sample(10, {'rpm': 2345, 'speed': math.nan}, {}, {})
            self.assertFalse(log.sample(10.02, {}, {}, {}))
            log.sample(10.1, {'speed': 27}, {'obd.throttle': 35},
                       {'imu': {'ready': True, 'calibrated': True, 'display_g': [.4, -.7]}})
            log.close()
            records = [json.loads(line) for path in Path(tmp).glob('*.jsonl') for line in path.read_text().splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(records[1]['channels']['rpm'], 2345)
            self.assertIsNone(records[1]['channels']['speed'])
            self.assertIsNone(records[1]['channels']['gx'])
            self.assertEqual(records[2]['channels']['gy'], -.7)
            self.assertEqual(records[2]['channels']['throttle'], 35)

    def test_freeze_is_independent_of_recording_and_history(self):
        log = Telemetry(enabled=False)
        log.sample(0, {'rpm': 1000}, {}, {})
        log.toggle_pause()
        for n in range(800):
            log.sample(n+1, {'rpm': n}, {}, {})
        self.assertEqual(log.frozen[0]['channels']['rpm'], 1000)
        self.assertLessEqual(len(log.history), 620)
        self.assertFalse(log.recording)
        log.toggle_pause()
        self.assertIsNone(log.frozen)

    def test_rotation_does_not_touch_other_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = Path(tmp)/'trip.csv'
            keep.write_text('keep')
            log = Telemetry(tmp, max_bytes=1600, max_files=3)
            for n in range(60):
                log.sample(n, {'rpm': n}, {}, {})
            log.close()
            files = list(Path(tmp).glob('telemetry-*.jsonl'))
            self.assertEqual(len(files), 3)
            for path in files:
                self.assertLessEqual(path.stat().st_size, 1600)
                self.assertEqual(json.loads(path.read_text().splitlines()[0])['type'], 'header')
            self.assertEqual(keep.read_text(), 'keep')

    def test_storage_error_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'file'
            path.write_text('not directory')
            log = Telemetry(path)
            log.sample(1, {}, {}, {})
            log.close()
            self.assertTrue(log.error)
            self.assertEqual(log.dropped, 1)

    def test_legacy_sky_migrates_only_saved_direct(self):
        for direct in (None, dict(address='02:00:00:00:00:03', enabled=True)):
            with tempfile.TemporaryDirectory() as tmp:
                raw = dict(connection_mode='sky', address='02:00:00:00:00:07', enabled=True,
                           connections={} if direct is None else {'direct': direct})
                (Path(tmp)/'settings.json').write_text(json.dumps(raw))
                config = Config(tmp)
                self.assertEqual(config.data['connection_mode'], 'direct')
                self.assertEqual(config.data['address'], direct['address'] if direct else '')
                self.assertNotIn('sky', config.data['connections'])
                with self.assertRaises(ValueError):
                    config.set_connection_mode('sky')

    def test_vertical_navigation_and_buttons_do_not_toggle_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            controls = TouchSettings(Config(tmp), Mock(), brightness=Mock(read=lambda:50))
            controls.telemetry = Telemetry(enabled=False)
            controls.input('down', 300, 70, 1)
            controls.input('up', 305, 250, 1.3)
            self.assertEqual(controls.page, 'telemetry')
            controls.input('down', 440, 22, 2)
            controls.input('up', 441, 22, 2.1)
            self.assertIsNotNone(controls.telemetry.frozen)
            controls.input('down', 300, 270, 3)
            controls.input('up', 305, 100, 3.3)
            self.assertEqual(controls.page, 'gauge')

    def test_native_page_draw_and_full_gauge_restore(self):
        import gauge_sdl
        with tempfile.TemporaryDirectory() as tmp:
            source = SimpleNamespace(read=lambda:dict(rpm=2500, speed=45, coolant=90, oil=80, battery=13),
                                     connection_status=lambda:'已连接')
            controls = TouchSettings(Config(tmp), source, brightness=Mock(read=lambda:50))
            controls.motion = Mock(read=lambda:{})
            gauge = gauge_sdl.Gauge(source, headless=True, controls=controls)
            gauge.draw_interactive_frame()
            controls.page = 'telemetry'
            frame = gauge.draw_interactive_frame()
            self.assertEqual(frame[0][0], (0,0,640,360))
            controls.page = 'gauge'
            self.assertTrue(gauge.draw_interactive_frame())
            self.assertEqual(gauge.previous_page, 'gauge')
            self.assertIsNone(gauge.telemetry.worker)


if __name__ == '__main__':
    unittest.main()

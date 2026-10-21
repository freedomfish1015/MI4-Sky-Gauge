import json
import math
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

import gauge_power as ui
import gauge_power_service as daemon


class PolicyTests(unittest.TestCase):
    def armed(self):
        policy = daemon.Policy()
        policy.heartbeat(100)
        self.assertFalse(policy.update(True, 100))
        self.assertFalse(policy.update(False, 101))
        self.assertEqual(policy.snapshot(101)['remaining'], 20)
        return policy

    def test_twenty_seconds_monotonic_and_exact_deadline(self):
        policy = self.armed()
        for second in range(1, 20):
            policy.heartbeat(101 + second)
            self.assertFalse(policy.update(False, 101 + second))
            self.assertEqual(policy.snapshot(101 + second)['remaining'], 20 - second)
        policy.heartbeat(121)
        self.assertTrue(policy.update(False, 121))

    def test_keep_on_until_next_connect_disconnect(self):
        policy = self.armed()
        policy.keep_on()
        policy.heartbeat(200)
        self.assertFalse(policy.update(False, 200))
        self.assertEqual(policy.phase, 'held')
        policy.update(True, 201)
        policy.update(False, 202)
        self.assertEqual(policy.deadline, 222)

    def test_replug_cancels_immediately(self):
        policy = self.armed()
        self.assertFalse(policy.update(True, 120))
        self.assertEqual(policy.phase, 'idle')
        self.assertIsNone(policy.deadline)

    def test_unknown_never_causes_poweroff(self):
        policy = self.armed()
        policy.heartbeat(122)
        self.assertFalse(policy.update(None, 122))
        self.assertEqual(policy.phase, 'idle')

    def test_boot_without_cable_does_not_invent_unplug(self):
        policy = daemon.Policy()
        policy.heartbeat(100)
        policy.update(False, 100)
        self.assertEqual(policy.phase, 'idle')

    def test_frozen_or_absent_ui_waits_then_restarts_full_countdown(self):
        policy = self.armed()
        self.assertFalse(policy.update(False, 121))
        self.assertEqual(policy.phase, 'waiting_ui')
        policy.heartbeat(130)
        policy.update(False, 130)
        self.assertEqual(policy.deadline, 150)


class SupplyTests(unittest.TestCase):
    def test_both_inputs_and_unknown_sensor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('smbb-usbin', 'smbb-dcin'):
                (root / name).mkdir()
                (root / name / 'online').write_text('0')
            self.assertIs(daemon.external_online(root), False)
            (root / 'smbb-dcin/online').write_text('1')
            self.assertIs(daemon.external_online(root), True)
            (root / 'smbb-usbin/online').unlink()
            self.assertIs(daemon.external_online(root), True)
            (root / 'smbb-dcin/online').write_text('0')
            self.assertIsNone(daemon.external_online(root))


class ServiceTests(unittest.TestCase):
    def test_authenticated_manual_shutdown_while_charging_once_only(self):
        with tempfile.TemporaryDirectory() as directory:
            service = daemon.Service(directory, directory, os.getuid())
            service.policy.update(True, 100)
            connection = mock.Mock()
            connection.getsockopt.return_value = struct.pack('3i', 9, os.getuid(), 9)
            connection.recv.return_value = b'{"command":"shutdown"}'
            with mock.patch.object(daemon.subprocess, 'run') as run:
                service.command(connection)
                service.command(connection)
            run.assert_called_once_with(['/usr/bin/systemctl', '--no-block', 'poweroff'],
                                        check=True, timeout=5)
            self.assertFalse(service.policy.update(True, 200))
            self.assertEqual(service.policy.snapshot(200)['reason'], 'manual')
            self.assertEqual(service.policy.phase, 'shutdown')

    def service(self, directory):
        service = daemon.Service(directory, directory, os.getuid())
        service.policy.heartbeat(100)
        service.policy.update(True, 100)
        service.policy.update(False, 100)
        service.policy.heartbeat(120)
        return service

    def test_cable_powers_off_after_countdown(self):
        """Unplug must power off: s2idle flattened the cell overnight."""
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory)
            with mock.patch.object(daemon.time, 'monotonic', return_value=120), \
                 mock.patch.object(daemon, 'external_online', return_value=False), \
                 mock.patch.object(daemon.subprocess, 'run') as run:
                service.step()
                service.step()
            run.assert_called_once_with(['/usr/bin/systemctl', '--no-block', 'poweroff'],
                                        check=True, timeout=5)
            self.assertEqual(service.policy.phase, 'shutdown')
            self.assertEqual(service.policy.reason, 'cable')

    def test_no_suspend_path_can_be_reintroduced(self):
        """The unplug path must never suspend: modem RAM needs real power."""
        self.assertFalse(hasattr(daemon.Service, 'suspend'))
        self.assertFalse(hasattr(daemon.Service, 'suspend_cable'))
        self.assertFalse(hasattr(daemon, 'arm_rtc_alarm'))

    def test_final_hardware_recheck_prevents_replug_race(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory)
            with mock.patch.object(daemon.time, 'monotonic', return_value=120), \
                 mock.patch.object(daemon, 'external_online', side_effect=[False, True]), \
                 mock.patch.object(daemon.subprocess, 'run') as run:
                service.step()
            run.assert_not_called()
            self.assertEqual(service.policy.phase, 'idle')

    def test_dry_run_never_executes_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory)
            service.dry_run = True
            with mock.patch.object(daemon.time, 'monotonic', return_value=120), \
                 mock.patch.object(daemon, 'external_online', return_value=False), \
                 mock.patch.object(daemon.subprocess, 'run') as run:
                service.step()
            run.assert_not_called()

    def test_failed_poweroff_stays_visible_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory)
            with mock.patch.object(daemon.time, 'monotonic', return_value=120), \
                 mock.patch.object(daemon, 'external_online', return_value=False), \
                 mock.patch.object(daemon.subprocess, 'run', side_effect=OSError('test failure')):
                service.step()
            self.assertEqual(service.policy.phase, 'error')
            self.assertIn('失败', service.policy.message)

    def test_socket_only_accepts_known_operations_from_expected_uid(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory)
            for uid, command, expected in ((99999, 'keep_on', 'countdown'),
                                           (os.getuid(), 'poweroff', 'countdown'),
                                           (os.getuid(), 'keep_on', 'held')):
                connection = mock.Mock()
                connection.getsockopt.return_value = struct.pack('3i', 9, uid, 9)
                connection.recv.return_value = json.dumps(dict(command=command)).encode()
                service.command(connection)
                self.assertEqual(service.policy.phase, expected)


class UITests(unittest.TestCase):
    def test_button_requires_tap_not_swipe(self):
        client = ui.PowerClient()
        with mock.patch.object(client, 'send', return_value=True) as send:
            client.input('down', 250, 265)
            client.input('up', 450, 265)
            send.assert_not_called()
            client.input('down', 280, 260)
            client.input('up', 282, 262)
            send.assert_called_once_with('keep_on')

    def test_modal_cached_and_underlying_gauge_fully_restored(self):
        import gauge_sdl as gauge
        power = mock.Mock()
        power.poll.return_value = None
        view = gauge.Gauge(gauge.DemoSource(), headless=True, power=power)
        view.draw_interactive_frame()
        power.poll.return_value = dict(phase='countdown', remaining=20)
        self.assertTrue(view.draw_interactive_frame())
        self.assertEqual(view.draw_interactive_frame(), [])
        view.input_events.put(('down', 260, 260, 1))
        view.input_events.put(('up', 260, 260, 1.1))
        view.draw_interactive_frame()
        self.assertEqual(power.input.call_count, 2)
        power.poll.return_value = None
        regions = view.draw_interactive_frame()
        self.assertEqual(regions[0][0], (0., 0., 640., 360.))
        reference = gauge.Gauge(gauge.DemoSource(), headless=True)
        reference.draw_frame(view.values, full=True)
        self.assertEqual(bytes(view.surface.get_data()), bytes(reference.surface.get_data()))


def export(path):
    import cairo
    import gauge_sdl as gauge
    view = gauge.Gauge(gauge.DemoSource(), headless=True)
    view.draw_frame(dict(rpm=2860, coolant=92, oil=84, battery=13.8, speed=28), full=True)
    backdrop = cairo.ImageSurface(cairo.FORMAT_ARGB32, gauge.RW, gauge.RH)
    cr = cairo.Context(backdrop)
    cr.set_source_surface(view.surface, 0, 0)
    cr.paint()
    ui.paint_modal(view, dict(phase='countdown', remaining=20), backdrop)
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1920, 1080)
    cr = cairo.Context(out)
    cr.translate(0, 1080)
    cr.rotate(-math.pi / 2)
    cr.set_source_surface(view.surface, 0, 0)
    cr.paint()
    out.write_to_png(path)


if __name__ == '__main__':
    import sys
    if '--export' in sys.argv:
        export(sys.argv[-1])
    else:
        unittest.main()

import asyncio
import ctypes
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

import gauge_settings as settings
import gauge_sdl as gauge


class FakeSource:
    def __init__(self):
        self.calls = []

    def configure(self, *args):
        self.calls.append(args)

    def connection_status(self):
        return '测试连接状态'

    def read(self):
        return dict(rpm=2300, coolant=87, oil=80, speed=50, battery=13.8)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.backlight = self.path / 'backlight'
        self.backlight.mkdir()
        (self.backlight / 'max_brightness').write_text('4095')
        (self.backlight / 'brightness').write_text('2351')
        self.config = settings.Config(self.path / 'config', '02:00:00:00:00:05')
        self.source = FakeSource()
        self.controls = settings.TouchSettings(self.config, self.source, settings.Brightness(self.backlight))

    def swipe(self, left=True):
        a, b = (500, 120) if left else (120, 500)
        self.controls.input('down', a, 160, 1)
        self.controls.input('up', b, 165, 1.3)

    def test_swipe_tabs_profile_and_persistence(self):
        self.swipe()
        self.assertEqual(self.controls.page, 'settings')
        self.controls.tap(300, 156)
        self.assertEqual(self.config.data['profile'], 'bmw-g-sim')
        self.assertEqual(len(self.source.calls), 1)
        loaded = settings.Config(self.config.directory)
        self.assertEqual(loaded.data['profile'], 'bmw-g-sim')
        self.controls.tap(200, 56)
        self.assertEqual(self.controls.tab, 1)
        self.swipe(False)
        self.assertEqual(self.controls.page, 'gauge')

    def test_slider_does_not_navigate_and_clamps_and_saves(self):
        self.swipe()
        self.controls.tap(320, 56)
        self.controls.input('down', 570, 210)
        self.controls.input('move', 100, 215)
        self.controls.input('up', -30, 215)
        self.assertEqual(self.controls.page, 'settings')
        self.assertEqual(self.controls.percent, 5)
        self.assertEqual((self.backlight / 'brightness').read_text(), '205')
        self.assertEqual(settings.Config(self.config.directory).data['brightness'], 5)

    def test_tap_cannot_be_triggered_by_large_drag(self):
        self.swipe()
        self.controls.input('down', 100, 130, 1)
        self.controls.input('up', 140, 200, 1.2)
        self.assertFalse(self.source.calls)
        self.controls.tap(60, 30)
        self.assertEqual(self.controls.page, 'gauge')

    def test_manual_power_button_is_a_tap_not_a_swipe(self):
        self.controls.page = 'settings'
        self.controls.shutdown = mock.Mock(return_value=True)
        self.controls.input('down', 576, 34, 1)
        self.controls.input('up', 480, 34, 1.2)
        self.controls.shutdown.assert_not_called()
        self.controls.page = 'settings'
        self.controls.input('down', 575, 33, 2)
        self.controls.input('up', 576, 34, 2.1)
        self.controls.shutdown.assert_called_once_with()

    def test_manual_power_unavailable_is_reported(self):
        self.controls.tap(576, 34)
        self.assertIn('不可用', self.controls.message)

    def test_config_corruption(self):
        self.config.directory.mkdir()
        for raw in ('{bad', '[]', '{"brightness": "no", "enabled": "false"}'):
            self.config.path.write_text(raw)
            recovered = settings.Config(self.config.directory, '02:00:00:00:00:05')
            self.assertTrue(recovered.data['enabled'])
            self.assertNotIn('brightness', recovered.data)

    def test_window_binding_selection_is_saved_without_reconnecting(self):
        from gauge_windows import DEFAULT_WINDOWS
        self.controls.page = 'settings'
        self.controls.tap(440, 56)
        self.assertEqual(self.controls.tab, 3)
        self.controls.tap(300, settings.PID_TOP + 3 * 44 + 20)
        self.assertEqual(self.config.data['windows'][0], 'obd.speed')
        self.assertFalse(self.source.calls)
        self.assertEqual(settings.Config(self.config.directory).data['windows'][0], 'obd.speed')
        self.assertEqual(self.config.data['windows'][1:], list(DEFAULT_WINDOWS[1:]))
        # Right-hand data list scrolls; dragging must not change a binding.
        self.controls.input('down', 400, 300, 1)
        self.controls.input('up', 400, 100, 1.2)
        self.assertEqual(self.controls.window_scroll, 200)
        self.assertEqual(self.config.data['windows'][0], 'obd.speed')
        self.assertEqual(self.controls.page, 'settings')
        self.controls.tap(100, settings.PID_TOP + 3 * 56 + 24)
        self.assertEqual(self.controls.window_slot, 3)
        self.controls.tap(300, settings.PID_TOP + 20)
        self.assertEqual(self.config.data['windows'][3], 'obd.gear')
        self.assertFalse(self.source.calls)

    def test_window_binding_corruption_falls_back_per_slot(self):
        from gauge_windows import DEFAULT_WINDOWS
        self.config.directory.mkdir()
        self.config.path.write_text(json.dumps({'windows': ['obd.speed', 'evil', 5, 'obd.gear']}))
        loaded = settings.Config(self.config.directory)
        self.assertEqual(loaded.data['windows'], ['obd.speed', DEFAULT_WINDOWS[1], DEFAULT_WINDOWS[2], 'obd.gear'])

    def test_window_bindings_refresh_labels_once_and_missing_value_is_not_zero(self):
        self.source.read_signals = lambda: {'obd.throttle': 32, 'obd.gear': None}
        view = gauge.Gauge(self.source, headless=True, controls=self.controls)
        view.sweep_done = True
        view.draw_interactive_frame()
        with mock.patch.object(view, 'build_static', wraps=view.build_static) as rebuild:
            self.config.data['windows'] = ['obd.throttle', 'obd.gear', 'obd.oil_temp', 'obd.speed']
            self.assertEqual(view.draw_interactive_frame()[0][0], (0, 0, 640, 360))
            self.assertEqual(view.cards[0][2], '节气门')
            self.assertEqual(view.cards[0][-1], '%')
            self.assertEqual(view.shown[0][0], '32')
            self.assertEqual(view.shown[1][0], '--')
            view.draw_interactive_frame()
            self.assertEqual(rebuild.call_count, 1)
        reference = gauge.Gauge(self.source, headless=True, controls=self.controls)
        reference.draw_frame(view.values, full=True)
        self.assertEqual(bytes(view.static.get_data()), bytes(reference.static.get_data()))
        actual, expected = bytes(view.surface.get_data()), bytes(reference.surface.get_data())
        points = [(i // 4 % gauge.RW, i // 4 // gauge.RW) for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
        self.assertEqual(len(points), 0, 'dirty/full pixel differences=%d first=%s' % (len(points), points[:8]))

    def test_readonly_profile_validation_and_decoding(self):
        standard, bmw = self.config.profiles
        self.assertEqual(settings.decode(['41 0C 1F 40'], standard['pids']['rpm']), 2000)
        self.assertEqual(settings.decode(['62440200B0'], bmw['pids']['oil']), 84)
        self.assertIsNone(settings.decode(['NO DATA'], bmw['pids']['oil']))
        for command in ('04', 'ATZ', '2E440200', '010C\r04'):
            bad = json.loads(json.dumps(standard))
            bad['pids']['rpm']['command'] = command
            with self.assertRaises(ValueError):
                settings.validate_profile(bad)

    def test_scan_is_background_and_connection_is_explicit(self):
        released = threading.Event()
        async def discover(timeout):
            while not released.is_set():
                await asyncio.sleep(.01)
            return [types.SimpleNamespace(name='OBDII', address='02:00:00:00:00:05')]
        with mock.patch.dict('sys.modules', bleak=types.SimpleNamespace(BleakScanner=types.SimpleNamespace(discover=discover))):
            self.controls.scan()
            self.assertTrue(self.controls.scanning)
            self.assertFalse(self.source.calls)
            self.controls.scan()  # No duplicate worker.
            released.set()
            for _ in range(100):
                if not self.controls.scanning:
                    break
                time.sleep(.01)
        self.controls.tab = 1
        self.controls.tap(100, settings.BLE_TOP + 20)
        self.assertEqual(len(self.source.calls), 1)
        self.controls.tap(100, 330)
        self.assertFalse(self.config.data['enabled'])

    def test_sdl_abi_and_rotation(self):
        self.assertEqual(ctypes.sizeof(gauge.SDLEvent), 56)
        self.assertEqual(gauge.SDLFingerEvent.x.offset, 24)
        self.assertEqual(settings.logical_point(.25, .75), (480, 270))

    def test_device_list_scroll_does_not_connect_or_leave_settings(self):
        self.controls.page, self.controls.tab = 'settings', 1
        self.controls.devices = [('OBD %d' % i, 'AA:BB:CC:DD:EE:%02X' % i) for i in range(12)]
        self.controls.input('down', 300, 280, 1)
        self.controls.input('move', 300, 190, 1.1)
        self.controls.input('up', 300, 180, 1.2)
        self.assertEqual(self.controls.device_scroll, 100)
        self.assertEqual(self.controls.page, 'settings')
        self.assertFalse(self.source.calls)
        self.controls.input('down', 300, settings.BLE_TOP + 5, 2)
        self.controls.input('up', 300, settings.BLE_TOP + 5, 2.1)
        self.assertEqual(self.config.data['address'], self.controls.devices[2][1])
        self.controls.input('down', 300, 280, 3)
        self.controls.input('up', 300, -900, 3.2)
        self.assertEqual(self.controls.device_scroll, 12 * settings.BLE_ROW - (settings.BLE_BOTTOM - settings.BLE_TOP))
        self.controls.input('down', 300, 180, 4)
        self.controls.input('up', 300, 900, 4.2)
        self.assertEqual(self.controls.device_scroll, 0)
        self.assertEqual(len(self.source.calls), 1)
        # Horizontal gestures in the same list must still return to the gauge.
        self.controls.input('down', 100, 220, 5)
        self.controls.input('up', 500, 223, 5.2)
        self.assertEqual(self.controls.page, 'gauge')

    def test_pid_list_vertical_scroll_clamp_tap_and_gap(self):
        self.controls.page, self.controls.tab = 'settings', 0
        for i in range(17):
            self.config.profiles.append(dict(self.config.profiles[0], id='profile-%d' % i, name='Profile %d' % i))
        self.controls.input('down', 300, 300, 1)
        self.controls.input('move', 300, 150, 1.1)
        self.controls.input('up', 300, 100, 1.2)
        self.assertEqual(self.controls.profile_scroll, 200)
        self.assertFalse(self.source.calls)
        self.assertEqual(self.controls.page, 'settings')
        self.controls.input('down', 300, settings.PID_TOP + 20, 2)
        self.controls.input('up', 300, settings.PID_TOP + 20, 2.1)
        self.assertEqual(self.config.data['profile'], self.config.profiles[4]['id'])
        self.assertEqual(len(self.source.calls), 1)
        self.controls.input('down', 300, 200, 3)
        self.controls.input('up', 300, -900, 3.2)
        self.assertEqual(self.controls.profile_scroll, 19 * settings.PID_ROW - (settings.PID_BOTTOM - settings.PID_TOP))
        self.controls.input('down', 300, 200, 4)
        self.controls.input('up', 300, 1200, 4.2)
        self.assertEqual(self.controls.profile_scroll, 0)
        # Gap between cards and bottom hint must never select a PID.
        self.controls.tap(300, settings.PID_TOP + settings.PID_ROW - 3)
        self.controls.tap(500, 344)
        self.assertEqual(len(self.source.calls), 1)
        self.controls.profile_scroll = 123
        self.controls.tap(200, 56)
        self.assertEqual(self.controls.tab, 1)
        self.assertEqual(self.controls.device_scroll, 0)
        self.controls.tap(100, 56)
        self.assertEqual(self.controls.profile_scroll, 123)
        self.controls.input('down', 100, 220, 5)
        self.controls.input('up', 500, 223, 5.2)
        self.assertEqual(self.controls.page, 'gauge')

    def test_settings_cached_and_dashboard_restored(self):
        view = gauge.Gauge(self.source, headless=True, controls=self.controls)
        view.sweep_done = True
        view.draw_interactive_frame()
        self.swipe()
        full = view.draw_interactive_frame()
        self.assertEqual(full[0][0], (0, 0, 640, 360))
        self.assertEqual(view.draw_interactive_frame(), [])
        for tab in range(4):
            self.controls.tab = tab
            view.draw_interactive_frame()
        self.controls.page = 'gauge'
        self.assertEqual(view.draw_interactive_frame()[0][0], (0, 0, 640, 360))
        reference = gauge.Gauge(self.source, headless=True)
        reference.draw_frame(view.values, full=True)
        self.assertEqual(bytes(view.surface.get_data()), bytes(reference.surface.get_data()))

    def test_missing_pid_is_not_a_fabricated_value(self):
        view = gauge.Gauge(self.source, headless=True)
        values = {key: math.nan for key in settings.KEYS}
        view.draw_frame(values)
        self.assertEqual(view.shown_rpm[0], '--')
        self.assertTrue(all(v[0] == '--' for v in view.shown.values()))
        view.draw_frame(self.source.read())
        view.draw_frame(values)


class ReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_switch_disconnects_old_client_before_new_connect(self):
        calls = []
        class Link:
            def __init__(self, address):
                self.address = address
            async def connect(self):
                calls.append(('connect', self.address))
            async def disconnect(self):
                calls.append(('disconnect', self.address))
            async def command(self, command):
                await asyncio.sleep(.002)
                return ['410C1F40'] if command == '010C' else []
        source = settings.SettingsBleSource.__new__(settings.SettingsBleSource)
        source.lock, source.revision = threading.Lock(), 0
        profile = settings.profiles_in('/nonexistent')[0]
        source.configure('02:00:00:00:00:03', profile)
        with mock.patch.dict('sys.modules', obd_ble=types.SimpleNamespace(BleElm327=Link)):
            task = asyncio.create_task(source._session())
            try:
                await asyncio.sleep(.15)
                self.assertEqual(source.read()['rpm'], 2000)
                source.configure('02:00:00:00:00:04', profile)
                await asyncio.sleep(.3)
                self.assertLess(calls.index(('disconnect', '02:00:00:00:00:03')),
                                calls.index(('connect', '02:00:00:00:00:04')))
                source.configure('02:00:00:00:00:04', profile, False)
                await asyncio.sleep(.2)
                self.assertTrue(math.isnan(source.read()['rpm']))
                self.assertEqual(source.connection_status(), '蓝牙已断开')
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


@unittest.skipUnless(__import__('os').environ.get('GAUGE_TEST_NATIVE_SDL') == '1', 'opt-in SDL')
class NativeTouchTests(unittest.TestCase):
    def test_real_sdl_finger_events_rotation_and_duplicate_mouse(self):
        import os
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        screen = gauge.Screen.__new__(gauge.Screen)
        screen.sdl = ctypes.CDLL('libSDL2-2.0.so.0')
        screen._bind()
        self.assertEqual(screen.sdl.SDL_Init(gauge.SDL_INIT_VIDEO), 0)
        try:
            window = screen.sdl.SDL_CreateWindow(b'touch test', 0, 0, 1080, 1920, 0)
            self.assertTrue(window)
            screen.active_finger, screen.mouse_down = None, False
            screen.width, screen.height = 1080, 1920
            screen.poll_input()
            push = screen.sdl.SDL_PushEvent
            push.argtypes = [ctypes.POINTER(gauge.SDLEvent)]
            for kind, x, y in ((0x700, .5, .8), (0x702, .5, .4), (0x701, .5, .2)):
                event = gauge.SDLEvent()
                event.finger.type = kind
                event.finger.touchId, event.finger.fingerId = 1, 10
                event.finger.x, event.finger.y = x, y
                self.assertEqual(push(ctypes.byref(event)), 1)
            duplicate = gauge.SDLEvent()
            duplicate.button.type, duplicate.button.which = 0x401, 0xffffffff
            duplicate.button.button = 1
            self.assertEqual(push(ctypes.byref(duplicate)), 1)
            events = screen.poll_input()
            self.assertEqual([e[0] for e in events], ['down', 'move', 'up'])
            self.assertAlmostEqual(events[0][1], 512, places=3)
            self.assertAlmostEqual(events[-1][1], 128, places=3)
            self.assertIsNone(screen.active_finger)
        finally:
            screen.sdl.SDL_DestroyWindow.argtypes = [ctypes.c_void_p]
            screen.sdl.SDL_DestroyWindow(window)
            screen.sdl.SDL_Quit()


def export(directory):
    import cairo
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    case = SettingsTests()
    case.setUp()
    try:
        view = gauge.Gauge(case.source, headless=True, controls=case.controls)
        case.controls.page = 'settings'
        case.controls.devices = [('OBDII', '02:00:00:00:00:05')] + [
            ('BLE OBD %d' % i, 'AA:BB:CC:DD:EE:%02X' % i) for i in range(8)]
        for name in ('BMW F/G', 'BMW G OBD', 'BMW E', 'Subaru ZC6 CAN', 'Subaru ZD8', 'Toyota Supra A90', 'MINI R55'):
            case.config.profiles.append(dict(case.config.profiles[0], id=name, name=name,
                                            description='原格式车型包 · 11 信号 · rev 1'))
        for tab in range(4):
            case.controls.tab = tab
            view.draw_interactive_frame()
            out = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1920, 1080)
            cr = cairo.Context(out)
            cr.translate(0, 1080)
            cr.rotate(-math.pi / 2)
            cr.set_source_surface(view.surface, 0, 0)
            cr.paint()
            out.write_to_png(str(destination / ('settings-%d.png' % tab)))
    finally:
        case.doCleanups()


if __name__ == '__main__':
    import sys
    if '--export' in sys.argv:
        export(sys.argv[-1])
    else:
        unittest.main(verbosity=2)

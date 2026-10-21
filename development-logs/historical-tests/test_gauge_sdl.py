"""Dirty-frame regressions; run with system Python (Cairo + GI).

GAUGE_TEST_NATIVE_SDL=1 additionally checks real SDL2 through a dummy/software
renderer, without touching the phone's KMS display or kiosk service.
"""
import ctypes
import importlib.util
import os
import threading
import time
import unittest
import math
from unittest import mock

import cairo
if os.environ.get("GAUGE_TEST_MODULE_PATH"):
    spec = importlib.util.spec_from_file_location("gauge_candidate", os.environ["GAUGE_TEST_MODULE_PATH"])
    gauge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gauge)
else:
    import gauge_sdl as gauge


class TextureRecorder:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.data = bytearray(width * height * 4)
        self.calls = []

    def SDL_UpdateTexture(self, texture, rectangle, pixels, pitch):
        rect = ctypes.cast(rectangle, ctypes.POINTER(gauge.SDLRect)).contents
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        self.calls.append((x, y, w, h))
        address = pixels.value
        for row in range(h):
            start = ((y + row) * self.width + x) * 4
            self.data[start:start + w * 4] = ctypes.string_at(address + row * pitch, w * 4)
        return 0


def patterned_surface(width=24, height=20):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    for y in range(height):
        for x in range(width):
            cr.set_source_rgb(x / width, y / height, (x + y) / (width + height))
            cr.rectangle(x, y, 1, 1)
            cr.fill()
    surface.flush()
    return surface


def recorder_screen(width=24, height=20):
    screen = gauge.Screen.__new__(gauge.Screen)
    screen.sdl = TextureRecorder(width, height)
    screen.texture = ctypes.c_void_p(1)
    return screen


class UploadTests(unittest.TestCase):
    def test_hide_cursor_only_changes_visibility(self):
        calls = []

        class CursorSDL:
            def SDL_ShowCursor(self, toggle):
                calls.append(toggle)
                return 0

        screen = gauge.Screen.__new__(gauge.Screen)
        screen.sdl = CursorSDL()
        with mock.patch("builtins.print"):
            screen.hide_cursor()
        self.assertEqual(calls, [0, -1])

    def test_native_render_geometry(self):
        self.assertEqual((gauge.RW, gauge.RH), (1080, 1920))
        self.assertEqual(gauge.RS, 3.0)

    def test_sdl2_rectangle_abi(self):
        self.assertEqual(ctypes.sizeof(gauge.SDLRect), 4 * ctypes.sizeof(ctypes.c_int))
        self.assertEqual(gauge.SDLRect.h.offset, 3 * ctypes.sizeof(ctypes.c_int))

    def test_partial_upload_uses_rectangle_origin(self):
        surface = patterned_surface()
        screen = recorder_screen()
        screen.upload(surface, [(7, 5, 6, 4)])
        source = bytes(surface.get_data())
        for y in range(5, 9):
            start = (y * 24 + 7) * 4
            self.assertEqual(screen.sdl.data[start:start + 24], source[start:start + 24])
        self.assertEqual(screen.sdl.data[:24 * 5 * 4], bytes(24 * 5 * 4))

    def test_fractional_bounds_are_outward_rounded_and_clipped(self):
        screen = recorder_screen()
        screen.upload(patterned_surface(), [(2.2, 3.7, 4.2, 2.4), (-3, 18, 10, 9)])
        self.assertEqual(screen.sdl.calls, [(2, 3, 5, 4), (0, 18, 7, 2)])

    def test_empty_rectangles_are_skipped(self):
        screen = recorder_screen()
        screen.upload(patterned_surface(), [(40, 40, 2, 2), (3, 4, 0, 5)])
        self.assertEqual(screen.sdl.calls, [])

    def test_native_error_is_not_silenced(self):
        class FailingSDL:
            def SDL_UpdateTexture(self, *_args):
                return -1

            def SDL_GetError(self):
                return b"injected upload failure"

        screen = recorder_screen()
        screen.sdl = FailingSDL()
        with self.assertRaisesRegex(RuntimeError, "injected upload failure"):
            screen.upload(patterned_surface(), [(0, 0, 24, 20)])


class IncrementalTests(unittest.TestCase):
    def assert_frame_matches(self, actual, expected, width, height, stride, message):
        # A changed arc endpoint can make Cairo flatten the same curve
        # slightly differently. Permit only antialias coverage changes in a
        # two-native-pixel (<1 layout unit) edge neighbourhood for the larger,
        # thick rounded bars; solid interiors must still match.
        changed = {offset // 4 for offset, (a, b) in enumerate(zip(actual, expected))
                   if abs(a - b) > 1}
        for source, target in ((actual, expected), (expected, actual)):
            for pixel in changed:
                x, y = pixel % width, pixel // width
                offsets = [yy * stride + xx * 4
                           for yy in range(max(0, y - 2), min(height, y + 3))
                           for xx in range(max(0, x - 2), min(width, x + 3))]
                for channel in range(4):
                    value = source[y * stride + x * 4 + channel]
                    neighbours = [target[offset + channel] for offset in offsets]
                    if not min(neighbours) - 2 <= value <= max(neighbours) + 2:
                        self.fail("%s: non-edge mismatch at (%d, %d), channel %d"
                                  % (message, x, y, channel))

    def test_incremental_matches_fresh_full_frame(self):
        incremental = gauge.Gauge(gauge.DemoSource(), headless=True)
        reference = gauge.Gauge(gauge.DemoSource(), headless=True)
        # Small arc hops, high/low jumps, wrap around quadrant extrema, zero,
        # unchanged formatted digits crossing colour thresholds, and long text.
        rpms = [0, 30, 90, 771, 2850, 3000, 7200, 7999, 8000, 4300, 100, 0]
        for index, rpm in enumerate(rpms):
            values = dict(rpm=rpm, battery=9.8 if index % 2 else 13.9,
                          coolant=104.6 if index % 2 else 105.2,
                          oil=111.6 if index % 2 else 112.2, speed=index * 23)
            incremental.draw_frame(values)
            reference.draw_frame(values, full=True)
            actual = bytes(incremental.surface.get_data())
            expected = bytes(reference.surface.get_data())
            try:
                self.assert_frame_matches(actual, expected, gauge.RW, gauge.RH,
                                          incremental.surface.get_stride(),
                                          "frame %d / RPM %s" % (index, rpm))
            except AssertionError:
                incremental.surface.write_to_png("native1080-mismatch-incremental.png")
                reference.surface.write_to_png("native1080-mismatch-reference.png")
                raise

    def test_merged_regions_are_disjoint(self):
        # New box bridges two previously separate boxes; one-pass merge is
        # insufficient and the later repaint can erase the earlier content.
        regions = [((0, 0, 10, 10), 1), ((20, 0, 10, 10), 2), ((8, 0, 14, 10), 4)]
        merged = gauge.Gauge.merge_regions(regions)
        self.assertEqual(merged, [[(0, 0, 30, 10), 7]])

    def test_large_dial_layout_and_digit_bounds(self):
        instance = gauge.Gauge(gauge.DemoSource(), headless=True)
        cx, cy, radius = gauge.RPM_CENTER
        self.assertGreaterEqual(radius, 150)
        reach = instance.arc_radius() + instance.arc_width() / 2 + 4
        self.assertGreater(cx - reach, 0)
        # Enlarged hex tips occupy the gap BETWEEN the four corner cards.
        reach_y = instance.arc_radius() * math.sqrt(3)/2 + instance.arc_width()/2 + 4
        self.assertGreater(cy - reach_y, 6)
        self.assertLess(cy + reach_y, 354)
        self.assertGreater(cy, gauge.CARD_Y[0] + gauge.CARD_H + 10)
        self.assertLess(cy, gauge.CARD_Y[1] - 10)
        for index, card in enumerate(gauge.CARDS):
            x, y, _label, _key, _fmt, _unit = card
            bx, by, bw, bh = instance.card_value_box(index)
            self.assertGreaterEqual(bx, x)
            self.assertGreater(by, y + 30)  # Clear of the label/unit line.
            self.assertLessEqual(bx + bw, x + gauge.CARD_W)
            self.assertLessEqual(by + bh, y + gauge.CARD_H)
        for label in ('0', '2860', '7999', '8000', '--'):
            width = sum(instance.big_digits.glyphs[c][1] for c in label)
            self.assertLessEqual(width + 6, instance.rpm_value_box()[2])

    def test_unavailable_data_recovers_in_incremental_frame(self):
        incremental = gauge.Gauge(gauge.DemoSource(), headless=True)
        reference = gauge.Gauge(gauge.DemoSource(), headless=True)
        for rpm in (8000, float('nan'), 0, 2860):
            values = dict(rpm=rpm, battery=13.8, coolant=92, oil=84, speed=28)
            incremental.draw_frame(values)
            reference.draw_frame(values, full=True)
            self.assert_frame_matches(bytes(incremental.surface.get_data()),
                                      bytes(reference.surface.get_data()),
                                      gauge.RW, gauge.RH, incremental.surface.get_stride(),
                                      'missing/recovered RPM %s' % rpm)

    def test_hex_corner_progress_matches_full_repaint(self):
        incremental = gauge.Gauge(gauge.DemoSource(), headless=True)
        reference = gauge.Gauge(gauge.DemoSource(), headless=True)
        for rpm in (1330, 1336, 3109, 3114, 4886, 4892, 6663, 6670):
            values = dict(rpm=rpm, battery=13.8, coolant=92, oil=84, speed=28)
            incremental.draw_frame(values)
            reference.draw_frame(values, full=True)
            self.assert_frame_matches(bytes(incremental.surface.get_data()),
                                      bytes(reference.surface.get_data()),
                                      gauge.RW, gauge.RH, incremental.surface.get_stride(),
                                      'hex corner RPM %d' % rpm)


class PipelineTests(unittest.TestCase):
    def test_sdl_stays_on_main_and_upload_surface_is_stable(self):
        instance = gauge.Gauge(gauge.DemoSource(), headless=True)
        main_id = threading.get_ident()
        owner = self
        painted = []
        original_draw = instance.draw_frame

        def worker_draw(values, **kwargs):
            owner.assertNotEqual(threading.get_ident(), main_id)
            owner.assertFalse(kwargs["upload"])
            painted.append(True)
            return original_draw(values, **kwargs)

        class FakeScreen:
            count = 0

            def upload(self, surface, boxes):
                owner.assertEqual(threading.get_ident(), main_id)
                before = bytes(surface.get_data())
                time.sleep(0.001)
                owner.assertEqual(before, bytes(surface.get_data()))

            def present(self):
                owner.assertEqual(threading.get_ident(), main_id)
                time.sleep(0.002)
                self.count += 1
                if self.count >= 8:
                    instance._stop()

        instance.draw_frame = worker_draw
        instance.screen = FakeScreen()
        with mock.patch.object(gauge.signal, "signal"):
            instance.run()
        self.assertEqual(instance.screen.count, 8)
        self.assertEqual(instance.total_frames, 8)
        self.assertGreaterEqual(len(painted), 8)

    def test_worker_exception_is_propagated(self):
        class BrokenSource:
            def read(self):
                raise ValueError("injected source failure")

        instance = gauge.Gauge(BrokenSource(), headless=True)
        with mock.patch.object(gauge.signal, "signal"):
            with self.assertRaisesRegex(RuntimeError, "Cairo render worker failed") as result:
                instance.run()
        self.assertIsInstance(result.exception.__cause__, ValueError)
        self.assertFalse(instance.running)


@unittest.skipUnless(os.environ.get("GAUGE_TEST_NATIVE_SDL") == "1", "opt-in real SDL2")
class NativeSDLTests(unittest.TestCase):
    def test_real_sdl_partial_texture_matches_source(self):
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_RENDER_DRIVER"] = "software"
        screen = gauge.Screen.__new__(gauge.Screen)
        screen.sdl = ctypes.CDLL("libSDL2-2.0.so.0")
        screen._bind()
        sdl = screen.sdl
        self.assertEqual(sdl.SDL_Init(gauge.SDL_INIT_VIDEO), 0)
        window = renderer = texture = None
        try:
            window = sdl.SDL_CreateWindow(b"upload regression", 0, 0, 24, 20, 0)
            self.assertTrue(window)
            screen.hide_cursor()
            self.assertEqual(sdl.SDL_ShowCursor(-1), 0)
            renderer = sdl.SDL_CreateRenderer(window, -1, 1)  # SOFTWARE
            self.assertTrue(renderer)
            texture = sdl.SDL_CreateTexture(renderer, gauge.SDL_PIXELFORMAT_ARGB8888,
                                            gauge.SDL_TEXTUREACCESS_STREAMING, 24, 20)
            self.assertTrue(texture)
            screen.window, screen.renderer, screen.texture = window, renderer, texture
            sdl.SDL_SetTextureBlendMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self.assertEqual(sdl.SDL_SetTextureBlendMode(texture, 0), 0)
            surface = patterned_surface()
            screen.upload(surface, [(0, 0, 24, 20)])
            cr = cairo.Context(surface)
            cr.set_source_rgb(0.8, 0.1, 0.2)
            cr.rectangle(7, 5, 6, 4)
            cr.fill()
            surface.flush()
            screen.upload(surface, [(7, 5, 6, 4)])
            self.assertEqual(sdl.SDL_RenderCopy(renderer, texture, None, None), 0)
            sdl.SDL_RenderReadPixels.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                                ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
            output = ctypes.create_string_buffer(24 * 20 * 4)
            self.assertEqual(sdl.SDL_RenderReadPixels(renderer, None,
                              gauge.SDL_PIXELFORMAT_ARGB8888, output, 24 * 4), 0)
            self.assertEqual(output.raw, bytes(surface.get_data()))
        finally:
            for item, name in ((texture, "SDL_DestroyTexture"),
                               (renderer, "SDL_DestroyRenderer"), (window, "SDL_DestroyWindow")):
                if item:
                    function = getattr(sdl, name)
                    function.argtypes = [ctypes.c_void_p]
                    function(item)
            sdl.SDL_Quit()


if __name__ == "__main__":
    unittest.main(verbosity=2)

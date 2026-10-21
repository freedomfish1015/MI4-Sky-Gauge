#!/usr/bin/env python3
"""OBD dashboard on bare KMS/DRM.

Layout is authored in a 640x360 landscape space. The vector artwork and fonts
are rasterised at 3 render pixels per layout unit, rotated 90 degrees into the
panel's native 1080x1920 surface (1920x1080 landscape). The texture is displayed
pixel-for-pixel, not enlarged from a lower-resolution image.

Performance model: Cairo is a CPU rasteriser, so the only way to get both
sharpness and 60 fps is to stop redrawing everything. The static artwork
(dial track, ticks, labels, card frames) is rasterised once into a cached
surface. Every frame repaints only the regions that actually changed -- the
arc swept by the needle since the previous frame and the digits -- and uploads
just those rectangles to the GPU.
"""
import asyncio
import ctypes
import math
import os
from pathlib import Path
import queue
import signal
import sys
import threading
import time

os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
os.environ.setdefault("SDL_RENDER_DRIVER", "opengles2")
os.environ.setdefault("SDL_VIDEO_KMSDRM_DEVICE", "/dev/dri/card0")

_drawing_ready = False


def load_drawing():
    """Keep the boot SDL window independent of the dashboard font stack."""
    global cairo, Pango, PangoCairo, _drawing_ready
    if not _drawing_ready:
        import cairo
        import gi
        gi.require_version('Pango', '1.0')
        gi.require_version('PangoCairo', '1.0')
        from gi.repository import Pango, PangoCairo
        _drawing_ready = True

# ---------------------------------------------------------------- geometry

LW, LH = 640, 360              # logical landscape layout space
RS = 3.0                       # Vector/layout units -> native render pixels
RW, RH = int(LH * RS), int(LW * RS)   # Native 1080 x 1920, no texture upscaling
FPS_TARGET = int(os.environ.get("GAUGE_FPS", "60"))

# ----------------------------------------------------------------- palette

BG = (0.965, 0.982, 0.994)
CARD_BG = (1.0, 1.0, 1.0)
CARD_EDGE = (0.768, 0.835, 0.898)
WHITE = (0.102, 0.176, 0.247)  # Historical name: foreground ink, now dark on white.
DIM = (0.365, 0.455, 0.533)
BLUE = (0.180, 0.420, 0.635)
CYAN = (0.310, 0.655, 0.812)
RED = (0.733, 0.133, 0.231)
TRACK = (0.812, 0.863, 0.910)

# ------------------------------------------------------------------ layout

# Central hexagonal engine HUD, flanked by clipped-corner telemetry pods.
RPM_CENTER = (320, 180, 190)
CARD_W, CARD_H = 156, 112
CARD_X = (12, 472)
CARD_Y = (24, 224)

# x, y, label, source key, format, unit
CARDS = [
    (CARD_X[0], CARD_Y[0], "电压", "battery", "%.1f", "V"),
    (CARD_X[1], CARD_Y[0], "水温", "coolant", "%.0f", "°C"),
    (CARD_X[0], CARD_Y[1], "油温", "oil", "%.0f", "°C"),
    (CARD_X[1], CARD_Y[1], "时速", "speed", "%.0f", "km/h"),
]

RPM_MAX = 8000.0
RPM_STEP = 150.0
COOLANT_STEP = 1.2
SPEED_MAX = 240.0
SPEED_STEP = 3.0
RPM_REDLINE = 7000.0
SPEED_REDLINE = 180.0

# Bit mask describing which dynamic element lives inside a dirty region.
REGION_ARC = 1
REGION_RPM = 2
REGION_CARD0 = 4
REGION_SPEED_ARC = 64
REGION_SPEED = 128
REGION_MOTION = 256
REGION_ALL = (REGION_ARC | REGION_RPM | REGION_SPEED_ARC | REGION_SPEED | REGION_MOTION |
              sum(REGION_CARD0 << i for i in range(4)))


def approach(current, target, step):
    if not math.isfinite(target) or not math.isfinite(current):
        return target
    delta = target - current
    if abs(delta) <= step:
        return target
    return current + (step if delta > 0 else -step)


def responsive_approach(current, target, minimum_step, elapsed):
    """Keep small changes immediate; settle large jumps without FPS-dependent lag."""
    if not math.isfinite(current) or not math.isfinite(target):
        return target
    alpha = -math.expm1(-max(0, min(.1, elapsed))/.04)
    return approach(current, target, max(minimum_step, abs(target-current)*alpha))


def value_color(key, value):
    if not math.isfinite(value):
        return DIM
    if key == "coolant" and value >= 105:
        return RED
    if key == "oil" and value >= 112:
        return RED
    if key == "battery" and value < 11.0:
        return RED
    return WHITE


# ------------------------------------------------------------------ data feed

class DemoSource:
    name = "DEMO"

    def __init__(self):
        self.phase = 0.0
        self.values = {"rpm": 0.0, "coolant": 62.0, "oil": 55.0,
                       "speed": 0.0, "battery": 12.5}

    def read(self):
        self.phase += 0.045
        base = 820 + 260 * math.sin(self.phase * 0.7) + 120 * math.sin(self.phase * 2.3)
        blip = 1500 * max(0.0, math.sin(self.phase * 0.31)) ** 3
        self.values["rpm"] = approach(self.values["rpm"], base + blip, 90)
        self.values["coolant"] = min(90.0, self.values["coolant"] + 0.08)
        self.values["oil"] = min(84.0, self.values["oil"] + 0.06)
        self.values["speed"] = max(0.0, (self.values["rpm"] - 800) * 0.012)
        self.values["battery"] = 13.9 if self.values["rpm"] > 900 else 12.5
        return dict(self.values)


class BleSource:
    """Reads the ELM327 simulator over BLE and keeps the latest values."""

    def __init__(self, address):
        self.address = address
        self.name = "BLE " + address[-5:].replace(":", "")
        self.lock = threading.Lock()
        self.values = {"rpm": 0.0, "coolant": 60.0, "oil": 60.0,
                       "speed": 0.0, "battery": 12.0}
        self.connected = False
        self.reported = False
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            asyncio.run(self._session())
        except Exception as exc:
            print("BLE worker stopped: %r" % (exc,), flush=True)

    async def _session(self):
        from obd_ble import BleElm327

        while True:
            link = BleElm327(self.address)
            try:
                await link.connect()
                await link.command("ATE0")
                await link.command("ATS0")
                self.connected = True
                print("BLE connected %s" % self.address, flush=True)
                rounds = 0
                while True:
                    rpm = await link.read_pid("rpm")
                    extra = {}
                    if rounds % 12 == 0:
                        extra["coolant"] = await link.read_pid("coolant")
                    if rounds % 30 == 0:
                        extra["speed"] = await link.read_pid("speed")
                        extra["battery"] = await link.read_pid("battery")
                    if rounds % 60 == 0:
                        extra["oil"] = await link.read_pid("oil")
                    rounds += 1
                    if not self.reported:
                        self.reported = True
                        print("BLE first read rpm=%s coolant=%s"
                              % (rpm, extra.get("coolant")), flush=True)
                    with self.lock:
                        if rpm is not None:
                            self.values["rpm"] = float(rpm)
                        for key, value in extra.items():
                            if value is not None:
                                self.values[key] = float(value)
                    await asyncio.sleep(0.02)
            except Exception as exc:
                self.connected = False
                print("BLE error: %r" % (exc,), flush=True)
                await asyncio.sleep(2.0)
            finally:
                try:
                    await link.disconnect()
                except Exception:
                    pass

    def read(self):
        with self.lock:
            return dict(self.values)


# -------------------------------------------------------------------- output

SDL_INIT_VIDEO = 0x00000020
SDL_WINDOWPOS_UNDEFINED = 0x1FFF0000
SDL_WINDOW_FULLSCREEN = 0x00000001
SDL_RENDERER_ACCELERATED = 0x00000002
SDL_RENDERER_PRESENTVSYNC = 0x00000004
SDL_TEXTUREACCESS_STREAMING = 1
SDL_PIXELFORMAT_ARGB8888 = 0x16362004
SDL_SCALEMODE_NEAREST = 0


class SDLRect(ctypes.Structure):
    # SDL2 uses four C ints (16 bytes), not SDL1's 16-bit fields.
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int),
                ("w", ctypes.c_int), ("h", ctypes.c_int)]


class SDLFingerEvent(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint32), ('timestamp', ctypes.c_uint32),
                ('touchId', ctypes.c_int64), ('fingerId', ctypes.c_int64),
                ('x', ctypes.c_float), ('y', ctypes.c_float),
                ('dx', ctypes.c_float), ('dy', ctypes.c_float),
                ('pressure', ctypes.c_float), ('windowID', ctypes.c_uint32)]


class SDLMouseButton(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint32), ('timestamp', ctypes.c_uint32),
                ('windowID', ctypes.c_uint32), ('which', ctypes.c_uint32),
                ('button', ctypes.c_uint8), ('state', ctypes.c_uint8),
                ('clicks', ctypes.c_uint8), ('padding', ctypes.c_uint8),
                ('x', ctypes.c_int), ('y', ctypes.c_int)]


class SDLMouseMotion(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint32), ('timestamp', ctypes.c_uint32),
                ('windowID', ctypes.c_uint32), ('which', ctypes.c_uint32),
                ('state', ctypes.c_uint32), ('x', ctypes.c_int),
                ('y', ctypes.c_int), ('xrel', ctypes.c_int), ('yrel', ctypes.c_int)]


class SDLEvent(ctypes.Union):
    _fields_ = [('type', ctypes.c_uint32), ('finger', SDLFingerEvent),
                ('button', SDLMouseButton), ('motion', SDLMouseMotion),
                ('padding', ctypes.c_uint8 * 56), ('align', ctypes.c_uint64)]


def pixel_box(box, width, height):
    """Enclose fractional dirty bounds in whole pixels, clipped to the image."""
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return None
    x0, y0 = max(0, math.floor(x)), max(0, math.floor(y))
    x1, y1 = min(width, math.ceil(x + w)), min(height, math.ceil(y + h))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1 - x0, y1 - y0


class SDLDisplayMode(ctypes.Structure):
    _fields_ = [("format", ctypes.c_uint32), ("w", ctypes.c_int),
                ("h", ctypes.c_int), ("refresh_rate", ctypes.c_int),
                ("driverdata", ctypes.c_void_p)]


class Screen:
    """Thin SDL2 wrapper around one streaming texture.

    pygame's Texture.update() re-validates and re-converts on every call, and
    measured 15 ms per upload on this SoC -- two of those per frame capped the
    gauge at 25 fps however little had actually changed. Calling
    SDL_UpdateTexture with an explicit rectangle copies just that rectangle and
    costs a fraction of a millisecond.
    """

    def __init__(self, tex_w, tex_h, vsync=True):
        self.texture_width, self.texture_height = tex_w, tex_h
        self.sdl = ctypes.CDLL("libSDL2-2.0.so.0")
        self._bind()
        if self.sdl.SDL_Init(SDL_INIT_VIDEO) != 0:
            raise RuntimeError("SDL_Init failed")

        mode = SDLDisplayMode()
        self.sdl.SDL_GetDesktopDisplayMode(0, ctypes.byref(mode))
        self.width, self.height = mode.w, mode.h
        self.refresh = mode.refresh_rate or 60

        self.window = self.sdl.SDL_CreateWindow(
            b"OBD Gauge", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
            self.width, self.height, SDL_WINDOW_FULLSCREEN)
        if not self.window:
            raise RuntimeError("SDL_CreateWindow failed: %s"
                               % self.sdl.SDL_GetError().decode())
        self.hide_cursor()

        flags = SDL_RENDERER_ACCELERATED
        if vsync:
            flags |= SDL_RENDERER_PRESENTVSYNC
        self.renderer = self.sdl.SDL_CreateRenderer(self.window, -1, flags)
        if not self.renderer:
            raise RuntimeError("SDL_CreateRenderer failed: %s"
                               % self.sdl.SDL_GetError().decode())

        output_w, output_h = ctypes.c_int(), ctypes.c_int()
        if self.sdl.SDL_GetRendererOutputSize(self.renderer, ctypes.byref(output_w),
                                              ctypes.byref(output_h)) != 0:
            raise RuntimeError("SDL_GetRendererOutputSize failed: %s"
                               % self.sdl.SDL_GetError().decode())
        if (output_w.value, output_h.value) != (tex_w, tex_h):
            raise RuntimeError("Native rendering requires texture/output equality: "
                               "%dx%d texture vs %dx%d output"
                               % (tex_w, tex_h, output_w.value, output_h.value))
        print("Native texture %dx%d -> output %dx%d (1:1, no upscaling)"
              % (tex_w, tex_h, output_w.value, output_h.value), flush=True)

        self.texture = self.sdl.SDL_CreateTexture(
            self.renderer, SDL_PIXELFORMAT_ARGB8888,
            SDL_TEXTUREACCESS_STREAMING, tex_w, tex_h)
        if not self.texture:
            raise RuntimeError("SDL_CreateTexture failed: %s"
                               % self.sdl.SDL_GetError().decode())

        # There is no resize at equal texture/output dimensions; retain nearest
        # defensively so a future mode change cannot silently blur the image.
        self.sdl.SDL_SetTextureScaleMode(self.texture, SDL_SCALEMODE_NEAREST)
        self.active_finger = None
        self.mouse_down = False

    def _bind(self):
        s = self.sdl
        s.SDL_Init.argtypes = [ctypes.c_uint32]
        s.SDL_GetError.restype = ctypes.c_char_p
        s.SDL_ShowCursor.argtypes = [ctypes.c_int]
        s.SDL_ShowCursor.restype = ctypes.c_int
        s.SDL_GetDesktopDisplayMode.argtypes = [ctypes.c_int,
                                                ctypes.POINTER(SDLDisplayMode)]
        s.SDL_CreateWindow.restype = ctypes.c_void_p
        s.SDL_CreateWindow.argtypes = [ctypes.c_char_p, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_uint32]
        s.SDL_CreateRenderer.restype = ctypes.c_void_p
        s.SDL_CreateRenderer.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                         ctypes.c_uint32]
        s.SDL_GetRendererOutputSize.restype = ctypes.c_int
        s.SDL_GetRendererOutputSize.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_int),
                                                ctypes.POINTER(ctypes.c_int)]
        s.SDL_CreateTexture.restype = ctypes.c_void_p
        s.SDL_CreateTexture.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int]
        s.SDL_SetTextureScaleMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
        s.SDL_UpdateTexture.restype = ctypes.c_int
        s.SDL_UpdateTexture.argtypes = [ctypes.c_void_p, ctypes.POINTER(SDLRect),
                                        ctypes.c_void_p, ctypes.c_int]
        s.SDL_RenderCopy.restype = ctypes.c_int
        s.SDL_RenderCopy.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.POINTER(SDLRect),
                                     ctypes.POINTER(SDLRect)]
        s.SDL_RenderPresent.argtypes = [ctypes.c_void_p]
        s.SDL_PumpEvents.argtypes = []
        s.SDL_PollEvent.argtypes = [ctypes.POINTER(SDLEvent)]
        s.SDL_PollEvent.restype = ctypes.c_int

    def poll_input(self):
        from gauge_settings import logical_point
        events = []
        event = SDLEvent()
        for _ in range(128):
            if not self.sdl.SDL_PollEvent(ctypes.byref(event)):
                break
            if event.type in (0x700, 0x701, 0x702):
                f = event.finger
                identity = (f.touchId, f.fingerId)
                if event.type == 0x700 and self.active_finger is None:
                    self.active_finger = identity
                if self.active_finger != identity:
                    continue
                kind = {0x700: 'down', 0x701: 'up', 0x702: 'move'}[event.type]
                events.append((kind, *logical_point(f.x, f.y)))
                if kind == 'up':
                    self.active_finger = None
            elif event.type in (0x401, 0x402):
                b = event.button
                if b.which == 0xffffffff or b.button != 1:
                    continue  # SDL's synthetic touch mouse would duplicate taps.
                self.mouse_down = event.type == 0x401
                events.append(('down' if self.mouse_down else 'up',
                               *logical_point(b.x / self.width, b.y / self.height)))
            elif event.type == 0x400 and self.mouse_down:
                m = event.motion
                if m.which != 0xffffffff:
                    events.append(('move', *logical_point(m.x / self.width, m.y / self.height)))
        return events

    def hide_cursor(self):
        # Hide only SDL's pointer. Touch/mouse event delivery and input
        # devices remain enabled for touchscreen controls.
        if self.sdl.SDL_ShowCursor(0) < 0:
            raise RuntimeError("SDL_ShowCursor failed: %s" % self.sdl.SDL_GetError().decode())
        state = self.sdl.SDL_ShowCursor(-1)
        if state != 0:
            raise RuntimeError("Mouse cursor was not hidden: SDL state=%d" % state)
        print("Mouse cursor hidden (SDL cursor state=0)", flush=True)

    def replace_texture(self, pixel_format):
        """Keep the KMS window/renderer across video -> dashboard handoff."""
        texture = self.sdl.SDL_CreateTexture(self.renderer, pixel_format,
                    SDL_TEXTUREACCESS_STREAMING, self.texture_width, self.texture_height)
        if not texture:
            raise RuntimeError('Replacement texture failed: %s' % self.sdl.SDL_GetError().decode())
        self.sdl.SDL_DestroyTexture.argtypes = [ctypes.c_void_p]
        self.sdl.SDL_DestroyTexture(self.texture)
        self.texture = texture
        self.sdl.SDL_SetTextureScaleMode(self.texture, SDL_SCALEMODE_NEAREST)

    def upload(self, surface, boxes):
        surface.flush()
        data = surface.get_data()
        addr = ctypes.addressof(ctypes.c_char.from_buffer(data))
        pitch = surface.get_stride()
        for box in boxes:
            bounds = pixel_box(box, surface.get_width(), surface.get_height())
            if bounds is None:
                continue
            x, y, w, h = bounds
            rect = SDLRect(x, y, w, h)
            # pixels points at THIS rectangle's top-left, with the original
            # full-surface row pitch. SDL does not apply x/y to this pointer.
            pixels = ctypes.c_void_p(addr + y * pitch + x * 4)
            if self.sdl.SDL_UpdateTexture(self.texture, ctypes.byref(rect), pixels, pitch) != 0:
                raise RuntimeError("SDL_UpdateTexture failed for %r: %s"
                                   % (bounds, self.sdl.SDL_GetError().decode()))

    def present(self):
        if self.sdl.SDL_RenderCopy(self.renderer, self.texture, None, None) != 0:
            raise RuntimeError("SDL_RenderCopy failed: %s" % self.sdl.SDL_GetError().decode())
        self.sdl.SDL_RenderPresent(self.renderer)
        self.sdl.SDL_PumpEvents()


# ---------------------------------------------------------------------- text

def font_desc(size, weight="normal", family="DejaVu Sans"):
    """Build a font description whose size is in layout pixels, not points.

    Pango's default size unit is points, which at 96 dpi inflates everything
    by 4/3 -- that is why the first draft had a 66 px figure where 50 was
    asked for. set_absolute_size pins it to pixels.
    """
    load_drawing()
    desc = Pango.FontDescription()
    desc.set_family(family)
    desc.set_weight(Pango.Weight.BOLD if str(weight).lower() == "bold"
                    else Pango.Weight.NORMAL)
    desc.set_absolute_size(size * Pango.SCALE)
    return desc


class Digits:
    """Pre-rasterised numerals.

    Pango layout + shaping costs a couple of milliseconds per string, which is
    what kept the frame time just above the 16.6 ms vsync budget and forced
    30 fps. Each numeral is rasterised once at device resolution and blitted as
    an alpha mask, so colouring is free and drawing a five-digit figure is five
    mask operations.
    """

    GLYPHS = "0123456789.-"

    def __init__(self, size, dpr=RS, weight="bold", family="DejaVu Sans"):
        load_drawing()
        self.size = size
        self.glyphs = {}
        box = int(math.ceil(size * dpr * 2.4))
        for char in self.GLYPHS:
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, box, box)
            surface.set_device_scale(dpr, dpr)
            cr = cairo.Context(surface)
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(font_desc(size, weight, family))
            layout.set_text(char, -1)
            width, height = layout.get_pixel_size()
            cr.set_source_rgb(1.0, 1.0, 1.0)
            PangoCairo.show_layout(cr, layout)
            surface.flush()
            self.glyphs[char] = (surface, width, height)

    def draw(self, cr, cx, cy, text, color=WHITE):
        widths = [self.glyphs.get(c, self.glyphs["0"])[1] for c in text]
        x = cx - sum(widths) / 2.0
        cr.set_source_rgb(*color)
        for char, advance in zip(text, widths):
            surface, glyph_w, glyph_h = self.glyphs.get(char, self.glyphs["0"])
            cr.mask_surface(surface, x, cy - glyph_h / 2.0)
            x += advance


# --------------------------------------------------------------------- gauge

class Gauge:
    theme = dict(background=BG, text=WHITE, dim=DIM, accent=BLUE, track=TRACK)

    def __init__(self, source, headless=False, upright=False, controls=None, startup_screen=None,
                 power=None, static_cache=None):
        load_drawing()
        self.headless = headless
        self.upright = upright
        self.source = source
        self.rei_portrait = None
        portrait = Path(__file__).resolve().parent / 'assets/rei-reference.png'
        if portrait.is_file():
            self.rei_portrait = cairo.ImageSurface.create_from_png(str(portrait))
        self.controls = controls
        from gauge_telemetry import Telemetry
        self.telemetry = Telemetry(enabled=bool(controls) and not headless)
        if controls is not None:
            controls.telemetry = self.telemetry
        self.telemetry_paint_at = 0
        from gauge_tracks import TrackView
        self.tracks = TrackView()
        self.route_paint_at = 0
        if controls is not None:
            controls.track_view = self.tracks
        from gauge_motion import MotionClient
        self.motion = controls.motion if controls else MotionClient()
        self.motion_state = {}
        self.motion_signature = None
        self.motion_visual_box = None
        self.motion_envelope_signature = None
        from gauge_windows import DEFAULT_WINDOWS, card_layout, normalize_windows
        self.window_bindings = normalize_windows(controls.config.data.get('windows') if controls else DEFAULT_WINDOWS)
        self.window_profile = controls.config.data['profile'] if controls else None
        self.cards = card_layout(CARDS, self.window_bindings, controls.config.profile if controls else None)
        self.power = power
        self.power_state = None
        self.power_backdrop = None
        self.input_events = queue.Queue(maxsize=512)
        self.ui_state = None
        self.previous_page = 'gauge'

        self.use_vsync = os.environ.get("GAUGE_VSYNC", "1") != "0"
        if headless:
            self.screen = None
            self.screen_w, self.screen_h = 1080, 1920
        else:
            self.screen = startup_screen or Screen(RW, RH, vsync=self.use_vsync)
            self.screen_w = self.screen.width
            self.screen_h = self.screen.height
            print("KMS mode %dx%d @%dHz vsync=%s"
                  % (self.screen_w, self.screen_h, self.screen.refresh,
                     self.use_vsync), flush=True)

        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, RW, RH)
        self.static = cairo.ImageSurface(cairo.FORMAT_ARGB32, RW, RH)
        # Reused every frame: constructing a context per dirty rectangle and
        # re-wrapping the cached surface cost more than the drawing itself.
        self.cr = cairo.Context(self.surface)

        radius = RPM_CENTER[2]
        self.big_digits = Digits(31)
        self.speed_digits = Digits(43)
        self.card_digits = Digits(30)

        self.progress_grad = cairo.LinearGradient(
            RPM_CENTER[0] - radius, RPM_CENTER[1] - radius,
            RPM_CENTER[0] + radius, RPM_CENTER[1] + radius)
        self.progress_grad.add_color_stop_rgb(0.0, *BLUE)
        self.progress_grad.add_color_stop_rgb(1.0, *CYAN)
        # Speed reads from the left; give it a cooler ramp so the two halves
        # stay distinguishable at a glance.
        self.speed_grad = cairo.LinearGradient(
            RPM_CENTER[0] - radius, RPM_CENTER[1] + radius,
            RPM_CENTER[0], RPM_CENTER[1] - radius)
        self.speed_grad.add_color_stop_rgb(0.0, *CYAN)
        self.speed_grad.add_color_stop_rgb(1.0, *BLUE)

        # The boot launcher can hand over a layer rasterised while the startup
        # movie was still playing, which removes the visible stall right after
        # the handoff. Only reuse it when the window layout actually matches.
        if static_cache is not None and static_cache.get('cards') == self.cards:
            self.static = static_cache['surface']
        else:
            self.build_static()

        # The pattern must be created AFTER self.static is finalised. Binding
        # it earlier made every dirty-rectangle repaint restore the blank
        # surface and the whole dashboard decoration disappeared.
        self.static_pattern = cairo.SurfacePattern(self.static)
        self.static_pattern.set_filter(cairo.FILTER_NEAREST)

        self.values = {"rpm": 0.0, "coolant": 60.0, "oil": 55.0,
                       "speed": 0.0, "battery": 12.0}
        self.prev = {"rpm": 0.0, "coolant": 60.0, "oil": 55.0,
                     "speed": 0.0, "battery": 12.0}
        self.prev_arc = None
        self.prev_speed = 0.0
        self.shown = {}
        self.shown_rpm = None
        self.shown_speed = None
        self.sweep_done = False
        self.sweep_start = time.monotonic()
        self.frames = 0
        self.total_frames = 0  # Lifetime counter; FPS accounting resets frames.
        self.dump_path = None
        self.dump_frame = 300
        dump = os.environ.get("GAUGE_DUMP")
        if dump:
            path, separator, frame = dump.rpartition(":")
            self.dump_path = path if separator else dump
            self.dump_frame = int(frame) if separator else 300
            if not self.dump_path or self.dump_frame < 0:
                raise ValueError("GAUGE_DUMP must be path[:nonnegative_frame]")
        self.fps_window = time.monotonic()
        self.prof_paint = self.prof_upload = self.prof_present = 0.0
        self.running = True
        if startup_screen is not None:
            # Retain the last video frame while fonts/static artwork are built.
            # Only then replace the texture and show the first dashboard frame.
            self.values = self.source.read()
            startup_screen.replace_texture(SDL_PIXELFORMAT_ARGB8888)
            self.draw_frame(self.values, full=True)
            self.sweep_start = self.fps_window = time.monotonic()

    # ------------------------------------------------------------ transforms

    def apply_layout(self, cr):
        """Rasterise 640x360 layout units onto the native 1080x1920 surface."""
        cr.scale(RS, RS)
        cr.translate(LH, 0)
        cr.rotate(math.pi / 2)

    def to_device(self, x, y, w, h):
        """Axis-aligned box in layout space -> box in surface pixels."""
        dx0 = RW - RS * (y + h)
        dx1 = RW - RS * y
        dy0 = RS * x
        dy1 = RS * (x + w)
        return (dx0, dy0, dx1 - dx0, dy1 - dy0)

    # ------------------------------------------------------------- primitives

    def text(self, cr, x, y, value, size, color, weight="normal",
             align="center", family="DejaVu Sans"):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(font_desc(size, weight, family))
        layout.set_text(value, -1)
        width, height = layout.get_pixel_size()
        if align == "center":
            cr.move_to(x - width / 2.0, y - height / 2.0)
        elif align == "right":
            cr.move_to(x - width, y - height / 2.0)
        else:
            cr.move_to(x, y - height / 2.0)
        cr.set_source_rgb(*color)
        PangoCairo.show_layout(cr, layout)
        return width, height

    def rounded_card(self, cr, x, y, w, h, radius=11):
        cr.new_path()
        cr.arc(x + radius, y + radius, radius, math.pi, 1.5 * math.pi)
        cr.arc(x + w - radius, y + radius, radius, 1.5 * math.pi, 2 * math.pi)
        cr.arc(x + w - radius, y + h - radius, radius, 0, 0.5 * math.pi)
        cr.arc(x + radius, y + h - radius, radius, 0.5 * math.pi, math.pi)
        cr.close_path()
        cr.set_source_rgb(*CARD_BG)
        cr.fill_preserve()

        # A faint top-to-middle highlight lifts the card off the background
        # without needing a shadow pass.
        sheen = cairo.LinearGradient(0, y, 0, y + h * 0.55)
        sheen.add_color_stop_rgba(0.0, 0.55, 0.75, 0.93, 0.065)
        sheen.add_color_stop_rgba(1.0, 0.55, 0.75, 0.93, 0.0)
        cr.set_source(sheen)
        cr.fill_preserve()

        cr.set_line_width(1.3)
        cr.set_source_rgb(*CARD_EDGE)
        cr.stroke()

    def draw_rei_portrait(self, cr, x, y, width, height, opacity=1.0):
        if self.rei_portrait is None:
            return
        image = self.rei_portrait
        scale = min(width / image.get_width(), height / image.get_height())
        cr.save()
        cr.translate(x + (width - image.get_width() * scale) / 2,
                     y + (height - image.get_height() * scale) / 2)
        cr.scale(scale, scale)
        cr.set_source_surface(image, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint_with_alpha(opacity)
        cr.restore()

    @staticmethod
    def hex_point(cx, cy, radius, angle):
        """Intersection of a polar ray with a regular, point-right hexagon."""
        delta = (angle % (math.pi / 3)) - math.pi / 6
        reach = radius * math.cos(math.pi / 6) / math.cos(delta)
        return (cx + reach * math.cos(angle), cy + reach * math.sin(angle))

    @staticmethod
    def polygon(cr, points):
        cr.new_path()
        cr.move_to(*points[0])
        for point in points[1:]:
            cr.line_to(*point)
        cr.close_path()

    def hex_path(self, cr, radius):
        cx, cy, _ = RPM_CENTER
        self.polygon(cr, [(cx + radius * math.cos(i * math.pi / 3),
                           cy + radius * math.sin(i * math.pi / 3))
                          for i in range(6)])

    def hud_card(self, cr, x, y, w, h):
        self.polygon(cr, [(x + 11, y), (x + w - 22, y), (x + w, y + 22),
                          (x + w, y + h - 8), (x + w - 8, y + h),
                          (x, y + h), (x, y + 11)])
        fill = cairo.LinearGradient(0, y, 0, y + h)
        fill.add_color_stop_rgb(0, .90, .95, .99)
        fill.add_color_stop_rgb(1, 1, 1, 1)
        cr.set_source(fill)
        cr.fill_preserve()
        cr.set_source_rgb(*CARD_EDGE)
        cr.set_line_width(1)
        cr.stroke()
        self.polygon(cr, [(x + 3, y + 11), (x + 12, y + 3),
                          (x + w - 24, y + 3), (x + w - 16, y + 11)])
        cr.set_source_rgb(*BLUE)
        cr.fill()
        cr.set_source_rgb(*CARD_EDGE)
        cr.set_line_width(.5)
        cr.move_to(x + 10, y + 29)
        cr.line_to(x + w - 10, y + 29)
        cr.stroke()
        for i in range(15):
            cr.set_source_rgb(*(CYAN if i < 6 else TRACK))
            cr.rectangle(x + 10 + i * 8.1, y + h - 8, 5.5, 2)
            cr.fill()

    def angle_for(self, value):
        if not math.isfinite(value):
            value = 0
        ratio = max(0.0, min(1.0, value / RPM_MAX))
        return math.radians(70 - 140 * ratio)  # right half, bottom -> top

    @staticmethod
    def speed_angle(value):
        """Left half carries road speed: 0 at the bottom, rising over the top."""
        if not math.isfinite(value):
            value = 0
        ratio = max(0.0, min(1.0, value / SPEED_MAX))
        return math.radians(110 + 140 * ratio)  # strictly left half

    def arc_radius(self):
        return RPM_CENTER[2] * 0.95

    def arc_width(self):
        return RPM_CENTER[2] * 0.14

    # ------------------------------------------------------------ static pass

    def build_static(self):
        cr = cairo.Context(self.static)
        cr.set_source_rgb(*BG)
        cr.paint()

        self.apply_layout(cr)

        cx, cy, radius = RPM_CENTER

        # All decoration is cached: the larger dial does not add a per-frame
        # portrait, shadow or font-layout pass.
        glow = cairo.RadialGradient(cx, cy, radius * 0.10, cx, cy, radius * 2.7)
        glow.add_color_stop_rgb(0.0, 1.0, 1.0, 1.0)
        glow.add_color_stop_rgb(0.55, 0.973, 0.988, 1.0)
        glow.add_color_stop_rgb(1.0, *BG)
        cr.set_source(glow)
        cr.rectangle(0, 0, LW, LH)
        cr.fill()

        # Warning strip: a gradient reads as a bezel rather than a pasted bar.
        strip = cairo.LinearGradient(0, 0, LW, 0)
        strip.add_color_stop_rgb(0.0, *BLUE)
        strip.add_color_stop_rgb(0.8, *CYAN)
        strip.add_color_stop_rgb(1.0, 0.88, 0.94, 0.98)
        cr.set_source(strip)
        cr.rectangle(0, 0, LW, 4)
        cr.fill()

        # Chamfered outer chassis and registration lines: reference-inspired
        # EVA HUD geometry, with Rei's white/ice-blue rather than purple/green.
        frame = [(9, 40), (52, 10), (588, 10), (631, 40),
                 (631, 321), (591, 347), (49, 347), (9, 321)]
        self.polygon(cr, frame)
        cr.set_line_width(1.1)
        cr.set_source_rgb(*CARD_EDGE)
        cr.stroke()

        self.hex_path(cr, radius + 10)
        cr.set_source_rgb(.87, .92, .96)
        cr.fill_preserve()
        cr.set_source_rgb(*CARD_EDGE)
        cr.set_line_width(1.2)
        cr.stroke()
        self.hex_path(cr, radius + 4)
        cr.set_source_rgb(1, 1, 1)
        cr.fill_preserve()
        cr.set_source_rgb(*BLUE)
        cr.set_line_width(.8)
        cr.stroke()
        self.hex_path(cr, radius - 24)
        cr.set_source_rgb(*CARD_EDGE)
        cr.set_line_width(.6)
        cr.stroke()
        cr.save()
        self.hex_path(cr, radius - 30)
        cr.clip()
        self.draw_rei_portrait(cr, cx - 93, cy - 97, 186, 186, opacity=.22)
        # Two separate legibility veils, one under each readout. A single band
        # across the middle would fight the two-figure layout.
        for side in (-1, 1):
            veil = cairo.LinearGradient(0, cy - 22, 0, cy + 46)
            veil.add_color_stop_rgba(0, 1, 1, 1, 0)
            veil.add_color_stop_rgba(.5, 1, 1, 1, .86)
            veil.add_color_stop_rgba(1, 1, 1, 1, .15)
            cr.set_source(veil)
            cr.rectangle(cx + side * radius * 0.46 - 54, cy - 22, 108, 68)
            cr.fill()
        cr.restore()

        ring_r = self.arc_radius()

        # Two independent dials share the hexagon: road speed on the left
        # (90deg of arc from the bottom), engine speed on the right (270deg).
        # Each keeps its own redline so either value can be judged alone.
        cr.new_path()
        cr.set_line_width(self.arc_width())
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgb(*TRACK)
        self.progress_path(cr, self.speed_angle(0), self.speed_angle(SPEED_MAX))
        self.progress_path(cr, self.angle_for(0), self.angle_for(RPM_MAX))
        cr.stroke()

        cr.new_path()
        cr.set_line_width(self.arc_width())
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(0.91, 0.70, 0.75, 0.95)
        self.progress_path(cr, self.speed_angle(SPEED_REDLINE),
                          self.speed_angle(SPEED_MAX))
        self.progress_path(cr, self.angle_for(RPM_REDLINE),
                          self.angle_for(RPM_MAX))
        cr.stroke()


        for x, y, label, key, fmt, unit in self.cards:
            self.hud_card(cr, x, y, CARD_W, CARD_H)
            self.text(cr, x + 11, y + 22, label, 12, DIM, align="left")
            self.text(cr, x + CARD_W - 11, y + 22, unit, 10, DIM,
                      align="right")

        self.static.flush()

    # ------------------------------------------------------------ dirty boxes

    def arc_box(self, a0, a1):
        return self.swept_arc_box(a0, a1)

    def swept_arc_box(self, a0, a1):
        cx, cy, _ = RPM_CENTER
        lo, hi = sorted((a0, a1))
        lo -= math.radians(5)
        hi += math.radians(5)
        radius = self.arc_radius()
        points = [self.hex_point(cx, cy, radius, a) for a in (lo, hi)]
        for k in range(math.floor(lo / (math.pi/3)), math.ceil(hi / (math.pi/3))+1):
            angle = k * math.pi/3
            if lo <= angle <= hi:
                points.append(self.hex_point(cx, cy, radius, angle))
        pad = self.arc_width()/2 + 5
        xs, ys = zip(*points)
        return (min(xs)-pad, min(ys)-pad, max(xs)-min(xs)+2*pad, max(ys)-min(ys)+2*pad)

    def text_box(self, cx, cy, width, height):
        return (cx - width / 2.0, cy - height / 2.0, width, height)

    def card_value_box(self, index):
        x, y, label, key, fmt, unit = self.cards[index]
        height = max(glyph[2] for glyph in self.card_digits.glyphs.values()) + 6
        return self.text_box(x + CARD_W / 2.0, y + CARD_H * 0.58, CARD_W - 16, height)

    def rpm_value_box(self):
        """Measured glyph bounds keep font/layout changes in the dirty path."""
        cx, cy, radius = RPM_CENTER
        width = 4 * max(g[1] for g in self.big_digits.glyphs.values()) + 6
        height = max(g[2] for g in self.big_digits.glyphs.values()) + 6
        return self.text_box(424, 187, width, height)

    def speed_value_box(self):
        cx, cy, radius = RPM_CENTER
        width = 4 * max(g[1] for g in self.card_digits.glyphs.values()) + 6
        height = max(g[2] for g in self.card_digits.glyphs.values()) + 6
        return self.text_box(216, 187, 68, 40)

    def speed_arc_box(self, a0, a1):
        return self.swept_arc_box(a0, a1)

    @staticmethod
    def boxes_overlap(a, b, pad=2):
        return not (a[0] + a[2] + pad < b[0] or b[0] + b[2] + pad < a[0] or
                    a[1] + a[3] + pad < b[1] or b[1] + b[3] + pad < a[1])

    @staticmethod
    def merge_boxes(a, b):
        x0 = min(a[0], b[0])
        y0 = min(a[1], b[1])
        x1 = max(a[0] + a[2], b[0] + b[2])
        y1 = max(a[1] + a[3], b[1] + b[3])
        return (x0, y0, x1 - x0, y1 - y0)

    @classmethod
    def merge_regions(cls, regions):
        merged = []
        for box, mask in regions:
            index = 0
            while index < len(merged):
                if cls.boxes_overlap(box, merged[index][0]):
                    other_box, other_mask = merged.pop(index)
                    box = cls.merge_boxes(box, other_box)
                    mask |= other_mask
                    index = 0  # The expanded box can bridge earlier regions.
                else:
                    index += 1
            merged.append([box, mask])
        return merged

    # -------------------------------------------------------------- per frame

    def progress_path(self, cr, start, end):
        """Piecewise-linear perimeter, including every exact hex corner."""
        cx, cy, _ = RPM_CENTER
        start, end = sorted((start, end))
        position = start
        cr.move_to(*self.hex_point(cx, cy, self.arc_radius(), position))
        while position < end - 1e-9:
            corner = (math.floor((position + 1e-8) / (math.pi / 3)) + 1) * math.pi / 3
            following = min(end, position + math.radians(5), corner)
            cr.line_to(*self.hex_point(cx, cy, self.arc_radius(), following))
            position = following

    def progress_path_at(self, cr, start, end, ring_r):
        """Same perimeter walk at an explicit radius, for the speed arc."""
        cx, cy, _ = RPM_CENTER
        position = start
        cr.move_to(*self.hex_point(cx, cy, ring_r, position))
        while position < end - 1e-9:
            corner = (math.floor((position + 1e-8) / (math.pi / 3)) + 1) * math.pi / 3
            following = min(end, position + math.radians(5), corner)
            cr.line_to(*self.hex_point(cx, cy, ring_r, following))
            position = following

    def stroke_segment(self, cr, start, end, color, cap=None):
        # No cairo reference in a default argument: the module-level `cairo`
        # name only exists after load_drawing() runs, so binding
        # cairo.LINE_CAP_ROUND here would break at class definition time.
        if cap is None:
            cap = cairo.LINE_CAP_ROUND
        cr.save()
        cr.new_path()
        cr.rectangle(0,0,LW,LH)
        for x,y,_label,_key,_fmt,_unit in self.cards:
            cr.rectangle(x,y,CARD_W,CARD_H)
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.clip()
        cr.new_path()
        cr.set_line_width(self.arc_width())
        cr.set_line_cap(cap)
        self.progress_path(cr, start, end)
        if isinstance(color, tuple):
            cr.set_source_rgb(*color)
        else:
            cr.set_source(color)
        cr.stroke()
        cr.restore()

    def draw_progress(self, cr, a_from, a_to):
        """Draw progress under the current dirty clip, with stable end caps.

        The clip limits rasterisation. Changing cap style as the arc grows
        would also change the distant start cap, outside the swept dirty box.
        """
        if abs(a_to - a_from) < 1e-5:
            return

        lo, hi = (a_from, a_to) if a_to > a_from else (a_to, a_from)
        cap = cairo.LINE_CAP_ROUND
        a_red = self.angle_for(RPM_REDLINE)

        if lo >= a_red:
            segments = [(lo, hi, self.progress_grad)]
        elif hi <= a_red:
            segments = [(lo, hi, RED)]
        else:
            segments = [(lo, a_red, RED), (a_red, hi, self.progress_grad)]

        for start, end, color in segments:
            if end - start < 1e-5:
                continue
            self.stroke_segment(cr, start, end, color, cap)

    def draw_speed_progress(self, cr, a_from, a_to):
        """Speed uses the left 180 degrees, coloured independently of RPM."""
        if abs(a_to - a_from) < 1e-5:
            return
        lo, hi = (a_from, a_to) if a_to > a_from else (a_to, a_from)
        a_red = self.speed_angle(SPEED_REDLINE)
        if hi <= a_red:
            color = self.speed_grad
        elif lo >= a_red:
            color = RED
        else:
            # Split across the redline; the gradient part keeps its own stops.
            self.stroke_segment(cr, lo, a_red, self.speed_grad)
            color = RED
        if hi > a_red and lo < a_red:
            self.stroke_segment(cr, a_red, hi, RED)
            return
        self.stroke_segment(cr, lo, hi, color)

    def draw_readouts(self, cr, values):
        self.draw_rpm(cr, values["rpm"])
        self.draw_speed(cr, values.get("speed", math.nan))
        for index in range(len(self.cards)):
            self.draw_card_value(cr, index, values)

    def draw_rpm(self, cr, rpm):
        pass  # Only the side bar remains; the centre belongs to the G meter.

    def draw_speed(self, cr, speed):
        pass

    def draw_card_value(self, cr, index, values):
        x, y, label, key, fmt, unit = self.cards[index]
        value = values.get(key, math.nan)
        self.card_digits.draw(cr, x + CARD_W / 2.0, y + CARD_H * 0.58,
                              self.value_label(fmt, value), value_color(key, value))

    @staticmethod
    def rpm_label(value):
        return '%d' % round(value) if math.isfinite(value) else '--'

    @staticmethod
    def value_label(fmt, value):
        return fmt % value if math.isfinite(value) else '--'

    def paint(self, values, regions, prev_rpm):
        """Repaint only the requested regions, each with only its own content.

        Earlier versions redrew the arc and all five readouts inside every
        dirty rectangle, which meant up to fifteen Pango layouts per frame and
        pinned the CPU. The mask makes each region pay only for what is inside
        it.
        """
        cr = self.cr
        speed = values.get("speed", math.nan)
        for box, mask in regions:
            # Any cleared rectangle must rebuild every dynamic item it meets,
            # including stable digits. This also fixes the old dual-dial erasure.
            if self.boxes_overlap(box, self.rpm_value_box()):
                mask |= REGION_RPM
            if self.boxes_overlap(box, self.speed_value_box()):
                mask |= REGION_SPEED
            if self.boxes_overlap(box, (320, 5, 200, 350)):
                mask |= REGION_ARC
            if self.boxes_overlap(box, (120, 5, 200, 350)):
                mask |= REGION_SPEED_ARC
            for index in range(len(self.cards)):
                if self.boxes_overlap(box, self.card_value_box(index)):
                    mask |= REGION_CARD0 << index
            bounds = pixel_box(self.to_device(*box), RW, RH)
            if bounds is None:
                continue
            dx, dy, dw, dh = bounds
            cr.save()
            cr.identity_matrix()
            cr.rectangle(dx, dy, dw, dh)
            cr.clip()

            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source(self.static_pattern)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)

            self.apply_layout(cr)
            if mask & REGION_ARC:
                # Restoring the static background also erases old progress
                # inside this box. Rebuild the current prefix under the clip,
                # not just the newest delta, otherwise gaps accumulate.
                self.draw_progress(cr, self.angle_for(0),
                                   self.angle_for(values["rpm"]))
            if mask & REGION_SPEED_ARC:
                self.draw_speed_progress(cr, self.speed_angle(0),
                                         self.speed_angle(speed)
                                         if math.isfinite(speed)
                                         else self.speed_angle(0))
            if mask & REGION_RPM:
                self.draw_rpm(cr, values["rpm"])
            if mask & REGION_SPEED:
                self.draw_speed(cr, speed)
            if (mask & REGION_MOTION or self.boxes_overlap(box, (180, 40, 280, 310))
                    or self.boxes_overlap(box, (251, 346, 138, 14))):
                from gauge_motion import paint_meter
                paint_meter(self, self.motion_state)
            for index in range(len(self.cards)):
                if mask & (REGION_CARD0 << index):
                    self.draw_card_value(cr, index, values)
            cr.restore()

    def upload(self, regions):
        if self.headless or self.screen is None:
            return
        boxes = [self.to_device(*box) for box, _mask in regions]
        t0 = time.perf_counter()
        self.screen.upload(self.surface, boxes)
        t1 = time.perf_counter()
        self.screen.present()
        t2 = time.perf_counter()
        self.prof_upload += t1 - t0
        self.prof_present += t2 - t1

    def draw_frame(self, values, full=False, upload=True):
        regions = []
        signature = self.motion.signature()
        from gauge_motion import VALUE_BOUNDS, PEAK_BOUNDS, motion_bounds
        old_motion = self.motion_state
        self.motion_state = self.motion.read()
        first = full or self.prev_arc is None
        speed = values.get("speed", math.nan)
        if first:
            regions.append(((0.0, 0.0, float(LW), float(LH)), REGION_ALL))
        else:
            if signature != self.motion_signature:
                envelope_signature = tuple((round(x,3),round(y,3)) for x,y in
                    self.motion_state.get('_visual_envelope', self.motion_state.get('imu',{}).get('envelope_g',())))
                visual_box = motion_bounds(self.motion_state, envelope_signature != self.motion_envelope_signature)
                regions.append((visual_box,REGION_MOTION))
                if self.motion_visual_box is not None:
                    regions.append((self.motion_visual_box,REGION_MOTION))
                self.motion_visual_box = visual_box
                self.motion_envelope_signature = envelope_signature
                regions.append((VALUE_BOUNDS,REGION_MOTION))
                old_peaks = tuple(round(v, 2) for v in old_motion.get('imu', {}).get('peaks_g', ()))
                new_peaks = tuple(round(v, 2) for v in self.motion_state.get('imu', {}).get('peaks_g', ()))
                if old_peaks != new_peaks or not old_motion:
                    for box in PEAK_BOUNDS:
                        regions.append((box, REGION_MOTION))
                if (old_motion.get('gps', {}).get('fix') != self.motion_state.get('gps', {}).get('fix')
                        or old_motion.get('recording') != self.motion_state.get('recording')
                        or old_motion.get('gps', {}).get('status') != self.motion_state.get('gps', {}).get('status')
                        or bool(old_motion) != bool(self.motion_state)):
                    regions.append(((251,346,138,14),REGION_MOTION))
            a_prev = self.angle_for(self.prev["rpm"])
            a_now = self.angle_for(values["rpm"])
            if abs(a_now - a_prev) > 1e-4:
                regions.append((self.arc_box(min(a_prev, a_now),
                                             max(a_prev, a_now)), REGION_ARC))

            # Road speed sweeps the left 180 degrees.
            s_now = speed if math.isfinite(speed) else 0.0
            s_prev = self.prev_speed
            a_sprev = self.speed_angle(s_prev)
            a_snow = self.speed_angle(s_now)
            if abs(a_snow - a_sprev) > 1e-4:
                regions.append((self.speed_arc_box(min(a_sprev, a_snow),
                                                  max(a_sprev, a_snow)),
                                REGION_SPEED_ARC))

            for index, (x, y, label, key, fmt, unit) in enumerate(self.cards):
                value = values.get(key, math.nan)
                current = (self.value_label(fmt, value), value_color(key, value))
                if self.shown.get(index) != current:
                    self.shown[index] = current
                    regions.append((self.card_value_box(index),
                                    REGION_CARD0 << index))

        # Merge overlapping regions so no pixel is painted twice.
        merged = self.merge_regions(regions)

        prev_rpm = 0.0 if first else self.prev["rpm"]

        t0 = time.perf_counter()
        self.paint(values, merged, prev_rpm)
        self.surface.flush()
        self.prof_paint += time.perf_counter() - t0
        if upload:
            self.upload(merged)

        self.prev = dict(values)
        if first:
            self.motion_visual_box = motion_bounds(self.motion_state,True)
        self.motion_signature = signature
        self.prev_arc = self.angle_for(values["rpm"])
        self.prev_speed = speed if math.isfinite(speed) else 0.0
        self.shown_rpm = (self.rpm_label(values["rpm"]), values["rpm"] >= 7200)
        self.shown_speed = (self.value_label("%.0f", speed),
                            math.isfinite(speed) and speed >= SPEED_REDLINE)
        for index, (_x, _y, _label, key, fmt, _unit) in enumerate(self.cards):
            value = values.get(key, math.nan)
            self.shown[index] = (self.value_label(fmt, value), value_color(key, value))
        return merged

    def draw_interactive_frame(self):
        now = time.monotonic()
        if now - self.telemetry.last_sample >= .099:
            if hasattr(self.source, 'telemetry_snapshot'):
                raw, signals, status, context = self.source.telemetry_snapshot()
            else:
                raw = self.source.read()
                signals = self.source.read_signals() if hasattr(self.source, 'read_signals') else {}
                status, context = getattr(self.source, 'name', ''), {}
            self.telemetry.sample(now, raw, signals, self.motion.read(), status, context)
        power_state = self.power.poll() if self.power is not None else None
        if power_state and self.power_backdrop is None:
            if self.prev_arc is None:
                self.draw_frame(self.values, full=True, upload=False)
            self.power_backdrop = cairo.ImageSurface(cairo.FORMAT_ARGB32, RW, RH)
            backdrop_cr = cairo.Context(self.power_backdrop)
            backdrop_cr.set_source_surface(self.surface, 0, 0)
            backdrop_cr.paint()
            if self.controls is not None:
                # Do not resume an interrupted settings drag after a modal tap.
                self.controls.start = None
                self.controls.slider = self.controls.scrolling = False
        while True:
            try:
                event = self.input_events.get_nowait()
            except queue.Empty:
                break
            if power_state:
                self.power.input(*event)
            elif self.controls is not None:
                self.controls.input(*event)
        if power_state:
            if power_state != self.power_state:
                from gauge_power import paint_modal
                paint_modal(self, power_state, self.power_backdrop)
                self.power_state = dict(power_state)
                return [((0, 0, LW, LH), REGION_ALL)]
            return []
        if self.power_backdrop is not None:
            self.power_backdrop = self.power_state = None
            self.previous_page, self.prev_arc = '__power__', None
        if self.controls is not None:
            if (self.controls.pending_brightness is not None and
                    time.monotonic() - self.controls.last_brightness_write >= 0.1):
                self.controls.flush_brightness()
            page = self.controls.page
            if page == 'route':
                from gauge_tracks import paint
                motion = self.motion.read()
                self.tracks.tick(motion, now)
                state = (self.tracks.revision, self.controls.message)
                changed = self.previous_page != page or self.ui_state != state
                self.previous_page, self.ui_state = page, state
                if changed or now-self.route_paint_at >= .5:
                    paint(self, self.tracks, motion, self.controls.message)
                    self.route_paint_at = now
                    return [((0, 0, LW, LH), REGION_ALL)]
                return []
            if page == 'telemetry':
                from gauge_telemetry import paint
                state = (self.telemetry.frozen is not None, self.telemetry.recording)
                changed = self.previous_page != page or self.ui_state != state
                self.previous_page, self.ui_state = page, state
                if changed or now-self.telemetry_paint_at >= .1:
                    paint(self, self.telemetry)
                    self.telemetry_paint_at = now
                    return [((0, 0, LW, LH), REGION_ALL)]
                return []
            if page == 'settings':
                from gauge_settings import paint_settings
                state = self.controls.snapshot()
                changed = self.previous_page != page or self.ui_state != state
                self.previous_page, self.ui_state = page, state
                if changed:
                    paint_settings(self, self.controls, state)
                    return [((0, 0, LW, LH), REGION_ALL)]
                return []
            if self.previous_page != page:
                self.prev_arc = None  # Restore every dashboard pixel after settings.
            self.previous_page = page
            from gauge_windows import normalize_windows, card_layout
            bindings = normalize_windows(self.controls.config.data.get('windows'))
            profile = self.controls.config.data['profile']
            if bindings != self.window_bindings or profile != self.window_profile:
                self.window_bindings, self.window_profile = bindings, profile
                self.cards = card_layout(CARDS, bindings, self.controls.config.profile)
                self.build_static()  # Rebuild labels/units once, never each frame.
                self.prev_arc = None
                self.shown.clear()
        self.advance_values(time.monotonic())
        return self.draw_frame(self.values, upload=False)

    # ------------------------------------------------------------------- loop

    def _stop(self, *_args):
        self.running = False

    def advance_values(self, now):
        """Data/animation state is owned by the render worker, not SDL."""
        target = self.source.read()
        elapsed = max(0, now-getattr(self, 'last_value_update', now-1/60))
        self.last_value_update = now
        if not self.sweep_done:
            progress = (now - self.sweep_start) / 2.2
            if progress >= 1.0:
                self.sweep_done = True
            else:
                sweep = progress * 2 if progress < 0.5 else (1.0 - progress) * 2
                target = {key: value * sweep for key, value in target.items()}
        fast = bool(self.sweep_done and self.controls and self.controls.config.data.get('sky_forward',False))
        self.values["rpm"] = (responsive_approach(self.values['rpm'],target['rpm'],RPM_STEP,elapsed)
                              if fast else approach(self.values["rpm"], target["rpm"], RPM_STEP))
        self.values["coolant"] = approach(self.values["coolant"], target["coolant"], COOLANT_STEP)
        for key in ("oil", "battery"):
            self.values[key] = approach(self.values[key], target[key], 1.5)
        # Speed now drives its own arc, so it needs a step that matches the
        # arc's sweep instead of the slow card-value ramp.
        self.values["speed"] = (responsive_approach(self.values['speed'],target['speed'],SPEED_STEP,elapsed)
                                if fast else approach(self.values["speed"], target["speed"],SPEED_STEP))
        signals = self.source.read_signals() if hasattr(self.source, 'read_signals') else {}
        for _x, _y, _label, key, _fmt, _unit in self.cards:
            if key not in ('rpm', 'coolant', 'oil', 'speed', 'battery'):
                value = signals.get(key)
                self.values[key] = value if isinstance(value, (int, float)) and math.isfinite(value) else math.nan

    def run(self):
        """Overlap Cairo for N+1 with the vblank wait for N.

        There is one CPU surface and at most one outstanding frame. The
        worker may touch it ONLY after SDL_UpdateTexture has copied frame N.
        All SDL APIs (including event pumping) remain on this main thread.
        """
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        request = threading.Event()
        ready = queue.Queue(maxsize=1)

        def render_worker():
            while self.running:
                if not request.wait(0.2):
                    continue
                request.clear()
                if not self.running:
                    break
                try:
                    start = time.perf_counter()
                    regions = self.draw_interactive_frame()
                    ready.put((regions, time.perf_counter() - start, None))
                except Exception as exc:
                    ready.put((None, 0.0, exc))
                    break

        worker = threading.Thread(target=render_worker, name="gauge-cairo", daemon=True)
        worker.start()
        request.set()
        paint_time = upload_time = present_time = wait_time = 0.0
        try:
            while self.running:
                frame_start = time.perf_counter()
                try:
                    regions, paint_elapsed, error = ready.get(timeout=0.2)
                except queue.Empty:
                    continue
                if error is not None:
                    raise RuntimeError("Cairo render worker failed") from error
                if not self.running:
                    break
                received = time.perf_counter()
                # The worker is blocked here: this is a consistent snapshot.
                if self.dump_path and self.total_frames == self.dump_frame:
                    self.surface.write_to_png(self.dump_path)
                    print("DUMPED %s at frame %d" % (self.dump_path, self.total_frames), flush=True)
                    self.dump_path = None
                boxes = [self.to_device(*box) for box, _mask in regions]
                self.screen.upload(self.surface, boxes)
                uploaded = time.perf_counter()
                # SDL has copied the pixel data. Cairo may now work on N+1
                # while the main thread submits N and waits for its pageflip.
                request.set()
                self.screen.present()
                if hasattr(self.screen, 'poll_input'):
                    for event in self.screen.poll_input():
                        try:
                            self.input_events.put_nowait(event)
                        except queue.Full:
                            # A full queue is exceptional; don't silently lose an UP.
                            self._stop()
                            raise RuntimeError('Touch input queue overflow')
                presented = time.perf_counter()
                self.frames += 1
                self.total_frames += 1
                paint_time += paint_elapsed
                upload_time += uploaded - received
                present_time += presented - uploaded
                wait_time += received - frame_start
                elapsed = presented - self.fps_window
                if elapsed >= 2.0:
                    count = max(1, self.frames)
                    print("FPS %.1f  paint=%.1fms upload=%.1fms present=%.1fms wait=%.1fms pipeline=1"
                          % (count / elapsed, paint_time * 1000 / count,
                             upload_time * 1000 / count, present_time * 1000 / count,
                             wait_time * 1000 / count), flush=True)
                    self.frames = 0
                    paint_time = upload_time = present_time = wait_time = 0.0
                    self.fps_window = presented
                if not self.use_vsync:
                    remaining = 1.0 / FPS_TARGET - (time.perf_counter() - frame_start)
                    if remaining > 0:
                        time.sleep(remaining)
        finally:
            self.running = False
            request.set()
            worker.join(timeout=1.0)
            self.telemetry.close()
            self.tracks.close()


def selftest(path):
    """Headless regression check: run many INCREMENTAL frames (no full
    repaint) and dump the result. If digits/arc disappear here, the dirty
    region logic is broken; if they survive, the display path is at fault."""
    gauge = Gauge(DemoSource(), headless=True)
    source = DemoSource()
    for _ in range(300):
        target = source.read()
        for key, value in target.items():
            step = RPM_STEP if key == "rpm" else 1.5
            gauge.values[key] = approach(gauge.values[key], value, step)
        gauge.draw_frame(gauge.values)
    # un-rotate for review
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                             gauge.surface.get_height(),
                             gauge.surface.get_width())
    cr = cairo.Context(out)
    cr.translate(0, gauge.surface.get_width())
    cr.rotate(-math.pi / 2)
    cr.set_source_surface(gauge.surface, 0, 0)
    cr.paint()
    out.write_to_png(path)
    print("SELFTEST EXPORTED %s" % path, flush=True)
    return 0


def main(startup_screen=None, preset_source=None, preset_static=None):
    address = None
    if "--ble" in sys.argv:
        index = sys.argv.index("--ble") + 1
        address = sys.argv[index] if index < len(sys.argv) else ""

    if "--selftest" in sys.argv:
        return selftest(sys.argv[sys.argv.index("--selftest") + 1])

    if "--export" in sys.argv:
        path = sys.argv[sys.argv.index("--export") + 1]
        flat = "--flat" in sys.argv
        gauge = Gauge(DemoSource(), headless=True)
        gauge.draw_frame({"rpm": 2860, "coolant": 92, "oil": 84,
                          "speed": 28, "battery": 13.8}, full=True)
        if flat:
            # Undo the panel rotation so the layout can be reviewed upright.
            src = gauge.surface
            out = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                     src.get_height(), src.get_width())
            cr = cairo.Context(out)
            cr.translate(0, src.get_width())
            cr.rotate(-math.pi / 2)
            cr.set_source_surface(src, 0, 0)
            cr.paint()
            out.write_to_png(path)
        else:
            gauge.surface.write_to_png(path)
        print("EXPORTED %s" % path, flush=True)
        return 0

    from gauge_power import PowerClient
    power = PowerClient()
    if preset_source is not None:
        # The boot launcher already built and connected this worker while the
        # startup movie was playing. Reuse it instead of waiting a fresh
        # handshake; its config is the same on-disk Config().
        source = preset_source
        from gauge_settings import TouchSettings
        controls = TouchSettings(source.config, source, shutdown=power.shutdown)
        print("BLE preset reused from boot warmup", flush=True)
    elif address or "--ble" in sys.argv:
        from gauge_settings import Config, SettingsBleSource, TouchSettings
        config = Config(address=address)
        source = SettingsBleSource(config)
        controls = TouchSettings(config, source, shutdown=power.shutdown)
    else:
        source, controls = DemoSource(), None
    Gauge(source, controls=controls, startup_screen=startup_screen, power=power,
          static_cache=preset_static).run()
    return 0


from gauge_home import apply_home_design
apply_home_design(Gauge)

if __name__ == "__main__":
    sys.exit(main())

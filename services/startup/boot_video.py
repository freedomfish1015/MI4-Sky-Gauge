"""GPU boot movie: media EOS gates Gauge; no boot partition modifications."""
import argparse
import ctypes as C
import os
from pathlib import Path
import signal
import sys
import time

WIDTH, HEIGHT = 1080, 1920
# Keep a bounded, clock-synchronised video sink. Late pictures must not queue
# behind audio; BaseSink QoS also lets upstream decoders skip obsolete work.
VIDEO_SINK = ('appsink name=frames sync=true qos=true max-lateness=50000000 '
              'processing-deadline=0 max-buffers=1 drop=true '
              'enable-last-sample=false wait-on-eos=false')
TYPELIB = Path(__file__).resolve().parent / 'girepository'
if TYPELIB.is_dir():
    os.environ['GI_TYPELIB_PATH'] = str(TYPELIB) + os.pathsep + os.environ.get('GI_TYPELIB_PATH', '')
PLUGINS = Path(__file__).resolve().parent / 'gstreamer'
if PLUGINS.is_dir():
    os.environ['GST_PLUGIN_PATH'] = str(PLUGINS) + os.pathsep + os.environ.get('GST_PLUGIN_PATH', '')


class BacklightGuard:
    """Hide uninitialised KMS scanout, not by changing the display driver.

    Restore the exact brightness after the first fully uploaded frame. A
    durable /run marker also lets ExecStopPost recover after a forced kill.
    """
    def __init__(self, directory='/sys/class/backlight/backlight', runtime=None):
        self.directory = Path(directory)
        self.marker = Path(runtime or os.environ.get('XDG_RUNTIME_DIR', '/run/obd-gauge')) / 'boot-brightness'
        self.saved = None

    def begin(self):
        try:
            maximum = int((self.directory / 'max_brightness').read_text())
            value = int((self.directory / 'brightness').read_text())
            if not 0 < value <= maximum:
                return
            self.marker.write_text(str(value))
            self.saved = value
            (self.directory / 'brightness').write_text('0')
        except (OSError, ValueError):
            # Brightness gating is best-effort, never a reason to lose boot.
            self.restore()

    def restore(self):
        try:
            value = self.saved
            if value is None and self.marker.is_file():
                value = int(self.marker.read_text())
            if value is not None:
                maximum = int((self.directory / 'max_brightness').read_text())
                if not 0 < value <= maximum:
                    raise ValueError('Invalid saved brightness')
                (self.directory / 'brightness').write_text(str(value))
                self.marker.unlink(missing_ok=True)
                self.saved = None
        except (OSError, ValueError):
            pass


def validate_layout(size, offsets, strides):
    if not 0 < size <= 32 * 1024 * 1024 or len(offsets) < 3 or len(strides) < 3:
        raise ValueError('Invalid YUV buffer')
    for i, (width, height) in enumerate(((WIDTH, HEIGHT), (WIDTH // 2, HEIGHT // 2), (WIDTH // 2, HEIGHT // 2))):
        end = offsets[i] + (height - 1) * strides[i] + width
        if offsets[i] < 0 or not width <= strides[i] <= width + 4096 or end > size:
            raise ValueError('YUV plane outside buffer')


class VideoScreen:
    def __init__(self, first_frame=None, jpeg_colors=False):
        from gauge_sdl import Screen
        self.guard = BacklightGuard()
        self.guard.begin()
        self.frames_shown = 0
        try:
            self.screen = Screen(WIDTH, HEIGHT)
            sdl = self.screen.sdl
            import cairo
            data = bytearray(Path(first_frame).read_bytes()) if first_frame else bytearray(WIDTH * HEIGHT * 4)
            if len(data) != WIDTH * HEIGHT * 4:
                raise ValueError('Invalid first-frame artwork')
            surface = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, WIDTH, HEIGHT, WIDTH * 4)
            self.screen.upload(surface, [(0, 0, WIDTH, HEIGHT)])
            # KMS starts scanning out as soon as the renderer exists, before
            # any buffer has been uploaded. Presenting the artwork repeatedly
            # here means every buffer the display can reach already holds the
            # first frame, so a later backlight restore cannot reveal an
            # uninitialised (white) buffer.
            for _ in range(3):
                self.screen.present()
            self.screen.replace_texture(0x56555949)  # SDL_PIXELFORMAT_IYUV
            sdl.SDL_UpdateYUVTexture.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_int,
                                              C.c_void_p, C.c_int, C.c_void_p, C.c_int]
            sdl.SDL_UpdateYUVTexture.restype = C.c_int
            sdl.SDL_SetYUVConversionMode.argtypes = [C.c_int]
            sdl.SDL_SetYUVConversionMode(0 if jpeg_colors else 2)
            # The texture format just changed under the scanout. Present the
            # ARGB frame once more so the swap chain settles in the new
            # format before any decoded picture is pushed through it.
            self.screen.present()
        except BaseException:
            self.guard.restore()
            raise

    def restore_backlight(self):
        self.guard.restore()

    def show(self, pixels, offsets, strides):
        validate_layout(len(pixels), offsets, strides)
        anchor = C.c_char_p(pixels)
        address = C.cast(anchor, C.c_void_p).value
        if self.screen.sdl.SDL_UpdateYUVTexture(self.screen.texture, None,
                address + offsets[0], strides[0], address + offsets[1], strides[1],
                address + offsets[2], strides[2]) != 0:
            raise RuntimeError(self.screen.sdl.SDL_GetError().decode())
        self.screen.present()
        self.frames_shown += 1
        if self.guard.saved is not None and self.frames_shown >= 2:
            # Wait for the second decoded frame before lighting the panel.
            # A single frame is not enough: KMS flips asynchronously across
            # several buffers, so restoring after one present could expose a
            # buffer that has not received any YUV data yet, which is what the
            # white flash before playback used to be.
            self.screen.present()
            self.guard.restore()

    def close(self):
        self.guard.restore()
        sdl = self.screen.sdl
        for name, value in (('SDL_DestroyTexture', self.screen.texture),
                            ('SDL_DestroyRenderer', self.screen.renderer), ('SDL_DestroyWindow', self.screen.window)):
            function = getattr(sdl, name)
            function.argtypes = [C.c_void_p]
            function(value)
        sdl.SDL_Quit()


def play(path, renderer=None, max_seconds=45, inspect=False, audio=False, volume=.5,
         audio_backend='pulse'):
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstVideo', '1.0')
    from gi.repository import Gst, GstVideo
    Gst.init(None)
    sink_bin = Gst.parse_bin_from_description(
        'videoconvert ! video/x-raw,format=I420,width=1080,height=1920,pixel-aspect-ratio=1/1 ! '
        + VIDEO_SINK, True)
    sink = sink_bin.get_by_name('frames')
    player = Gst.ElementFactory.make('playbin', 'boot-player')
    player.set_property('uri', Path(path).resolve().as_uri())
    player.set_property('flags', 19 if audio else 1)
    player.set_property('video-sink', sink_bin)
    if audio:
        if audio_backend not in ('pulse', 'alsa'):
            raise ValueError('Unknown boot audio backend')
        output = ('alsasink device="hw:0,0"' if audio_backend == 'alsa' else
                  'pulsesink server="unix:/run/user/1000/pulse/native"')
        audio_bin = Gst.parse_bin_from_description(
            'audioconvert ! audioresample ! audio/x-raw,format=S16LE,rate=48000,channels=2 ! ' + output, True)
        player.set_property('audio-sink', audio_bin)
        player.set_property('volume', volume)
        player.set_property('mute', False)
    bus = player.get_bus()
    frames, first, last_pts, render_time = 0, None, None, 0.0
    started = time.monotonic()
    stopped, eos, complete = False, False, False
    def stop(*_):
        nonlocal stopped
        stopped = True
    handlers = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        if player.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('Video pipeline failed to start')
        while not stopped and time.monotonic() - started < max_seconds:
            sample = sink.emit('try-pull-sample', 100 * Gst.MSECOND)
            if sample is not None:
                buffer, caps = sample.get_buffer(), sample.get_caps()
                structure = caps.get_structure(0)
                if (structure.get_value('width'), structure.get_value('height'), structure.get_value('format')) != (WIDTH, HEIGHT, 'I420'):
                    raise RuntimeError('Unexpected native video format')
                meta = GstVideo.buffer_get_video_meta(buffer)
                layout = meta if meta is not None else GstVideo.VideoInfo.new_from_caps(caps)
                offsets, strides = list(layout.offset), list(layout.stride)
                validate_layout(buffer.get_size(), offsets, strides)
                pixels = buffer.extract_dup(0, buffer.get_size())
                now = time.monotonic()
                if first is None:
                    first = now
                    print('BOOT_VIDEO_FIRST_FRAME startup=%.2fs native=1080x1920 audio=%d volume=%.2f GPU=YUV strides=%s' % (
                          now - started, audio, volume if audio else 0, strides[:3]), flush=True)
                if renderer is not None:
                    stamp = time.perf_counter()
                    renderer.show(pixels, offsets, strides)
                    render_time += time.perf_counter() - stamp
                last_pts = buffer.pts / Gst.SECOND if buffer.pts != Gst.CLOCK_TIME_NONE else None
                frames += 1
                if inspect:
                    print('VIDEO_DECODE_INSPECT_OK caps=%s' % caps.to_string(), flush=True)
                    return dict(complete=False, inspected=True)
            message = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if message:
                if message.type == Gst.MessageType.ERROR:
                    failure, detail = message.parse_error()
                    raise RuntimeError('Video decode error: %s / %s' % (failure, detail))
                eos = True
            if eos and sample is None and sink.get_property('eos'):
                complete = True
                break
        if not complete:
            raise RuntimeError('Video did not finish: stopped=%s frames=%d pts=%s' % (stopped, frames, last_pts))
        elapsed = time.monotonic() - (first or started)
        print('BOOT_VIDEO_EOS_COMPLETE frames=%d elapsed=%.2fs fps=%.1f last_pts=%s render=%.1fms' % (
            frames, elapsed, frames / max(.001, elapsed), last_pts, render_time * 1000 / max(1, frames)), flush=True)
        duration_ok, duration_ns = player.query_duration(Gst.Format.TIME)
        duration = duration_ns / Gst.SECOND if duration_ok and duration_ns > 0 else None
        stats = sink.get_property('stats')
        dropped = int(stats.get_value('dropped')) if stats else 0
        print('BOOT_VIDEO_CLOCK_STATS duration=%s elapsed=%.2fs dropped=%d' % (
              duration, elapsed, dropped), flush=True)
        return dict(complete=True, frames=frames, last_pts=last_pts,
                    elapsed=elapsed, duration=duration, dropped=dropped)
    finally:
        player.set_state(Gst.State.NULL)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def main():
    if sys.argv[1:] == ['--restore-backlight']:
        BacklightGuard().restore()
        return
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('--max-seconds', type=float, default=45)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--audio', action='store_true')
    parser.add_argument('--volume', type=float, default=.5)
    parser.add_argument('--first-frame')
    parser.add_argument('--audio-backend', choices=('pulse', 'alsa'), default='pulse')
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 60 or not 0 <= args.volume <= 1:
        parser.error('Invalid deadline or normal-range stream volume')
    renderer = None if args.inspect else VideoScreen(args.first_frame, Path(args.video).suffix.lower() == '.avi')
    try:
        play(args.video, renderer, args.max_seconds, args.inspect, args.audio, args.volume,
             args.audio_backend)
    finally:
        if renderer:
            renderer.close()


if __name__ == '__main__':
    main()

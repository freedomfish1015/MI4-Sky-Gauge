"""Boot-only movie and in-process handoff to the existing real OBD gauge."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

# Import this FIRST: it sets the scoped GstVideo typelib path before GI init.
from boot_video import VideoScreen, play

ASSETS = Path('/usr/local/share/obd-gauge')
APP = Path('/home/umeko/desktop-offline')
sys.path.insert(0, str(APP))

# Filled in by warmup() while the movie is still playing; consumed by
# gauge_sdl.main() afterwards so the dashboard starts already connected.
WARMUP = {}


def bluetooth_ready(timeout=25, poll=.1):
    """Wait until BlueZ has published an adapter.

    The movie starts before bluetooth.service finishes activating; asking
    bleak at that point fails with 'No Bluetooth adapters found' and burns
    the connection on the first attempt. hci0 appearing under sysfs is the
    same signal BlueZ itself uses, and it is cheap to poll.
    """
    until = time.monotonic() + timeout
    root = Path('/sys/class/bluetooth')
    while time.monotonic() < until:
        try:
            if any(root.glob('hci*')):
                return True
        except OSError:
            pass
        time.sleep(poll)
    return False


def warmup():
    """Spend the movie's playback window doing the dashboard's startup work.

    Scheduling matters more than the work itself. The first video frame is
    the most latency sensitive moment of the boot, so this thread sleeps
    briefly to let decoding claim the CPU, and every stage is done while the
    movie is running rather than after EOS.
    """
    started = time.monotonic()
    # Let the decoder take the CPU for its first frames. Rasterising glyphs
    # during this window measurably delayed the first video frame by ~2.5s.
    time.sleep(1.5)

    try:
        import gauge_sdl
        gauge_sdl.load_drawing()
        import cairo
        from pathlib import Path as _Path
        portrait = _Path(gauge_sdl.__file__).resolve().parent / 'assets/rei-reference.png'
        if portrait.is_file():
            cairo.ImageSurface.create_from_png(str(portrait))
        gauge_sdl.Digits(int(gauge_sdl.RPM_CENTER[2] * 0.31))
        gauge_sdl.Digits(35)
        print('BOOT_WARMUP_ASSETS %.2fs' % (time.monotonic() - started), flush=True)
    except Exception as exc:
        # Warming is an optimisation; never let it break the boot path.
        print('BOOT_WARMUP_ASSETS_SKIPPED %r' % (exc,), flush=True)

    try:
        ready = bluetooth_ready()
        print('BOOT_WARMUP_BLUETOOTH_READY %d after=%.2fs'
              % (ready, time.monotonic() - started), flush=True)
        if not ready:
            raise RuntimeError('no bluetooth adapter before the movie ended')
        from gauge_settings import Config, SettingsBleSource
        config = Config()
        if config.data['enabled'] and config.data['address']:
            source = SettingsBleSource(config)
            WARMUP['source'] = source
            WARMUP['config'] = config
            print('BOOT_WARMUP_BLE_STARTED %s profile=%s'
                  % (config.data['address'], config.data['profile']), flush=True)
            prerender_static(config)
    except Exception as exc:
        print('BOOT_WARMUP_BLE_SKIPPED %r' % (exc,), flush=True)


def prerender_static(config):
    """Rasterise the dashboard's decoration layer while the movie plays.

    Pure Cairo work on an offscreen surface: no DRM master and no SDL objects,
    so it is safe to do while the video owns the display. It is keyed by the
    resolved card layout and simply discarded if the user changed windows.

    The scratch object must reach the same state __init__ would produce, so
    every attribute build_static() reads is initialised here. Skipping the
    artwork decode would silently drop the portrait from the cached layer.
    """
    started = time.monotonic()
    try:
        import gauge_sdl
        # gauge_sdl only binds its cairo/Pango names once the drawing stack is
        # loaded; this function must be safe to call on its own.
        gauge_sdl.load_drawing()
        import cairo
        from pathlib import Path as _Path
        from gauge_windows import DEFAULT_WINDOWS, card_layout, normalize_windows
        bindings = normalize_windows(config.data.get('windows', DEFAULT_WINDOWS))
        cards = card_layout(gauge_sdl.CARDS, bindings, config.profile)

        scratch = gauge_sdl.Gauge.__new__(gauge_sdl.Gauge)
        scratch.cards = cards
        scratch.rei_portrait = None
        portrait = _Path(gauge_sdl.__file__).resolve().parent / 'assets/rei-reference.png'
        if portrait.is_file():
            scratch.rei_portrait = cairo.ImageSurface.create_from_png(str(portrait))
        scratch.window_bindings = bindings
        scratch.window_profile = config.profile
        scratch.static = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                            gauge_sdl.RW, gauge_sdl.RH)
        scratch.build_static()
        WARMUP['static'] = dict(surface=scratch.static, cards=cards)
        print('BOOT_WARMUP_STATIC %.2fs portrait=%s'
              % (time.monotonic() - started, bool(scratch.rei_portrait)),
              flush=True)
    except Exception as exc:
        print('BOOT_WARMUP_STATIC_SKIPPED %r' % (exc,), flush=True)


def audio_ready(wait=8, backend='pulse'):
    until = time.monotonic() + wait
    while time.monotonic() < until:
        if backend == 'alsa':
            # ExecStartPost marks successful hardware bring-up. Early boot
            # has no system bus yet; asking systemctl adds seconds of delay.
            if Path('/run/mi4-audio-init/ready').exists() and Path('/dev/snd/pcmC0D0p').exists():
                return True
            time.sleep(.05)
            continue
        try:
            active = subprocess.run(['systemctl', 'is-active', '--quiet', 'mi4-audio-init.service'], timeout=1).returncode == 0
            endpoint = '/dev/snd/pcmC0D0p' if backend == 'alsa' else '/run/user/1000/pulse/native'
            if active and Path(endpoint).exists():
                return True
        except subprocess.TimeoutExpired:
            pass
        time.sleep(.2)
    return False


def restore_desktop_audio():
    # Direct ALSA avoids waiting for the desktop manager at boot. If that
    # manager already exists (live test / late boot), retry its normal audio
    # units after releasing the exclusive hardware PCM. No driver reloads.
    if Path('/run/user/1000/bus').exists():
        environment = dict(os.environ, XDG_RUNTIME_DIR='/run/user/1000',
                           DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
        try:
            subprocess.run(['systemctl', '--user', '--no-block', 'start',
                            'pipewire.service', 'pipewire-pulse.service', 'wireplumber.service'],
                           env=environment, timeout=2, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass


def run():
    marker = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/obd-gauge')) / 'boot-video.done'
    renderer = None
    worker = None
    # Warming only makes sense while the movie is actually playing: that is the
    # only window where the CPU work is free. When the marker already exists
    # (service restart after boot) there is no movie, and a warmup thread would
    # open a second BLE client that fights the one main() creates for itself.
    if not marker.exists():
        worker = threading.Thread(target=warmup, name='obd-warmup', daemon=True)
        worker.start()
        marker.write_text(json.dumps(dict(status='started')))
        try:
            backend = os.environ.get('OBD_BOOT_AUDIO', 'pulse')
            renderer = VideoScreen(ASSETS / 'nerv-first-1080.argb', jpeg_colors=True)
            audio = audio_ready(backend=backend)
            if not audio:
                print('BOOT_AUDIO_NOT_READY: silent video fallback, driver unchanged', flush=True)
            result = play(ASSETS / 'nerv-startup-1080-mjpeg.avi', renderer,
                          max_seconds=45, audio=audio, volume=.5, audio_backend=backend)
            if not result.get('complete'):
                raise RuntimeError('EOS required before normal dashboard handoff')
            marker.write_text(json.dumps(dict(status='complete', **result)))
        except Exception as exc:
            # A failed video must not turn a dedicated dashboard into a boot loop.
            marker.write_text(json.dumps(dict(status='failed', reason=str(exc))))
            print('BOOT_VIDEO_FAILURE_FALLBACK %r' % exc, flush=True)
        finally:
            if renderer is not None:
                renderer.restore_backlight()
            if os.environ.get('OBD_BOOT_AUDIO') == 'alsa':
                restore_desktop_audio()

    if worker is not None:
        # Never hand over a half-built warmup: a source published after this
        # point would be ignored while its BLE client kept running.
        worker.join(timeout=5)
        print('BOOT_WARMUP_JOINED alive=%s' % worker.is_alive(), flush=True)

    import gauge_sdl
    print('BOOT_HANDOFF_TO_GAUGE same_window=%d warm=%d static=%d'
          % (bool(renderer), 'source' in WARMUP, 'static' in WARMUP), flush=True)
    # Reuse the BLE worker and the decoration layer that have been ready since
    # the movie started playing.
    return gauge_sdl.main(renderer.screen if renderer else None,
                          preset_source=WARMUP.get('source'),
                          preset_static=WARMUP.get('static'))


if __name__ == '__main__':
    sys.exit(run())

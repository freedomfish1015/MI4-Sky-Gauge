"""Direct dashboard startup: no media imports, audio wait or movie warmup."""
import importlib
import json
import os
from pathlib import Path
import sys
import time

APP = Path('/home/umeko/desktop-offline')
STARTUP_LOGO = Path('/usr/local/share/obd-gauge/sky-logo-1080.argb')


class BacklightGuard:
    """Blank only during KMS acquisition; recover exact brightness on failure."""
    def __init__(self, directory='/sys/class/backlight/backlight', runtime=None):
        self.directory = Path(directory)
        self.runtime = Path(runtime or os.environ.get('XDG_RUNTIME_DIR', '/run/obd-gauge'))
        self.marker = self.runtime / 'direct-boot-brightness'
        self.saved = None

    def begin(self, blank=True):
        self.restore()  # Recover a previous killed process before saving zero.
        try:
            maximum = int((self.directory / 'max_brightness').read_text())
            value = int((self.directory / 'brightness').read_text())
            if not 0 < value <= maximum:
                return
            self.marker.write_text(str(value))
            self.saved = value
            if blank:
                (self.directory / 'brightness').write_text('0')
        except (OSError, ValueError):
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


def boot_uptime():
    try:
        return float(Path('/proc/uptime').read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def release_logo_curtain(runtime):
    """End optional fbdev repainting before SDL owns KMS, without racing writes."""
    lock = None
    try:
        import fcntl
        lock = os.open('/run/obd-gauge-logo.lock', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        fcntl.flock(lock, fcntl.LOCK_EX)
        (runtime / 'logo-handoff').write_text(str(os.getpid()))
        print('DIRECT_GAUGE_CURTAIN_RELEASE uptime=%s' % boot_uptime(), flush=True)
    except OSError as exc:
        # Decorative curtain absence must never stop the working dashboard.
        print('DIRECT_GAUGE_CURTAIN_RELEASE_SKIPPED %r' % exc, flush=True)
    finally:
        if lock is not None:
            os.close(lock)


def show_startup_logo(screen, present, path=STARTUP_LOGO):
    """Present the same native logo while Gauge builds its static/glyph layers.

    No movie, sleeps or extra window. Use the base present method so a logo
    frame cannot be mistaken for the first dashboard frame/readiness marker.
    """
    if not path.is_file():
        return False
    pixels = bytearray(path.read_bytes())
    if len(pixels) != 1080 * 1920 * 4 or (screen.texture_width, screen.texture_height) != (1080, 1920):
        raise ValueError('Unexpected native logo/texture geometry')
    import cairo
    surface = cairo.ImageSurface.create_for_data(pixels, cairo.FORMAT_ARGB32, 1080, 1920, 1080 * 4)
    screen.upload(surface, [(0, 0, 1080, 1920)])
    # Fully populate scanout before revealing a new KMS renderer.
    present()
    present()
    print('DIRECT_GAUGE_LOGO_PRESENTED uptime=%s' % boot_uptime(), flush=True)
    return True


def guarded_screen(base, guard, started):
    class DirectScreen(base):
        def __init__(self, *args, **kwargs):
            self.first_frame = True
            release_logo_curtain(guard.runtime)
            # Keep the already-visible fbdev logo lit while SDL loads. Only
            # the native display transition may briefly blank its scanout;
            # hiding the backlight throughout SDL initialization added ~2.6s.
            guard.begin(blank=False)
            try:
                super().__init__(*args, **kwargs)
                try:
                    if show_startup_logo(self, lambda: base.present(self)):
                        guard.restore()
                except Exception as exc:
                    # A bad/missing decorative asset must not prevent boot.
                    print('DIRECT_GAUGE_LOGO_FALLBACK %r' % exc, flush=True)
            except BaseException:
                guard.restore()
                raise

        def present(self):
            result = super().present()
            if self.first_frame:
                self.first_frame = False
                guard.restore()
                status = dict(pid=os.getpid(), uptime=boot_uptime(),
                              elapsed=round(time.monotonic() - started, 3))
                # A marker is diagnostic only. Never crash working display
                # because a filesystem has become read-only/full.
                try:
                    (guard.runtime / 'direct-gauge.ready').write_text(json.dumps(status))
                except OSError:
                    pass
                print('DIRECT_GAUGE_FIRST_FRAME ' + json.dumps(status), flush=True)
            return result
    return DirectScreen


def run():
    started = time.monotonic()
    guard = BacklightGuard()
    if sys.argv[1:] == ['--restore-backlight']:
        guard.restore()
        return 0
    try:
        (guard.runtime / 'direct-gauge.ready').unlink(missing_ok=True)
    except OSError:
        pass
    sys.path.insert(0, str(APP))
    print('DIRECT_GAUGE_START uptime=%s' % boot_uptime(), flush=True)
    gauge = importlib.import_module('gauge_sdl')
    original = gauge.Screen
    gauge.Screen = guarded_screen(original, guard, started)
    try:
        # The existing main starts BLE asynchronously. Nothing waits for OBD,
        # audio, satellite acquisition, or an animation before first display.
        return gauge.main()
    finally:
        gauge.Screen = original
        guard.restore()


if __name__ == '__main__':
    sys.exit(run())

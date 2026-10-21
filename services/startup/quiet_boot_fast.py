"""Hide current and subsequently reset VT cursors without touching boot.img."""
import os
from pathlib import Path


def quiet_parameter(path, value):
    try:
        Path(path).write_text(value)
        return True
    except OSError as exc:
        print('QUIET_BOOT_PARAMETER_SKIPPED %s: %s' % (path, exc), flush=True)
        return False


def main():
    quiet_parameter('/proc/sys/kernel/printk', '0 4 1 7\n')
    # DECTCEM alone only affects the current VT state. fbcon/VT resets can
    # create another visible cursor, so also change the kernel runtime default.
    quiet_parameter('/sys/module/vt/parameters/global_cursor_default', '0')
    quiet_parameter('/sys/class/graphics/fbcon/cursor_blink', '0')
    for terminal in ('/dev/tty1', '/dev/tty0'):
        try:
            fd = os.open(terminal, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
            try:
                os.write(fd, b'\x1b[?25l')
            finally:
                os.close(fd)
        except OSError as exc:
            print('QUIET_BOOT_CURSOR_SKIPPED %s: %s' % (terminal, exc), flush=True)
    print('QUIET_BOOT_FAST_READY (VT cursor default off; no framebuffer rewrite)', flush=True)


if __name__ == '__main__':
    main()

"""Rootfs text suppression only; retain the bootloader Sky Gauge splash."""
import os
from pathlib import Path


def main():
    try:
        Path('/proc/sys/kernel/printk').write_text('0 4 1 7\n')
    except OSError as exc:
        print('QUIET_BOOT_PRINTK_SKIPPED %s' % exc, flush=True)
    try:
        fd = os.open('/dev/tty1', os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            os.write(fd, b'\x1b[?25l')
        finally:
            os.close(fd)
    except OSError as exc:
        print('QUIET_BOOT_CURSOR_SKIPPED %s' % exc, flush=True)
    # No fb0 reads/writes, KMS modesets, media assets or sleeps.
    print('QUIET_BOOT_DIRECT_READY', flush=True)


if __name__ == '__main__':
    main()

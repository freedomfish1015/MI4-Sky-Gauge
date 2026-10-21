"""Rootfs-only boot curtain: suppress console output, paint cached dashboard.

Never opens a boot partition, changes console bindings or display power modes.
Normal kernel/journal ring buffers remain available for troubleshooting.
"""
import ctypes as C
import fcntl
import os
from pathlib import Path
import sys
import time

WIDTH, HEIGHT = 1080, 1920


class Bitfield(C.Structure):
    _fields_ = [('offset', C.c_uint32), ('length', C.c_uint32), ('msb_right', C.c_uint32)]


class Variable(C.Structure):
    _fields_ = [(key, C.c_uint32) for key in
                ('xres', 'yres', 'xres_virtual', 'yres_virtual', 'xoffset', 'yoffset',
                 'bits_per_pixel', 'grayscale')]
    _fields_ += [(key, Bitfield) for key in ('red', 'green', 'blue', 'transp')]
    _fields_ += [(key, C.c_uint32) for key in
                 ('nonstd', 'activate', 'height', 'width', 'accel_flags', 'pixclock',
                  'left_margin', 'right_margin', 'upper_margin', 'lower_margin',
                  'hsync_len', 'vsync_len', 'sync', 'vmode', 'rotate', 'colorspace')]
    _fields_ += [('reserved', C.c_uint32 * 4)]


class Fixed(C.Structure):
    _fields_ = [('id', C.c_char * 16), ('smem_start', C.c_ulong),
                ('smem_len', C.c_uint32), ('type', C.c_uint32),
                ('type_aux', C.c_uint32), ('visual', C.c_uint32),
                ('xpanstep', C.c_uint16), ('ypanstep', C.c_uint16),
                ('ywrapstep', C.c_uint16), ('line_length', C.c_uint32),
                ('mmio_start', C.c_ulong), ('mmio_len', C.c_uint32),
                ('accel', C.c_uint32), ('capabilities', C.c_uint16),
                ('reserved', C.c_uint16 * 2)]


def info(fd):
    var, fixed = Variable(), Fixed()
    fcntl.ioctl(fd, 0x4600, var, True)    # FBIOGET_VSCREENINFO: read-only
    fcntl.ioctl(fd, 0x4602, fixed, True)  # FBIOGET_FSCREENINFO: read-only
    return var, fixed


def validate(var, fixed, pixels):
    if (var.xres, var.yres, var.bits_per_pixel) != (WIDTH, HEIGHT, 32):
        raise ValueError('Unexpected framebuffer geometry')
    if var.xoffset or var.yoffset or var.grayscale or var.nonstd:
        raise ValueError('Unexpected framebuffer offsets/format')
    if [(b.offset, b.length, b.msb_right) for b in (var.red, var.green, var.blue)] != [
            (16, 8, 0), (8, 8, 0), (0, 8, 0)]:
        raise ValueError('Framebuffer is not native little-endian XRGB/ARGB')
    if fixed.type != 0 or fixed.visual != 2:
        raise ValueError('Framebuffer is not packed truecolor')
    if not WIDTH * 4 <= fixed.line_length <= WIDTH * 4 + 4096:
        raise ValueError('Unexpected framebuffer stride')
    if fixed.smem_len < fixed.line_length * HEIGHT or len(pixels) != WIDTH * HEIGHT * 4:
        raise ValueError('Framebuffer/artwork bounds mismatch')


def padded_pixels(pixels, stride):
    if stride == WIDTH * 4:
        return pixels
    output = bytearray(stride * HEIGHT)
    for y in range(HEIGHT):
        output[y * stride:y * stride + WIDTH * 4] = pixels[y * WIDTH * 4:(y + 1) * WIDTH * 4]
    return output


def suppress():
    Path('/proc/sys/kernel/printk').write_text('0 4 1 7\n')
    # Hide only the text cursor. Do not change KD mode, VT bindings or KMS.
    fd = os.open('/dev/tty1', os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        os.write(fd, b'\x1b[?25l')
    finally:
        os.close(fd)


def paint(path):
    pixels = Path(path).read_bytes()
    fd = os.open('/dev/fb0', os.O_RDWR | os.O_CLOEXEC)
    try:
        var, fixed = info(fd)
        validate(var, fixed, pixels)
        data = padded_pixels(pixels, fixed.line_length)
        done = 0
        while done < len(data):
            count = os.pwrite(fd, memoryview(data)[done:], done)
            if count <= 0:
                raise OSError('Framebuffer short write')
            done += count
        return fixed.line_length
    finally:
        os.close(fd)


def main():
    if sys.argv[1:] == ['--inspect']:
        fd = os.open('/dev/fb0', os.O_RDONLY)
        try:
            var, fixed = info(fd)
            validate(var, fixed, bytes(WIDTH * HEIGHT * 4))
            print('FB_OK %dx%d bpp=%d stride=%d bytes=%d name=%s ABI=%d/%d' % (
                var.xres, var.yres, var.bits_per_pixel, fixed.line_length,
                fixed.smem_len, fixed.id.decode(), C.sizeof(var), C.sizeof(fixed)))
        finally:
            os.close(fd)
        return
    if len(sys.argv) != 2:
        raise SystemExit('Usage: boot_curtain.py native-1080.argb | --inspect')
    suppress()
    until = time.monotonic() + 2
    while not Path('/dev/fb0').exists() and time.monotonic() < until:
        time.sleep(.05)
    stride = paint(sys.argv[1])
    print('BOOT_CURTAIN_PAINTED stride=%d (no boot/kernel changes)' % stride, flush=True)


if __name__ == '__main__':
    main()

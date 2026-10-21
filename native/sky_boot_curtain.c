/* Rootfs-only framebuffer curtain. No modesets, blanking or block devices. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <time.h>
#include <unistd.h>

#define WIDTH 1080u
#define HEIGHT 1920u
#define ROW_BYTES (WIDTH * 4u)
#define PIXEL_BYTES (ROW_BYTES * HEIGHT)
#define HANDOFF "/run/obd-gauge/logo-handoff"
#define LOGO_LOCK "/run/obd-gauge-logo.lock"

static int handoff_requested(void) {
    struct stat st;
    char data[32] = {0};
    int fd = open(HANDOFF, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return 0;
    int valid = !fstat(fd, &st) && S_ISREG(st.st_mode) && st.st_uid == 1000;
    ssize_t count = valid ? read(fd, data, sizeof(data) - 1) : -1;
    close(fd);
    if (count <= 0) return 0;
    char *end;
    long pid = strtol(data, &end, 10);
    return end != data && pid > 1 && pid <= INT32_MAX && kill((pid_t)pid, 0) == 0;
}

static int userspace_drm_master(void) {
    FILE *file = fopen("/sys/kernel/debug/dri/0/clients", "r");
    if (!file) return 0;
    char line[512], command[80], master, active;
    int pid, device, found = 0;
    unsigned uid;
    while (fgets(line, sizeof(line), file)) {
        if (sscanf(line, "%79s %d %d %c %c %u", command, &pid, &device,
                   &master, &active, &uid) == 6 && master == 'y') {
            found = 1;
            break;
        }
    }
    fclose(file);
    return found;
}

static int changed_rows(int fb, const uint8_t *pixels, size_t stride) {
    uint8_t row[ROW_BYTES];
    for (unsigned i = 0; i < 10; i++) {
        unsigned y = (HEIGHT - 1) * i / 9;
        off_t offset = (off_t)y * stride;
        if (pread(fb, row, sizeof(row), offset) != sizeof(row)) return -1;
        if (memcmp(row, pixels + offset, sizeof(row))) return 1;
    }
    return 0;
}

static int valid_geometry(const struct fb_var_screeninfo *v,
                          const struct fb_fix_screeninfo *f) {
    return v->xres == WIDTH && v->yres == HEIGHT && v->bits_per_pixel == 32 &&
        !v->xoffset && !v->yoffset && !v->grayscale && !v->nonstd &&
        v->red.offset == 16 && v->green.offset == 8 && v->blue.offset == 0 &&
        v->red.length == 8 && v->green.length == 8 && v->blue.length == 8 &&
        !v->red.msb_right && !v->green.msb_right && !v->blue.msb_right &&
        f->type == FB_TYPE_PACKED_PIXELS && f->visual == FB_VISUAL_TRUECOLOR &&
        f->line_length >= ROW_BYTES && f->line_length <= ROW_BYTES + 4096 &&
        f->smem_len >= (size_t)f->line_length * HEIGHT;
}

static double monotonic(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return 0;
    return t.tv_sec + t.tv_nsec / 1e9;
}

static void quiet_write(const char *path, const char *value) {
    int fd = open(path, O_WRONLY | O_CLOEXEC | O_NOCTTY | O_NONBLOCK);
    if (fd >= 0) {
        ssize_t ignored = write(fd, value, strlen(value));
        (void)ignored;
        close(fd);
    }
}

static int read_exact(int fd, uint8_t *data, size_t size) {
    size_t done = 0;
    while (done < size) {
        ssize_t n = read(fd, data + done, size - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        done += (size_t)n;
    }
    return 0;
}

static int write_exact(int fd, const uint8_t *data, size_t size, off_t offset) {
    size_t done = 0;
    while (done < size) {
        ssize_t n = pwrite(fd, data + done, size - done, offset + (off_t)done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        done += (size_t)n;
    }
    return 0;
}

#ifdef SKY_NATIVE_TEST
#include <assert.h>
int main(void) {
    struct fb_var_screeninfo v = {0};
    struct fb_fix_screeninfo f = {0};
    v.xres = WIDTH; v.yres = HEIGHT; v.bits_per_pixel = 32;
    v.red.offset = 16; v.green.offset = 8;
    v.red.length = v.green.length = v.blue.length = 8;
    f.type = FB_TYPE_PACKED_PIXELS; f.visual = FB_VISUAL_TRUECOLOR;
    f.line_length = 4352; f.smem_len = f.line_length * HEIGHT;
    assert(valid_geometry(&v, &f));
    v.xoffset = 1; assert(!valid_geometry(&v, &f)); v.xoffset = 0;
    v.red.offset = 0; assert(!valid_geometry(&v, &f)); v.red.offset = 16;
    v.bits_per_pixel = 24; assert(!valid_geometry(&v, &f)); v.bits_per_pixel = 32;
    f.line_length = ROW_BYTES - 1; assert(!valid_geometry(&v, &f)); f.line_length = 4352;
    f.smem_len--; assert(!valid_geometry(&v, &f));
    FILE *temporary = tmpfile();
    assert(temporary);
    int fd = fileno(temporary);
    assert(!ftruncate(fd, PIXEL_BYTES));
    uint8_t *pixels = calloc(1, PIXEL_BYTES);
    assert(pixels && changed_rows(fd, pixels, ROW_BYTES) == 0);
    uint8_t byte = 1;
    assert(pwrite(fd, &byte, 1, 0) == 1);
    assert(changed_rows(fd, pixels, ROW_BYTES) == 1);
    assert(!ftruncate(fd, 0));
    assert(changed_rows(fd, pixels, ROW_BYTES) == -1);
    free(pixels);
    fclose(temporary);
    puts("SKY_NATIVE_GEOMETRY_AND_REPAINT_GUARDS_OK (9 cases)");
    return 0;
}
#else
int main(int argc, char **argv) {
    const int inspect = argc == 2 && !strcmp(argv[1], "--inspect");
    const int hold = argc == 3 && !strcmp(argv[1], "--hold-logo");
    int fb = -1, image = -1, lock = -1, result = 1;
    uint8_t *pixels = NULL;
    struct fb_var_screeninfo v;
    struct fb_fix_screeninfo f;
    struct stat st;
    double started = monotonic();
    if (argc != 2 && !hold) {fprintf(stderr, "Usage: sky_boot_curtain native-1080.argb | --inspect | --quiet-only | --hold-logo native-1080.argb\n"); return 2;}
    if (!inspect) {
        quiet_write("/proc/sys/kernel/printk", "0 4 1 7\n");
        quiet_write("/sys/module/vt/parameters/global_cursor_default", "0");
        quiet_write("/sys/class/graphics/fbcon/cursor_blink", "0");
        quiet_write("/dev/tty1", "\033[?25l");
        quiet_write("/dev/tty0", "\033[?25l");
    }
    if (!strcmp(argv[1], "--quiet-only")) {
        puts("SKY_QUIET_ONLY (no framebuffer access)");
        return 0;
    }
    do {
        fb = open("/dev/fb0", (inspect ? O_RDONLY : O_RDWR) | O_CLOEXEC | O_NOFOLLOW);
        if (fb >= 0 || inspect || errno != ENOENT) break;
        struct timespec pause = {.tv_sec = 0, .tv_nsec = 20000000};
        nanosleep(&pause, NULL);
    } while (monotonic() - started < 1.5);
    if (fb < 0 || fstat(fb, &st) || !S_ISCHR(st.st_mode) || major(st.st_rdev) != 29 || minor(st.st_rdev) != 0) {
        fprintf(stderr, "SKY_CURTAIN_FRAMEBUFFER_UNAVAILABLE\n"); goto out;
    }
    if (ioctl(fb, FBIOGET_VSCREENINFO, &v) || ioctl(fb, FBIOGET_FSCREENINFO, &f) || !valid_geometry(&v, &f)) {
        fprintf(stderr, "SKY_CURTAIN_GEOMETRY_REJECTED\n"); goto out;
    }
    if (inspect) {
        printf("SKY_FB_OK %ux%u bpp=%u stride=%u bytes=%u ABI=%zu/%zu\n",
               v.xres, v.yres, v.bits_per_pixel, f.line_length, f.smem_len, sizeof(v), sizeof(f));
        result = 0; goto out;
    }
    image = open(argv[hold ? 2 : 1], O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (image < 0 || fstat(image, &st) || !S_ISREG(st.st_mode) || st.st_size != PIXEL_BYTES) {
        fprintf(stderr, "SKY_CURTAIN_ASSET_REJECTED\n"); goto out;
    }
    pixels = calloc(HEIGHT, f.line_length);
    if (!pixels) goto out;
    for (unsigned y = 0; y < HEIGHT; y++) {
        if (read_exact(image, pixels + (size_t)y * f.line_length, ROW_BYTES)) {
            fprintf(stderr, "SKY_CURTAIN_SHORT_IMAGE\n"); goto out;
        }
    }
    if (hold) {
        lock = open(LOGO_LOCK, O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0644);
        if (lock < 0 || fstat(lock, &st) || !S_ISREG(st.st_mode) || st.st_uid != 0) {
            fprintf(stderr, "SKY_CURTAIN_LOCK_REJECTED\n"); goto out;
        }
    }
    unsigned paints = 0;
    do {
        if (hold && flock(lock, LOCK_EX)) goto out;
        // The launcher writes its marker under the same lock. No framebuffer
        // writes can race with this launcher's SDL acquisition. Also stop if
        // another userspace KMS owner (e.g. charging UI) is already present.
        if (hold && (handoff_requested() || userspace_drm_master())) {
            flock(lock, LOCK_UN);
            break;
        }
        int changed = paints ? changed_rows(fb, pixels, f.line_length) : 1;
        if (changed < 0) {if (hold) flock(lock, LOCK_UN); goto out;}
        if (changed && write_exact(fb, pixels, (size_t)HEIGHT * f.line_length, 0)) {
            if (hold) flock(lock, LOCK_UN);
            fprintf(stderr, "SKY_CURTAIN_WRITE_FAILED\n"); goto out;
        }
        if (changed) {
            paints++;
            printf("SKY_CURTAIN_PAINTED uptime=%.3f elapsed=%.3f stride=%u count=%u\n",
                   monotonic(), monotonic() - started, f.line_length, paints);
            fflush(stdout);
        }
        if (hold) flock(lock, LOCK_UN);
        if (!hold) break;
        struct timespec pause = {.tv_sec = 0, .tv_nsec = 100000000};
        nanosleep(&pause, NULL);
    } while (monotonic() - started < 35);
    if (hold) printf("SKY_CURTAIN_HOLD_END uptime=%.3f paints=%u\n", monotonic(), paints);
    result = 0;
out:
    free(pixels);
    if (image >= 0) close(image);
    if (fb >= 0) close(fb);
    if (lock >= 0) close(lock);
    return result;
}
#endif

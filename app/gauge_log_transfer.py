"""Small lazy UI client; does not enable Wi-Fi or create any boot-time worker."""
import json
from pathlib import Path
import subprocess
import threading

RUN = Path('/run/obd-log-transfer')


class TransferClient:
    def __init__(self):
        self.busy = False
        self.error = ''
        self.images = {}

    def read(self):
        try:
            data = json.loads((RUN / 'state.json').read_text())
        except (OSError, ValueError):
            data = dict(phase='off', message='热点未开启')
        if self.busy: data = dict(data, phase='starting', message='正在切换共享服务…')
        if self.error: data = dict(data, message=self.error)
        return data

    def signature(self):
        try:
            info = (RUN / 'state.json').stat()
            changed = (info.st_mtime_ns, info.st_size)
        except OSError:
            changed = ()
        return changed, self.busy, self.error

    def tap(self, x, y):
        if self.busy or not (432 <= x <= 616 and 112 <= y <= 158):
            return
        action = 'stop' if self.read().get('phase') in ('ready', 'starting') else 'start'
        self.busy, self.error = True, ''
        def worker():
            try:
                result = subprocess.run(['/usr/bin/sudo', '-n', '/usr/local/lib/obd-log-transfer/control.py', action],
                    timeout=15, check=False, capture_output=True)
                if result.returncode:
                    self.error = '共享服务切换失败，请稍后重试'
            except (OSError, subprocess.TimeoutExpired):
                self.error = '共享服务暂不可用'
            finally:
                self.busy = False
        threading.Thread(target=worker, name='log-transfer-control', daemon=True).start()


def paint(gauge, client):
    cr = gauge.cr
    state = client.read()
    ready = state.get('phase') == 'ready'
    foreground, dim, accent = (gauge.theme[key] for key in ('text', 'dim', 'accent'))
    def text(x, y, value, size=11, color=None, align='left'):
        gauge.text(cr, x, y, str(value), size, color or foreground, align=align)
    def qr(name, center):
        path = RUN / name
        try:
            stamp = path.stat().st_mtime_ns
            if name not in client.images or client.images[name][0] != stamp:
                import cairo
                client.images[name] = stamp, cairo.ImageSurface.create_from_png(str(path))
            surface = client.images[name][1]
            import cairo
            factor = max(1, 138 // surface.get_width())
            extent = factor * surface.get_width()
            cr.save(); cr.translate(int(center - extent / 2), int(218 - extent / 2)); cr.scale(factor, factor)
            cr.set_source_surface(surface, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint(); cr.restore()
        except Exception:
            text(center, 218, '二维码准备中', 11, dim, 'center')
    text(28, 91, state.get('message', '')[:52], 11, accent if ready else dim)
    gauge.rounded_card(cr, 24, 112, 226, 206, 10)
    text(137, 132, '扫码连接 · LOG 下载', 13, align='center')
    if ready: qr('pairing.png', 137)
    else: text(137, 218, '开启热点后显示', 11, dim, 'center')
    text(137, 302, '请在配套小程序内扫描', 10, dim, 'center')
    gauge.rounded_card(cr, 432, 112, 184, 46, 10)
    text(524, 135, '关闭共享' if ready else '正在开启…' if state.get('phase') == 'starting' else '开启热点', 15, accent, 'center')
    text(274, 133, 'mi4-sky · LOG', 13, accent)
    text(274, 179, '热点：' + state.get('ssid', 'mi4-sky'), 11)
    text(274, 203, '密码：' + state.get('password', '开启后显示'), 11)
    text(274, 231, '先打开小程序，再点“扫描仪表”', 11)
    text(274, 255, '确认连接热点 → 选择 LOG 下载', 11, accent)
    text(274, 283, '已连接 %d 台 · 可导出 %d 个文件' % (state.get('stations', 0), state.get('files', 0)), 11)
    text(274, 305, 'RaceChrono CSV v3 · 15 分钟自动关闭', 10, dim)
    text(24, 341, '离线直传 · 不上传云端 · 不删除原文件 · 热点无互联网是正常现象', 10, dim)

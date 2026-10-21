"""Unprivileged touch client and modal for the root-owned cable policy."""
import json
from pathlib import Path
import socket
import time

BUTTON = (200, 244, 240, 44)
MODAL_PHASES = ('waiting_ui', 'countdown', 'shutdown', 'error')


class PowerClient:
    def __init__(self, directory='/run/obd-power'):
        self.directory = Path(directory)
        self.next_poll = self.next_heartbeat = 0
        self.state = None
        self.start = None

    def send(self, command):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(.2)
                connection.connect(str(self.directory / 'control.sock'))
                connection.sendall(json.dumps(dict(command=command)).encode())
                return json.loads(connection.recv(128)).get('ok') is True
        except (OSError, ValueError, AttributeError):
            return False

    def poll(self):
        now = time.monotonic()
        if now >= self.next_heartbeat:
            self.send('heartbeat')
            self.next_heartbeat = now + 1
        if now >= self.next_poll:
            try:
                raw = json.loads((self.directory / 'state.json').read_text())
                self.state = raw if raw.get('phase') in MODAL_PHASES else None
            except (OSError, ValueError, AttributeError):
                self.state = None
            self.next_poll = now + .1
        return self.state

    def shutdown(self):
        accepted = self.send('shutdown')
        if accepted:
            self.next_poll = 0
        return accepted

    def input(self, kind, x, y, stamp=None):
        if kind == 'down':
            self.start = (x, y)
        elif kind == 'up':
            start, self.start = self.start, None
            bx, by, bw, bh = BUTTON
            if (start is not None and abs(start[0] - x) < 18 and abs(start[1] - y) < 18
                    and bx <= start[0] <= bx + bw and by <= start[1] <= by + bh
                    and bx <= x <= bx + bw and by <= y <= by + bh):
                if self.send('keep_on'):
                    self.next_poll = 0


def paint_modal(gauge, state, backdrop):
    import cairo
    cr = gauge.cr
    cr.save()
    cr.identity_matrix()
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_surface(backdrop, 0, 0)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    gauge.apply_layout(cr)
    cr.set_source_rgba(.04, .10, .18, .57)
    cr.rectangle(0, 0, 640, 360)
    cr.fill()
    gauge.rounded_card(cr, 150, 57, 340, 248, 15)
    theme = gauge.theme
    manual = state.get('reason') == 'manual'
    gauge.text(cr, 320, 86, '正在安全关机' if manual else '外部电源已断开',
               19, theme['text'], 'bold')
    phase = state['phase']
    remaining = ('--' if phase == 'error' else
                 str(state.get('remaining', 20)) if phase != 'shutdown' else '0')
    gauge.text(cr, 320, 147, remaining, 52, theme['accent'], 'bold')
    message = ('正在安全关机…' if phase == 'shutdown' else
               state.get('message') or '秒后自动关机')
    gauge.text(cr, 320, 195, message, 12, theme['text'])
    if phase == 'shutdown':
        gauge.text(cr, 320, 244, '请等待系统完成关机', 13, theme['dim'])
    else:
        gauge.text(cr, 320, 220, '重新接入电源将取消倒计时', 10, theme['dim'])
        gauge.rounded_card(cr, *BUTTON, radius=8)
        gauge.text(cr, 320, 266, '保持开机', 16, theme['accent'], 'bold')
    cr.restore()
    gauge.surface.flush()

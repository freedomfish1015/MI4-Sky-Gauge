"""Bounded local telemetry capture and a native-resolution, GT-style trace page.

Samples are raw source snapshots, never dashboard interpolation/startup sweep.
The render thread only enqueues; disk IO and rotation belong to one writer.
"""
from collections import deque
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import threading
import time
import uuid
from gauge_motion import acceleration_available

CHANNELS = (
    ('speed', '车速', 'km/h', 0, 240, (.16, .72, .61)),
    ('rpm', '转速', 'RPM', 0, 8000, (.18, .63, .91)),
    ('throttle', '节气门', '%', 0, 100, (.88, .56, .20)),
    ('gx', '横轴 G', 'G', -2.2, 2.2, (.70, .42, .81)),
    ('gy', '纵轴 G', 'G', -2.2, 2.2, (.89, .40, .44)),
)
STOP = object()
FLUSH = object()
CLOSE = object()


def finite(value):
    return float(value) if type(value) in (float, int) and math.isfinite(value) else None


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    if type(value) is float and not math.isfinite(value):
        return None
    return value


class Telemetry:
    def __init__(self, directory=None, enabled=True, max_bytes=5*1024*1024, max_files=8):
        self.directory = Path(directory or Path.home() / '.local/state/obd-gauge/telemetry')
        self.max_bytes, self.max_files = max_bytes, max_files
        self.history = deque(maxlen=620)
        self.frozen = None
        self.last_sample = -math.inf
        self.recording = enabled
        self.enabled = enabled
        self.trip = ''
        self.error = ''
        self.dropped = 0
        self.path = None
        self.pending = queue.Queue(maxsize=256)
        self.worker = None
        self.closed = False
        self.session = uuid.uuid4().hex[:12]
        if enabled:
            self._start()

    def _start(self):
        if self.worker is None:
            self.worker = threading.Thread(target=self._write, name='telemetry-log', daemon=True)
            self.worker.start()

    def _enqueue(self, item):
        try:
            self.pending.put_nowait(item)
        except queue.Full:
            self.dropped += 1

    def set_recording(self, enabled):
        if self.closed:
            return
        self.recording = bool(enabled)
        if enabled:
            self._start()
        elif self.worker:
            self._enqueue(FLUSH)

    def sync_trip(self, motion):
        # The daemon's acknowledged state, not a button press, owns the trip.
        # An absent/stale state must not falsely end a recording.
        if not self.enabled or 'recording' not in motion:
            return
        trip = str(motion.get('track') or '') if motion['recording'] else ''
        if trip == self.trip or (motion['recording'] and not trip):
            return
        self._enqueue(CLOSE)
        self.trip = trip
        self.set_recording(bool(trip))

    def toggle_pause(self):
        # Freeze a COPY, not a timestamp into the rolling history that expires.
        self.frozen = list(self.history) if self.frozen is None else None

    def sample(self, now, values, signals, motion, status='', context=None):
        if self.closed or now - self.last_sample < .099:
            return False
        self.last_sample = now
        self.sync_trip(motion)
        imu = motion.get('imu', {})
        xy = imu.get('display_g', ()) if acceleration_available(imu) else ()
        vector = list(xy)[:2] if isinstance(xy, (list, tuple)) else []
        channels = dict(rpm=finite(values.get('rpm')), speed=finite(values.get('speed')),
                        throttle=finite(signals.get('obd.throttle')),
                        gear=finite(signals.get('obd.gear')),
                        coolant=finite(signals.get('obd.coolant_temp', values.get('coolant'))),
                        oil=finite(signals.get('obd.oil_temp', values.get('oil'))),
                        gx=finite(vector[0]) if len(vector) == 2 else None,
                        gy=finite(vector[1]) if len(vector) == 2 else None)
        record = dict(type='sample', utc=datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                      t=now, channels=channels, values=clean(values), signals=clean(signals),
                      connection=str(status), context=clean(context or {}))
        record['trip'] = self.trip or None
        record['acceleration'] = clean(dict(mode=imu.get('measurement_mode', 'legacy_relative'),
            includes_gravity=imu.get('includes_gravity'), accel_g=imu.get('accel_g'),
            accel_ms2=imu.get('accel_ms2'), total_g=imu.get('total_g'),
            dynamic_g=imu.get('dynamic_g'), sustained_g_valid=imu.get('sustained_g_valid'),
            filter_tau_s=imu.get('filter_tau_s'), deadzone_g=imu.get('deadzone_g')))
        # Keep GPS timestamps/fix status with every car/G sample for alignment.
        gps = motion.get('gps', {})
        valid = bool(gps.get('fix'))
        record['gps'] = clean(dict(fix=valid, utc=gps.get('utc') if valid else None,
            latitude=gps.get('latitude') if valid else None,
            longitude=gps.get('longitude') if valid else None,
            accuracy_m=gps.get('accuracy_m') if valid else None,
            speed_ms=gps.get('speed_ms') if valid else None))
        self.history.append(record)
        if self.recording:
            self._enqueue(record)
        return True

    def _open(self, trip=None):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Only our uniquely prefixed logs are rotated; GPS tracks are elsewhere.
        files = sorted(self.directory.glob('telemetry-*.jsonl'), key=lambda p: p.name)
        for old in files[:max(0, len(files)-self.max_files+1)]:
            old.unlink()
        name = 'telemetry-%s-%s.jsonl' % (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'), uuid.uuid4().hex[:8])
        self.path = self.directory / name
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        stream = os.fdopen(fd, 'w', encoding='utf-8')
        header = dict(type='header', schema='mi4.telemetry/1', session=self.session,
                      trip=trip, gps_track=(trip+'.csv') if trip else None,
                      sample_hz=10, units=dict(rpm='RPM', speed='km/h', throttle='%', gx='G', gy='G',
                                               gear='gear', coolant='degC', oil='degC'),
                      missing='null', g_coordinates='mounted display axes; see per-sample acceleration metadata',
                      channel_meaning=dict(throttle='throttle opening, NOT accelerator or brake pedal',
                                           gx='mounted display X, NOT vehicle-calibrated lateral G',
                                           gy='mounted display Y, NOT vehicle-calibrated longitudinal G'),
                      note='raw source snapshots; values repeat between OBD responses, not unique ECU samples')
        stream.write(json.dumps(header, ensure_ascii=False)+'\n')
        return stream

    def _write(self):
        stream = None
        size = 0
        stream_trip = None
        flushed = time.monotonic()
        try:
            while True:
                try:
                    item = self.pending.get(timeout=.5)
                except queue.Empty:
                    item = FLUSH
                if item is STOP:
                    break
                if item is CLOSE:
                    if stream:
                        stream.close()
                    stream, size = None, 0
                    continue
                if item is FLUSH:
                    if stream:
                        stream.flush()
                    continue
                try:
                    line = json.dumps(item, ensure_ascii=False, allow_nan=False)+'\n'
                    length = len(line.encode('utf-8'))
                    trip = item.get('trip')
                    if stream is None or trip != stream_trip or size + length > self.max_bytes:
                        if stream:
                            stream.close()
                        stream = self._open(trip)
                        stream_trip = trip
                        size = stream.tell()
                    stream.write(line)
                    size += length
                    if time.monotonic()-flushed >= 1:
                        stream.flush()
                        flushed = time.monotonic()
                    self.error = ''
                except (OSError, ValueError, TypeError) as exc:
                    self.error = str(exc)[:120]
                    if stream:
                        stream.close()
                    stream = None
                    self.dropped += 1
        finally:
            if stream:
                stream.close()

    def close(self):
        self.closed = True
        self.recording = False
        if self.worker:
            try:
                self.pending.put(STOP, timeout=1)
                self.worker.join(timeout=2)
            except queue.Full:
                self.error = '日志写入队列未能及时清空'


def paint(gauge, telemetry):
    cr = gauge.cr
    cr.save()
    cr.identity_matrix()
    cr.set_source_rgb(*gauge.theme['background'])
    cr.paint()
    gauge.apply_layout(cr)
    text_color, dim = gauge.theme['text'], gauge.theme['dim']
    def text(x, y, value, size=11, color=None, align='left'):
        gauge.text(cr, x, y, str(value), size, color or text_color, align=align)
    def button(x, w, label):
        gauge.rounded_card(cr, x, 6, w, 32, 6)
        text(x+w/2, 22, label, 11, align='center')
    button(12, 82, '‹ 仪表')
    text(113, 22, '赛道 LOG', 15)
    button(390, 100, '继续曲线' if telemetry.frozen is not None else '暂停曲线')
    button(500, 128, '停止记录' if telemetry.recording else '开始记录')
    history = list(telemetry.history) if telemetry.frozen is None else telemetry.frozen
    end = history[-1]['t'] if history else time.monotonic()
    rows = [r for r in history if end-30 <= r['t'] <= end]
    current = rows[-1] if rows else {}
    if current.get('context', {}).get('simulated_source'):
        text(225, 22, '台架模拟数据', 11, (.80,.20,.25))
    for index, (key, label, unit, low, high, color) in enumerate(CHANNELS):
        top = 51+index*48
        left, width, height = 145, 473, 40
        text(17, top+4, label, 11)
        value = current.get('channels', {}).get(key)
        number = '--' if value is None else ('%+.2f' % value if key in ('gx','gy') else '%.0f' % value)
        text(17, top+22, number+' '+unit, 14, color)
        available = [r['channels'].get(key) for r in rows if r['channels'].get(key) is not None]
        if value is None:
            note = '当前未提供' if key not in ('gx','gy') else '等待加速度计'
        elif available:
            if key in ('gx','gy'):
                note = '峰值 %+.2f / %+.2f' % (min(available),max(available))
            else:
                note = '30s 峰值 %.0f' % max(available)
        else:
            note = ''
        text(17, top+38, note, 8, dim)
        cr.set_source_rgba(*dim, .18)
        cr.set_line_width(.5)
        for n in range(7):
            x = left+n*width/6
            cr.move_to(x, top); cr.line_to(x, top+height)
        for n in range(3):
            y = top+n*height/2
            cr.move_to(left, y); cr.line_to(left+width, y)
        cr.stroke()
        if low < 0 < high:
            zero = top+height*high/(high-low)
            cr.set_source_rgba(*dim, .45)
            cr.set_line_width(.7)
            cr.move_to(left,zero); cr.line_to(left+width,zero); cr.stroke()
        text(left-5, top+4, high, 8, dim, 'right')
        text(left-5, top+height-3, low, 8, dim, 'right')
        cr.save()
        cr.rectangle(left, top, width, height); cr.clip()
        for channel, tint in ((key, color),):
            cr.set_source_rgb(*tint)
            cr.set_line_width(1.4)
            previous = None
            for row in rows:
                v = row['channels'].get(channel)
                if v is None:
                    previous = None
                    continue
                x = left+(row['t']-end+30)/30*width
                y = top+height*(1-(max(low,min(high,v))-low)/(high-low))
                if previous is None or row['t']-previous > .35:
                    cr.move_to(x,y)
                else:
                    cr.line_to(x,y)
                previous = row['t']
            cr.stroke()
        cr.restore()
    for n in range(7):
        text(145+n*473/6, 300, ('现在' if n == 6 else '-%ds' % (30-n*5)), 9, dim, 'center')
    def metric(key, label, unit=''):
        value = current.get('channels', {}).get(key)
        return label+' '+('--' if value is None else '%.0f' % value)+unit
    text(17, 320, '   ·   '.join((metric('gear','档位'),metric('coolant','水温','°C'),
                                   metric('oil','油温','°C'))), 11)
    mode = current.get('acceleration', {}).get('mode')
    note = ('动态 G 自动回中 · 不测持续侧向 G · 节气门≠踏板/刹车' if mode == 'accelerometer_autocenter' else
            '加速度计直读（含重力） · 无需静置归零 · 节气门≠踏板/刹车' if mode == 'accelerometer_raw' else
            '节气门不代表踏板/刹车 · G 为手机安装坐标，未标定车辆方向')
    text(17, 334, note, 8, dim)
    status = ('写入错误：'+telemetry.error if telemetry.error else
              ('● GPS 行程联动 / 10 Hz' if telemetry.trip else
               '● 本机记录中 / 10 Hz' if telemetry.recording else '○ 已停止文件记录'))
    if telemetry.dropped:
        status += ' · 丢弃 %d 条' % telemetry.dropped
    text(16, 350, status, 9, (.80,.20,.25) if telemetry.error else dim)
    text(624, 350, '最近 30 秒 · 上滑返回 · 缺失留空', 9, dim, 'right')
    cr.restore()

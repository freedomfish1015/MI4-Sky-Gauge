#!/usr/bin/env python3
"""Local IIO motion sampling + QRTR GNSS; never upload coordinates."""
import collections
import csv
import datetime
import glob
import json
import math
import os
from pathlib import Path
import select
import signal
import struct
import time
from xml.sax.saxutils import escape
from mi4_satellite_log import satellite_metadata
from mi4_accel_autocenter import AutoCenter

G = 9.80665
CONTROL = Path('/home/umeko/.config/obd-gauge/motion-control.json')
STATE = Path('/run/obd-motion/state.json')
TRACKS = Path('/var/lib/obd-motion/tracks')


def directional_peaks(peaks, x, y):
    return [max(old, value) for old, value in zip(peaks, (-y, y, -x, x))]


def accumulate_envelope(bins, x, y):
    index = int((math.atan2(y,x) + math.pi) / math.tau * len(bins)) % len(bins)
    old = bins[index]
    if old is None or x*x+y*y > old[0]*old[0]+old[1]*old[1]:
        bins[index] = (x,y)


class RollingEnvelope:
    """Maximum measured radius per angle sector, restricted to recent 5 s."""
    def __init__(self, seconds=5., sectors=72):
        self.seconds, self.sectors = seconds, sectors
        self.samples = collections.deque(maxlen=512)

    def clear(self):
        self.samples.clear()

    def add(self, x, y, stamp):
        if all(math.isfinite(v) for v in (x,y,stamp)) and x*x+y*y > 1e-10:
            self.samples.append((stamp,x,y))

    def points(self, now):
        while self.samples and now-self.samples[0][0] >= self.seconds:
            self.samples.popleft()
        bins = [None]*self.sectors
        for stamp,x,y in self.samples:
            if 0 <= now-stamp < self.seconds:
                accumulate_envelope(bins,x,y)
        return [point for point in bins if point is not None]


class PersistentEnvelope:
    """Bounded per-direction peak area; no time expiry or idle reset."""
    def __init__(self, sectors=72):
        self.sectors = sectors
        self.clear()

    def clear(self):
        self.bins = [None]*self.sectors

    def add(self, x, y, stamp=None):
        if all(math.isfinite(v) for v in (x,y)) and x*x+y*y > 1e-10:
            accumulate_envelope(self.bins,x,y)

    def points(self, now=None):
        return [point for point in self.bins if point is not None]


def acceleration_state(latest, sampled_at, now):
    """Direct accelerometer output, SI scale -> G; no zero/bias/gravity removal."""
    ready = (isinstance(latest, (list,tuple)) and len(latest) == 3
             and all(type(v) in (int,float) and math.isfinite(v) for v in latest)
             and 0 <= now-sampled_at < 1)
    state = dict(ready=ready, calibrated=False, calibration_required=False,
                 measurement_mode='accelerometer_raw', includes_gravity=True,
                 gyro_enabled=False)
    if ready:
        vector = [v/G for v in latest]
        state.update(accel_ms2=list(latest), accel_g=vector, display_g=vector[:2],
                     total_g=math.sqrt(sum(v*v for v in vector)),
                     plane_g=math.hypot(*vector[:2]))
    return state


def auto_center_state(latest, sampled_at, now, auto):
    state = acceleration_state(latest, sampled_at, now)
    state.update(measurement_mode='accelerometer_autocenter', includes_gravity=False,
                 raw_includes_gravity=True, gravity_removal='estimated low-pass baseline',
                 filter_tau_s=auto.tau, deadzone_g=auto.deadzone,
                 sustained_g_valid=False)
    state['ready'] = state['ready'] and auto.dynamic is not None
    if state['ready']:
        vector = list(auto.dynamic)
        state.update(raw_total_g=state['total_g'], dynamic_g=vector,
                     display_g=vector[:2], total_g=math.sqrt(sum(v*v for v in vector)),
                     plane_g=math.hypot(*vector[:2]), gravity_estimate_g=list(auto.baseline))
    return state


def atomic_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


class Sensor:
    def __init__(self, name, kind):
        self.path = next(p for p in Path('/sys/bus/iio/devices').glob('iio:device*')
                         if (p / 'name').read_text().strip() == name)
        self.kind = kind
        self.scale = float((self.path / ('in_' + kind + '_scale')).read_text())
        (self.path / 'buffer/enable').write_text('0')
        for item in (self.path / 'scan_elements').glob('*_en'):
            item.write_text('1')
        (self.path / ('in_' + kind + '_sampling_frequency')).write_text('50')
        (self.path / 'buffer/length').write_text('128')
        self.fd = os.open('/dev/' + self.path.name, os.O_RDONLY | os.O_NONBLOCK)
        (self.path / 'buffer/enable').write_text('1')
        self.latest = None
        self.at = 0

    def read(self):
        samples = []
        while select.select([self.fd], [], [], 0)[0]:
            raw = os.read(self.fd, 24 * 128)
            for offset in range(0, len(raw) - 23, 24):
                x, y, z, ticks = struct.unpack_from('<iii4xQ', raw, offset)
                self.latest = [v * self.scale for v in (x, y, z)]
                self.at = time.monotonic()
                samples.append(self.latest)
        return samples

    def close(self):
        (self.path / 'buffer/enable').write_text('0')
        os.close(self.fd)


class Track:
    """CSV is the durable primary log; GPX always has closing XML tags."""
    FOOT = '</trkseg></trk></gpx>\n'

    def __init__(self):
        self.csv = self.gpx = self.gnss = None
        self.points = 0
        self.last_utc = 0
        self.last_sync = 0
        self.basename = ''
        self.last_gnss_log = -100
        self.last_gnss_sync = 0

    def start(self):
        TRACKS.mkdir(parents=True, exist_ok=True)
        self.basename = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        # Do not replace an existing trip even if the host clock moved back.
        self.basename += '-%d' % time.monotonic_ns()
        self.csv = open(TRACKS / (self.basename + '.csv'), 'x', newline='')
        self.writer = csv.writer(self.csv)
        self.writer.writerow(['utc', 'latitude', 'longitude', 'accuracy_m', 'speed_ms', 'altitude_m',
                              'observed_systems', 'signal_systems', 'used_ids', 'used_systems',
                              'used_systems_complete', 'sv_report_available'])
        self.gpx = open(TRACKS / (self.basename + '.gpx'), 'x+')
        self.gpx.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                       '<gpx version="1.1" creator="Mi4 OBD" xmlns="http://www.topografix.com/GPX/1/1" '
                       'xmlns:mi4="urn:mi4-obd:gnss:2">'
                       '<trk><name>Mi4 GPS</name><trkseg>\n' + self.FOOT)
        self.points, self.last_utc = 0, 0
        self.csv.flush()
        self.gpx.flush()
        self.gnss = open(TRACKS / (self.basename + '.gnss.jsonl'), 'x')
        self.gnss.write(json.dumps(dict(event='header', schema=2,
                              meaning='observed is not used-in-fix; absent reports mean unknown'))+'\n')
        self.gnss.flush()
        self.last_gnss_log = -100

    def log_satellites(self, gps, now):
        if not self.gnss or now-self.last_gnss_log < 1:
            return
        data = satellite_metadata(gps, now)
        data.update(event='satellites', monotonic=now,
                    recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    status=gps.get('status'))
        self.gnss.write(json.dumps(data, allow_nan=False)+'\n')
        self.gnss.flush()
        if now-self.last_gnss_sync > 5:
            os.fsync(self.gnss.fileno())
            self.last_gnss_sync = now
        self.last_gnss_log = now

    def append(self, gps):
        now = time.monotonic()
        # Record even without a fix: failed trips must still have evidence.
        self.log_satellites(gps, now)
        if not self.csv or not gps.get('fix') or gps['utc'] <= self.last_utc:
            return
        stamp = datetime.datetime.fromtimestamp(gps['utc'], datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        metadata = satellite_metadata(gps, now)
        self.writer.writerow([stamp, gps['latitude'], gps['longitude'], gps['accuracy_m'],
                              gps.get('speed_ms', ''), gps.get('altitude_m', ''),
                              json.dumps(metadata['observed_systems']),
                              json.dumps(metadata['signal_systems']),
                              json.dumps(metadata['used_ids']), json.dumps(metadata['used_systems']),
                              metadata['used_systems_complete'], metadata['sv_report_available']])
        self.gpx.seek(0, 2)
        self.gpx.seek(self.gpx.tell() - len(self.FOOT))
        point = '<trkpt lat="%.8f" lon="%.8f">' % (gps['latitude'], gps['longitude'])
        if 'altitude_m' in gps:
            point += '<ele>%.2f</ele>' % gps['altitude_m']
        summary = {k: metadata[k] for k in ('observed_systems', 'signal_systems', 'used_ids',
                   'used_systems', 'used_systems_complete', 'sv_report_available')}
        self.gpx.write(point + '<time>' + stamp + '</time><extensions><mi4:satellites>' +
                       escape(json.dumps(summary)) + '</mi4:satellites></extensions></trkpt>\n' + self.FOOT)
        self.gpx.truncate()
        self.csv.flush()
        self.gpx.flush()
        self.points += 1
        self.last_utc = gps['utc']
        if time.monotonic() - self.last_sync > 5:
            os.fsync(self.csv.fileno())
            os.fsync(self.gpx.fileno())
            self.last_sync = time.monotonic()

    def stop(self):
        for stream in (self.csv, self.gpx, self.gnss):
            if stream:
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
        self.csv = self.gpx = self.gnss = None


def main():
    from mi4_gnss import Gnss
    os.umask(0o027)
    accel = Sensor('qcom-smgr-accel', 'accel')
    gps = Gnss()
    track = Track()
    auto = AutoCenter()
    last_batch_at = -100.
    record_blocked = False
    peaks = [0.0] * 4  # front, rear, left, right in dashboard axes
    peak_token = None
    envelope = PersistentEnvelope()  # Retain angular peaks until explicit reset.
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    published = 0
    STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        while running:
            recent = accel.read()
            now = time.monotonic()
            if recent:
                if now-last_batch_at > 1:
                    auto.reset()  # Avoid a false impulse after sensor interruption.
                last_batch_at = now
            # Process at the configured 50 Hz, including buffered sample batches.
            for index,sample in enumerate(recent):
                x,y,_z = auto.update(sample, dt=.02)
                peaks = directional_peaks(peaks, x, y)
                envelope.add(x,y,now-(len(recent)-1-index)*.02)
            now = time.monotonic()
            if now - published >= .1:
                try:
                    control = json.loads(CONTROL.read_text())
                    if not isinstance(control, dict):
                        control = {}
                except (OSError, ValueError):
                    control = {}
                if control.get('reset_peaks') != peak_token:
                    peak_token = control.get('reset_peaks')
                    peaks = [0.0] * 4
                    envelope.clear()
                # No explicit zero command or stationary warm-up is needed.
                imu = auto_center_state(accel.latest, accel.at, now, auto)
                if imu['ready']:
                    imu.update(peaks_g=peaks,
                               envelope_g=envelope.points(now), envelope_window_s=None,
                               envelope_retention='until_peak_reset')
                gps_state = dict(gps.state)
                if now - gps_state.get('fix_at', -100) > 3:
                    gps_state['fix'] = False
                if not control.get('record', False):
                    record_blocked = False
                if control.get('record', False) and not track.csv and not record_blocked:
                    # Bounded storage; never delete existing trips automatically.
                    total = sum(p.stat().st_size for p in TRACKS.glob('*') if p.is_file())
                    if total < 256 * 1024 * 1024:
                        track.start()
                    else:
                        record_blocked = True
                if not control.get('record', False) and track.csv:
                    track.stop()
                if track.csv and track.csv.tell() + track.gpx.tell() + track.gnss.tell() > 64 * 1024 * 1024:
                    # A single trip cannot grow forever. Retain prior files.
                    track.stop()
                    record_blocked = True
                track.append(gps_state)
                atomic_json(STATE, dict(updated=now, imu=imu, gps=gps_state,
                                       recording=bool(track.csv), points=track.points,
                                       track=track.basename, storage_full=record_blocked))
                published = now
            time.sleep(.01)
    finally:
        track.stop()
        accel.close()


if __name__ == '__main__':
    main()

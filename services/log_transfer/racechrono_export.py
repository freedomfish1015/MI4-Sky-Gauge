"""Read-only mi4.telemetry/1 -> RaceChrono CSV v3-compatible export.

No interpolation, inferred lap numbers, fake GPS fixes or guessed pedal values.
Only bounded newline-complete source snapshots are consumed. No source writes.
"""
import csv
from datetime import datetime, timezone
import io
import json
import math
import os
import tempfile
import time

MAX_SOURCE = 128 * 1024 * 1024
MAX_OUTPUT = 128 * 1024 * 1024
MAX_LINE = 256 * 1024
EXPORT_NAME_SUFFIX = '.racechrono.csv'

# The first speed column is GPS; the second is OBD, in m/s as in RaceChrono.
# x/y/z_acc are raw sensor axes; acceleration_1/2 are the filtered display axes.
# They are deliberately NOT labelled vehicle lateral/longitudinal acceleration.
COLUMNS = (
    ('timestamp', 'unix time', ''), ('fragment_id', '', ''), ('elapsed_time', 's', ''),
    ('accuracy', 'm', '100: gps'), ('latitude', 'deg', '100: gps'),
    ('longitude', 'deg', '100: gps'), ('speed', 'm/s', '100: gps'),
    ('speed', 'm/s', '300: obd'), ('rpm', 'rpm', '300: obd'),
    ('throttle_pos', '%', '300: obd'), ('gear', '', '300: obd'),
    ('coolant_temp', '.C', '300: obd'), ('engine_oil_temp', '.C', '300: obd'),
    ('battery_voltage', 'V', '300: obd'), ('engine_load', '%', '300: obd'),
    ('x_acc', 'G', '200: acc'), ('y_acc', 'G', '200: acc'), ('z_acc', 'G', '200: acc'),
    ('acceleration_1', 'G', '201: data'), ('acceleration_2', 'G', '201: data'),
    ('digital_1', '', '201: data'),
)


def finite(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) else None


def mapping(value):
    return value if isinstance(value, dict) else {}


def epoch(value):
    if not isinstance(value, str): return None
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None: return None
        result = date.timestamp()
        return result if 946684800 <= result < 4102444800 else None
    except (ValueError, OverflowError):
        return None


def records(fd, size):
    """Never read past fstat size; partial/oversized final lines cannot escape."""
    offset, buffer = 0, b''
    while offset < size:
        chunk = os.pread(fd, min(65536, size - offset), offset)
        if not chunk: break
        offset += len(chunk)
        buffer += chunk
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            if len(line) > MAX_LINE: raise ValueError('Source record exceeds safe limit')
            try: value = json.loads(line)
            except (ValueError, UnicodeError): continue
            if isinstance(value, dict): yield value
        if len(buffer) > MAX_LINE: raise ValueError('Source record exceeds safe limit')


def header(fd, size):
    for record in records(fd, min(size, MAX_LINE)):
        if record.get('type') == 'header': return record
        break
    return {}


def csv_value(value):
    if value is None: return ''
    if type(value) is int: return str(value)
    return ('%.7f' % value).rstrip('0').rstrip('.') if value != 0 else '0'


def convert(fd, size, name, deadline_seconds=30):
    """Return an anonymous, seekable temp file, byte size and conversion stats."""
    if not 0 <= size <= MAX_SOURCE: raise ValueError('Source exceeds safe limit')
    meta = header(fd, size)
    if meta.get('schema') != 'mi4.telemetry/1': raise ValueError('Unsupported source schema')
    samples = records(fd, size)
    output = tempfile.TemporaryFile(mode='w+b')  # Disk-backed, not a giant RAM CSV.
    began = time.monotonic()
    scratch = io.StringIO(newline='')
    writer = csv.writer(scratch, lineterminator='\n')
    def write(row):
        scratch.seek(0); scratch.truncate(0); writer.writerow(row)
        data = scratch.getvalue().encode('utf-8')
        if output.tell() + len(data) > MAX_OUTPUT: raise ValueError('Export exceeds safe limit')
        output.write(data)
    count, skipped, simulations, fragment = 0, 0, 0, 0
    origin, prev_t, prev_utc = None, None, None
    try:
        for record in samples:
            if time.monotonic() - began > deadline_seconds: raise ValueError('Export time limit exceeded')
            if record.get('type') != 'sample': continue
            utc, mono = epoch(record.get('utc')), finite(record.get('t'))
            if utc is None or mono is None:
                skipped += 1; continue
            if count == 0:
                date = datetime.fromtimestamp(utc, timezone.utc)
                write(['This file is created using mi4-sky (RaceChrono CSV v3 compatible).'])
                write(['Format', 3])
                write(['Session title', 'mi4-sky ' + name.removesuffix('.jsonl')])
                write(['Session type', 'Data logging'])
                write(['Track name', ''])
                write(['Driver name', ''])
                write(['Created', date.strftime('%d/%m/%Y'), date.strftime('%H:%M')])
                write(['Note', 'UTC; 10 Hz source snapshots, not unique ECU updates; missing data blank; '
                    'no lap timing; raw accelerometer axes include gravity as recorded; '
                    'acceleration_1/2 = filtered display X/Y G, not vehicle-calibrated; '
                    'digital_1 = 1 bench simulator, 0 source not marked simulated'])
                write([])
                write([c[0] for c in COLUMNS]); write([c[1] for c in COLUMNS]); write([c[2] for c in COLUMNS])
                origin = mono
            elif mono <= prev_t or utc < prev_utc:
                fragment += 1
                origin = mono  # Preserve real UTC, do not fabricate a corrected clock.
            channels = mapping(record.get('channels'))
            signals = mapping(record.get('signals'))
            gps = mapping(record.get('gps'))
            acceleration = mapping(record.get('acceleration'))
            context = mapping(record.get('context'))
            fixed = gps.get('fix') is True
            lat, lon = finite(gps.get('latitude')), finite(gps.get('longitude'))
            fixed = fixed and lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180
            vector = acceleration.get('accel_g')
            vector = vector if isinstance(vector, (list, tuple)) and len(vector) == 3 else [None] * 3
            sim = 1 if context.get('simulated_source') is True else 0
            simulations += sim
            speed = finite(signals.get('obd.speed'))
            row = [utc, fragment, mono - origin,
                finite(gps.get('accuracy_m')) if fixed else None, lat if fixed else None,
                lon if fixed else None, finite(gps.get('speed_ms')) if fixed else None,
                speed / 3.6 if speed is not None else None, finite(signals.get('obd.rpm')),
                finite(signals.get('obd.throttle')), finite(signals.get('obd.gear')),
                finite(signals.get('obd.coolant_temp')), finite(signals.get('obd.oil_temp')),
                finite(signals.get('obd.battery_voltage')), finite(signals.get('obd.load')),
                *[finite(v) for v in vector], finite(channels.get('gx')), finite(channels.get('gy')), sim]
            write([csv_value(v) for v in row])
            count += 1
            prev_t, prev_utc = mono, utc
        if not count: raise ValueError('No complete timestamped samples available')
        size_out = output.tell()
        output.seek(0)
        return output, size_out, dict(samples=count, skipped=skipped, simulated=simulations, fragments=fragment + 1)
    except BaseException:
        output.close()
        raise

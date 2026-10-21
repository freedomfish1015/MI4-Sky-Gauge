import csv
import hashlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from racechrono_export import COLUMNS, convert, records
import test_log_download as export_tests


def sample(offset=0):
    return dict(type='sample', utc='2026-10-21T01:00:%02d.000+00:00' % offset, t=100.0 + offset,
        channels=dict(gx=.2, gy=-.3, rpm=9999, speed=999),
        signals={'obd.speed': 36, 'obd.rpm': 2000, 'obd.coolant_temp': 90, 'obd.throttle': 15},
        gps=dict(fix=True, latitude=31.123, longitude=121.456, accuracy_m=5, speed_ms=9),
        acceleration=dict(accel_g=[.1, .2, .98]), context=dict(simulated_source=True))


def payload(samples, trip=None):
    rows = [dict(type='header', schema='mi4.telemetry/1', trip=trip)] + samples
    return ''.join(json.dumps(row, allow_nan=True) + '\n' for row in rows).encode()


class ConverterTests(unittest.TestCase):
    def export(self, samples, suffix=b''):
        with tempfile.TemporaryFile() as source:
            data = payload(samples) + suffix
            source.write(data); source.flush()
            exported, size, stats = convert(source.fileno(), len(data), 'telemetry-example.jsonl')
            with exported: result = exported.read()
            self.assertEqual(hashlib.sha256(os.pread(source.fileno(), len(data), 0)).digest(), hashlib.sha256(data).digest())
        self.assertEqual(size, len(result))
        lines = list(csv.reader(io.StringIO(result.decode())))
        start = next(i for i, row in enumerate(lines) if row and row[0] == 'timestamp')
        return lines, start, stats

    def test_v3_structure_units_sources_and_native_time(self):
        lines, index, stats = self.export([sample(), sample(1)])
        self.assertEqual(lines[1], ['Format', '3'])
        self.assertEqual(index, 9)
        self.assertEqual(lines[index], [c[0] for c in COLUMNS])
        self.assertEqual(lines[index+1], [c[1] for c in COLUMNS])
        self.assertEqual(lines[index+2], [c[2] for c in COLUMNS])
        self.assertEqual(stats['samples'], 2)
        self.assertEqual(float(lines[index+3][0]), 1792544400)
        self.assertEqual(float(lines[index+4][2]), 1)
        for line in lines[index:]: self.assertEqual(len(line), len(COLUMNS))

    def test_speed_conversion_sources_and_no_dashboard_defaults(self):
        lines, index, _ = self.export([sample()])
        values = lines[index+3]
        self.assertEqual(values[6], '9')
        self.assertEqual(values[7], '10')
        self.assertEqual(values[8], '2000')
        value = sample(); value['signals'] = {}
        rows, start, _ = self.export([value])
        self.assertEqual(rows[start+3][7:15], ['']*8)

    def test_missing_invalid_or_unfixed_gps_stays_blank(self):
        for gps in ({'fix': False, 'latitude': 31, 'longitude': 121},
                    {'fix': True, 'latitude': 100, 'longitude': 121},
                    {'fix': True, 'latitude': float('nan'), 'longitude': 121}):
            value = sample(); value['gps'] = gps
            rows, start, _ = self.export([value])
            self.assertEqual(rows[start+3][3:7], ['']*4)

    def test_nonfinite_values_are_not_output_as_nan(self):
        value = sample(); value['signals']['obd.rpm'] = float('inf')
        value['channels']['gx'] = float('nan')
        rows, start, _ = self.export([value])
        self.assertEqual(rows[start+3][8], '')
        self.assertEqual(rows[start+3][18], '')

    def test_no_fake_laps_or_vehicle_calibrated_g(self):
        rows, start, _ = self.export([sample()])
        self.assertNotIn('lap_number', rows[start])
        self.assertNotIn('lateral_acc', rows[start])
        self.assertNotIn('longitudinal_acc', rows[start])
        self.assertEqual(rows[start+3][15:18], ['0.1', '0.2', '0.98'])
        self.assertEqual(rows[start+3][18:20], ['0.2', '-0.3'])

    def test_simulated_source_marked_per_row(self):
        second = sample(1); second['context'] = {}
        rows, start, stats = self.export([sample(), second])
        self.assertEqual(rows[start+3][-1], '1')
        self.assertEqual(rows[start+4][-1], '0')
        self.assertEqual(stats['simulated'], 1)

    def test_partial_last_line_ignored(self):
        rows, start, stats = self.export([sample()], b'{"type":"sample"')
        self.assertEqual(stats['samples'], 1)
        self.assertEqual(len(rows[start+3:]), 1)

    def test_real_clock_rollback_starts_new_fragment(self):
        second = sample(1); second['t'] = 99
        rows, start, stats = self.export([sample(), second])
        self.assertEqual(rows[start+4][1:3], ['1', '0'])
        self.assertEqual(stats['fragments'], 2)

    def test_invalid_date_skipped_and_no_unknown_schema(self):
        value = sample(); value['utc'] = 'bad'
        _, _, stats = self.export([value, sample(1)])
        self.assertEqual(stats['skipped'], 1)
        with tempfile.TemporaryFile() as source:
            source.write(b'{}\n'); source.flush()
            with self.assertRaises(ValueError): convert(source.fileno(), 3, 'telemetry-empty.jsonl')

    def test_oversized_record_is_rejected(self):
        with tempfile.TemporaryFile() as source:
            source.write(b'x' * 300000); source.flush()
            with self.assertRaises(ValueError): list(records(source.fileno(), 300000))


class RaceChronoHTTPTests(unittest.TestCase):
    tearDown = export_tests.ExportTests.tearDown
    request = export_tests.ExportTests.request

    def setUp(self):
        export_tests.ExportTests.setUp(self)
        (self.root / 'log' / self.name).write_bytes(payload([sample(), sample(1)], trip='test-trip'))
        self.export_name = self.name[:-6] + '.racechrono.csv'
        self.url = '/s/safe-test-token/file/racechrono/' + self.export_name

    def test_virtual_export_list_and_csv_download(self):
        status, _, data = self.request('/s/safe-test-token/api/files')
        exported = next(row for row in json.loads(data)['files'] if row['kind'] == 'racechrono')
        self.assertEqual(exported['name'], self.export_name)
        self.assertTrue(exported['generated'])
        self.assertEqual(status, 200)
        status, headers, data = self.request(self.url)
        self.assertEqual(status, 200)
        self.assertIn(b'Format,3\n', data)
        self.assertIn(self.export_name, headers['Content-Disposition'])
        self.assertEqual(headers['X-Mi4-Sky-Format'], 'racechrono-csv-v3')

    def test_export_range_and_head(self):
        status, _, data = self.request(self.url, {'Range':'bytes=0-8'})
        self.assertEqual(status, 206); self.assertEqual(data, b'This file')
        status, headers, data = self.request(self.url, method='HEAD')
        self.assertEqual(status, 200); self.assertEqual(data, b'')
        self.assertGreater(int(headers['Content-Length']), 500)

    def test_active_trip_rejected_and_marked(self):
        with patch('log_download.active_trip', return_value='test-trip'):
            self.assertEqual(self.request(self.url)[0], 409)
            rows = self.catalog.files()
            self.assertTrue(next(row for row in rows if row['kind'] == 'racechrono')['recording'])

    def test_export_filename_whitelist(self):
        self.assertEqual(self.request('/s/safe-test-token/file/racechrono/boot.img')[0], 404)
        self.assertEqual(self.request('/s/safe-test-token/file/racechrono/telemetry-%2e%2e%2fsecret.racechrono.csv')[0], 404)

    def test_one_conversion_at_a_time(self):
        with patch('log_download.EXPORT_SLOTS.acquire', return_value=False):
            self.assertEqual(self.request(self.url)[0], 429)


if __name__ == '__main__':
    unittest.main()

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import mi4_motiond
from mi4_satellite_log import satellite_metadata


def gps_state():
    return dict(fix=True, fix_at=100, utc=1760000000, latitude=30., longitude=120.,
                accuracy_m=5, satellite_report_at=100,
                satellite_details=[dict(system='gps', id=1, snr_dbhz=30),
                                   dict(system='compass', id=201, snr_dbhz=35),
                                   dict(system='compass', id=202, snr_dbhz=0)],
                used_satellites=dict(at=100, reported=True, ids=[1, 201]),
                satellite_nmea=[dict(at=100, sentence='$BDGSV,example')])


class SatelliteLogTests(unittest.TestCase):
    def test_observed_and_used_are_separate(self):
        meta = satellite_metadata(gps_state(), 101)
        self.assertEqual(meta['observed_systems'], dict(gps=1, beidou=2))
        self.assertEqual(meta['signal_systems'], dict(gps=1, beidou=1))
        self.assertEqual(meta['used_systems'], dict(gps=1, beidou=1))
        self.assertTrue(meta['used_systems_complete'])

    def test_missing_sv_does_not_infer_gps_from_ids(self):
        state = gps_state()
        state.pop('satellite_report_at')
        meta = satellite_metadata(state, 101)
        self.assertFalse(meta['sv_report_available'])
        self.assertEqual(meta['used_systems'], {})
        self.assertEqual(meta['unresolved_used_ids'], [1, 201])
        self.assertFalse(meta['used_systems_complete'])

    def test_old_reports_expire(self):
        meta = satellite_metadata(gps_state(), 110)
        self.assertEqual(meta['observed_systems'], {})
        self.assertEqual(meta['used_ids'], [])
        self.assertEqual(meta['nmea'], [])

    def test_no_fix_never_keeps_old_used_claim(self):
        state = gps_state()
        state['fix'] = False
        meta = satellite_metadata(state, 101)
        self.assertEqual(meta['used_ids'], [])
        self.assertFalse(meta['used_ids_available'])

    def test_ambiguous_id_remains_unknown(self):
        state = gps_state()
        state['satellite_details'].append(dict(system='glonass', id=1))
        meta = satellite_metadata(state, 101)
        self.assertIn(1, meta['unresolved_used_ids'])
        self.assertFalse(meta['used_systems_complete'])

    def test_csv_gpx_and_searching_sidecar(self):
        with tempfile.TemporaryDirectory() as root, patch.object(mi4_motiond, 'TRACKS', Path(root)):
            track = mi4_motiond.Track()
            track.start()
            with patch('mi4_motiond.time.monotonic', return_value=101):
                track.append(gps_state())
                track.append(gps_state())
            state = gps_state()
            state.update(fix=False, status='searching')
            with patch('mi4_motiond.time.monotonic', return_value=102):
                track.append(state)
            track.stop()
            with next(Path(root).glob('*.csv')).open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(json.loads(rows[0]['used_systems']), {'gps': 1, 'beidou': 1})
            xml = ET.parse(next(Path(root).glob('*.gpx')))
            ext = xml.find('.//{urn:mi4-obd:gnss:2}satellites')
            self.assertEqual(json.loads(ext.text)['used_ids'], [1, 201])
            log = [json.loads(s) for s in next(Path(root).glob('*.jsonl')).read_text().splitlines()]
            self.assertEqual(len(log), 3)  # header + one per second, duplicate ignored
            self.assertFalse(log[-1]['fix'])
            self.assertEqual(log[-1]['status'], 'searching')
            self.assertTrue(log[-1]['sv_report_available'])


if __name__ == '__main__':
    unittest.main()

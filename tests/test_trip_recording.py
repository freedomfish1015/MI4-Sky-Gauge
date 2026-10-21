import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from gauge_telemetry import Telemetry
from gauge_settings import Config, TouchSettings


class TripTests(unittest.TestCase):
    def test_trip_rotates_independent_log_and_stops_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Telemetry(tmp)
            log.sample(1, {'rpm': 1000}, {}, {'recording': False})
            motion = dict(recording=True, track='test-trip', gps=dict(
                fix=True, latitude=30, longitude=120, utc=123, accuracy_m=5))
            log.sample(2, {'rpm': 2000}, {}, motion)
            self.assertTrue(log.recording)
            log.sample(3, {}, {}, {})  # state temporarily unavailable
            self.assertTrue(log.recording)
            log.sample(4, {}, {}, dict(recording=False))
            self.assertFalse(log.recording)
            log.close()
            files = [list(map(json.loads, p.read_text().splitlines()))
                     for p in Path(tmp).glob('*.jsonl')]
            self.assertEqual(len(files), 2)
            trip = next(rows for rows in files if rows[0]['trip'])
            self.assertEqual(trip[0]['gps_track'], 'test-trip.csv')
            self.assertEqual(len(trip), 3)
            self.assertEqual(trip[1]['gps']['latitude'], 30)
            self.assertFalse(trip[2]['gps']['fix'])
            self.assertIsNone(trip[2]['gps']['latitude'])

    def test_each_trip_separate_and_no_fix_has_no_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Telemetry(tmp)
            for n, name in enumerate(('one', 'two')):
                log.sample(2*n+1, {}, {}, dict(recording=True, track=name,
                    gps=dict(fix=False, latitude=30, longitude=120)))
                log.sample(2*n+2, {}, {}, dict(recording=False))
            log.close()
            files = [list(map(json.loads, p.read_text().splitlines()))
                     for p in Path(tmp).glob('*.jsonl')]
            self.assertEqual(len(files), 2)
            self.assertEqual({rows[0]['trip'] for rows in files}, {'one','two'})
            self.assertTrue(all(rows[1]['gps']['latitude'] is None for rows in files))

    def test_log_stop_button_stops_gps_when_linked(self):
        with tempfile.TemporaryDirectory() as tmp:
            controls = TouchSettings(Config(tmp), Mock(), brightness=Mock(read=lambda:50))
            controls.page = 'telemetry'
            controls.motion = Mock(read=lambda:dict(recording=True))
            controls.telemetry = Mock(trip='trip')
            controls.input('down', 550, 22, 1)
            controls.input('up', 550, 22, 1.1)
            controls.motion.command.assert_called_once_with(record=False)
            controls.telemetry.set_recording.assert_not_called()

    def test_log_transfer_settings_do_not_start_gps_but_route_button_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            controls = TouchSettings(Config(tmp), Mock(), brightness=Mock(read=lambda:50))
            controls.motion = Mock(read=lambda:dict(recording=False))
            controls.log_transfer = Mock()
            controls.tab = 4
            controls.tap(400, 270)
            controls.motion.command.assert_not_called()
            controls.log_transfer.tap.assert_called_once_with(400,270)
            controls.page = 'route'
            controls.input('down', 550, 22, 1)
            controls.input('up', 550, 22, 1.1)
            controls.motion.command.assert_called_once_with(record=True)

    def test_resume_existing_trip_after_app_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Telemetry(tmp)
            log.sample(1, {}, {}, dict(recording=True, track='ongoing'))
            self.assertEqual(log.trip, 'ongoing')
            log.close()
            rows = [json.loads(s) for p in Path(tmp).glob('*.jsonl') for s in p.read_text().splitlines()]
            self.assertEqual(rows[0]['trip'], 'ongoing')


if __name__ == '__main__':
    unittest.main()

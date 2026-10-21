import json
import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import gauge_motion
import mi4_motiond
import mi4_gnss


class MotionTests(unittest.TestCase):
    def test_raw_acceleration_uses_first_sample_and_keeps_gravity(self):
        state = mi4_motiond.acceleration_state([0,0,mi4_motiond.G],100,100.01)
        self.assertTrue(state['ready'])
        self.assertFalse(state['calibration_required'])
        self.assertFalse(state['calibrated'])
        self.assertEqual(state['accel_g'],[0,0,1])
        self.assertEqual(state['total_g'],1)
        self.assertNotIn('linear_g',state)
        moving = mi4_motiond.acceleration_state([mi4_motiond.G,2*mi4_motiond.G,0],100,100.01)
        self.assertEqual(moving['display_g'],[1,2])
        self.assertFalse(mi4_motiond.acceleration_state([0,0,1],100,102)['ready'])
        self.assertFalse(mi4_motiond.acceleration_state([math.nan,0,1],100,100.01)['ready'])

    def test_raw_visual_output_has_no_calibration_or_interpolation(self):
        client = gauge_motion.MotionClient()
        client.visual_point = [0,0]
        state = {'imu': mi4_motiond.acceleration_state([mi4_motiond.G,0,0],100,100.01)}
        self.assertTrue(gauge_motion.acceleration_available(state['imu']))
        client.smooth(state)
        self.assertEqual(state['_visual_point'],[1,0])

    def test_visual_smoothing_approaches_target_without_changing_peak_data(self):
        client = gauge_motion.MotionClient()
        client.visual_at = 100
        client.visual_point = [0,0]
        state = {'imu':dict(ready=True,calibrated=True,display_g=[1,0],peaks_g=[0,0,0,1])}
        with patch('gauge_motion.time.monotonic',return_value=100.05):
            client.smooth(state)
        first = state['_visual_point'][0]
        with patch('gauge_motion.time.monotonic',return_value=100.10):
            client.smooth(state)
        self.assertTrue(0 < first < state['_visual_point'][0] < 1)
        self.assertEqual(state['imu']['peaks_g'],[0,0,0,1])

    def test_display_range_is_two_point_two_without_changing_raw_peaks(self):
        self.assertEqual(gauge_motion.display_vector(2.2,0),(1,0))
        self.assertEqual(gauge_motion.display_vector(1.1,0),(.5,0))
        self.assertEqual(gauge_motion.display_vector(5,0),(1,0))
        self.assertEqual(mi4_motiond.directional_peaks([0]*4,3.5,0)[3],3.5)

    def test_envelope_includes_diagonal_extrema_not_just_axis_peaks(self):
        bins = [None]*72
        for p in [(0,0),(.4,.4),(.3,.3),(-.5,.2),(.1,-.6)]:
            mi4_motiond.accumulate_envelope(bins,*p)
        points = [p for p in bins if p is not None]
        self.assertIn((.4,.4),points)
        self.assertNotIn((.3,.3),points)
        self.assertIn((.4,.4),gauge_motion.convex_hull(points))

    def test_four_directional_peaks_keep_extrema_until_reset(self):
        peaks = [0.0]*4
        for x,y in [(.2,-.4),(-.7,.3),(.1,-.1)]:
            peaks = mi4_motiond.directional_peaks(peaks,x,y)
        self.assertEqual(peaks, [.4,.3,.7,.2])

    def test_both_bars_are_bottom_to_top_on_opposite_sides(self):
        import gauge_sdl as gauge
        app = gauge.Gauge(gauge.DemoSource(), headless=True)
        for angle, maximum, side in [(app.angle_for,gauge.RPM_MAX,1),
                                     (app.speed_angle,gauge.SPEED_MAX,-1)]:
            points = [app.hex_point(*gauge.RPM_CENTER[:2],app.arc_radius(),angle(v))
                      for v in (0,maximum*.5,maximum)]
            self.assertTrue(all((x-320)*side > 0 for x,y in points))
            self.assertGreater(points[0][1],points[1][1])
            self.assertGreater(points[1][1],points[2][1])

    def test_stale_state_never_becomes_a_live_reading(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / 'state.json'
            state.write_text(json.dumps(dict(updated=time.monotonic()-10, imu={'ready': True})))
            with patch.object(gauge_motion, 'STATE', state):
                self.assertEqual(gauge_motion.MotionClient().read(), {})

    def test_trail_expires_after_five_seconds(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)/'state.json'
            with patch.object(gauge_motion,'STATE',state):
                client = gauge_motion.MotionClient()
                for stamp in (100,102,108):
                    state.write_text(json.dumps(dict(updated=stamp,imu=dict(
                        ready=True,calibrated=True,display_g=[.1,.2]))))
                    with patch('gauge_motion.time.monotonic',return_value=stamp):
                        client.read()
                self.assertEqual(len(client.history),1)
                self.assertEqual(client.history[0][0],108)

    def test_control_merge_preserves_recording_when_zeroing(self):
        with tempfile.TemporaryDirectory() as root, patch.object(gauge_motion, 'CONTROL', Path(root)/'control.json'):
            client = gauge_motion.MotionClient()
            client.command(record=True)
            client.command(zero=123)
            self.assertEqual(json.loads(gauge_motion.CONTROL.read_text()), dict(record=True, zero=123))

    def test_track_rejects_no_fix_and_duplicate_points_and_writes_valid_gpx(self):
        with tempfile.TemporaryDirectory() as root, patch.object(mi4_motiond, 'TRACKS', Path(root)):
            track = mi4_motiond.Track()
            track.start()
            track.append({'fix': False})
            self.assertEqual(track.points, 0)
            good = dict(fix=True, utc=1760000000, latitude=30.0, longitude=120.0, accuracy_m=5)
            track.append(good)
            track.append(good)
            self.assertEqual(track.points, 1)
            ET.parse(next(Path(root).glob('*.gpx')))
            track.stop()
            self.assertEqual(len(next(Path(root).glob('*.csv')).read_text().splitlines()), 2)

    def test_g_meter_incremental_pixels_match_static_telemetry(self):
        import gauge_sdl as gauge
        app = gauge.Gauge(gauge.DemoSource(), headless=True)
        state = {'imu': {'ready': True, 'calibrated': True, 'total_g': .2, 'display_g': [.1, -.17]},
                 'gps': {'fix': False, 'status': 'searching'}, 'updated': time.monotonic()}
        app.motion.state, app.motion.last = state, time.monotonic()
        # On armhf a full native frame can exceed the client's 100 ms refresh
        # period. Keep this pixel fixture isolated from the REAL device state.
        read_patch = patch.object(app.motion,'read',return_value=state)
        read_patch.start()
        self.addCleanup(read_patch.stop)
        values = dict(rpm=2800, speed=48, coolant=90, oil=80, battery=13.8)
        app.draw_frame(values, full=True, upload=False)
        state['imu'].update(total_g=.31, display_g=[-.2, .24])
        app.motion.visual_point = [-.2,.24]
        app.draw_frame(values, upload=False)
        actual = bytes(app.surface.get_data())
        app.draw_frame(values, full=True, upload=False)
        expected = bytes(app.surface.get_data())
        # Tiny Cairo clip-edge coverage differences are allowed, not missing pixels.
        self.assertLess(sum(abs(a-b)>5 for a,b in zip(actual, expected)), 40)


if __name__ == '__main__':
    unittest.main()

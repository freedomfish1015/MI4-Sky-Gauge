import math
import time
import unittest
from unittest.mock import patch
from gauge_motion import directional_contour, rounded_contour_segments
from mi4_motiond import RollingEnvelope, PersistentEnvelope


class DirectionalEnvelopeTests(unittest.TestCase):
    def test_rounding_is_local_and_does_not_change_measured_points(self):
        original=[(0.,0.),(100.,0.),(20.,20.),(100.,100.),(0.,100.)]
        points=list(original)
        segments=rounded_contour_segments(points)
        self.assertEqual(points,original)
        self.assertEqual([p for _entry,p,_exit in segments],original)
        for i,(entry,p,exit) in enumerate(segments):
            self.assertLessEqual(math.dist(entry,p),6.00001)
            self.assertLessEqual(math.dist(exit,p),6.00001)
            neighbors=(original[i-1],p,original[(i+1)%len(original)])
            for q in (entry,exit):
                for axis in (0,1):
                    self.assertGreaterEqual(q[axis],min(v[axis] for v in neighbors)-1e-9)
                    self.assertLessEqual(q[axis],max(v[axis] for v in neighbors)+1e-9)
        self.assertEqual(rounded_contour_segments([]),[])
        self.assertEqual(rounded_contour_segments([(0,0),(0,0),(1,1)]),[])

    def test_persistent_area_survives_idle_and_zero_readings(self):
        env=PersistentEnvelope()
        env.add(.7,.7,100)
        expected=env.points(101)
        for stamp in (106,160,10000):
            env.add(0,0,stamp)
            self.assertEqual(env.points(stamp),expected)
        env.add(.3,.3,10001)
        self.assertEqual(env.points(10002),expected)
        env.add(.9,.9,10003)
        self.assertEqual(env.points(10004),[(.9,.9)])
        env.clear()
        self.assertEqual(env.points(10005),[])

    def test_radial_valley_not_replaced_by_convex_hull(self):
        valley=(.15/math.sqrt(2),.15/math.sqrt(2))
        contour=directional_contour([(1,0),valley,(0,1)])
        self.assertIn((valley[0]/2.2,valley[1]/2.2),contour)
        self.assertEqual(len(contour),4)  # three measured directions + origin

    def test_sectors_preserve_max_and_all_directions(self):
        points=[(.5,.5),(-.5,.5),(-.5,-.5),(.5,-.5),(.2,.2)]
        contour=directional_contour(points)
        self.assertEqual(sum(bool(x or y) for x,y in contour),4)
        self.assertTrue(all(math.hypot(x,y)<=1 for x,y in directional_contour([(5,5)])))
        self.assertTrue(all(p==(0,0) for p in directional_contour([])))

    def test_rolling_peak_expires_and_reveals_newer_smaller_peak(self):
        env=RollingEnvelope()
        env.add(1,0,100)
        env.add(.5,0,103)
        self.assertEqual(env.points(104),[(1,0)])
        self.assertEqual(env.points(105),[(.5,0)])
        self.assertEqual(env.points(108),[])

    def test_bounded_history_and_clear(self):
        env=RollingEnvelope()
        for i in range(1000):env.add(.2,.3,100+i*.02)
        self.assertLessEqual(len(env.samples),512)
        env.clear()
        self.assertEqual(env.points(120),[])

    def test_incremental_shrink_erases_old_contour(self):
        import gauge_sdl as gauge
        app=gauge.Gauge(gauge.DemoSource(),headless=True)
        imu=dict(ready=True,calibrated=False,measurement_mode='accelerometer_autocenter',
                 display_g=[0,0],total_g=0,envelope_g=[
                    ((.7+.3*math.sin(a*3))*math.cos(a),(.7+.3*math.sin(a*3))*math.sin(a))
                    for a in [i*math.tau/72 for i in range(72)]])
        state=dict(imu=imu,gps={},updated=time.monotonic())
        values=dict(rpm=2800,speed=48,coolant=90,oil=80,battery=13.8)
        with patch.object(app.motion,'read',return_value=state):
            app.draw_frame(values,full=True,upload=False)
            imu['envelope_g']=[(.15,0),(.1,.1),(0,.15)]
            app.draw_frame(values,upload=False)
            actual=bytes(app.surface.get_data())
            app.draw_frame(values,full=True,upload=False)
            expected=bytes(app.surface.get_data())
        self.assertLess(sum(abs(a-b)>5 for a,b in zip(actual,expected)),40)


if __name__=='__main__':unittest.main()

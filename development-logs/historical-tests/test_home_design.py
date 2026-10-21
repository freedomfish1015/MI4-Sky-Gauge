import math
import time
import unittest
from unittest.mock import patch
import gauge_sdl as g
import gauge_home as home


class HomeDesignTests(unittest.TestCase):
    def test_extended_strokes_fit_dirty_boxes(self):
        app=self.app()
        for rail,box in ((home.SPEED_RAIL,app.speed_arc_box(0,0)),
                         (home.RPM_RAIL,app.arc_box(0,0))):
            x,y,w,h=box
            radius=home.RAIL_WIDTH/2+1
            self.assertLessEqual(x,rail-radius)
            self.assertGreaterEqual(x+w,rail+radius)
            self.assertLessEqual(y,home.RAIL_TOP-radius)
            self.assertGreaterEqual(y+h,home.RAIL_BOTTOM+radius)

    def test_thick_speed_rail_stays_blue_at_full_scale_rpm_keeps_redline(self):
        from unittest.mock import MagicMock
        app=self.app()
        speed_cr=MagicMock()
        app.draw_speed_progress(speed_cr,app.speed_angle(0),app.speed_angle(g.SPEED_MAX))
        speed_cr.set_line_width.assert_called_with(16)
        self.assertNotIn(unittest.mock.call(*g.RED),speed_cr.set_source_rgb.call_args_list)
        # Full scale must reach the top, without clipping the blue fill at 180.
        speed_cr.line_to.assert_called_with(home.SPEED_RAIL,home.RAIL_TOP)
        rpm_cr=MagicMock()
        app.draw_progress(rpm_cr,app.angle_for(0),app.angle_for(g.RPM_MAX))
        rpm_cr.set_line_width.assert_called_with(16)
        rpm_cr.set_source_rgb.assert_any_call(*g.RED)

    def test_static_speed_track_has_no_pink_red_zone(self):
        app=self.app()
        cr=g.cairo.Context(app.static)
        app.apply_layout(cr)
        def pixel(x,y):
            x,y=cr.user_to_device(x,y)
            stride=app.static.get_stride()
            b,gc,r,a=bytes(app.static.get_data())[int(y)*stride+int(x)*4:][:4]
            return r,gc,b
        # Upper speed track used to be pink; blue-grey track is now uniform.
        self.assertEqual(pixel(home.SPEED_RAIL,130),pixel(home.SPEED_RAIL,225))
        self.assertNotEqual(pixel(home.RPM_RAIL,130),pixel(home.RPM_RAIL,225))

    def app(self):
        app=g.Gauge(g.DemoSource(),headless=True)
        state=dict(updated=time.monotonic(),imu=dict(ready=True,calibrated=False,
            measurement_mode='accelerometer_autocenter',display_g=[0,0],total_g=0,
            envelope_g=[(.7,0),(.2,.2),(0,.8),(-.4,.1),(0,-1)]),gps={})
        mocked=patch.object(app.motion,'read',return_value=state)
        mocked.start()
        self.addCleanup(mocked.stop)
        return app

    def test_primary_and_four_custom_windows_fit_and_do_not_overlap_g_plot(self):
        app=self.app()
        self.assertEqual(len(app.cards),4)
        for i in range(4):
            x,y,w,h=app.card_value_box(i)
            self.assertTrue(0<=x and x+w<=640 and 0<=y and y+h<=360)
            self.assertTrue(x+w<180 or x>460)
        for box in (app.rpm_value_box(),app.speed_value_box()):
            x,y,w,h=box
            self.assertTrue(x+w<180 or x>460)

    def test_dirty_update_matches_full_including_clamped_and_missing_values(self):
        app=self.app()
        values=dict(rpm=2800,speed=48,coolant=90,oil=80,battery=13.8)
        app.draw_frame(values,full=True,upload=False)
        # A single transition covers decreasing rails, missing speed and card
        # temperature warnings. No obsolete numerals should survive.
        values.update(rpm=7600,speed=math.nan,coolant=110,oil=115,battery=10.8)
        app.draw_frame(values,upload=False)
        actual=bytes(app.surface.get_data())
        app.draw_frame(values,full=True,upload=False)
        expected=bytes(app.surface.get_data())
        self.assertLess(sum(abs(a-b)>5 for a,b in zip(actual,expected)),40)

    def test_zero_to_missing_and_above_scale_still_dirty_primary_digits(self):
        app=self.app()
        values=dict(rpm=0,speed=0,coolant=90,oil=80,battery=13.8)
        app.draw_frame(values,full=True,upload=False)
        values.update(rpm=math.nan,speed=math.nan)
        regions=app.draw_frame(values,upload=False)
        self.assertTrue(any(mask & g.REGION_RPM for _box,mask in regions))
        self.assertTrue(any(mask & g.REGION_SPEED for _box,mask in regions))
        values.update(rpm=8500,speed=250)
        app.draw_frame(values,upload=False)
        values.update(rpm=8600,speed=260)
        regions=app.draw_frame(values,upload=False)
        self.assertTrue(any(mask & g.REGION_RPM for _box,mask in regions))
        self.assertTrue(any(mask & g.REGION_SPEED for _box,mask in regions))


if __name__=='__main__':unittest.main()

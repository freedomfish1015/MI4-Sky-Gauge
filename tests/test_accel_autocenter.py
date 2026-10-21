import math
import unittest
from mi4_accel_autocenter import AutoCenter, G
from mi4_motiond import auto_center_state
from gauge_motion import MotionClient, acceleration_available
from gauge_telemetry import Telemetry


class AutoCenterTests(unittest.TestCase):
    def test_first_sample_is_immediately_centered_at_any_orientation(self):
        for xyz in ([0,0,G], [G,0,0], [2,-3,-8]):
            auto = AutoCenter()
            self.assertEqual(auto.update(xyz), [0,0,0])
            state = auto_center_state(xyz,100,100.01,auto)
            self.assertTrue(state['ready'])
            self.assertFalse(state['calibration_required'])
            self.assertFalse(state['gyro_enabled'])
            self.assertFalse(state['sustained_g_valid'])
            self.assertEqual(state['display_g'],[0,0])
            self.assertTrue(acceleration_available(state))

    def test_impulse_responds_and_constant_offset_recenters(self):
        auto = AutoCenter()
        auto.update([0,0,G])
        first = auto.update([G,0,G])
        self.assertGreater(first[0], .9)
        for _ in range(150):
            result = auto.update([G,0,G])
        self.assertEqual(result, [0,0,0])

    def test_tilt_stops_following_once_held(self):
        auto = AutoCenter()
        auto.update([0,0,G])
        auto.update([G,0,0])
        for _ in range(180):
            result = auto.update([G,0,0])
        self.assertEqual(result,[0,0,0])

    def test_stationary_sensor_noise_does_not_move_dot(self):
        auto = AutoCenter()
        auto.update([0,0,G])
        for n in range(500):
            result=auto.update([.01*G*math.sin(n),.01*G*math.cos(n),G])
            self.assertEqual(result,[0,0,0])

    def test_reset_after_dropout_does_not_make_false_impulse(self):
        auto = AutoCenter()
        auto.update([0,0,G])
        auto.reset()
        self.assertEqual(auto.update([G,0,0]),[0,0,0])
        self.assertFalse(auto_center_state([G,0,0],100,102,auto)['ready'])

    def test_reject_nonfinite_or_invalid_parameters(self):
        for tau,deadzone in ((0,.02),(1,-1),(math.nan,.02)):
            with self.assertRaises(ValueError):
                AutoCenter(tau,deadzone)
        auto=AutoCenter()
        for xyz in ([0,0], [0,math.nan,0]):
            with self.assertRaises(ValueError):
                auto.update(xyz)
        with self.assertRaises(ValueError):
            auto.update([0,0,G],dt=0)

    def test_visual_and_log_use_dynamic_not_raw_gravity(self):
        auto=AutoCenter()
        auto.update([G,0,0])
        imu=auto_center_state([G,0,0],100,100.01,auto)
        state={'imu':imu}
        client=MotionClient()
        client.smooth(state)
        self.assertEqual(state['_visual_point'],[0,0])
        log=Telemetry(enabled=False)
        log.sample(1,{}, {}, state)
        row=log.history[-1]
        self.assertEqual(row['channels']['gx'],0)
        self.assertEqual(row['acceleration']['accel_g'],[1,0,0])
        self.assertEqual(row['acceleration']['dynamic_g'],[0,0,0])


if __name__=='__main__':
    unittest.main()

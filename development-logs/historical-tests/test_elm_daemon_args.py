import sys
import unittest
from unittest.mock import patch, Mock
import elm327_ble_bridge as bridge


class DaemonArgsTests(unittest.TestCase):
    def test_zero_waits_until_explicit_stop(self):
        args = ['bridge','--advertise-only','--sky-address','02:00:00:00:00:02','--seconds','0']
        with patch.object(sys, 'argv', args), patch.object(bridge, 'run', new_callable=Mock) as run, patch('asyncio.run'):
            bridge.main()
        self.assertEqual(run.call_args.args[0].seconds, 0)
        self.assertTrue(run.call_args.args[0].advertise_only)
        self.assertFalse(run.call_args.args[0].simulate)

    def test_negative_is_rejected(self):
        with patch.object(sys, 'argv', ['bridge','--advertise-only','--sky-address','02:00:00:00:00:02','--seconds','-1']):
            with self.assertRaises(SystemExit):
                bridge.main()


if __name__ == '__main__':
    unittest.main()

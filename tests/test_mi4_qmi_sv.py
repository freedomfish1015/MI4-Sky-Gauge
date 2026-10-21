import ctypes
import math
import unittest
from mi4_qmi_sv import Satellite, decode_records


class NativeRecords(unittest.TestCase):
    def record(self, **fields):
        row = Satellite()
        for k, v in fields.items():
            setattr(row, k, v)
        return bytes(row)

    def test_layout(self):
        self.assertEqual(ctypes.sizeof(Satellite), 36)
        self.assertEqual(Satellite.signal_to_noise_ratio_bhz.offset, 32)

    def test_masks_and_unknown_enums(self):
        rows = decode_records(self.record(valid_information=0, system=999)+
                              self.record(valid_information=155, system=4,
                                          gnss_satellite_id=201, satellite_status=2,
                                          signal_to_noise_ratio_bhz=32.5))
        self.assertEqual(rows[0], {'valid_mask': 0})
        self.assertEqual(rows[1]['system'], 'compass')
        self.assertEqual(rows[1]['snr_dbhz'], 32.5)
        self.assertEqual(rows[1]['navigation_data'], 0)
        unknown = decode_records(self.record(valid_information=9, system=999,
                                              satellite_status=999))[0]
        self.assertEqual(unknown['system'], 'unknown-999')

    def test_nonfinite_and_bounds(self):
        row = decode_records(self.record(valid_information=128,
                                          signal_to_noise_ratio_bhz=math.nan))[0]
        self.assertNotIn('snr_dbhz', row)
        self.assertEqual(decode_records(b''), [])
        for data in (b'\0', bytes(36*256)):
            with self.assertRaises(ValueError):
                decode_records(data)


if __name__ == '__main__':
    unittest.main()

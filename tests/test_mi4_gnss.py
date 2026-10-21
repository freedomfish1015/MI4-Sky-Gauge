"""GNSS report decoding tests; no hardware, GLib loop or LOC session."""
import types
import unittest
from unittest.mock import patch
from mi4_gnss import Gnss


class SatelliteReportTests(unittest.TestCase):
    def setUp(self):
        def decode(output):
            # Fake reports test state handling, not the native ABI adapter.
            return [dict(valid_mask=i.valid_information,
                         **({'system': i.system.value_nick,
                             'id': i.gnss_satellite_id} if i.valid_information & 1 else {}))
                    for i in output.get_list()]
        self.reader = patch('mi4_qmi_sv.read_satellites', side_effect=decode)
        self.reader.start()
        self.addCleanup(self.reader.stop)

    def make_gnss(self):
        obj = Gnss.__new__(Gnss)
        obj.state = {}
        return obj

    def report(self, *systems):
        items = [types.SimpleNamespace(system=types.SimpleNamespace(value_nick=s),
                                       valid_information=3, gnss_satellite_id=i+1)
                 for i, s in enumerate(systems)]
        return types.SimpleNamespace(get_list=lambda: items)

    def test_struct_fields_include_compass(self):
        obj = self.make_gnss()
        obj.satellites(None, self.report('gps', 'compass', 'gps', 'glonass'))
        self.assertEqual(obj.state['systems'], {'gps': 2, 'compass': 1, 'glonass': 1})
        self.assertEqual(obj.state['satellites'], 4)
        self.assertIn('satellite_report_at', obj.state)

    def test_empty_report_clears_old_systems(self):
        obj = self.make_gnss()
        obj.satellites(None, self.report('compass'))
        obj.satellites(None, self.report())
        self.assertEqual(obj.state['systems'], {})
        self.assertEqual(obj.state['satellites'], 0)

    def test_report_error_visible_and_cleared_on_recovery(self):
        obj = self.make_gnss()
        obj.satellites(None, object())
        self.assertIn('satellite_report_error', obj.state)
        obj.satellites(None, self.report('gps'))
        self.assertNotIn('satellite_report_error', obj.state)

    def test_nmea_preserves_gsv_and_gsa_but_not_coordinates(self):
        obj = self.make_gnss()
        for line in ('$BDGSV,1,1,01,201,30,120,35*00', '$GPGSA,A,3,01,,,,,,,,,,,,1,1,1*00',
                     '$GPGGA,has-private-position'):
            obj.nmea(None, types.SimpleNamespace(get_nmea_string=lambda: line))
        self.assertEqual(len(obj.state['satellite_nmea']), 2)
        self.assertTrue(all('GGA' not in r['sentence'] for r in obj.state['satellite_nmea']))

    def test_invalid_system_mask_not_counted(self):
        obj = self.make_gnss()
        report = self.report('compass')
        report.get_list()[0].valid_information = 0
        obj.satellites(None, report)
        self.assertEqual(obj.state['systems'], {})


if __name__ == '__main__':
    unittest.main()

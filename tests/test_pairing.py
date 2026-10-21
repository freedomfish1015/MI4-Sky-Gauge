import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import log_hotspot


class PairingTests(unittest.TestCase):
    def test_single_qr_contains_wifi_and_current_session(self):
        data = dict(ssid='mi4-sky', password='123456abcdef')
        session = dict(token='x' * 32, address='192.168.73.1', port=8787)
        result = json.loads(log_hotspot.pairing_payload(data, session))
        self.assertEqual(result, dict(kind='skygauge-log', v=1, ssid='mi4-sky',
            password=data['password'], host='192.168.73.1', port=8787, token='x' * 32))
        self.assertNotIn('sudo', result)

    def test_session_changes_change_qr(self):
        data = dict(ssid='mi4-sky', password='123456abcdef')
        self.assertNotEqual(log_hotspot.pairing_payload(data, dict(token='a' * 32)),
                            log_hotspot.pairing_payload(data, dict(token='b' * 32)))

    def test_existing_password_preserved_without_rewriting_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            original = json.dumps(dict(ssid='SkyGauge-Mi4', password='123456abcdef'))
            path.write_text(original)
            with patch.object(log_hotspot, 'CONFIG', path):
                self.assertEqual(log_hotspot.configuration(), dict(ssid='mi4-sky', password='123456abcdef'))
            self.assertEqual(path.read_text(), original)

    def test_only_one_qr_and_no_captive_portal(self):
        source = Path(log_hotspot.__file__).read_text()
        self.assertIn("qr_image(pairing_payload(data, session), 'pairing.png')", source)
        self.assertNotIn("qr_image('WIFI:", source)
        self.assertNotIn("qr_image(url", source)
        self.assertIn("'port=0'", source)
        self.assertNotIn("'port=53'", source)


if __name__ == '__main__':
    unittest.main()

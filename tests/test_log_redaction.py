import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('redact',Path(__file__).resolve().parents[1]/'tools/redact_logs.py')
redact=importlib.util.module_from_spec(spec);spec.loader.exec_module(redact)

class RedactionTests(unittest.TestCase):
    def test_private_values_and_encoded_envelopes_removed(self):
        data='password="not-public"\n{"token":"not-public-2"}\nhttps://example.invalid/private?k=abc\n02:11:22:33:44:55\n{"latitude":31.234,"longitude":121.234}\nprintf abc | base64 -d | bash\n'
        clean,stats=redact.redact(data)
        for secret in ('not-public','example.invalid','02:11','31.234','base64 -d'):
            self.assertNotIn(secret,clean)
        self.assertTrue(stats)

    def test_diagnostic_measurements_and_public_sources_remain(self):
        data='FPS=58.4 upload=0.1ms\nhttps://github.com/steveEcode/obd_brz_gauge\nSHA256='+('a'*64)+'\n'
        clean,_=redact.redact(data)
        self.assertIn('FPS=58.4',clean);self.assertIn('github.com',clean);self.assertIn('a'*64,clean)

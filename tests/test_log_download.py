import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from log_download import Catalog, DownloadServer, handler, allowed, byte_range, snapshot_size


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'log').mkdir()
        (self.root / 'track').mkdir()
        self.catalog = Catalog({kind: self.root / kind for kind in ('log', 'track')})
        self.name = 'telemetry-20261021T000000Z-test.jsonl'
        (self.root / 'log' / self.name).write_bytes(b'{"a":1}\n{"b":2}\npartial')
        self.session = dict(token='safe-test-token', address='127.0.0.1', port=0, hosts=[])
        self.server = DownloadServer(('127.0.0.1', 0), handler(self.session, self.catalog))
        self.session['hosts'].append('127.0.0.1:%d' % self.server.server_port)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join()
        self.temp.cleanup()

    def request(self, path, headers=None, method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_authenticated_catalog(self):
        status, headers, body = self.request('/s/safe-test-token/api/files')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['files'][0]['name'], self.name)
        self.assertNotIn(str(self.root), body.decode())
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_missing_and_wrong_tokens(self):
        for path in ('/', '/s/wrong/api/files', '/s/%E4%B8%AD/api/files'):
            self.assertEqual(self.request(path)[0], 403)

    def test_download_snapshot_ends_on_newline(self):
        status, headers, body = self.request('/s/safe-test-token/file/log/' + self.name)
        self.assertEqual(status, 200)
        self.assertEqual(body, b'{"a":1}\n{"b":2}\n')
        self.assertIn('attachment', headers['Content-Disposition'])

    def test_range_and_head(self):
        path = '/s/safe-test-token/file/log/' + self.name
        self.assertEqual(self.request(path, {'Range': 'bytes=0-2'})[2], b'{"a')
        self.assertEqual(self.request(path, {'Range': 'bytes=500-'})[0], 416)
        status, headers, body = self.request(path, method='HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'')
        self.assertEqual(int(headers['Content-Length']), 16)

    def test_traversal_and_symlink_rejected(self):
        (self.root / 'secret').write_text('PRIVATE')
        os.symlink(self.root / 'secret', self.root / 'log' / 'telemetry-link.jsonl')
        for name in ('%2e%2e%2fsecret', 'telemetry-link.jsonl', 'other.jsonl'):
            status, _, body = self.request('/s/safe-test-token/file/log/' + name)
            self.assertEqual(status, 404)
            self.assertNotIn(b'PRIVATE', body)

    def test_host_rebinding_rejected(self):
        self.assertEqual(self.request('/s/safe-test-token/', {'Host': 'evil.example'})[0], 403)

    def test_recording_gps_not_exported_mid_write(self):
        name = '20261021T000000Z-123.gpx'
        (self.root / 'track' / name).write_text('<gpx/>')
        with patch('log_download.active_trip', return_value='20261021T000000Z-123'):
            self.assertEqual(self.request('/s/safe-test-token/file/track/' + name)[0], 409)
            rows = self.catalog.files()
            self.assertTrue(next(row for row in rows if row['kind'] == 'track')['recording'])

    def test_webpage_and_script_are_offline(self):
        status, _, body = self.request('/s/safe-test-token/')
        self.assertEqual(status, 200)
        self.assertNotIn(b'https://', body)
        self.assertEqual(self.request('/s/safe-test-token/app.js')[0], 200)

    def test_only_export_extensions(self):
        self.assertFalse(allowed('track', 'boot.img'))
        self.assertFalse(allowed('log', 'telemetry-../secret.jsonl'))
        self.assertTrue(allowed('track', '20261021T000000Z-123.gnss.jsonl'))
        self.assertEqual(byte_range('bytes=-4', 10), (6, 10))


if __name__ == '__main__':
    unittest.main()

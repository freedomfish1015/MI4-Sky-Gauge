import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
import gauge_ble_diagnostics as diag


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tearDown()

    def tearDown(self):
        if diag._logger:
            for handler in diag._logger.handlers:
                handler.close()
        diag._logger=None
        diag._last.clear()

    def test_log_protocol_packets_errors_and_throttle(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,OBD_BLE_LOG_DIR=directory):
                trace=diag.Trace('test-device')
                trace.protocol(NS(kind='elm',rx='rx',tx='tx',response=True))
                for _ in range(100):
                    trace.packet('rx',b'41 0C 00 00\r>')
                try:
                    raise RuntimeError('test failure')
                except RuntimeError as exc:
                    diag.error('test_error',exc)
            rows=[json.loads(line) for line in (Path(directory)/'bluetooth.jsonl').read_text().splitlines()]
            self.assertEqual(rows[1]['protocol'],'elm')
            self.assertEqual(len([r for r in rows if r['event']=='packet']),61)
            self.assertIn('RuntimeError',rows[-1]['traceback'])
            self.assertIn('time_utc',rows[0])

    def test_rotation_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,OBD_BLE_LOG_DIR=directory):
                diag.event('start')
                diag._logger.handlers[0].maxBytes=200
                for i in range(20):
                    diag.event('large',text='x'*100,index=i)
                self.assertLessEqual(len(list(Path(directory).glob('bluetooth.jsonl*'))),5)

    def test_io_failure_is_nonfatal(self):
        with patch.object(diag.Path,'mkdir',side_effect=OSError('read-only')):
            diag.event('failure')
        self.assertIsNone(diag._logger)


if __name__=='__main__':
    unittest.main()

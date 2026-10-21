import ast
from pathlib import Path
import time
import types
import unittest
from unittest.mock import Mock, patch
from gauge_log_transfer import TransferClient

SOURCE = (Path(__file__).resolve().parents[1]/'app/gauge_settings.py').read_text()
TREE = ast.parse(SOURCE)
CLASS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'TouchSettings')
TAP = next(n for n in CLASS.body if isinstance(n, ast.FunctionDef) and n.name == 'tap')
scope = dict(time=time, TAB_TOP=42, TAB_HEIGHT=28)
exec(compile(ast.Module(body=[TAP], type_ignores=[]), '<tap>', 'exec'), scope)


class TransferUITests(unittest.TestCase):
    def test_old_page_replaced_without_removing_route_recording(self):
        self.assertNotIn("'G值 / GPS'", SOURCE)
        self.assertIn("'LOG 数据传输'", SOURCE)
        self.assertIn("start_recording=not self.motion.read().get('recording',False)", SOURCE)

    def test_transfer_tap_never_changes_motion(self):
        controls = types.SimpleNamespace(tab=4, motion=Mock(), log_transfer=Mock())
        scope['tap'](controls, 520, 135)
        controls.log_transfer.tap.assert_called_once_with(520, 135)
        controls.motion.command.assert_not_called()

    def test_removed_peak_and_record_buttons_are_inert(self):
        client = TransferClient()
        with patch('gauge_log_transfer.subprocess.run') as command:
            client.tap(165, 220)
            client.tap(465, 272)
        command.assert_not_called()

    def test_client_does_not_start_hotspot_on_construction(self):
        with patch('gauge_log_transfer.subprocess.run') as command:
            client = TransferClient()
        command.assert_not_called()
        self.assertFalse(client.busy)


if __name__ == '__main__':
    unittest.main()

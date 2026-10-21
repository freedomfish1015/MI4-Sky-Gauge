from pathlib import Path
import sys
import unittest
from unittest.mock import patch,Mock
import tempfile
from types import SimpleNamespace
import os
import fastboot_screen_repair as repair

class BundledRepairTests(unittest.TestCase):
    def test_stock_needs_no_write(self):
        self.assertEqual(repair.classify(repair.STOCK_SHA),'stock-already-has-rabbit')
    def test_already_repaired_needs_no_write(self):
        self.assertEqual(repair.classify(repair.NEW_SHA),'already-repaired')
    def test_known_sky_can_be_opted_in(self):
        self.assertEqual(repair.classify(repair.OLD_SHA),'eligible-known-sky-version')
    def test_unknown_refused(self):
        self.assertEqual(repair.classify('0'*64),'unsupported-refuse-write')
        with self.assertRaises(RuntimeError):repair.patched(bytes(4194304))
    @unittest.skipUnless(os.environ.get('MI4_TEST_ABOOT'), 'Optional private aboot fixture is not redistributed')
    def test_patch_matches_hardware_tested_candidate(self):
        original=Path(os.environ['MI4_TEST_ABOOT'])
        new=repair.patched(original.read_bytes())
        self.assertEqual(repair.sha(new),repair.NEW_SHA)
    def test_does_not_retain_personal_boot_or_logo_hash_requirement(self):
        self.assertFalse(hasattr(repair,'BOOT_SHA'))
        self.assertFalse(hasattr(repair,'LOGO_SHA'))

    def auto_case(self,status,power_error=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); real_path=Path
            def paths(value):
                if value=='/sys/firmware/devicetree/base/model':return SimpleNamespace(read_bytes=lambda:b'Xiaomi Mi4(cancro)\0')
                if value=='/run/lock/mi4-sky-logo.lock':return root/'lock'
                if value=='/run/obd-motion/state.json':return root/'absent-motion'
                return real_path(value)
            with patch.object(repair,'ROOT',root/'state'),patch.object(repair,'Path',side_effect=paths),\
                 patch.object(repair.os,'geteuid',return_value=0),patch.object(repair.fcntl,'flock'),\
                 patch.object(repair,'open_partition',return_value=123) as opened,\
                 patch.object(repair.os,'close'),patch.object(repair,'read_exact',return_value=b'test'),\
                 patch.object(repair,'sha',return_value='test-sha'),patch.object(repair,'classify',return_value=status),\
                 patch.object(repair,'power',side_effect=RuntimeError('low power') if power_error else None) as power,\
                 patch.object(repair,'write_sector') as write,patch.object(repair,'flush_dir'),\
                 patch.object(sys,'argv',['repair','--auto']):
                repair.main()
                write.assert_not_called();opened.assert_called_once_with('aboot')
                return (root/'state/status.json').read_text(),(root/'state/completed').exists(),power.call_count

    def test_auto_stock_no_aboot_write_and_completion_recorded(self):
        status,done,calls=self.auto_case('stock-already-has-rabbit')
        self.assertTrue(done);self.assertEqual(calls,0)

    def test_auto_already_repaired_no_aboot_write(self):
        status,done,calls=self.auto_case('already-repaired')
        self.assertTrue(done);self.assertEqual(calls,0)

    def test_auto_unknown_skips_without_completion_or_write(self):
        status,done,calls=self.auto_case('unsupported-refuse-write')
        self.assertFalse(done);self.assertIn('unsupported-refuse-write',status)

    def test_auto_low_power_defers_without_writable_partition(self):
        status,done,calls=self.auto_case('eligible-known-sky-version',power_error=True)
        self.assertFalse(done);self.assertIn('deferred',status)

# Reuse the seven failure/rollback tests against the actual bundled transaction.
import test_flash_guard
test_flash_guard.transaction=repair.transaction
test_flash_guard.patched=repair.patched
test_flash_guard.SECTOR=repair.SECTOR
GuardTests=test_flash_guard.GuardTests

if __name__=='__main__':unittest.main(verbosity=2)

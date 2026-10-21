"""Synthetic in-memory transactions only: never open a device or donor aboot."""
import unittest
from fastboot_screen_repair import transaction, patched, SECTOR

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.before=bytes(SECTOR+1024)
        changed=bytearray(self.before)
        changed[SECTOR+124:SECTOR+128]=b'ABCD'
        self.after=bytes(changed)
        self.disk=bytearray(self.before)
        self.writes=[]

    def write(self,raw):
        self.assertEqual(len(raw),512)
        self.writes.append(raw)
        self.disk[SECTOR:SECTOR+512]=raw

    def run_tx(self,power=lambda:None,untouched=lambda:None,write=None):
        transaction(self.before,self.after,lambda:bytes(self.disk),write or self.write,power,untouched)

    def test_success_writes_exactly_one_sector(self):
        self.run_tx();self.assertEqual(bytes(self.disk),self.after);self.assertEqual(len(self.writes),1)

    def test_low_power_never_writes(self):
        def fail():raise RuntimeError('power')
        with self.assertRaises(RuntimeError):self.run_tx(power=fail)
        self.assertEqual(self.writes,[])

    def test_concurrent_change_never_writes(self):
        self.disk[10]=1
        with self.assertRaises(RuntimeError):self.run_tx()
        self.assertEqual(self.writes,[])

    def test_failed_readback_rolls_back_original_sector(self):
        def write(raw):
            self.write(raw)
            if len(self.writes)==1:self.disk[SECTOR]=1
        with self.assertRaises(RuntimeError):self.run_tx(write=write)
        self.assertEqual(bytes(self.disk),self.before);self.assertEqual(len(self.writes),2)

    def test_untouched_partition_mismatch_rolls_back(self):
        def fail():raise RuntimeError('boot changed')
        with self.assertRaises(RuntimeError):self.run_tx(untouched=fail)
        self.assertEqual(bytes(self.disk),self.before)

    def test_partial_write_exception_rolls_back(self):
        def write(raw):
            self.write(raw)
            if len(self.writes)==1:raise OSError('interrupted')
        with self.assertRaises(OSError):self.run_tx(write=write)
        self.assertEqual(bytes(self.disk),self.before)

    def test_unknown_aboot_refused(self):
        with self.assertRaises(RuntimeError):patched(bytes(4194304))

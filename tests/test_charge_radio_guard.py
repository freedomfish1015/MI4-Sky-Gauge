import json
from pathlib import Path
import tempfile
import unittest
from charge_radio_guard import ChargeRadioGuard

class RadioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.rf=self.base/'rfkill';self.rf.mkdir()
        self.node=self.make('rfkill0','bluetooth','hci0')
        self.guard=ChargeRadioGuard(self.base/'persist/radio.json',self.rf,settle_seconds=0)

    def tearDown(self):self.tmp.cleanup()

    def make(self,name,kind,hci):
        node=self.rf/name;node.mkdir()
        (node/'type').write_text(kind);(node/'soft').write_text('0')
        hardware=self.base/'hardware'/hci;hardware.mkdir(parents=True,exist_ok=True)
        (node/'device').symlink_to(hardware,target_is_directory=True)
        return node

    def test_no_journal_does_not_override_user_block(self):
        (self.node/'soft').write_text('1');self.guard.recover()
        self.assertEqual((self.node/'soft').read_text(),'1')

    def test_reboot_restores_enabled_intent_and_removes_journal(self):
        self.guard.save({'rfkill0':0});(self.node/'soft').write_text('1')
        self.assertTrue(self.guard.recover());self.assertEqual((self.node/'soft').read_text(),'0')
        self.assertFalse(self.guard.journal.exists())

    def test_preexisting_disabled_intent_remains_disabled(self):
        self.guard.save({'rfkill0':1});self.guard.recover()
        self.assertEqual((self.node/'soft').read_text(),'1')

    def test_changed_rfkill_and_hci_indices(self):
        self.guard.save({'rfkill0':0})
        for p in self.node.iterdir():p.unlink()
        self.node.rmdir()
        replacement=self.make('rfkill5','bluetooth','hci2');(replacement/'soft').write_text('1')
        self.guard.recover();self.assertEqual((replacement/'soft').read_text(),'0')

    def test_late_hci_keeps_journal_for_retry(self):
        self.guard.save({'rfkill0':0});self.node.rename(self.rf/'absent')
        self.assertFalse(self.guard.recover());self.assertTrue(self.guard.journal.exists())
        (self.rf/'absent').rename(self.node);self.assertTrue(self.guard.recover())

    def test_wifi_is_never_touched(self):
        wifi=self.make('rfkill1','wlan','phy0');(wifi/'soft').write_text('1')
        self.guard.save({'rfkill0':0});self.guard.recover()
        self.assertEqual((wifi/'soft').read_text(),'1')

    def test_non_bluetooth_snapshot_refused(self):
        self.make('rfkill1','wlan','phy0')
        with self.assertRaises(ValueError):self.guard.save({'rfkill1':0})

    def test_bad_journal_refused_without_radio_write(self):
        self.guard.save({'rfkill0':0});data=json.loads(self.guard.journal.read_text())
        data['radios'][0]['soft']=2;self.guard.journal.write_text(json.dumps(data))
        (self.node/'soft').write_text('1')
        with self.assertRaises(ValueError):self.guard.recover()
        self.assertEqual((self.node/'soft').read_text(),'1')

    def test_boot_restore_waits_for_rfkill_replay(self):
        self.guard.save({'rfkill0':0});(self.node/'soft').write_text('1')
        now=[10.0]
        guard=ChargeRadioGuard(self.guard.journal,self.rf,clock=lambda:now[0])
        self.assertFalse(guard.recover());self.assertEqual((self.node/'soft').read_text(),'1')
        now[0]=13.0;self.assertTrue(guard.recover())
        self.assertEqual((self.node/'soft').read_text(),'0')

    def test_in_progress_charging_loop_does_not_recover(self):
        import ast
        tree=ast.parse((Path(__file__).resolve().parents[1]/'services/charge/gauge_charge_mode_service.py').read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=="mode.state['phase'] == 'normal'"
               and any(isinstance(c,ast.Call) and isinstance(c.func,ast.Attribute) and c.func.attr=='recover_charge_radio' for c in ast.walk(n))]
        self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main(verbosity=2)

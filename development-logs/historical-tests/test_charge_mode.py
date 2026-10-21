import copy
from types import SimpleNamespace
import unittest

from gauge_charge_mode_service import ChargeMode,Platform,UNITS,EVENT
from gauge_charge_mode import handle_charge_tap

class Backend:
    def __init__(self):
        self.supply=True;self.calls=[];self.fail=None
    def online(self):return self.supply
    def grab_key(self):self.calls.append('grab')
    def release_key(self):self.calls.append('release')
    def snapshot(self):
        return dict(brightness=901,units={u:True for u in UNITS},radios={'rfkill0':0},video_marker='original')
    def stop_recording(self):self.calls.append('save-recordings')
    def stop(self,unit):
        self.calls.append(('stop',unit))
        if unit==self.fail:raise OSError('test stop failure')
    def block_radio(self,state):self.calls.append('radio-block')
    def brightness(self,value):self.calls.append(('light',value))
    def restore(self,state):self.calls.append(('restore',copy.deepcopy(state)))

class ChargeModeTests(unittest.TestCase):
    def setUp(self):
        self.backend=Backend();self.saved=[]
        self.mode=ChargeMode(self.backend,lambda s:self.saved.append(copy.deepcopy(s)))
    def enter(self):self.mode.prepare();self.mode.enter()

    def test_enter_saves_logs_stops_only_fixed_services_then_blanks(self):
        self.enter()
        self.assertEqual(self.mode.state['phase'],'charging')
        self.assertEqual(self.backend.calls,['grab','save-recordings','radio-block']+
                         [('stop',u) for u in UNITS]+[('light',0)])
    def test_power_key_release_restores_not_other_touch_or_repeat(self):
        self.enter()
        self.assertFalse(self.mode.key_event(1,330,1))
        self.assertFalse(self.mode.key_event(1,116,0))
        self.assertFalse(self.mode.key_event(1,116,2))
        self.assertFalse(self.mode.key_event(1,116,1))
        self.assertTrue(self.mode.key_event(1,116,0))
        self.assertEqual(self.mode.state,dict(phase='normal',reason='power-key'))
        self.assertEqual(self.backend.calls[-1],'release')
    def test_unplug_exits_mode_so_original_countdown_can_be_seen(self):
        self.enter();self.backend.supply=False;self.mode.tick()
        self.assertEqual(self.mode.state,dict(phase='normal',reason='unplug'))
    def test_unknown_supply_does_not_fake_unplug(self):
        self.enter();self.backend.supply=None;self.mode.tick()
        self.assertEqual(self.mode.state['phase'],'charging')
    def test_battery_only_request_refused_before_key_grab(self):
        self.backend.supply=False
        with self.assertRaises(ValueError):self.mode.prepare()
        self.assertFalse(self.backend.calls)
    def test_stop_error_restores_previous_state(self):
        self.backend.fail=UNITS[1];self.mode.prepare()
        with self.assertRaises(OSError):self.mode.enter()
        self.assertEqual(self.mode.state['phase'],'normal')
        self.assertEqual(self.backend.calls[-1],'release')
        self.assertEqual(self.backend.calls[-2][0],'restore')
    def test_duplicate_request_does_not_overwrite_original_snapshot(self):
        self.enter()
        snapshot=copy.deepcopy(self.mode.state)
        with self.assertRaises(ValueError):self.mode.prepare()
        self.assertEqual(snapshot,self.mode.state)
    def test_inactive_unit_is_not_stopped(self):
        self.mode.prepare();self.mode.state['units'][UNITS[2]]=False;self.mode.enter()
        self.assertNotIn(('stop',UNITS[2]),self.backend.calls)
    def test_native_event_roundtrip(self):
        event=EVENT.pack(1,2,1,116,0)
        self.assertEqual(EVENT.unpack(event)[2:],(1,116,0))

    def test_runtime_mask_and_unmask_are_transient_and_restore_safe(self):
        platform=object.__new__(Platform)
        platform.radio_guard=SimpleNamespace(save=lambda state:None,recover=lambda:True)
        calls=[]
        platform.command=lambda *args:calls.append(args)
        platform.brightness=lambda value:calls.append(('light',value))
        state=dict(radios={},units={u:False for u in UNITS},brightness=901,bluetooth_runtime_masked=False)
        platform.block_radio(state);platform.restore(state)
        self.assertEqual(calls,[('mask','--runtime','--now','bluetooth.service'),
            ('unmask','--runtime','bluetooth.service'),('light',901)])
        calls.clear();state['bluetooth_runtime_masked']=True
        platform.block_radio(state);platform.restore(state)
        self.assertEqual(calls,[('light',901)])

class ButtonTests(unittest.TestCase):
    def setUp(self):
        self.logs=[];self.requests=[]
        self.controls=SimpleNamespace(message='',telemetry=SimpleNamespace(set_recording=self.logs.append))
        self.client=SimpleNamespace(request=lambda op:self.requests.append(op) or dict(ok=True))
    def test_confirmation_then_entry_and_log_flush(self):
        handle_charge_tap(self.controls,10,self.client)
        self.assertFalse(self.requests)
        handle_charge_tap(self.controls,11,self.client)
        self.assertEqual(self.requests,['enter']);self.assertEqual(self.logs,[False])
    def test_expired_confirmation_rearms_without_entering(self):
        handle_charge_tap(self.controls,10,self.client)
        handle_charge_tap(self.controls,17,self.client)
        self.assertFalse(self.requests)
    def test_failed_request_leaves_log_recording_unchanged(self):
        bad=SimpleNamespace(request=lambda op:dict(ok=False,error='请先连接充电线'))
        handle_charge_tap(self.controls,10,bad);handle_charge_tap(self.controls,11,bad)
        self.assertEqual(self.controls.message,'请先连接充电线');self.assertFalse(self.logs)

if __name__=='__main__':unittest.main()

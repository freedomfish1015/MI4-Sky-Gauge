import asyncio
import struct
from types import SimpleNamespace as NS
import unittest
from gauge_ble_protocol import (select_protocol,decode_skygauge,run_skygauge,
                                UnsupportedBleProtocol,uuid16,SkyTelemetry,
                                SKY_ALLOW_ALL_100MS)


def service(uuid,chars):
    return NS(uuid=uuid16(uuid),characteristics=chars)


def char(uuid,props):
    return NS(uuid=uuid16(uuid),properties=props)


class ProtocolTests(unittest.TestCase):
    def test_ota_and_pairing_are_never_elm(self):
        with self.assertRaisesRegex(UnsupportedBleProtocol,'遥测'):
            select_protocol([service('1ff9',[char('0003',['read'])]),
                             service('1ffa',[char('0001',['read'])]),
                             service('1ffb',[char('0001',['write'])])])

    def test_rc_characteristic_is_selected_by_service_not_ambiguous_uuid(self):
        rx=char('0001',['read','notify'])
        proto=select_protocol([service('1ffa',[char('0001',['read'])]),service('1ff8',[rx])])
        self.assertEqual(proto.kind,'skygauge')
        self.assertIs(proto.rx,rx)
        self.assertIsNone(proto.tx)

    def test_elm_write_mode_matches_actual_properties(self):
        for props,response in [(['notify','write'],True),(['notify','write-without-response'],False)]:
            proto=select_protocol([service('ffe0',[char('ffe1',props)])])
            self.assertEqual(proto.kind,'elm')
            self.assertEqual(proto.response,response)

    def test_split_elm_channels(self):
        for sid,rid,tid in [('fff0','fff2','fff1'),('18f0','2af0','2af1'),
                            ('ff12','ff14','ff15')]:
            for mode,response in [('write',True),('write-without-response',False)]:
                with self.subTest(service=sid,mode=mode):
                    rx=char(rid,['notify'])
                    tx=char(tid,[mode])
                    proto=select_protocol([service(sid,[tx,rx])])
                    self.assertIs(proto.rx,rx)
                    self.assertIs(proto.tx,tx)
                    self.assertEqual(proto.response,response)

    def test_no_cross_service_pairing_or_unknown_writes(self):
        for services in [
            [service('fff0',[char('fff1',['write'])]),
             service('1ffb',[char('fff2',['notify'])])],
            [service('abcd',[char('ffe1',['notify','write'])])],
            [service('fff0',[char('fff1',['write']),char('abcd',['notify'])])],
        ]:
            with self.assertRaises(UnsupportedBleProtocol):
                select_protocol(services)

    def test_binary_channels_scaling_and_signed_temperatures(self):
        packet=b''.join(struct.pack('<Ii',pid,value) for pid,value in
                        [(0xf101,2860),(0xf102,88),(0xf103,-12),(0xf108,13800),(0xf106,750)])
        values=decode_skygauge(packet)
        self.assertEqual(values['obd.rpm'],2860)
        self.assertEqual(values['obd.coolant_temp'],-12)
        self.assertAlmostEqual(values['obd.battery_voltage'],13.8)
        self.assertEqual(values['obd.load'],75)
        self.assertEqual(decode_skygauge(b'bad'),{})
        self.assertEqual(decode_skygauge(struct.pack('<Ii',0xabcd,123)),{})

    def test_all_nine_stock_channels_and_validity_rules(self):
        wire = [(0xf101,2860),(0xf102,88),(0xf103,-40),(0xf104,32),
                (0xf105,95),(0xf106,750),(0xf107,235),(0xf108,13800),(0xf109,1234)]
        decoded = decode_skygauge(b''.join(struct.pack('<Ii',*item) for item in wire))
        self.assertEqual(len(decoded),9)
        self.assertEqual(decoded['obd.coolant_temp'],-40)
        self.assertEqual(decoded['obd.throttle'],23.5)
        self.assertAlmostEqual(decoded['obd.brake_temp'],123.4)
        for pid, invalid in [(0xf101,0),(0xf102,-1),(0xf103,-100),
                             (0xf104,-32768),(0xf105,-100),(0xf106,-10),
                             (0xf107,-10),(0xf108,0),(0xf109,-1000)]:
            self.assertEqual(decode_skygauge(struct.pack('<Ii',pid,invalid)),{})
        self.assertEqual(decode_skygauge(struct.pack('<Ii',0xf102,0)),{'obd.speed':0})

    def test_each_field_expires_independently_and_unknown_packets_do_not_refresh(self):
        state=SkyTelemetry()
        state.receive(struct.pack('<Ii',0xf101,2000),0)
        state.receive(struct.pack('<Ii',0xf103,90),2)
        state.receive(struct.pack('<Ii',0xdead,123),3)
        state.receive(b'bad',3)
        self.assertEqual(state.snapshot(3.1),{'obd.coolant_temp':90})
        self.assertIn('1/9',state.status(3.1))
        self.assertEqual(state.snapshot(5.1),{})
        self.assertIn('等待',state.status(5.1))
        self.assertEqual(state.malformed,1)
        self.assertEqual(state.counts,{'obd.rpm':1,'obd.coolant_temp':1})

    def test_only_matching_1ff8_control_may_be_used(self):
        rx=char('0001',['notify'])
        ota=char('0002',['write'])
        proto=select_protocol([service('1ffb',[ota]),service('1ff8',[rx])])
        self.assertIsNone(proto.control)
        control=char('0002',['write'])
        proto=select_protocol([service('1ffb',[ota]),service('1ff8',[rx,control])])
        self.assertIs(proto.control,control)
        self.assertIsNone(proto.tx)

    def test_stock_subscription_command_and_cancellation_clear_values(self):
        async def scenario():
            rx=char('0001',['notify'])
            control=char('0002',['write'])
            proto=select_protocol([service('1ff8',[rx,control])])
            calls=[]
            publications=[]
            ready=asyncio.Event()
            class Client:
                is_connected=True
                async def start_notify(self,channel,callback):
                    self.callback=callback
                    calls.append('notify')
                async def write_gatt_char(self,channel,data,response):
                    self_outer.assertIs(channel,control)
                    # Captured runtime requests 250 ms; the old constant name is retained for compatibility.
                    self_outer.assertEqual(data,b'\x01\x00\xfa')
                    self_outer.assertTrue(response)
                    calls.append('subscribe')
                    self.callback(rx,struct.pack('<Ii',0xf101,2300))
                async def stop_notify(self,_channel):calls.append('stop')
            self_outer=self
            def publish(values,status):
                publications.append((dict(values),status))
                if values.get('obd.rpm')==2300:ready.set()
            task=asyncio.create_task(run_skygauge(Client(),proto,publish))
            try:
                await asyncio.wait_for(ready.wait(),1)
            finally:
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
            self.assertEqual(calls,['notify','subscribe','stop'])
            self.assertEqual(publications[-1][0],{})
            self.assertIn('断开',publications[-1][1])
            self.assertEqual(SKY_ALLOW_ALL_100MS,b'\x01\x00\xfa')
        asyncio.run(scenario())

    def test_silent_connection_repairs_once_then_reconnects_without_fake_data(self):
        async def scenario():
            calls=[]
            publications=[]
            class Client:
                is_connected=True
                async def start_notify(self,*args):calls.append('start')
                async def stop_notify(self,*args):calls.append('stop')
            proto=select_protocol([service('1ff8',[char('0001',['notify'])])])
            with self.assertRaisesRegex(TimeoutError,'停止更新'):
                await asyncio.wait_for(run_skygauge(Client(),proto,
                    lambda values,status:publications.append(dict(values)),silence_timeout=.01),1)
            self.assertEqual(calls,['start','stop','start','stop'])
            self.assertTrue(all(values=={} for values in publications))
        asyncio.run(scenario())

    def test_skygauge_subscribes_without_ever_writing_commands(self):
        async def scenario():
            class Client:
                is_connected=True
                unsubscribed=False
                async def start_notify(self,characteristic,callback):
                    callback(characteristic,struct.pack('<Ii',0xf101,2000))
                async def stop_notify(self,_char):
                    self.unsubscribed=True
                async def write_gatt_char(self,*_args,**_kwargs):
                    raise AssertionError('No ELM or OTA writes allowed')
            client=Client()
            rx=char('0001',['notify'])
            proto=select_protocol([service('1ff8',[rx])])
            event=asyncio.Event()
            def publish(values,status):
                if values.get('obd.rpm')==2000:event.set()
            task=asyncio.create_task(run_skygauge(client,proto,publish))
            try:
                await asyncio.wait_for(event.wait(),1)
            finally:
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
            self.assertTrue(client.unsubscribed)
        asyncio.run(scenario())


if __name__=='__main__':
    unittest.main()

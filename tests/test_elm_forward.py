import asyncio
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from elm_bridge_ipc import CommandFramer, GatewayRelay
from elm_passive import Passive, frames
from gauge_elm_forward import run_forward


class DecoderTests(unittest.TestCase):
    def test_command_fragment_guard_and_repeat(self):
        framer = CommandFramer()
        self.assertEqual(framer.feed(b'01'), [])
        self.assertEqual(framer.feed(b'0C\r'), [(b'010C\r','010C')])
        self.assertEqual(framer.feed(b'\r'), [(b'\r','010C')])
        for cmd in ('ATZ','ATSH7DF','ATCRA','ATCEA01','ATCAF0','ATST0A','22D002','010C1'):
            self.assertTrue(CommandFramer().feed((cmd+'\r').encode()))
        for cmd in ('04','2E1234FF','1101','2701','ATPP01ON','ATSH7DF\x0004'):
            with self.assertRaises(ValueError):
                CommandFramer().feed((cmd+'\r').encode())
        with self.assertRaises(ValueError):
            CommandFramer().feed(b'180322DA2E\r')
        framer.acknowledge('ATCAF0',b'\rOK\r>')
        self.assertTrue(framer.feed(b'180322DA2E\r'))
        with self.assertRaises(ValueError):
            framer.feed(b'18042EDA2E01\r')

    def test_passive_units_missing_stale_and_headers(self):
        passive = Passive({})
        passive.begin('010C'); passive.consume(b'010C\r7E8 04 41 0C 1F 40\r>', 1)
        passive.begin('010D'); passive.consume(b'41 0D 32\r>', 1)
        self.assertEqual(passive.snapshot(2)['obd.rpm'], 2000)
        self.assertEqual(passive.snapshot(2)['obd.speed'], 50)
        self.assertEqual(passive.snapshot(5), {})
        passive.begin('010C'); passive.consume(b'NO DATA\r>', 6)
        self.assertEqual(passive.snapshot(6), {})
        passive.begin('010C'); passive.consume(b'410C1F40\r410C2F40\r>', 7)
        self.assertEqual(passive.snapshot(7), {})

    def test_profile_rpn_and_multiframe(self):
        profile = {'_native_profile':{'signals':[dict(id='obd.battery_voltage',unit='mV',src=[
            dict(req='0142',len=2,rpn=[['R',0,16,'be']])])]}}
        passive = Passive(profile)
        passive.begin('0142'); passive.consume(b'41 42 36 B0\r>', 1)
        self.assertEqual(passive.snapshot(2)['obd.battery_voltage'], 14)
        raw = '7E8 10 09 62 12 34 01 02 03\r7E8 21 04 05 06 00 00 00 00'
        self.assertEqual(list(frames(raw)), [bytes.fromhex('621234010203040506')])
        profile={'_native_profile':{'signals':[dict(id='obd.gear',src=[
            dict(raw='18 03 22 DA 2E',expect='62DA2E',len=1,rpn=[['A',0]])])]}}
        passive=Passive(profile)
        passive.begin('180322DA2E'); passive.consume(b'F1 04 62 DA 2E 05\r>',1)
        self.assertEqual(passive.snapshot(2)['obd.gear'],5)


class ForwardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        patcher=patch('gauge_elm_forward.event')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name)/'bridge.sock')
        self.relay = GatewayRelay()
        await self.relay.start(self.path, uid=os.getuid())
        self.writes = []
        self.clients = []
        self.published = []
        outer = self
        class FakeClient:
            def __init__(self, *a, **kw):
                self.is_connected = False
                self.services = [SimpleNamespace(uuid='0000ffe0-0000-1000-8000-00805f9b34fb',
                    characteristics=[SimpleNamespace(uuid='0000ffe1-0000-1000-8000-00805f9b34fb',
                                                    properties=['notify','write-without-response'])])]
                outer.clients.append(self)
            async def connect(self): self.is_connected = True
            async def start_notify(self, char, callback): self.callback = callback
            async def write_gatt_char(self, char, data, response=False):
                outer.writes.append(bytes(data))
                if data == b'ATMA\r':
                    return  # a monitor emits no prompt until interrupted
                reply = (b'STOPPED\r>' if data == b'\r' else
                         b'ELM327 v1.5\r>' if data == b'ATZ\r' else b'41 0C 1F 40\r>')
                asyncio.get_running_loop().call_later(.01, self.callback, 1, reply[:4])
                asyncio.get_running_loop().call_later(.02, self.callback, 1, reply[4:])
            async def stop_notify(self, char): pass
            async def disconnect(self): self.is_connected = False
        self.client_factory = FakeClient
        self.pump = asyncio.create_task(self.pump_tx())

    async def pump_tx(self):
        while True:
            await self.relay.send(await self.relay.take_tx())

    async def asyncTearDown(self):
        if hasattr(self, 'uplink'):
            self.uplink.cancel()
            await asyncio.gather(self.uplink, return_exceptions=True)
        self.pump.cancel()
        await asyncio.gather(self.pump, return_exceptions=True)
        await self.relay.close()
        self.tmp.cleanup()

    async def start_uplink(self):
        self.uplink = asyncio.create_task(run_forward('02:00:00:00:00:03', {},
            lambda values,status:self.published.append((values,status)),
            client_factory=self.client_factory, socket_path=self.path))
        for _ in range(100):
            if self.relay.ready: break
            await asyncio.sleep(.01)
        self.assertTrue(self.relay.ready)
        self.relay.notifying = True
        self.relay.subscribed()

    async def test_end_to_end_raw_stream_and_passive_values(self):
        await self.start_uplink()
        self.relay.write(b'ATZ\r010')
        self.relay.write(b'C\r')
        output = b''
        for _ in range(4):
            output += await asyncio.wait_for(self.relay.take_rx(), 1)
        self.assertEqual(output, b'ELM327 v1.5\r>41 0C 1F 40\r>')
        self.assertEqual(self.writes, [b'ATZ\r',b'010C\r'])
        await asyncio.sleep(.15)
        self.assertEqual(self.published[-1][0]['obd.rpm'], 2000)
        self.relay.end_session()
        with self.assertRaises((ConnectionError,ValueError)):
            await asyncio.wait_for(self.uplink, 1)
        self.assertFalse(self.clients[0].is_connected)
        self.assertEqual(self.published[-1][0], {})

    async def test_write_commands_never_reach_obd(self):
        await self.start_uplink()
        self.relay.write(b'04\r')
        with self.assertRaises(ValueError):
            await asyncio.wait_for(self.uplink, 1)
        self.assertEqual(self.writes, [])

    async def test_monitor_interrupt_does_not_deadlock_transaction_queue(self):
        await self.start_uplink()
        self.relay.write(b'ATMA\r')
        await asyncio.sleep(.05)
        self.relay.write(b'\r')
        stop = await asyncio.wait_for(self.relay.take_rx(), 1)
        stop += await asyncio.wait_for(self.relay.take_rx(), 1)
        self.assertEqual(stop,b'STOPPED\r>')
        self.relay.write(b'010C\r')
        await asyncio.wait_for(self.relay.take_rx(), 1)
        await asyncio.wait_for(self.relay.take_rx(), 1)
        self.assertEqual(self.writes,[b'ATMA\r',b'\r',b'010C\r'])

    async def test_second_uplink_cannot_replace_current_owner(self):
        await self.start_uplink()
        from elm_bridge_ipc import packet
        reader, writer = await asyncio.open_unix_connection(self.path)
        writer.write(packet('ready',address='02:00:00:00:00:04'))
        await writer.drain()
        try:
            self.assertEqual(await asyncio.wait_for(reader.read(),1), b'')
        except ConnectionResetError:
            pass  # closing a rejected Unix peer may reset unread handshake bytes
        self.assertTrue(self.relay.ready)
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionResetError:
            pass


if __name__ == '__main__': unittest.main()

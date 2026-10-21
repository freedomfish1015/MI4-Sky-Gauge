import asyncio
import unittest
from elm_bridge_core import ByteRelay, chunks


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_raw_commands_and_responses_unchanged(self):
        relay = ByteRelay()
        relay.ready = relay.notifying = True
        for value in (b'AT', b'SH7E0\r', b'22F190\r', b'\r'):
            relay.write(value)
            self.assertEqual(await relay.take_tx(), value)
        raw = b'22F190\r7E8 10 14 62 F1 90\r7E8 21 31 32 33\r\r>'
        relay.receive(raw)
        self.assertEqual(b''.join(chunks(await relay.take_rx())), raw)

    async def test_no_offline_fake_replies(self):
        relay = ByteRelay()
        relay.notifying = True
        with self.assertRaises(RuntimeError):
            relay.write(b'ATZ\r')
        self.assertTrue(relay.rx.empty())

    async def test_no_replay_to_new_subscriber(self):
        relay = ByteRelay()
        relay.receive(b'old data>')
        self.assertTrue(relay.rx.empty())
        relay.notifying = True
        relay.receive(b'new data>')
        relay.clear()
        self.assertTrue(relay.rx.empty())

    async def test_overflow_rejects_whole_write(self):
        relay = ByteRelay(limit=5)
        relay.ready = relay.notifying = True
        relay.write(b'ATZ\r')
        with self.assertRaises(BufferError):
            relay.write(b'ATI\r')
        self.assertEqual(await relay.take_tx(), b'ATZ\r')
        self.assertTrue(relay.tx.empty())

    async def test_notification_overflow_is_error_not_silent_truncation(self):
        relay = ByteRelay(limit=4)
        relay.notifying = True
        with self.assertRaises(BufferError):
            relay.receive(b'12345')

    async def test_chunk_size_preserves_all_bytes(self):
        value = bytes(range(255))
        self.assertEqual(b''.join(chunks(value)), value)
        self.assertTrue(all(len(c) <= 20 for c in chunks(value)))


if __name__ == '__main__':
    unittest.main()

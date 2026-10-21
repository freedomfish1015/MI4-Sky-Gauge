"""Bounded, byte-preserving UART relay; no ELM emulation or fake replies."""
import asyncio


class ByteRelay:
    def __init__(self, limit=65536):
        self.limit = limit
        self.tx = asyncio.Queue(maxsize=256)
        self.rx = asyncio.Queue(maxsize=256)
        self.tx_bytes = self.rx_bytes = 0
        self.ready = False
        self.notifying = False

    def write(self, data):
        if not self.ready or not self.notifying:
            raise RuntimeError('upstream not ready or Sky has not subscribed')
        data = bytes(data)
        if not data or len(data) > 512:
            raise ValueError('invalid ATT write size')
        if self.tx.full() or self.tx_bytes+len(data) > self.limit:
            raise BufferError('upstream queue overflow; reconnect required')
        self.tx.put_nowait(data)
        self.tx_bytes += len(data)

    def receive(self, data):
        data = bytes(data)
        if not self.notifying:
            return  # Do not replay old vehicle data to a new subscriber.
        if self.rx.full() or self.rx_bytes+len(data) > self.limit:
            raise BufferError('downstream queue overflow; reconnect required')
        self.rx.put_nowait(data)
        self.rx_bytes += len(data)

    async def take_tx(self):
        data = await self.tx.get()
        self.tx_bytes -= len(data)
        return data

    async def take_rx(self):
        data = await self.rx.get()
        self.rx_bytes -= len(data)
        return data

    def clear(self):
        for queue in (self.tx, self.rx):
            while not queue.empty():
                queue.get_nowait()
        self.tx_bytes = self.rx_bytes = 0


def chunks(data, size=20):
    if size < 1:
        raise ValueError('invalid MTU payload')
    return [bytes(data[i:i+size]) for i in range(0, len(data), size)]

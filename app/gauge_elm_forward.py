"""Gauge-owned upstream: serial read-only Sky requests, passive UI updates."""
import asyncio
import time
from elm_bridge_core import chunks
from elm_bridge_ipc import SOCKET, packet, unpack, payload, CommandFramer
from elm_passive import Passive
from gauge_ble_diagnostics import event


async def run_forward(address, profile, publish, simulated=False, client_factory=None, socket_path=SOCKET):
    if client_factory is None:
        from bleak import BleakClient
        client_factory = BleakClient
    from gauge_ble_protocol import select_protocol
    notifications = asyncio.Queue(maxsize=256)
    commands = asyncio.Queue(maxsize=32)
    prompt = asyncio.Event()
    failed = asyncio.Event()
    observer = Passive(profile)
    framer = CommandFramer()
    response = bytearray()
    active = False
    sky = False
    monitoring = False
    write_lock = asyncio.Lock()
    label = '台架模拟源' if simulated else '真实 OBD'
    def receive(_sender, data):
        if not active:
            return
        if notifications.full() or not 1 <= len(data) <= 2048:
            failed.set()
        else:
            notifications.put_nowait(bytes(data))
    client = client_factory(address, disconnected_callback=lambda _:failed.set())
    writer = None
    tasks = []
    subscribed = False
    counts = dict(commands=0, rx_bytes=0, tx_bytes=0)
    try:
        publish({}, label+' · 正在连接上游 '+address)
        await client.connect()
        protocol = select_protocol(client.services)
        if protocol.kind != 'elm':
            raise RuntimeError('转发上游必须是 ELM327 BLE 适配器，不是 Sky 主表')
        await client.start_notify(protocol.rx, receive)
        subscribed = True
        reader, writer = await asyncio.open_unix_connection(socket_path, limit=8192)
        writer.write(packet('ready', address=address, simulated=simulated))
        await writer.drain()
        active = True

        async def read_sky():
            nonlocal sky
            while True:
                message = unpack(await reader.readline())
                if message.get('kind') == 'sky':
                    sky = message.get('connected') is True
                elif message.get('kind') == 'tx':
                    for command in framer.feed(payload(message)):
                        raw, cmd = command
                        if monitoring and not raw.strip():
                            # Stock Sky sends CR to stop ATMA before its prompt.
                            # This is an interrupt, not a second ECU transaction.
                            async with write_lock:
                                await client.write_gatt_char(protocol.tx, raw, response=protocol.response)
                            counts['tx_bytes'] += len(raw)
                        else:
                            commands.put_nowait(command)
                else:
                    raise ValueError('unknown gateway message')

        async def send_commands():
            nonlocal monitoring
            while True:
                raw, cmd = await commands.get()
                response.clear()
                prompt.clear()
                observer.begin(cmd)
                monitoring = cmd in ('ATMA','ATMR','ATMT')
                async with write_lock:
                    for part in chunks(raw):
                        await client.write_gatt_char(protocol.tx, part, response=protocol.response)
                        counts['tx_bytes'] += len(part)
                counts['commands'] += 1
                await asyncio.wait_for(prompt.wait(), 12 if cmd.startswith('AT') else 8)
                monitoring = False

        async def relay_notifications():
            while True:
                data = await notifications.get()
                counts['rx_bytes'] += len(data)
                if observer.pending is not None:
                    response.extend(data)
                    if len(response) > 32768:
                        if monitoring:
                            del response[:-2048]
                        else:
                            raise BufferError('ELM reply overflow')
                    if b'>' in data:
                        framer.acknowledge(observer.pending, bytes(response))
                        observer.consume(bytes(response))
                        prompt.set()
                writer.write(packet('rx', data))
                await asyncio.wait_for(writer.drain(), 2)
                if prompt.is_set():
                    # Publish fresh engineering values immediately after sending
                    # the reply onward, not on the old 100ms UI timer.
                    publish(observer.snapshot(), label+(' → Sky 转发中' if sky else '已连接 · 等待 Sky 主表'))

        async def state():
            previous = 0
            while True:
                publish(observer.snapshot(), label+(' → Sky 转发中' if sky else '已连接 · 等待 Sky 主表'))
                if time.monotonic()-previous >= 5:
                    event('elm_forward_stats', address=address, simulated=simulated, sky=sky, **counts)
                    previous = time.monotonic()
                await asyncio.sleep(.1)

        tasks = [asyncio.create_task(fn()) for fn in (read_sky, send_commands, relay_notifications, state)]
        tasks.append(asyncio.create_task(failed.wait()))
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if not task.cancelled() and task.exception():
                raise task.exception()
        raise ConnectionError('ELM or gateway disconnected')
    finally:
        active = False
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if writer:
            writer.close()
            await writer.wait_closed()
        if client.is_connected:
            try:
                if subscribed:
                    await asyncio.wait_for(client.stop_notify(protocol.rx), 3)
            finally:
                await asyncio.wait_for(client.disconnect(), 5)
        publish({}, label+' · 转发已断开，等待重连')
        event('elm_forward_session_end', address=address, simulated=simulated, **counts)

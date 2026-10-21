"""Async BLE transport for the single-flight upstream vehicle engine."""
import asyncio
import time
from gauge_compat import Vehicle
from gauge_ble_diagnostics import Trace, error as diagnostic_error, event

CHAR_UUID = '0000ffe1-0000-1000-8000-00805f9b34fb'
ALIASES = dict(rpm='obd.rpm', speed='obd.speed', coolant='obd.coolant_temp',
               oil='obd.oil_temp', battery='obd.battery_voltage')


async def run_vehicle_ble(address, profile, publish, client_factory=None):
    """Own one BLE connection, never mix legacy commands into this engine.

    Notifications only queue bytes. The coroutine owns every engine call;
    cancellation closes native state and BLE subscription before reconnect.
    publish receives engineering values/None and a diagnostic status.
    """
    if client_factory is None:
        from bleak import BleakClient
        client_factory = BleakClient
    queue = asyncio.Queue(maxsize=128)
    overflow = False
    started = time.monotonic()
    trace = Trace(address)
    def milliseconds():
        return int((time.monotonic() - started) * 1000)
    def notify(_sender, data):
        nonlocal overflow
        trace.packet('rx',data)
        if queue.full() or len(data) > 65536:
            overflow = True
        else:
            queue.put_nowait(bytes(data))
    client = client_factory(address)
    subscribed = False
    engine = None
    try:
        await client.connect()
        trace.mark('gatt_connected')
        if hasattr(client,'services'):
            trace.services(client.services)
        from gauge_ble_protocol import select_protocol, run_skygauge
        protocol = select_protocol(client.services) if hasattr(client,'services') else None
        if protocol is not None:
            trace.protocol(protocol)
        if protocol is not None and protocol.kind == 'skygauge':
            await run_skygauge(client,protocol,publish)
            return
        rx_char = protocol.rx if protocol else CHAR_UUID
        tx_char = protocol.tx if protocol else CHAR_UUID
        response = protocol.response if protocol else False
        engine = Vehicle(profile)
        await client.start_notify(rx_char, notify)
        subscribed = True
        trace.mark('notify_subscribed')
        engine.link(True, milliseconds())
        previous = -100
        while client.is_connected:
            if overflow:
                raise RuntimeError('ELM notification queue overflow; reconnect required')
            while not queue.empty():
                engine.rx(queue.get_nowait(), milliseconds())
            wait, command = engine.run(milliseconds())
            if command is not None:
                payload = (command + '\r').encode('ascii')
                # The upstream whitelist currently fits an ATT payload of 20.
                if len(payload) > 20:
                    raise RuntimeError('ELM command exceeds verified BLE packet size')
                await client.write_gatt_char(tx_char,payload,response=response)
                trace.packet('tx',payload)
            now = milliseconds()
            if now - previous >= 50:
                snapshot = engine.snapshot()
                event('engine_state',throttle=(trace.session,'state'),address=address,
                      session=trace.session,link=snapshot['link'],reconnect=snapshot['reconnect'],
                      values=snapshot['values'])
                publish(snapshot['values'], '已连接 ' + address if snapshot['link'] == 2
                        else '已连接，正在初始化/等待数据')
                if snapshot['reconnect']:
                    raise RuntimeError('ELM engine requested reconnect')
                previous = now
            try:
                packet = await asyncio.wait_for(queue.get(), max(1, min(wait, 100)) / 1000)
                engine.rx(packet, milliseconds())
            except asyncio.TimeoutError:
                pass
        raise RuntimeError('BLE disconnected')
    except BaseException as exc:
        diagnostic_error('transport_error',exc,address=address,session=trace.session)
        raise
    finally:
        trace.mark('disconnect',counts=trace.counts)
        if engine is not None:
            engine.link(False,milliseconds())
            engine.close()
        if subscribed and client.is_connected:
            try:
                await client.stop_notify(rx_char)
            except Exception:
                pass
        if client.is_connected:
            try:
                await client.disconnect()
            except Exception:
                pass

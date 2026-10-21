"""Explicit BLE protocols. Never treat SkyGauge OTA as an ELM UART."""
import asyncio
from dataclasses import dataclass
import struct
import time


def uuid16(value):
    return '0000%s-0000-1000-8000-00805f9b34fb' % value


class UnsupportedBleProtocol(RuntimeError):
    pass


@dataclass
class Protocol:
    kind: str
    rx: object
    tx: object = None
    response: bool = False
    control: object = None


def select_protocol(services):
    services = list(services)
    for service in services:
        if service.uuid.lower() == uuid16('1ff8'):
            controls = [c for c in service.characteristics
                        if c.uuid.lower() == uuid16('0002') and 'write' in c.properties]
            if len(controls) > 1:
                raise UnsupportedBleProtocol('SkyGauge 遥测订阅通道不唯一')
            for char in service.characteristics:
                if char.uuid.lower() == uuid16('0001') and 'notify' in char.properties:
                    return Protocol('skygauge',char,control=controls[0] if controls else None)
            raise UnsupportedBleProtocol('SkyGauge 遥测服务缺少通知通道')
    # Known ELM UART layouts from upstream elm327_ble_client.c. RX/TX may
    # be separate characteristics; never guess writable OTA/config handles.
    layouts = [('ffe0','ffe1','ffe1'), ('fff0','fff2','fff1'),
               ('18f0','2af0','2af1'), ('ff12','ff14','ff15')]
    for service_id,rx_id,tx_id in layouts:
        for service in services:
            if service.uuid.lower() != uuid16(service_id):
                continue
            receivers = [c for c in service.characteristics
                         if c.uuid.lower() == uuid16(rx_id) and
                         ('notify' in c.properties or 'indicate' in c.properties)]
            writers = [c for c in service.characteristics
                       if c.uuid.lower() == uuid16(tx_id) and
                       ('write' in c.properties or 'write-without-response' in c.properties)]
            if len(receivers) == 1 and len(writers) == 1:
                tx = writers[0]
                return Protocol('elm',receivers[0],tx,
                                'write-without-response' not in tx.properties)
    if any(s.uuid.lower() in (uuid16('1ff9'),uuid16('1ffa'),uuid16('1ffb')) for s in services):
        raise UnsupportedBleProtocol('SkyGauge 无 BLE 遥测服务，需兼容主机固件')
    raise UnsupportedBleProtocol('此设备没有支持的 OBD / SkyGauge 数据通道')


RC_CHANNELS = {
    0xf101: ('obd.rpm',1), 0xf102: ('obd.speed',1),
    0xf103: ('obd.coolant_temp',1), 0xf104: ('obd.intake_temp',1),
    0xf105: ('obd.oil_temp',1), 0xf106: ('obd.load',.1),
    0xf107: ('obd.throttle',.1), 0xf108: ('obd.battery_voltage',.001),
    0xf109: ('obd.brake_temp',.1),
}

# Source pinned to main-104-9c3fa1b27e9d, racechrono_ble_diy.c.
# CAN notification is LE32 virtual PID + LE32 signed value. Filter command 1
# accepts a BIG-endian interval. This affects this connection, not flash/NVS.
SKY_INTERVAL_MS = 250
SKY_ALLOW_ALL_100MS = bytes((1, (SKY_INTERVAL_MS >> 8) & 0xFF,
                             SKY_INTERVAL_MS & 0xFF))
SKY_STALE_SECONDS = 3


def _valid_sky_raw(pid, raw):
    # Mirror the stock producer's validity rules; do not replace missing RPM
    # with zero or discard -40C, which the producer explicitly allows.
    if pid == 0xf101:
        return 0 < raw <= 65535
    if pid == 0xf102:
        return 0 <= raw <= 255
    if pid in (0xf103, 0xf104, 0xf105):
        return -100 < raw <= 32767
    if pid in (0xf106, 0xf107):
        return 0 <= raw <= 327670
    if pid == 0xf108:
        return raw > 0
    if pid == 0xf109:
        return -1000 < raw <= 32767
    return False


def decode_skygauge(packet):
    # Source: racechrono_ble_diy.c send_can_packet(): LE uint32 ID + LE int32.
    if not packet or len(packet)%8:
        return {}
    values = {}
    for offset in range(0,len(packet),8):
        pid,raw = struct.unpack_from('<Ii',packet,offset)
        if pid in RC_CHANNELS and _valid_sky_raw(pid, raw):
            key,scale = RC_CHANNELS[pid]
            values[key] = raw*scale
    return values


class SkyTelemetry:
    """Bounded, per-field freshness; a live temperature never refreshes old RPM."""
    def __init__(self):
        self.latest = {}
        self.counts = {}
        self.packets = 0
        self.malformed = 0
        self.last_valid_at = None

    def receive(self, packet, now):
        self.packets += 1
        if not packet or len(packet) % 8:
            self.malformed += 1
            return {}
        decoded = decode_skygauge(packet)
        if decoded:
            self.last_valid_at = now
        for key, value in decoded.items():
            self.latest[key] = (value, now)
            self.counts[key] = self.counts.get(key, 0) + 1
        return decoded

    def snapshot(self, now):
        return {key: value for key, (value, stamp) in self.latest.items()
                if now - stamp < SKY_STALE_SECONDS}

    def status(self, now):
        fresh = self.snapshot(now)
        return ('BLE遥测 · %d/9项' % len(fresh) if fresh else
                '蓝牙已连接 · 等待有效遥测')


async def run_skygauge(client, protocol, publish, *, silence_timeout=6):
    """Receive stock telemetry; optional session-only 1FF8 subscription control.

    Never send ELM, OTA, configuration/NVS, or ESP-NOW control commands.
    """
    telemetry = SkyTelemetry()
    from gauge_ble_diagnostics import event
    subscribed = False
    began = time.monotonic()
    repair_at = None
    def notify(_sender,data):
        now = time.monotonic()
        decoded = telemetry.receive(bytes(data), now)
        event('skygauge_rx',throttle='skygauge_rx',length=len(data),
              hex=bytes(data[:256]).hex(),values=decoded)
    try:
        await client.start_notify(protocol.rx,notify)
        subscribed = True
        if protocol.control is not None:
            await asyncio.wait_for(client.write_gatt_char(
                protocol.control, SKY_ALLOW_ALL_100MS, response=True), 5)
            event('skygauge_subscription',interval_ms=SKY_INTERVAL_MS,channels='all_stock_9',
                  service=uuid16('1ff8'),control=uuid16('0002'))
        while client.is_connected:
            now = time.monotonic()
            values = telemetry.snapshot(now)
            publish(values,telemetry.status(now))
            event('skygauge_summary',throttle=('skygauge_summary',id(client)),
                  packets=telemetry.packets,malformed=telemetry.malformed,
                  channel_counts=dict(telemetry.counts),fresh_values=values,
                  fresh_count=len(values),transport='BLE',vehicle_link='unknown')
            last = telemetry.last_valid_at if telemetry.last_valid_at is not None else began
            if repair_at is not None:
                last = max(last,repair_at)
            if now-last >= silence_timeout:
                if repair_at is not None:
                    raise TimeoutError('SkyGauge BLE已连接，但遥测停止更新')
                event('skygauge_subscription_repair',silence_s=round(now-last,2))
                await asyncio.wait_for(client.stop_notify(protocol.rx),3)
                subscribed = False
                await asyncio.wait_for(client.start_notify(protocol.rx,notify),5)
                subscribed = True
                if protocol.control is not None:
                    await asyncio.wait_for(client.write_gatt_char(
                        protocol.control, SKY_ALLOW_ALL_100MS, response=True),5)
                repair_at = time.monotonic()
            await asyncio.sleep(.1)
        raise RuntimeError('SkyGauge 蓝牙连接已断开')
    finally:
        if subscribed and client.is_connected:
            try:
                await asyncio.wait_for(client.stop_notify(protocol.rx),3)
            except Exception:
                pass
        publish({},'SkyGauge BLE遥测已断开')

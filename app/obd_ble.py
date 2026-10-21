#!/usr/bin/env python3
"""Drive the AI Passport ELM327 BLE simulator from the Mi 4.

Supports known BLE ELM UART layouts, including separate receive/transmit
characteristics. The ESP32-C3 simulator uses FFE0/FFE1; commercial adapters
may instead use FFF0, 18F0 or FF12. Discovery selects the actual layout.

Usage:
    python3 obd_ble.py --scan
    python3 obd_ble.py --address 02:00:00:00:00:01
"""
import argparse
import asyncio
import sys

from bleak import BleakClient, BleakScanner
from gauge_ble_diagnostics import Trace, error as diagnostic_error

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

PIDS = {
    "rpm": ("010C", lambda b: ((b[0] << 8) | b[1]) / 4.0),
    "coolant": ("0105", lambda b: b[0] - 40.0),
    "speed": ("010D", lambda b: float(b[0])),
    "load": ("0104", lambda b: b[0] * 100.0 / 255.0),
    "throttle": ("0111", lambda b: b[0] * 100.0 / 255.0),
    "intake": ("010F", lambda b: b[0] - 40.0),
    "map": ("010B", lambda b: float(b[0])),
    "battery": ("0142", lambda b: ((b[0] << 8) | b[1]) / 1000.0),
    "oil": ("015C", lambda b: b[0] - 40.0),
}


async def scan(seconds=8.0):
    print("扫描 BLE 设备 %d 秒…" % int(seconds))
    devices = await BleakScanner.discover(timeout=seconds)
    found = []
    for device in devices:
        name = device.name or ""
        print("  %s  %s" % (device.address, name or "(no name)"))
        lower = name.lower()
        if "obd" in lower or "elm" in lower or "vl" in lower:
            found.append(device)
    if not found:
        print("没有发现名字像 OBD 的广播；上面列的是全部可见设备。")
    return found


class BleElm327:
    def __init__(self, address):
        self.address = address
        self.client = None
        self.buffer = bytearray()
        self.ready = asyncio.Event()
        self.protocol = None
        self.subscribed = False
        self.trace = None

    async def connect(self):
        from gauge_ble_protocol import select_protocol
        self.trace = Trace(self.address)
        self.client = BleakClient(self.address,timeout=25)
        try:
            await asyncio.wait_for(self.client.connect(),30)
            self.trace.mark('gatt_connected')
            self.trace.services(self.client.services)
            self.protocol = select_protocol(self.client.services)
            self.trace.protocol(self.protocol)
            if self.protocol.kind == 'elm':
                await self.client.start_notify(self.protocol.rx,self._on_notify)
                self.subscribed = True
                self.trace.mark('notify_subscribed')
            return self.client.is_connected
        except BaseException as exc:
            diagnostic_error('connect_error',exc,address=self.address)
            try:
                await asyncio.wait_for(self.disconnect(),3)
            except Exception:
                pass
            raise

    async def disconnect(self):
        if self.trace:
            self.trace.mark('disconnect',counts=self.trace.counts)
        if self.client and self.client.is_connected:
            try:
                if self.subscribed:
                    await self.client.stop_notify(self.protocol.rx)
            finally:
                self.subscribed = False
                await self.client.disconnect()

    def _on_notify(self, _sender, data):
        if self.trace:
            self.trace.packet('rx',data)
        self.buffer.extend(data)
        if b">" in self.buffer:
            self.ready.set()

    async def command(self, text, timeout=2.0):
        if not self.client or not self.client.is_connected:
            raise RuntimeError("BLE 未连接")
        self.buffer.clear()
        self.ready.clear()
        if not self.protocol or self.protocol.kind != 'elm':
            raise RuntimeError('此连接不是 ELM327 串口；禁止发送 AT/PID')
        if self.trace:
            self.trace.packet('tx',(text+'\r').encode())
        await self.client.write_gatt_char(self.protocol.tx,(text+'\r').encode(),
                                          response=self.protocol.response)
        try:
            await asyncio.wait_for(self.ready.wait(), timeout)
        except asyncio.TimeoutError:
            if self.trace:
                self.trace.mark('elm_prompt_timeout',command=text,buffer_hex=bytes(self.buffer[:256]).hex())
        raw = bytes(self.buffer).decode("ascii", "ignore")
        return [line.strip() for line in raw.replace("\r", "\n").split("\n")
                if line.strip() and line.strip() != ">"]

    async def read_pid(self, name):
        command, decode = PIDS[name]
        lines = await self.command(command)
        prefix = "41" + command[2:]
        for line in lines:
            squeezed = "".join(ch for ch in line if ch in "0123456789abcdefABCDEF").upper()
            if not squeezed.startswith(prefix) or len(squeezed) <= len(prefix):
                continue
            body = squeezed[len(prefix):]
            try:
                payload = [int(body[i:i + 2], 16) for i in range(0, len(body) - 1, 2)]
                return decode(payload)
            except (ValueError, IndexError):
                continue
        return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--address")
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--hold", type=float, default=0.0,
                        help="keep polling for this many seconds")
    args = parser.parse_args()

    if args.scan or not args.address:
        found = await scan(args.seconds)
        if not found:
            return 1
        address = found[0].address
        print("使用 %s" % address)
    else:
        address = args.address

    link = BleElm327(address)
    if not await link.connect():
        print("连接失败")
        return 1
    print("已连接 %s" % address)

    for line in await link.command("ATI"):
        print("ATI  ->", line)
    print("ATDP ->", await link.command("ATDP"))
    print("ATRV ->", await link.command("ATRV"))

    if args.hold > 0:
        import time
        end = time.monotonic() + args.hold
        while time.monotonic() < end:
            values = {}
            for name in ("rpm", "coolant", "oil", "speed", "throttle", "load", "map", "battery"):
                values[name] = await link.read_pid(name)
            print("  ".join("%s=%s" % (k, "-" if v is None else ("%.1f" % v))
                            for k, v in values.items()))
            await asyncio.sleep(0.5)
    else:
        for name in ("rpm", "coolant", "oil", "speed", "throttle", "load", "map", "battery"):
            print("%-9s %s" % (name, await link.read_pid(name)))

    await link.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""Local, bounded BLE gateway transport; only the gauge worker owns the OBD.

Root owns BlueZ peripheral registration. The unprivileged existing gauge BLE
worker owns the upstream connection and is either polling OR forwarding.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import pwd
import re
import socket
import struct
from elm_bridge_core import ByteRelay

SOCKET = '/run/mi4-elm/bridge.sock'
MAC = re.compile(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}')


def packet(kind, data=None, **fields):
    if data is not None:
        fields['data'] = base64.b64encode(data).decode('ascii')
    return (json.dumps(dict(kind=kind, **fields), separators=(',', ':'))+'\n').encode()


def unpack(line):
    if not line or len(line) > 8192:
        raise ValueError('IPC disconnected or oversized message')
    obj = json.loads(line)
    if not isinstance(obj, dict):
        raise ValueError('invalid IPC message')
    return obj


def payload(obj):
    value = base64.b64decode(obj.get('data', ''), validate=True)
    if not 1 <= len(value) <= 2048:
        raise ValueError('invalid IPC payload length')
    return value


class GatewayRelay(ByteRelay):
    def __init__(self, logger=lambda *a, **k: None):
        super().__init__()
        self.generation = 0
        self.writer = None
        self.server = None
        self.handlers = set()
        self.disconnect_requested = False
        self.upstream_address = ''
        self.logger = logger

    async def start(self, path=SOCKET, uid=None):
        self.uid = pwd.getpwnam('umeko').pw_uid if uid is None else uid
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        # A single systemd service owns this exact socket path.
        if self.path.exists():
            self.path.unlink()
        self.server = await asyncio.start_unix_server(self.accept, path, limit=8192)
        if uid is None:
            os.chown(path, 0, pwd.getpwnam('umeko').pw_gid)
        os.chmod(path, 0o660)

    def end_session(self):
        if self.writer is not None:
            self.disconnect_requested = True
        self.ready = False
        self.upstream_address = ''
        self.notifying = False
        self.generation += 1
        self.clear()
        if self.writer:
            self.writer.close()

    async def accept(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        active = False
        try:
            peer = writer.get_extra_info('socket')
            _pid, uid, _gid = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != self.uid or self.writer is not None:
                raise PermissionError('IPC peer rejected or upstream already owned')
            hello = unpack(await asyncio.wait_for(reader.readline(), 3))
            address = str(hello.get('address', '')).upper()
            if hello.get('kind') != 'ready' or not MAC.fullmatch(address):
                raise ValueError('invalid upstream handshake')
            if self.writer is not None:
                raise PermissionError('upstream ownership changed during handshake')
            self.writer = writer
            active = True
            self.generation += 1
            self.clear()
            self.ready = True
            self.upstream_address = address
            self.logger('ipc_upstream_ready', address=address, simulated=hello.get('simulated') is True)
            writer.write(packet('sky', connected=self.notifying))
            await writer.drain()
            while True:
                message = unpack(await reader.readline())
                if message.get('kind') != 'rx':
                    raise ValueError('invalid upstream message kind')
                self.receive(payload(message))
        except (Exception, asyncio.CancelledError) as exc:
            self.logger('ipc_upstream_closed', reason=type(exc).__name__)
        finally:
            if active and self.writer is writer:
                self.end_session()
                self.writer = None
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            self.handlers.discard(task)

    async def send(self, data):
        writer = self.writer
        if writer is None or not self.ready:
            raise ConnectionError('OBD uplink not ready')
        writer.write(packet('tx', data))
        await asyncio.wait_for(writer.drain(), 2)

    def subscribed(self):
        self.generation += 1
        if self.writer:
            self.writer.write(packet('sky', connected=True))

    async def close(self):
        self.end_session()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for task in list(self.handlers):
            task.cancel()
        await asyncio.gather(*list(self.handlers), return_exceptions=True)
        if self.path.exists():
            self.path.unlink()


# Adapter formatting/bus setup + read-only vehicle requests. No clear-DTC,
# ECU reset, security access, write-data, routines or arbitrary CAN payloads.
AT = re.compile(r'AT(?:Z|WS|D|I|@1|@2|RV|DP|DPN|PC|AR|AL|NL|MA|MR|MT|'
                r'[ELSH][01]|AT[012]|SP[0-9A-C]|TP[0-9A-C]|ST[0-9A-F]{2}|'
                r'CAF[01]|CFC[01]|CEA(?:[0-9A-F]{2})?|CRA(?:[0-9A-F]{3}|[0-9A-F]{8})?|'
                r'SH(?:[0-9A-F]{3}|[0-9A-F]{8})|(?:CF|CM)(?:[0-9A-F]{3}|[0-9A-F]{8})|'
                r'FCSH(?:[0-9A-F]{3}|[0-9A-F]{8})|FCSD[0-9A-F]{2,10}|FCSM[012])')
READ = re.compile(r'(?:01(?:[0-9A-F]{2}){1,6}|22[0-9A-F]{4}|09[0-9A-F]{2}|03|07|0A)(?:[1-6])?')


def raw_read(command):
    if not re.fullmatch('[0-9A-F]{4,16}', command) or len(command)%2:
        return False
    data = bytes.fromhex(command)
    for offset in (0,1):  # ordinary / extended-addressing ISO-TP single frame
        if len(data) > offset and 1 <= data[offset] <= 7:
            count = data[offset]
            body = data[offset+1:offset+1+count]
            if len(body) == count and READ.fullmatch(body.hex().upper()):
                return True
    return False


class CommandFramer:
    def __init__(self):
        self.buffer = bytearray()
        self.previous = None
        self.caf0 = False

    def acknowledge(self, command, reply):
        if command in ('ATZ','ATWS','ATD'):
            self.caf0 = False
        elif command in ('ATCAF0','ATCAF1') and re.search(rb'(?:^|[\r\n])\s*OK\s*(?:[\r\n>]|$)', reply):
            self.caf0 = command == 'ATCAF0'

    def feed(self, data):
        result = []
        for c in data:
            if c == 10:
                continue
            if c == 13:
                raw = bytes(self.buffer)+b'\r'
                self.buffer.clear()
                cmd = raw[:-1].decode('ascii').replace(' ', '').upper()
                if not cmd:
                    if self.previous is None:
                        continue
                    cmd = self.previous
                if not (AT.fullmatch(cmd) or READ.fullmatch(cmd) or (self.caf0 and raw_read(cmd))):
                    raise ValueError('blocked non-read-only ELM command: '+cmd[:20])
                self.previous = cmd
                result.append((raw, cmd))
            elif 32 <= c <= 126:
                self.buffer.append(c)
                if len(self.buffer) > 128:
                    raise ValueError('ELM command too long')
            else:
                raise ValueError('non-ASCII ELM command')
        return result

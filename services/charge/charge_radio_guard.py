"""Durable, Bluetooth-only recovery journal for an interrupted charging mode.

Never enables a radio that was already disabled before charging. No firmware,
pairing, Wi-Fi or boot writes. Call recover only outside active charging mode.
"""
import json
import os
from pathlib import Path
import re
import time

class ChargeRadioGuard:
    def __init__(self, journal='/var/lib/obd-charge/radio-restore.json',
                 rfkill='/sys/class/rfkill', settle_seconds=2, clock=time.monotonic):
        self.journal = Path(journal)
        self.rfkill = Path(rfkill)
        self.settle_seconds, self.clock = settle_seconds, clock
        self.seen = {}

    @staticmethod
    def identity(node):
        value = str((node / 'device').resolve())
        value = re.sub(r'/hci\d+$', '/hci*', value)
        return re.sub(r'remoteproc\d+', 'remoteproc*', value)

    def nodes(self):
        output = {}
        for node in self.rfkill.glob('rfkill*'):
            try:
                if (node / 'type').read_text().strip() == 'bluetooth':
                    identity = self.identity(node)
                    if identity in output:
                        raise ValueError('Ambiguous Bluetooth hardware identity')
                    output[identity] = node
            except FileNotFoundError:
                pass
        return output

    def sync_directory(self):
        fd = os.open(self.journal.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def save(self, radios):
        if self.journal.exists():
            self.recover()
            if self.journal.exists():
                raise ValueError('Previous Bluetooth recovery is still pending')
        records = []
        for name, old in radios.items():
            if not re.fullmatch(r'rfkill\d+', name) or type(old) is not int or old not in (0, 1):
                raise ValueError('Invalid Bluetooth snapshot')
            node = self.rfkill / name
            if (node / 'type').read_text().strip() != 'bluetooth':
                raise ValueError('Refuse non-Bluetooth radio')
            records.append(dict(identity=self.identity(node), soft=old))
        if not records:
            return
        self.journal.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.journal.with_name(self.journal.name + '.next')
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(dict(schema=1, radios=records), stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.journal)
        self.sync_directory()

    def recover(self):
        if not self.journal.exists():
            return True
        if self.journal.is_symlink() or self.journal.stat().st_size > 32768:
            raise ValueError('Invalid charging radio journal')
        data = json.loads(self.journal.read_text())
        if not isinstance(data, dict):
            raise ValueError('Invalid charging radio journal object')
        records = data.get('radios')
        if data.get('schema') != 1 or not isinstance(records, list) or not 1 <= len(records) <= 8:
            raise ValueError('Invalid charging radio journal schema')
        seen = set()
        for row in records:
            if (not isinstance(row, dict) or not isinstance(row.get('identity'), str)
                    or not 1 <= len(row['identity']) <= 8192 or row['identity'] in seen
                    or type(row.get('soft')) is not int or row['soft'] not in (0, 1)):
                raise ValueError('Invalid charging radio journal entry')
            seen.add(row['identity'])
        nodes = self.nodes()
        if any(row['identity'] not in nodes for row in records):
            return False  # Firmware may register HCI late; keep the original intent.
        now = self.clock()
        for row in records:
            self.seen.setdefault(row['identity'], now)
        if any(now < self.seen[row['identity']] + self.settle_seconds for row in records):
            return False  # Let systemd-rfkill finish its initial state replay.
        for row in records:
            soft = nodes[row['identity']] / 'soft'
            soft.write_text(str(row['soft']))
            if int(soft.read_text()) != row['soft']:
                raise OSError('Bluetooth recovery readback mismatch')
        self.journal.unlink()
        self.sync_directory()
        print('CHARGE_RADIO_RECOVERED', len(records), flush=True)
        return True

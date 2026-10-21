"""Release-only first boot. Never rewrites calibration or bootloader partitions."""
import os
from pathlib import Path
import re
import subprocess
import uuid

state = Path('/var/lib/mi4-sky')
state.mkdir(mode=0o700, parents=True, exist_ok=True)
marker = state / 'initialized'
if marker.exists():
    raise SystemExit(0)
root = subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip()
if not re.fullmatch(r'/dev/mmcblk\d+p\d+', root):
    raise SystemExit('Unexpected root block device; refusing resize')
actual = subprocess.check_output(['blkid', '-s', 'UUID', '-o', 'value', root], text=True).strip()
if actual != '93afcbbe-875f-49b0-83da-ee8193f20ca5':
    raise SystemExit('Unexpected root UUID; refusing resize')
subprocess.run(['/usr/sbin/resize2fs', root], check=True, timeout=240)
machine = Path('/etc/machine-id')
if not re.fullmatch('[a-f0-9]{32}', machine.read_text().strip()):
    machine.write_text(uuid.uuid4().hex + '\n')
for directory, mode in [('/var/lib/bluetooth', 0o700), ('/var/log', 0o755),
                        ('/var/tmp', 0o1777), ('/tmp', 0o1777), ('/root', 0o700)]:
    Path(directory).mkdir(mode=mode, parents=True, exist_ok=True)
    os.chmod(directory, mode)
os.sync()
marker.write_text('2026.10.21 clean image first boot completed\n')
os.chmod(marker, 0o600)
os.sync()

"""Generic root wrapper: each new installation binds its own Sky master MAC."""
import os
from pathlib import Path
import re
import subprocess
import sys

config = Path('/etc/mi4-sky/sky-peer.conf')
if os.geteuid() != 0:
    raise SystemExit('Run with sudo')
if len(sys.argv) == 3 and sys.argv[1] == 'bind':
    mac = sys.argv[2].upper()
    if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', mac):
        raise SystemExit('Invalid SkyGauge Bluetooth MAC')
    config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    config.write_text(mac + '\n')
    config.chmod(0o600)
    subprocess.run(['systemctl', 'restart', 'mi4-elm-advertiser.service'], check=True)
    print('Sky peer bound. Enable forwarding separately in the dashboard.')
elif len(sys.argv) == 2 and sys.argv[1] == 'run':
    mac = config.read_text().strip().upper()
    if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', mac):
        raise SystemExit('Invalid Sky peer config')
    os.execv('/usr/bin/python3', ['python3', '-u',
        '/home/umeko/desktop-offline/elm327_ble_bridge.py', '--ipc', '--sky-address', mac,
        '--legacy-advertising', '--seconds', '0'])
else:
    raise SystemExit('Usage: sudo mi4-sky-bind-sky bind 02:00:00:00:00:01')

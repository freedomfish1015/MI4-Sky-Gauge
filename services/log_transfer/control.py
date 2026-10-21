#!/usr/bin/python3
"""Exact sudo allowlist entry point. No user paths, shell or arbitrary units."""
import os
import subprocess
import sys

assert os.geteuid() == 0
if len(sys.argv) != 2 or sys.argv[1] not in ('start', 'stop'):
    raise SystemExit('Use start or stop')
subprocess.run(['/usr/bin/systemctl', sys.argv[1], 'obd-log-transfer.service'], check=True, timeout=12)

"""Explicit, hardware-free test selection; services are imported but not started."""
import argparse
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tests')]+[
 str(ROOT/'services'/name) for name in ('motion','power','charge','log_transfer','platform','bms','startup')]
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
os.environ['MI4_COMPAT_UPSTREAM']=str(ROOT/'vendor/obd_brz_gauge')

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--full',action='store_true',help='Also run tests needing Cairo/pygame/native PID library')
 args=p.parse_args()
 basic=['test_elm_bridge_core','test_gauge_ble_protocol','test_accel_autocenter',
        'test_charge_radio_guard','test_log_download','test_pairing','test_racechrono_export','test_log_redaction','test_packaging']
 extra=['test_gauge_compat','test_gauge_telemetry','test_gauge_tracks','test_gauge_settings',
        'test_elm_forward','test_elm_latency','test_trip_recording','test_gauge_power','test_mi4_gnss',
        'test_mi4_motion','test_mi4_qmi_sv','test_mi4_satellite_log','test_bundled_fastboot_repair']
 suite=unittest.defaultTestLoader.loadTestsFromNames(basic+(extra if args.full else []))
 return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())

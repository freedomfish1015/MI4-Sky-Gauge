"""Root-owned live binding of the fixed module, with native-driver fallback."""
from pathlib import Path
import subprocess
import sys
import time

DEVICE='fc4cf000.spmi:pm8941@0:battery@4000'
BUS=Path('/sys/bus/platform')
NODE=BUS/'devices'/DEVICE
NATIVE=BUS/'drivers/qcom-bms'
FIXED=BUS/'drivers/mi4-bms-fixed'
MODULE=Path('/usr/local/lib/mi4-bms-fixed/mi4_bms_fixed.ko')


def rollback():
    if (NODE/'driver').exists() and (NODE/'driver').resolve()==FIXED:
        (FIXED/'unbind').write_text(DEVICE)
    if Path('/sys/module/mi4_bms_fixed').exists():
        subprocess.run(['rmmod','mi4_bms_fixed'],check=True,timeout=5)
    (NODE/'driver_override').write_text('qcom-bms')
    if not (NODE/'driver').exists():
        (NATIVE/'bind').write_text(DEVICE)
    (NODE/'driver_override').write_text('\n')
    print('NATIVE_BMS_RESTORED',flush=True)


def main():
    if '--rollback' in sys.argv:
        rollback()
        return
    kernel=subprocess.check_output(['uname','-r'],text=True).strip()
    if kernel!='6.15.11-mi4-audio1':
        print('BMS fix skipped for unsupported kernel',kernel,flush=True)
        return
    for _ in range(100):
        if (NODE/'driver').exists():
            break
        time.sleep(.1)
    if (NODE/'driver').resolve()==FIXED:
        print('BMS_FIXED_ALREADY_ACTIVE',flush=True)
        return
    assert (NODE/'driver').resolve()==NATIVE,'Unexpected BMS binding'
    try:
        (NODE/'driver_override').write_text('mi4-bms-fixed')
        (NATIVE/'unbind').write_text(DEVICE)
        subprocess.run(['insmod',str(MODULE)],check=True,timeout=10)
        if not (NODE/'driver').exists():
            (FIXED/'bind').write_text(DEVICE)
        assert (NODE/'driver').resolve()==FIXED
        supply=Path('/sys/class/power_supply/bms')
        assert 0<=int((supply/'capacity').read_text())<=100
        assert 2500000<=int((supply/'voltage_ocv').read_text())<=4600000
        print('BMS_FIXED_READY', (supply/'uevent').read_text(),flush=True)
    except BaseException:
        rollback()
        raise


if __name__=='__main__': main()

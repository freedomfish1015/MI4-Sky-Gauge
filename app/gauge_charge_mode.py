"""Unprivileged charge-mode button; no shell commands or hardware writes."""
import json
from pathlib import Path
import socket
import time

SOCKET=Path('/run/mi4-charge-mode/control.sock')

class ChargeModeClient:
    def request(self,operation='enter'):
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as stream:
                stream.settimeout(1.5)
                stream.connect(str(SOCKET))
                stream.sendall(json.dumps({'operation':operation}).encode()+b'\n')
                return json.loads(stream.recv(1024))
        except (OSError,ValueError):
            return dict(ok=False,error='充电模式服务不可用，请稍后重试')

def handle_charge_tap(controls,now=None,client=None):
    now=time.monotonic() if now is None else now
    if now>=getattr(controls,'charge_confirm_until',0):
        controls.charge_confirm_until=now+6
        controls.message='再次点击充电模式：保存记录并熄屏，短按电源键恢复'
        return
    controls.charge_confirm_until=0
    result=(client or ChargeModeClient()).request('enter')
    if result.get('ok') is True:
        if controls.telemetry is not None:controls.telemetry.set_recording(False)
        controls.message='正在保存记录并进入充电模式…'
    else:
        controls.message=result.get('error','无法进入充电模式')

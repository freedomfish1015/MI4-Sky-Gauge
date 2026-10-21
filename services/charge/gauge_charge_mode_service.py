"""Fixed root charging workflow. No suspend, poweroff, PMIC or boot writes.

Kiosk/motion/gateway/BlueZ stop only for an explicit authenticated request.
Short power-key release or unplug restores only previously active services.
The power key is exclusively grabbed ONLY while in this mode, preventing
logind from interpreting the wake gesture as a shutdown request.
"""
import argparse
import fcntl
import grp
import json
import os
from pathlib import Path
import pwd
import select
import signal
import socket
import struct
import subprocess
import time
from charge_radio_guard import ChargeRadioGuard

DIRECTORY=Path('/run/mi4-charge-mode')
STATE=DIRECTORY/'state.json'
BACKLIGHT=Path('/sys/class/backlight/backlight/brightness')
POWER_KEY=Path('/dev/input/by-path/platform-fc4cf000.spmi-platform-fc4cf000.spmi:pm8941@0:pon@800:pwrkey-event')
UNITS=('obd-gauge-kiosk.service','mi4-motion.service','mi4-elm-advertiser.service','bluetooth.service')
MARKER=Path('/run/obd-gauge/boot-video.done')
CONTROL=Path('/home/umeko/.config/obd-gauge/motion-control.json')
MOTION_STATE=Path('/run/obd-motion/state.json')
EVENT=struct.Struct('llHHI') # native input_event: 16B armhf, 24B x86_64
EVIOCGRAB=0x40044590

class ChargeMode:
    """State transitions are injectable so tests never operate real hardware."""
    def __init__(self,backend,persist):
        self.backend,self.persist=backend,persist
        self.state={'phase':'normal'}

    def prepare(self):
        if self.state['phase']!='normal':raise ValueError('充电模式正在切换，请稍后')
        if self.backend.online() is not True:raise ValueError('请先连接充电线')
        self.backend.grab_key()
        self.pressed=False
        try:
            self.state=dict(phase='entering',**self.backend.snapshot())
            self.persist(self.state)
        except BaseException:
            self.backend.release_key();self.state={'phase':'normal'}
            raise

    def enter(self):
        assert self.state['phase']=='entering'
        try:
            self.backend.stop_recording()
            self.backend.block_radio(self.state)
            for unit in UNITS:
                if self.state['units'].get(unit):self.backend.stop(unit)
            self.backend.brightness(0) # after kiosk ExecStopPost restores light
            self.state['phase']='charging'
            self.persist(self.state)
        except BaseException:
            self.restore('进入失败，已恢复')
            raise

    def restore(self,reason='power-key'):
        if self.state['phase']=='normal':return
        self.state['phase']='restoring';self.persist(self.state)
        # Un-grab only after the power key's release was consumed.
        self.backend.restore(self.state)
        self.backend.release_key()
        self.state={'phase':'normal','reason':reason}
        self.persist(self.state)

    def key_event(self,event_type,code,value):
        if self.state['phase']!='charging':return False
        if event_type==1 and code==116:
            if value==1:self.pressed=True
            elif value==0 and getattr(self,'pressed',False):
                self.pressed=False
                self.restore('power-key')
                return True
        return False

    def tick(self):
        if self.state['phase']=='charging':
            if self.backend.online() is False:
                self.restore('unplug') # original 20s unplug dialog runs again
            else:self.backend.brightness(0)

class Platform:
    def __init__(self):
        self.radio_guard=ChargeRadioGuard()
        self.radio_retry_at=0
        self.key_fd=None
        self.key_bytes=b''
        account=pwd.getpwnam('umeko')
        self.uid,self.gid=account.pw_uid,account.pw_gid

    @staticmethod
    def command(*args,timeout=15):
        return subprocess.run(['/usr/bin/systemctl',*args],check=True,timeout=timeout)

    def online(self):
        known=[]
        for name in ('smbb-usbin','smbb-dcin'):
            try:known.append(int(Path('/sys/class/power_supply',name,'online').read_text())==1)
            except (OSError,ValueError):pass
        return True if any(known) else (False if known else None)

    def grab_key(self):
        if self.key_fd is not None:return
        fd=os.open(POWER_KEY,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            fcntl.ioctl(fd,EVIOCGRAB,1)
            while True:
                try:
                    if not os.read(fd,EVENT.size*16):break
                except BlockingIOError:break
        except BaseException:
            os.close(fd);raise
        self.key_fd=fd;self.key_bytes=b''

    def release_key(self):
        if self.key_fd is not None:
            try:fcntl.ioctl(self.key_fd,EVIOCGRAB,0)
            finally:os.close(self.key_fd);self.key_fd=None;self.key_bytes=b''

    def snapshot(self):
        radios={}
        for p in Path('/sys/class/rfkill').glob('rfkill*'):
            try:
                if (p/'type').read_text().strip()=='bluetooth':
                    radios[p.name]=int((p/'soft').read_text())
            except (OSError,ValueError):pass
        try:marker=MARKER.read_text()[:8192]
        except OSError:marker='{"status":"skip-on-charge-resume"}'
        return dict(brightness=int(BACKLIGHT.read_text()),
            units={unit:subprocess.run(['/usr/bin/systemctl','is-active','--quiet',unit]).returncode==0 for unit in UNITS},
            radios=radios,video_marker=marker,entered_at=time.time(),
            bluetooth_runtime_masked=Path('/run/systemd/system/bluetooth.service').is_symlink()
                and Path('/run/systemd/system/bluetooth.service').resolve()==Path('/dev/null'))

    def stop_recording(self):
        try:control=json.loads(CONTROL.read_text())
        except (OSError,ValueError):control={}
        if not isinstance(control,dict):raise ValueError('行程控制文件异常，已取消进入')
        control['record']=False
        temporary=CONTROL.with_name('.charge-mode-motion-control.tmp')
        with temporary.open('w') as stream:
            json.dump(control,stream);stream.flush();os.fsync(stream.fileno())
        os.chown(temporary,self.uid,self.gid)
        os.chmod(temporary,0o600)
        os.replace(temporary,CONTROL)
        # Give the daemon time to close/fsync the trip and UI to pair its LOG.
        deadline=time.monotonic()+2
        time.sleep(.4)
        while time.monotonic()<deadline:
            try:
                if json.loads(MOTION_STATE.read_text()).get('recording') is False:break
            except (OSError,ValueError):pass
            time.sleep(.1)
        time.sleep(.2)

    def stop(self,unit):
        assert unit in UNITS
        self.command('stop',unit,timeout=20)
        probe=subprocess.run(['/usr/bin/systemctl','is-active','--quiet',unit])
        if probe.returncode==0:raise RuntimeError('服务未停止: '+unit)

    def block_radio(self,state):
        # Save original intent outside /run BEFORE the temporary rfkill block.
        # systemd-rfkill otherwise persists that temporary block across reboot.
        self.radio_guard.save(state.get('radios',{}))
        # WirePlumber/DBus otherwise auto-activates BlueZ immediately after
        # stop. Runtime-only mask disappears on reboot and is removed on wake.
        if not state.get('bluetooth_runtime_masked',False):
            self.command('mask','--runtime','--now','bluetooth.service')
        for name in state.get('radios',{}):
            self.radio(name,1)

    def radio(self,name,blocked):
        assert name.startswith('rfkill') and name[6:].isdigit()
        node=Path('/sys/class/rfkill')/name
        if not node.exists():return # firmware may remove HCI on rfkill
        assert (node/'type').read_text().strip()=='bluetooth'
        (node/'soft').write_text(str(int(blocked)))

    def brightness(self,value):
        if int(BACKLIGHT.read_text())!=value:BACKLIGHT.write_text(str(value))

    def restore(self,state):
        if not state.get('bluetooth_runtime_masked',False):
            self.command('unmask','--runtime','bluetooth.service')
        for name,old in state.get('radios',{}).items():self.radio(name,old)
        self.radio_guard.recover()
        if state['units'].get('obd-gauge-kiosk.service'):
            MARKER.parent.mkdir(mode=0o700,exist_ok=True)
            os.chown(MARKER.parent,self.uid,self.gid)
            MARKER.write_text(state['video_marker'])
            os.chown(MARKER,self.uid,self.gid)
        active=[unit for unit in UNITS if state['units'].get(unit)]
        if active:self.command('--no-block','start',*active)
        # Resume directly to dashboard (preserved boot-video marker).
        deadline=time.monotonic()+10
        if state['units'].get('obd-gauge-kiosk.service'):
            while time.monotonic()<deadline:
                if subprocess.run(['/usr/bin/systemctl','is-active','--quiet','obd-gauge-kiosk.service']).returncode==0:break
                time.sleep(.2)
            time.sleep(2)
        self.brightness(state['brightness'])

    def recover_charge_radio(self):
        if time.monotonic()<self.radio_retry_at:return
        self.radio_retry_at=time.monotonic()+5
        try:self.radio_guard.recover()
        except (OSError,ValueError) as exc:
            print('CHARGE_RADIO_RECOVERY_PENDING',repr(exc),flush=True)

def publish(state):
    temporary=DIRECTORY/'state.next'
    temporary.write_text(json.dumps(state,ensure_ascii=False))
    temporary.chmod(0o644)
    os.replace(temporary,STATE)
    print('CHARGE_MODE',state['phase'],state.get('reason',''),flush=True)

def run():
    backend=Platform()
    mode=ChargeMode(backend,publish)
    DIRECTORY.mkdir(mode=0o755,parents=True,exist_ok=True)
    if STATE.exists():
        state=json.loads(STATE.read_text())
        if state.get('phase')!='normal':
            mode.state=state
            if state.get('phase')=='charging':
                try:backend.grab_key()
                except OSError:mode.restore('power-key-unavailable')
            else:mode.restore('service-recovery')
    path=DIRECTORY/'control.sock'
    path.unlink(missing_ok=True)
    running=True
    def stop(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(path));path.chmod(0o660);os.chown(path,0,backend.gid)
        server.listen(4);server.setblocking(False)
        publish(mode.state)
        try:
            while running:
                watching=[server]+([backend.key_fd] if backend.key_fd is not None else [])
                ready,_,_=select.select(watching,[],[],.5)
                if server in ready:
                    stream,_=server.accept()
                    with stream:
                        try:
                            stream.settimeout(.5)
                            _pid,uid,_gid=struct.unpack('3i',stream.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                            if uid not in (0,backend.uid):raise ValueError('未授权的请求')
                            operation=json.loads(stream.recv(256)).get('operation')
                            if operation=='status':stream.sendall(json.dumps(dict(ok=True,phase=mode.state['phase'])).encode());continue
                            if operation=='enter':mode.prepare()
                            elif operation!='restore':raise ValueError('不支持的操作')
                            stream.sendall(b'{"ok":true}\n')
                        except (OSError,ValueError) as exc:
                            stream.sendall(json.dumps(dict(ok=False,error=str(exc)),ensure_ascii=False).encode())
                            continue
                    try:
                        if operation=='enter':mode.enter()
                        else:mode.restore('usb-command')
                    except Exception as exc:
                        print('CHARGE_MODE_ERROR',repr(exc),flush=True)
                        raise # restart recovers from persisted transition state
                if backend.key_fd is not None and backend.key_fd in ready:
                    try:backend.key_bytes+=os.read(backend.key_fd,EVENT.size*16)
                    except BlockingIOError:pass
                    while backend.key_fd is not None and len(backend.key_bytes)>=EVENT.size:
                        event=EVENT.unpack(backend.key_bytes[:EVENT.size]);backend.key_bytes=backend.key_bytes[EVENT.size:]
                        if mode.key_event(*event[2:]):break
                mode.tick()
                if mode.state['phase']=='normal':backend.recover_charge_radio()
        finally:
            backend.release_key();path.unlink(missing_ok=True)
            # Never start services from SIGTERM during shutdown. State stays
            # in /run for a service restart; a full reboot starts normally.

if __name__=='__main__':
    assert os.geteuid()==0
    run()

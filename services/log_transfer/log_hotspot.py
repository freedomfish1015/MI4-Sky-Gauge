"""On-demand isolated Wi-Fi AP, DHCP and unprivileged read-only log download.

Does not enable NetworkManager, change routing/NAT, replace firmware, modify
stored station connections or start at boot. Owned changes are reversed.
"""
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

from log_download import Catalog

BASE = Path('/usr/local/lib/obd-log-transfer')
TOOLS = BASE / 'tools/usr/sbin'
RUN = Path('/run/obd-log-transfer')
CONFIG = Path('/var/lib/obd-log-transfer/config.json')
ADDRESS, PREFIX, PORT = '192.168.73.1', '192.168.73.1/24', 8787
IFACE, MAX_SECONDS = 'wlan0', 900
LIBENV = dict(os.environ, LD_LIBRARY_PATH=str(BASE / 'tools/usr/lib/arm-linux-gnueabihf'))
running = True


def command(*args, check=True):
    return subprocess.run(args, check=check, timeout=8, capture_output=True, text=True, env=LIBENV)


def write_json(name, value, mode=0o640):
    target = RUN / name
    temporary = RUN / ('.' + name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False))
    temporary.chmod(mode)
    os.replace(temporary, target)


def state(phase, message='', **fields):
    write_json('state.json', dict(phase=phase, message=message, updated=time.monotonic(), **fields))


def configuration():
    if not CONFIG.exists():
        CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        data = dict(ssid='mi4-sky', password=secrets.token_hex(6))
        fd = os.open(CONFIG, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream)
    data = json.loads(CONFIG.read_text())
    assert data['ssid'] in ('mi4-sky', 'SkyGauge-Mi4')
    assert len(data['password']) == 12 and all(ch in '0123456789abcdef' for ch in data['password'])
    # Keep the existing PSK; old configuration remains usable for rollback.
    data['ssid'] = 'mi4-sky'
    return data


def cleanup():
    # The snapshot is root-only. Never accept addresses, devices or shell
    # commands from the display/UI state file.
    origin = RUN / 'origin.json'
    if not origin.exists():
        return
    saved = json.loads(origin.read_text())
    command('/usr/bin/systemctl', 'stop', 'obd-log-download.service', check=False)
    if saved.get('added_address'):
        command('/usr/sbin/ip', 'address', 'del', PREFIX, 'dev', IFACE, check=False)
    if saved.get('changed_type'):
        command('/usr/sbin/ip', 'link', 'set', IFACE, 'down', check=False)
        command(str(TOOLS / 'iw'), 'dev', IFACE, 'set', 'type', 'managed', check=False)
        if saved.get('was_up'):
            command('/usr/sbin/ip', 'link', 'set', IFACE, 'up', check=False)
    origin.unlink(missing_ok=True)


def prepare():
    if Path('/proc/sys/net/ipv4/ip_forward').read_text().strip() != '0':
        raise RuntimeError('检测到已有网络转发，请先关闭现有路由共享后重试')
    link = command(str(TOOLS / 'iw'), 'dev', IFACE, 'link').stdout
    if 'Connected to' in link:
        raise RuntimeError('Wi-Fi 正连接其他网络，请先断开再开启热点')
    interfaces = command('/usr/bin/busctl', 'get-property', 'fi.w1.wpa_supplicant1',
                         '/fi/w1/wpa_supplicant1', 'fi.w1.wpa_supplicant1', 'Interfaces', check=False)
    if interfaces.returncode == 0 and interfaces.stdout.strip() != 'ao 0':
        raise RuntimeError('Wi-Fi 正由其他连接管理，请先断开原连接')
    addresses = json.loads(command('/usr/sbin/ip', '-j', '-4', 'address', 'show', 'dev', IFACE).stdout)
    if any(item.get('addr_info') for item in addresses):
        raise RuntimeError('Wi-Fi 已有 IPv4 配置，为保护现有网络未开启热点')
    info = json.loads(command('/usr/sbin/ip', '-j', 'link', 'show', 'dev', IFACE).stdout)[0]
    saved = dict(was_up='UP' in info.get('flags', []), changed_type=True, added_address=False)
    write_json('origin.json', saved, 0o600)
    command('/usr/sbin/ip', 'link', 'set', IFACE, 'down')
    command('/usr/sbin/ip', 'address', 'add', PREFIX, 'dev', IFACE)
    saved['added_address'] = True
    write_json('origin.json', saved, 0o600)
    command('/usr/sbin/ip', 'link', 'set', IFACE, 'up')


def qr_image(value, name):
    import qrcode
    qr = qrcode.QRCode(box_size=1, border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(value)
    qr.make(fit=True)
    target = RUN / name
    temporary = RUN / ('.' + name + '.tmp')
    qr.make_image(fill_color='black', back_color='white').save(temporary, format='PNG')
    temporary.chmod(0o640)
    os.replace(temporary, target)


def pairing_payload(data, session):
    # Application QR: no system/admin credentials or arbitrary remote endpoints.
    return json.dumps(dict(kind='skygauge-log', v=1, ssid=data['ssid'],
        password=data['password'], host=ADDRESS, port=PORT, token=session['token']),
        separators=(',', ':'))


def main():
    global running
    assert os.geteuid() == 0
    if sys.argv[1:] == ['--cleanup']:
        cleanup()
        return
    assert len(sys.argv) == 1
    children, phase, error = [], 'off', ''
    try:
        state('starting', '正在准备热点…')
        data = configuration()
        prepare()
        config = RUN / 'hostapd.conf'
        config.write_text('\n'.join([
            'interface=' + IFACE, 'driver=nl80211', 'ssid=' + data['ssid'],
            'hw_mode=g', 'channel=6', 'country_code=CN', 'ieee80211d=1',
            'wmm_enabled=1', 'ieee80211n=1', 'auth_algs=1', 'wpa=2',
            'wpa_key_mgmt=WPA-PSK', 'rsn_pairwise=CCMP',
            'wpa_passphrase=' + data['password'], 'ctrl_interface=' + str(RUN / 'hostapd'), '']))
        config.chmod(0o600)
        hostapd = subprocess.Popen([str(TOOLS / 'hostapd'), str(config)], env=LIBENV)
        children.append(hostapd)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not running:
                return
            if hostapd.poll() is not None:
                raise RuntimeError('热点启动失败，请查看本机热点服务日志')
            status = command(str(TOOLS / 'hostapd_cli'), '-p', str(RUN / 'hostapd'), '-i', IFACE, 'status', check=False)
            if 'state=ENABLED' in status.stdout:
                break
            time.sleep(.2)
        else:
            raise RuntimeError('热点未就绪，请稍后重试')
        dhcp_config = RUN / 'dnsmasq.conf'
        dhcp_config.write_text('\n'.join([
            'interface=' + IFACE, 'bind-interfaces', 'port=0',
            'dhcp-range=192.168.73.20,192.168.73.60,255.255.255.0,1h',
            'dhcp-option=3', 'dhcp-option=6', 'dhcp-authoritative',
            'leasefile-ro', 'user=nobody', 'group=nogroup', 'pid-file=', '']))
        dhcp_config.chmod(0o600)
        dnsmasq = subprocess.Popen([str(TOOLS / 'dnsmasq'), '--keep-in-foreground',
                                   '--conf-file=' + str(dhcp_config)], env=LIBENV)
        children.append(dnsmasq)
        session = dict(address=ADDRESS, port=PORT, token=secrets.token_urlsafe(24))
        write_json('session.json', session)
        url = 'http://%s:%d/s/%s/' % (ADDRESS, PORT, session['token'])
        qr_image(pairing_payload(data, session), 'pairing.png')
        command('/usr/bin/systemctl', 'start', 'obd-log-download.service')
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for attempt in range(30):
            try:
                with opener.open(url + 'api/files', timeout=1) as response:
                    json.load(response)
                break
            except OSError:
                if attempt == 29: raise RuntimeError('下载服务未就绪')
                time.sleep(.1)
        began = time.monotonic()
        while running and time.monotonic() - began < MAX_SECONDS:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('热点服务已退出，请关闭后重新开启')
            if command('/usr/bin/systemctl', 'is-active', '--quiet', 'obd-log-download.service', check=False).returncode:
                raise RuntimeError('下载服务已退出，请重新开启')
            files = Catalog().files()
            stations = command(str(TOOLS / 'iw'), 'dev', IFACE, 'station', 'dump', check=False).stdout.count('Station ')
            state('ready', '在 mi4-sky 配套小程序内扫码连接并下载', ssid=data['ssid'],
                  password=data['password'], url=url, stations=stations, files=len(files),
                  bytes=sum(row['size'] for row in files), expires=began + MAX_SECONDS)
            for _ in range(10):
                if not running: break
                time.sleep(.5)
    except Exception as exc:
        phase, error = 'error', str(exc)[:180]
        print('LOG_HOTSPOT_ERROR: ' + error, flush=True)
    finally:
        command('/usr/bin/systemctl', 'stop', 'obd-log-download.service', check=False)
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=4)
                except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=2)
        cleanup()
        for name in ('session.json', 'wifi.png', 'download.png', 'pairing.png', 'hostapd.conf', 'dnsmasq.conf'):
            (RUN / name).unlink(missing_ok=True)
        state(phase, error or '热点已关闭')


def stop(signum, frame):
    global running
    running = False


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    main()

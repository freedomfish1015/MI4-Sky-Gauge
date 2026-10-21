"""Touch settings and read-only BLE PID profiles; no shell/driver changes."""
import asyncio
import copy
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from gauge_windows import DEFAULT_WINDOWS, WINDOW_NAMES, data_types, normalize_windows
from gauge_ble_diagnostics import event as diagnostic_event, error as diagnostic_error

KEYS = ('rpm', 'coolant', 'oil', 'speed', 'battery')
TAB_TOP, TAB_HEIGHT = 42, 28
PID_TOP, PID_BOTTOM, PID_ROW = 82, 326, 52
BLE_TOP, BLE_BOTTOM, BLE_ROW = 166, 310, 44
STANDARD = {
    'rpm': dict(command='010C', bytes=2, scale=0.25, offset=0),
    'coolant': dict(command='0105', bytes=1, scale=1, offset=-40),
    'oil': dict(command='015C', bytes=1, scale=1, offset=-40),
    'speed': dict(command='010D', bytes=1, scale=1, offset=0),
    'battery': dict(command='0142', bytes=2, scale=0.001, offset=0),
}


def validate_profile(raw):
    profile = dict(id=str(raw['id']), name=str(raw['name'])[:28],
                   description=str(raw.get('description', '自定义只读 PID'))[:48], pids={})
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}', profile['id']):
        raise ValueError('无效数据包 ID')
    for key in KEYS:
        item = raw['pids'].get(key)
        if item is None:
            continue
        cmd = str(item['command']).upper()
        if not re.fullmatch(r'(01[0-9A-F]{2}|22[0-9A-F]{4})', cmd):
            raise ValueError('仅允许 Mode 01 / 22 只读查询')
        size = item['bytes']
        if type(size) is not int or not 1 <= size <= 4:
            raise ValueError('PID 字节数应为 1–4')
        scale, offset = float(item['scale']), float(item.get('offset', 0))
        if not all(math.isfinite(v) and abs(v) < 1e6 for v in (scale, offset)):
            raise ValueError('无效换算系数')
        profile['pids'][key] = dict(command=cmd, bytes=size, scale=scale, offset=offset)
    if 'rpm' not in profile['pids']:
        raise ValueError('数据包需要包含 rpm')
    return profile


def profiles_in(directory):
    standard = dict(id='standard', name='标准 OBD-II',
                    description='通用标准 PID · 不支持的项目显示 --', pids=STANDARD)
    bmw = copy.deepcopy(standard)
    bmw.update(id='bmw-g-sim', name='BMW G 模拟器',
               description='仅已验证 ESP32 模拟器 · 非实车适配保证')
    bmw['pids']['oil'] = dict(command='224402', bytes=2, scale=0.75, offset=-48)
    profiles = [validate_profile(standard), validate_profile(bmw)]
    for path in sorted(Path(directory).glob('*.json'))[:24]:
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            if str(raw.get('schema', '')).startswith('skygauge.vehicle/'):
                from gauge_compat import Vehicle
                with Vehicle(raw) as native:
                    report = native.report
                item = dict(id=raw['id'], name=raw['name'],
                            description='原格式车型包 · %d 信号 · rev %d' % (report['signals'], raw['rev']),
                            _native_profile=raw)
            else:
                item = validate_profile(raw)
            if item['id'] not in {p['id'] for p in profiles}:
                profiles.append(item)
        except Exception as exc:
            print('Ignored PID profile %s: %s' % (path.name, exc), flush=True)
    return profiles


def decode(lines, item):
    cmd = item['command']
    prefix = ('41' if cmd.startswith('01') else '62') + cmd[2:]
    for line in lines:
        text = ''.join(str(line).split()).upper().rstrip('>')
        if not text.startswith(prefix):
            continue
        body = text[len(prefix):len(prefix) + item['bytes'] * 2]
        if len(body) == item['bytes'] * 2 and re.fullmatch(r'[0-9A-F]+', body):
            return int(body, 16) * item['scale'] + item['offset']
    return None


class Config:
    def __init__(self, directory=None, address=None):
        self.directory = Path(directory or Path.home() / '.config/obd-gauge')
        self.path = self.directory / 'settings.json'
        self.profiles = profiles_in(self.directory / 'pid-profiles')
        self.data = dict(profile='standard', address=address or '', enabled=bool(address),
                         windows=list(DEFAULT_WINDOWS))
        raw = {}
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(raw, dict):
                raise ValueError('settings must be an object')
            if raw.get('profile') in {p['id'] for p in self.profiles}:
                self.data['profile'] = raw['profile']
            if re.fullmatch(r'([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', str(raw.get('address', ''))):
                self.data['address'] = raw['address'].upper()
            if type(raw.get('enabled')) is bool:
                self.data['enabled'] = raw['enabled']
            if type(raw.get('brightness')) in (int, float) and math.isfinite(raw['brightness']):
                self.data['brightness'] = max(5, min(100, round(raw['brightness'])))
            self.data['windows'] = list(normalize_windows(raw.get('windows')))
        except (OSError, ValueError, TypeError):
            pass
        raw = raw if isinstance(raw,dict) else {}
        old_mode = raw.get('connection_mode', 'direct')
        self.data['connection_mode'] = 'direct'
        self.data['connections'] = {}
        saved = raw.get('connections',{})
        for mode in ('direct',):
            item = saved.get(mode,{}) if isinstance(saved,dict) else {}
            item = item if isinstance(item,dict) else {}
            address_value = str(item.get('address',''))
            self.data['connections'][mode] = dict(
                address=address_value.upper() if re.fullmatch(r'([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',address_value) else '',
                enabled=item.get('enabled') is True)
        mode = self.data['connection_mode']
        if not isinstance(saved,dict) or mode not in saved:
            # Never migrate a Sky master MAC into the direct OBD target.
            self.data['connections'][mode] = (dict(address='', enabled=False) if old_mode == 'sky'
                else dict(address=self.data['address'],enabled=self.data['enabled']))
        self.data.update(self.data['connections'][mode])
        self.data['sky_forward'] = raw.get('sky_forward') is True
        self.data['simulator_address'] = str(raw.get('simulator_address', '')).upper()
        self.data['previous_obd_address'] = str(raw.get('previous_obd_address', '')).upper()

    def set_connection_mode(self, mode):
        if mode != 'direct':
            raise ValueError('unknown connection mode')
        old = self.data['connection_mode']
        self.data['connections'][old] = dict(address=self.data['address'],enabled=self.data['enabled'])
        self.data['connection_mode'] = mode
        self.data.update(self.data['connections'][mode])

    @property
    def profile(self):
        return next(p for p in self.profiles if p['id'] == self.data['profile'])

    def save(self):
        self.data['connections'][self.data['connection_mode']] = dict(
            address=self.data['address'],enabled=self.data['enabled'])
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(self.data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)


class Brightness:
    def __init__(self, directory='/sys/class/backlight/backlight'):
        self.path = Path(directory)

    def read(self):
        maximum = int((self.path / 'max_brightness').read_text())
        return round(int((self.path / 'brightness').read_text()) * 100 / maximum)

    def write(self, percent):
        maximum = int((self.path / 'max_brightness').read_text())
        value = max(1, round(maximum * max(5, min(100, percent)) / 100))
        (self.path / 'brightness').write_text(str(value))


class SettingsBleSource:
    """One BLE worker; configuration revisions trigger clean reconnects."""
    name = 'BLE'

    def __init__(self, config):
        self.lock = threading.Lock()
        # Kept so a caller that constructed this early (boot warmup) can
        # build matching controls without re-reading the settings file.
        self.config = config
        self.revision = 0
        self.values = {key: math.nan for key in KEYS}
        self.signals = {}
        self.window_sources = tuple(config.data.get('windows', DEFAULT_WINDOWS))
        self.status = '未连接'
        self.configure(config.data['address'], config.profile, config.data['enabled'],
                       mode=config.data.get('connection_mode','direct'),
                       forward=config.data.get('sky_forward',False),
                       simulated=bool(config.data['address']) and config.data['address'] == config.data.get('simulator_address'))
        threading.Thread(target=lambda: asyncio.run(self._session()),
                         name='obd-ble', daemon=True).start()

    def configure(self, address, profile, enabled=True, mode='direct', forward=False, simulated=False):
        if mode != 'direct':
            raise ValueError('Only direct OBD connections are supported')
        diagnostic_event('configuration',address=address,profile=profile.get('id'),enabled=enabled,mode=mode)
        with self.lock:
            if not hasattr(self, 'window_sources'):
                self.window_sources = DEFAULT_WINDOWS
            self.address, self.profile, self.enabled = address, copy.deepcopy(profile), enabled
            self.mode = mode
            self.forward, self.simulated = bool(forward), bool(simulated)
            self.revision += 1
            self.values = {key: math.nan for key in KEYS}
            self.signals = {}
            self.status = '正在切换连接…' if enabled else '蓝牙已断开'

    def read(self):
        with self.lock:
            return dict(self.values)

    def connection_status(self):
        with self.lock:
            return self.status

    def read_signals(self):
        with self.lock:
            return dict(self.signals)

    def telemetry_snapshot(self):
        with self.lock:
            return dict(self.values), dict(self.signals), self.status, dict(
                address=self.address, profile=self.profile['id'], mode=self.mode,
                sky_forward=self.forward, simulated_source=self.simulated)

    def set_window_sources(self, sources):
        with self.lock:
            requested = tuple(normalize_windows(sources))
            if requested != self.window_sources:
                basic = {'obd.rpm', 'obd.coolant_temp', 'obd.oil_temp', 'obd.speed', 'obd.battery_voltage'}
                for key in set(requested).difference(basic):
                    self.signals[key] = None
            self.window_sources = requested

    async def _session(self):
        from obd_ble import BleElm327
        while True:
            with self.lock:
                revision, address, profile, enabled, mode, forward, simulated = (
                    self.revision, self.address, self.profile, self.enabled, self.mode,
                    self.forward, self.simulated)
            if not enabled or not address:
                await asyncio.sleep(0.2)
                continue
            link = BleElm327(address)
            async def connected_session():
                if forward:
                    from gauge_elm_forward import run_forward
                    from elm_passive import ALIASES
                    def publish_forward(signals, status):
                        with self.lock:
                            if revision == self.revision:
                                self.signals = dict(signals)
                                self.values = {key:signals.get(signal, math.nan) for key,signal in ALIASES.items()}
                                self.status = status
                    await run_forward(address, profile, publish_forward, simulated=simulated)
                    return
                if '_native_profile' in profile:
                    from gauge_compat_ble import run_vehicle_ble, ALIASES
                    def publish(signals, status):
                        with self.lock:
                            if revision == self.revision:
                                self.signals = dict(signals)
                                self.values = {key: signals.get(source) if signals.get(source) is not None
                                               else math.nan for key, source in ALIASES.items()}
                                self.status = status
                    await run_vehicle_ble(address, profile['_native_profile'], publish)
                    return
                await link.connect()
                if getattr(getattr(link,'protocol',None),'kind','elm') == 'skygauge':
                    from gauge_ble_protocol import run_skygauge
                    def publish_skygauge(signals,status):
                        aliases = dict(rpm='obd.rpm',speed='obd.speed',coolant='obd.coolant_temp',
                                       oil='obd.oil_temp',battery='obd.battery_voltage')
                        with self.lock:
                            if revision == self.revision:
                                self.signals = dict(signals)
                                self.values = {key:signals.get(signal,math.nan) for key,signal in aliases.items()}
                                self.status = status
                    await run_skygauge(link.client,link.protocol,publish_skygauge)
                    return
                await link.command('ATE0')
                await link.command('ATS0')
                with self.lock:
                    if revision == self.revision:
                        self.status = '已连接 ' + address
                print('BLE connected %s profile=%s' % (address, profile['id']), flush=True)
                rounds = 0
                while True:
                    for key in KEYS:
                        period = dict(rpm=1, coolant=12, oil=60, speed=30, battery=30)[key]
                        if rounds % period or key not in profile['pids']:
                            continue
                        item = profile['pids'][key]
                        value = decode(await link.command(item['command']), item)
                        with self.lock:
                            if revision == self.revision:
                                self.values[key] = value if value is not None else math.nan
                                canonical = dict(rpm='obd.rpm', coolant='obd.coolant_temp', oil='obd.oil_temp',
                                                 speed='obd.speed', battery='obd.battery_voltage')[key]
                                self.signals[canonical] = value
                    # Only query additional generic data when a window uses
                    # it. No extra polling or reconnect for unchanged defaults.
                    if rounds % 12 == 0:
                        extra = {
                            'obd.throttle': dict(command='0111', bytes=1, scale=100/255, offset=0),
                            'obd.load': dict(command='0104', bytes=1, scale=100/255, offset=0),
                            'obd.intake_temp': dict(command='010F', bytes=1, scale=1, offset=-40),
                            'obd.afr': dict(command='0144', bytes=2, scale=2*14.7/65536, offset=0),
                        }
                        with self.lock:
                            requested = set(self.window_sources)
                        for key in requested.intersection(extra):
                            value = decode(await link.command(extra[key]['command']), extra[key])
                            if key == 'obd.afr' and value is not None and not 8 <= value <= 22:
                                value = None
                            with self.lock:
                                if revision == self.revision:
                                    self.signals[key] = value
                    rounds += 1
                    await asyncio.sleep(0.02)
            task = asyncio.create_task(connected_session())
            retry_ticks = 20
            try:
                while not task.done():
                    with self.lock:
                        changed = revision != self.revision
                    if changed:
                        break
                    await asyncio.sleep(0.1)
                if task.done():
                    await task
            except Exception as exc:
                from gauge_ble_protocol import UnsupportedBleProtocol
                diagnostic_error('session_error',exc,address=address,profile=profile.get('id'))
                if isinstance(exc,UnsupportedBleProtocol):
                    retry_ticks = 200
                with self.lock:
                    if revision == self.revision:
                        self.status = (str(exc) if isinstance(exc,UnsupportedBleProtocol) else
                                       '服务发现超时，请确认设备的数据广播已开启' if isinstance(exc,TimeoutError) else
                                       '连接失败，稍后重试')
                        self.values = {key: math.nan for key in KEYS}
                        self.signals = {}
                print('BLE error: %r' % exc, flush=True)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                try:
                    await asyncio.wait_for(link.disconnect(), 3)
                except Exception:
                    pass
            # Interruptible retry delay, without starting overlapping clients.
            for _ in range(retry_ticks):
                with self.lock:
                    changed = revision != self.revision
                if changed:
                    break
                await asyncio.sleep(0.1)


def logical_point(nx, ny):
    return ny * 640, (1 - nx) * 360


class TouchSettings:
    def __init__(self, config, source, brightness=None, shutdown=None):
        self.config, self.source = config, source
        self.shutdown = shutdown
        self.brightness = brightness or Brightness()
        self.page, self.tab = 'gauge', 0
        self.telemetry = None
        self.track_view = None
        from gauge_motion import MotionClient
        self.motion = MotionClient()
        from gauge_log_transfer import TransferClient
        self.log_transfer = TransferClient()
        self.profile_scroll = 0.0
        self.window_slot = 0
        self.window_scroll = 0.0
        self.device_scroll = 0.0
        self.scroll_origin = 0.0
        self.scrolling = False
        self.start = None
        self.slider = False
        self.message = ''
        self.lock = threading.Lock()
        self.scanning = False
        self.devices = [('已保存的 OBD 设备', config.data['address'])] if config.data['address'] else []
        self.percent = 50
        self.pending_brightness = None
        self.last_brightness_write = 0
        if hasattr(self.source, 'set_window_sources'):
            self.source.set_window_sources(self.config.data['windows'])
        try:
            self.percent = self.brightness.read()
            if 'brightness' in config.data:
                self.set_brightness(config.data['brightness'], final=True)
        except OSError:
            self.message = '亮度接口暂不可用'

    def persist(self):
        try:
            self.config.save()
        except OSError:
            self.message = '保存失败：请检查存储空间和权限'

    def apply_connection(self):
        args = (self.config.data['address'], self.config.profile,self.config.data['enabled'])
        if isinstance(self.source,SettingsBleSource):
            self.source.configure(*args,mode=self.config.data['connection_mode'],
                                  forward=self.config.data.get('sky_forward', False),
                                  simulated=bool(self.config.data['address']) and self.config.data['address'] == self.config.data.get('simulator_address'))
        else:
            self.source.configure(*args)
        self.persist()

    def set_brightness(self, value, final=False):
        self.percent = max(5, min(100, round(value)))
        self.pending_brightness = self.percent
        if final or time.monotonic() - self.last_brightness_write >= 0.1:
            self.flush_brightness(final)

    def flush_brightness(self, final=False):
        if self.pending_brightness is None:
            return
        try:
            self.brightness.write(self.pending_brightness)
            self.config.data['brightness'] = self.pending_brightness
            self.message = ''
            if final:
                self.persist()
        except OSError:
            self.message = '无法调节亮度：接口权限或设备错误'
        self.pending_brightness = None
        self.last_brightness_write = time.monotonic()

    def scan(self):
        with self.lock:
            if self.scanning:
                return
            self.scanning = True
            self.message = '扫描中，请稍候…'
        def worker():
            try:
                diagnostic_event('scan_begin')
                from bleak import BleakScanner
                devices = asyncio.run(BleakScanner.discover(timeout=6))
                diagnostic_event('scan_result',devices=[dict(name=d.name,address=d.address) for d in devices])
                rows = sorted(((d.name or '未命名 BLE', d.address) for d in devices),
                              key=lambda row: ('obd' not in row[0].lower(), row[0]))
                with self.lock:
                    # Connected peripherals often stop advertising. Keep the
                    # saved target selectable even when a scan cannot see it.
                    saved = self.config.data['address']
                    if saved and not any(row[1] == saved for row in rows):
                        rows.insert(0, ('已保存的 OBD 设备', saved))
                    self.devices = rows
                    self.device_scroll = 0.0
                    self.message = '附近 %d 台 · 已保留保存的设备' % len(devices)
            except Exception as exc:
                diagnostic_error('scan_error',exc)
                with self.lock:
                    self.message = '扫描失败：请确认蓝牙已启用'
                print('BLE scan error: %r' % exc, flush=True)
            finally:
                with self.lock:
                    self.scanning = False
        threading.Thread(target=worker, name='ble-scan', daemon=True).start()

    def input(self, kind, x, y, stamp=None):
        now = time.monotonic() if stamp is None else stamp
        if kind == 'down':
            if self.start is not None:
                return
            self.start = (x, y, now)
            self.scroll_origin = (self.profile_scroll if self.tab == 0 else
                                  self.window_scroll if self.tab == 3 else self.device_scroll)
            self.scrolling = False
            self.slider = self.page == 'settings' and self.tab == 2 and 40 <= x <= 600 and 185 <= y <= 245
            if self.slider:
                self.set_brightness(5 + (x - 60) / 520 * 95)
        elif self.start is not None and kind in ('move', 'up'):
            sx, sy, started = self.start
            dx, dy = x - sx, y - sy
            top, bottom, row = ((PID_TOP, PID_BOTTOM, 44) if self.tab == 3 else
                                (PID_TOP, PID_BOTTOM, PID_ROW) if self.tab == 0
                                else (BLE_TOP, BLE_BOTTOM, BLE_ROW))
            in_list = (self.page == 'settings' and self.tab in (0, 1, 3) and
                       (226 if self.tab == 3 else 24) <= sx <= 616 and top <= sy < bottom)
            if in_list and (self.scrolling or (abs(dy) > 8 and abs(dy) > abs(dx))):
                self.scrolling = True
                with self.lock:
                    count = (len(self.config.profiles) if self.tab == 0 else
                             len(data_types(self.config.profile)) if self.tab == 3 else len(self.devices))
                    maximum = max(0, count * row - (bottom - top))
                    position = max(0, min(maximum, self.scroll_origin - dy))
                    if self.tab == 0:
                        self.profile_scroll = position
                    elif self.tab == 3:
                        self.window_scroll = position
                    else:
                        self.device_scroll = position
            if self.slider:
                self.set_brightness(5 + (x - 60) / 520 * 95, final=kind == 'up')
            if kind == 'up':
                if not self.slider and not self.scrolling:
                    if now - started < 1.8 and abs(dy) > 65 and abs(dx) < 60 and self.page in ('gauge', 'telemetry', 'route'):
                        if self.page == 'gauge':
                            self.page = 'telemetry' if dy > 0 else 'route'
                            self.message = ''
                        elif self.page == 'telemetry' and dy < 0:
                            self.page = 'gauge'
                        elif self.page == 'route' and dy > 0:
                            self.page = 'gauge'
                    elif self.page == 'route' and abs(dx) < 18 and abs(dy) < 18:
                        if 6 <= y <= 38 and x < 100:
                            self.page = 'gauge'
                        elif 6 <= y <= 38 and x >= 500:
                            try:
                                start_recording=not self.motion.read().get('recording',False)
                                self.motion.command(record=start_recording)
                                if start_recording and self.track_view is not None:
                                    self.track_view.tap(590,213)
                                self.message = ''
                            except OSError:
                                self.message = '轨迹记录控制写入失败'
                        elif self.track_view is not None:
                            self.track_view.tap(x,y)
                    elif self.page == 'telemetry' and abs(dx) < 18 and abs(dy) < 18:
                        if 6 <= y <= 39:
                            if x < 100:
                                self.page = 'gauge'
                            elif self.telemetry is not None and x >= 500:
                                if self.motion.read().get('recording') or self.telemetry.trip:
                                    try:
                                        self.motion.command(record=False)
                                        self.message = '正在停止 GPS 与行程 LOG'
                                    except OSError:
                                        self.message = '行程停止失败，请重试'
                                else:
                                    self.telemetry.set_recording(not self.telemetry.recording)
                            elif self.telemetry is not None and x >= 390:
                                self.telemetry.toggle_pause()
                    elif now - started < 1.8 and abs(dx) > 75 and abs(dy) < 60:
                        self.page = 'settings' if dx < 0 else 'gauge'
                        self.message = ''
                    elif abs(dx) < 18 and abs(dy) < 18 and self.page == 'settings':
                        self.tap(x, y)
                self.start, self.slider, self.scrolling = None, False, False

    def tap(self, x, y):
        if 458 <= x <= 544 and 6 <= y <= 36:
            from gauge_charge_mode import handle_charge_tap
            handle_charge_tap(self)
        elif 552 <= x <= 624 and 6 <= y <= 36:
            self.message = ('正在安全关机…' if self.shutdown and self.shutdown()
                            else '关机服务不可用，请稍后重试')
        elif 16 <= x <= 92 and 6 <= y <= 36:
            self.page = 'gauge'
        elif TAB_TOP <= y <= TAB_TOP + TAB_HEIGHT:
            for tab in range(5):
                if 24 + tab * 120 <= x <= 136 + tab * 120:
                    self.tab = tab
                    self.message = ''
        elif self.tab == 4:
            self.log_transfer.tap(x, y)
        elif self.tab == 0:
            if PID_TOP <= y < PID_BOTTOM and 24 <= x <= 616:
                position = y - PID_TOP + self.profile_scroll
                index = int(position // PID_ROW)
                if index < len(self.config.profiles) and position % PID_ROW < PID_ROW - 6:
                    self.config.data['profile'] = self.config.profiles[index]['id']
                    self.apply_connection()
                    self.message = '已保存 PID 数据包；正在重新连接'
        elif self.tab == 1:
            if 410 <= x <= 616 and 78 <= y <= 112:
                self.config.data['sky_forward'] = not self.config.data.get('sky_forward', False)
                self.apply_connection()
                self.message = ('Sky 发起查询 · 手机被动显示' if self.config.data['sky_forward']
                                else '已恢复手机直接轮询 OBD')
            elif 122 <= y <= 158 and x >= 496:
                self.scan()
            elif BLE_TOP <= y < BLE_BOTTOM and 24 <= x <= 616:
                with self.lock:
                    index = int((y - BLE_TOP + self.device_scroll) // BLE_ROW)
                    address = self.devices[index][1] if index < len(self.devices) else None
                if address:
                    self.config.data.update(address=address, enabled=True)
                    self.apply_connection()
                    self.message = '正在连接选中的设备…'
            elif 318 <= y <= 350:
                if x <= 210:
                    self.config.data['enabled'] = not self.config.data['enabled']
                    self.apply_connection()
        elif self.tab == 2 and 268 <= y <= 312:
            for i, value in enumerate((5, 25, 50, 75, 100)):
                if 40 + i * 114 <= x <= 144 + i * 114:
                    self.set_brightness(value, final=True)
        elif self.tab == 3:
            if 24 <= x <= 214 and PID_TOP <= y < PID_TOP + 4 * 56:
                if (y - PID_TOP) % 56 < 48:
                    self.window_slot = int((y - PID_TOP) // 56)
                    self.message = ''
            elif 226 <= x <= 616 and PID_TOP <= y < PID_BOTTOM:
                position = y - PID_TOP + self.window_scroll
                options = data_types(self.config.profile)
                index = int(position // 44)
                if index < len(options) and position % 44 < 40:
                    self.config.data['windows'][self.window_slot] = options[index][0]
                    if hasattr(self.source, 'set_window_sources'):
                        self.source.set_window_sources(self.config.data['windows'])
                    self.persist()
                    self.message = '已保存 · 右滑返回查看 · 读不到的数据为 --'

    def snapshot(self):
        with self.lock:
            return (self.tab, self.config.data['profile'], self.profile_scroll,
                    tuple(self.devices), self.device_scroll, self.scanning,
                    self.source.connection_status(), self.percent, self.message,
                    self.config.data['enabled'], self.config.data['address'],
                    tuple(self.config.data['windows']), self.window_slot, self.window_scroll,
                    self.log_transfer.signature() if self.tab == 4 else ())


def draw_settings_logo(gauge, cr, x, y, size):
    """Render the supplied PNG only in the settings header; cache native pixels."""
    import cairo
    path = Path(__file__).resolve().parent / 'assets/mi4-sky-settings-logo-20261021.png'
    pixels = max(1, round(size * 3))
    cached = getattr(gauge, '_settings_brand_logo', None)
    if cached is None or cached[0] != pixels:
        try:
            source = cairo.ImageSurface.create_from_png(str(path))
            # Original alpha bounds; omit only its transparent outer padding.
            left, top, right, bottom = 314, 537, 3938, 3294
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, pixels, pixels)
            render = cairo.Context(surface)
            scale = min((pixels - 8) / (right - left), (pixels - 8) / (bottom - top))
            render.translate((pixels - (right - left) * scale) / 2,
                             (pixels - (bottom - top) * scale) / 2)
            render.scale(scale, scale)
            render.set_source_surface(source, -left, -top)
            render.get_source().set_filter(cairo.FILTER_BEST)
            render.paint()
            del render, source  # Do not retain a 4252px image for a header icon.
        except (OSError, cairo.Error):
            surface = None
        cached = gauge._settings_brand_logo = (pixels, surface)
    cr.save()
    radius = 4
    cr.new_path()
    for cx, cy, angle in ((x+radius,y+radius,math.pi),
                          (x+size-radius,y+radius,1.5*math.pi),
                          (x+size-radius,y+size-radius,0),
                          (x+radius,y+size-radius,.5*math.pi)):
        cr.arc(cx, cy, radius, angle, angle + .5*math.pi)
    cr.close_path()
    cr.set_source_rgb(*gauge.theme['text'])  # White logo needs dark contrast.
    cr.fill()
    if cached[1] is not None:
        cr.translate(x, y)
        cr.scale(size / pixels, size / pixels)
        cr.set_source_surface(cached[1], 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BEST)
        cr.paint()
    cr.restore()


def paint_settings(gauge, controls, state):
    """Only called when UI state changes, not sixty Pango redraws/second."""
    cr = gauge.cr
    cr.save()
    cr.identity_matrix()
    cr.set_source_rgb(*gauge.theme['background'])
    cr.paint()
    gauge.apply_layout(cr)
    white, dim, blue = gauge.theme['text'], gauge.theme['dim'], gauge.theme['accent']
    (tab, selected, profile_scroll, devices, scroll, scanning, status, percent,
     message, enabled, address, windows, window_slot, window_scroll, motion_signature) = state
    def text(x, y, label, size=13, color=white, align='left'):
        gauge.text(cr, x, y, str(label), size, color, align=align)
    def box(x, y, w, h, label, active=False):
        gauge.rounded_card(cr, x, y, w, h, 8)
        if active:
            cr.set_source_rgb(*blue)
            cr.set_line_width(1.5)
            cr.rectangle(x + 2, y + 2, w - 4, h - 4)
            cr.stroke()
        text(x + w / 2, y + h / 2, label, 12, blue if active else white, 'center')
    def scrollbar(position, count, row, top, bottom):
        extent = bottom - top
        maximum = count * row - extent
        if maximum <= 0:
            return
        height = max(18, extent * extent / (count * row))
        y = top + max(0, min(maximum, position)) / maximum * (extent - height)
        cr.set_source_rgb(*blue)
        cr.rectangle(621, y, 3, height)
        cr.fill()
    box(16, 6, 76, 30, '‹ 返回')
    draw_settings_logo(gauge, cr, 106, 7, 28)
    text(290, 21, 'MI4 Sky Gauge', 15, white, 'center')
    box(458, 6, 86, 30, '充电模式')
    gauge.rounded_card(cr, 552, 6, 72, 30, 7)
    text(588, 21, '关机', 12, (.733, .133, .231), 'center')
    for i, title in enumerate(('PID 数据包', '蓝牙连接', '屏幕亮度', '窗口数据', 'LOG 数据传输')):
        box(24 + i * 120, TAB_TOP, 112, TAB_HEIGHT, title, tab == i)
    if tab == 0:
        cr.save()
        cr.rectangle(24, PID_TOP, 592, PID_BOTTOM - PID_TOP)
        cr.clip()
        first = int(profile_scroll // PID_ROW)
        for index in range(first, min(len(controls.config.profiles), first + 6)):
            profile = controls.config.profiles[index]
            y = PID_TOP + index * PID_ROW - profile_scroll
            if y >= PID_BOTTOM:
                break
            gauge.rounded_card(cr, 24, y, 592, PID_ROW - 6, 7)
            text(40, y + 14, ('● ' if profile['id'] == selected else '○ ') + profile['name'], 14,
                 blue if profile['id'] == selected else white)
            text(62, y + 34, profile['description'], 10, dim)
        cr.restore()
        scrollbar(profile_scroll, len(controls.config.profiles), PID_ROW, PID_TOP, PID_BOTTOM)
        text(24, 344, message or '上下滑动 · 点选即保存并重新连接', 11, dim)
        text(616, 344, '共 %d 个' % len(controls.config.profiles), 10, dim, 'right')
    elif tab == 1:
        text(24, 95, '直连 BLE OBD 适配器', 15, blue)
        forwarding = controls.config.data.get('sky_forward', False)
        box(410, 78, 206, 34, '向 Sky 转发：开' if forwarding else '向 Sky 转发：关', forwarding)
        text(24, 126, status[:42], 10, blue)
        text(24, 149, message[:52] or ('两端选择相同车型 · Sky 查询，手机被动显示' if forwarding else
                                     '选择 BLE OBD 适配器 · 仪表下滑查看实时 LOG'), 9, dim)
        box(496, 122, 120, 34, '扫描中…' if scanning else '扫描设备')
        cr.save()
        cr.rectangle(24, BLE_TOP, 592, BLE_BOTTOM - BLE_TOP)
        cr.clip()
        first = int(scroll // BLE_ROW)
        for index in range(first, min(len(devices), first + 6)):
            name, mac = devices[index]
            y = BLE_TOP + index * BLE_ROW - scroll
            if y >= BLE_BOTTOM:
                continue
            gauge.rounded_card(cr, 24, y, 592, 40, 8)
            text(38, y + 20, name[:26], 13, blue if mac == address else white)
            text(602, y + 20, mac, 11, dim, 'right')
        cr.restore()
        if not devices:
            text(320, 235, '点击“扫描设备”，选择附近的 BLE OBD 适配器', 13, dim, 'center')
        box(24, 318, 156, 32, '断开连接' if enabled else '重新连接')
        text(320, 334, '共 %d 台' % len(devices), 11, dim, 'center')
        text(616, 334, '上下滑动浏览', 11, dim, 'right')
        scrollbar(scroll, len(devices), BLE_ROW, BLE_TOP, BLE_BOTTOM)
    elif tab == 2:
        text(320, 156, '%d%%' % percent, 30, white, 'center')
        cr.set_line_width(8)
        cr.set_line_cap(1)
        cr.set_source_rgb(*gauge.theme['track'])
        cr.move_to(60, 215)
        cr.line_to(580, 215)
        cr.stroke()
        knob = 60 + (percent - 5) / 95 * 520
        cr.set_source_rgb(*blue)
        cr.move_to(60, 215)
        cr.line_to(knob, 215)
        cr.stroke()
        cr.arc(knob, 215, 13, 0, math.tau)
        cr.fill()
        for i, value in enumerate((5, 25, 50, 75, 100)):
            box(40 + i * 114, 268, 104, 44, '%d%%' % value, percent == value)
        text(320, 337, message or '最低保留 5% 亮度 · 松手自动保存', 12, dim, 'center')
    elif tab == 4:
        from gauge_log_transfer import paint as paint_transfer
        paint_transfer(gauge, controls.log_transfer)
    else:
        options = data_types(controls.config.profile)
        by_source = {item[0]: item for item in options}
        for i, title in enumerate(WINDOW_NAMES):
            y = PID_TOP + i * 56
            box(24, y, 190, 48, '', window_slot == i)
            text(36, y + 13, title, 10, dim)
            text(36, y + 33, by_source.get(windows[i], (None, windows[i]))[1], 13,
                 blue if window_slot == i else white)
        cr.save()
        cr.rectangle(226, PID_TOP, 390, PID_BOTTOM - PID_TOP)
        cr.clip()
        first = int(window_scroll // 44)
        for index in range(first, min(len(options), first + 7)):
            source, label, fmt, unit, key = options[index]
            y = PID_TOP + index * 44 - window_scroll
            if y >= PID_BOTTOM:
                break
            box(226, y, 390, 40, '', windows[window_slot] == source)
            text(240, y + 20, ('● ' if windows[window_slot] == source else '○ ') + label, 13,
                 blue if windows[window_slot] == source else white)
            text(602, y + 20, unit, 10, dim, 'right')
        cr.restore()
        scrollbar(window_scroll, len(options), 44, PID_TOP, PID_BOTTOM)
        text(24, 344, message or '先选左侧窗口，再选右侧数据 · 中央转速表保持不变', 10, dim)
    cr.restore()
    gauge.surface.flush()

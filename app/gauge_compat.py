"""Single-owner ctypes interface to unchanged 976106c rule/PID/ELM cores.

This module does not connect to Bluetooth, send commands or alter the system.
The caller supplies transport/time. Values are engineering units, not the
editor's legacy integer display encoding. None means invalid/stale, never 0.
"""
import ctypes as C
import json
import math
from pathlib import Path
import time

SOURCES = ('obd.rpm', 'obd.speed', 'obd.boost', 'obd.coolant_temp',
           'obd.oil_pressure', 'obd.gear', 'obd.battery_voltage', 'obd.oil_temp',
           'obd.afr', 'obd.throttle', 'obd.intake_temp', 'obd.load',
           'sys.obd_link', 'sys.role', 'sys.page_index', 'sys.rpm_flash', 'sys.uptime_s')


def encoded(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()


class Core:
    def __init__(self, library=None):
        if library is None:
            library = Path(__file__).parent / 'compat' / (
                'build-armhf' if C.sizeof(C.c_void_p) == 4 else 'build-host') / 'libmi4compat.so'
        self.lib = C.CDLL(str(library))
        specs = {
            'sg_free': ([C.c_void_p], None),
            'sg_rules_open': ([C.c_char_p, C.c_size_t, C.c_char_p], C.c_void_p),
            'sg_rules_close': ([C.c_void_p], None),
            'sg_rules_report': ([C.c_void_p], C.c_void_p),
            'sg_rules_reset': ([C.c_void_p], None),
            'sg_rules_tick': ([C.c_void_p, C.POINTER(C.c_double), C.c_uint64, C.c_uint64, C.c_double], C.c_void_p),
            'sg_vehicle_open': ([C.c_char_p, C.c_size_t, C.POINTER(C.c_void_p)], C.c_void_p),
            'sg_vehicle_close': ([C.c_void_p], None),
            'sg_vehicle_link': ([C.c_void_p, C.c_int, C.c_uint32], None),
            'sg_vehicle_rx': ([C.c_void_p, C.c_char_p, C.c_size_t, C.c_uint32], None),
            'sg_vehicle_run': ([C.c_void_p, C.c_uint32], C.c_uint),
            'sg_vehicle_command': ([C.c_void_p, C.c_char_p, C.c_size_t], C.c_int),
            'sg_vehicle_snapshot': ([C.c_void_p], C.c_void_p),
        }
        for name, (arguments, result) in specs.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = arguments, result

    def result(self, pointer):
        if not pointer:
            raise RuntimeError('Native core did not return a result')
        try:
            return json.loads(C.string_at(pointer))
        finally:
            self.lib.sg_free(pointer)


class Rules:
    def __init__(self, page, sources=SOURCES, core=None, strict=True):
        self.core = core or Core()
        self.sources = tuple(sources)
        if len(self.sources) > 64 or len(set(self.sources)) != len(self.sources):
            raise ValueError('Expected at most 64 unique source keys')
        if any(not isinstance(key, str) or not 1 <= len(key) <= 31 for key in self.sources):
            raise ValueError('Invalid source key')
        text = encoded(page)
        if len(text) > 262144:
            raise ValueError('Rule page too large')
        self.handle = self.core.lib.sg_rules_open(text, len(text), encoded(self.sources))
        if not self.handle:
            raise ValueError('Could not compile rule page')
        self.report = self.core.result(self.core.lib.sg_rules_report(self.handle))
        if strict and any(self.report[key] for key in (
                'rules_dropped', 'conditions_dropped', 'actions_dropped',
                'unknown_sources', 'unknown_targets', 'bad_values')):
            self.close()
            raise ValueError('Rule compatibility diagnostics: ' + str(self.report))

    def tick(self, values, elapsed_ms, changed=()):
        if not self.handle:
            raise RuntimeError('Rules closed')
        if not math.isfinite(elapsed_ms) or elapsed_ms < 0:
            raise ValueError('Invalid monotonic timestamp')
        numbers, invalid, changed_mask = [], 0, 0
        changed = set(changed)
        for i, key in enumerate(self.sources):
            value = values.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                invalid |= 1 << i
                value = math.nan
            numbers.append(value)
            if key in changed:
                changed_mask |= 1 << i
        array = (C.c_double * len(numbers))(*numbers)
        return self.core.result(self.core.lib.sg_rules_tick(
            self.handle, array, invalid, changed_mask, elapsed_ms))

    def reset(self):
        if self.handle:
            self.core.lib.sg_rules_reset(self.handle)

    def close(self):
        if getattr(self, 'handle', None):
            self.core.lib.sg_rules_close(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Vehicle:
    """Validated profile and upstream single-flight ELM state machine.

    link(True) starts initialization; run() yields (wait_ms, command_or_None).
    The transport appends CR, feeds every notify chunk into rx(), and never
    sends an independent ELM command while this engine owns the connection.
    """
    def __init__(self, profile, core=None):
        self.core = core or Core()
        self.started = time.monotonic()
        text = encoded(profile)
        if len(text) > 16384:
            raise ValueError('PID package exceeds 16 KiB')
        pointer = C.c_void_p()
        self.handle = self.core.lib.sg_vehicle_open(text, len(text), C.byref(pointer))
        self.report = self.core.result(pointer.value) if pointer.value else {'ok': False}
        if not self.handle:
            raise ValueError('PID package rejected: ' + str(self.report))

    def _now(self, now):
        if not self.handle:
            raise RuntimeError('Vehicle closed')
        if now is None:
            now = int((time.monotonic() - self.started) * 1000)
        if type(now) is not int or now < 0:
            raise ValueError('Expected unsigned monotonic milliseconds')
        return now & 0xffffffff

    def link(self, up, now_ms=None):
        self.core.lib.sg_vehicle_link(self.handle, bool(up), self._now(now_ms))

    def rx(self, data, now_ms=None):
        if not isinstance(data, bytes) or len(data) > 65536:
            raise ValueError('Expected a bounded notify bytes chunk')
        self.core.lib.sg_vehicle_rx(self.handle, data, len(data), self._now(now_ms))

    def run(self, now_ms=None):
        wait = self.core.lib.sg_vehicle_run(self.handle, self._now(now_ms))
        buffer = C.create_string_buffer(24)
        available = self.core.lib.sg_vehicle_command(self.handle, buffer, len(buffer))
        return wait, buffer.value.decode('ascii') if available else None

    def snapshot(self):
        if not self.handle:
            raise RuntimeError('Vehicle closed')
        return self.core.result(self.core.lib.sg_vehicle_snapshot(self.handle))

    def close(self):
        if getattr(self, 'handle', None):
            self.core.lib.sg_vehicle_close(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

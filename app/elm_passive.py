"""Conservative passive decoder. Never sends requests or changes forwarded bytes."""
import math
import re
import time

ALIASES = dict(rpm='obd.rpm', speed='obd.speed', coolant='obd.coolant_temp',
               oil='obd.oil_temp', battery='obd.battery_voltage')
STANDARD = {
    '010C': ('obd.rpm',2,.25,0), '010D': ('obd.speed',1,1,0),
    '0105': ('obd.coolant_temp',1,1,-40), '015C': ('obd.oil_temp',1,1,-40),
    '0142': ('obd.battery_voltage',2,.001,0), '0111': ('obd.throttle',1,100/255,0),
    '0104': ('obd.load',1,100/255,0), '010F': ('obd.intake_temp',1,1,-40),
    '0144': ('obd.afr',2,14.7/32768,0),
}


def frames(text):
    """Decode ordinary ELM payloads and headered single/multi-frame ISO-TP."""
    assembling = {}
    for line in text.upper().replace('>', '').splitlines():
        line = line.strip()
        if not line or ':' in line:
            # ELM numbered headerless long replies are intentionally not guessed.
            continue
        parts = line.split()
        ecu = None
        if len(parts) > 1 and len(parts[0]) in (3,8) and re.fullmatch('[0-9A-F]+', parts[0]):
            ecu = parts.pop(0)
            if parts and len(parts[0]) == 1:
                parts.pop(0)  # optional DLC
        compact = ''.join(parts)
        if not re.fullmatch('[0-9A-F]+', compact):
            continue
        if ecu is None and len(compact)%2 and len(compact) > 5:
            ecu, compact = compact[:3], compact[3:]
        if len(compact)%2:
            continue
        data = bytes.fromhex(compact)
        if not data:
            continue
        if data[0] >> 4 == 0 and data[0] <= len(data)-1:
            yield data[1:1+data[0]]
        elif ecu and len(data) >= 2 and data[0] >> 4 == 1:
            length = ((data[0]&15)<<8)+data[1]
            if 1 <= length <= 4095:
                assembling[ecu] = (length, bytearray(data[2:]), 1)
        elif ecu and data[0] >> 4 == 2 and ecu in assembling:
            length, joined, seq = assembling[ecu]
            if data[0]&15 != seq:
                del assembling[ecu]
                continue
            joined.extend(data[1:])
            if len(joined) >= length:
                yield bytes(joined[:length])
                del assembling[ecu]
            else:
                assembling[ecu] = length, joined, (seq+1)&15
        elif data[0] in (0x41,0x62):
            yield data
        elif len(data) >= 3 and 1 <= data[1] <= 7 and data[1] <= len(data)-2:
            yield data[2:2+data[1]]  # ISO-TP extended address + single frame


def rpn(tokens, data):
    stack = []
    for token in tokens[:96]:
        if isinstance(token, list):
            if token[0] == 'k':
                stack.append(float(token[1]))
            elif token[0] == 'A':
                stack.append(float(data[int(token[1])]))
            elif token[0] == 'R':
                offset, bits = int(token[1]), int(token[2])
                size = (bits+7)//8
                if len(data[offset:offset+size]) != size or not 1 <= bits <= 32:
                    raise ValueError('short RPN read')
                stack.append(float(int.from_bytes(data[offset:offset+size], 'little' if token[3]=='le' else 'big')))
            else:
                raise ValueError('unsupported RPN token')
        else:
            b, a = stack.pop(), stack.pop()
            if token == '+': value = a+b
            elif token == '-': value = a-b
            elif token == '*': value = a*b
            elif token == '/': value = a/b
            elif token == '%': value = a%b
            elif token == '&': value = int(a)&int(b)
            elif token == '|': value = int(a)|int(b)
            elif token == '>>' and 0 <= b <= 31: value = int(a)>>int(b)
            elif token == '<<' and 0 <= b <= 31: value = int(a)<<int(b)
            else: raise ValueError('unsupported RPN operation')
            stack.append(value)
    if len(stack) != 1 or not math.isfinite(stack[0]):
        raise ValueError('invalid RPN result')
    return stack[0]


class Passive:
    def __init__(self, profile):
        self.profile = profile
        self.latest = {}
        self.pending = None
        self.responses = 0

    def begin(self, cmd):
        self.pending = cmd

    def consume(self, raw, now=None):
        now = time.monotonic() if now is None else now
        cmd = self.pending
        self.pending = None
        self.responses += 1
        if cmd in ('ATZ','ATWS','ATD'):
            self.latest.clear()
        if not cmd:
            return
        text = raw.decode('ascii', errors='replace')
        if cmd == 'ATRV':
            match = re.search(r'(?m)^\s*(\d{1,2}\.\d+)\s*V\s*$', text)
            if match:
                self.latest['obd.battery_voltage'] = (float(match[1]), now)
            return
        native = self.profile.get('_native_profile', {})
        base = cmd[:4] if cmd.startswith('01') else cmd[:6]
        raw_sources = [item for signal in native.get('signals',[]) for item in signal.get('src',[])
                       if ''.join(str(item.get('raw','')).split()).upper() == cmd]
        if raw_sources:
            expects = {''.join(str(item.get('expect','')).split()).upper() for item in raw_sources}
            if len(expects) != 1:
                return
            expected = next(iter(expects))
            if not re.fullmatch(r'(?:41[0-9A-F]{2}|62[0-9A-F]{4})', expected):
                return
            prefix = bytes.fromhex(expected)
        elif re.fullmatch(r'(?:01[0-9A-F]{2}|22[0-9A-F]{4})', base):
            prefix = bytes.fromhex(('41' if base.startswith('01') else '62')+base[2:])
        else:
            return
        bodies = [v[len(prefix):] for v in frames(text) if v.startswith(prefix)]
        if not bodies:
            return
        # Multiple ECUs with different values are ambiguous: don't choose one.
        bodies = list(set(bodies))
        if len(bodies) != 1:
            return
        body = bodies[0]
        if native:
            for signal in native.get('signals', []):
                for item in signal.get('src', []):
                    matching = (''.join(str(item.get('raw','')).split()).upper() == cmd if raw_sources
                                else str(item.get('req','')).upper() == base)
                    if not matching or len(body) < item.get('len', 1):
                        continue
                    try:
                        value = rpn(item.get('rpn', []), body)
                        if any(not bounds[0] <= value <= bounds[1] for bounds in
                               (item.get('valid', [-math.inf, math.inf]), signal.get('valid', [-math.inf, math.inf]))):
                            continue
                        post = signal.get('post', {})
                        if 'clamp' in post:
                            value = max(post['clamp'][0], min(post['clamp'][1], value))
                        if 'zero_le' in post and value <= post['zero_le']:
                            value = 0
                        unit = signal.get('unit')
                        if unit == 'mV': value /= 1000
                        elif unit in ('kPa_rel', 'kPa'): value /= 100
                        self.latest[signal['id']] = (value, now)
                    except (IndexError, KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
                        pass  # unsupported decoder cannot damage raw forwarding
        else:
            if base in STANDARD:
                key, length, scale, offset = STANDARD[base]
                if len(body) >= length:
                    self.latest[key] = (int.from_bytes(body[:length], 'big')*scale+offset, now)
            for key, item in self.profile.get('pids', {}).items():
                if item['command'] == base and key in ALIASES and len(body) >= item['bytes']:
                    self.latest[ALIASES[key]] = (int.from_bytes(body[:item['bytes']], 'big')*item['scale']+item.get('offset',0), now)

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        return {key:value for key,(value,stamp) in self.latest.items()
                if now-stamp <= (3 if key in ('obd.rpm','obd.speed','obd.throttle','obd.load') else 15)}

"""Data bindings only: keep the Rei artwork and physical layout unchanged."""
import re

# source, label, format, engineering unit, existing dashboard alias
DATA_TYPES = (
    ('obd.battery_voltage', '电压', '%.1f', 'V', 'battery'),
    ('obd.coolant_temp', '水温', '%.0f', '°C', 'coolant'),
    ('obd.oil_temp', '油温', '%.0f', '°C', 'oil'),
    ('obd.speed', '时速', '%.0f', 'km/h', 'speed'),
    ('obd.rpm', '转速', '%.0f', 'rpm', 'rpm'),
    ('obd.gear', '档位', '%.0f', '', 'obd.gear'),
    ('obd.throttle', '节气门', '%.0f', '%', 'obd.throttle'),
    ('obd.load', '发动机负荷', '%.0f', '%', 'obd.load'),
    ('obd.intake_temp', '进气温度', '%.0f', '°C', 'obd.intake_temp'),
    ('obd.boost', '增压', '%.2f', 'bar', 'obd.boost'),
    ('obd.oil_pressure', '油压', '%.2f', 'bar', 'obd.oil_pressure'),
    ('obd.afr', '空燃比', '%.2f', 'AFR', 'obd.afr'),
)
DEFAULT_WINDOWS = tuple(item[0] for item in DATA_TYPES[:4])
WINDOW_NAMES = ('左上窗口', '右上窗口', '左下窗口', '右下窗口')
BY_SOURCE = {item[0]: item for item in DATA_TYPES}


def valid_source(key):
    return isinstance(key, str) and (key in BY_SOURCE or bool(re.fullmatch(r'veh\.[a-z0-9_]{1,27}', key)))


def normalize_windows(raw):
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return DEFAULT_WINDOWS
    return tuple(key if valid_source(key) else DEFAULT_WINDOWS[i] for i, key in enumerate(raw))


def data_types(profile=None):
    result = list(DATA_TYPES)
    seen = set(BY_SOURCE)
    for signal in (profile or {}).get('_native_profile', {}).get('signals', []):
        key = signal.get('id')
        if valid_source(key) and key not in seen and not signal.get('disabled'):
            result.append((key, signal.get('name', key)[:23], '%.0f', signal.get('unit', '')[:7], key))
            seen.add(key)
    return result


def card_layout(base_cards, windows, profile=None):
    table = {item[0]: item for item in data_types(profile)}
    cards = []
    for base, source in zip(base_cards, normalize_windows(windows)):
        _, label, fmt, unit, key = table.get(source, (source, source, '%.0f', '', source))
        cards.append((base[0], base[1], label, key, fmt, unit))
    return cards

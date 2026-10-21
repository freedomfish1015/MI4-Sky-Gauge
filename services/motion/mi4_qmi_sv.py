"""Bounded, borrowed C-array reader for libqmi LOC satellite indications.

Avoid converting GArray<plain C struct> to a list of GI boxed wrappers on the
older armhf GI stack. Only the public libqmi getter and public GArray layout
are used; no modem traffic, private Qmi output layout, frees or ownership changes.
"""
import ctypes
import math


class GArray(ctypes.Structure):
    _fields_ = [('data', ctypes.c_void_p), ('len', ctypes.c_uint)]


class Satellite(ctypes.Structure):
    _fields_ = [('valid_information', ctypes.c_uint32), ('system', ctypes.c_int),
                ('gnss_satellite_id', ctypes.c_uint16), ('health_status', ctypes.c_int),
                ('satellite_status', ctypes.c_int), ('navigation_data', ctypes.c_int),
                ('elevation_degrees', ctypes.c_float), ('azimuth_degrees', ctypes.c_float),
                ('signal_to_noise_ratio_bhz', ctypes.c_float)]


_getter = _glib = None


def read_satellites(output):
    global _getter, _glib
    import gi
    gi.require_version('Qmi', '1.0')
    from gi.repository import Qmi
    if not isinstance(output, Qmi.IndicationLocGnssSvInfoOutput):
        raise TypeError('not a LOC satellite indication')
    # Fail closed if package updates change the ABI. Do not dereference guessed
    # layouts. These field sizes/offsets come from this installed GI namespace.
    info = Qmi.IndicationLocGnssSvInfoOutputListElement.__info__
    expected = {name: getattr(Satellite, name).offset for name, _ in Satellite._fields_}
    actual = {field.get_name(): field.get_offset() for field in info.get_fields()}
    if info.get_size() != ctypes.sizeof(Satellite) or actual != expected:
        raise RuntimeError('libqmi satellite ABI mismatch')
    # PyGBoxed hashes its C address on this runtime; verify against its native
    # repr on EVERY invocation before passing it to the C getter. No offset into
    # a Python object is used. Keep output alive until all records are copied.
    address = hash(output)
    if address <= 0 or (' at 0x%x)' % address) not in repr(output):
        raise RuntimeError('unsupported PyGBoxed address representation')
    if _getter is None:
        lib = ctypes.CDLL('libqmi-glib.so.5')
        _getter = lib.qmi_indication_loc_gnss_sv_info_output_get_list
        _getter.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(GArray)),
                           ctypes.POINTER(ctypes.c_void_p)]
        _getter.restype = ctypes.c_int
        _glib = ctypes.CDLL('libglib-2.0.so.0')
        _glib.g_error_free.argtypes = [ctypes.c_void_p]
        _glib.g_error_free.restype = None
        _glib.g_array_get_element_size.argtypes = [ctypes.POINTER(GArray)]
        _glib.g_array_get_element_size.restype = ctypes.c_uint
    array = ctypes.POINTER(GArray)()
    error = ctypes.c_void_p()
    ok = _getter(address, ctypes.byref(array), ctypes.byref(error))
    if error.value:
        _glib.g_error_free(error)
    if not ok or not array:
        raise ValueError('satellite list TLV missing or rejected')
    n = array.contents.len
    if n > 255 or _glib.g_array_get_element_size(array) != ctypes.sizeof(Satellite):
        raise ValueError('invalid satellite array bounds/stride')
    if n and not array.contents.data:
        raise ValueError('NULL satellite array')
    raw = ctypes.string_at(array.contents.data, n*ctypes.sizeof(Satellite)) if n else b''
    return decode_records(raw)


def decode_records(raw):
    if len(raw) % ctypes.sizeof(Satellite) or len(raw) > 255*ctypes.sizeof(Satellite):
        raise ValueError('invalid satellite record length')
    details = []
    systems = {1: 'gps', 2: 'galileo', 3: 'sbas', 4: 'compass', 5: 'glonass'}
    statuses = {0: 'idle', 1: 'searching', 2: 'tracking'}
    for start in range(0, len(raw), ctypes.sizeof(Satellite)):
        sv = Satellite.from_buffer_copy(raw, start)
        mask = sv.valid_information
        record = {'valid_mask': mask}
        if mask & 1:
            record['system'] = systems.get(sv.system, 'unknown-%d' % sv.system)
        if mask & 2:
            record['id'] = sv.gnss_satellite_id
        if mask & 4:
            record['health'] = sv.health_status
        if mask & 8:
            record['status'] = statuses.get(sv.satellite_status, 'unknown')
        if mask & 16:
            record['navigation_data'] = sv.navigation_data
        for bit, name, value in ((32, 'elevation_deg', sv.elevation_degrees),
                                 (64, 'azimuth_deg', sv.azimuth_degrees),
                                 (128, 'snr_dbhz', sv.signal_to_noise_ratio_bhz)):
            if mask & bit and math.isfinite(value):
                record[name] = float(value)
        details.append(record)
    return details

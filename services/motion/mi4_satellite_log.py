"""Fresh, evidence-based satellite metadata for local trip recording."""
import time


def satellite_metadata(gps, now=None):
    now = time.monotonic() if now is None else now

    def fresh(at):
        return isinstance(at, (float, int)) and 0 <= now-at <= 3

    def system_name(name):
        return {'compass': 'beidou', 'bds': 'beidou'}.get(name, name)

    at = gps.get('satellite_report_at')
    sv_fresh = fresh(at) and 'satellite_details' in gps and not gps.get('satellite_report_error')
    details = gps.get('satellite_details', []) if sv_fresh else []
    observed, signalled, id_systems = {}, {}, {}
    for sv in details:
        name = sv.get('system')
        if not name:
            continue
        name = system_name(name)
        observed[name] = observed.get(name, 0)+1
        if sv.get('snr_dbhz', 0) > 0:
            signalled[name] = signalled.get(name, 0)+1
        if 'id' in sv:
            id_systems.setdefault(sv['id'], set()).add(name)
    used = gps.get('used_satellites') or {}
    used_known = bool(gps.get('fix') and fresh(gps.get('fix_at'))
                      and used.get('reported') and fresh(used.get('at')))
    ids = list(used.get('ids', [])) if used_known else []
    used_systems, unresolved = {}, []
    for sv_id in ids:
        names = id_systems.get(sv_id, set())
        if len(names) != 1:
            unresolved.append(sv_id)
        else:
            name = next(iter(names))
            used_systems[name] = used_systems.get(name, 0)+1
    # Do not guess a constellation from a PRN alone or a generic GN talker.
    return dict(schema=2, fix=bool(gps.get('fix') and fresh(gps.get('fix_at'))),
                sv_report_available=sv_fresh,
                sv_report_age_s=round(now-at, 3) if isinstance(at, (float, int)) else None,
                observed_systems=observed, signal_systems=signalled,
                satellites=details, used_ids_available=used_known, used_ids=ids,
                used_systems=used_systems, unresolved_used_ids=unresolved,
                used_systems_complete=used_known and not unresolved,
                nmea=[entry['sentence'] for entry in gps.get('satellite_nmea', [])
                      if fresh(entry.get('at'))],
                report_error=gps.get('satellite_report_error'))

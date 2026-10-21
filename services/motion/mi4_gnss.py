"""Keep one QRTR LOC client alive for both session and indications."""
import threading
import time


class Gnss:
    # The modem can leave a session "started" while the GNSS engine stops
    # emitting anything (seen 2026-10-19: session_status=in-progress, but no NMEA
    # for 14 minutes and satellites stuck at 0). Without this watchdog the
    # process keeps reporting "searching" forever and never reconnects.
    STALL_SECONDS = 45

    def __init__(self):
        import faulthandler
        faulthandler.enable()  # Native faults retain Python callback stacks in journal.
        self.state = {'status': 'starting', 'fix': False, 'satellites': 0}
        self.last_event = time.monotonic()
        self.thread = threading.Thread(target=self.run, daemon=True, name='mi4-gnss')
        self.thread.start()
        threading.Thread(target=self.watchdog, daemon=True, name='mi4-gnss-wd').start()

    def touch(self):
        self.last_event = time.monotonic()

    def watchdog(self):
        while True:
            time.sleep(5)
            loop = getattr(self, 'loop', None)
            if loop is None:
                continue
            idle = time.monotonic() - self.last_event
            if idle <= self.STALL_SECONDS:
                continue
            # Take the timestamp first: run_session() may already be rebuilding
            # and a second quit() must not abort the fresh session.
            self.touch()
            self.state['stalls'] = self.state.get('stalls', 0) + 1
            self.state.update(status='stalled', fix=False, idle_s=round(idle, 1))
            print('GNSS watchdog: no LOC event for %.0fs, rebuilding session' % idle,
                  flush=True)
            loop.quit()

    def run(self):
        while True:
            try:
                self.run_session()
            except Exception as exc:
                self.state.update(status='error', fix=False, error=str(exc))
            time.sleep(15)

    def run_session(self):
        self.touch()
        for key in ('satellite_details', 'systems', 'satellite_report_at',
                    'used_satellites', 'satellite_nmea'):
            self.state.pop(key, None)
        import gi
        gi.require_version('Qmi', '1.0')
        gi.require_version('Qrtr', '1.0')
        from gi.repository import Qmi, Qrtr, GLib
        self.Qmi, self.GLib = Qmi, GLib
        self.loop = GLib.MainLoop()

        def bus_ready(_source, result, *_args):
            try:
                self.bus = Qrtr.Bus.new_finish(result)
                node = self.bus.get_node(0)
                if node is None:
                    raise RuntimeError('modem QRTR node 0 unavailable')
                Qmi.Device.new_from_node(node, None, device_ready, None)
            except Exception as exc:
                self.fail(exc)

        def device_ready(_source, result, *_args):
            try:
                self.device = Qmi.Device.new_finish(result)
                self.device.open(Qmi.DeviceOpenFlags.NONE, 10, None, opened, None)
            except Exception as exc:
                self.fail(exc)

        def opened(device, result, *_args):
            try:
                device.open_finish(result)
                device.allocate_client(Qmi.Service.LOC, Qmi.CID_NONE, 10,
                                       None, allocated, None)
            except Exception as exc:
                self.fail(exc)

        def allocated(device, result, *_args):
            try:
                self.client = device.allocate_client_finish(result)
                self.client.connect('position-report', self.position)
                self.client.connect('nmea', self.nmea)
                self.client.connect('gnss-sv-info', self.satellites)
                req = Qmi.MessageLocRegisterEventsInput.new()
                req.set_event_registration_mask(
                    Qmi.LocEventRegistrationFlag.POSITION_REPORT |
                    Qmi.LocEventRegistrationFlag.GNSS_SATELLITE_INFO |
                    Qmi.LocEventRegistrationFlag.NMEA)
                self.client.register_events(req, 10, None, registered, None)
            except Exception as exc:
                self.fail(exc)

        def registered(client, result, *_args):
            try:
                client.register_events_finish(result).get_result()
                req = Qmi.MessageLocStartInput.new()
                req.set_session_id(7)
                req.set_fix_recurrence_type(Qmi.LocFixRecurrenceType(1))
                req.set_minimum_interval_between_position_reports(1000)
                self.client.start(req, 10, None, started, None)
            except Exception as exc:
                self.fail(exc)

        def started(client, result, *_args):
            try:
                client.start_finish(result).get_result()
                self.state.update(status='searching', session_started=True)
                print('GNSS continuous LOC session started', flush=True)
            except Exception as exc:
                self.fail(exc)

        Qrtr.Bus.new(2000, None, bus_ready, None)
        self.loop.run()

    def fail(self, exc):
        self.state.update(status='error', fix=False, error=str(exc))
        print('GNSS ERROR:', exc, flush=True)
        self.loop.quit()

    def nmea(self, _client, output):
        self.touch()
        self.state['nmea_at'] = time.monotonic()
        self.state['nmea_count'] = self.state.get('nmea_count', 0) + 1
        try:
            line = output.get_nmea_string()
        except Exception:
            return
        if line and 'GSV' in line:
            self._gsv(line)
        if line and line.startswith('$') and line[3:6] in ('GSV', 'GSA'):
            # Only satellite sentences, not coordinate-bearing GGA/RMC traces.
            self.state['satellite_nmea'] = (
                self.state.get('satellite_nmea', []) +
                [dict(at=time.monotonic(), sentence=line.strip()[:1024])])[-32:]

    def _gsv(self, line):
        """Record per-constellation satellite count and SNR from a GSV sentence.

        Talkers: GP=GPS, GL=GLONASS, BD/GB=BeiDou, GA=Galileo, GQ=QZSS.
        Kept small on purpose -- the gauge reads this from /run/obd-motion/state.json.
        """
        fields = line.split('*')[0].split(',')
        if len(fields) < 4:
            return
        talker = fields[0][1:3]
        found = {}
        for index in range(4, len(fields) - 3, 4):
            try:
                prn = int(fields[index])
                snr = int(fields[index + 3] or 0)
            except (ValueError, IndexError):
                continue
            if snr > 0:
                found[prn] = snr
        if not found:
            return
        table = self.state.setdefault('constellations', {})
        table[talker] = {'count': len(found),
                         'snr': sorted(found.values(), reverse=True)[:8]}

    def satellites(self, _client, output):
        self.touch()
        self.state['sv_indication_count'] = self.state.get('sv_indication_count', 0)+1
        try:
            from mi4_qmi_sv import read_satellites
            details = read_satellites(output)
            self.state['satellites'] = len(details)
            systems = {}
            for detail in details:
                name = detail.get('system')
                if name:
                    systems[name] = systems.get(name, 0) + 1
            self.state['systems'] = systems
            self.state['satellite_details'] = details
            self.state.pop('satellite_report_error', None)
        except Exception as exc:
            self.state['satellite_report_error'] = str(exc)
            print('GNSS SV decode error:', exc, flush=True)
        self.state['satellite_report_at'] = time.monotonic()

    def position(self, _client, output):
        self.touch()
        # Never retain an older fix's used-in-solution list if TLV is absent.
        self.state['used_satellites'] = dict(at=time.monotonic(), reported=False, ids=[])
        try:
            status = output.get_session_status()
            if status != self.Qmi.LocSessionStatus.SUCCESS:
                self.state.update(fix=False, status='searching',
                                  session_status=status.value_nick)
                return
            lat, lon = output.get_latitude(), output.get_longitude()
            stamp = output.get_utc_timestamp() / 1000
            accuracy = output.get_horizontal_uncertainty_circular()
            import math
            if not (all(math.isfinite(x) for x in (lat, lon, stamp, accuracy))
                    and -90 <= lat <= 90 and -180 <= lon <= 180
                    and stamp > 1577836800 and 0 < accuracy <= 100):
                self.state.update(fix=False, status='poor_accuracy')
                return
            report = dict(status='fixed', fix=True, latitude=lat, longitude=lon,
                          utc=stamp, accuracy_m=accuracy, fix_at=time.monotonic())
            try:
                ids = [int(sv) for sv in output.get_satellites_used()]
                report['used_satellites'] = dict(at=time.monotonic(), reported=True, ids=ids)
            except Exception:
                pass  # Optional TLV missing: unknown, not "GPS only".
            for field, method in [('speed_ms', 'get_horizontal_speed'),
                                  ('altitude_m', 'get_altitude_from_sealevel')]:
                try:
                    value = getattr(output, method)()
                    if math.isfinite(value):
                        report[field] = value
                except Exception:
                    pass
            self.state.update(report)
        except Exception as exc:
            self.state.update(fix=False, status='invalid_report', error=str(exc))

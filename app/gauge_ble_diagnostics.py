"""Bounded persistent BLE diagnostics; logging failures never stop the gauge."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import time
import traceback

_lock = threading.RLock()
_logger = None
_last = {}


def event(kind, *, throttle=None, interval=5, **fields):
    global _logger
    try:
        with _lock:
            now = time.monotonic()
            if throttle is not None:
                if now - _last.get(throttle, -1e9) < interval:
                    return
                if len(_last) > 256:
                    _last.clear()
                _last[throttle] = now
            if _logger is None:
                directory = Path(os.environ.get('OBD_BLE_LOG_DIR',
                    str(Path.home()/'.local/state/obd-gauge/diagnostics')))
                directory.mkdir(parents=True,exist_ok=True,mode=0o700)
                handler = RotatingFileHandler(directory/'bluetooth.jsonl',
                    maxBytes=1024*1024,backupCount=4,encoding='utf-8')
                _logger = logging.Logger('obd-ble-diagnostics')
                _logger.addHandler(handler)
            _logger.info(json.dumps(dict(time_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                monotonic_s=round(now,3),pid=os.getpid(),event=kind,**fields),
                ensure_ascii=False,default=str))
    except Exception:
        pass


def error(kind, exc, **fields):
    event(kind,error=repr(exc),traceback=''.join(traceback.format_exception(exc))[-6000:],**fields)


class Trace:
    def __init__(self,address):
        self.address=address
        self.session='%s-%x' % (os.getpid(),time.monotonic_ns())
        self.counts={}
        event('connect_begin',address=address,session=self.session)

    def mark(self,kind,**fields):
        event(kind,address=self.address,session=self.session,**fields)

    def packet(self,direction,data):
        count=self.counts.get(direction,0)+1
        self.counts[direction]=count
        # Preserve initialization, then sample each direction every five seconds.
        event('packet',throttle=None if count<=60 else (self.session,direction),
              address=self.address,session=self.session,direction=direction,
              count=count,length=len(data),hex=bytes(data[:256]).hex(),
              ascii=bytes(data[:256]).decode('ascii','replace'))

    def services(self,services):
        for service in services:
            self.mark('gatt_service',uuid=service.uuid,characteristics=[
                dict(uuid=c.uuid,handle=getattr(c,'handle',None),properties=list(c.properties))
                for c in service.characteristics])

    def protocol(self,protocol):
        self.mark('protocol_selected',protocol=protocol.kind,
                  rx=str(getattr(protocol.rx,'uuid',protocol.rx)),
                  tx=str(getattr(protocol.tx,'uuid',protocol.tx)),response=protocol.response)

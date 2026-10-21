"""Read-only, session-token protected LAN export. Never serve arbitrary paths."""
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import stat
import threading
from urllib.parse import unquote, urlsplit, quote
from racechrono_export import convert, header as telemetry_header

ROOTS = {'log': Path('/home/umeko/.local/state/obd-gauge/telemetry'),
         'track': Path('/var/lib/obd-motion/tracks')}
MAX_FILE = 128 * 1024 * 1024
STATE = Path('/run/obd-motion/state.json')
EXPORT_SLOTS = threading.BoundedSemaphore(1)


def allowed(kind, name):
    if '..' in name or '/' in name or '\\' in name or len(name) > 160:
        return False
    pattern = (r'telemetry-[A-Za-z0-9-]+\.jsonl' if kind == 'log' else
               r'telemetry-[A-Za-z0-9-]+\.racechrono\.csv' if kind == 'racechrono' else
               r'\d{8}T\d{6}Z-\d+\.(?:csv|gpx|gnss\.jsonl)' if kind == 'track' else None)
    return bool(pattern and re.fullmatch(pattern, name))


def active_trip():
    try:
        data = json.loads(STATE.read_text())
        return str(data.get('track', '')) if data.get('recording') else ''
    except (OSError, ValueError):
        return ''


class Catalog:
    def __init__(self, roots=None):
        self.roots = roots or ROOTS

    def open(self, kind, name):
        if not allowed(kind, name) or kind not in self.roots:
            raise FileNotFoundError('Not an exported log')
        directory = os.open(self.roots[kind], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= MAX_FILE:
            os.close(fd)
            raise FileNotFoundError('Not a bounded regular file')
        return fd, info

    def files(self):
        rows, trip = [], active_trip()
        for kind, directory in self.roots.items():
            try:
                candidates = list(directory.iterdir())
            except OSError:
                continue
            for path in candidates[:2000]:
                if not allowed(kind, path.name):
                    continue
                try:
                    fd, info = self.open(kind, path.name)
                    try:
                        metadata = telemetry_header(fd, info.st_size) if kind == 'log' else {}
                    finally:
                        os.close(fd)
                except (OSError, ValueError):
                    continue
                busy = bool(trip and kind == 'track' and path.name.startswith(trip + '.'))
                rows.append(dict(kind=kind, name=path.name, size=info.st_size,
                    modified=datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                    recording=busy))
                if kind == 'log' and metadata.get('schema') == 'mi4.telemetry/1':
                    rows.append(dict(kind='racechrono', name=path.name[:-6] + '.racechrono.csv', size=0,
                        generated=True, source_name=path.name, source_size=info.st_size,
                        format='racechrono-csv-v3', modified=rows[-1]['modified'],
                        recording=bool(trip and metadata.get('trip') == trip)))
        return sorted(rows, key=lambda row: row['modified'], reverse=True)[:1000]


def byte_range(header, size):
    if header is None:
        return 0, size
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
    if not match or not any(match.groups()) or size == 0:
        raise ValueError('Invalid range')
    left, right = match.groups()
    if not left:
        count = int(right)
        if count <= 0:
            raise ValueError('Invalid suffix')
        return max(0, size - count), size
    start = int(left)
    end = min(size, int(right) + 1) if right else size
    if start >= size or start >= end:
        raise ValueError('Unsatisfiable range')
    return start, end


def snapshot_size(fd, name, size):
    # Append-only JSONL/CSV snapshots must end at a complete line. GPX files
    # are only served after their active recording session has ended.
    if size and name.endswith(('.jsonl', '.csv')):
        tail = os.pread(fd, min(size, 65536), max(0, size - 65536))
        last = tail.rfind(b'\n')
        return size - len(tail) + last + 1 if last >= 0 else 0
    return size


def handler(session, catalog=None):
    catalog = catalog or Catalog()
    token = session['token']
    prefix = '/s/' + token
    page = Path(__file__).with_name('download.html').read_text()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def log_message(self, *args):
            pass  # Do not print bearer-token URLs or private location filenames.

        def respond_headers(self, status, length, content_type, extra=None):
            self.send_response(status)
            self.send_header('Content-Length', str(length))
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()

        def text(self, status, message):
            data = message.encode()
            self.respond_headers(status, len(data), 'text/plain; charset=utf-8')
            if self.command != 'HEAD':
                self.wfile.write(data)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            try:
                self.serve()
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                self.close_connection = True

        def serve(self):
            path = unquote(urlsplit(self.path).path)
            pieces = path.split('/')
            if len(pieces) < 4 or pieces[1] != 's' or not hmac.compare_digest(pieces[2].encode(), token.encode()):
                self.text(403, '共享已关闭或二维码已失效，请重新扫描仪表上的下载二维码。')
                return
            host = self.headers_in_host()
            if host not in session.get('hosts', [session['address'] + ':' + str(session['port'])]):
                self.text(403, 'Host not allowed')
                return
            suffix = '/'.join(pieces[3:])
            if suffix == '':
                data = page.encode()
                self.respond_headers(200, len(data), 'text/html; charset=utf-8')
                if self.command != 'HEAD': self.wfile.write(data)
            elif suffix == 'app.js':
                data = Path(__file__).with_name('download.js').read_bytes()
                self.respond_headers(200, len(data), 'text/javascript; charset=utf-8')
                if self.command != 'HEAD': self.wfile.write(data)
            elif suffix == 'api/files':
                rows = catalog.files()
                for row in rows:
                    row['url'] = prefix + '/file/' + row['kind'] + '/' + quote(row['name'])
                data = json.dumps(dict(schema='skygauge.log-transfer/1', files=rows), ensure_ascii=False).encode()
                self.respond_headers(200, len(data), 'application/json; charset=utf-8')
                if self.command != 'HEAD': self.wfile.write(data)
            elif suffix.startswith('file/'):
                components = suffix.split('/')
                if len(components) != 3:
                    self.text(404, 'Not found'); return
                _, kind, name = components
                if kind == 'racechrono':
                    self.serve_racechrono(name)
                    return
                trip = active_trip()
                if kind == 'track' and trip and name.startswith(trip + '.'):
                    self.text(409, '这条轨迹仍在记录，请先在仪表轨迹页结束行程，再导出。'); return
                try:
                    fd, info = catalog.open(kind, name)
                except OSError:
                    self.text(404, 'Not found'); return
                try:
                    size = snapshot_size(fd, name, info.st_size)
                    try:
                        start, end = byte_range(self.headers.get('Range'), size)
                    except ValueError:
                        self.respond_headers(416, 0, 'application/octet-stream', {'Content-Range': 'bytes */%d' % size})
                        return
                    extra = {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(name),
                             'Accept-Ranges': 'bytes'}
                    partial = self.headers.get('Range') is not None
                    if partial: extra['Content-Range'] = 'bytes %d-%d/%d' % (start, end - 1, size)
                    self.respond_headers(206 if partial else 200, end - start, 'application/octet-stream', extra)
                    if self.command == 'HEAD': return
                    offset = start
                    while offset < end:
                        chunk = os.pread(fd, min(65536, end - offset), offset)
                        if not chunk:
                            self.close_connection = True
                            return
                        self.wfile.write(chunk)
                        offset += len(chunk)
                finally:
                    os.close(fd)
            else:
                self.text(404, 'Not found')

        def headers_in_host(self):
            return self.headers.get('Host', '')

        def serve_racechrono(self, name):
            if not allowed('racechrono', name):
                self.text(404, 'Not found'); return
            raw_name = name[:-len('.racechrono.csv')] + '.jsonl'
            try:
                fd, info = catalog.open('log', raw_name)
            except OSError:
                self.text(404, 'Not found'); return
            try:
                trip = active_trip()
                if trip and telemetry_header(fd, info.st_size).get('trip') == trip:
                    self.text(409, '这条行程仍在记录，请先结束行程再导出 CSV。'); return
                if not EXPORT_SLOTS.acquire(False):
                    self.text(429, '另一个 CSV 正在导出，请稍后重试。'); return
                try:
                    try:
                        exported, size, _ = convert(fd, info.st_size, raw_name)
                    except (ValueError, OSError):
                        self.text(422, '暂无可转换的完整数据，或文件格式不受支持。原始 LOG 未改变。'); return
                    with exported:
                        try:
                            start, end = byte_range(self.headers.get('Range'), size)
                        except ValueError:
                            self.respond_headers(416, 0, 'text/csv; charset=utf-8', {'Content-Range': 'bytes */%d' % size})
                            return
                        extra = {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(name),
                                 'Accept-Ranges': 'bytes', 'X-Mi4-Sky-Format': 'racechrono-csv-v3'}
                        partial = self.headers.get('Range') is not None
                        if partial: extra['Content-Range'] = 'bytes %d-%d/%d' % (start, end - 1, size)
                        self.respond_headers(206 if partial else 200, end - start, 'text/csv; charset=utf-8', extra)
                        if self.command == 'HEAD': return
                        exported.seek(start)
                        left = end - start
                        while left:
                            chunk = exported.read(min(65536, left))
                            if not chunk: break
                            self.wfile.write(chunk)
                            left -= len(chunk)
                finally:
                    EXPORT_SLOTS.release()
            finally:
                os.close(fd)

    return Handler


class DownloadServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, callback):
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(address, callback)

    def process_request(self, request, client_address):
        if not self.slots.acquire(False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def main():
    session = json.loads(Path('/run/obd-log-transfer/session.json').read_text())
    server = DownloadServer((session['address'], session['port']), handler(session))
    print('LOG_DOWNLOAD_LISTENING (private AP only)', flush=True)
    server.serve_forever(poll_interval=.5)


if __name__ == '__main__':
    main()

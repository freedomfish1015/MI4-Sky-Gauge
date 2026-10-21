"""Exact-version Fastboot image repair; CLI default is read-only inspection.

The release boot unit uses --auto; unknown/low-power devices are skipped.
Does not install a donor aboot. Unknown versions are refused. No auto reboot.
The original Mi4 aboot already draws its rabbit and needs no patch.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import time

ROOT = Path('/var/lib/mi4-sky/fastboot-repair')
STOCK_SHA = 'ff7bd7e050e5e91a6f50e8e31025c911f4c2f8b2ec73d2e2b3ccbc247b1c1212'
OLD_SHA = '362986d35fe58e55508615fc806483a4533e55f83fa9ab631ed1d7d9cb7c3f40'
NEW_SHA = 'd9ed7759fd8ed89cdd4351d582e45428316ab7ac6788bca4a45444c8b3dd5d49'
OFFSET = 0x2467c
SECTOR = 0x24600
SIZES = dict(aboot=4194304, logo=8388608, boot=33554432)
MINORS = dict(aboot=7, logo=10, boot=19)

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def classify(digest):
    return {STOCK_SHA:'stock-already-has-rabbit', NEW_SHA:'already-repaired',
            OLD_SHA:'eligible-known-sky-version'}.get(digest, 'unsupported-refuse-write')

def patched(raw):
    require(len(raw) == SIZES['aboot'] and sha(raw) == OLD_SHA, 'Unknown current aboot')
    require(struct.unpack_from('<I', raw, OFFSET)[0] == 0xebfff329, 'Unexpected instruction')
    result = bytearray(raw)
    struct.pack_into('<I', result, OFFSET, 0xe3a00000)
    result = bytes(result)
    require(sha(result) == NEW_SHA, 'Candidate differs from offline-tested image')
    require([i for i, (a, b) in enumerate(zip(raw, result)) if a != b] == list(range(OFFSET, OFFSET+4)), 'Patch exceeds four bytes')
    return result

def power():
    base = Path('/sys/class/power_supply')
    values = dict(voltage_uv=int((base/'bms/voltage_now').read_text()),
                  capacity=int((base/'bms/capacity').read_text()),
                  usb_online=int((base/'smbb-usbin/online').read_text()))
    require(values['usb_online'] == 1 and values['voltage_uv'] >= 3800000 and values['capacity'] >= 50,
            'Hard power floor not met: ' + repr(values))
    return values

def open_partition(name, writable=False):
    path = Path('/dev/disk/by-partlabel') / name
    require(str(path.resolve()) == '/dev/mmcblk0p%d' % MINORS[name], 'Wrong partition path')
    fd = os.open(path, (os.O_RDWR | os.O_SYNC if writable else os.O_RDONLY) | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISBLK(info.st_mode) and (os.major(info.st_rdev), os.minor(info.st_rdev)) == (179, MINORS[name]), 'Wrong block device')
        size = bytearray(8)
        fcntl.ioctl(fd, (2 << 30) | (struct.calcsize('P') << 16) | 0x1272, size, True)
        require(struct.unpack('<Q', size)[0] == SIZES[name], 'Wrong partition size')
        return fd
    except BaseException:
        os.close(fd)
        raise

def read_exact(fd, count, offset=0):
    output = bytearray()
    while len(output) < count:
        part = os.pread(fd, count-len(output), offset+len(output))
        require(bool(part), 'Short block read')
        output.extend(part)
    return bytes(output)

def write_sector(fd, raw):
    require(len(raw) == 512, 'Only one 512-byte sector may be written')
    view, offset = memoryview(raw), SECTOR
    while view:
        n = os.pwrite(fd, view, offset)
        require(n > 0, 'Short block write')
        view, offset = view[n:], offset+n
    os.fsync(fd)

def durable(path, raw):
    with path.open('xb') as f:
        os.chmod(path, 0o600)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    require(path.read_bytes() == raw, 'Backup readback mismatch')

def flush_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def transaction(before, after, read, write, check_power, verify_untouched):
    """Testable transaction. Every write, including rollback, is one sector."""
    check_power()
    require(read() == before, 'Concurrent aboot modification before write')
    attempted = False
    try:
        attempted = True
        write(after[SECTOR:SECTOR+512])
        require(read() == after, 'Full aboot readback mismatch')
        verify_untouched()
    except BaseException as failure:
        if attempted:
            try:
                write(before[SECTOR:SECTOR+512])
                require(read() == before, 'Rollback full readback mismatch')
            except BaseException as rollback_failure:
                raise RuntimeError('WRITE FAILED AND ROLLBACK FAILED: %r / %r; DO NOT REBOOT' % (failure, rollback_failure)) from failure
        raise

def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--check', action='store_true', help='Read-only check (default)')
    action.add_argument('--apply-known-patch', action='store_true', help='Explicitly authorize high-risk aboot patch')
    action.add_argument('--auto', action='store_true', help='Bundled first-boot exact-version policy; skip unsupported or insufficient power')
    args = parser.parse_args()
    def status_file(status, complete=False, **fields):
        if not (args.auto or args.apply_known_patch):return
        ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        value=dict(status=status,**fields)
        temporary=ROOT/'status.next'
        with temporary.open('w') as stream:
            os.chmod(temporary,0o600)
            json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,ROOT/'status.json');flush_dir(ROOT)
        if complete and not (ROOT/'completed').exists():
            durable(ROOT/'completed',(status+'\n').encode());flush_dir(ROOT)
    require(os.geteuid() == 0, 'Requires root')
    require(Path('/sys/firmware/devicetree/base/model').read_bytes().rstrip(b'\0') == b'Xiaomi Mi4(cancro)', 'Wrong device model')
    with Path('/run/lock/mi4-sky-logo.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = open_partition('aboot')
        try:
            current_sha = sha(read_exact(fd, SIZES['aboot']))
        finally:
            os.close(fd)
        status = classify(current_sha)
        print(json.dumps(dict(status=status, aboot_sha256=current_sha, wrote=False)), flush=True)
        if status in ('stock-already-has-rabbit', 'already-repaired'):
            status_file(status,complete=True,aboot_sha256=current_sha,wrote=False)
            return
        if args.auto and status == 'unsupported-refuse-write':
            status_file(status,aboot_sha256=current_sha,wrote=False)
            return
        require(status == 'eligible-known-sky-version', 'Unknown aboot version; no write is permitted')
        if not (args.apply_known_patch or args.auto):
            print('CHECK_ONLY: --apply-known-patch is required; aboot failure can remove Fastboot recovery.', flush=True)
            return
        state_path = Path('/run/obd-motion/state.json')
        if state_path.exists():
            require(not json.loads(state_path.read_text()).get('recording'), 'Recording active; refuse')
        samples = []
        try:
            for _ in range(3):
                samples.append(power())
                time.sleep(0.5)
            require(max(p['voltage_uv'] for p in samples)-min(p['voltage_uv'] for p in samples) < 150000, 'Unstable voltage')
        except (OSError,ValueError,RuntimeError) as failure:
            if not args.auto:raise
            status_file('deferred-insufficient-or-unstable-power',wrote=False,reason=str(failure))
            print('AUTO_REPAIR_DEFERRED_NO_WRITE',flush=True)
            return
        fds = {}
        try:
            for name in SIZES:
                fds[name] = open_partition(name, name == 'aboot')
            before = read_exact(fds['aboot'], SIZES['aboot'])
            after = patched(before)
            boot_sha = sha(read_exact(fds['boot'], SIZES['boot']))
            logo_sha = sha(read_exact(fds['logo'], SIZES['logo']))
            def untouched():
                require(sha(read_exact(fds['boot'], SIZES['boot'])) == boot_sha, 'Linux boot changed')
                require(sha(read_exact(fds['logo'], SIZES['logo'])) == logo_sha, 'Logo changed')
            untouched()
            ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
            (ROOT/'backups').mkdir(exist_ok=True)
            backup = Path(tempfile.mkdtemp(prefix='fastboot-rabbit-before-', dir=ROOT/'backups'))
            backup.chmod(0o700)
            durable(backup/'aboot.img', before)
            durable(backup/'aboot-expected.img', after)
            report = dict(status='backup-verified-before-write', power=samples, old_sha256=OLD_SHA,
                          new_sha256=NEW_SHA, changed_bytes=[OFFSET, OFFSET+4], write_sector=[SECTOR, 512],
                          boot_sha256=boot_sha, logo_sha256=logo_sha, edl_verified=False,
                          authorization=('Release automatic known-version policy requested by publisher' if args.auto else 'Owner invoked --apply-known-patch'),
                          no_reboot=True)
            durable(backup/'before.json', json.dumps(report, indent=2).encode())
            flush_dir(backup)
            flush_dir(backup.parent)
            print('BACKUP', backup, flush=True)
            try:
                transaction(before, after,
                            lambda: read_exact(fds['aboot'], SIZES['aboot']),
                            lambda raw: write_sector(fds['aboot'], raw), power, untouched)
            except BaseException as failure:
                durable(backup/'failure.json', json.dumps(dict(error=repr(failure)), indent=2).encode())
                flush_dir(backup)
                raise
            report['status'] = 'written-full-readback-verified-not-rebooted'
            try:
                report['power_after'] = power()
            except RuntimeError as warning:
                report['power_after_warning'] = str(warning)
            durable(backup/'success.json', json.dumps(report, indent=2).encode())
            flush_dir(backup)
            print('FASTBOOT_RABBIT_WRITE_VERIFIED', NEW_SHA, flush=True)
            print('BOOT_AND_LOGO_UNCHANGED; NO_REBOOT', flush=True)
            status_file('repaired-and-full-readback-verified',complete=True,aboot_sha256=NEW_SHA,wrote=True,backup=str(backup))
        finally:
            for fd in fds.values():
                os.close(fd)

if __name__ == '__main__':
    main()

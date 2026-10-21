"""Copy project sources into an explicit OFFLINE Ubuntu ARMhf staging tree.

No chroot, package installation, service execution, partition write or cleanup.
This is an overlay helper, not a complete OS/image factory.
"""
import argparse
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rootfs',type=Path,required=True)
    p.add_argument('--ack-offline-staging',action='store_true',required=True)
    p.add_argument('--enable-services',action='store_true',help='Create recorded wants links; external dependencies must already be supplied')
    args=p.parse_args()
    dest=args.rootfs.resolve()
    if dest==Path('/') or dest in ROOT.parents or not (dest/'etc/os-release').is_file():
        raise SystemExit('Need a dedicated offline Ubuntu rootfs, never the host root')
    content=(dest/'etc/passwd').read_text()
    if not any(line.startswith('umeko:x:1000:1000:') for line in content.splitlines()):
        raise SystemExit('Prepare the umeko UID/GID 1000 account in staging first')
    if (dest/'home/umeko/.config/obd-gauge/settings.json').exists():
        raise SystemExit('Existing configuration found; use a new clean staging tree')
    def copy(src,rel,executable=False):
        target=dest/rel
        if not target.parent.resolve().is_relative_to(dest) or target.is_symlink():
            raise RuntimeError('Refuse a path escaping staging or replacing a symlink')
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,target)
        target.chmod(0o755 if executable else 0o644)
        if 'sudoers.d' in target.parts:target.chmod(0o440)
    for path in (ROOT/'app').glob('*.py'):
        copy(path,'home/umeko/desktop-offline/'+path.name)
    mapping={'motion':'obd-motion','power':'obd-power','charge':'obd-charge',
             'log_transfer':'obd-log-transfer','platform':'mi4-sky','bms':'mi4-bms-fixed','startup':'obd-gauge'}
    for source,folder in mapping.items():
        for path in (ROOT/'services'/source).iterdir():
            if path.is_file():copy(path,'usr/local/lib/'+folder+'/'+path.name,path.suffix in ('.py','.sh'))
    for path in (ROOT/'overlay').rglob('*'):
        if path.is_file():copy(path,path.relative_to(ROOT/'overlay'), 'bin' in path.parts or 'sbin' in path.parts)
    for path in (ROOT/'vehicles/catalog').glob('*.vehicle.json'):
        copy(path,'home/umeko/.config/obd-gauge/pid-profiles/'+path.name)
    native=ROOT/'app/compat/build-armhf/libmi4compat.so'
    if native.is_file():
        header=native.read_bytes()[:20]
        if header[:6]!=b'\x7fELF\x01\x01' or int.from_bytes(header[18:20],'little')!=40:
            raise RuntimeError('Not a 32-bit little-endian ARM library')
        copy(native,'home/umeko/desktop-offline/compat/build-armhf/libmi4compat.so')
    if args.enable_services:
        for item in json.loads((ROOT/'metadata/overlay-links.json').read_text()):
            target=dest/item['path']
            if not (target.parent/item['target']).resolve().is_relative_to(dest):
                raise RuntimeError('Unsafe service symlink')
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() or target.is_symlink():raise RuntimeError('Existing service link')
            target.symlink_to(item['target'])
    if os.geteuid()==0:
        for path in (dest/'home/umeko').rglob('*'):os.chown(path,1000,1000,follow_symlinks=False)
    print('Project overlay copied. External firmware/helpers, packages, kernel modules, initramfs and boot validation remain required.')

if __name__=='__main__':main()

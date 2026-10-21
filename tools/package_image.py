"""Pack independently prepared images; never flash, imply privacy approval, or mark tested."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import uuid
import zipfile

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
    return h.hexdigest()

def check_sparse(path):
    with path.open('rb') as stream:
        total=path.stat().st_size
        data=stream.read(28)
        if len(data)!=28:raise ValueError('Sparse header truncated')
        magic,major,minor,header,chunk,block,blocks,chunks,crc=struct.unpack('<I4H4I',data)
        if magic!=0xed26ff3a or major!=1 or block!=4096 or block*blocks!=4294967296 or not (28<=header<=4096 and 12<=chunk<=4096 and 0<chunks<=1000000):
            raise ValueError('Invalid sparse header/expanded size')
        stream.seek(header);count=0;prefix=bytearray()
        for _ in range(chunks):
            position=stream.tell();raw=stream.read(12)
            if len(raw)!=12:raise ValueError('Truncated chunk header')
            kind,reserved,n,size=struct.unpack('<HHII',raw)
            payload=size-chunk
            expected=n*block if kind==0xcac1 else 4 if kind in (0xcac2,0xcac4) else 0 if kind==0xcac3 else -1
            if payload!=expected or expected<0 or (kind==0xcac4 and n!=0) or position+size>total:
                raise ValueError('Invalid sparse chunk')
            stream.seek(position+chunk)
            need=min(max(0,2048-len(prefix)),n*block)
            if need:
                if kind==0xcac1:prefix.extend(stream.read(need))
                elif kind==0xcac2:
                    fill=stream.read(4);prefix.extend((fill*((need+3)//4))[:need])
                elif kind==0xcac3:prefix.extend(bytes(need))
            stream.seek(position+size);count+=n
        if count!=blocks or stream.tell()!=total:raise ValueError('Sparse count/trailing bytes mismatch')
        if len(prefix)<1144 or prefix[1080:1082]!=b'\x53\xef':raise ValueError('Not an ext4 superblock')
        if str(uuid.UUID(bytes=bytes(prefix[1128:1144])))!='93afcbbe-875f-49b0-83da-ee8193f20ca5':
            raise ValueError('Root filesystem UUID mismatch')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--boot',type=Path,required=True)
    p.add_argument('--rootfs-sparse',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--version',required=True)
    p.add_argument('--ack-reviewed-inputs',action='store_true',required=True,
                   help='Input privacy, firmware/artwork licensing and hardware correctness must be separately reviewed')
    args=p.parse_args()
    if args.output.exists():raise SystemExit('Refuse overwriting an existing image')
    if not args.version or len(args.version)>100:raise SystemExit('Invalid version')
    with args.boot.open('rb') as stream:
        if args.boot.stat().st_size!=33554432 or stream.read(8)!=b'ANDROID!':raise SystemExit('Need full physical 32 MiB boot')
        stream.seek(524288)
        if stream.read(8)!=b'ANDROID!':raise SystemExit('Missing Linux header at 512 KiB')
    check_sparse(args.rootfs_sparse)
    manifest=dict(format=1,product='mi4-sky',version=args.version,installer_min=2,
        profile='mi4-lte-jdi-mxt640t',install_mode='clean-stock-fastboot',boot_partition_bytes=33554432,
        root_uuid='93afcbbe-875f-49b0-83da-ee8193f20ca5',rootfs_bytes=4294967296,
        validation='candidate-not-clean-flash-tested',bundled_repairs=[],files=[
            dict(name=name,size=path.stat().st_size,sha256=digest(path)) for name,path in
            (('boot.img',args.boot),('rootfs.sparse.img',args.rootfs_sparse))])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as archive:
        archive.writestr('manifest.json',json.dumps(manifest,indent=2))
        archive.write(args.boot,'boot.img');archive.write(args.rootfs_sparse,'rootfs.sparse.img')
        archive.writestr('LICENSES.txt','Project source GPL-3.0; third-party input licenses remain unchanged. This packager does not approve redistribution, clean-flash validation, privacy or hardware compatibility. First-boot behavior is determined by the supplied rootfs and must be reviewed.\n')
    print('PACKAGED CANDIDATE',args.output,digest(args.output))

if __name__=='__main__':main()

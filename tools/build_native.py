"""Build the vendored, GPLv3 PID/event cores. No downloads and no device I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--target',choices=('host','armhf'),default='host')
    args=p.parse_args()
    from verify_dependencies import verify
    verify()
    upstream=ROOT/'vendor/obd_brz_gauge/main'
    vehicle=upstream/'vehicle'
    rules=upstream/'theme_engine/rules'
    cjson=ROOT/'vendor/cjson'
    sources=[vehicle/(name+'.c') for name in ('vp_common','vp_compile','vp_defaults',
             'vp_builtin_generic','vp_rpn','vp_rpn_json','vp_validate','vp_engine')]
    sources += [upstream/'app_obd_dsp/signal_registry.c']
    sources += [rules/(name+'.c') for name in ('tr_parse','tr_eval','tr_format')]
    sources += [cjson/'cJSON.c',ROOT/'native/mi4_compat.c']
    out=ROOT/'app/compat'/('build-'+args.target)
    out.mkdir(parents=True,exist_ok=True)
    output=out/'libmi4compat.so'
    command=['gcc' if args.target=='host' else 'arm-linux-gnueabihf-gcc',
             '-std=c99','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-fPIC','-shared']
    command += ['-I'+str(path) for path in (upstream,vehicle,rules,cjson)]
    subprocess.run(command+list(map(str,sources))+['-lm','-o',str(output)],check=True)
    manifest=dict(target=args.target,upstream_commit='976106c7bce8421ba7aa689a61d79dce4e8e16df',
                  cjson='1.7.19',sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                  sources={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (out/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('BUILT',output)

if __name__=='__main__':main()

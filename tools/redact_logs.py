"""Publish technical history without publishing live identities or coordinates.

Conservative heuristic, not a proof that every secret is found. Review output.
Original inputs are never modified; opaque transfer payloads are not retained.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ANSI=re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
SAFE_DOMAINS=('github.com','raw.githubusercontent.com','docs.github.com','kernel.org',
              'git.kernel.org','gnu.org','www.gnu.org','ubuntu.com','packages.ubuntu.com')

def redact(text):
    stats={}
    def count(name):stats[name]=stats.get(name,0)+1
    text=re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----',
                '[PRIVATE KEY BLOCK REMOVED]',text,flags=re.S)
    output=[]
    for line in text.splitlines():
        line=ANSI.sub('',line).replace('\x00','')
        if re.search(r'base64\s+-d|SERIAL_DONE_|^\s*[A-Za-z0-9+/]{120,}={0,2}\s*$',line):
            count('encoded-transfer-or-shell-envelope')
            continue
        if re.search(r'(?:\$G[PNLAB]|\$BD)(?:RMC|GGA|GSA|GSV|GLL|VTG)|(?:latitude|longitude|lat_deg|lon_deg|<trkpt|<wpt)',line,re.I):
            # Do not preserve an entire telemetry JSON line containing location.
            output.append('[LOCATION-BEARING LINE REMOVED]')
            count('location')
            continue
        if re.match(r'^\s*(?:Cookie|Set-Cookie|Authorization)\s*:',line,re.I):
            output.append('[AUTH HEADER REMOVED]');count('credential');continue
        if line.strip()=='1234':
            output.append('[AUTH INPUT REMOVED]');count('credential');continue
        line,n=re.subn(r'(?i)(["\']?(?:password|passwd|passphrase|psk|secret|ssid|access_token|refresh_token|token)["\']?\s*[:=]\s*)(["\'])[^"\'\r\n]+\2',r'\1"[REDACTED]"',line)
        if n:stats['credential']=stats.get('credential',0)+n
        line,n=re.subn(r'(?i)((?:password|passphrase|psk|secret|ssid|access_token|refresh_token|token)\s*[:=]\s*)[^\s,;]+',r'\1[REDACTED]',line)
        if n:stats['credential']=stats.get('credential',0)+n
        def url(match):
            value=match.group()
            host=value.split('://',1)[1].split('/',1)[0].lower()
            if host in SAFE_DOMAINS and not ('?' in value or '@' in host):return value
            count('non-public-url');return '[URL REDACTED]'
        line=re.sub(r'https?://[^\s\])>"\']+',url,line)
        line,n=re.subn(r'(?<![\w:])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![\w:])','[BT-ADDRESS]',line,flags=re.I)
        if n:stats['bluetooth-address']=stats.get('bluetooth-address',0)+n
        line,n=re.subn(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])','[IP-ADDRESS]',line)
        if n:stats['ip-address']=stats.get('ip-address',0)+n
        line,n=re.subn(r'(?i)(?<![A-Za-z0-9])[A-Z]:[/\\][^`\s|\]\)"<>]+','[LOCAL-PATH]',line)
        if n:stats['local-path']=stats.get('local-path',0)+n
        line,n=re.subn(r'(?i)wxid_[a-z0-9_-]+','[MESSAGING-ID]',line)
        if n:stats['messaging-id']=stats.get('messaging-id',0)+n
        line,n=re.subn(r'\b5b628616\b','[DEVICE-SERIAL]',line,flags=re.I)
        if n:stats['serial']=stats.get('serial',0)+n
        output.append(line)
    return '\n'.join(output)+'\n',stats

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',action='append',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    target=args.out.resolve()
    if target.exists():raise SystemExit('Use a new output directory; do not overwrite reviewed logs')
    if any(target.is_relative_to(source.resolve()) for source in args.input):
        raise SystemExit('Output must not be inside an input tree')
    target.mkdir(parents=True)
    records=[]
    excluded=[]
    for number,base in enumerate(args.input):
        for path in sorted(base.glob('*')):
            if not path.is_file() or path.suffix.lower() not in ('.log','.md'):
                continue
            if re.search(r'netease|weapi|qq-|cookie|music-|account|sudo|private|chunk|export-endpoint',path.name,re.I):
                excluded.append(dict(file=path.name,reason='account/private/transfer material; technical summary retained elsewhere'))
                continue
            if path.stat().st_size>2*1024*1024:
                excluded.append(dict(file=path.name,reason='over 2 MiB; requires manual review'))
                continue
            raw=path.read_text(encoding='utf-8-sig',errors='replace')
            cleaned,stats=redact(raw)
            name=f'{number+1:02d}/'+path.name
            dest=target/name
            dest.parent.mkdir(exist_ok=True)
            dest.write_text(cleaned,encoding='utf-8',newline='\n')
            records.append(dict(file=name,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),redactions=stats))
    (target/'index.json').write_text(json.dumps(dict(files=records,excluded=excluded,
        warning='Historical evidence, not current deployment instructions; inputs remain private and unchanged.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SANITIZED_HISTORY',len(records),'files; excluded',len(excluded),'account/private items')

if __name__=='__main__':main()

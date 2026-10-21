"""Conservative source publication checks. Review licenses and privacy manually too."""
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
IGNORED={'.git','build','dist','__pycache__','.venv','build-host','build-armhf'}

def public_files():
    try:
        result=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z'],stderr=subprocess.DEVNULL)
        if result:return [ROOT/p.decode() for p in result.split(b'\0') if p]
    except (subprocess.CalledProcessError,FileNotFoundError):pass
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and not set(p.relative_to(ROOT).parts)&IGNORED)

def audit():
    files=public_files();problems=[]
    forbidden={'.img','.mi4sky','.so','.ko','.exe','.dll','.mp4','.avi','.zip','.gz','.key','.pk8'}
    for path in files:
        rel=path.relative_to(ROOT).as_posix()
        if path.is_symlink():problems.append((rel,'source export unexpectedly contains a symlink'));continue
        if path.suffix.lower() in forbidden:problems.append((rel,'binary/private artifact in source set'))
        if path.stat().st_size>=25*1024*1024:problems.append((rel,'too large for browser source upload'))
        if path.name in ('.obd-sudo-pass','.env','sky-peer.conf','radio-restore.json','settings.json'):
            problems.append((rel,'live state/credential filename'))
        if path.suffix in ('.png','.pdf'):continue
        try:text=path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:problems.append((rel,'unclassified binary'));continue
        patterns={
            'private-key-block':r'(?m)^-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
            'github-credential':r'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})\b',
            'developer-home-path':r'(?i)[A-Z]:[/\\]Users[/\\]freed(?:[/\\]|\b)',
            'messaging-identity':r'\bwxid_[a-zA-Z0-9_-]+',
        }
        for kind,pattern in patterns.items():
            if re.search(pattern,text):problems.append((rel,kind))
        if rel.startswith('development-logs/') and path.suffix in ('.log','.md') and path.name not in ('index.json','README.md'):
            if re.search(r'(?<![\w:])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![\w:])',text):
                problems.append((rel,'unredacted address in historical log'))
            if re.search(r'printf.*base64\s+-d|SERIAL_DONE_',text):
                problems.append((rel,'opaque shell envelope'))
    result=dict(files=len(files),total_bytes=sum(p.stat().st_size for p in files),
                largest_bytes=max((p.stat().st_size for p in files),default=0),
                automated_checks_passed=not problems,problems=problems,
                note='Heuristics and file-size checks; not a legal or complete secret-scanning certification.')
    return result

if __name__=='__main__':
    value=audit();print(json.dumps(value,ensure_ascii=False,indent=2));raise SystemExit(0 if value['automated_checks_passed'] else 1)

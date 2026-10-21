"""Verify the pinned, vendored source closure without requiring network/Git metadata."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def verify():
    lock=json.loads((ROOT/'metadata/dependencies.lock.json').read_text())
    for rel,expected in lock['vendored_files'].items():
        path=ROOT/rel
        if not path.resolve().is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Vendored source changed: '+rel+'. Review the fork and update the lock intentionally.')
    print('VERIFIED',len(lock['vendored_files']),'vendored source files')

if __name__=='__main__':verify()

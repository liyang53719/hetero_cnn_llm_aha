"""SOURCE-only cold launcher; production C++ is data, never executed."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
ENTRY_PIN=(2375, 'ef0e1e1a7e3dba494d57775cd291110b1b36b5e6dac39bd230bf334a97ff0383')
raw=(ROOT/'source_entry.py').read_bytes()
if (len(raw),hashlib.sha256(raw).hexdigest())!=ENTRY_PIN:
    raise ValueError('COLD_ENTRY_IDENTITY')
scope={'__name__':'checked_pc01_entry','__file__':str(ROOT/'source_entry.py')}
exec(compile(raw,str(ROOT/'source_entry.py'),'exec'),scope)
result=scope['run'](ROOT)
print(json.dumps(result,sort_keys=True))
raise SystemExit(0 if result['passed'] else 1)

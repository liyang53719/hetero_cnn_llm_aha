"""Dependency-only preflight. No numerical imports, CDLL, compilation or execution."""
import json
from pathlib import Path
from .source_contract import ROOT, blob, check as source_check

HERE=Path(__file__).resolve().parent

def check():
    pins=json.loads((HERE/'numeric_pins.json').read_text())
    if pins['baseline_commit']!='033ac109bf790be16ecac34db485f8b7799e06e5':
        raise ValueError('numeric baseline drift')
    for name,expected in pins['inputs'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('nonrepository input')
        if blob((ROOT/path).read_bytes())!=expected:
            raise ValueError('numeric source drift: '+name)
    source_check()
    return {'status':'PASS_PREPARATION_ONLY','inputs':len(pins['inputs']),
            'arithmetic_executed':False,'hardware_simulation':False}

if __name__=='__main__':
    print(json.dumps(check(),sort_keys=True))

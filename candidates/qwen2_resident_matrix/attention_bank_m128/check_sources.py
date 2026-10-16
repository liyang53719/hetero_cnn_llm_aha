"""Freeze the tiled controller and complete original-owner oracle closure."""
import hashlib,json
from pathlib import Path
from ..attention_bank_multirow import check_sources as prior
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_bank_m128/'
SOURCES=tuple(sorted((*prior.SOURCES,*prior.OWN,prior.PREFIX+'pins.json')))
OWN=tuple(PREFIX+n for n in ('controller.py','storage.py','test_controller.py','run_numeric.py','test_runner.py','check_sources.py','README.md'))
def snapshot():
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in (*SOURCES,*OWN,PREFIX+'pins.json')}
def check():
    pins=json.loads((HERE/'pins.json').read_bytes())
    if type(pins) is not dict or set(pins)!={'schema','profile','sources','own'} or type(pins['schema']) is not int or pins['schema']!=1 or pins['profile']!='attention-bank-tiled-fraction-v1':raise ValueError('source contract')
    if set(pins['sources'])!=set(SOURCES) or set(pins['own'])!=set(OWN):raise ValueError('source inventory')
    for group in ('sources','own'):
        for name,digest in pins[group].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('source drift')
    prior.check()
    return dict(status='PASS_SOURCE_ONLY',sources=len(SOURCES),own=len(OWN),native_enabled=False,rtl_enabled=False)
if __name__=='__main__':print(json.dumps(check(),sort_keys=True))

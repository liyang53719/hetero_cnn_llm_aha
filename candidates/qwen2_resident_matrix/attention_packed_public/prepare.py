"""Pinned composition of original Public transport and exact-owner profile."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from ..attention_packed_owner import prepare as owner
from ..raw_kv_public import prepare as public
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_packed_public/'
TARGETS=(*public.TARGETS,'candidates/qwen2_resident_matrix/raw_kv_attention/model.py','candidates/qwen2_resident_matrix/raw_kv_public/model.py')
ORACLE_SOURCE='candidates/qwen2_resident_matrix/official_bf16/owners.py'
ORACLE_COPY=PREFIX+'original_owner.source'
OWN=tuple(PREFIX+n for n in ('profile.py','mux.py','public.patch','prepare.py','test_mux.py','test_public.py','README.md'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs():
    return tuple(sorted(set((*owner.SOURCES,*owner.OWN,owner.PREFIX+'pins.json',*public.check()['inputs'],'candidates/qwen2_resident_matrix/raw_kv_attention/numeric_bridge.py','candidates/qwen2_resident_matrix/dense_block_reduce/profile.py'))))
def snapshot():return {n:digest(ROOT/n) for n in (*inputs(),*OWN,PREFIX+'pins.json')}
def check():
    owner.check();p=json.loads((HERE/'pins.json').read_bytes());names=inputs()
    if set(p)!= {'schema','sources','own','generated'} or type(p['schema']) is not int or p['schema']!=1:raise ValueError('packed Public profile')
    if set(p['sources'])!=set(names) or set(p['own'])!=set(OWN) or set(p['generated'])!=set(TARGETS):raise ValueError('packed Public source inventory')
    for field in ('sources','own'):
        for n,h in p[field].items():
            if digest(ROOT/n)!=h:raise ValueError('packed Public source drift')
    return p

def _compose(destination):
    destination=Path(destination);owner.compose(destination)
    for n in inputs():
        target=destination/n
        if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
    with tempfile.TemporaryDirectory() as d:
        out=Path(d)/'public';public.prepare(out)
        for n in public.TARGETS:(destination/n).write_bytes((out/n).read_bytes())
    for n in OWN:
        target=destination/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
    pin=HERE/'pins.json'
    if pin.exists():(destination/PREFIX/'pins.json').write_bytes(pin.read_bytes())
    (destination/ORACLE_COPY).write_bytes((ROOT/ORACLE_SOURCE).read_bytes())
    r=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(HERE/'public.patch')],cwd=destination,capture_output=True,timeout=5)
    if r.returncode or any(x in r.stdout+r.stderr for x in (b'offset',b'fuzz')):raise ValueError('packed Public composition')
    return destination

def compose(destination):
    p=check();out=_compose(destination)
    if {n:digest(out/n) for n in TARGETS}!=p['generated']:raise ValueError('packed Public generated identity')
    if digest(out/ORACLE_COPY)!=p['sources'][ORACLE_SOURCE]:raise ValueError('original oracle source identity')
    return out

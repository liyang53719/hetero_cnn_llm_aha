"""Default-off source overlay. No native build or Public admission."""
import hashlib,json,subprocess
from pathlib import Path
from ..attention_packed_native import prepare as native
from ..attention_bank_panel import check_sources as panel
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_packed_owner/'
TARGETS=('candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py','candidates/qwen2_resident_matrix/official_bf16/owners.py')
SOURCES=tuple(sorted(set((*native.SOURCES,*native.OWN,native.PREFIX+'pins.json',*panel.SOURCES,*panel.OWN,panel.PREFIX+'pins.json','candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py'))))
OWN=tuple(PREFIX+n for n in ('owner.patch','client.py','protocol.py','schedule.py','hooks.py','bridge.py','prepare.py','test_client.py','test_owner.py','README.md'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot():return {n:digest(ROOT/n) for n in (*SOURCES,*OWN,PREFIX+'pins.json')}
def check():
    native.check();panel.check();p=json.loads((HERE/'pins.json').read_bytes())
    if set(p)!= {'schema','sources','own','generated'} or type(p['schema']) is not int or p['schema']!=1:raise ValueError('packed owner profile')
    if set(p['sources'])!=set(SOURCES) or set(p['own'])!=set(OWN) or set(p['generated'])!=set(TARGETS):raise ValueError('packed owner source inventory')
    for field in ('sources','own'):
        for n,h in p[field].items():
            if digest(ROOT/n)!=h:raise ValueError('packed owner source drift')
    return p

def compose(destination):
    p=check();destination=Path(destination);native.compose(destination)
    for n in SOURCES:
        target=destination/n
        if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
    for n in OWN:
        target=destination/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
    result=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(HERE/'owner.patch')],cwd=destination,capture_output=True,timeout=5)
    if result.returncode or any(x in result.stdout+result.stderr for x in (b'offset',b'fuzz')):raise ValueError('owner composition')
    if {n:digest(destination/n) for n in TARGETS}!=p['generated']:raise ValueError('owner generated identity')
    return destination

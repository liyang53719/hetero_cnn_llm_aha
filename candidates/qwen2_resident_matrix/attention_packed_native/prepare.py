"""Strict source-only composition of an explicit packed host Matrix profile."""
import hashlib,json,subprocess
from pathlib import Path
from ..attention_bank_m128 import check_sources as prior
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_packed_native/'
TARGETS=('candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp','candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py')
BACKEND=('chisel/continuous_prefill/src/main/scala/heteronpu/continuous/RetainedMatrix.scala',
 'rtl/integration/qwen2_matrix_command_endpoint.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv')
SOURCES=tuple(sorted(set((*prior.SOURCES,*prior.OWN,prior.PREFIX+'pins.json',*TARGETS,*BACKEND,'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp'))))
OWN=tuple(PREFIX+n for n in ('profile.patch','prepare.py','test_prepare.py','check_native.py','README.md'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot():return {n:digest(ROOT/n) for n in (*SOURCES,*OWN,PREFIX+'pins.json')}
def check():
    p=json.loads((HERE/'pins.json').read_bytes())
    if set(p)!={'schema','profile','sources','own','generated'} or type(p['schema']) is not int or p['schema']!=1 or p['profile']!='original-attention-packed-matrix-profile2-v1':raise ValueError('packed source contract')
    if set(p['sources'])!=set(SOURCES) or set(p['own'])!=set(OWN) or set(p['generated'])!=set(TARGETS):raise ValueError('source inventory')
    for group in ('sources','own'):
        for n,h in p[group].items():
            if digest(ROOT/n)!=h:raise ValueError('source drift')
    prior.check()
    return p

def compose(destination):
    p=check();destination=Path(destination)
    if destination.exists():raise ValueError('fresh composition destination required')
    destination.mkdir(parents=True)
    for n in SOURCES:
        target=destination/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
    result=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(HERE/'profile.patch')],cwd=destination,capture_output=True,timeout=10)
    if result.returncode or b'offset' in result.stdout+result.stderr or b'fuzz' in result.stdout+result.stderr:raise ValueError('zero-fuzz composition')
    for n in TARGETS:
        if digest(destination/n)!=p['generated'][n]:raise ValueError('generated source identity')
    return dict(status='PASS_SOURCE_COMPOSITION',source_sha256=snapshot(),generated_sha256={n:digest(destination/n) for n in TARGETS})

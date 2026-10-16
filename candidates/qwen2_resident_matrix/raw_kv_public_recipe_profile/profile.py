"""Source-only admission for a new Public reference producer profile.

No setup producer, package, library or numerical entry is executed here.
"""
import hashlib
import json
from pathlib import Path

from ..raw_kv_native_qk_run import runtime as native

ROOT=Path(__file__).resolve().parents[3]
PREFIX='candidates/qwen2_resident_matrix/raw_kv_public_recipe_profile/'
PINS=PREFIX+'pins.json'
PROFILE='qwen2-public-pv16-native-pair-avx512bf16-v1'
STATUS='PREPARATION_ONLY_EXECUTION_BLOCKED'
NATIVE_CONTRACT_SHA256='a479df84ff09bfab7e1e8173415feb69ef91ff6e80de9424fb6ff23f2f8d34de'
PUBLIC_CONTRACT='candidates/qwen2_resident_matrix/raw_kv_public_m128_run/launch-contract.json'
PUBLIC_CONTRACT_SHA256='e5f9dd18f6f288c98598b0935426da87588cdd20f1c197b1545a6e822e7902a7'
OWN=('profile.py','dispatch.py','test_profile.py','test_dispatch.py','README.md')
EVIDENCE=tuple('candidates/qwen2_resident_matrix/raw_kv_native_pass_results/'+n for n in ('EVIDENCE.json','README.md','test_evidence.py'))+('candidates/qwen2_resident_matrix/raw_kv_native_info_results/EVIDENCE.json',)
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def need(ok):
    if not ok:raise ValueError('Public recipe preparation contract')


def snapshot():
    """Freeze the original public closure and independently validated producer."""
    need(ROOT==native.ROOT)
    frozen=native.snapshot()
    need(frozen['contract_sha256']==NATIVE_CONTRACT_SHA256)
    need(native.sha(native.read_source(PUBLIC_CONTRACT))==PUBLIC_CONTRACT_SHA256)
    raw=native.read_source(PINS,262144)
    value=native.json_bytes(raw)
    fixed=dict(schema=1,profile=PROFILE,status=STATUS,rows=128,past_tokens=0,
        native_contract_sha256=NATIVE_CONTRACT_SHA256,public_contract_sha256=PUBLIC_CONTRACT_SHA256,
        setup_budget_seconds=900,work_budget_seconds=2400,external_budget_seconds=2430,
        outer_budget_seconds=3420,numerical_execution_enabled=False)
    need(type(value) is dict and set(value)==set(fixed)|{'source_sha256'})
    need(all(type(value[k]) is type(v) and value[k]==v for k,v in fixed.items()))
    names=set(frozen['sources'])|{PREFIX+n for n in OWN}|set(EVIDENCE)
    sources=value['source_sha256']
    need(type(sources) is dict and set(sources)==names)
    need(all(native.relative_name(n) and native.digest(h) for n,h in sources.items()))
    need(all(sources[n]==h for n,h in frozen['sources'].items()))
    need(sources[PREFIX+'profile.py']==IMPORTED_SHA256)
    need(all(native.sha(native.read_source(n))==h for n,h in sources.items()))
    sources=dict(sources);sources[PINS]=native.sha(raw)
    return dict(status=STATUS,profile=PROFILE,source_sha256=sources,
        pins_sha256=native.sha(raw),numerical_execution_enabled=False,
        setup_overlay_implemented=False,asset_overlay_implemented=False,
        actual_chain_executed=False,full_29_node_acceptance=False)


def authorize_run(*args,**kwargs):
    raise ValueError('Public recipe setup and linked launch are not implemented')

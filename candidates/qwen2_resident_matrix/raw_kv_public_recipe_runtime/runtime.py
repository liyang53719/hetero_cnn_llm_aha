"""Closed source/setup identity for the Public paired-reference runtime.

The linked Public launch remains blocked until its separate reviewed layer.
"""
import hashlib
import json
import math
from pathlib import Path
import time

from ..raw_kv_public_recipe_profile import profile as previous
from ..raw_kv_native_qk_run import runtime as native
from ..raw_kv_public_m128 import prerequisite

ROOT=Path(__file__).resolve().parents[3]
PREFIX='candidates/qwen2_resident_matrix/raw_kv_public_recipe_runtime/'
PINS_PATH=PREFIX+'pins.json'
PROFILE='qwen2-public-pv16-native-pair-runtime-v1'
SETUP_PROFILE='qwen2-public-fresh-pair-m128-setup-v1'
ASSET_PROFILE='qwen2-public-pv16-pair-assets-m128-v1'
BASE_COMMIT='e2cfc667baa9114b7c22a1cb7c0076e9bb8acaba'
PREVIOUS_PINS_SHA256='e59717cff3e0caecd3af0bb7d15da50ed247bc4a9ae6572054959c47a10cf5b3'
GENERATED_MODULE_SHA256=native.GENERATED_MODULE_SHA256
OWN=('runtime.py','producer.py','admission.py','prepare.py','runtime.patch',
     'test_runtime.py','test_producer.py','test_admission.py','README.md')
TARGETS=(prerequisite.ASSETS,prerequisite.ENTRY,prerequisite.SETUP)
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
PHASE_LIMITS=dict(preflight=20,environment=120,acquisition=420,references=140,
    recipe_kernel=30,native16=60,native128=120,library=40,seal=30)


def need(ok):
    if not ok:raise ValueError('Public paired runtime contract')


def read_source(name,limit=4194304):
    need(ROOT==native.ROOT==previous.ROOT)
    return native.read_source(name,limit)


def contract_value():
    base_raw=read_source(previous.PINS,262144)
    need(native.sha(base_raw)==PREVIOUS_PINS_SHA256)
    base=native.json_bytes(base_raw)
    old=dict(base['source_sha256']);old[previous.PINS]=PREVIOUS_PINS_SHA256
    legacy_raw=read_source(previous.PUBLIC_CONTRACT,262144)
    need(native.sha(legacy_raw)==previous.PUBLIC_CONTRACT_SHA256)
    legacy=native.json_bytes(legacy_raw)
    raw=read_source(PINS_PATH,262144);value=native.json_bytes(raw)
    fixed=dict(schema=1,profile=PROFILE,base_commit=BASE_COMMIT,setup_profile=SETUP_PROFILE,asset_profile=ASSET_PROFILE,
        previous_pins_sha256=PREVIOUS_PINS_SHA256,rows=128,past_tokens=0,enable_raw_kv=True,
        setup_budget=900,work_budget=2400,external_budget=2430,outer_budget=3420,
        generated_module_sha256=GENERATED_MODULE_SHA256,public_execution_enabled=False)
    need(type(value) is dict and set(value)==set(fixed)|{'source_sha256','generated_sha256','phase_limits'})
    need(all(type(value[k]) is type(v) and value[k]==v for k,v in fixed.items()))
    need(prerequisite.same(value['phase_limits'],PHASE_LIMITS))
    sources=value['source_sha256'];generated=value['generated_sha256']
    need(type(sources) is dict and set(sources)==set(old)|{PREFIX+n for n in OWN})
    need(all(native.relative_name(n) and native.digest(h) for n,h in sources.items()))
    need(all(sources[n]==h for n,h in old.items()))
    need(sources[PREFIX+'runtime.py']==IMPORTED_SHA256)
    need(type(generated) is dict and set(generated)==set(legacy['generated_sha256']) and len(generated)==10)
    need(all(native.digest(h) for h in generated.values()))
    need(all(generated[n]==h for n,h in legacy['generated_sha256'].items() if n not in TARGETS))
    need(all(generated[n]!=legacy['generated_sha256'][n] for n in TARGETS))
    return raw,value


def contract_snapshot(*,composed=False):
    need(type(composed) is bool)
    raw,value=contract_value();sources=dict(value['source_sha256'])
    if composed:sources.update(value['generated_sha256'])
    need(all(native.sha(read_source(n))==h for n,h in sources.items()))
    sources[PINS_PATH]=native.sha(raw)
    return dict(sources=sources,inputs=sources,contract_sha256=native.sha(raw),generated=dict(value['generated_sha256']))


def source_snapshot():return contract_snapshot(composed=True)['sources']

def asset_source_snapshot(*,enable_raw_kv=False):
    need(type(enable_raw_kv) is bool and enable_raw_kv is True)
    frozen=contract_snapshot(composed=True)
    prerequisite.compatible_sources(frozen['sources'],{n:frozen['generated'][n] for n in prerequisite.VARIANTS},
        profile=prerequisite.PROFILE,rows=128,past_tokens=0)
    return frozen['sources']

def own_asset_sources():return asset_source_snapshot(enable_raw_kv=True)
def setup_source_snapshot(enabled):return asset_source_snapshot(enable_raw_kv=enabled)
def asset_sources(sources):
    expected=asset_source_snapshot(enable_raw_kv=True);need(prerequisite.same(sources,expected));return expected

def base_verifier_sources():
    _,value=contract_value();sources=dict(value['source_sha256']);sources.update(value['generated_sha256'])
    prefix='candidates/qwen2_resident_matrix/raw_kv_public_fresh/'
    return {prefix+n:sources[prefix+n] for n in ('assets.py','official_entry.patch','public_entry.patch','prepare.py','pins.json','README.md','test_assets.py')}

def verify_loaded_setup(identity):need(identity==contract_snapshot(composed=True)['generated'][prerequisite.SETUP])
def setup_git_sources():return tuple(PREFIX+n for n in OWN)+(PINS_PATH,)


def producer_context(context,workspace,*,check_deadline=True):
    from ..raw_kv_native_qk import kernel
    need(type(check_deadline) is bool and type(context) is dict and set(context)=={'schema','workspace','checkout_commit',
        'enable_raw_kv','source_sha256','asset_source_sha256','work_deadline_ns'})
    need(type(context['schema']) is int and context['schema']==1 and context['enable_raw_kv'] is True)
    need(type(context['checkout_commit']) is str and native.digest(context['checkout_commit'],40))
    need(type(context['work_deadline_ns']) is int and 0<context['work_deadline_ns']<1<<63)
    if check_deadline:need(context['work_deadline_ns']>time.monotonic_ns())
    workspace=kernel.safe_path(workspace,directory=True)
    need(type(context['workspace']) is str and str(workspace)==context['workspace'])
    frozen=contract_snapshot(composed=True)
    need(prerequisite.same(context['source_sha256'],frozen['sources']) and
         prerequisite.same(context['asset_source_sha256'],frozen['sources']))
    return dict(context,contract_sha256=frozen['contract_sha256'],
        generated_module=str(workspace/'generated/qwen2_layer0_model_gate.py'),generated_module_sha256=GENERATED_MODULE_SHA256)


def read_context(path,*,check_deadline=True):
    from ..raw_kv_native_qk import kernel
    path=kernel.safe_path(path);need(path.name=='context.json')
    raw=kernel.read(path,262144);context=native.json_bytes(raw)
    return producer_context(context,path.parent,check_deadline=check_deadline),path.parent


def remaining(context,ceiling):
    need(type(ceiling) in (int,float) and math.isfinite(ceiling) and 0<ceiling<=900)
    seconds=min(ceiling,(context['work_deadline_ns']-time.monotonic_ns())/1e9)
    if seconds<=0:raise TimeoutError()
    return seconds


def authorize_run(*args,**kwargs):
    raise ValueError('Public paired-reference linked launch not implemented')

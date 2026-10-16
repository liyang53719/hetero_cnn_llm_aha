"""Exact linked Public paired-reference launch contract; no numerical imports."""
import hashlib
import json
import math
from pathlib import Path
import time
from ..raw_kv_public_recipe_runtime import runtime as prior
from ..raw_kv_public_m128 import prerequisite
from ..raw_kv_public_m128_run import launch as legacy
from ..raw_kv_native_qk_run import runtime as native
ROOT=Path(__file__).resolve().parents[3]
PREFIX='candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/'
CONTRACT=PINS_PATH=PREFIX+'launch-contract.json'
PROFILE='qwen2-public-paired-m128-linked-launch-v1'
SETUP_PROFILE=prior.SETUP_PROFILE
ASSET_PROFILE=prior.ASSET_PROFILE
BASE_COMMIT=prior.BASE_COMMIT
M16_EVIDENCE_SHA256=prerequisite.EVIDENCE_SHA256
PRIOR_CONTRACT_SHA256='82dd02d6d6c298446fdc86f9f1e174a0014be2a476009061d09d6b483ea17689'
WORKFLOW='.github/workflows/raw-kv-public-pair-m128.yml'
OWN=tuple(PREFIX+n for n in ('launch.py','prepare.py','launch_bridge.patch','admission.py','test_admission.py','run_ci.py','test_run_ci.py','test_prepare.py','numeric_progress.py','test_numeric_progress.py','README.md'))+(WORKFLOW,)
SOURCE_COUNT=285
GENERATED_COUNT=12
SNAPSHOT_KEY='m128_recipe_launch'
GENERATED_MODULE_SHA256=prior.GENERATED_MODULE_SHA256
PHASE_LIMITS=prior.PHASE_LIMITS
SETUP=prerequisite.SETUP
HELPERS=tuple(prior.PREFIX+n for n in ('producer.py','admission.py'))
TARGETS=prior.TARGETS+HELPERS
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

def need(ok,reason='Public paired launch contract'):
    if not ok:raise ValueError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read_source(name,limit=4194304):
    need(ROOT==prior.ROOT==native.ROOT)
    return native.read_source(name,limit)

def contract_value():
    oldraw,old=prior.contract_value();need(sha(oldraw)==PRIOR_CONTRACT_SHA256)
    old_sources=dict(old['source_sha256']);old_sources[prior.PINS_PATH]=sha(oldraw)
    raw=read_source(CONTRACT,262144);value=native.json_bytes(raw)
    fixed=dict(schema=1,profile=PROFILE,base_commit=BASE_COMMIT,rows=128,past_tokens=0,enable_raw_kv=True,
        setup_profile=SETUP_PROFILE,asset_profile=ASSET_PROFILE,setup_budget=900,work_budget=2400,
        external_budget=2430,total_budget=3420,m16_evidence_sha256=M16_EVIDENCE_SHA256,
        prior_contract_sha256=PRIOR_CONTRACT_SHA256,generated_module_sha256=GENERATED_MODULE_SHA256)
    need(type(value) is dict and set(value)==set(fixed)|{'source_sha256','generated_sha256','bridge_sha256'})
    need(all(type(value[k]) is type(v) and value[k]==v for k,v in fixed.items()))
    sources=value['source_sha256'];generated=value['generated_sha256']
    need(type(sources) is dict and set(sources)==set(old_sources)|set(OWN))
    need(len(sources)+1==SOURCE_COUNT and all(native.relative_name(n) and native.digest(h) for n,h in sources.items()))
    need(all(sources[n]==h for n,h in old_sources.items()))
    need(sources[PREFIX+'launch.py']==IMPORTED_SHA256 and value['bridge_sha256']==sources[PREFIX+'launch_bridge.patch'])
    need(type(generated) is dict and set(generated)==set(old['generated_sha256'])|set(HELPERS) and len(generated)==GENERATED_COUNT)
    need(all(native.digest(h) for h in generated.values()))
    need(all(generated[n]==h for n,h in old['generated_sha256'].items() if n not in TARGETS))
    need(all(generated[n]!=old['generated_sha256'][n] for n in prior.TARGETS))
    need(all(generated[n]!=sources[n] for n in HELPERS))
    return raw,value

def contract_snapshot(*,composed=False):
    need(type(composed) is bool)
    raw,value=contract_value();sources=dict(value['source_sha256'])
    if composed:sources.update(value['generated_sha256'])
    blobs={CONTRACT:hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
    for name,identity in sources.items():
        content=read_source(name);need(sha(content)==identity,'M128 launch source drift')
        if not composed:blobs[name]=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
    sources[CONTRACT]=sha(raw)
    return dict(contract_sha256=sha(raw),sources=sources,inputs=sources,
        original_sources=value['source_sha256'],generated=value['generated_sha256'],git_blobs=blobs)

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

def setup_git_sources():return OWN+(CONTRACT,)

def source_snapshot():return contract_snapshot(composed=True)['sources']

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

def bind_snapshot(snapshot,identity,context):
    """Add a bounded linked identity to the original newly prepared snapshot."""
    need(type(snapshot) is dict and SNAPSHOT_KEY not in snapshot)
    need(type(snapshot.get('rows')) is int and snapshot['rows']==128)
    frozen=contract_snapshot(composed=True)
    need(snapshot['source_sha256']==frozen['sources'])
    need(context['contract_sha256']==frozen['contract_sha256'])
    from . import admission
    admission.revalidate(identity)
    need(identity.checkout_commit==context['checkout_commit'])
    result=dict(snapshot)
    result[SNAPSHOT_KEY]=dict(profile=PROFILE,checkout_commit=identity.checkout_commit,
        launch_contract_sha256=frozen['contract_sha256'],setup_receipt_sha256=identity.receipt_sha256,
        m16_evidence_sha256=prerequisite.EVIDENCE_SHA256)
    return result

def authorize_run(snapshot,*,wall_budget,enable_raw_kv,fresh_profile):
    """Require linked fresh setup before the original entry imports native code."""
    need(type(enable_raw_kv) is bool and enable_raw_kv is True and
         type(fresh_profile) is bool and fresh_profile is True)
    need(type(wall_budget) in (int,float) and math.isfinite(wall_budget) and 0<wall_budget<=2400)
    need(type(snapshot) is dict and type(snapshot.get('rows')) is int and snapshot['rows']==128)
    need(snapshot.get('enable_raw_kv') is True and snapshot.get('fresh_profile') is True)
    linked=snapshot.get(SNAPSHOT_KEY)
    keys={'profile','checkout_commit','launch_contract_sha256','setup_receipt_sha256','m16_evidence_sha256'}
    need(type(linked) is dict and set(linked)==keys)
    need(linked['profile']==PROFILE and linked['m16_evidence_sha256']==prerequisite.EVIDENCE_SHA256)
    need(type(linked['checkout_commit']) is str and len(linked['checkout_commit'])==40 and
         all(c in '0123456789abcdef' for c in linked['checkout_commit']))
    need(all(native.digest(linked[k]) for k in ('launch_contract_sha256','setup_receipt_sha256','m16_evidence_sha256')))
    frozen=contract_snapshot(composed=True)
    need(linked['launch_contract_sha256']==frozen['contract_sha256'])
    need(prerequisite.same(snapshot['source_sha256'],frozen['sources']))
    need(snapshot['source_manifest_sha256']==sha((json.dumps(frozen['sources'],sort_keys=True,indent=2)+'\n').encode()))
    fresh=snapshot.get('fresh_assets')
    need(type(fresh) is dict and set(fresh)=={'profile','manifest','manifest_sha256','enable_raw_kv'})
    need(fresh['profile']==ASSET_PROFILE and fresh['enable_raw_kv'] is True)
    need(type(fresh['manifest']) is str and native.digest(fresh['manifest_sha256']))
    workspace=Path(fresh['manifest']).parent
    need(Path(fresh['manifest']).name=='ASSETS.json')
    from . import admission
    identity=admission.verify_setup(workspace,workspace.parent/'setup_evidence/summary.json',
        checkout_commit=linked['checkout_commit'],enable_raw_kv=True,rows=128)
    need(str(identity.manifest)==fresh['manifest'] and identity.manifest_sha256==fresh['manifest_sha256'] and
         identity.receipt_sha256==linked['setup_receipt_sha256'])
    need(prerequisite.same(dict(identity.source_sha256),frozen['sources']))
    reference=snapshot.get('independent_reference')
    need(type(reference) is dict and type(reference.get('rows')) is int and reference['rows']==128 and
         type(reference.get('past_tokens')) is int and reference['past_tokens']==0)
    admission.revalidate(identity)
    return identity

def validate_backend_failure(value,sources):return legacy.validate_backend_failure(value,sources)


def backend_preflight(context_path):
    setup_module=None
    try:
        from ..raw_kv_public_fresh import setup as setup_module
        return setup_module.backend_preflight(context_path)
    except BaseException as error:
        try:
            sources=contract_snapshot(composed=True)['sources']
            stage,diagnostic=legacy._backend_diagnostic(error,sources,setup_loaded=setup_module is not None)
            value=validate_backend_failure(dict(schema=1,stage=stage,diagnostic=diagnostic,checks=legacy._backend_checks()),sources)
            legacy._write_backend_failure(context_path,value,setup_module)
        except BaseException:pass
        raise

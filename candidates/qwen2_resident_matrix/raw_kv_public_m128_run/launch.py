"""Exact M128 launch source contract and linked setup admission.

No producer or native library is loaded by this module. Runtime authorization
checks fresh private setup credentials and the frozen successful M16 evidence.
"""
import hashlib
import json
import math
from pathlib import Path

from ..raw_kv_public_m128 import prerequisite
from ..raw_kv_public_m128_runtime import runtime as prior

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
PREFIX='candidates/qwen2_resident_matrix/raw_kv_public_m128_run/'
CONTRACT=PINS_PATH=PREFIX+'launch-contract.json'
PROFILE='qwen2-public-m128-linked-launch-v1'
SETUP_PROFILE=prior.SETUP_PROFILE
ASSET_PROFILE='qwen2-public-pv16-fresh-assets-m128-v1'
M16_EVIDENCE_SHA256=prerequisite.EVIDENCE_SHA256
BASE_COMMIT=prior.BASE_COMMIT
PRIOR_CONTRACT_SHA256='865201564043f109b90467634b6006acb6db93f3263996d8db8c6562470bb767'
WORKFLOW='.github/workflows/raw-kv-public-m128.yml'
OWN=tuple(PREFIX+n for n in ('launch.py','prepare.py','launch_bridge.patch','admission.py',
    'test_admission.py','run_ci.py','test_run_ci.py','test_prepare.py','README.md'))+(WORKFLOW,)
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SETUP=prerequisite.SETUP


def need(ok, reason='M128 linked launch contract'):
    if not ok:raise ValueError(reason)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def read_source(name,limit=4194304):
    need(ROOT==prior.ROOT)
    return prior.read_source(name,limit)


def contract_value():
    raw=read_source(CONTRACT,131072);value=prior.prior.json_bytes(raw)
    fixed=dict(schema=1,profile=PROFILE,base_commit=BASE_COMMIT,rows=128,past_tokens=0,
        enable_raw_kv=True,setup_budget=900,work_budget=2400,external_budget=2430,total_budget=3420,
        m16_evidence_sha256=prerequisite.EVIDENCE_SHA256,prior_contract_sha256=PRIOR_CONTRACT_SHA256)
    need(type(value) is dict and set(value)==set(fixed)|{'source_sha256','generated_sha256','bridge_sha256'})
    need(all(type(value[k]) is type(v) and value[k]==v for k,v in fixed.items()))
    old_raw,old=prior.contract_value();need(sha(old_raw)==PRIOR_CONTRACT_SHA256)
    old_sources=dict(old['source_sha256']);old_sources[prior.PINS_PATH]=sha(old_raw)
    sources=value['source_sha256'];generated=value['generated_sha256']
    need(type(sources) is dict and set(sources)==set(old_sources)|set(OWN))
    need(all(prior.prior.relative_name(n) and prior.prior.digest(h) for n,h in sources.items()))
    need(all(sources[n]==h for n,h in old_sources.items()))
    need(sources[PREFIX+'launch.py']==IMPORTED_SHA256)
    need(value['bridge_sha256']==sources[PREFIX+'launch_bridge.patch'])
    need(type(generated) is dict and set(generated)==set(old['generated_sha256']) and len(generated)==10)
    changed=set(prerequisite.VARIANTS)
    need(all(prior.prior.digest(h) for h in generated.values()))
    need(all(generated[n]==h for n,h in old['generated_sha256'].items() if n not in changed))
    need(all(generated[n]!=old['generated_sha256'][n] for n in changed))
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
    expected=asset_source_snapshot(enable_raw_kv=True)
    need(prerequisite.same(sources,expected));return dict(expected)


def base_verifier_sources():
    _,value=contract_value();sources=dict(value['source_sha256']);sources.update(value['generated_sha256'])
    prefix='candidates/qwen2_resident_matrix/raw_kv_public_fresh/'
    return {prefix+n:sources[prefix+n] for n in ('assets.py','official_entry.patch','public_entry.patch',
        'prepare.py','pins.json','README.md','test_assets.py')}


def verify_loaded_setup(identity):
    need(prior.prior.digest(identity))
    need(identity==contract_snapshot(composed=True)['generated'][SETUP])


def setup_git_sources():return OWN+(CONTRACT,)


def bind_snapshot(snapshot,identity,context):
    """Add a bounded linked identity to the original newly prepared snapshot."""
    need(type(snapshot) is dict and 'm128_launch' not in snapshot)
    need(type(snapshot.get('rows')) is int and snapshot['rows']==128)
    frozen=contract_snapshot(composed=True)
    need(snapshot['source_sha256']==frozen['sources'])
    need(context['contract_sha256']==frozen['contract_sha256'])
    from . import admission
    admission.revalidate(identity)
    need(identity.checkout_commit==context['checkout_commit'])
    result=dict(snapshot)
    result['m128_launch']=dict(profile=PROFILE,checkout_commit=identity.checkout_commit,
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
    linked=snapshot.get('m128_launch')
    keys={'profile','checkout_commit','launch_contract_sha256','setup_receipt_sha256','m16_evidence_sha256'}
    need(type(linked) is dict and set(linked)==keys)
    need(linked['profile']==PROFILE and linked['m16_evidence_sha256']==prerequisite.EVIDENCE_SHA256)
    need(type(linked['checkout_commit']) is str and len(linked['checkout_commit'])==40 and
         all(c in '0123456789abcdef' for c in linked['checkout_commit']))
    need(all(prior.prior.digest(linked[k]) for k in ('launch_contract_sha256','setup_receipt_sha256','m16_evidence_sha256')))
    frozen=contract_snapshot(composed=True)
    need(linked['launch_contract_sha256']==frozen['contract_sha256'])
    need(prerequisite.same(snapshot['source_sha256'],frozen['sources']))
    need(snapshot['source_manifest_sha256']==sha((json.dumps(frozen['sources'],sort_keys=True,indent=2)+'\n').encode()))
    fresh=snapshot.get('fresh_assets')
    need(type(fresh) is dict and set(fresh)=={'profile','manifest','manifest_sha256','enable_raw_kv'})
    need(fresh['profile']=='qwen2-public-pv16-fresh-assets-m128-v1' and fresh['enable_raw_kv'] is True)
    need(type(fresh['manifest']) is str and prior.prior.digest(fresh['manifest_sha256']))
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

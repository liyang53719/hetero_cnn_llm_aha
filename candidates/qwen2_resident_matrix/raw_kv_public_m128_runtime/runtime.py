"""Versioned M128 setup source admission; numerical launch remains unavailable."""
import hashlib
import json
from pathlib import Path

from ..raw_kv_public_m128 import profile as prior
from ..raw_kv_public_m128 import prerequisite

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_public_m128_runtime/'
PINS_PATH = PREFIX + 'pins.json'
PROFILE = 'qwen2-public-m128-setup-runtime-v1'
SETUP_PROFILE = 'qwen2-public-fresh-m128-setup-v1'
BASE_COMMIT = '72ca5e52f97490fa80fd94eac056f338e25ba7fc'
STATUS = 'SETUP_SOURCE_READY_NUMERIC_BLOCKED'
OWN = ('runtime.py','prepare.py','bridging.patch','setup128.patch',
       'test_setup_runtime.py','test_runtime.py','README.md')
PATCHES = ('setup128.patch','bridging.patch')
IMPORTED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SETUP = prerequisite.SETUP


def need(ok, reason='M128 setup runtime contract'):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_source(name, limit=4194304):
    # Same bounded regular-file checks as the frozen preparation profile.
    need(ROOT == prior.ROOT, 'M128 source root differs')
    return prior.read_source(name, limit)


def contract_value():
    raw = read_source(PINS_PATH, 131072)
    value = prior.json_bytes(raw)
    fixed = dict(schema=1,profile=PROFILE,base_commit=BASE_COMMIT,status=STATUS,
        rows=128,past_tokens=0,enable_raw_kv=True,setup_budget=900,
        work_budget=2400,external_budget=2430,outer_budget=3420,
        m16_evidence_sha256=prerequisite.EVIDENCE_SHA256)
    need(type(value) is dict and set(value)==set(fixed)|{'source_sha256','patch_sha256','generated_sha256'})
    need(all(type(value[k]) is type(v) and value[k]==v for k,v in fixed.items()))
    # Check the immutable previous contract without assuming its generated files
    # are currently installed: this function also runs inside the final overlay.
    old_raw = read_source(prior.PINS,131072)
    old = prior.validate_contract(prior.json_bytes(old_raw))
    old_inputs = dict(old['source_sha256']); old_inputs[prior.PINS]=sha(old_raw)
    names=set(old_inputs)|{PREFIX+n for n in OWN}
    sources=value['source_sha256']; generated=value['generated_sha256']
    need(type(sources) is dict and set(sources)==names)
    need(all(prior.relative_name(n) and prior.digest(h) for n,h in sources.items()))
    need(all(sources[n]==h for n,h in old_inputs.items()),'frozen preparation identity changed')
    need(sources[PREFIX+'runtime.py']==IMPORTED_SHA256,'loaded runtime identity differs')
    need(type(value['patch_sha256']) is dict and set(value['patch_sha256'])==set(PATCHES))
    need(all(value['patch_sha256'][n]==sources[PREFIX+n] for n in PATCHES))
    need(type(generated) is dict and set(generated)==set(old['generated_sha256'])|{SETUP})
    need(len(generated)==10 and all(prior.digest(h) for h in generated.values()))
    changed={prerequisite.ENTRY,prerequisite.ASSETS}
    need(all(generated[n]==h for n,h in old['generated_sha256'].items() if n not in changed))
    need(all(generated[n]!=old['generated_sha256'][n] for n in changed))
    need(generated[SETUP]!=sources[SETUP])
    return raw,value


def contract_snapshot(*, composed=False):
    need(type(composed) is bool)
    raw,value=contract_value()
    expected=dict(value['source_sha256'])
    if composed:
        expected.update(value['generated_sha256'])
    for name,identity in expected.items():
        need(sha(read_source(name))==identity,'M128 setup frozen source drift')
    expected[PINS_PATH]=sha(raw)
    return dict(status=STATUS,profile=PROFILE,inputs=expected,
        generated=dict(value['generated_sha256']),pins_sha256=sha(raw),
        setup_source_ready=True,numerical_launch_ready=False,
        m128_executed=False,full_29_node_acceptance=False)


def asset_source_snapshot(*, enable_raw_kv=False):
    need(type(enable_raw_kv) is bool and enable_raw_kv is True,'explicit raw M128 required')
    result=contract_snapshot(composed=True)
    replacements={n:result['generated'][n] for n in prerequisite.VARIANTS}
    prerequisite.compatible_sources(result['inputs'],replacements,
        profile=prerequisite.PROFILE,rows=128,past_tokens=0)
    return result['inputs']


def own_asset_sources():
    """Explicit complete runtime closure, including the setup implementation."""
    return asset_source_snapshot(enable_raw_kv=True)


def setup_source_snapshot(enabled):
    return asset_source_snapshot(enable_raw_kv=enabled)


def asset_sources(sources):
    expected=asset_source_snapshot(enable_raw_kv=True)
    need(prerequisite.same(sources,expected),'asset/setup closed map differs')
    return dict(expected)


def base_verifier_sources():
    _,value=contract_value()
    sources=dict(value['source_sha256']); sources.update(value['generated_sha256'])
    prefix='candidates/qwen2_resident_matrix/raw_kv_public_fresh/'
    names=('assets.py','official_entry.patch','public_entry.patch','prepare.py','pins.json','README.md','test_assets.py')
    return {prefix+n:sources[prefix+n] for n in names}


def verify_loaded_setup(identity):
    need(prior.digest(identity))
    result=contract_snapshot(composed=True)
    need(identity==result['generated'][SETUP],'loaded setup variant differs')


def setup_git_sources():
    """Generated overlays are checked by their map, never asserted clean Git."""
    return tuple(PREFIX+n for n in OWN)+(PINS_PATH,)


def authorize_run(snapshot, *, wall_budget, enable_raw_kv, fresh_profile):
    # Setup readiness is not a linked numerical credential. Do not let the new
    # budget branch execute until the separate launch/admission layer is reviewed.
    need(type(enable_raw_kv) is bool and enable_raw_kv is True and
         type(fresh_profile) is bool and fresh_profile is True)
    need(type(snapshot) is dict and type(snapshot.get('rows')) is int and snapshot['rows']==128)
    asset_source_snapshot(enable_raw_kv=True)
    raise ValueError('M128 linked numerical admission unavailable: launch_layer_missing')

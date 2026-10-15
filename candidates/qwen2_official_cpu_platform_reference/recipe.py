"""Independent new-contract recipe; existing prepare/source checks stay intact."""
import importlib.util
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
# Only cold package imports need the repo path; do not leave a new numerical
# import search path installed in the capture worker.
sys.path.insert(0,str(ROOT))
try:
    from candidates.qwen2_official_cpu_platform_reference import policy as P,validator as V,capture_source as CS
finally:sys.path.pop(0)
CI=ROOT/'candidates/qwen2_fullblock_ci_reference'
spec=importlib.util.spec_from_file_location('_new_reference_original_ci_recipe',CI/'recipe.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
# Verify the existing package before executing any of its other adapters.
C.source_manifest()
for key in dir(C):
    if not key.startswith('_') and key not in ('ROOT','HERE','WORK','PACKAGE','source_manifest','source_check','main'):
        globals()[key]=getattr(C,key)
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
WORK='work/qwen2_official_cpu_platform_reference'
PACKAGE=P.PACKAGE
NEW_PLATFORM_REFERENCE_CONTRACT=P.policy()['contract_id']
RUN_ENV='QWEN2_NEW_REFERENCE_RUN'
_capture,validate_new_observations,derivation_proof=CS.load(ROOT)
validate_observations=validate_new_observations
observe_platform_before=V.observe_platform_before
observe_platform_after=V.observe_platform_after


def load_ci(name):
    need(name in ('issuer.py','lifecycle.py','backend_policy.py'),'fixed CI adapter source')
    expected=parse((CI/'SOURCE_MANIFEST.json').read_bytes())['files'][name]
    checked(ROOT,'candidates/qwen2_fullblock_ci_reference/'+name,expected)
    spec=importlib.util.spec_from_file_location('_new_reference_ci_'+name[:-3],CI/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def repeat_run_id():
    run=os.environ.get(RUN_ENV,'new01')
    need(run in ('new01','new02'),'fixed new reference pair run')
    return run


def source_manifest(root=ROOT):
    need(root==ROOT,'fixed source root')
    manifest=parse((HERE/'SOURCE_MANIFEST.json').read_bytes())
    exact_keys(manifest,('schema','files'),'new source manifest')
    need(manifest['schema']==1 and set(manifest['files'])==set(P.FILES),'exact declared new sources')
    present={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file()}
    need(present==set(P.FILES)|{'SOURCE_MANIFEST.json'},'exact new source inventory')
    for name,spec in manifest['files'].items():checked(root,PACKAGE+'/'+name,spec)
    return identity(HERE/'SOURCE_MANIFEST.json')


def source_check(root,pins):
    source_manifest(root)
    profile=dependency('candidates/qwen2_fullblock_ci_execution/runtime_profile.py')
    need(profile.profile()==P.PROFILE and profile.mkldnn_enabled() is False,'only explicit new backend profile')
    need('QWEN2_REFERENCE_REPEAT_RUN' not in os.environ,'old repeat protocol not reused')
    return C.source_check(root,pins)


def bootstrap_policy():
    return {**C.bootstrap_policy(),'output_namespace':WORK,'new_reference_contract':P.policy(),'source_derivation':derivation_proof,
            'new_run_ids':['new01','new02'],'new_capture_manifest':'NEW_PLATFORM_REFERENCE_OBSERVATIONS_PENDING_REVIEW'}


def main(argv=None):
    need(argv in (None,[]),'cold check only; issuer owns binding admission')
    source_manifest()
    print(json.dumps(dict(status='NOT_EXECUTED_NEW_CONTRACT_PENDING',numeric_execution_allowed=False)))
    return 0

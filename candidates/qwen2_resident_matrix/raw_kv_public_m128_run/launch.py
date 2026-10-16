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


def _backend_failure_spec():
    stages=('setup_import','context_source','package_import','backend_identity','native_identity',
            'thread_configuration','thread_checks','evidence_write','unknown_backend')
    checks=('python_312','python_unoptimized','numpy_235','torch_210_cpu','torch_commit',
            'cpu_avx512','aten_override_absent','transformers_4401','mkldnn_enabled',
            'mkldnn_version','mkldnn_commit','intraop_4','interop_1','deterministic')
    exceptions=('ValueError','TypeError','KeyError','OSError','FileNotFoundError','PermissionError',
        'ImportError','ModuleNotFoundError','RuntimeError','TimeoutError','TimeoutExpired',
        'CalledProcessError','InterruptedError','KeyboardInterrupt','SetupError','OtherError')
    return stages,checks,exceptions


def _backend_checks():
    """Diagnostic getters only; never import/retry a numerical package or forward."""
    import os
    import sys
    result={name:None for name in _backend_failure_spec()[1]}
    result.update(python_312=sys.version_info[:2]==(3,12),python_unoptimized=sys.flags.optimize==0,
                  aten_override_absent=os.getenv('ATEN_CPU_CAPABILITY') is None)
    def sample(name,module,getter):
        loaded=sys.modules.get(module)
        if loaded is not None:
            try:
                value=getter(loaded)
                if type(value) is bool:result[name]=value
            except BaseException:pass
    sample('numpy_235','numpy',lambda m:vars(m).get('__version__')=='2.3.5')
    sample('torch_210_cpu','torch',lambda m:vars(m).get('__version__')=='2.10.0+cpu')
    sample('torch_commit','torch.version',lambda m:vars(m).get('git_version')=='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0')
    sample('cpu_avx512','torch.backends.cpu',lambda m:vars(m)['get_cpu_capability']()=='AVX512')
    sample('transformers_4401','transformers',lambda m:vars(m).get('__version__')=='4.40.1')
    sample('mkldnn_enabled','torch.backends.mkldnn',lambda m:m.enabled is True)
    sample('mkldnn_version','torch.__config__',lambda m:'3.7.1' in vars(m)['show']())
    sample('mkldnn_commit','torch.__config__',lambda m:'8d263e693366ef8db40acc569cc7d8edf644556d' in vars(m)['show']())
    sample('intraop_4','torch',lambda m:vars(m)['get_num_threads']()==4)
    sample('interop_1','torch',lambda m:vars(m)['get_num_interop_threads']()==1)
    sample('deterministic','torch',lambda m:vars(m)['are_deterministic_algorithms_enabled']() is True)
    return result


def _backend_diagnostic(error,sources,*,setup_loaded):
    """Classify verified repository function names, without exception text/locals."""
    kind=type(error).__name__
    if kind not in _backend_failure_spec()[2]:kind='OtherError'
    frames=[];functions=[];checked={};tb=error.__traceback__
    while tb is not None:
        try:
            name=str(Path(tb.tb_frame.f_code.co_filename).resolve().relative_to(ROOT.resolve()))
            if name in sources:
                if name not in checked:checked[name]=sha(read_source(name))==sources[name]
                if checked[name] and type(tb.tb_lineno) is int and 0<tb.tb_lineno<100000:
                    frames.append(dict(source=name,line=tb.tb_lineno))
                    functions.append((name,tb.tb_frame.f_code.co_name))
        except (OSError,ValueError,TypeError):pass
        tb=tb.tb_next
    names={function for _,function in functions}
    if not setup_loaded:stage='setup_import'
    elif names & {'_read_context','source_snapshot','asset_sources','contract_snapshot','contract_value'}:stage='context_source'
    elif kind in ('ImportError','ModuleNotFoundError'):stage='package_import'
    elif 'runtime_identity' in names:stage='native_identity'
    elif 'backend_threads' in names:stage='thread_checks'
    elif names & {'private_json','atomic_json'}:stage='evidence_write'
    elif 'backend_identity' in names:stage='backend_identity'
    elif (SETUP,'backend_preflight') in functions:stage='thread_configuration'
    else:stage='unknown_backend'
    return stage,dict(phase='environment',exception=kind,frames=frames[-3:])


def validate_backend_failure(value,sources):
    """Exact public projection; no commands, exception strings or private paths."""
    stages,checks,exceptions=_backend_failure_spec()
    need(type(value) is dict and set(value)=={'schema','stage','diagnostic','checks'})
    need(type(value['schema']) is int and value['schema']==1 and
         type(value['stage']) is str and value['stage'] in stages)
    need(type(value['checks']) is dict and set(value['checks'])==set(checks) and
         all(item is None or type(item) is bool for item in value['checks'].values()))
    diagnostic=value['diagnostic']
    need(type(diagnostic) is dict and set(diagnostic)=={'phase','exception','frames'} and
         diagnostic['phase']=='environment' and type(diagnostic['exception']) is str and
         diagnostic['exception'] in exceptions and type(diagnostic['frames']) is list and len(diagnostic['frames'])<=3)
    for frame in diagnostic['frames']:
        need(type(frame) is dict and set(frame)=={'source','line'} and type(frame['source']) is str and
             frame['source'] in set(sources)|set(OWN) and prior.prior.relative_name(frame['source']) and
             type(frame['line']) is int and 0<frame['line']<100000)
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    need(len(raw)<=4096)
    return json.loads(raw)


def _write_backend_failure(context_path,value,setup_module):
    """Known private sibling only; the fallback also handles setup import failure."""
    import os
    import stat
    path=Path(context_path)
    need(path.is_absolute() and '..' not in path.parts and path.name=='context.json')
    need(all(not part.is_symlink() for part in (path,*path.parents)) and
         stat.S_ISREG(path.stat().st_mode) and path.parent.is_dir())
    target=path.parent/'backend.failure.json'
    need(not target.exists() and not target.is_symlink())
    if setup_module is not None:
        setup_module.atomic_json(target,value,4096)
        return
    raw=(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    need(len(raw)<=4096)
    temporary=target.with_name(target.name+'.pending');created=False
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);created=True
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target);created=False
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if created:
            try:temporary.unlink()
            except OSError:pass


def backend_preflight(context_path):
    """Run the original gate once; retain bounded failure metadata and re-raise."""
    setup_module=None
    try:
        from ..raw_kv_public_fresh import setup as setup_module
        return setup_module.backend_preflight(context_path)
    except BaseException as error:
        try:
            try:sources=contract_snapshot(composed=True)['sources']
            except BaseException:
                sources={}
                for name in OWN:
                    try:sources[name]=sha(read_source(name))
                    except (OSError,ValueError):pass
            stage,diagnostic=_backend_diagnostic(error,sources,setup_loaded=setup_module is not None)
            value=validate_backend_failure(dict(schema=1,stage=stage,diagnostic=diagnostic,checks=_backend_checks()),sources)
            _write_backend_failure(context_path,value,setup_module)
        except BaseException:pass  # Never replace the original gate/import failure.
        raise


def _native_failure_spec():
    stages=tuple(sorted(('x','n0','qr','kr','v','q','k','cache_k','cache_v','repeat_k','repeat_v',
        'scores','logits','prob','pv','att','o','r','n1','gate','up','silu','act','down','y',
        'cos','sin','mask','softmax_fp32')))
    semantics=('mask_exact','native_fp32_probability_sum_within_2e_5',
        'independent_fp32_probability_sum_within_2e_5','native_cache_append_k_exact',
        'native_cache_append_v_exact','independent_cache_append_k_exact',
        'independent_cache_append_v_exact','native_future_probability_zero',
        'independent_future_probability_zero')
    return stages,semantics


def _native_failure_policy():
    """Read the frozen original tolerances without importing its numerical code."""
    import re
    name='spec/numerical_contract.md';raw=read_source(name)
    need(sha(raw)=='5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5')
    result={}
    for key,title in (('operator','BF16 single operator'),('block','BF16 one Transformer block')):
        match=re.search(re.escape(title)+r':\s+max_abs <= ([0-9.eE+-]+)\s+mean_abs <= ([0-9.eE+-]+)',raw.decode())
        need(match is not None)
        result[key]=dict(max_abs=float(match[1]),mean_abs=float(match[2]))
    return result,sha(raw)


def _native_failure_stage(name,stage,mode,limits,*,original):
    """Recompute only the original metadata verdict; no arrays or arithmetic runs."""
    need(type(stage) is dict)
    for key in ('max_abs','mean_abs'):
        need(type(stage.get(key)) in (int,float) and math.isfinite(stage[key]) and stage[key]>=0)
    need(stage.get('finite') is True and type(stage.get('bit_exact')) is bool)
    if name=='mask':
        passed=stage['bit_exact'];expected_limits=None;contract='exact_causal_mask'
    elif mode=='fp32' or name=='softmax_fp32':
        passed=None;expected_limits=None;contract=None
        if original:need(stage.get('status')=='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE')
    else:
        kind='block' if name=='y' else 'operator';expected_limits=limits[kind]
        passed=stage['max_abs']<=expected_limits['max_abs'] and stage['mean_abs']<=expected_limits['mean_abs']
        contract='spec/numerical_contract.md:'+kind
    need(type(stage.get('passed')) is type(passed) and stage['passed']==passed)
    if original:need(stage.get('contract')==contract)
    need(prerequisite.same(stage.get('limits'),expected_limits))
    return dict(max_abs=stage['max_abs'],mean_abs=stage['mean_abs'],limits=expected_limits,
                passed=passed,finite=True,bit_exact=stage['bit_exact'])


def _native_failure_mode(mode,phase,failed,semantics):
    need(type(phase) is dict and type(phase.get('failed_stages')) is list and
         phase['failed_stages']==failed and all(type(name) is str for name in phase['failed_stages']))
    checks=phase.get('semantics')
    need(type(checks) is dict and set(checks)==set(semantics) and all(type(v) is bool for v in checks.values()))
    exact=all(checks.values())
    need(type(phase.get('all_semantics_exact')) is bool and phase['all_semantics_exact']==exact)
    status=('PASS_BF16_STAGE_BUDGET' if not failed and exact else 'FAIL_BF16_STAGE_BUDGET') if mode=='bf16' else ('DIAGNOSTIC_FP32' if exact else 'FAIL_FP32_SEMANTICS')
    need(phase.get('status')==status)
    return dict(status=status,failed_stages=list(failed),semantics=dict(checks),all_semantics_exact=exact)


def validate_native_failure(value):
    """Strict diagnostic-only projection; a passing native receipt is never admitted."""
    fixed=dict(schema=1,status='NATIVE128_FAILURE_DIAGNOSTIC',tokens=128,carried=False,
        incomplete=True,postflight_complete=False,numerical_acceptance=False,actual_chain_executed=False,
        native_status='FAIL_BF16_STAGE_BUDGET')
    need(type(value) is dict and set(value)==set(fixed)|{'result_sha256','source_sha256','approved_limits','bf16_stages','modes'})
    need(all(type(value[k]) is type(want) and value[k]==want for k,want in fixed.items()))
    need(prior.prior.digest(value['result_sha256']) and
         value['source_sha256']=='917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85')
    limits,_=_native_failure_policy();need(prerequisite.same(value['approved_limits'],limits))
    stages,semantics=_native_failure_spec();observed=value['bf16_stages'];modes=value['modes']
    need(type(observed) is dict and set(observed)==set(stages) and type(modes) is dict and set(modes)=={'bf16','fp32'})
    for name,stage in observed.items():
        need(type(stage) is dict and set(stage)=={'max_abs','mean_abs','limits','passed','finite','bit_exact'})
        need(prerequisite.same(stage,_native_failure_stage(name,stage,'bf16',limits,original=False)))
    bf16_failed=[name for name in stages if observed[name]['passed'] is False]
    for mode in ('bf16','fp32'):
        item=modes[mode]
        need(type(item) is dict and set(item)=={'status','failed_stages','semantics','all_semantics_exact'})
        failed=bf16_failed if mode=='bf16' else ([] if item.get('semantics',{}).get('mask_exact') is True else ['mask'])
        need(prerequisite.same(item,_native_failure_mode(mode,item,failed,semantics)))
    need(modes['bf16']['semantics']['mask_exact'] is observed['mask']['bit_exact'])
    need(modes['bf16']['status']=='FAIL_BF16_STAGE_BUDGET' or modes['fp32']['all_semantics_exact'] is False)
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    need(len(raw)<=16384)
    return json.loads(raw)


def project_native_failure(value,*,result_sha256,source_sha256):
    """Project a completed failed native128 RESULT, retaining every failure class."""
    script='scripts/qwen2_layer0_model_gate.py'
    need(source_sha256=='917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85' and
         sha(read_source(script))==source_sha256 and prior.prior.digest(result_sha256))
    fixed=dict(schema_version=1,status='FAIL_BF16_STAGE_BUDGET',tokens=128,carried=False,layer=0,
               official_framework_forward=True,rtl_execution=False,hardware_recipe_acceptance=False)
    need(type(value) is dict and all(type(value.get(k)) is type(want) and value[k]==want for k,want in fixed.items()))
    need(type(value.get('identity')) is dict and value['identity'].get('runner_sha256')==source_sha256)
    limits,policy_sha=_native_failure_policy();policy=value.get('policy')
    need(type(policy) is dict and policy.get('source')=='spec/numerical_contract.md' and policy.get('sha256')==policy_sha and
         all(prerequisite.same(policy.get(k),v) for k,v in limits.items()))
    stages,semantics=_native_failure_spec();modes=value.get('modes');safe_modes={};bf16={}
    need(type(modes) is dict and set(modes)=={'bf16','fp32'})
    for mode in ('bf16','fp32'):
        item=modes[mode]
        need(type(item) is dict and type(item.get('phases')) is list and len(item['phases'])==1)
        phase=item['phases'][0]
        need(type(phase) is dict and type(phase.get('phase')) is int and phase['phase']==0 and
             type(phase.get('past_tokens')) is int and phase['past_tokens']==0)
        for key in ('token_ids','position_ids'):
            need(type(phase.get(key)) is list and phase[key]==list(range(128)) and all(type(n) is int for n in phase[key]))
        observed=phase.get('stages');need(type(observed) is dict and set(observed)==set(stages))
        projected={name:_native_failure_stage(name,observed[name],mode,limits,original=True) for name in stages}
        failed=[name for name in stages if projected[name]['passed'] is False]
        safe_modes[mode]=_native_failure_mode(mode,phase,failed,semantics)
        need(safe_modes[mode]['semantics']['mask_exact'] is projected['mask']['bit_exact'])
        if mode=='bf16':bf16=projected
    result=dict(schema=1,status='NATIVE128_FAILURE_DIAGNOSTIC',tokens=128,carried=False,
        incomplete=True,postflight_complete=False,numerical_acceptance=False,actual_chain_executed=False,
        native_status='FAIL_BF16_STAGE_BUDGET',result_sha256=result_sha256,source_sha256=source_sha256,
        approved_limits=limits,bf16_stages=bf16,modes=safe_modes)
    return validate_native_failure(result)

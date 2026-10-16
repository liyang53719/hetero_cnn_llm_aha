"""Native-only combined QKV/QK validation; no producer is run on import."""
import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import time

from ..raw_kv_native_qk import kernel
from ..raw_kv_native_qkv import kernel as qkv_kernel

ROOT=Path(__file__).resolve().parents[3]
SOURCE='candidates/qwen2_resident_matrix/raw_kv_native_qk_run/phase.py'
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
PHASES=('kernel','native16','native128')
PHASE_CAPS=dict(kernel=30,native16=60,native128=120)
MAX_REPORT=16384
SEMANTICS=('mask_exact','native_fp32_probability_sum_within_2e_5',
    'independent_fp32_probability_sum_within_2e_5','native_cache_append_k_exact',
    'native_cache_append_v_exact','independent_cache_append_k_exact',
    'independent_cache_append_v_exact','native_future_probability_zero',
    'independent_future_probability_zero')
CONFIG=dict(hidden_size=1536,intermediate_size=8960,num_attention_heads=12,num_key_value_heads=2)


def need(ok):
    if not ok:raise ValueError('native QKV/QK phase contract')


def same(a,b):return kernel.encoded(a)==kernel.encoded(b)
def canonical(value):return kernel.json_bytes(kernel.encoded(value),1048576)
def finite(value):return type(value) in (int,float) and math.isfinite(value) and value>=0


def helpers():
    """Only three hash-bound original metadata helpers; never import native code."""
    raw=kernel.source(kernel.ORIGINAL)
    need(kernel.sha(raw)==qkv_kernel.FIXED[kernel.ORIGINAL])
    tree=ast.parse(raw);names={'load_policy','stage_verdict','expected_shapes'}
    body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    need(len(body)==3)
    namespace={'Path':Path,'sha':lambda path:kernel.sha(kernel.read(path))}
    exec(compile(ast.Module(body=body,type_ignores=[]),kernel.ORIGINAL,'exec'),namespace)
    stage_node=next(node.value for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='REQUIRED_STAGES' for target in node.targets))
    stages=tuple(sorted(ast.literal_eval(stage_node)));need(len(stages)==29)
    need(kernel.sha(kernel.source(kernel.SPEC))==qkv_kernel.FIXED[kernel.SPEC])
    return namespace,stages,namespace['load_policy'](ROOT)


def _stage(name,item,mode,policy,helper,*,original):
    need(type(item) is dict and all(finite(item.get(k)) for k in ('max_abs','mean_abs')))
    need(item.get('finite') is True and type(item.get('bit_exact')) is bool)
    verdict=helper(name,item,mode,policy)
    need(type(item.get('passed')) is type(verdict['passed']) and item['passed']==verdict['passed'])
    need(same(item.get('limits'),verdict.get('limits')))
    if original:need(all(same(item.get(k),v) for k,v in verdict.items()))
    return dict(max_abs=item['max_abs'],mean_abs=item['mean_abs'],finite=True,
        bit_exact=item['bit_exact'],limits=verdict.get('limits'),passed=verdict['passed'])


def _mode(mode,item,failed):
    need(type(item) is dict and same(item.get('failed_stages'),failed))
    semantics=item.get('semantics')
    need(type(semantics) is dict and set(semantics)==set(SEMANTICS) and
        all(type(value) is bool for value in semantics.values()))
    exact=all(semantics.values())
    need(type(item.get('all_semantics_exact')) is bool and item['all_semantics_exact']==exact)
    status=('PASS_BF16_STAGE_BUDGET' if not failed and exact else 'FAIL_BF16_STAGE_BUDGET') if mode=='bf16' else ('DIAGNOSTIC_FP32' if exact else 'FAIL_FP32_SEMANTICS')
    need(item.get('status')==status)
    return dict(status=status,failed_stages=list(failed),semantics=dict(semantics),all_semantics_exact=exact)


def validate_report(value):
    """Strict public projection. Neither paths nor arbitrary producer text survive."""
    fixed=dict(schema=1,carried=False,stage_count=29,assigned_bf16_checks=28,backend_order_proven=False,
        export_count=116,postflight_complete=True,actual_chain_executed=False,rtl_execution=False)
    hashes=('result_sha256','source_manifest_sha256','contract_sha256','original_module_sha256',
        'generated_module_sha256','library_sha256','library_receipt_sha256','recipe_pins_sha256',
        'payload_manifest_sha256','qkv_library_sha256','qkv_library_receipt_sha256','qkv_recipe_pins_sha256')
    keys=set(fixed)|set(hashes)|{'tokens','status','native_status','native_acceptance','approved_limits',
        'bf16_stages','modes','m16_result_sha256'}
    need(type(value) is dict and set(value)==keys)
    need(all(type(value[k]) is type(v) and value[k]==v for k,v in fixed.items()))
    need(type(value['tokens']) is int and value['tokens'] in (16,128) and all(kernel.digest(value[k]) for k in hashes))
    need(value['original_module_sha256']==qkv_kernel.FIXED[kernel.ORIGINAL])
    need(value['m16_result_sha256'] is None if value['tokens']==16 else kernel.digest(value['m16_result_sha256']))
    funcs,stages,policy=helpers();limits={key:policy[key] for key in ('operator','block')}
    need(same(value['approved_limits'],limits))
    observed=value['bf16_stages'];modes=value['modes']
    need(type(observed) is dict and set(observed)==set(stages) and type(modes) is dict and set(modes)=={'bf16','fp32'})
    for name,item in observed.items():
        need(type(item) is dict and set(item)=={'max_abs','mean_abs','finite','bit_exact','limits','passed'})
        need(same(item,_stage(name,item,'bf16',policy,funcs['stage_verdict'],original=False)))
    for mode in ('bf16','fp32'):
        item=modes[mode]
        need(type(item) is dict and set(item)=={'status','failed_stages','semantics','all_semantics_exact'})
        failed=[name for name in stages if observed[name]['passed'] is False] if mode=='bf16' else ([] if item.get('semantics',{}).get('mask_exact') is True else ['mask'])
        need(same(item,_mode(mode,item,failed)))
    need(modes['bf16']['semantics']['mask_exact'] is observed['mask']['bit_exact'])
    passed=modes['bf16']['status']=='PASS_BF16_STAGE_BUDGET' and modes['fp32']['all_semantics_exact']
    need(type(value['native_acceptance']) is bool and value['native_acceptance']==passed)
    need(value['native_status']==('PASS_BF16_STAGE_BUDGET' if passed else 'FAIL_BF16_STAGE_BUDGET'))
    need(value['status']==('COMPLETE_NATIVE_VALIDATION' if passed else 'FAIL_NATIVE_VALIDATION'))
    need(len(kernel.encoded(value))<=MAX_REPORT)
    return canonical(value)


def combined_identity(library,qkv_library):
    return dict(profile=kernel.PROFILE,
        qkv=dict(profile=qkv_kernel.PROFILE,library_sha256=qkv_library['library_sha256'],
            source_sha256=qkv_library['source_sha256'],pins_sha256=qkv_library['pins_sha256']),
        qk=dict(library_sha256=library['library_sha256'],source_sha256=library['source_sha256'],
            pins_sha256=library['pins_sha256']),backend_order_proven=False)


def project_result(value,*,tokens,result_sha256,source_sha256,contract_sha256,generated_module_sha256,
                   library,qkv_library,payload_manifest_sha256,m16_result_sha256=None):
    need(type(tokens) is int and tokens in (16,128))
    fixed=dict(schema_version=1,tokens=tokens,carried=False,layer=0,torch_threads=4,
        official_framework_forward=True,rtl_execution=False,hardware_recipe_acceptance=False,
        logits=False,full_model_quality=False)
    need(type(value) is dict and all(type(value.get(k)) is type(v) and value[k]==v for k,v in fixed.items()))
    need(type(source_sha256) is dict and source_sha256.get(kernel.ORIGINAL)==qkv_kernel.FIXED[kernel.ORIGINAL] and
        all(type(n) is str and kernel.digest(h) for n,h in source_sha256.items()))
    need(value.get('payload_manifest_sha256')==payload_manifest_sha256 and value.get('m16_gate_sha256')==m16_result_sha256)
    recipe=combined_identity(library,qkv_library)
    need(type(value.get('identity')) is dict and value['identity'].get('runner_sha256')==generated_module_sha256 and
        same(value['identity'].get('independent_qkv_recipe'),recipe) and
        same(value.get('arithmetic',{}).get('independent_qkv'),recipe))
    funcs,stages,policy=helpers();need(same(value.get('policy'),policy))
    modes=value.get('modes');need(type(modes) is dict and set(modes)=={'bf16','fp32'})
    safe_modes={};bf16={}
    shapes=funcs['expected_shapes'](CONFIG,tokens,0)
    for mode in ('bf16','fp32'):
        item=modes[mode];need(type(item) is dict and type(item.get('phases')) is list and len(item['phases'])==1)
        phase=item['phases'][0]
        need(type(phase) is dict and type(phase.get('phase')) is int and phase['phase']==0 and
            type(phase.get('past_tokens')) is int and phase['past_tokens']==0)
        for key in ('token_ids','position_ids'):need(same(phase.get(key),list(range(tokens))))
        observed=phase.get('stages');need(type(observed) is dict and set(observed)==set(stages))
        projected={}
        for name in stages:
            stage=observed[name]
            need(same(stage.get('shape'),shapes[name]) and type(stage.get('elements')) is int and stage['elements']==math.prod(shapes[name]))
            projected[name]=_stage(name,stage,mode,policy,funcs['stage_verdict'],original=True)
        failed=[name for name in stages if projected[name]['passed'] is False]
        safe_modes[mode]=_mode(mode,phase,failed)
        need(safe_modes[mode]['semantics']['mask_exact'] is projected['mask']['bit_exact'])
        if mode=='bf16':bf16=projected
    passed=safe_modes['bf16']['status']=='PASS_BF16_STAGE_BUDGET' and safe_modes['fp32']['all_semantics_exact']
    native_status='PASS_BF16_STAGE_BUDGET' if passed else 'FAIL_BF16_STAGE_BUDGET'
    need(value.get('status')==native_status)
    report=dict(schema=1,tokens=tokens,carried=False,stage_count=29,assigned_bf16_checks=28,backend_order_proven=False,
        export_count=116,postflight_complete=True,actual_chain_executed=False,rtl_execution=False,
        status='COMPLETE_NATIVE_VALIDATION' if passed else 'FAIL_NATIVE_VALIDATION',native_status=native_status,
        native_acceptance=passed,result_sha256=result_sha256,source_manifest_sha256=kernel.sha(kernel.encoded(source_sha256)),
        contract_sha256=contract_sha256,original_module_sha256=qkv_kernel.FIXED[kernel.ORIGINAL],
        generated_module_sha256=generated_module_sha256,library_sha256=library['library_sha256'],
        library_receipt_sha256=library['receipt_sha256'],recipe_pins_sha256=library['pins_sha256'],
        qkv_library_sha256=qkv_library['library_sha256'],qkv_library_receipt_sha256=qkv_library['receipt_sha256'],
        qkv_recipe_pins_sha256=qkv_library['pins_sha256'],
        payload_manifest_sha256=payload_manifest_sha256,m16_result_sha256=m16_result_sha256,
        approved_limits={key:policy[key] for key in ('operator','block')},bf16_stages=bf16,modes=safe_modes)
    return validate_report(report)


def verify_exports(value,directory,tokens):
    """Hash all 116 original exports and validate geometry without array loading."""
    directory=kernel.safe_path(directory,directory=True);funcs,stages,_=helpers()
    shapes=funcs['expected_shapes'](CONFIG,tokens,0);identities=set()
    for mode in ('bf16','fp32'):
        observed=value['modes'][mode]['phases'][0]['stages']
        for name in stages:
            item=observed[name];shape=shapes[name]
            exported=[shape[0],shape[2],shape[1]*shape[3]] if name in ('q','k') else shape
            for kind in ('native','independent'):
                relative=f'{mode}/phase_0/{kind}_{name}.f32le'
                need(item.get(kind+'_file')==relative and same(item.get(kind+'_export_shape'),exported))
                path=kernel.safe_path(directory/relative);info=path.stat()
                need(info.st_size==4*math.prod(exported) and (info.st_dev,info.st_ino) not in identities)
                identities.add((info.st_dev,info.st_ino))
                digest=kernel.sha(kernel.read(path,8*1024*1024))
                need(digest==item.get(kind+'_file_sha256'))
                if name not in ('q','k'):need(digest==item.get('actual_f32_sha256' if kind=='native' else 'reference_f32_sha256'))
    need(len(identities)==116)


def validate_kernel_report(value):
    fixed=dict(schema=1,status='COMPLETE_KERNEL_BUILD',numerical_execution=False,backend_order_proven=False)
    hashes={'library_sha256','library_receipt_sha256','source_manifest_sha256',
        'contract_sha256','generated_module_sha256','recipe_pins_sha256',
        'qkv_library_sha256','qkv_library_receipt_sha256','qkv_recipe_pins_sha256'}
    need(type(value) is dict and set(value)==set(fixed)|hashes and
        all(type(value[k]) is type(v) and value[k]==v for k,v in fixed.items()) and
        all(kernel.digest(value[k]) for k in hashes))
    return canonical(value)


def _generated(path,expected):
    path=kernel.safe_path(path);need(not path.is_relative_to(ROOT))
    raw=kernel.read(path,1048576);need(kernel.sha(raw)==expected)
    spec=importlib.util.spec_from_file_location('qwen2_native_qkv_qk_generated',path)
    need(spec is not None)
    module=importlib.util.module_from_spec(spec)
    # Compile the exact checked bytes, never an independently resolved .pyc.
    exec(compile(raw,str(path),'exec'),module.__dict__)
    need(kernel.sha(kernel.read(path,1048576))==expected)
    return module


def phase_deadline(context,name):
    raw=os.getenv('QWEN2_NATIVE_QK_PHASE_END_NS')
    need(type(raw) is str and raw.isascii() and raw.isdecimal() and 1<=len(raw)<=24)
    end=int(raw);now=time.monotonic_ns()
    need(str(end)==raw and now<end<=context['deadline_ns'] and end<=now+PHASE_CAPS[name]*10**9)
    return end


def _phase_remaining(context,end):
    from . import runtime
    runtime.remaining(context,1)
    if end-6*10**9<=time.monotonic_ns():raise TimeoutError()


def _postflight(context,workspace,sources,end,library,qkv_library):
    from . import runtime
    _phase_remaining(context,end)
    need(same(runtime.source_snapshot(),sources))
    again,root=runtime.read_context(workspace/'validation_context.json')
    need(same(again,context) and root==workspace)
    need(kernel.sha(kernel.read(context['generated_module'],1048576))==context['generated_module_sha256'])
    need(same(kernel.verify(workspace/'qk_library'),library))
    need(same(qkv_kernel.verify(workspace/'qkv_library'),qkv_library))
    _phase_remaining(context,end)



MAX_DIAGNOSTICS=65536


def backend_build(identity):
    """Only validated build hashes and fixed, pinned implementation identities."""
    raw=kernel.source(kernel.ORIGINAL)
    need(kernel.sha(raw)==qkv_kernel.FIXED[kernel.ORIGINAL])
    tree=ast.parse(raw)
    expected=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='SOURCE_HASHES' for t in n.targets)))
    need(type(identity) is dict and identity.get('installed_sources_verified_exact') is True and
        same(identity.get('source_sha256'),expected))
    need(all(type(identity.get(k)) is str and len(identity[k].encode())<=65536 for k in ('torch_build','numpy_build')))
    return dict(torch_build_sha256=kernel.sha(identity['torch_build'].encode()),
        numpy_build_sha256=kernel.sha(identity['numpy_build'].encode()),
        torch_commit='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0',
        onednn_version='3.7.1',onednn_commit='8d263e693366ef8db40acc569cc7d8edf644556d',
        installed_sources_verified_exact=True,official_source_sha256=expected)


def validate_backend_build(value):
    raw=kernel.source(kernel.ORIGINAL);need(kernel.sha(raw)==qkv_kernel.FIXED[kernel.ORIGINAL])
    tree=ast.parse(raw)
    sources=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='SOURCE_HASHES' for t in n.targets)))
    fixed=dict(torch_commit='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0',onednn_version='3.7.1',
        onednn_commit='8d263e693366ef8db40acc569cc7d8edf644556d',installed_sources_verified_exact=True,
        official_source_sha256=sources)
    need(type(value) is dict and set(value)==set(fixed)|{'torch_build_sha256','numpy_build_sha256'} and
        all(same(value[k],v) for k,v in fixed.items()) and
        all(kernel.digest(value[k]) for k in ('torch_build_sha256','numpy_build_sha256')))
    return canonical(value)


def fenv_changes(value):
    def changed(a,b):
        if a is None or b is None or a.get('status')!='OBSERVED' or b.get('status')!='OBSERVED':return None
        return not same(a,b)
    loads=value['libraries'] or {}
    return dict(qkv_load=changed(loads.get('before'),loads.get('after_qkv')),
        qk_load=changed(loads.get('after_qkv'),loads.get('after_qk')),
        recipe=changed(value['before_recipe'],value['after_recipe']),
        gate=changed(value['after_recipe'],value['after_gate']))


def _completed_dispatch(observed):
    """FP32 may have no oneDNN event; BF16 requires recognized execution.

    This only admits observations after the caller's independent numerical and
    source postflight checks. Absence never identifies a backend or its order.
    """
    return (observed is not None and observed['bf16']['status']=='COMPLETE_DIAGNOSTIC' and
        observed['fp32']['status'] in ('COMPLETE_DIAGNOSTIC','NO_ONEDNN_EXECUTION_OBSERVED'))



def continuation_eligible(value):
    """Permit numerical comparison with incomplete info-only observations.

    This is not diagnostic completeness, CPU/ISA identity, or numerical PASS.
    Callers must independently require the original native acceptance receipt.
    """
    from . import dispatch_diagnostic as diagnostic
    value=validate_diagnostics(value)
    if not value['postflight_complete'] or value['cpu'] is None or value['backend_build'] is None:
        return False
    env=value['fenv'];loads=env['libraries']
    snapshots=list((loads or {}).values())+[env[k] for k in ('before_recipe','after_recipe','after_gate')]
    if len(snapshots)!=6 or any(v is None or v['status']!='OBSERVED' for v in snapshots):
        return False
    observed=value['capture']
    if observed is None:return False
    for mode in ('bf16','fp32'):
        capture=observed[mode]
        if capture['status'] not in ('COMPLETE_DIAGNOSTIC','NO_ONEDNN_EXECUTION_OBSERVED') and not diagnostic.has_only_informational_unknowns(capture):
            return False
    # Original native_forward: Q/K/V, QK, PV, O, gate/up/down = nine matmuls.
    bf16=observed['bf16']
    expected={'QKV_KV':2,'DENSE_HIDDEN':2,'MLP':3}
    expected.update({'QK':1,'PV':1} if value['tokens']==16 else {'ATTENTION_SQUARE':2})
    actual={}
    if bf16['exec_records']!=9:return False
    for record in bf16['records']:
        if record['primitive']!='matmul':return False
        desc=record['descriptors']
        if any(desc.get(k,{}).get('dtype')!='bf16' for k in ('src','wei','dst')):return False
        if 'bia' in desc and desc['bia']['dtype'] not in ('bf16','undef'):return False
        actual[record['role']]=actual.get(record['role'],0)+record['count']
    return actual==expected


def validate_diagnostics(value):
    from . import dispatch_capture as capture_module,dispatch_diagnostic as diagnostic
    fixed=dict(schema=2,diagnostic_only=True,numerical_acceptance=False,backend_order_proven=False,
        actual_chain_executed=False,rtl_execution=False)
    hashes={'source_manifest_sha256','contract_sha256','generated_module_sha256','library_sha256','qkv_library_sha256'}
    fields={'tokens','status','postflight_complete','result_sha256','payload_manifest_sha256','payload_tensor_map_sha256',
        'capture','cpu','backend_build','fenv','fenv_changes','payload_sha256','stage_sha256'}
    need(type(value) is dict and set(value)==set(fixed)|hashes|fields and
        all(type(value[k]) is type(v) and value[k]==v for k,v in fixed.items()))
    need(all(kernel.digest(value[k]) for k in hashes) and type(value['tokens']) is int and value['tokens'] in (16,128) and
        type(value['postflight_complete']) is bool and value['status'] in ('COMPLETE_DIAGNOSTICS','INCOMPLETE_DIAGNOSTICS'))
    need(value['postflight_complete'] is (value['result_sha256'] is not None))
    if value['result_sha256'] is None:
        need(all(value[k] is None for k in ('payload_manifest_sha256','payload_tensor_map_sha256','payload_sha256','stage_sha256')))
    else:
        need(kernel.digest(value['result_sha256']) and kernel.digest(value['payload_manifest_sha256']))
        need(same(diagnostic.validate_payload_hashes(value['payload_sha256']),value['payload_sha256']))
        need(value['payload_tensor_map_sha256']==kernel.sha(kernel.encoded(value['payload_sha256'])))
        need(same(diagnostic.validate_stage_hashes(value['stage_sha256']),value['stage_sha256']))
    observed=value['capture']
    if observed is not None:
        need(type(observed) is dict and set(observed)=={'bf16','fp32'})
        need(all(same(diagnostic.validate_verbose(v),v) for v in observed.values()))
    if value['cpu'] is not None:need(same(diagnostic.validate_cpu_features(value['cpu']),value['cpu']))
    if value['backend_build'] is not None:validate_backend_build(value['backend_build'])
    environment=value['fenv']
    need(type(environment) is dict and set(environment)=={'libraries','before_recipe','after_recipe','after_gate'})
    loads=environment['libraries']
    if loads is not None:
        need(type(loads) is dict and set(loads)=={'before','after_qkv','after_qk'})
        for item in loads.values():capture_module.validate_fenv(item)
    for name in ('before_recipe','after_recipe','after_gate'):
        if environment[name] is not None:capture_module.validate_fenv(environment[name])
    need(same(value['fenv_changes'],fenv_changes(environment)))
    snapshots=list((loads or {}).values())+[environment[k] for k in ('before_recipe','after_recipe','after_gate')]
    complete=(value['postflight_complete'] and value['result_sha256'] is not None and
        _completed_dispatch(observed) and
        value['cpu'] is not None and value['backend_build'] is not None and
        len(snapshots)==6 and all(v is not None and v['status']=='OBSERVED' for v in snapshots))
    need(value['status']==('COMPLETE_DIAGNOSTICS' if complete else 'INCOMPLETE_DIAGNOSTICS'))
    need(len(kernel.encoded(value))<=MAX_DIAGNOSTICS)
    return canonical(value)


def diagnostic_record(context,tokens,library,qkv_library,observed,cpu,backend,environment,validated=None):
    from . import dispatch_diagnostic as diagnostic
    value=dict(schema=2,diagnostic_only=True,numerical_acceptance=False,backend_order_proven=False,
        actual_chain_executed=False,rtl_execution=False,tokens=tokens,status='INCOMPLETE_DIAGNOSTICS',
        postflight_complete=validated is not None,source_manifest_sha256=kernel.sha(kernel.encoded(context['source_sha256'])),
        contract_sha256=context['contract_sha256'],generated_module_sha256=context['generated_module_sha256'],
        library_sha256=library['library_sha256'],qkv_library_sha256=qkv_library['library_sha256'],
        result_sha256=None,payload_manifest_sha256=None,payload_tensor_map_sha256=None,capture=observed,cpu=cpu,backend_build=backend,
        fenv=environment,fenv_changes=fenv_changes(environment),payload_sha256=None,stage_sha256=None)
    if validated is not None:
        disk,report,manifest=validated
        value.update(result_sha256=report['result_sha256'],payload_manifest_sha256=report['payload_manifest_sha256'],
            payload_sha256=diagnostic.payload_hashes(manifest),stage_sha256=diagnostic.stage_hashes(disk,tokens=tokens))
        value['payload_tensor_map_sha256']=kernel.sha(kernel.encoded(value['payload_sha256']))
    loads=environment['libraries'];snapshots=list((loads or {}).values())+[environment[k] for k in ('before_recipe','after_recipe','after_gate')]
    if (validated is not None and _completed_dispatch(observed) and
        cpu is not None and backend is not None and len(snapshots)==6 and
        all(v is not None and v['status']=='OBSERVED' for v in snapshots)):
        value['status']='COMPLETE_DIAGNOSTICS'
    return validate_diagnostics(value)


def read_cpu_features():
    from . import dispatch_diagnostic as diagnostic
    try:
        with open('/proc/cpuinfo','rb') as stream:raw=stream.read(diagnostic.CPU_MAX_BYTES+1)
        return diagnostic.cpu_features(raw)
    except (OSError,ValueError):return None


def run(name,context_path):
    """Called in a separate supervised child for each fixed phase."""
    from . import runtime
    need(type(name) is str and name in PHASES)
    context,workspace=runtime.read_context(context_path)
    end=phase_deadline(context,name)
    sources=runtime.source_snapshot()
    need(same(context['source_sha256'],sources) and sources.get(SOURCE)==IMPORTED_SHA256)
    _phase_remaining(context,end)
    destination=workspace/('phase_'+name+'.json')
    need(not destination.exists() and not destination.is_symlink())
    # The parent is the sole compiler owner. Even this direct kernel entry only
    # verifies already-built libraries; it never starts a nested compiler group.
    library=kernel.verify(workspace/'qk_library')
    qkv_library=qkv_kernel.verify(workspace/'qkv_library')
    need(all(sources.get(n)==h for receipt in (library,qkv_library)
        for n,h in receipt['source_sha256'].items()))
    if name=='kernel':
        _postflight(context,workspace,sources,end,library,qkv_library)
        report=dict(schema=1,status='COMPLETE_KERNEL_BUILD',numerical_execution=False,backend_order_proven=False,
            library_sha256=library['library_sha256'],library_receipt_sha256=library['receipt_sha256'],
            qkv_library_sha256=qkv_library['library_sha256'],qkv_library_receipt_sha256=qkv_library['receipt_sha256'],
            qkv_recipe_pins_sha256=qkv_library['pins_sha256'],
            source_manifest_sha256=kernel.sha(kernel.encoded(sources)),contract_sha256=context['contract_sha256'],
            generated_module_sha256=context['generated_module_sha256'],recipe_pins_sha256=library['pins_sha256'])
        kernel._atomic(destination,validate_kernel_report(report))
        _phase_remaining(context,end)
        return 0
    tokens=16 if name=='native16' else 128
    native=_generated(context['generated_module'],context['generated_module_sha256'])
    from ..raw_kv_public_fresh import setup
    need(setup.IMPORTED_SETUP_SHA256==sources.get('candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py'))
    torch,backend_identity=setup.backend_identity()  # The original run_gate alone sets interop threads.
    from . import dispatch_capture as capture_module
    capture=capture_module.Capture(workspace/(name+'_dispatch'),torch)
    diagnostic_destination=workspace/('phase_'+name+'_diagnostics.json')
    need(not diagnostic_destination.exists() and not diagnostic_destination.is_symlink())
    environment=dict(libraries=None,before_recipe=None,after_recipe=None,after_gate=None)
    backend=None;cpu=None;validated=None
    try:
        backend=backend_build(backend_identity)
        cpu=read_cpu_features()
        environment['libraries']=capture_module.library_fenv(qkv_library['library_path'],library['library_path'])
        from ..raw_kv_native_qk.adapter import Recipe
        environment['before_recipe']=capture_module.fenv_snapshot()
        try:recipe=Recipe(workspace/'qkv_library',workspace/'qk_library')
        finally:environment['after_recipe']=capture_module.fenv_snapshot()
        recipe_identity=recipe.identity()
        need(same(recipe_identity,combined_identity(library,qkv_library)))
        payload_raw=kernel.read(workspace/'payload/manifest.json',1048576)
        payload_sha=kernel.sha(payload_raw)
        small=None;small_sha=None
        if tokens==128:
            small=workspace/'native16/RESULT.json';small_sha=kernel.sha(kernel.read(small,1048576))
            prior=validate_report(kernel.json_bytes(kernel.read(workspace/'phase_native16.json',MAX_REPORT),MAX_REPORT))
            need(prior['tokens']==16 and prior['native_acceptance'] is True and prior['result_sha256']==small_sha and
                prior['payload_manifest_sha256']==payload_sha and prior['generated_module_sha256']==context['generated_module_sha256'] and
                prior['library_sha256']==library['library_sha256'] and prior['library_receipt_sha256']==library['receipt_sha256'] and
                prior['recipe_pins_sha256']==library['pins_sha256'] and
                prior['qkv_library_sha256']==qkv_library['library_sha256'] and
                prior['qkv_library_receipt_sha256']==qkv_library['receipt_sha256'] and
                prior['qkv_recipe_pins_sha256']==qkv_library['pins_sha256'] and
                prior['source_manifest_sha256']==kernel.sha(kernel.encoded(sources)) and prior['contract_sha256']==context['contract_sha256'])
            prior_diagnostics=validate_diagnostics(kernel.json_bytes(
                kernel.read(workspace/'phase_native16_diagnostics.json',MAX_DIAGNOSTICS),MAX_DIAGNOSTICS))
            need(prior_diagnostics['tokens']==16 and continuation_eligible(prior_diagnostics) and
                prior_diagnostics['postflight_complete'] is True and
                all(prior_diagnostics[key]==prior[key] for key in ('result_sha256','payload_manifest_sha256',
                    'source_manifest_sha256','contract_sha256','generated_module_sha256','library_sha256','qkv_library_sha256')))
        _phase_remaining(context,end)
        try:
            result=native.run_gate(ROOT,workspace/'payload',workspace/name,tokens,
                carried=False,threads=4,small_gate=small,qkv_recipe=recipe,diagnostics=capture)
        finally:environment['after_gate']=capture_module.fenv_snapshot()
        setup.backend_threads(torch)
        _phase_remaining(context,end)
        raw=kernel.read(workspace/name/'RESULT.json',1048576);disk=kernel.json_bytes(raw,1048576)
        need(same(canonical(result),disk))
        _,identity=native.runtime_identity(ROOT)
        identity['independent_qkv_recipe']=recipe_identity
        need(same(disk.get('identity'),identity))
        kwargs=dict(tokens=tokens,result_sha256=kernel.sha(raw),source_sha256=sources,
            contract_sha256=context['contract_sha256'],generated_module_sha256=context['generated_module_sha256'],
            library=library,qkv_library=qkv_library,payload_manifest_sha256=payload_sha,m16_result_sha256=small_sha)
        report=project_result(disk,**kwargs)
        need(same(project_result(canonical(result),**kwargs),report))
        verify_exports(disk,workspace/name,tokens)
        recipe.revalidate()
        need(kernel.sha(kernel.read(workspace/'payload/manifest.json',1048576))==payload_sha)
        need(kernel.sha(kernel.read(workspace/name/'RESULT.json',1048576))==kernel.sha(raw))
        if small is not None:need(kernel.sha(kernel.read(small,1048576))==small_sha)
        _postflight(context,workspace,sources,end,library,qkv_library)
        kernel._atomic(destination,report)
        validated=(disk,report,kernel.json_bytes(payload_raw,1048576))
        observation=diagnostic_record(context,tokens,library,qkv_library,capture.report(),cpu,backend,environment,validated)
        kernel._atomic(diagnostic_destination,observation)
        _phase_remaining(context,end)
        return 0 if report['native_acceptance'] and continuation_eligible(observation) else 1

    except BaseException:
        # Keep available bounded observations on exceptions without hiding the
        # original failure, changing arithmetic, or promoting partial evidence.
        try:
            need(time.monotonic_ns()<min(end,context['deadline_ns'])-10**9)
            if not diagnostic_destination.exists() and not diagnostic_destination.is_symlink():
                observed=None
                try:observed=capture.report()
                except BaseException:pass
                observation=diagnostic_record(context,tokens,library,qkv_library,
                    observed,cpu,backend,environment)
                kernel._atomic(diagnostic_destination,observation)
        except BaseException:pass
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=PHASES,required=True)
    parser.add_argument('--context',type=Path,required=True)
    args=parser.parse_args()
    context=None;workspace=None;end=None
    try:
        from . import runtime
        context,workspace=runtime.read_context(args.context)
        end=phase_deadline(context,args.phase)
        return run(args.phase,args.context)
    except BaseException as error:
        # Detailed producer stderr remains private; this fixed projection contains
        # no exception text, locals, commands, or non-repository traceback paths.
        try:
            need(context is not None and workspace is not None and end is not None and
                time.monotonic_ns()<min(end,context['deadline_ns'])-10**9)
            from ..raw_kv_public_fresh import setup
            diagnostic=setup.safe_diagnostic(error,phase='preflight',sources=context['source_sha256'])
            setup.validate_diagnostic(diagnostic,'preflight',context['source_sha256'])
            diagnostic['phase']=args.phase
            need(len(kernel.encoded(diagnostic))<=4096)
            destination=workspace/(args.phase+'.failure.json')
            need(not destination.exists() and not destination.is_symlink())
            kernel._atomic(destination,diagnostic)
        except BaseException:pass
        return 1


if __name__=='__main__':raise SystemExit(main())

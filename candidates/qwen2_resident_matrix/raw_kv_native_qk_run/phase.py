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
    torch,_=setup.backend_identity()  # The original run_gate alone sets interop threads.
    from ..raw_kv_native_qk.adapter import Recipe
    recipe=Recipe(workspace/'qkv_library',workspace/'qk_library');recipe_identity=recipe.identity()
    need(same(recipe_identity,combined_identity(library,qkv_library)))
    payload_sha=kernel.sha(kernel.read(workspace/'payload/manifest.json',1048576))
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
    _phase_remaining(context,end)
    result=native.run_gate(ROOT,workspace/'payload',workspace/name,tokens,
        carried=False,threads=4,small_gate=small,qkv_recipe=recipe)
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
    _phase_remaining(context,end)
    return 0 if report['native_acceptance'] else 1


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

"""Pure source/metadata controls; no real owner, native code or model payload."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
from types import SimpleNamespace

HERE=Path(__file__).resolve().parents[1]

def need(ok,message):
    if not ok:raise AssertionError(message)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module

def rejects(fn):
    try:fn()
    except (ValueError,TypeError,KeyError,AssertionError):return
    raise AssertionError('negative accepted')

def run(baseline,output):
    start=time.monotonic();baseline=Path(baseline).absolute();output=Path(output).absolute()
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and not sys.flags.optimize,'isolated runtime')
    need(not output.exists(),'fresh source-test output')
    resource.setrlimit(resource.RLIMIT_CPU,(15,15));resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    signal.alarm(15);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    inputs=json.loads((HERE/'INPUT_PINS.json').read_bytes())
    allowed={baseline/name for section in ('baseline','baseline_changed_files') for name in inputs[section]}
    denied=[]
    def audit(event,args):
        if event.startswith(('ctypes.','subprocess.','socket.')) or event in ('os.system','os.fork','os.forkpty','os.posix_spawn'):
            denied.append(event);raise RuntimeError('native/process/network denied')
        if event=='import' and args[0].split('.')[0] in {'ctypes','numpy','torch','candidates','subprocess','socket','multiprocessing'}:
            denied.append(event+':'+args[0]);raise RuntimeError('DUT/native import denied')
        if event=='open' and isinstance(args[0],(str,bytes)):
            p=Path(os.fsdecode(args[0])).absolute()
            mode=args[1];flags=args[2]
            writing=(type(mode) is str and any(c in mode for c in 'wax+')) or (type(flags) is int and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)))
            ok=(p==output or output in p.parents) if writing else (p in allowed or p==HERE or HERE in p.parents or p==output or output in p.parents or str(p).startswith(sys.base_prefix+'/lib/'))
            if not ok:denied.append('open');raise RuntimeError('unlisted source-test file')
    sys.addaudithook(audit)
    for name,spec in inputs['overlay'].items():
        raw=(HERE/'overlay'/name).read_bytes();need({'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}==spec,'overlay pin')
    prep=load('_pv_metadata_plan',HERE/'prepare_metadata.py')
    preflight=load('_pv_preflight',HERE/'overlay/assembly_preflight.py')
    interface=load('_pv_interface',HERE/'overlay/integration/interface.py')
    guard=load('_pv_source_guard',HERE/'overlay/observation/source_guard.py')
    output.mkdir(); planned=output/'planned'
    receipt=prep.build(baseline,planned)
    need(receipt['unchanged_assembly_entries']==319 and receipt['source_qualified'] is False and receipt['actual_authorized'] is False,'scope')
    manifest=json.loads((planned/'SOURCE_MANIFEST.json').read_bytes())
    base=json.loads((baseline/'ASSEMBLY_BASE.json').read_bytes())['objects']
    expected=preflight.successor_assembly(base)
    domains=(('source','source_sha256','source_bytes',306),('selected','selected_source_sha256','selected_source_bytes',9),('support','support_sha256','support_bytes',6))
    def validate(m):
        preflight.validate_successor_identity(m)
        for d in domains:preflight.validate_successor_domain(m,expected,*d)
    validate(manifest);checks=['exact_two_entry_successor']
    for name,delta in preflight.PV_REUSE_DELTA.items():
        d,rel=name.split('/',1);hkey={'source':'source_sha256','selected':'selected_source_sha256'}[d];skey={'source':'source_bytes','selected':'selected_source_bytes'}[d]
        bad=copy.deepcopy(manifest);bad[hkey][rel]=delta['before']['sha256'];bad[skey][rel]=delta['before']['bytes'];rejects(lambda:validate(bad))
    checks.append('owner_only_or_scala_only_rejected')
    changed=set(preflight.PV_REUSE_DELTA);untouched=0
    for name in expected:
        if name in changed:continue
        d,rel=name.split('/',1);hkey={'source':'source_sha256','selected':'selected_source_sha256','support':'support_sha256'}[d]
        bad=copy.deepcopy(manifest);bad[hkey][rel]='0'*64;rejects(lambda:validate(bad));untouched+=1
    need(untouched==319,'remaining source count');checks.append('all319_unchanged_entry_drift_rejected')
    for key,value in [('schema','fixed93-fullblock-integration-source-v1'),('reviewed_manifest_sha256',preflight.R3_SHA),('candidate_review_status','PENDING_INDEPENDENT_REVIEW'),('candidate_identity','foreign'),('old_pass_inherited',True),('actual_execution_authorized',True),('evidence_contract','old-contract')]:
        bad=copy.deepcopy(manifest);bad[key]=value;rejects(lambda:validate(bad))
    checks.append('old_review_and_wrong_identity_rejected')
    for mutate in ('missing','extra','bool_size','same_name_wrong_baseline'):
        bad=copy.deepcopy(manifest)
        if mutate=='missing':bad['source_sha256'].pop(next(iter(bad['source_sha256'])))
        elif mutate=='extra':bad['support_sha256']['extra.py']='0'*64;bad['support_bytes']['extra.py']=1
        elif mutate=='bool_size':bad['source_bytes'][next(iter(bad['source_bytes']))]=True
        else:
            wrong=copy.deepcopy(base);wrong[0]['sha256']='0'*64
            # Unchanged baseline rows are authenticated by exact BASE_SHA at real verify.
            raw=(baseline/'ASSEMBLY_BASE.json').read_bytes();need(hashlib.sha256(raw).hexdigest()==preflight.BASE_SHA,'baseline SHA pin')
            wrong[2]['path']='../escape';rejects(lambda:preflight.successor_assembly(wrong));continue
        rejects(lambda:validate(bad))
    checks.append('domain_shape_type_and_baseline_path_negatives')
    # True new source guard prefix, stopped before first306 file read. This is
    # a declared sentinel, not a loaded owner/closure/runtime qualification.
    class SourceReadStop(Exception):pass
    reached=[]
    original=guard.relative_path
    def stop(root,name):reached.append(name);raise SourceReadStop()
    guard.relative_path=stop
    def guard_prefix(document):
        p=output/'guard_manifest.json';raw=json.dumps(document,sort_keys=True).encode();p.write_bytes(raw)
        return guard.verify_closure(output/'no-source-materialized',p,hashlib.sha256(raw).hexdigest())
    try:
        try:guard_prefix(manifest)
        except SourceReadStop:pass
        else:raise AssertionError('positive source prefix did not reach sentinel')
        need(len(reached)==1,'positive source sentinel')
        for key,value in [('schema','fixed93-fullblock-integration-source-v1'),('reviewed_manifest_sha256',preflight.R3_SHA),('candidate_identity','foreign'),('candidate_review_status','PENDING_INDEPENDENT_REVIEW'),('evidence_contract','old-contract')]:
            bad=copy.deepcopy(manifest);bad[key]=value;before=len(reached);rejects(lambda:guard_prefix(bad));need(len(reached)==before,'negative must stop before306 read')
    finally:guard.relative_path=original
    checks.append('real_source_guard_identity_prefix_sentinel')
    owner_raw=(HERE/'overlay/source/candidates/qwen2_fixed93_attention/owner.py').read_bytes();tree=ast.parse(owner_raw)
    owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Fixed93AttentionOwner')
    anchors=json.loads((planned/'capture/anchors.json').read_bytes())
    oldanchors=json.loads((baseline/'capture/anchors.json').read_bytes())
    for name,method in [('owner_attention','_attention'),('owner_tick','tick')]:
        node=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name==method)
        need(anchors[name]['firstlineno']==node.lineno and anchors[name]['end_lineno']==node.end_lineno and anchors[name]['sha256']==hashlib.sha256(owner_raw).hexdigest(),'AST anchor')
    need({k:v for k,v in anchors.items() if k not in ('owner_attention','owner_tick')}=={k:v for k,v in oldanchors.items() if k not in ('owner_attention','owner_tick')},'other anchors unchanged');checks.append('two_anchor_locations_and_all_others_preserved')
    b=json.loads((planned/'BUDGET_PROPOSAL.json').read_bytes());need(b['status'].startswith('OPEN_'),'not reviewed budget')
    need(b['output_bytes']==sum(b['owned_reservation_components'].values())==22917099404 and b['startup_available_bytes_required']==23453970316,'whole budget sums')
    for v in (b['wholeblock_trace_limits']['codec'],b['attention_trace_limits']['codec_limits']):need(198+v['max_raw']+v['max_records']*(88+v['max_metadata'])<=v['max_output'],'no compression fallback')
    checks.append('open_budget_complete_reservation_and_fallback')
    shapes={name:(12,128,128) for name in ('dot_raw','dot_bf16','scale_fp32','score_bf16','score_difference','exp_fp32','denominator_step')}
    shapes.update({name:(12,128,128,16) for name in ('packed_stripes','fold_before','fold_after')});shapes.update({name:(12,128,128,8) for name in ('probability_fp32','probability_bf16')});shapes.update(pv_key_raw=(12,128,128,8,16),normalizer=(12,128,3),pv_final_raw=(12,128,128),pv_bf16=(12,128,128))
    shell=SimpleNamespace(fields={k:{'shape':v,'frequency':'MOCK-not-values'} for k,v in shapes.items()},report=lambda:None,save=lambda:None,legacy_adapter=lambda:None,field_words=lambda name:bytes(786432))
    report=dict(schema='fixed93-fullblock-attention-pv-reuse-observation-v1',complete_observation=True,control_only=False,status='COMPLETE_SYNTHETIC_DECLARATION',normalization_evaluations_per_causal_key=1,probability_use_repeats=8,normalization_reuses_per_causal_key=7,observed_normalization_reuses=693504,scalar_schedule_changed=True,both_probability_domains_repeats_verified=True)
    interface.validate_observation(shell,report)
    for key in ('normalization_evaluations_per_causal_key','probability_use_repeats','normalization_reuses_per_causal_key','observed_normalization_reuses'):
        for value in (True,0,9):bad=dict(report,**{key:value});rejects(lambda:interface.validate_observation(shell,bad))
    for key,value in [('schema','fixed93-fullblock-attention-observation-v1'),('scalar_schedule_changed',False),('both_probability_domains_repeats_verified',False)]:bad=dict(report,**{key:value});rejects(lambda:interface.validate_observation(shell,bad))
    checks.append('real_interface_1_8_7_guard_mock_fields_only')
    old_observer=ast.parse((baseline/'observation/fullblock_attention.py').read_bytes());new_observer=ast.parse((HERE/'overlay/observation/fullblock_attention.py').read_bytes())
    def fn(tree,name):return next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    for name in ('native_snapshot','_identity','_validate'):need(ast.dump(fn(old_observer,name))==ast.dump(fn(new_observer,name)),'native hardening retained')
    for rel in ('fullblock_runtime.py','integration/runner.py','capture/wholeblock.py','supervision/gate.py'):
        old=(baseline/rel).read_text();new=(HERE/'overlay'/rel).read_text();need(old.replace('original-algorithm-arrays-plus-true-events-and-fixed-attention-v1',preflight.CONTRACT)==new,'scope literal only: '+rel)
    checks.append('native_helper_global_closure_and_current_fixes_preserved')
    prod=json.loads((planned/'PRODUCTION_SOURCE_MANIFEST.json').read_bytes());need(manifest['preparation_files']['PRODUCTION_SOURCE_MANIFEST.json']==prep.pin((planned/'PRODUCTION_SOURCE_MANIFEST.json').read_bytes()),'no manifest hash cycle')
    need(prod['preparation_files']=={k:v for k,v in manifest['preparation_files'].items() if k!='PRODUCTION_SOURCE_MANIFEST.json'},'current production/top prep consistency')
    for m in (manifest,prod):
        for name,rawpin in m['preparation_files'].items():
            path=(planned/name) if (planned/name).is_file() else (HERE/'overlay'/name)
            if path.is_file():need(prep.pin(path.read_bytes())==rawpin,'changed preparation pin')
    need(not (planned/'ADMISSION.json').exists() and not (planned/'source/candidates').exists(),'plan not runtime materialization')
    inventory=json.loads((HERE/'overlay/integration/EVIDENCE_INVENTORY.json').read_bytes())
    prep.validate_inventory_contract(inventory)
    need(inventory['evidence_contract']==manifest['evidence_contract']==prod['evidence_contract']==preflight.CONTRACT,'algorithm seal contract propagation')
    for bad in (dict(inventory,evidence_contract='original-algorithm-arrays-plus-true-events-and-fixed-attention-v1'),dict(inventory,evidence_contract=None),{},[]):
        rejects(lambda:prep.validate_inventory_contract(bad))
    before=json.loads((baseline/'integration/EVIDENCE_INVENTORY.json').read_bytes())
    need({k:v for k,v in before.items() if k!='evidence_contract'}=={k:v for k,v in inventory.items() if k!='evidence_contract'},'algorithm inventory only contract changed')
    checks.append('planned_pins_binding_no_admission_no_source_copy')
    checks.append('algorithm_seal_inventory_contract_and_old_contract_rejection')
    rejects(lambda:prep.build(baseline,planned));checks.append('fresh_output_replay_rejected')
    need(not denied and not any(n.split('.')[0] in {'ctypes','numpy','torch','candidates'} for n in sys.modules),'no DUT/native paths')
    result=dict(status='PASS_PURE_SOURCE_AND_MOCK_METADATA_CONTROLS_ONLY',checks=checks,groups=len(checks),untouched_drift_negatives=untouched,
                elapsed_seconds=time.monotonic()-start,maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                denied_attempts=denied,CPU_count=len(os.sched_getaffinity(0)),address_space_limit_bytes=256*1024**2,
                source_guard_scope='real identity prefix stopped before first source file; loaded guard not executed',
                interface_scope='real declaration/shape guard with synthetic fields; no values or owner execution',
                full_preflight_executed=False,whole_closure_bytes_rehashed=False,source_qualified=False,
                actual_authorized=False,native_executed=False,DUT_executed=False,fullblock_acceptance=False)
    (output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(run(a.baseline,a.output),sort_keys=True))

"""Exactly one normally loaded model root per fresh native worker, no reload.
A only seals a true terminal. B compares retained reference after both terminals;
the old independent recipe is never executed again by this diagnostic.
"""
import argparse,hashlib,importlib,json,os,resource,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from admission import validate_review
from artifacts import persist_words,persist_fields
from durable import Stages,atomic_json
from policy import ARMS,PROFILE,LIMITS
import binding,support
from support import need,digest
OUT=PHASES=CONFIG=None

def scalar_probes(owner,scalar,lib,state):
    cases=(('div_zero','div',0x3f800000,0,None,'ArithmeticFault','BlockScalarFloat invalid/div0/overflow/nonfinite result'),
        ('nonfinite','mul',0x7f800000,0x3f800000,None,'ArithmeticFault','BlockScalarFloat rejects nonfinite input'),
        ('overflow','mul',0x7f7fffff,0x40000000,None,'ArithmeticFault','BlockScalarFloat invalid/div0/overflow/nonfinite result'),
        ('inexact_underflow','mul',1,0x3f000000,None,'ArithmeticFault','BlockScalarFloat rejects inexact underflow'),
        ('exact_subnormal','mul',0x00800000,0x3f000000,0x00400000,None,None),
        ('signed_zero','mul',0x80000000,0x3f800000,0x80000000,None,None))
    before=dict(scalar.calls);fmas=int(lib.matrix_normal_fmas())
    report=dict(scope='SIX_POST_TERMINAL_SCALAR_HELPER_PROBES_NOT_MATRIX_JOBS',cases=[],passed=False,matrix_fmas_before=fmas)
    state['probe_report']=report
    need(owner.state=='idle' and scalar.client is None and owner.matrix.owner is None,'clean released owner before probes')
    need(scalar.acquire(owner),'probe scalar ownership')
    try:
        for name,operation,a,b,expected,category,message in cases:
            row=dict(name=name,operation=operation,a=a,b=b,policy='legacy_scalar')
            try:row['word']=owner._op(operation,a,b,policy='legacy_scalar')
            except Exception as error:row.update(exception_category=type(error).__name__,exception_message=str(error))
            row['matches']=(row.get('word')==expected and 'word' in row) if category is None else row.get('exception_category')==category and row.get('exception_message')==message
            report['cases'].append(row)
    finally:scalar.release(owner)
    report['scalar_delta']={k:scalar.calls[k]-before.get(k,0) for k in scalar.calls if scalar.calls[k]!=before.get(k,0)}
    report['matrix_fmas_after']=int(lib.matrix_normal_fmas())
    report['passed']=all(r['matches'] for r in report['cases']) and report['scalar_delta']=={'div':1,'mul':5} and report['matrix_fmas_after']==fmas and scalar.client is None
    return report

def retain(out,state,result):
    record=dict(actual_terminal_verified=state.get('actual_terminal_verified',False),capture_error=state.get('capture_error'),service_error=state.get('service_error'),mask_receipts=state.get('mask_receipts',[]))
    capture=state.get('capture');fields=getattr(getattr(capture,'data',None),'fields',None)
    if fields is not None:record['fields']=persist_fields(out/'artifacts','CAPTURE',fields)
    tracer=state.get('tracer')
    if tracer is not None:atomic_json(out/'artifacts/SERVICE_EVENTS.json',tracer.events)
    if state.get('actual_terminal_verified'):
        record['output']=persist_words(out/'artifacts','OUTPUT',state['output'])
        atomic_json(out/'artifacts/WRITES.json',state['writes'])
        if result is not None:record['scores']=persist_words(out/'artifacts','SCORES',result['scores'])
    atomic_json(out/'metadata/ARM_EVIDENCE.json',record)
    return record

def baseline_metadata(config,baseline,handoff,handoff_sha,*,both_terminals=False):
    need(digest(handoff)==handoff_sha,'parent handoff identity')
    receipt=json.loads(Path(handoff).read_text());need(receipt['arm']=='baseline' and receipt['state']=='EXITED_TERMINAL_ONLY' and receipt['config_sha256']==config['config_sha256'],'baseline parent identity')
    need(receipt['directory']==str(baseline) and receipt['terminal_acked'] is True and receipt['resources_released'] is True,'parent validated baseline terminal metadata')
    for rel,pin in receipt['files'].items():
        path=baseline/rel
        need(type(rel) is str and not Path(rel).is_absolute() and '..' not in Path(rel).parts and path.resolve()==path and type(pin['bytes']) is int and pin['bytes']>=0 and len(pin['sha256'])==64,'exact unaliased handoff file')
    if both_terminals:
        need(receipt['terminal_sha256']==digest(baseline/'TERMINAL.json'),'baseline terminal hash')
        value=json.loads((baseline/'TERMINAL.json').read_text())
        need(value['status']=='COMPLETE_REAL_M2_TERMINAL_REFERENCE_PENDING' and value['arm']=='baseline' and value['terminal_acked'] is True and value['resources_released'] is True,'real baseline terminal')
    return receipt

def main():
    global OUT,PHASES,CONFIG
    p=argparse.ArgumentParser()
    for name in ('config','sha','review','review-sha','out','arm'):p.add_argument('--'+name,required=True)
    for name in ('baseline','handoff','handoff-sha'):p.add_argument('--'+name)
    p.add_argument('--m',type=int,choices=(2,),required=True);a=p.parse_args()
    need(os.environ.get('ORDERED_NATIVE_PARENT')==str(os.getppid()),'supervised fresh worker')
    need(digest(a.config)==a.sha,'config identity');bundle,review=validate_review(a.config,a.review,a.review_sha,HERE)
    need(a.arm in ARMS and bundle['profile']==PROFILE,'fixed arm')
    config=dict(bundle,**bundle['profiles'][a.arm],arm=a.arm,config_sha256=a.sha);CONFIG=config
    need(len(os.sched_getaffinity(0))==1 and resource.getrlimit(resource.RLIMIT_AS)[0]==LIMITS['address_space_bytes'],'caps')
    need(not any(k.startswith('LD_') for k in os.environ),'no loader override')
    OUT=Path(a.out)
    for name in ('artifacts','audits','metadata','streams'):(OUT/name).mkdir()
    PHASES=Stages(OUT/'metadata/stages');PHASES.mark('PREFLIGHT_ENTER')
    support.check_manifest(config,include_reference=False)
    identity=support.process_identity();atomic_json(OUT/'metadata/IDENTITY.json',identity)
    for k,v in config['git_environment'].items():os.environ[k]=v
    baseline=None if a.arm=='baseline' else Path(a.baseline).resolve(strict=True)
    handoff=None if baseline is None else baseline_metadata(config,baseline,a.handoff,a.handoff_sha)
    sys.path[:0]=[config['source_root'],config['numpy_root'],config['observer_runtime_root']]
    guard=binding.Isolation(config,OUT,baseline);sys.addaudithook(guard.audit)
    inputs=[]
    for role,width in (('qr',1536),('kr',256),('v',256)):
        spec=config['inputs'][role];need(digest(spec['path'])==spec['sha256'],'same frozen operand')
        with Path(spec['path']).open('rb') as f:raw=f.read(2*width*4)
        need(hashlib.sha256(raw).hexdigest()==config['input_prefixes'][role]['sha256'] and len(raw)==2*width*4,'same true M2 prefix')
        inputs.append(struct.unpack('<%dI'%(2*width),raw))
    gate,root,files,modules,runtime,source_receipt=binding.prepare(config,guard)
    # No model modules have executed before this point; only one helper profile.
    helper=importlib.import_module('harness');exact=helper.load_exact(config['exact_helper'])
    lib,loaded=support.load_library(config,OUT/'audits')
    PHASES.mark('BEFORE_REAL_M2_OWNER',dict(arm=a.arm,source_root=config['source_root']))
    state={};result=None
    try:
        with binding.model_gate(gate,root,files,config,source_receipt):
            result=helper.run_owner(lib,inputs,2,exact,config,modules['bridge'],modules['service_trace'],state=state)
    finally:
        original=sys.exc_info()[1]
        try:retain(OUT,state,result)
        except BaseException:
            if original is None:raise
    PHASES.mark('REAL_M2_TERMINAL_EVIDENCE_RETAINED')
    need(result is not None and result['terminal_acked'] and result['resources_released'],'actual M2 terminal')
    guard.terminal=True
    need(state['capture_error'] is state['service_error'] is result['capture_error'] is result['service_trace_error'] is None,'monitor lifecycle acceptance')
    need([v['phase'] for v in result['selective_masks']]==['installed','cleaned'],'real full mask lifecycle')
    registry=modules['registry']._attention(2,result['capture_fields'],result['capture_report'])
    need(result['native_fmas']==933888 and result['scalar_calls']==dict(bf=19968,add=360,mul=612,div=24),'exact unchanged M2 native/scalar work')
    probe=scalar_probes(state['owner'],state['scalar'],lib,state);atomic_json(OUT/'metadata/SCALAR_PROBES.json',probe)
    need(probe['passed'],'bounded real scalar exception/value qualification')
    PHASES.mark('POST_TERMINAL_SCALAR_PROBES_COMPLETE')
    support.audit_runtime(config,OUT/'audits','ARM_TERMINAL')
    guard.integrity=True
    try:support.check_manifest(config,include_reference=False)
    finally:guard.integrity=False
    atomic_json(OUT/'metadata/SOURCE_BINDING.json',source_receipt)
    summary={k:v for k,v in result.items() if k not in ('output','scores','writes','service_events','capture_fields')}
    summary.update(status='COMPLETE_REAL_M2_TERMINAL_REFERENCE_PENDING',arm=a.arm,config_sha256=a.sha,identity=identity,loaded=loaded,
        masks=result['selective_masks'],scalar_probe_report=probe,registry=registry,model_source_root=config['source_root'],model_Scala_correspondence_proved=False,performance_adopted=False)
    atomic_json(OUT/'TERMINAL.json',summary);PHASES.mark('OWN_TERMINAL_AUDITED')
    if a.arm=='baseline':
        atomic_json(OUT/'RESULT.json',summary);return
    # The old recipe has already succeeded on the exact same immutable M2 inputs.
    # Both fresh terminals precede its provenance/hash qualification and any
    # decoding of the baseline/reference saved numerical arrays.
    guard.all_terminals=True
    baseline_metadata(config,baseline,a.handoff,a.handoff_sha,both_terminals=True)
    PHASES.mark('BOTH_TERMINALS_BEFORE_RETAINED_REFERENCE_QUALIFICATION')
    from comparison import qualify_reference,compare_saved
    guard.handoff_files={str(baseline/rel) for rel in handoff['files']}
    guard.integrity=True
    try:
        for rel,pin in handoff['files'].items():need(digest(baseline/rel)==pin['sha256'] and (baseline/rel).stat().st_size==pin['bytes'],'baseline immutable handoff bytes')
        for path,pin in config['reference_artifacts'].items():need(digest(path)==pin['sha256'] and Path(path).stat().st_size==pin['bytes'],'immutable retained reference bytes')
        reference=qualify_reference(config)
    finally:guard.integrity=False
    atomic_json(OUT/'metadata/REFERENCE_QUALIFICATION.json',reference);guard.reference_qualified=True
    PHASES.mark('RETAINED_RECIPE_SUCCESS_QUALIFIED_NO_REEXECUTION')
    comparison=compare_saved(config,baseline,OUT,runtime)
    atomic_json(OUT/'metadata/COMPARISON.json',comparison);PHASES.mark('COMPARISON_COMPLETE')
    guard.integrity=True
    try:support.check_manifest(config)
    finally:guard.integrity=False
    support.audit_runtime(config,OUT/'audits','POSTFLIGHT');PHASES.mark('POSTFLIGHT_COMPLETE')
    atomic_json(OUT/'RESULT.json',dict(status='PASS_TWO_FRESH_M2_HELPER_DIAGNOSTIC_ONLY',m=2,arm=a.arm,config_sha256=a.sha,
        reference_values_loaded_after_current_terminals=True,reference_reexecuted=False,reference_recipe_reexecuted=False,comparison=comparison,fullblock=False,hardware_cycles=False,
        model_Scala_correspondence_proved=False,performance_adopted=False,stages=PHASES.rows))

if __name__=='__main__':
    try:main()
    except BaseException as error:
        if PHASES is not None:
            try:PHASES.mark('FAILED_RETAINED',dict(type=type(error).__name__,detail=str(error)))
            except BaseException:pass
        if OUT is not None and CONFIG is not None:
            try:support.audit_runtime(CONFIG,OUT/'audits','FAILURE')
            except BaseException:pass
        raise

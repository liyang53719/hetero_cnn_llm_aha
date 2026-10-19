"""Exact coordinator with synthetic modules, and pure deadline/FIFO/data tests."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B')
import copy,io,json,os,tempfile,types
from pathlib import Path
from contextlib import redirect_stdout
from unittest import mock
checks=[]
def need(ok,why):
    if not ok:raise ValueError(why)
def rejects(fn,why):
    try:fn()
    except (ValueError,KeyError,TypeError,OSError,TimeoutError):return
    raise ValueError('missing rejection: '+why)
start=1000.;stop=7600.;times=continuation.budget(start,stop)
need(times=={'total_stop':stop,'work_stop':7480.,'pre_stop':3880.,'numeric_seconds':3600,'tail_seconds':120},'exact 6480 work 2880 pre 120 evidence')
for a,b in ((True,6601),(0,6601),(0,6599),(float('nan'),6600),(0,float('inf'))):rejects(lambda:continuation.budget(a,b),'bad outer budget')
checks.append('one_6600_budget_exact_6480_work_2880_pre_and_120_evidence_tail')
bound={'total_seconds':60,'work_seconds':40};records=[]
for name in continuation.PHASES:
    want=times['work_stop'] if name in continuation.PHASES[-2:] else times['pre_stop']
    need(continuation.admit_phase(name,bound,records,start,stop,start)==want,'one shared phase deadline')
    records.append({'name':name,'status':'EXIT0_CLEANED'})
checks.append('exact_seventeen_phase_order_shares_pre_and_numeric_deadlines')
for name,rows in ((continuation.PHASES[1],[]),(continuation.PHASES[0],records),(continuation.PHASES[1],[{'name':continuation.PHASES[0],'status':'FAILED'}]),(continuation.PHASES[1],[{'name':'wrong','status':'EXIT0_CLEANED'}])):
    rejects(lambda:continuation.admit_phase(name,bound,rows,start,stop,start),'phase order or failed predecessor')
for now in (start-1,float('nan'),True,times['pre_stop']-15,times['pre_stop']):
    rejects(lambda:continuation.admit_phase(continuation.PHASES[0],bound,[],start,stop,now),'pre work reserve')
for bad in ({},{'total_seconds':True,'work_seconds':1},{'total_seconds':60,'work_seconds':60},{'total_seconds':60,'work_seconds':0}):
    rejects(lambda:continuation.admit_phase(continuation.PHASES[0],bad,[],start,stop,start),'finite stage bounds')
prior=[{'name':n,'status':'EXIT0_CLEANED'} for n in continuation.PHASES[:-2]]
need(continuation.admit_phase('host93_first_n0',bound,prior,start,stop,times['pre_stop'])==times['work_stop'],'full exact3600 window boundary')
rejects(lambda:continuation.admit_phase('host93_first_n0',bound,prior,start,stop,times['pre_stop']+0.0001),'must not shrink N0 window')
need(continuation.admit_phase(continuation.PHASES[0],bound,[],start,stop,times['pre_stop']-15.0001)==times['pre_stop'],'pre phase final strict reserve boundary')
checks.append('late_prephase_incomplete_bad_order_and_full3600_n0_boundary')

def fifo_fixture():
    pins={n:{'bytes':i+1,'sha256':str(i)*64} for i,n in enumerate(continuation.FIFO_SOURCE_NAMES)}
    row={'status':'EXIT0_CLEANED','exit_code':0,'waitid_status':0,'waitid_code':1,'cleanup_confirmed':True,'receipt_timed_out':False,'final_reap_signal':None}
    docs={'summary.json':{'fifo_observation':{'state':'AVAILABLE','cases':4,'comparisons':5180}},'source_hashes.json':{'project_sources':[{'path':n,**p} for n,p in pins.items()]},'stage_exits.json':{'stages':[dict(row,name=n) for n in ('icarus_acquire','fifo_compile','fifo_run')]},'review.json':{'run_id':39232100796,'verdict':'PASS_ACTUAL_CLUSTER_HOST_COMPILE_AND_BOUNDED_RESET_LAUNCH_ONLY'}}
    return pins,docs
def fifo_case(change=None):
    pins,docs=fifo_fixture();calls=[]
    if change:change(pins,docs)
    def checked(path,pin,*args):
        calls.append((Path(path),pin));return json.dumps(docs[Path(path).name]).encode() if Path(path).name in docs else b'synthetic source'
    g=types.SimpleNamespace(checked=checked,decode=json.loads)
    call=lambda:continuation.inherited_fifo(g,Path('/synthetic/repo'),Path('/synthetic/fifo'),Path('/synthetic/review.json'),pins)
    if change:rejects(call,'historical FIFO contract')
    else:
        out=call();need(out['local_fifo_execution']=='NOT_RUN' and out['scope']=='EXACT_SAME_SOURCE_HISTORICAL_FIFO_PRECONDITION' and out['cases']==4 and out['comparisons']==5180,'history never called local')
        need(len(calls)==9,'three exact receipts review and five same-source checks')
fifo_case();checks.append('historical_fifo4_5180_fixed_three_receipts_review_five_sources_not_new_local')
for field,value in (('cases',3),('comparisons',5179),('state','UNAVAILABLE')):
    fifo_case(lambda p,d,k=field,v=value:d['summary.json']['fifo_observation'].__setitem__(k,v));checks.append('historical_'+field+'_rejected')
for field,value in (('run_id',1),('verdict','PASS')):
    fifo_case(lambda p,d,k=field,v=value:d['review.json'].__setitem__(k,v));checks.append('historical_review_'+field+'_rejected')
fifo_case(lambda p,d:d['source_hashes.json']['project_sources'][0].__setitem__('sha256','x'*64));checks.append('historical_source_drift_rejected')
fifo_case(lambda p,d:d['stage_exits.json']['stages'].reverse());checks.append('historical_fifo_stage_order_rejected')
for field,value in (('exit_code',False),('status','FAILED'),('waitid_status',9),('waitid_code',2),('cleanup_confirmed',False),('receipt_timed_out',True),('final_reap_signal',9)):
    fifo_case(lambda p,d,k=field,v=value:d['stage_exits.json']['stages'][0].__setitem__(k,v));checks.append('historical_natural_'+field+'_rejected')

def coordinator_case(bad=None,matched=True):
    with tempfile.TemporaryDirectory(dir=ROOT) as t:
        root=Path(t);work=root/'out';repo=root/'repo';dep=root/'dependency';repo.mkdir();dep.mkdir();clock=[start];native=[];saved={};flags=[];limits_seen=[];source_checks=[];consumer_stops=[];parent_data=[]
        cfg={k:str(root/k) for k in ('qualification_result','qualification_review','fifo_evidence_root','fifo_review','fir','sv','idma_zip','provider_root','metadata_root','runtime_root','reference_file','reference_receipt')}
        cfg.update(schema='LOCAL_BACKEND_HOST_N0_BINDING_V1',repo=str(repo),work=str(work),source_cache=None,tool_binding={'path':str(root/'binding'),'bytes':2,'sha256':'b'*64},local_profile={'path':str(root/'profile'),'bytes':2,'sha256':'c'*64})
        fs=types.SimpleNamespace(fresh_directory=lambda p:p.mkdir(mode=0o700))
        g=types.SimpleNamespace(clean=lambda p:Path(p),checked=lambda *x:b'{}',binding=lambda *x:{},paths=lambda b:{'work':dep})
        def limits(total,work,cpu,space,size):return {'total_seconds':total,'work_seconds':work,'cpu_seconds':cpu,'as_bytes':space,'fsize_bytes':size}
        bounds=limits(60,40,40,512*1024**2,4*1024**2)
        def source_check():source_checks.append(True)
        def save(path,value):saved[path.name]=copy.deepcopy(value);path.write_text(json.dumps(value));return pin(path.read_bytes())
        def toolrun(repo_,out,callback):
            for name in continuation.PHASES[:10]:
                if bad=='late_pre' and name=='fresh_make':clock[0]=times['pre_stop']-15
                callback(name,['/synthetic/private/tool'],work,{},dict(bounds))
            return {'status':'SYNTHETIC_BACKEND_TINY'}
        component=types.SimpleNamespace(run=toolrun,host_identities=lambda s:{},save_private=save)
        def phase(fs_,base,name,argv,cwd,evidence,env,bound,deadline,owner,diagnostics):
            native.append(name);limits_seen.append((name,deadline));need(owner['deadline']==deadline,'same exact supervisor deadline')
            if name in continuation.PHASES[-2:]:need(deadline==times['work_stop'],'N0 work stop')
            else:need(deadline==times['pre_stop'],'all predecessors pre stop')
            if name=='idma319_extract':need('--fifo-valid-split' in argv,'original split path')
            if name=='host93_configuration':need('--cluster-boundary' in argv,'original cluster config')
            if name=='host93_cpp_compile' and bad=='late_n0':clock[0]=times['pre_stop']+0.1
            return {'exit_code':1 if bad==name else 0,'cleanup_confirmed':bad!='unclean_'+name},b'',{'synthetic':True}
        supervisor=types.SimpleNamespace(fixed_support=lambda r:(fs,{},{}),diagnostic_defaults=lambda:{},run_phase=phase)
        P=types.SimpleNamespace(verify_file=lambda p,pin:None,empty_observation=lambda:{'state':'NOT_RUN'},native_environment=lambda w:{})
        def executor_run(repo_,out,callback,tools,host,idma,retained,config,**kwargs):
            need(kwargs['cluster_boundary'] is True and kwargs['first_n0'] is True,'original real first N0 flags')
            need(host['origin']=='EXISTING_PINNED_ARTIFACTS_REVALIDATED_NOT_NEW_EMISSION','truthful previous FIR/SV')
            flags.append(kwargs);callback('host93_cpp_generate',['/synthetic/verilator'],work,{},dict(bounds));kwargs['diagnostic_callback'](out,{})
            callback('host93_cpp_compile',['/usr/bin/make','-j1'],work,{},dict(bounds));return {'status':'COMPILED_FIRST_N0_FIXTURE_ONLY'}
        executor=types.SimpleNamespace(run=executor_run,validate_cluster_census=lambda g:need(g=={'synthetic':'census'},'original census used'))
        census=types.SimpleNamespace(collect=lambda *x:{'synthetic':'census'},validate_report=lambda g:None)
        def module(repo_,pins,name,label):
            if name.endswith('pipeline.py'):return P
            if name.endswith('host_execution.py'):return executor
            if name.endswith('generation_diagnostics.py'):return census
            return types.SimpleNamespace()
        def memory(*args):
            if bad=='admission':raise ValueError('synthetic memory admission refused')
        C=types.SimpleNamespace(memory_disk_gate=memory,project_pin_map=lambda r:({}, {continuation.CI+'idma319/ENTRY.json':b'{"bootstrap":"synthetic"}',continuation.CI+'configuration/ENTRY.json':b'{"argv_prefix":["x","x","x","x","x","synthetic"]}'}),module_from=module,exact=lambda *x:None,phase_limits=lambda *x:None,decode=json.loads,limits=limits)
        def numeric(repo_,out,pins,callback,numeric_stop,front,execution,observation,completed,stages):
            need(numeric_stop==stop-105,'original consumer receives stop-105 with own 15s reserve')
            for name in continuation.PHASES[-2:]:callback(name,['/synthetic/numeric'],work,{},dict(bounds))
            observation.update(state='AVAILABLE',compared=196608);return matched
        def prepare(*args,**kwargs):consumer_stops.append((args,kwargs));return numeric,{'synthetic':'front'},{'synthetic':'historical-reference'}
        consumer=types.SimpleNamespace(SOURCE_PINS={},prepare=prepare,require_numeric_window=lambda stop_:stop_-105)
        mods={'bootstrap':g,'observer':None,'profile':None,'adapter':None,'accepted':types.SimpleNamespace(bind=lambda *x:(component,{'local_probe_rerun':False})),'header':None,'header_raw':b'synthetic','consumer':consumer,'coordinator':C,'supervisor':supervisor}
        def stage(P_,repo_,pins,providers,metadata,destination):
            destination.mkdir(mode=0o700);parent_data.append(True);return {'kind':'PARENT_DATA_ONLY','files':16,'numeric_conversion':False,'native_started':False}
        patches=[mock.patch.object(continuation,'inherited_fifo',return_value={'scope':'EXACT_SAME_SOURCE_HISTORICAL_FIFO_PRECONDITION','local_fifo_execution':'NOT_RUN'}),mock.patch.object(continuation,'stage_inputs',side_effect=stage),mock.patch.object(continuation.time,'monotonic',side_effect=lambda:clock[0]),mock.patch.object(continuation.os,'sched_getaffinity',return_value={0}),mock.patch.object(continuation.signal,'signal',return_value=None),mock.patch.object(continuation.signal,'setitimer',return_value=None)]
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patch in patches:stack.enter_context(patch)
            stack.enter_context(redirect_stdout(io.StringIO()))
            call=lambda:continuation.run(cfg,start,stop,mods,source_check)
            if bad:rejects(call,bad)
            else:
                result=call();need(result['status']==('PASS_FIRST_N0_LIMITED_TOLERANCE_ONLY' if matched else 'N0_LIMITED_TOLERANCE_FAIL'),'only finished comparison PASS/FAIL')
                need(native==list(continuation.PHASES) and len(result['stages'])==17,'all exact native phases')
                need(len(parent_data)==1 and result['parent_data_stages'][0]['files']==16,'separate canonical16 data receipt')
                need(result['full_block_pass'] is False and result['baseline_adopted'] is False,'scope never full block or baseline')
                need(len(consumer_stops)==2 and len(flags)==1,'reference preflight twice and original executor once')
                need(all(n not in native for n in accepted.PHASES),'no ten tool reprobes or old dependency restage')
        if bad=='admission':need(native==[] and not saved,'admission before output/callback')
        elif bad:
            need(saved['RESULT.json']['status']=='INCOMPLETE','any phase/time failure is incomplete')
            if bad in continuation.PHASES:need(native==list(continuation.PHASES[:continuation.PHASES.index(bad)+1]),'first failure stops subsequent stages')
            if bad=='late_pre':need(native==list(continuation.PHASES[:5]),'late pre rejects before make callback')
            if bad=='late_n0':need(native==list(continuation.PHASES[:15]),'full N0 window lost no numeric callback')
coordinator_case();checks.append('complete_original_coordinator_mock_seventeen_stages_and_truthful_scopes')
coordinator_case(matched=False);checks.append('completed_196608_comparison_false_is_only_numeric_fail')
for bad in continuation.PHASES:
    coordinator_case(bad);checks.append(bad+'_failure_stops_successors_and_records_incomplete')
for bad in ('late_pre','late_n0','admission','unclean_fresh_make'):
    coordinator_case(bad);checks.append(bad+'_no_later_native_and_no_numeric_fail')
print(json.dumps({'status':'PASS_CONTINUATION_SYNTHETIC_ONLY','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False,'host_started':False},sort_keys=True))
TEST_RESULTS.append({'module':'test_continuation_cold.py','tests':len(checks),'checks':checks})

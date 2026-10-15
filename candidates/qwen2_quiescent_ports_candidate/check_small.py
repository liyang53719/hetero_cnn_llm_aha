"""One bounded baseline/memo differential batch with complete edge transcripts."""
import argparse
from array import array
from contextlib import nullcontext
from dataclasses import asdict,is_dataclass
import gzip,hashlib,json,resource,subprocess,sys,time
from pathlib import Path
from types import SimpleNamespace
from candidates.qwen2_exact64_tile_profile import profile as p
from .memo import QuiescentPorts
ROOT=p.ROOT;HERE=Path(__file__).resolve().parent
CASES=(('BASE_TWO_TILES',False,'two'),('MEMO_TWO_TILES',True,'two'),
       ('BASE_ABORT_WRITE',False,'abort_write'),('MEMO_ABORT_WRITE',True,'abort_write'))
def sources_now():
    p.source_identity();p.make_qwen2_21_fixture(16);sources=p.source_check()
    for m in tuple(sys.modules.values()):
        f=Path(getattr(m,'__file__','') or '/')
        if f.suffix=='.py' and f.is_relative_to(ROOT):sources[str(f.relative_to(ROOT))]=p.sha(f)
    for f in HERE.iterdir():
        if f.is_file():sources[str(f.relative_to(ROOT))]=p.sha(f)
    for f in (*p.dense_silu.SOURCE_CLOSURE,'candidates/qwen2_supervisor_recovery/observation.py'):sources[f]=p.sha(ROOT/f)
    for f,_ in p.QWEN2_21_SOURCE_PINS:sources[f]=p.sha(ROOT/f)
    sources.update(p.source_identity()['control_source_sha256'])
    external={f for f in sources if not f.startswith(str(HERE.relative_to(ROOT))+'/')}
    tracked=set(subprocess.run(['git','ls-files','--',*sorted(external)],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines())
    p.need(external==tracked,'all external dependencies tracked');return sources

def wire(v):
    if is_dataclass(v):return wire(asdict(v))
    if type(v) is bytes:return {'bytes':v.hex()}
    if type(v) is SimpleNamespace:return wire(vars(v))
    if type(v) is dict:return {k:wire(x) for k,x in v.items()}
    if type(v) in (list,tuple):return [wire(x) for x in v]
    p.need(v is None or type(v) in (int,bool,str),'canonical observation only');return v

def run_case(name,optimized,mode,lib,kernel_path,out,deadline,inputs):
    setup_wall=time.perf_counter();setup_cpu=time.process_time();p.need(lib.td_reset()==0,'fresh native state')
    f=p.make_qwen2_21_fixture(16,7);physical=p.PhysicalMemory(f,{n:(lambda i,raw=raw:raw[i:i+64]) for n,raw in inputs.items()})
    region=f.config.regions[3]
    dense=p.LoanDenseOwner(p.numeric.model.PrefixWorkspace(region.base,region.limit-region.base,8,2560),
      enable_dense_drain=True,enable_k_window=True,enable_ffn_drain=True,enable_ffn_window=True,enable_ffn_tiles=True)
    service=p.ProfiledMatrixService(lib,p.QWEN2_QKV_PROFILE);scalar=p.ScalarService()
    x=p.DiagnosticPublicExecution(p.public.PublicFrontend(physical.metadata_port(),f.config),dense,p.numeric.CappedTrace(out/(name+'.host.jsonl')),
      deadline,fixture=f,host=p.public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
      prefix_owner=p.OfficialPrefixOwner(scalar),attention_owner=p.ResidentPV32AttentionOwner(service,scalar,
        scratch=p.banked_scratch(dense.a_banks),identity=p.expected_kv_identity(physical)),matrix_service=service)
    j0=x.advance_to_request()['ordinary_request'];p.execute_prefix_owner(x,physical,j0);x.publish_completions((0,));physical.publish(j0,x.host)
    j=x.advance_to_request()['ordinary_request'];p.need(service.bindings[j.tag].role=='q_raw','real profiled binding')
    owner=p.Exact64ProjectionOwner(p.Exact64Kernel(kernel_path));driver=p.Exact64PublicDriver(x,physical,j,owner)
    memo=QuiescentPorts(dense) if optimized else None;setup=dict(cpu_seconds=time.process_time()-setup_cpu,wall_seconds=time.perf_counter()-setup_wall)
    points=[];call_wall=call_cpu=0.;events=0;digest=hashlib.sha256();aborted=False;accepted_debt_before_abort=False
    start_wall=time.perf_counter();start_cpu=time.process_time()
    with gzip.open(out/(name+'.edges.jsonl.gz'),'wb',compresslevel=1) as trace, (memo if memo else nullcontext()):
        def tick(abort=False):
            nonlocal call_wall,call_cpu,events
            before=(driver.pending,owner.state);a=time.perf_counter();c=time.process_time()
            e=driver.tick(abort=abort);call_cpu+=time.process_time()-c;call_wall+=time.perf_counter()-a
            observed=dict(before=before,abort=abort,event=e,after_pending=driver.pending,owner_state=owner.state,
              dense_clock=dense.clock,tile_cycle=dense.tiles.cycle,bank_edges=dense.bank_guard.counts['bank_edges'],
              host_state=x.host.state,host_edge=x.last_host_edge,physical_pending=physical.pending)
            raw=(json.dumps(wire(observed),sort_keys=True,separators=(',',':'))+'\n').encode();trace.write(raw);digest.update(raw);events+=1
            return e
        while driver.terminal is None:
            p.need(driver.counts['ticks']<17010 and time.monotonic()<deadline,'bounded differential case')
            trigger=not aborted and (owner.tiles_acked==2 if mode=='two' else driver.pending is not None and driver.pending[0].write)
            if trigger:
                accepted_debt_before_abort=driver.pending is not None
                aborted=True;tick(abort=True)
            else:tick()
            if mode=='two' and len(points)<owner.tiles_acked:
                points.append(dict(tiles=owner.tiles_acked,cpu_seconds=time.process_time()-start_cpu,wall_seconds=time.perf_counter()-start_wall,
                  observed_driver_cpu_seconds=call_cpu,observed_driver_wall_seconds=call_wall,ticks=driver.counts['ticks']))
        terminal=driver.run();expected_tiles=2 if mode=='two' else 1;expected_bytes=512 if mode=='two' else 64
        p.need(aborted and accepted_debt_before_abort==(mode=='abort_write') and terminal['terminal']['status']=='Protocol' and
          terminal['terminal']['write_bytes']==expected_bytes and owner.kernel.report()['fmas']==98304*expected_tiles and
          owner.kernel.report()['adds']==4096*expected_tiles,'fixed arithmetic and actual abort boundary')
        p.need(service.owner is None and dense.bank_guard.lease is None and physical.pending is None and
          lib.matrix_dense_fmas()==lib.matrix_normal_fmas()==0,'all accepted debts drained; zero invented Matrix work')
        for _ in range(8):
            if x.launch_result is not None:break
            hp=x.ports();x.completion_ready=hp['completion'] is not None;x.result_ready=hp['launch_result'] is not None;x.idle_edge()
        p.need(x.host.state=='locked' and x.reset_required() and x.counts['result_fire']==1,'original sticky failed Host terminal')
    p.need('ports' not in dense.__dict__,'instance method restored exactly')
    physical.check_coexistence();p.need(not physical.regions['qraw']['published'],'partial qraw never published')
    raw=physical.raw(j.dst,j.write_bytes);(out/(name+'.qraw.f32le')).write_bytes(raw)
    return dict(case=name,optimized=optimized,mode=mode,points=points,setup=setup,
      observed_driver_cpu_seconds=call_cpu,observed_driver_wall_seconds=call_wall,event_count=events,event_sha256=digest.hexdigest(),
      owner=terminal,final_qraw_sha256=hashlib.sha256(raw).hexdigest(),actual_accepted_debt_before_abort=accepted_debt_before_abort,
      host=x.report(),physical=physical.report(),memo=None if memo is None else memo.report(),original_ticks_skipped=0),raw

def run(out):
    resource.setrlimit(resource.RLIMIT_CPU,(20,20));resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(7<<20,7<<20))
    out=Path(out);p.need(not out.exists(),'fresh namespace');out.mkdir(parents=True);start=time.monotonic();cpu=time.process_time();sources=sources_now()
    p.need(p.sha(p.PRIOR/'RESULT.json')==p.PRIOR_SHA,'same approved prerequisite')
    prior=json.loads((p.PRIOR/'RESULT.json').read_text());kernel_path=p.PRIOR/'exact64.so'
    p.need(p.sha(kernel_path)==prior['build']['library_sha256'] and prior['build']['source_sha256']==p.source_check(),'same actual kernel')
    receipt=p.dense_silu.verify_library(p.PRIOR/'matrix_build/official_bf16_compile.json')
    lib=p.dense_silu.configure_silu_library(p.dense_silu.configure_library(p.C.CDLL(receipt['library'])))
    p.save(out/'PREREGISTRATION.json',dict(sources=sources,cases=CASES,prior_result_sha256=p.PRIOR_SHA,
      limits=dict(cpu_seconds=20,wall_seconds=30,address_space_bytes=2<<30,output_bytes=8<<20)))
    snap=out/'executed_sources';snap.mkdir()
    for f in HERE.iterdir():
        if f.is_file():(snap/f.name).write_bytes(f.read_bytes())
    inputs=dict(x=array('I',(p.word((i%31-15)/16) for i in range(16*1536))).tobytes(),gamma0=array('I',[p.word(1.)]*1536).tobytes(),
      wq=array('H',((0x8000 if i%3==0 else 0)|0x3c00|((i*17)%128) for i in range(1536*1536))).tobytes())
    results=[];outputs=[]
    for name,opt,mode in CASES:
        p.need(time.process_time()-cpu<16 and time.monotonic()-start<24,'no hidden budget expansion')
        r,raw=run_case(name,opt,mode,lib,kernel_path,out,start+27,inputs);results.append(r);outputs.append(raw);p.save(out/'PROGRESS.json',dict(cases=results))
    for a,b in ((0,1),(2,3)):
        p.need(outputs[a]==outputs[b],'same full actual output allocation')
        with gzip.open(out/(CASES[a][0]+'.edges.jsonl.gz'),'rb') as fa,gzip.open(out/(CASES[b][0]+'.edges.jsonl.gz'),'rb') as fb:
            p.need(fa.read()==fb.read(),'every original accepted/stalled/abort edge matches byte for byte')
        for key in ('event_count','event_sha256','owner','host','physical','actual_accepted_debt_before_abort'):
            p.need(results[a][key]==results[b][key],'same protocol/terminal/host/memory accounting')
    p.need(sources==sources_now() and p.sha(p.PRIOR/'RESULT.json')==p.PRIOR_SHA,'frozen sources and prior unchanged')
    result=dict(status='DIFFERENTIAL_COMPLETED',scope='DIAGNOSTIC_SOFTWARE_OWNER',sources=sources,cases=results,
      all_edge_transcripts_equal=True,all_output_bytes_equal=True,fullblock=False,full_projection=False,numerical_reference_comparison=False,
      hardware_mapping='NOT_IMPLEMENTED',performance='NO_GO',hardware_cycles=None,original_ticks_skipped=0,
      cpu_seconds=time.process_time()-cpu,wall_seconds=time.monotonic()-start,
      timing_scope='DRIVER_CALL_TIMERS_PLUS_FULL_LOOP_WITH_OBSERVER_OVERHEAD_NOT_HARDWARE_CYCLES')
    p.save(out/'RESULT.json',result);p.need(sum(f.stat().st_size for f in out.rglob('*') if f.is_file())<8<<20,'final output budget')
    print(json.dumps({k:result[k] for k in ('status','cpu_seconds','wall_seconds','all_edge_transcripts_equal')}))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--execute',action='store_true');a.add_argument('--out');args=a.parse_args()
    if args.execute:p.need(args.out is not None,'output required');run(args.out)
    else:print(json.dumps(dict(status='NOT_EXECUTED',case_count=len(CASES),source_count=len(sources_now()))))

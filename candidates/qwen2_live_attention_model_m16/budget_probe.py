#!/usr/bin/env python3
"""One bounded synthetic public3/Harness observer/timer factorial. No official data."""
import argparse
from collections import Counter
from contextlib import nullcontext
from dataclasses import asdict
import hashlib,json,os,resource,struct,sys,time,traceback
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from candidates.qwen2_live_attention_model_m16 import gates
from candidates.qwen2_live_attention_model_m128.runner import dependencies,save,require

class Timer:
    def __init__(self):self.enabled=False;self.ns=Counter();self.calls=Counter()
    def wrap(self,name,fn):
        def measured(*a,**kw):
            if not self.enabled:return fn(*a,**kw)
            started=time.perf_counter_ns()
            try:return fn(*a,**kw)
            finally:self.ns[name]+=time.perf_counter_ns()-started;self.calls[name]+=1
        return measured
    def wrap_frame_body(self,fn):
        timed=self.wrap('observer_line_body',fn)
        def measured(frame):return timed(frame)
        return measured
    def report(self):return {n:dict(calls=self.calls[n],seconds=self.ns[n]*1e-9) for n in self.calls}

def run(destination):
    resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30))
    require(not sys.flags.optimize,'actual probe needs original synthetic bus assertions')
    require(all(os.environ.get(k)=='1' for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS')),'single thread environment')
    out=Path(destination).absolute();gates.fresh_output(out,ROOT/'work/qwen2_live_qkv_inputs/published7b31_fix_v3');out.mkdir()
    start=time.monotonic();deadline=start+38
    report=dict(status='STARTED_SYNTHETIC_FACTORIAL',scope='synthetic M8 public3/Harness, not official M16 or public21',rows=8,
        old_m128_actual_restarted=False,official_numeric_executed=False,hardware_cycles=None,hardware_utilization=None,
        outer_budget_seconds=45,inner_budget_seconds=38,address_space_bytes=2<<30,threads=1,affinity=sorted(os.sched_getaffinity(0)),conditions=[])
    def checkpoint():save(out/'RESULT.json',report)
    checkpoint()
    try:
        r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation=dependencies()
        from candidates.qwen2_live_attention_model_m16.budget_fixture import attention_fixture
        from candidates.qwen2_live_attention_model_m128.pv32_owner import OfficialPV32AttentionOwner
        from candidates.qwen2_live_attention_model_m128.pv32_observation import PV32AttentionObservation
        from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Harness
        sources=gates.sources();report['source_sha256_before']=sources
        lib,built=dense.build_library(out/'build');report['compile']=built
        paths=dict(python=Path(sys.executable).resolve(),compiler=Path(built['compiler']['path']),library=Path(built['library']))
        report['tools_before']={n:dict(path=str(p),sha256=gates.sha(p),bytes=p.stat().st_size) for n,p in paths.items()}
        q=tuple(scalar.word((i%17-8)/32) for i in range(8*1536));k=tuple(scalar.word((i%13-6)/32) for i in range(8*256));v=tuple(scalar.word((i%19-9)/32+.0007) for i in range(8*256))
        stimulus={n:struct.pack('<%dI'%len(a),*a) for n,a in (('q',q),('k',k),('v',v))}
        report['stimulus']={n:dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) for n,raw in stimulus.items()}
        order=[(path,observe,timed) for timed in (False,True) for path in ('harness','public_physical') for observe in (False,True)]
        report['condition_order']=[dict(path=p,observer=o,timers=t) for p,o,t in order]
        reference=None
        for number,(path,observe,timed) in enumerate(order):
            require(time.monotonic()<deadline,'factorial overall deadline before condition')
            require(lib.td_reset()==0,'fresh per-condition Matrix state')
            service=binding.ProfiledMatrixService(lib,profiles.QWEN2_QKV_PROFILE);shared=scalar.ScalarService();backend=OfficialPV32AttentionOwner(service,shared)
            fixture=attention_fixture(8);memory=prefix.PhysicalMemory(fixture,{n:r.base.bytes_provider(raw) for n,raw in stimulus.items()})
            region=fixture.config.regions[3];dense_owner=owner_module.DenseReductionOwner(original.numeric.model.PrefixWorkspace(region.base,region.limit-region.base,fixture.config.epoch+1,2560),enable_dense_drain=True,enable_k_window=True,enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
            x=original.PublicExecution(public.PublicFrontend(memory.metadata_port(),fixture.config),dense_owner,original.numeric.CappedTrace(),deadline,
                host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),prefix_owner=execution.OfficialPrefixOwner(shared),attention_owner=backend,matrix_service=service)
            job=x.advance_to_request()['ordinary_request'];require(job.kind=='Attention' and job.m==8,'real public3 decoded job')
            timer=Timer();step=lib.matrix_normal_step
            if timed:
                lib.matrix_normal_step=timer.wrap('native_step_ctypes_plus_C',step)
                memory.read_bytes64=timer.wrap('physical_read64',memory.read_bytes64)
                memory.write_event=timer.wrap('physical_write_event',memory.write_event)
                x._host_edge=timer.wrap('public_host_edge',x._host_edge)
                dense_owner.tick=timer.wrap('dense_idle_tick',dense_owner.tick)
            observer=PV32AttentionObservation(backend,source_sha256=sources) if observe else None
            if observe and timed:
                observer._line=timer.wrap_frame_body(observer._line)
            if path=='harness':
                h=Harness(backend);h.bus.input(job.a,q);h.bus.input(job.b,k);h.bus.input(job.c,v);h.bus.output(job.dst,job.write_bytes)
            try:
                with observer if observer else nullcontext():
                    timer.enabled=timed;t0=time.perf_counter()
                    if path=='public_physical':
                        detail=suffix.execute_attention_owner(x,memory,job)
                        raw=memory.raw(job.dst,job.write_bytes);ticks=detail['accepted']['ticks'];reads=detail['accepted']['read_requests'];acks=detail['accepted']['write_acks']
                        public_state=x.report();terminal=detail['result']
                    else:
                        require(h.tick(job=job)['job_fire'],'Harness actual job admission');ticks=0;remaining=5;result=None
                        while result is None:
                            require(time.monotonic()<deadline,'synthetic Harness deadline')
                            kwargs=dict(memory_ready=ticks%5!=0,matrix_request_ready=ticks%7!=0,matrix_result_ready=ticks%11!=0,service_result_ready=ticks%13!=0,service_done_ready=ticks%17!=0,response_ready=True)
                            pending=h.bus.pending
                            if pending and pending.write and backend.ack_bytes+64==job.write_bytes and remaining:kwargs['respond']=False;remaining-=1
                            edge=h.tick(**kwargs);ticks+=1
                            if edge['response_fire']:result=edge['response']
                        raw=h.bus.raw(job.dst);reads=len(h.bus.reads);acks=len(h.bus.acked);terminal=asdict(result);public_state=None
                        require(remaining==0 and h.bus.pending is None,'Harness final ACK/drain')
                    seconds=time.perf_counter()-t0;timer.enabled=False
                require(terminal['status'] is None and backend.state=='idle' and service.owner is None and shared.client is None and backend.matrix_client is None,'successful all-debt terminal')
                item=dict(number=number,path=path,observer=observe,timers=timed,seconds=seconds,ticks=ticks,accepted_read64_events=reads,accepted_write64_acks=acks,output_sha256=hashlib.sha256(raw).hexdigest(),terminal=terminal,owner=backend.report(),matrix=service.report(),scalar_calls=dict(shared.calls),public_state=public_state,measured_components=timer.report())
                item['observer_timing_scope']=dict(line_body_only=True,registered_callback_replaced=False,py_return_callback_seconds=None) if observe and timed else None
                if observer:
                    summary=observer.report();require(summary['status'].startswith('COMPLETE_'),'observer coverage incomplete');item['observation']=summary
                signature=(raw,terminal,backend.report(),service.report(),dict(shared.calls),ticks,reads,acks)
                if reference is None:reference=signature
                require(signature==reference,'timers/observer/path changed functional bytes/counters/terminal')
                require(service.report()['normal_fma_calls']==2654208 and service.counts['normal_steps']==5184 and acks==768,'exact synthetic M8 schedule')
                report['conditions'].append(item);checkpoint();print(json.dumps({k:item[k] for k in ('number','path','observer','timers','seconds')}),flush=True)
            finally:lib.matrix_normal_step=step
        timer=Timer();empty=timer.wrap('empty_callable',lambda:None);timer.enabled=True;t0=time.perf_counter()
        for _ in range(100000):empty()
        report['empty_timer_probe']=dict(iterations=100000,wall_seconds=time.perf_counter()-t0,inside_measurement=timer.report(),scope='Python wrapper/two clocks/counter overhead evidence; not exact subtraction from nested timers')
        report['source_sha256_after']=gates.sources();report['tools_after']={n:dict(path=str(p),sha256=gates.sha(p),bytes=p.stat().st_size) for n,p in paths.items()}
        require(report['source_sha256_after']==sources and report['tools_after']==report['tools_before'],'source/tool drift')
        for name,digest in sources.items():
            raw=(ROOT/name).read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'snapshot drift');p=out/'frozen_sources'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        report.update(status='PASS_SYNTHETIC_PUBLIC3_FACTORIAL_ONLY',host_wall_seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,functional_equivalence_all_eight=True,architecture_speedup_claim=False)
        checkpoint()
    except BaseException as e:
        report.update(status='FAILED_SYNTHETIC_FACTORIAL',error=repr(e),traceback=traceback.format_exc(),host_wall_seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if 'observer' in locals() and observer is not None and observer.closed:report['failed_observer']=observer.report()
        if 'backend' in locals():report['failed_owner']=backend.report()
        if 'service' in locals():report['failed_matrix']=service.report()
        checkpoint();raise

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--actual-budget',action='store_true');ap.add_argument('--out');a=ap.parse_args(argv)
    if not a.actual_budget:
        require(a.out is None,'out needs explicit budget opt-in');print(json.dumps(dict(status='NOT_EXECUTED',official_numeric=False)));return 0
    require(a.out is not None,'fresh output required');run(a.out);return 0
if __name__=='__main__':raise SystemExit(main())

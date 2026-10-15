"""Bounded synthetic public pc1 timing; original software owner remains unchanged."""
import argparse
from array import array
import cProfile
import ctypes as C
import hashlib
import json
from pathlib import Path
import pstats
import resource
import subprocess
import sys
import time
from candidates.qwen2_exact64_projection_integration.kernel import Exact64Kernel,source_check,need
from candidates.qwen2_exact64_projection_integration.owner import Exact64ProjectionOwner
from candidates.qwen2_exact64_projection_integration.driver import Exact64PublicDriver
from candidates.qwen2_exact64_diagnostic_fullblock.public_binding import DiagnosticPublicExecution
from candidates.qwen2_exact64_diagnostic_fullblock.publication import expected_kv_identity
from candidates.qwen2_attention_shared_a_integration.banks import LoanDenseOwner,banked_scratch
from candidates.qwen2_attention_resident_candidate.owner import ResidentPV32AttentionOwner
from candidates.qwen2_resident_matrix.official_bf16 import dense_silu
from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialPrefixOwner
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService,source_identity,word
from candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding import ProfiledMatrixService
from candidates.qwen2_resident_matrix.dense_block_reduce.profile import QWEN2_QKV_PROFILE
from candidates.qwen2_resident_matrix.ffn_public import model as public
from candidates.qwen2_resident_matrix.ffn_public.fixture import make_qwen2_21_fixture,QWEN2_21_SOURCE_PINS
from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory,execute_prefix_owner
from candidates.qwen2_resident_matrix.ffn_public.execute_numeric import numeric
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
PRIOR=ROOT/'work/qwen2_exact64_projection_integration/small02'
PRIOR_SHA='9bddad88b44cf8b7a0283091aca4697876e0f8cbd60e20c0435b5e2f29f0fb90'
CASES=('UNPROFILED_TWO_TILES','CPROFILE_TWO_TILES')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,sort_keys=True,indent=2,allow_nan=False)+'\n')
def sources_now():
    source_identity();make_qwen2_21_fixture(16)
    sources=source_check()
    for module in tuple(sys.modules.values()):
        p=Path(getattr(module,'__file__','') or '/')
        if p.suffix=='.py' and p.is_relative_to(ROOT):sources[str(p.relative_to(ROOT))]=sha(p)
    for p in HERE.iterdir():
        if p.is_file():sources[str(p.relative_to(ROOT))]=sha(p)
    for p in (*dense_silu.SOURCE_CLOSURE,'candidates/qwen2_supervisor_recovery/observation.py'):sources[p]=sha(ROOT/p)
    for p,_ in QWEN2_21_SOURCE_PINS:sources[p]=sha(ROOT/p)
    sources.update(source_identity()['control_source_sha256'])
    external={p for p in sources if not p.startswith(str(HERE.relative_to(ROOT))+'/')}
    tracked=set(subprocess.run(['git','ls-files','--',*sorted(external)],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines())
    need(external==tracked,'all external code sources must be tracked')
    return sources

def timing_snapshot(driver,owner,wall,cpu):
    r=owner.report()
    return dict(wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,
      ticks=driver.counts['ticks'],driver_counts=dict(driver.counts),accepted=r['accepted'],memory=r['memory'],
      kernel_delta=r['kernel_delta'],tiles_output_acked=owner.tiles_acked)

def run_case(name,lib,kernel_path,out,deadline,inputs):
    setup_wall=time.perf_counter();setup_cpu=time.process_time()
    need(lib.td_reset()==0,'fresh actual native reservation state')
    f=make_qwen2_21_fixture(16,7)
    physical=PhysicalMemory(f,{n:(lambda i,raw=raw:raw[i:i+64]) for n,raw in inputs.items()})
    region=f.config.regions[3]
    dense=LoanDenseOwner(numeric.model.PrefixWorkspace(region.base,region.limit-region.base,8,2560),
      enable_dense_drain=True,enable_k_window=True,enable_ffn_drain=True,enable_ffn_window=True,enable_ffn_tiles=True)
    service=ProfiledMatrixService(lib,QWEN2_QKV_PROFILE);scalar=ScalarService()
    x=DiagnosticPublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),dense,numeric.CappedTrace(out/(name+'.host.jsonl')),
      deadline,fixture=f,host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
      prefix_owner=OfficialPrefixOwner(scalar),attention_owner=ResidentPV32AttentionOwner(service,scalar,
        scratch=banked_scratch(dense.a_banks),identity=expected_kv_identity(physical)),matrix_service=service)
    j0=x.advance_to_request()['ordinary_request'];need(j0.kind=='Norm' and j0.tag&65535==0,'actual pc0 offered')
    execute_prefix_owner(x,physical,j0);x.publish_completions((0,));physical.publish(j0,x.host)
    j1=x.advance_to_request()['ordinary_request'];binding=service.bindings.get(j1.tag)
    need(j1.tag&65535==1 and binding is not None and binding.role=='q_raw','actual pc1 Profiled binding')
    owner=Exact64ProjectionOwner(Exact64Kernel(kernel_path));driver=Exact64PublicDriver(x,physical,j1,owner)
    setup=dict(wall_seconds=time.perf_counter()-setup_wall,cpu_seconds=time.process_time()-setup_cpu)
    profiler=cProfile.Profile() if name==CASES[1] else None
    points=[];wall=time.perf_counter();cpu=time.process_time()
    if profiler is not None:profiler.enable()
    try:
        for target in (1,2):
            while owner.tiles_acked<target:
                need(driver.counts['ticks']<17000 and time.monotonic()<deadline,'bounded two tiles')
                driver.tick()
            points.append(timing_snapshot(driver,owner,wall,cpu))
            need(owner.ack_bytes==target*256 and driver.pending is None and physical.pending is None and
              owner.kernel.report()['fmas']==target*98304 and owner.kernel.report()['adds']==target*4096 and
              owner.counts['read_requests']==owner.counts['read_responses']==96+target*3072 and
              owner.counts['write_requests']==owner.counts['write_acks']==target*4 and
              owner.counts['responses']==96+target*3076,'real tile ACK/arithmetic/accepted-beat boundary')
    finally:
        if profiler is not None:profiler.disable()
    # The next tile is only cleared; no next request/FMA is accepted.
    abort_wall=time.perf_counter();abort_cpu=time.process_time();driver.tick(abort=True)
    while driver.terminal is None:
        need(driver.counts['ticks']<17010,'bounded abort');driver.tick()
    terminal=driver.run()
    need(terminal['terminal']['status']=='Protocol' and terminal['terminal']['write_bytes']==512 and
      service.owner is None and dense.bank_guard.lease is None and physical.pending is None and
      lib.matrix_dense_fmas()==lib.matrix_normal_fmas()==0,'actual failed owner terminal, debt drain, zero fake Matrix work')
    for _ in range(8):
        if x.launch_result is not None:break
        ports=x.ports();x.completion_ready=ports['completion'] is not None;x.result_ready=ports['launch_result'] is not None;x.idle_edge()
    need(x.launch_result is not None and x.launch_result['status']=='Protocol' and x.host.state=='locked' and
      x.reset_required() and x.counts['result_fire']==1,'real consumed result retains original sticky reset lock')
    need(not physical.regions['qraw']['terminal'] and not physical.regions['qraw']['published'],'partial output never published')
    physical.check_coexistence();raw=physical.raw(j1.dst,j1.write_bytes)[:512]
    (out/(name+'.f32le')).write_bytes(raw)
    abort=dict(wall_seconds=time.perf_counter()-abort_wall,cpu_seconds=time.process_time()-abort_cpu)
    hotspots=[]
    if profiler is not None:
        profiler.dump_stats(str(out/'driver.pstats'))
        stats=pstats.Stats(profiler)
        for (file,line,func),(primitive,calls,self_s,cumulative,callers) in sorted(stats.stats.items(),key=lambda x:x[1][3],reverse=True)[:40]:
            hotspots.append(dict(file=file,line=line,function=func,primitive_calls=primitive,calls=calls,self_seconds=self_s,cumulative_seconds=cumulative))
    result=dict(case=name,scope='DIAGNOSTIC_SOFTWARE_OWNER',setup_pc0_and_binding=setup,tile_points=points,
      second_tile_increment={key:points[1][key]-points[0][key] for key in ('wall_seconds','cpu_seconds','ticks')},
      abort_and_host_retirement=abort,owner=terminal,profiled=profiler is not None,hotspots=hotspots,
      host=dict(requests=x.counts['request_fire'],owner_results=x.counts['owner_result_fire'],completions=x.counts['completion_fire'],results=x.counts['result_fire'],state=x.host.state),
      physical=physical.report(),output_sha256=hashlib.sha256(raw).hexdigest(),sticky_reset_required=x.reset_required())
    return result,raw

def run(out):
    resource.setrlimit(resource.RLIMIT_CPU,(20,20));resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(7<<20,7<<20))
    out=Path(out);need(not out.exists(),'fresh profile namespace');out.mkdir(parents=True)
    wall=time.monotonic();cpu=time.process_time();sources=sources_now()
    need(sha(PRIOR/'RESULT.json')==PRIOR_SHA,'approved prior result identity')
    prior=json.loads((PRIOR/'RESULT.json').read_text());kernel_path=PRIOR/'exact64.so'
    need(sha(kernel_path)==prior['build']['library_sha256'] and prior['build']['source_sha256']==source_check(),'actual streamed kernel ELF/source')
    receipt=dense_silu.verify_library(PRIOR/'matrix_build/official_bf16_compile.json')
    lib=dense_silu.configure_silu_library(dense_silu.configure_library(C.CDLL(receipt['library'])))
    save(out/'PREREGISTRATION.json',dict(sources=sources,cases=CASES,prior_result_sha256=PRIOR_SHA,
      limits=dict(cpu_seconds=20,wall_seconds=30,address_space_bytes=2<<30,total_output_bytes=8<<20),
      kernel_library_sha256=sha(kernel_path),matrix_receipt=receipt,wholejob=False))
    snap=out/'executed_sources';snap.mkdir()
    for p in HERE.iterdir():
        if p.is_file():(snap/p.name).write_bytes(p.read_bytes())
    inputs=dict(x=array('I',(word((i%31-15)/16) for i in range(16*1536))).tobytes(),
      gamma0=array('I',[word(1.0)]*1536).tobytes(),
      wq=array('H',((0x8000 if i%3==0 else 0)|0x3c00|((i*17)%128) for i in range(1536*1536))).tobytes())
    results=[];outputs=[]
    for name in CASES:
        need(time.process_time()-cpu<16 and time.monotonic()-wall<24,'no budget expansion before next fixed case')
        r,raw=run_case(name,lib,kernel_path,out,wall+27,inputs);results.append(r);outputs.append(raw)
        save(out/'PROGRESS.json',dict(cases=results))
    need(outputs[0]==outputs[1],'profiler does not change actual output bytes')
    need(sources==sources_now() and sha(PRIOR/'RESULT.json')==PRIOR_SHA,'sources/prior remain fixed')
    result=dict(scope='DIAGNOSTIC_SOFTWARE_OWNER',status='PROFILE_COMPLETED',cases=results,profiler_output_bit_diff_count=0,
      input_sha256={n:hashlib.sha256(raw).hexdigest() for n,raw in inputs.items()},sources=sources,
      cpu_seconds=time.process_time()-cpu,wall_seconds=time.monotonic()-wall,
      full_projection=False,fullblock=False,hardware_cycles=None,hardware_mapping='NOT_IMPLEMENTED',performance='NO_GO',
      timing_scope='LOCAL_SOFTWARE_SECONDS_ONLY_NOT_STAGE_TIMING_OF_PRIOR_WHOLEJOB',
      numerical_reference_comparison=False)
    save(out/'RESULT.json',result);need(sum(p.stat().st_size for p in out.rglob('*') if p.is_file())<8<<20,'final output budget')
    print(json.dumps(dict(status=result['status'],cpu_seconds=result['cpu_seconds'],wall_seconds=result['wall_seconds'])))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--out');args=p.parse_args()
    if args.execute:need(args.out is not None,'output required');run(args.out)
    else:print(json.dumps(dict(status='NOT_EXECUTED',cases=CASES,source_count=len(sources_now()))))

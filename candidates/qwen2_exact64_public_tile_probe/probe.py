"""One real public M16 pc0/pc1 partial transaction; never a fullblock run."""
import argparse
from array import array
from dataclasses import asdict
import ctypes as C
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
from candidates.qwen2_exact64_projection_integration.kernel import Exact64Kernel,source_check,need
from candidates.qwen2_exact64_projection_integration.owner import Exact64ProjectionOwner
from candidates.qwen2_exact64_projection_integration.driver import Exact64PublicDriver
from candidates.qwen2_exact64_projection_integration.check_small import control
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
NEW_EXTERNAL={'candidates/qwen2_exact64_diagnostic_fullblock/public_binding.py',
              'candidates/qwen2_exact64_diagnostic_fullblock/publication.py'}
PROJECTION_SOURCE_PINS={'candidates/qwen2_exact64_projection_integration/README.md': '27fe9d2a5a27d093bc8796a8e0ebfd201a15658046a4730895d027a5d96a12a9', 'candidates/qwen2_exact64_projection_integration/check_small.py': 'b4c754cbe355d9b212a8ac86dc88a388261ee985eeee39513987496287d9066e', 'candidates/qwen2_exact64_projection_integration/driver.py': '96a3ca25e31f4159e06f0bbff45403133fb867a4b8e0e92861a4af32e152e658', 'candidates/qwen2_exact64_projection_integration/kernel.cpp': '7306ab783f4840acd626302bc540e1a4b7498ce5cb5704e49fef739eee8b7f36', 'candidates/qwen2_exact64_projection_integration/kernel.py': 'f53475d3148952fc07a661a1a51adc85172207a3bd38481757d7b7fcef4b503f', 'candidates/qwen2_exact64_projection_integration/owner.py': '549501a6543e5059f812c5101db02692c8a1883eb1cee56e4fa1b1e0666ae20b', 'candidates/qwen2_exact64_projection_integration/test_cold.py': '22fb3d738d258676afecc3bcea31e73666d69fc430a12e9ca5f5d53d2295937f'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+'\n')
def sources_now():
    source_identity();make_qwen2_21_fixture(16)
    sources=source_check()
    for module in tuple(sys.modules.values()):
        p=Path(getattr(module,'__file__','') or '/')
        if p.suffix=='.py' and p.is_relative_to(ROOT):sources[str(p.relative_to(ROOT))]=sha(p)
    for p in HERE.iterdir():
        if p.is_file():sources[str(p.relative_to(ROOT))]=sha(p)
    for p in dense_silu.SOURCE_CLOSURE:sources[p]=sha(ROOT/p)
    for p,_ in QWEN2_21_SOURCE_PINS:sources[p]=sha(ROOT/p)
    guard=source_identity()
    sources.update(guard['control_source_sha256'])
    original=PROJECTION_SOURCE_PINS
    for p,h in original.items():need(sha(ROOT/p)==h,'frozen projection source drift');sources[p]=h
    extern={p for p in sources if not p.startswith(str(HERE.relative_to(ROOT))+'/') and p not in original and p not in NEW_EXTERNAL}
    tracked=set(subprocess.run(['git','ls-files','--',*sorted(extern)],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines())
    need(extern==tracked,'external dependencies must be tracked or explicit reviewed siblings')
    return sources

def run(out):
    resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(15<<20,15<<20))
    out=Path(out);need(not out.exists(),'fresh public tile namespace');out.mkdir(parents=True)
    before=sources_now();save(out/'PREREGISTRATION.json',dict(sources=before,case='M16_PC0_THEN_PC1_ONE_TILE_ACK_ABORT',
      limits=dict(cpu_seconds=30,address_space_bytes=2<<30,output_bytes=16<<20),fullblock=False,scope='DIAGNOSTIC_SOFTWARE_OWNER'))
    start=time.monotonic();cpu=time.process_time();snap=out/'executed_sources';snap.mkdir()
    for p in HERE.iterdir():
        if p.is_file():(snap/p.name).write_bytes(p.read_bytes())
    prior=json.loads((PRIOR/'RESULT.json').read_text());need(len(prior['cases'])==8,'completed standalone prerequisite')
    kernel_path=PRIOR/'exact64.so';need(sha(kernel_path)==prior['build']['library_sha256'] and prior['build']['source_sha256']==source_check(),'frozen streamed kernel provenance')
    receipt=dense_silu.verify_library(PRIOR/'matrix_build/official_bf16_compile.json')
    lib=dense_silu.configure_silu_library(dense_silu.configure_library(C.CDLL(receipt['library'])))
    need(lib.td_reset()==0,'fresh actual Matrix state')
    f=make_qwen2_21_fixture(16,7)
    # This test supplies synthetic raw x/gamma0/wq only. n0 is never preloaded.
    xraw=array('I',(word((i%31-15)/16) for i in range(16*1536))).tobytes()
    gamma=array('I',[word(1.0)]*1536).tobytes()
    weight=array('H',((0x8000 if i%3==0 else 0)|0x3c00|((i*17)%128) for i in range(1536*1536))).tobytes()
    inputs={'x':xraw,'gamma0':gamma,'wq':weight}
    physical=PhysicalMemory(f,{n:(lambda i,raw=raw:raw[i:i+64]) for n,raw in inputs.items()})
    region=f.config.regions[3]
    dense=LoanDenseOwner(numeric.model.PrefixWorkspace(region.base,region.limit-region.base,8,2560),
      enable_dense_drain=True,enable_k_window=True,enable_ffn_drain=True,enable_ffn_window=True,enable_ffn_tiles=True)
    service=ProfiledMatrixService(lib,QWEN2_QKV_PROFILE);scalar=ScalarService()
    execution=DiagnosticPublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),dense,numeric.CappedTrace(out/'host.jsonl'),
      start+35,fixture=f,host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
      prefix_owner=OfficialPrefixOwner(scalar),attention_owner=ResidentPV32AttentionOwner(service,scalar,
        scratch=banked_scratch(dense.a_banks),identity=expected_kv_identity(physical)),matrix_service=service)
    need(execution.host.pc==0 and execution.host.jobs==execution.host.completed==0,'fresh original raw Host launch')
    j0=execution.advance_to_request()['ordinary_request'];need(j0.kind=='Norm' and j0.tag&0xffff==0,'actual pc0')
    norm=execute_prefix_owner(execution,physical,j0);execution.publish_completions((0,));physical.publish(j0,execution.host)
    n0=physical.raw(j0.dst,j0.write_bytes);(out/'actual_n0.f32le').write_bytes(n0)
    need(physical.regions['n0']['published'] and execution.host.jobs==execution.host.completed==1,'actual Norm ACK/public completion')
    j1=execution.advance_to_request()['ordinary_request'];need(j1.tag&0xffff==1,'actual pc1')
    binding=service.bindings.get(j1.tag);need(binding is not None and binding.role=='q_raw','actual advance bound Profiled Dense')
    owner=Exact64ProjectionOwner(Exact64Kernel(kernel_path));driver=Exact64PublicDriver(execution,physical,j1,owner)
    while owner.tiles_acked<1:
        need(time.monotonic()<start+35 and driver.counts['ticks']<10000,'one tile bound')
        driver.tick()
    need(owner.ack_bytes==256 and driver.pending is None and physical.pending is None and
         owner.kernel.report()['fmas']==98304 and owner.kernel.report()['adds']==4096,'one genuine tile and four ACKs')
    before_abort=dict(acks=owner.ack_bytes,tiles=owner.tiles_acked,kernel=owner.kernel.report(),physical_pending=physical.pending)
    driver.tick(abort=True)
    while driver.terminal is None:
        need(driver.counts['ticks']<10010,'bounded abort terminal');driver.tick()
    r=driver.run();need(r['terminal']['status']=='Protocol' and r['terminal']['write_bytes']==256,'actual failed Host owner terminal')
    need(service.owner is None and dense.bank_guard.lease is None and physical.pending is None and
         lib.matrix_dense_fmas()==lib.matrix_normal_fmas()==0,'real reservation drained; no fake Matrix arithmetic')
    raw=physical.raw(j1.dst,j1.write_bytes)[:256]
    expected,control_stats=control(owner.kernel.lib,n0[:6144],weight,1,1536)
    need(raw==expected[:256],'actual first tile exact64 same-input bits')
    (out/'actual_qraw_first64.f32le').write_bytes(raw)
    need(not physical.regions['qraw']['terminal'] and not physical.regions['qraw']['published'],'partial output must not publish')
    # Retire the actual failed completion/result through Host ports, not the
    # success-only convenience helpers. No later command is issued.
    for _ in range(8):
        hp=execution.ports()
        execution.completion_ready=hp['completion'] is not None
        execution.result_ready=hp['launch_result'] is not None
        if execution.launch_result is not None:break
        execution.idle_edge()
    need(execution.launch_result is not None and execution.launch_result['status']=='Protocol' and
      execution.host.state=='locked' and execution.reset_required() and execution.counts['result_fire']==1,
      'failed launch response consumed and original sticky reset lock retained')
    need(execution.host.jobs==2 and execution.counts['owner_result_fire']==2 and
      len(execution.requests)==2 and all(v['pc'] in (0,1) for v in execution.completions),'no hidden suffix command')
    physical.check_coexistence();need(before==sources_now(),'public probe source drift')
    report=dict(scope='DIAGNOSTIC_SOFTWARE_OWNER',case='M16_PC0_THEN_PC1_ONE_TILE_ACK_ABORT',
      status='EXPECTED_ABORT_PROTOCOL_PASS',public_prefix_norm_executed=True,profiled_pc1_binding_executed=True,
      full_projection=False,fullblock=False,hardware_mapping='NOT_IMPLEMENTED',performance='NO_GO',
      sources=before,input_sha256={n:hashlib.sha256(raw).hexdigest() for n,raw in inputs.items()},norm=norm,
      projection=r,before_abort=before_abort,control=control_stats,bit_diff_count=0,physical=physical.report(),
      public=execution.report(),matrix=service.report(),sticky_reset_required=execution.reset_required(),
      cpu_seconds=time.process_time()-cpu,wall_seconds=time.monotonic()-start,
      output_bytes_before_result=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()))
    save(out/'RESULT.json',report);need(sum(p.stat().st_size for p in out.rglob('*') if p.is_file())<16<<20,'total output budget')
    print(json.dumps(dict(status=report['status'],bit_diff_count=0,cpu_seconds=report['cpu_seconds'],wall_seconds=report['wall_seconds'])))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--out');args=p.parse_args()
    if args.execute:need(args.out is not None,'output required');run(args.out)
    else:print(json.dumps(dict(status='NOT_EXECUTED',case='M16_PC0_THEN_PC1_ONE_TILE_ACK_ABORT',source_count=len(sources_now()))))

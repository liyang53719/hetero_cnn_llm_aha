"""Small local diagnostic source/artifact checks; no inherited execution grant."""
import ctypes as C
import hashlib,json,os,resource,signal,subprocess,sys,time
from pathlib import Path
from .geometry import need
from .inputs import ROOT,sha
HERE=Path(__file__).resolve().parent
BASE=ROOT/'work/qwen2_m16_stage_diagnostic'
FREEZE=BASE/'SOURCE_FREEZE.json'
PRIOR=ROOT/'work/qwen2_exact64_projection_integration/small02'
PRIOR_SHA='9bddad88b44cf8b7a0283091aca4697876e0f8cbd60e20c0435b5e2f29f0fb90'
ENV=dict(ATEN_CPU_CAPABILITY='avx2',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',
 PYTHONNOUSERSITE='1',PYTHONPATH=str(ROOT/'work/runtime_recovery/site-packages'))

def save(path,value):
    with Path(path).open('w') as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())

def dependencies():
    from candidates.qwen2_exact64_tile_profile import profile as p
    from candidates.qwen2_fullblock_ci_dut import tail,statistics
    from candidates.qwen2_attention_resident_candidate.observation import ResidentAttentionObservation
    from candidates.qwen2_resident_matrix.ffn_public.fullgraph_memory import FullGraphMemory
    from candidates.qwen2_resident_matrix.official_bf16.execution import ObservedSiluLibrary
    from candidates.qwen2_exact64_diagnostic_fullblock.public_binding import DiagnosticVReductionDriver
    from candidates.qwen2_live_attention_model_m128_bounded.attention_driver import execute_attention_owner
    from candidates.qwen2_exact64_diagnostic_fullblock import accounting,retention
    from candidates.qwen2_fullblock_ci_execution import runtime_profile
    from candidates.qwen2_fullblock_reference_m128 import recipe
    from candidates.qwen2_runtime_relocation import runtime
    from scripts import qwen2_layer0_model_gate
    return locals()

def sources_now():
    d=dependencies();p=d['p'];p.source_identity();p.make_qwen2_21_fixture(16)
    sources=p.source_check()
    from scripts import observe_qwen2_attention_model as observer_sources
    sources.update(observer_sources.verify_execution_sources())
    sources[observer_sources.RECEIPT]=sha(ROOT/observer_sources.RECEIPT)
    for module in tuple(sys.modules.values()):
        path=Path(getattr(module,'__file__','') or '/')
        if path.suffix=='.py' and path.is_relative_to(ROOT) and not path.is_relative_to(ROOT/'work/runtime_recovery/site-packages'):sources[str(path.relative_to(ROOT))]=sha(path)
    for path in HERE.iterdir():
        if path.is_file():sources[str(path.relative_to(ROOT))]=sha(path)
    for path in (*p.dense_silu.SOURCE_CLOSURE,'spec/numerical_contract.md',
      'candidates/qwen2_fullblock_reference_m128/pins.json','candidates/qwen2_fullblock_reference_m128/capture.py',
      'candidates/qwen2_fullblock_reference_m128/official/activations.py',
      'config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'):
        sources[path]=sha(ROOT/path)
    for path,_ in p.QWEN2_21_SOURCE_PINS:sources[path]=sha(ROOT/path)
    sources.update(p.source_identity()['control_source_sha256'])
    external={n for n in sources if not n.startswith(str(HERE.relative_to(ROOT))+'/')}
    tracked=set(subprocess.run(['git','ls-files','--',*sorted(external)],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines())
    need(external==tracked,'all external sources tracked')
    return sources

def require_freeze():
    value=json.loads(FREEZE.read_text());current=sources_now();need(value['sources']==current,'reviewed local sources changed');return current

def check_environment():
    need(all(os.getenv(k)==v for k,v in ENV.items()),'fixed local environment')
    need(not any(k in os.environ for k in ('ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA','MKL_CBWR')),'undeclared backend override')
    from candidates.qwen2_runtime_relocation import runtime
    pins=runtime._expected('full29');native=runtime.check_native(pins,family='full29')
    runtime_python(pins)
    return pins,native

def runtime_python(pins):
    result={}
    for name in ('functional.py','modules/activation.py','modules/linear.py','modules/module.py'):
        relative='work/runtime_recovery/site-packages/torch/nn/'+name
        expected=pins['sources'][relative];path=ROOT/relative
        need(path.resolve()==path and not path.is_symlink() and path.stat().st_size==expected['bytes'] and sha(path)==expected['sha256'],'pinned framework Python boundary source')
        result[relative]=dict(expected)
    return result

def artifacts():
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu as dense
    from candidates.qwen2_exact64_projection_integration.kernel import source_check
    need(sha(PRIOR/'RESULT.json')==PRIOR_SHA,'prior native artifact authority')
    prior=json.loads((PRIOR/'RESULT.json').read_text());kernel=PRIOR/'exact64.so'
    need(sha(kernel)==prior['build']['library_sha256'] and prior['build']['source_sha256']==source_check(),'exact64 ELF/source identity')
    receipt=dense.verify_library(PRIOR/'matrix_build/official_bf16_compile.json')
    return kernel,receipt,dict(prior_result_sha256=PRIOR_SHA,kernel_sha256=sha(kernel),matrix_sha256=sha(receipt['library']),matrix_receipt_sha256=sha(PRIOR/'matrix_build/official_bf16_compile.json'))

def limits(cpu,wall):
    resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu));resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(48<<20,48<<20))
    def timeout(*args):raise TimeoutError('fixed diagnostic phase wall budget')
    need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'no preexisting timer')
    signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,wall)

def fresh_output(out,phase):
    out=Path(out).absolute();need(out.parent==BASE/'cost01' and out.name==phase and out.resolve()==out and not out.exists(),'fixed fresh phase namespace')
    out.mkdir();return out

def snapshot_sources(out,sources):
    save(out/'SOURCES_BEFORE.json',sources);dst=out/'executed_sources';dst.mkdir()
    for name in sources:
        path=ROOT/name
        if path.parent==HERE:(dst/path.name).write_bytes(path.read_bytes())

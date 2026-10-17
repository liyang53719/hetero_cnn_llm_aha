"""Zero-fuzz source composition only; never invokes Scala, compiler or simulator."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_packed_stream/'
SCALA='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
TARGET=SCALA+'MatrixPipeline.scala'
BASE=(SCALA+'MatrixPipeline.scala',SCALA+'BurstProtocol.scala',SCALA+'RetainedMatrix.scala',
 'candidates/qwen2_resident_matrix/MatrixAccumulatorSeedProtocol.scala')
LEAF='candidates/qwen2_resident_matrix/transposed_seed/leaf/retained_accumulator_seed.patch'
BASE+=tuple(n for n in ('rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv', 'rtl/matrix/candidates/rev8b_b/bf16_context_lane_cluster16_rev8b_b_candidate.sv', 'rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv', 'rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv', 'rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv', 'rtl/integration/qwen2_matrix_command_endpoint.sv', 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/RetainedMatrix.scala') if n not in BASE)
PATCHES=(LEAF,'candidates/qwen2_resident_matrix/transposed_route/combined_service.patch','candidates/qwen2_resident_matrix/transposed_seed/service_seed.patch')
OWN=tuple(PREFIX+n for n in ('PackedAttentionStreamClient.scala','drain_status.patch','model.py','prepare.py','test_model.py','test_sources.py','README.md'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def apply(out,name):
 subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=(ROOT/name).read_bytes(),cwd=out,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=5)
def baseline(out):
 out=Path(out);out.mkdir(parents=True)
 for n in BASE:
  p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/n).read_bytes())
 for n in PATCHES:apply(out,n)
 return out
def compose(out,*,verify=True):
 if verify:check()
 out=Path(out)
 if out.exists():raise ValueError('fresh source destination')
 baseline(out);apply(out,PREFIX+'drain_status.patch')
 name=SCALA+'PackedAttentionStreamClient.scala';(out/name).write_bytes((HERE/'PackedAttentionStreamClient.scala').read_bytes())
 return out

def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 if p['sources']!={n:sha(ROOT/n) for n in (*BASE,*PATCHES)} or p['own']!={n:sha(ROOT/n) for n in OWN}:raise ValueError('source drift')
 with tempfile.TemporaryDirectory() as d:
  out=compose(Path(d)/'source',verify=False)
  actual={str(x.relative_to(out)):sha(x) for x in out.rglob('*') if x.is_file()}
 if p['generated']!=actual:raise ValueError('generated source drift')
 return p

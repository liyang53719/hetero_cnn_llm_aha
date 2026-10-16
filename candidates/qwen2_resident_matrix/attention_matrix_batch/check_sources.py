"""Pinned source-only arithmetic/resource provenance; no execution admission."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
PREFIX='candidates/qwen2_resident_matrix/attention_matrix_batch/'
SOURCES=('candidates/qwen2_resident_matrix/official_bf16/owners.py','candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py','candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp','candidates/qwen2_resident_matrix/ffn_attention/scalar_recipe.py','candidates/qwen2_resident_matrix/ffn_attention/test_scalar_recipe.py','candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py','chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala','rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv','chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala','chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala','candidates/qwen2_resident_matrix/ffn_public/prefix_owners.py')
OWN=tuple(PREFIX+n for n in ('model.py','schedule.py','test_model.py','test_schedule.py','check_sources.py','README.md'))

def check():
    pins=json.loads((HERE/'pins.json').read_bytes())
    if type(pins) is not dict or set(pins)!={'schema','profile','sources','own','native_execution','rtl_execution'}:raise ValueError('pin schema')
    if pins['schema']!=1 or type(pins['schema']) is not int or pins['profile']!='attention-fixed-matrix-selected-projection-v1' or pins['native_execution'] is not False or pins['rtl_execution'] is not False:raise ValueError('pin scope')
    if set(pins['sources'])!=set(SOURCES) or set(pins['own'])!=set(OWN):raise ValueError('source inventory')
    for group in ('sources','own'):
        for name,digest in pins[group].items():
            p=Path(name)
            if p.is_absolute() or '..' in p.parts or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=digest:raise ValueError('source drift')
    pipeline=(ROOT/SOURCES[6]).read_text();scheduler=(ROOT/SOURCES[7]).read_text()
    required=('Reg(Vec(2,new MatrixStreamResult))','new Queue(new Meta,8,pipe=true)','Seq.fill(8)(Module(new RetainedMatrixEndpoint))','x.context<5.U','tags.io.deq.bits.emit','values.io.enq.ready')
    if not all(x in pipeline for x in required) or 'context_fifo[0:7]' not in scheduler or 'logic [4:0] busy_q' not in scheduler:raise ValueError('resource source contract')
    scalar=(ROOT/SOURCES[8]).read_text();owner=(ROOT/SOURCES[9]).read_text()
    if not all(x in scalar for x in ('io.request.ready:=state===idle','is(normal){','when(io.result.fire){state:=idle}')) or not all(x in owner for x in ('st("attReduce")','st("attReduceDone")','st("scalarReq")','st("scalarRsp")')):raise ValueError('scalar state contract')
    return dict(status='PASS_SOURCE_ONLY',sources=len(pins['sources']),own=len(pins['own']),native_execution=False,rtl_execution=False)

if __name__=='__main__':print(json.dumps(check(),sort_keys=True))

"""Pin the retained FIFO proposal and its original numerical/source closure."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_retained_result/'
SOURCES=('candidates/qwen2_resident_matrix/attention_matrix_batch/README.md', 'candidates/qwen2_resident_matrix/attention_matrix_batch/check_sources.py', 'candidates/qwen2_resident_matrix/attention_matrix_batch/model.py', 'candidates/qwen2_resident_matrix/attention_matrix_batch/pins.json', 'candidates/qwen2_resident_matrix/attention_matrix_batch/schedule.py', 'candidates/qwen2_resident_matrix/attention_matrix_batch/test_model.py', 'candidates/qwen2_resident_matrix/attention_matrix_batch/test_schedule.py', 'candidates/qwen2_resident_matrix/attention_scalar_schedule/README.md', 'candidates/qwen2_resident_matrix/attention_scalar_schedule/check_sources.py', 'candidates/qwen2_resident_matrix/attention_scalar_schedule/model.py', 'candidates/qwen2_resident_matrix/attention_scalar_schedule/pins.json', 'candidates/qwen2_resident_matrix/attention_scalar_schedule/test_model.py', 'candidates/qwen2_resident_matrix/attention_scheduled_numeric/README.md', 'candidates/qwen2_resident_matrix/attention_scheduled_numeric/check_sources.py', 'candidates/qwen2_resident_matrix/attention_scheduled_numeric/controller.py', 'candidates/qwen2_resident_matrix/attention_scheduled_numeric/pins.json', 'candidates/qwen2_resident_matrix/attention_scheduled_numeric/ports.py', 'candidates/qwen2_resident_matrix/attention_scheduled_numeric/test_controller.py', 'candidates/qwen2_resident_matrix/attention_scheduled_numeric/test_ports.py', 'candidates/qwen2_resident_matrix/dense_block_reduce/vector_add.patch', 'candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py', 'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp', 'candidates/qwen2_resident_matrix/ffn_attention/scalar_recipe.py', 'candidates/qwen2_resident_matrix/ffn_attention/test_scalar_recipe.py', 'candidates/qwen2_resident_matrix/ffn_public/prefix_owners.py', 'candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py', 'candidates/qwen2_resident_matrix/ffn_tiles/tile_ports.patch', 'candidates/qwen2_resident_matrix/official_bf16/owners.py', 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala', 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala', 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala', 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala', 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/VectorSilu.scala', 'reports/execution/QWEN2_DENSE_BLOCK_REDUCTION_20261012/M128_RESULT.json', 'rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv')
SOURCES=tuple(sorted((*SOURCES, 'candidates/qwen2_resident_matrix/raw_kv_parent/integration.patch', 'candidates/qwen2_resident_matrix/raw_kv/model.py', 'candidates/qwen2_resident_matrix/transposed_down/owner_down.patch')))
OWN=tuple(PREFIX+n for n in ('controller.py','test_controller.py','check_sources.py','README.md'))

def check():
    pins=json.loads((HERE/'pins.json').read_bytes())
    if type(pins) is not dict or set(pins)!={'schema','profile','sources','own'} or type(pins['schema']) is not int or pins['schema']!=1 or pins['profile']!='retained-joined-result-consumption-v1':raise ValueError('source contract')
    if set(pins['sources'])!=set(SOURCES) or set(pins['own'])!=set(OWN):raise ValueError('source inventory')
    for group in ('sources','own'):
        for name,digest in pins[group].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('source drift')
    prefix='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
    fifo=(ROOT/(prefix+'MatrixPipeline.scala')).read_text()
    core=(ROOT/(prefix+'Qwen2Block.scala')).read_text()
    if not all(x in fifo for x in ('Reg(Vec(2,new MatrixStreamResult))','io.deq.bits:=storage(head)','io.enq.ready:=count<2.U||io.deq.fire','io.port.result<>values.io.deq','state===finish && !values.io.deq.valid')):raise ValueError('original joined FIFO contract')
    if not all(x in core for x in ('val acc=Reg(Vec(16,UInt(32.W)))','val tmp=Reg(Vec(16,UInt(32.W)))','val av=Reg(Vec(16,UInt(32.W)))','val bv=Reg(Vec(16,UInt(32.W)))')):raise ValueError('proposed scalar staging resources')
    raw=(ROOT/'candidates/qwen2_resident_matrix/raw_kv_parent/integration.patch').read_text()
    bank=(ROOT/'candidates/qwen2_resident_matrix/transposed_down/owner_down.patch').read_text()
    if not all(x in raw for x in ('val line=UInt(13.W)','p.request.bits.key.line<4096.U','p.ack.bits.line<4096.U')) or 'Seq.fill(16)(SyncReadMem(1376,UInt(256.W)))' not in bank:raise ValueError('existing raw range/capacity')
    return dict(status='PASS_SOURCE_ONLY',sources=len(SOURCES),own=len(OWN),rtl_execution=False,native_execution=False)

if __name__=='__main__':print(json.dumps(check(),sort_keys=True))

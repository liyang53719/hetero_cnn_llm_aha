"""Exact source identities and narrow resource/FSM assertions; no RTL admission."""
import hashlib
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREFIX = 'candidates/qwen2_resident_matrix/attention_scalar_schedule/'
C = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
SOURCES = (C+'BlockFloat.scala', C+'Qwen2Block.scala', C+'VectorSilu.scala', C+'QwenOwnerProtocol.scala',
           'candidates/qwen2_resident_matrix/ffn_tiles/tile_ports.patch',
           'candidates/qwen2_resident_matrix/dense_block_reduce/vector_add.patch',
           'candidates/qwen2_resident_matrix/official_bf16/owners.py')
OWN = tuple(PREFIX+n for n in ('model.py', 'test_model.py', 'check_sources.py', 'README.md'))


def check():
    pins = json.loads((HERE/'pins.json').read_bytes())
    if type(pins) is not dict or set(pins) != {'schema', 'profile', 'sources', 'own'} or type(pins['schema']) is not int or pins['schema'] != 1 or pins['profile'] != 'exclusive-existing-alu-sfu-metadata-schedule-v1':
        raise ValueError('pin schema')
    if set(pins['sources']) != set(SOURCES) or set(pins['own']) != set(OWN):
        raise ValueError('pin inventory')
    for group in ('sources', 'own'):
        for name, digest in pins[group].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
                raise ValueError('source drift')
    scalar, core, silu, owner, tile, add, numerical = ((ROOT/name).read_text() for name in SOURCES)
    checks = ((scalar, ('io.request.ready:=state===idle', 'is(normal){', 'state:=done', 'when(io.result.fire){state:=idle}', 'index:=6.U', 'is(expFinish)', 'div.io.inReady', 'div.io.outValid_div||div.io.outValid_sqrt')),
              (core, ('(0 until 16).map{i=>val a=Module(new HeteroFP32Alu)', 'st("normSquare")', 'st("ropeMul0")', 'st("biasSum")', 'val vectorMul=WireDefault(false.B)')),
              (silu, ('Seq.fill(lanes)(Module(new BlockScalarFloat))', 'new SiluVectorUnit(16)', 'val allReady', 'val allValid', 'state === issue && allReady', 'state === waitAll && allValid', 'phase === 5.U')),
              (owner, ('val active=RegInit(false.B)', 'val mode=Reg(UInt(4.W))', 'ScheduledSiluOwner')),
              (tile, ('!overlap', 'enableTileLoan')),
              (add, ('binaryAdd', 'ScalarOp.Add.U', 'loanActive')),
              (numerical, ('def _attention',)))
    for text, fragments in checks:
        if not all(fragment in text for fragment in fragments):
            raise ValueError('resource/FSM source assertion')
    return dict(status='PASS_SOURCE_ONLY', source_count=len(SOURCES), own_count=len(OWN), arithmetic_executed=False, rtl_executed=False)


if __name__ == '__main__':
    print(json.dumps(check(), sort_keys=True))

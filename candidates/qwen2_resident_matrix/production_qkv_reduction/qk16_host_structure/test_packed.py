import tempfile,unittest
from pathlib import Path
from check_packed import check_packed
class Packed(unittest.TestCase):
 def fixture(self):
  k=['    inst core of Qwen2ContinuousBlock','    inst matrix of MatrixPipelineService','    inst dense of TransposedDenseDownOwner','    inst legacy of LegacyMatrixStreamClient']
  def c(t,v,guard=False):k.append(('      ' if guard else '    ')+'connect '+t+', '+v)
  c('core.io.packedQkStepsDrained','matrix.io.packedStepsDrained')
  for l in ['group.ready','step.ready','result.valid','done.valid']:c('core.io.packedQk.'+l,'and(core.io.packedQkActive, matrix.io.port.'+l+')')
  for l in ['result.bits.error','result.bits.last','result.bits.context','done.bits.error','done.bits.tag']+[f'result.bits.value[{i}][{j}]' for i in range(16) for j in range(256)]:c('core.io.packedQk.'+l,'matrix.io.port.'+l)
  k.append('    when core.io.packedQkActive :')
  for target in ['legacy.io.port','dense.io.matrix']:
   for l in ['group.ready','step.ready','result.valid','done.valid']:c(target+'.'+l,'UInt<1>(0h0)',True)
  for l in ['group.valid','group.bits.opcode','group.bits.sliceMask','group.bits.tag','step.valid','result.ready','done.ready','abort']:c('matrix.io.port.'+l,'core.io.packedQk.'+l,True)
  for l in ['emit','finish','last','clear','context']+[f'a[{i}]' for i in range(16)]+[f'b[{i}]' for i in range(256)]:c('matrix.io.port.step.bits.'+l,'core.io.packedQk.step.bits.'+l,True)
  for l in ['group.bits.transposedDense','group.bits.groupSequence']:c('matrix.io.port.'+l,'UInt<1>(0h0)',True)
  for l in ['matrix.io.port.seed.begin.valid','matrix.io.port.seed.beat.valid','matrix.io.port.seed.ack.ready','dense.io.matrix.seed.begin.ready','dense.io.matrix.seed.beat.ready','dense.io.matrix.seed.ack.valid']:c(l,'UInt<1>(0h0)',True)
  for msg,line in [('packed QK lease belongs only to the original core',523),('QKV reduction and packed QK cannot share the Matrix lease',570)]:k+=['    printf(clock, UInt<1>(0h1), "'+msg+' '+msg+'") @[QwenOwnerProtocol.scala '+str(line)+':9]','    assert(clock, cond, UInt<1>(0h1), "") @[QwenOwnerProtocol.scala '+str(line)+':9]']
  return 'circuit HostBlockTop :\n  module QwenOwnerKernel :\n'+'\n'.join(k)+'\n  module Qwen2ContinuousBlock :\n    inst packedQk of PackedAttentionStreamClient\n    regreset packedOwned : UInt<1>, clock, reset, UInt<1>(0h0)\n    connect io.packedQkActive, packedOwned\n    connect packedQk.io.stepsDrained, io.packedQkStepsDrained\n  module PackedAttentionStreamClient :\n'
 def check(self,s):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.fir';p.write_text(s);return check_packed(p)
 def test_fixture(self):self.assertEqual(self.check(self.fixture())['packed_client_instances'],1)
 def test_route_mutants(self):
  s=self.fixture()
  for a,b in [('and(core.io.packedQkActive, matrix.io.port.group.ready)','or(core.io.packedQkActive, matrix.io.port.group.ready)'),('when core.io.packedQkActive :','when other :'),('connect matrix.io.port.seed.begin.valid, UInt<1>(0h0)','connect matrix.io.port.seed.begin.valid, UInt<1>(0h1)'),('connect matrix.io.port.group.bits.tag, core.io.packedQk.group.bits.tag','connect matrix.io.port.group.bits.tag, wrong')]:
   with self.subTest(a=a),self.assertRaises(ValueError):self.check(s.replace(a,b))
 def test_late_override(self):
  s=self.fixture().replace('  module Qwen2ContinuousBlock :','    connect matrix.io.port.step.valid, other\n  module Qwen2ContinuousBlock :')
  with self.assertRaises(ValueError):self.check(s)
 def test_additional_overrides(self):
  for target,value in [('core.io.packedQkStepsDrained','UInt<1>(0h1)'),('matrix.io.port.group.bits.groupSequence','UInt<8>(0hff)'),('matrix.io.port.step','other')]:
   with self.subTest(target=target),self.assertRaises(ValueError):self.check(self.fixture().replace('  module Qwen2ContinuousBlock :','    connect '+target+', '+value+'\n  module Qwen2ContinuousBlock :'))
  with self.assertRaises(ValueError):self.check(self.fixture().replace('  module PackedAttentionStreamClient :','    connect io.packedQkActive, UInt<1>(0h0)\n  module PackedAttentionStreamClient :'))
 def test_dead_core_guard(self):
  with self.assertRaises(ValueError):self.check(self.fixture().replace('    connect io.packedQkActive, packedOwned','    when dead :\n      connect io.packedQkActive, packedOwned'))
 def test_invalidated_route(self):
  with self.assertRaises(ValueError):self.check(self.fixture().replace('  module Qwen2ContinuousBlock :','    invalidate matrix.io.port.step\n  module Qwen2ContinuousBlock :'))
 def test_expanded_leaf_mutants(self):
  s=self.fixture()
  for a,b in [('connect core.io.packedQk.result.bits.value[15][255], matrix.io.port.result.bits.value[15][255]','connect core.io.packedQk.result.bits.value[15][255], matrix.io.port.result.bits.value[15][254]'),('connect matrix.io.port.step.bits.b[255], core.io.packedQk.step.bits.b[255]','connect matrix.io.port.step.bits.b[255], wrong')]:
   with self.subTest(a=a),self.assertRaises(ValueError):self.check(s.replace(a,b))
  with self.assertRaises(ValueError):self.check(s.replace('  module Qwen2ContinuousBlock :','    connect core.io.packedQk.result.bits.value[15], other\n  module Qwen2ContinuousBlock :'))
 def test_only_exact_memory_default_allowed(self):
  s=self.fixture();block='    wire _scoreOut_WIRE : UInt<16> @[x]\n    invalidate _scoreOut_WIRE @[x]\n    when _scoreOut_T : @[x]\n      connect _scoreOut_WIRE, key @[x]\n      node _scoreOut_T_1 = bits(_scoreOut_WIRE, 9, 0) @[x]\n      read mport scoreOut = scores[_scoreOut_T_1], clock @[x]\n'
  s=s.replace('  module PackedAttentionStreamClient :',block+'  module PackedAttentionStreamClient :')
  self.assertEqual(len(self.check(s)['invalidation_evidence']),1)
  with self.assertRaises(ValueError):self.check(s.replace('connect _scoreOut_WIRE, key','connect _scoreOut_WIRE, other'))
  with self.assertRaises(ValueError):self.check(s.replace('  module PackedAttentionStreamClient :','    node alias = _scoreOut_WIRE\n  module PackedAttentionStreamClient :'))
 def test_missing_assert(self):
  with self.assertRaises(ValueError):self.check(self.fixture().replace('assert(clock','removed(clock'))
 def test_duplicate_client(self):
  with self.assertRaises(ValueError):self.check(self.fixture().replace('    inst packedQk of PackedAttentionStreamClient','    inst packedQk of PackedAttentionStreamClient\n    inst second of PackedAttentionStreamClient'))
if __name__=='__main__':unittest.main()

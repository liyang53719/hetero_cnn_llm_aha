import ast,json,hashlib,tempfile,unittest
from pathlib import Path
import run_structure as r
from check_structure import check
P=Path(__file__).parent
class Cold(unittest.TestCase):
 def test_parse(self):
  for p in P.glob('*.py'):ast.parse(p.read_text())
 def test_no_execute_default(self):
  class Args:execute=False
  with self.assertRaises(ValueError):r.run(Args())
 def test_fixed_profile(self):
  s=(P/'source/ProductionHostStructure.scala').read_text()
  for x in ['new HostBlockTop(','maxTokens=1024','matrixColumns=256','burstWrites=true','enableResidentFfn=true','enablePublic21QkvReduction=true','Qwen2OfficialBf16V2','emitCHIRRTL']:self.assertIn(x,s)
  self.assertNotIn('emitSystemVerilog',s)
 def test_source_pins(self):
  p=json.loads((P/'SOURCE_PINS.json').read_text());b=json.loads((P/'BASELINE_CLASS_PINS.json').read_text())
  self.assertEqual(len(p),92);self.assertEqual({n:h for n,h in p.items() if not n.startswith('structure/')},b['source_sha256'])
  self.assertEqual(p['structure/ProductionHostStructure.scala'],hashlib.sha256((P/'source/ProductionHostStructure.scala').read_bytes()).hexdigest())
 def synthetic(self):
  # Only a parser fixture, not synthesized/compiled hardware.
  names=['HostBlockCommands','TransposedDenseDownOwner','TransposedDownDenseBanks','ScheduledSiluOwner','VectorSiluOwner','MatrixPipelineService','LegacyMatrixStreamClient','FfnResidentCoordinator','Public21QkvReductionRouter','SharedMemoryArbiter','RetainedIdmaWeightBurstAdapter','idma_backend_rw_axi_flat_wrap']
  out='circuit HostBlockTop :\n  module HostBlockTop :\n    inst owner of QwenOwnerKernel\n'
  out+='  module QwenOwnerKernel :\n'
  for i,n in enumerate(names):out+=f'    inst x{i} of {n}\n'
  out+='    inst vector of SiluVectorUnit\n'
  for i in range(8):out+=f'    inst m{i} of qwen2_matrix_command_endpoint_{i}\n    inst c{i} of tc_clk_gating_{i}\n'
  for n in ['matrixDebt','readDebt','writeDebt','memoryDebt','seedDebt']:out+=f'    regreset {n} : UInt<1>, clock, reset, UInt<1>(0)\n'
  ports={'matrixDebt':('x5.io.port.group','x5.io.port.done'),'readDebt':('x1.io.burst','x1.io.burstResponse'),'writeDebt':('x1.io.writeRequest','x1.io.writeResponse'),'memoryDebt':('io.memory','io.response'),'seedDebt':('x5.io.port.seed.begin','x5.io.port.seed.ack')}
  for debt,(accept,retire) in ports.items():
   out+=f'    when and({accept}.valid, {accept}.ready) :\n      connect {debt}, UInt<1>(0h1)\n    when and({retire}.valid, {retire}.ready) :\n      connect {debt}, UInt<1>(0h0)\n'
  out+='    node combined = and(not(matrixDebt),not(seedDebt))\n    connect x8.io.matrixDrained, and(combined,not(x5.io.port.result.valid),not(x5.io.port.done.valid))\n    connect x8.io.dmaDrained, and(not(readDebt),not(writeDebt),not(memoryDebt))\n'
  for n in names:out+='  module '+n+' :\n'
  out+='  module SiluVectorUnit :\n'
  for i in range(16):out+=f'    inst f{i} of BlockScalarFloat_{i}\n'
  for i in range(16):out+=f'  module BlockScalarFloat_{i} :\n'
  for i in range(8):out+=f'  extmodule qwen2_matrix_command_endpoint_{i} :\n  extmodule tc_clk_gating_{i} :\n'
  return out
 def test_graph_and_debt_dependencies(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'test.fir';s=self.synthetic();p.write_text(s);x=check(p);self.assertEqual(x['resource_counts']['qwen2_matrix_command_endpoint'],8)
   for bad in [s.replace('    node combined =','    connect matrixDebt, someNode\n    node combined ='),s.replace('    node combined =','    node combined = matrixDebt\n    node combined ='),s.replace('when and(','when or('),s.replace('not(writeDebt)','writeDebt'),s+'  module HostBlockTop :\n',s.replace('inst x0 of HostBlockCommands','inst x1 of HostBlockCommands'),s.replace('not(writeDebt)','UInt(1)'),s.replace('inst m7 of','inst m7_removed of').replace('qwen2_matrix_command_endpoint_7\n','qwen2_matrix_command_endpoint_6\n'),s.replace('regreset seedDebt','regreset removedDebt')]:
    # Duplicate endpoint type still has eight physical instances and is legal.
    if 'm7_removed' in bad:continue
    p.write_text(bad)
    with self.assertRaises(ValueError):check(p)
 def test_reject_duplicate_resource(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'test.fir';p.write_text(self.synthetic().replace('    inst owner of QwenOwnerKernel','    inst owner of QwenOwnerKernel\n    inst second of MatrixPipelineService'))
   with self.assertRaises(ValueError):check(p)
if __name__=='__main__':unittest.main(verbosity=2)

"""Source and bounded control-contract tests only; never compile/run hardware."""
from pathlib import Path
import argparse,hashlib,json,re,unittest
HERE=Path(__file__).resolve().parent
ROOT=HERE/"composed"
P='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
NEW='candidates/qwen2_resident_matrix/production_qkv_reduction/Public21QkvReductionRouter.scala'
def text(n):return (ROOT/'source'/n).read_text()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def audit(sources=None):
 s=sources or {str(p.relative_to(ROOT/'source')):p.read_text() for p in (ROOT/'source').rglob('*') if p.is_file()}
 k=s[P+'QwenOwnerProtocol.scala'];r=s[NEW];top=s[P+'HostBlockTop.scala'];v=s[P+'OverlappedSilu.scala']
 checks={
 'production_route':(k,'Some(Module(new Public21QkvReductionRouter))'),
 'default_false':(k,'enablePublic21QkvReduction:Boolean=false'),
 'ordinary_alias':(k,'qkvRouter.get.io.ordinaryJob else io.job'),
 'done_alias':(k,'qkvRouter.get.io.ordinaryDone else io.done'),
 'actual_job_binding':(k,'r.io.job<>io.job;io.done<>r.io.done;r.io.residentHost<>io.resident.get'),
 'actual_window_binding':(k,'r.io.residentWindow<>resident.get.io.window;r.io.residentDrain<>resident.get.io.drain'),
 'actual_tile_binding':(k,'r.io.residentTiles<>resident.get.io.tiles;r.io.residentVector<>resident.get.io.silu'),
 'actual_service_window':(k,'dense.window.get<>ffnWindow.get'),
 'actual_service_tiles':(k,'dense.tiles.get<>ffnTiles.get;silu.get.io.loan.get<>ffnTileSilu.get'),
 'actual_service_drain':(k,'dense.drain.get<>ffnDrain.get'),
 'window_modes':(k,'enableKWindow=enablePublic21QkvReduction,enableDenseDrain=enablePublic21QkvReduction'),
 'binary_owner_forward':(k,'enableBinaryAdd=enablePublic21QkvReduction'),
 'binary_wrapper_forward':(v,'new VectorSiluOwner(enableTileLoan,numericPolicy=numericPolicy,enableBinaryAdd=enableBinaryAdd)'),
 'binary_port_forward':(v,'new SiluOwnerPort(enableTileLoan,enableBinaryAdd)'),
 'resident_binary_false':(r,'v.request.bits.binaryAdd.get:=Mux(q,qv.request.bits.binaryAdd.get,false.B)'),
 'resident_window_false':(r,'residentRequest.kWindow.get.enabled:=false.B'),
 'resident_handoff':(k,'io.residentHandoff.get:=r.io.handoff'),
 'top_backend_fault':(top,'owner.io.public21BackendReset.get:=hub.io.resetRequired || dmaPoison'),
 'actual_matrix_retire':(k,'when(matrix.io.port.done.fire){assert(matrixDebt);matrixDebt:=false.B}'),
 'actual_read_retire':(k,'when(dense.burstResponse.fire){assert(readDebt);readDebt:=false.B}'),
 'actual_write_retire':(k,'when(dense.writeResponse.get.fire){assert(writeDebt);writeDebt:=false.B}'),
 'actual_nonburst_retire':(k,'when(io.response.fire){assert(memoryDebt);memoryDebt:=false.B}'),
 'actual_seed_retire':(k,'when(matrix.io.port.seed.get.ack.fire){assert(seedDebt);seedDebt:=false.B}'),
 'registered_feedback':(k,'r.io.backendReset:=io.public21BackendReset.get || RegNext(sharedPoison || gdnPoison,false.B)'),
 'retained_matrix_owner':(k,'when(r.io.reductionOwns){matrix.io.port.abort:=dense.matrix.abort || r.io.backendAbort}'),
 'range0':(r,'reduction.io.dense.request.bits.kRanges(0).end:=1024.U'),
 'range1':(r,'reduction.io.dense.request.bits.kRanges(1).begin:=1024.U'),
 'range_end':(r,'reduction.io.dense.request.bits.kRanges(1).end:=1536.U'),
 'pair_order':(r,'reduction.io.dense.request.bits.pairReverse:=true.B'),
 'raw_partial':(r,'!j.outputBf16 && !j.materializeDenseOutput'),
 'ack_owner':(r,'when(io.done.fire || io.residentHost.result.fire){state:=idle}'),
 'no_abort_clearing':(r,'val cancel=fault || io.residentHost.abort || io.backendReset'),
 'host_late_failure_consumed':(s[P+'HostBlockCommands.scala'],'when(io.resident.get.resetRequired && (resident.get.pending || r.status===0.U)){fail(Status.Protocol.U)}'),
 'terminal_ready_after_fault':(r,'reduction.io.dense.result.ready:=state===reducing && io.done.ready'),
 'production_matrix_backend':(k,'val matrix=Module(new MatrixPipelineService('),
 }
 for name,(source,fragment) in checks.items():need(fragment in source,name)
 need(not re.search(r'(?<!io)\.ordinary(Job|Done)',k),'child interface renamed')
 for classname in ['Public21QkvReductionRouter','MatrixPipelineService','TransposedDenseDownOwner','ScheduledSiluOwner']:
  need(len(re.findall(r'new '+classname+r'\b',k))==1,'kernel instance '+classname)
 need(r.count('Module(new DenseBlockReductionCoordinator)')==1,'one reduction coordinator')
 need(not re.search(r'\b(?:SyncReadMem|Mem|Queue)\s*\(',r),'router payload storage')
 need(len(re.findall(r'\bReg(?:Init)?\(',r))==2,'router metadata only')
 need('when(ordinaryJob.fire){active:=true.B' in k,'ordinary active origin')
 need('when(io.job.fire){active:=true.B' not in k,'reduction sets ordinary active')
 need('io.port.done.valid:=state===finish && !values.io.deq.valid' in s[P+'MatrixPipeline.scala'],'real Matrix result drain contract')
 return checks

class Ownership:
 """Independent finite-state protocol specification; no Scala/RTL execution."""
 def __init__(self):self.state='idle';self.fault=False;self.debt={k:False for k in ['matrix','read','write','memory','seed']}
 def tick(self,job=None,resident=False,result=False,ready=False,abort=False,backend=False,accept=(),retire=(),malformed=False,stray=False):
  bad=self.fault or abort or backend or malformed or stray
  accept_route=None
  if self.state=='idle' and not bad and not any(self.debt.values()):
   accept_route='resident' if resident else job
  result_fire=self.state!='idle' and result and ready
  before=self.state
  for k in accept:
   if self.debt[k]:raise ValueError('second accepted obligation')
  for k in retire:
   if not self.debt[k]:raise ValueError('unaccepted return')
  for k in accept:self.debt[k]=True
  for k in retire:self.debt[k]=False
  if accept_route:self.state=accept_route
  if result_fire:self.state='idle'
  self.fault|=bad
  return accept_route,result_fire,before

class ColdTests(unittest.TestCase):
 def test_baseline_pins_and_unchanged_source_scope(self):
  pins=json.loads((HERE/'BASELINE_PINS.json').read_text())['composed']
  changed=[]
  for n,h in pins.items():
   b=(ROOT/'baseline'/n).read_bytes();self.assertEqual(hashlib.sha256(b).hexdigest(),h)
   if b!=(ROOT/'source'/n).read_bytes():changed.append(n)
  self.assertEqual(set(changed),{P+n for n in ['QwenOwnerProtocol.scala','HostBlockTop.scala','OverlappedSilu.scala']})
 def test_default_false_projection_matches_baseline(self):
  from default_projection import project,normalized
  for n in ['QwenOwnerProtocol.scala','HostBlockTop.scala','OverlappedSilu.scala']:
   self.assertEqual(project(text(P+n),n),normalized((ROOT/'baseline'/P/n).read_text()),n)
 def test_actual_production_connections(self):audit()
 def test_mandatory_wiring_mutations_rejected(self):
  s={str(p.relative_to(ROOT/'source')):p.read_text() for p in (ROOT/'source').rglob('*') if p.is_file()}
  checks=audit(s)
  for name,(source,fragment) in checks.items():
   key=next(k for k,v in s.items() if v is source)
   altered=dict(s);altered[key]=source.replace(fragment,'/* removed '+name+' */')
   with self.subTest(name=name),self.assertRaises(ValueError):audit(altered)
 def test_arithmetic_and_buffer_sources_byte_identical(self):
  for n in ['Qwen2Block.scala','BlockFloat.scala','VectorSilu.scala','MatrixPipeline.scala','HostBlockCommands.scala']:
   self.assertEqual((ROOT/'source'/P/n).read_bytes(),(ROOT/'baseline'/P/n).read_bytes())
  for n in ['transposed_owner/TransposedDenseOwner.scala','transposed_owner/TransposedDenseBanks.scala','dense_block_reduce/DenseBlockReductionCoordinator.scala','dense_block_reduce/DenseTileSumBridge.scala','ffn_group/FfnResidentCoordinator.scala']:
   p='candidates/qwen2_resident_matrix/'+n
   self.assertEqual((ROOT/'source'/p).read_bytes(),(ROOT/'baseline'/p).read_bytes())
 def test_transaction_route_held_across_stalls(self):
  for route in ['ordinary','reduction','resident']:
   m=Ownership();self.assertEqual(m.tick(job=route)[0],route)
   for i in range(33):
    self.assertEqual(m.tick(job='ordinary',resident=True,result=True,ready=False)[0],None)
    self.assertEqual(m.state,route)
   self.assertTrue(m.tick(result=True,ready=True)[1]);self.assertEqual(m.state,'idle')
 def test_resident_priority_and_no_dual_accept(self):
  m=Ownership();self.assertEqual(m.tick(job='reduction',resident=True)[0],'resident')
 def test_abort_never_clears_debt_or_route(self):
  for kind in ['matrix','read','write','memory','seed']:
   m=Ownership();m.tick(job='reduction');m.tick(accept=[kind]);m.tick(abort=True,result=False,ready=True)
   self.assertTrue(m.debt[kind]);self.assertEqual(m.state,'reduction')
   m.tick(retire=[kind]);self.assertFalse(m.debt[kind]);self.assertTrue(m.fault)
   self.assertIsNone(m.tick(job='ordinary')[0])
 def test_stray_and_malformed_poison_admission(self):
  for arg in ['stray','malformed','backend']:
   m=Ownership();self.assertIsNone(m.tick(job='reduction',**{arg:True})[0]);self.assertTrue(m.fault)
 def test_actual_return_required_for_every_debt(self):
  m=Ownership()
  for k in m.debt:
   with self.assertRaises(ValueError):m.tick(retire=[k])
   m.tick(accept=[k]);self.assertIsNone(m.tick(job='ordinary')[0])
   with self.assertRaises(ValueError):m.tick(accept=[k])
   m.tick(retire=[k])
 def test_held_success_late_fault_retires_as_host_error(self):
  for route in ['ordinary','reduction','resident']:
   for fault in ['abort','backend']:
    m=Ownership();m.tick(job=route)
    held={'tag':17,'status':0,'bytes':4096}
    before=dict(held)
    for _ in range(9):self.assertFalse(m.tick(result=True,ready=False)[1])
    fired=m.tick(result=True,ready=True,**{fault:True})[1]
    self.assertTrue(fired);self.assertEqual(held,before);self.assertTrue(m.fault)
    host_status=3 if m.fault and (route=='resident' or held['status']==0) else held['status']
    self.assertNotEqual(host_status,0);self.assertEqual(m.state,'idle')
    self.assertIsNone(m.tick(job='ordinary')[0])
 def test_terminal_ready_not_masked_by_bad(self):
  r=text(NEW)
  self.assertNotIn('successAllowed',r)
  self.assertIn('val residentReturn=state===residentRun',r)
  self.assertIn('io.ordinaryDone.ready:=state===ordinary && io.done.ready',r)
 def test_counter_capacity_vs_job_m(self):
  for m in [16,128]:
   self.assertLessEqual(m,1024)
  self.assertEqual(2*1024*4,8192)
  self.assertEqual(12*128*129//2*16,1585152)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,default=ROOT,help='replay output containing baseline/ and source/');a,rest=p.parse_known_args();ROOT=a.source_root.resolve();unittest.main(argv=['test_cold.py']+rest,verbosity=2)

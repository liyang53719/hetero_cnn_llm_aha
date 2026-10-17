import tempfile,unittest,subprocess
from pathlib import Path
from . import prepare as P
from .model import Owner,Result
class ControlTests(unittest.TestCase):
 def ready(self):
  o=Owner(True);o.tick();o.tick(group_ready=True)
  for _ in range(8):o.tick(step_ready=True)
  self.assertEqual(o.client.counts['steps'],8);self.assertTrue(o.final_issued);return o
 def commit(self,o,r):
  o.tick(result=r)
  for i in range(16):
   self.assertIs(o.tick(result=r,scalar_ack=True)['selected_held'],r)
  o.tick(result=r,scalar_ack=True);o.tick(result=r)
  self.assertTrue(o.committed);self.assertEqual(o.client.counts['results'],0)
 def test_default_off_never_accepts(self):
  o=Owner()
  for _ in range(20):self.assertFalse(o.tick(group_ready=True,step_ready=True)['client']['start_fire'])
  self.assertEqual(o.client.counts['steps'],0)
 def test_eight_acceptances_then_held_fold_scale_commit(self):
  o=self.ready();r=Result(payload=object());self.commit(o,r)
  self.assertEqual([x for x in o.events if isinstance(x,tuple) and x[0]=='fold'],[('fold',i) for i in range(16)])
  o.tick(result=r);self.assertEqual(o.client.counts['results'],1);self.assertTrue(o.owned)
  for _ in range(5):o.tick();self.assertTrue(o.owned)
  o.tick(done=(1,False));self.assertTrue(o.owned);o.tick();self.assertFalse(o.owned)
  self.assertLess(o.events.index('score-commit'),o.events.index('result-ack'))
  self.assertLess(o.events.index('result-ack'),o.events.index('done-ack'))
 def test_step_stalls_do_not_advance(self):
  o=Owner(True);o.tick();o.tick(group_ready=True)
  for _ in range(9):o.tick(step_ready=False)
  self.assertEqual(o.depth,0);self.assertEqual(o.client.counts['steps'],0)
 def test_selected_fault_never_commits_and_drains(self):
  o=self.ready();r=Result(payload=object());o.tick(result=r,selected_finite=False)
  self.assertTrue(o.poison);self.assertNotIn('score-commit',o.events)
  o.tick(result=r);o.tick(result=r);o.tick(done=(1,True));last=o.tick()
  self.assertTrue(last['owner_done']);self.assertFalse(o.owned)
 def test_abort_while_fold_holds_result(self):
  o=self.ready();r=Result();o.tick(result=r);o.tick(result=r,scalar_ack=True)
  self.assertFalse(o.tick(result=r,fault=True)['owner_done'])
  o.tick(result=r);o.tick(done=(1,True));self.assertTrue(o.tick()['owner_done']);self.assertNotIn('score-commit',o.events)
 def test_foreign_done_keeps_debt(self):
  o=self.ready();r=Result();self.commit(o,r);o.tick(result=r)
  o.tick(done=(99,False));self.assertTrue(o.poison);self.assertTrue(o.owned)
  o.tick(done=(1,True));self.assertTrue(o.tick()['owner_done'])
 def test_done_error_prevents_next_key(self):
  o=self.ready();r=Result();self.commit(o,r);o.tick(result=r);o.tick(done=(1,True));self.assertTrue(o.tick()['owner_done']);self.assertEqual(o.state,'finish')
 def test_abort_before_group_acceptance_has_no_invented_done(self):
  o=Owner(True);o.tick();o.tick(fault=True);self.assertTrue(o.tick()['owner_done']);self.assertEqual(o.client.counts['groups'],0);self.assertEqual(o.client.counts['done'],0)
 def test_unrelated_invalid_legacy_error_does_not_fault(self):
  o=Owner(True);o.tick();o.tick(group_ready=True)
  for _ in range(8):o.tick(step_ready=True,legacy_invalid_error=True)
  self.assertFalse(o.poison)
 def test_same_edge_fault_accepts_and_drains_each_resource(self):
  for kind in ('memory','local','scalar'):
   with self.subTest(kind=kind):
    o=Owner(True);o.tick();o.tick(group_ready=True)
    o.tick(fault=True,accepted=(kind,),memory_tag=9)
    self.assertTrue(o.debts[kind]);o.tick(done=(1,True));o.tick()
    self.assertFalse(o.tick()['owner_done'])
    if kind=='memory':
     o.tick(returned=(kind,),response_tag=8);self.assertTrue(o.debts[kind])
    self.assertFalse(o.tick(returned=(kind,),response_tag=9)['owner_done'])
    self.assertTrue(o.tick()['owner_done']);o.tick(owner_ack=True)
    self.assertEqual(o.state,'locked');self.assertFalse(o.tick()['owner_done'])
 def test_fault_on_score_edge_suppresses_write(self):
  o=self.ready();r=Result();o.tick(result=r)
  for _ in range(17):o.tick(result=r,scalar_ack=True)
  self.assertEqual(o.state,'score');o.tick(result=r,fault=True)
  self.assertNotIn('score-commit',o.events)
 def test_tag_wrap_fails_closed(self):
  o=Owner(True);o.tag=0;self.assertTrue(o.tick()['owner_done']);self.assertTrue(o.poison)
class SourceTests(unittest.TestCase):
 def test_exact_composition_and_reverse_projection(self):
  P.check()
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'tree';P.compose(out)
   core=(out/P.TARGETS[0]).read_text();kernel=(out/P.TARGETS[1]).read_text()
   self.assertIn('io.result.valid:=state===st("finish") && !packedBusy',core)
   self.assertIn('c.io.result.ready:=packedCommitted.get && !poisoned',core)
   self.assertIn('matrixFault:=matrixResult.fire && matrixResult.bits.error',core)
   self.assertIn('&& !packedBusy && !packedFeedDebt',core)
   self.assertIn('packedMemDebt.get && io.response.bits.tag===request.tag',core)
   self.assertIn('state=/=st("locked")',core)
   self.assertIn('matrix.io.port.result.ready:=p.result.ready',kernel)
   self.assertEqual(core.count('SyncReadMem('),(P.ROOT/P.TARGETS[0]).read_text().count('SyncReadMem('))
   subprocess.run(['patch','--batch','--fuzz=0','-R','-p1'],input=(P.HERE/'owner.patch').read_bytes(),cwd=out,check=True,capture_output=True)
   for n in P.TARGETS:self.assertEqual((out/n).read_bytes(),(P.ROOT/n).read_bytes())
 def test_fold_and_scale_arithmetic_statement_unchanged(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'tree';P.compose(out)
   old=(P.ROOT/P.TARGETS[0]).read_text();new=(out/P.TARGETS[0]).read_text()
   for state in ('attReduce','attReduceDone','attExpDiff','attExpResult','attExpSum','attInv','attPVCompute'):
    a=next(x for x in old.splitlines() if x.startswith('  when(state===st("'+state+'")'))
    self.assertIn(a,new)
 def test_source_drift_rejected(self):
  from unittest.mock import patch
  with patch.object(P,'sha',return_value='0'*64):
   with self.assertRaisesRegex(ValueError,'own source drift'):P.check()

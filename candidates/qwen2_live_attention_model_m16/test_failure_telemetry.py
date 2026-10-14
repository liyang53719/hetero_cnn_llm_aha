"""Cold failure receipts work without any work/ artifacts or numeric imports."""
import json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
from . import runner,gates,telemetry
class FailureTelemetry(unittest.TestCase):
 def test_preflight_failure_receipt_without_numeric_imports(self):
  oldtmp=tempfile.tempdir
  with tempfile.TemporaryDirectory() as temporary:
   out=Path(temporary)/'new';data=Path(temporary)/'absent_input';ref=Path(temporary)/'absent_reference'
   try:
    p=dict(gates.pins(),actual_execution_authorized=True)
    with (patch.object(gates,'OUTPUT_ROOT',Path(temporary)),patch.object(gates,'require_final_reference',return_value=p),
          patch.object(gates,'pins',return_value=p),patch.object(gates,'data_path',return_value=data),
          patch.object(gates,'reference_path',return_value=ref),
          patch.object(runner,'dependencies',side_effect=ValueError('public FFN host budget exceeded'))):
     with self.assertRaisesRegex(RuntimeError,'M16 preflight: public Host software deadline exceeded') as raised:runner.run(str(out),'cold_mock_data','cold_mock_reference')
    self.assertIsInstance(raised.exception.__cause__,ValueError)
    self.assertEqual(str(raised.exception.__cause__),'public FFN host budget exceeded')
    r=json.loads((out/'RESULT.json').read_text())
    self.assertEqual(r['failure_stage'],'preflight');self.assertEqual(r['failure_kind'],'BUDGET_EXCEEDED')
    self.assertEqual(r['original_error_message'],'public FFN host budget exceeded')
    self.assertEqual(r['stage_error'],'M16 preflight: public Host software deadline exceeded')
    self.assertFalse(r['oracle_opened']);self.assertEqual(r['oracle_reference_reads'],[]);self.assertGreater(r['peak_rss_kib'],0)
    self.assertNotIn('failed_attention_owner',r);self.assertFalse(data.exists() or ref.exists())
   finally:tempfile.tempdir=oldtmp
 def test_attention_failure_serializes_exact_fake_state_without_arithmetic(self):
  attention=S(state='matrix_wait',memory_pending=True,abort_pending=False,matrix_client=object(),matrix_request=object(),
      report=lambda:{'functional_state_ticks':{'owner:matrix_wait':7},'accepted':{'matrix_requests':3}})
  shared=S(client=attention,calls={'bf':32})
  matrix=S(owner=attention,lib=S(matrix_state=lambda:1),report=lambda:{'normal_fma_calls':1536})
  dense=S(pending=None,fifo=[],read_active=None,a_hold=None,a_rmw_pending=None,accepted_write=None,
      tiles=S(leased=False,idle=True),lease=None)
  physical=S(pending={'write':True},report=lambda:{'accepted':{'write_ack_bytes':64}})
  x=S(owner=dense,matrix_service=matrix,attention_owner=attention,prefix_owner=S(state='idle',scalar=shared),
      reduction=None,reset_required=lambda:False,report=lambda:{'accepted':{'owner_result_fire':0}})
  gate=S(opened=False,reference_reads=[],blocked=2)
  error=ValueError('public FFN host budget exceeded')
  r=telemetry.attach_failure({},error,stage='attention',started=time.monotonic(),cpu=time.process_time(),gate=gate,physical=physical,x=x,service=matrix,shared=shared)
  decoded=json.loads(json.dumps(r,allow_nan=False))
  self.assertEqual(decoded['failed_attention_owner']['functional_state_ticks'],{'owner:matrix_wait':7})
  self.assertEqual(decoded['failed_attention_owner']['exact_state'],'matrix_wait')
  self.assertTrue(decoded['failed_attention_owner']['matrix_client_live'])
  for key in ('matrix_owned','scalar_owned','dma_pending','attention_not_idle','attention_memory_pending','attention_client_live','attention_matrix_request'):
   self.assertTrue(decoded['failed_backend_debts'][key],key)
  self.assertEqual(decoded['failed_backend_debts']['matrix_c_state'],1)
  self.assertEqual(decoded['failed_scalar_calls'],{'bf':32});self.assertTrue(decoded['failed_scalar_owned'])
  self.assertEqual(decoded['failed_matrix']['normal_fma_calls'],1536)
  self.assertFalse(decoded['oracle_opened']);self.assertEqual(decoded['oracle_reference_reads'],[]);self.assertEqual(decoded['oracle_blocked_reads'],2)
  self.assertEqual(decoded['stage_error'],'M16 attention: public Host software deadline exceeded')
  try:raise telemetry.contextual_error('attention',error) from error
  except RuntimeError as wrapped:self.assertIs(wrapped.__cause__,error)
 def test_unrelated_error_keeps_original_object(self):
  error=ValueError('shape mismatch');self.assertIs(telemetry.contextual_error('attention',error),error)
if __name__=='__main__':unittest.main()

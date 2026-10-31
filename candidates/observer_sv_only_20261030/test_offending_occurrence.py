"""Synthetic diagnostic position checks only; no hardware or projection acceptance."""
import unittest,copy,json
import instance_port_labels as helper
import sv_difference_projection as p
from test_projection import fixture
class OffendingOccurrence(unittest.TestCase):
 def test_reports_actual_old_dense_key_not_eof(self):
  self.check(p.MODULES[1],False,b'io_tiles_response_bits_key_slot')
 def test_skips_removed_new_ports_and_reports_remaining_signal(self):
  self.check(p.MODULES[0],True,b'io_tiles_response_bits_key_identity')
 def check(self,module,new,key):
  marker=b'assign existing = '+key+b';'
  data=fixture(module,new,change=(marker+b'\n\n\n// trailing ordinary bytes\n\n').decode())
  location=data.index(marker)+len(b'assign existing = ')
  p.reset_diagnostic()
  try:p.projected_hash(data,module,new)
  except p.ProjectionRejected as error:report=p.failure_record(error)
  else:self.fail('remaining key must still be rejected')
  self.assertEqual(report['reason_code'],p.REJECTION_CODES['new key remains in unprojected logic/port'])
  self.assertEqual(report['progress']['lexical_byte_offset'],location)
  self.assertEqual(report['progress']['line_number'],data.count(b'\n',0,location)+1)
  self.assertLess(report['progress']['line_number'],data.count(b'\n'))
  self.assertEqual(report['offending_token_category'],'UNEXEMPTED_KEY_IDENTIFIER')
  self.assertEqual(report['phase'],'PROJECT_MODULE')
  self.assertEqual(report['module'],module)
  self.assertEqual(report['saturated_fields'],[])
class ClassifierDiagnostics(unittest.TestCase):
 def setup_context(self):
  p.reset_diagnostic();p.diagnostic_context('PROJECT_MODULE',p.MODULES[1],'old')
 def test_all_finite_branches_roundtrip_without_arbitrary_text(self):
  self.assertEqual(set(p.CLASSIFIER_REASONS),set(helper.REASONS))
  for reason in helper.REASONS:
   self.setup_context();p.diagnostic_classifier(reason,{k:0 for k in p.CLASSIFIER_COUNT_CAPS});r=p.failure_record(ValueError('SECRET_PATH'))
   self.assertEqual(r['classifier']['reason_code'],reason);self.assertNotIn('SECRET',json.dumps(r));self.assertIsNone(r['offending_token_category'])
 def test_first_overflow_and_larger_saturation(self):
  self.setup_context();counts={k:cap for k,cap in p.CLASSIFIER_COUNT_CAPS.items()};p.diagnostic_classifier('PORT_CAP',counts);r=p.failure_record(ValueError('not exported'));self.assertEqual(r['classifier']['counts'],counts);self.assertEqual(r['classifier']['saturated_fields'],[])
  p.diagnostic_classifier('PORT_CAP',{k:cap+100 for k,cap in p.CLASSIFIER_COUNT_CAPS.items()});r=p.failure_record(ValueError('not exported'));self.assertEqual(r['classifier']['counts'],counts);self.assertEqual(r['classifier']['saturated_fields'],sorted(counts))
 def test_invalid_callback_does_not_throw_or_leak(self):
  for reason,counts in [('SECRET',{k:0 for k in p.CLASSIFIER_COUNT_CAPS}),('EXACT_FOUR_LABELS',{'SECRET_PATH':'payload'}),('PORT_CAP',{k:True for k in p.CLASSIFIER_COUNT_CAPS})]:
   self.setup_context();p.diagnostic_classifier(reason,counts);r=p.failure_record(ValueError('not exported'));self.assertEqual(r['classifier']['reason_code'],'INVALID_CLASSIFIER_DIAGNOSTIC');self.assertTrue(all(v is None for v in r['classifier']['counts'].values()));self.assertNotIn('SECRET',json.dumps(r))
 def test_unknown_schema_payload_and_unbound_category_rejected(self):
  self.setup_context();p.diagnostic_classifier('OTHER_MODULE',{k:0 for k in p.CLASSIFIER_COUNT_CAPS});r=p.failure_record(ValueError('not exported'))
  for key,value in [('reason_code','SECRET'),('source_sha256','0'*64),('kind','private')]:
   bad=copy.deepcopy(r);bad['classifier'][key]=value
   with self.assertRaises(ValueError):p.project_failure(bad)
  bad=copy.deepcopy(r);bad['classifier']['counts']['payload']='SECRET'
  with self.assertRaises(ValueError):p.project_failure(bad)
  bad=copy.deepcopy(r);bad['offending_token_category']='UNEXEMPTED_KEY_IDENTIFIER'
  with self.assertRaises(ValueError):p.project_failure(bad)
if __name__=='__main__':unittest.main()

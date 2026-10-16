"""Cold negative tests for observed exit and exact preparation provenance."""
import copy,tempfile,unittest
from pathlib import Path
from . import preparation_receipts as p
class ReceiptTests(unittest.TestCase):
 def fixture(self):
  pins=p.provenance()
  supervisor=dict(status='OBSERVED_ZERO_REFERENCE_LAUNCHER_EXIT',observation='tool_terminal_result',
   outer_exit_code=0,child_exit_code=0,cleanup_complete=True,numerical_acceptance=False,ready_for_actual=False,
   summary_sha256=pins['preparation_summary_sha256'],launch_receipt_sha256=pins['launch_receipt_sha256'],
   reference_receipt_sha256=pins['references_sha256'],contract_sha256=pins['preparation_contract_sha256'])
  summary=dict(status='COMPLETE_REFERENCE_PREPARATION_ONLY',phase='complete',child_exit_code=0,
   cleanup_complete=True,numerical_acceptance=False,ready_for_actual=False,
   launch_receipt_sha256=pins['launch_receipt_sha256'],receipt_sha256=pins['references_sha256'],
   contract_sha256=pins['preparation_contract_sha256'])
  launch=dict(status='VALIDATED_REFERENCE_CHILD_EXIT_ONLY',caller_must_observe_launcher_exit=True,
   child=dict(returncode=0,cleanup_complete=True),numerical_acceptance=False,ready_for_actual=False,
   references=dict(sha256=pins['references_sha256']),contract_sha256=pins['preparation_contract_sha256'])
  return supervisor,summary,launch,pins
 def test_exact_successful_control_chain(self):p.validate_terminal(*self.fixture())
 def test_no_inferred_outer_exit(self):
  for value in (False,0.0,1,None):
   args=self.fixture();args[0]['outer_exit_code']=value
   with self.assertRaises(ValueError):p.validate_terminal(*args)
 def test_no_inferred_child_exit(self):
  for index in (0,1,2):
   for value in (False,0.0,1,None):
    args=self.fixture()
    if index==2:args[2]['child']['returncode']=value
    else:args[index]['child_exit_code']=value
    with self.assertRaises(ValueError):p.validate_terminal(*args)
 def test_cleanup_and_acceptance_canonical(self):
  for index in (0,1,2):
   for key,value in (('numerical_acceptance',0),('ready_for_actual',0),('status','PASS')):
    args=self.fixture();args[index][key]=value
    with self.assertRaises(ValueError):p.validate_terminal(*args)
  args=self.fixture();args[2]['child']['cleanup_complete']=1
  with self.assertRaises(ValueError):p.validate_terminal(*args)
 def test_receipt_link_drift(self):
  for index,key in ((0,'summary_sha256'),(0,'reference_receipt_sha256'),(1,'receipt_sha256'),(2,'contract_sha256')):
   args=self.fixture();args[index][key]='0'*64
   with self.assertRaises(ValueError):p.validate_terminal(*args)
 def test_pointer_same_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'receipt.json';raw=p.R.encoded({'status':'control-only'});path.write_bytes(raw)
   pointer=dict(path=str(path),sha256=p.R.sha(raw))
   self.assertEqual(p.read_pointer(pointer,pointer['sha256'])[1],{'status':'control-only'})
   path.write_bytes(p.R.encoded({'status':'changed'}))
   with self.assertRaises(ValueError):p.read_pointer(pointer,pointer['sha256'])
 def test_pointer_symlink_and_foreign_digest(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'receipt.json';path.write_bytes(b'{}');link=Path(d)/'link';link.symlink_to(path)
   with self.assertRaises(ValueError):p.read_pointer(dict(path=str(link),sha256=p.R.sha(b'{}')),p.R.sha(b'{}'))
   with self.assertRaises(ValueError):p.read_pointer(dict(path=str(path),sha256='0'*64),p.R.sha(b'{}'))
if __name__=='__main__':unittest.main()

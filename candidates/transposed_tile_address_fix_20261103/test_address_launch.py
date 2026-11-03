"""Dormant new-hardware launch qualification; never starts a workflow."""
import importlib.util,pathlib,unittest
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('address_launch',D/'validate_address_launch.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class AddressLaunch(unittest.TestCase):
 def fixture(self):
  source='1'*40;head='2'*40
  return dict(event={'ref':'refs/heads/main','before':source,'after':head},manifest={'schema':g.SCHEMA,'source_sha':source,'nonce':g.NONCE,'transfer_approval_sha256':g.ACCEPTED_TRANSFER_APPROVAL_SHA256},attempt='1',head=head,parent=source,diff='A\t'+g.LAUNCH+'\n')
 def test_exact_source_child(self):
  self.assertEqual(g.validate(**self.fixture()),'1'*40);g.require_transfer_approval()
 def test_old_nonce_rejected(self):
  x=self.fixture();x['manifest']['nonce']='five_m128_model_candidate_terminal_finite_20261102_once'
  with self.assertRaises(ValueError):g.validate(**x)
 def test_no_retry_or_extra_changes(self):
  for field,value in [('attempt','2'),('diff','M\t'+g.LAUNCH+'\n'),('diff','A\t'+g.LAUNCH+'\nM\tx\n'),('parent','3'*40)]:
   x=self.fixture();x[field]=value
   with self.assertRaises(ValueError):g.validate(**x)
 def test_actual_dormant_workflow(self):
  r=D.parents[1];s=(r/'.github/workflows/hetero-five-m128-tile-address-build.yml').read_text()
  self.assertIn('paths: ['+g.LAUNCH+']',s);self.assertEqual(s.count('--hardware-source transposed-tile-address-v1'),1)
  self.assertNotIn('--terminal-finite-readonly',s);self.assertNotIn('--first-fault-readonly',s)
  self.assertIn('group: hetero-exclusive-numeric-bootstrap',s);self.assertIn('cancel-in-progress: false',s)
  self.assertEqual(g.NONCE,'five_m128_model_tile_address_20261103_once')
if __name__=='__main__':unittest.main()

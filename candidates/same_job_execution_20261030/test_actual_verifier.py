"""Synthetic receipts with unmocked production verifier; never real DUT evidence."""
import importlib.util,json,os,pathlib,sys,tempfile,unittest
D=pathlib.Path(__file__).parent
BASE=pathlib.Path(os.environ.get('PROGRESS_TEST_BASE',str(D)))
sys.path.insert(0,str(BASE/'acceptance_tests'));sys.path.insert(0,str(D))
from test_safe_summary_join import Tests as Fixture,ID
import summary_progress as p
from test_progress import line
class Tests(unittest.TestCase):
 def test_unmocked_verifier_allfive_and_cleanup_rejection(self):
  with tempfile.TemporaryDirectory() as t:
   work=pathlib.Path(t);root=Fixture().setup_fixture(work)
   (work/'FLOW_RESULT.json').unlink() # Progress must survive incomplete global flow.
   for i in range(5):
    (root/f'profile{i}/material/dut_result/profile{i}.log').write_bytes(line(0,'reset')+line(1048576))
    op=root/f'runs/p{i}_dut/RESULT.json';r=json.loads(op.read_text());r['elapsed_seconds']=301;op.write_text(json.dumps(r))
   r=p.project(work,ID,BASE/'numeric');self.assertEqual([x['status'] for x in r['profiles']],['OBSERVED_PARTIAL_NOT_NUMERICAL_PASS']*5);self.assertFalse(r['numerical_pass']);self.assertNotIn(t,json.dumps(r))
   op=root/'runs/p2_dut/RESULT.json';v=json.loads(op.read_text());v['log_capture']['pipe_eof_observed']=False;op.write_text(json.dumps(v))
   r=p.project(work,ID,BASE/'numeric');self.assertEqual(r['profiles'][2]['status'],'UNAVAILABLE');self.assertIsNone(r['profiles'][2]['last'])
if __name__=='__main__':unittest.main()

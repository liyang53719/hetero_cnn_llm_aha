#!/usr/bin/env python3
"""Rejection must never rewrite an earlier PASS/FAIL proof directory."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,unittest
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'scripts'))
import recheck_published_owner_regression as audit
ROOT=Path(os.environ['OWNER_TEST_ARTIFACTS']) if 'OWNER_TEST_ARTIFACTS' in os.environ else Path(tempfile.mkdtemp(prefix='owner_output_preservation_'))
ROOT.mkdir(parents=True,exist_ok=True)
def fingerprint(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
class PreservationTests(unittest.TestCase):
    def case(self,script,gate,optimized=False,extra=()):
        case=Path(tempfile.mkdtemp(dir=ROOT));out=case/'old';out.mkdir()
        (out/'gate.exit').write_text(gate+'\n');(out/'run.log').write_bytes(b'IMMUTABLE OLD EXECUTION\n')
        before=fingerprint(out)
        command=[sys.executable]+(['-O'] if optimized else [])+[str(P/'scripts'/script),'--repo',str(case/'no_repo'),'--build',str(case/'no_build'),'--output',str(out),*extra]
        result=subprocess.run(command,capture_output=True,text=True)
        (case/'probe.stdout').write_text(result.stdout);(case/'probe.stderr').write_text(result.stderr)
        self.assertNotEqual(result.returncode,0);self.assertEqual(fingerprint(out),before)
    def test_lifecycle_old_pass(self):self.case('run_owner_lifecycle_gate.py','0')
    def test_lifecycle_old_fail(self):self.case('run_owner_lifecycle_gate.py','1')
    def test_lifecycle_invalid_seed(self):self.case('run_owner_lifecycle_gate.py','0',extra=('--seed','0'))
    def test_lifecycle_optimized(self):self.case('run_owner_lifecycle_gate.py','0',True)
    def test_replay_old_pass(self):self.case('run_owner_replay_gate.py','0')
    def test_replay_old_fail(self):self.case('run_owner_replay_gate.py','1')
    def test_replay_optimized(self):self.case('run_owner_replay_gate.py','0',True)
    def test_no_receipt_created_on_bad_inputs(self):
        case=Path(tempfile.mkdtemp(dir=ROOT));out=case/'new'
        c=subprocess.run([sys.executable,str(P/'scripts/run_owner_replay_gate.py'),'--repo',str(case/'no_repo'),'--build',str(case/'no_build'),'--output',str(out)],capture_output=True)
        self.assertNotEqual(c.returncode,0);self.assertFalse((out/'gate.exit').exists())
    def test_exact_reversible_cli_provenance(self):
        repo=P.parents[1];rel='chisel/continuous_prefill/scripts/run_owner_replay_gate.py'
        current=(repo/rel).read_text();marker="        # Existing evidence is never changed on rejection; caller records exit status.\n"
        original="        if a.output.exists():(a.output/'gate.exit').write_text('1\\n')\n"
        expected=hashlib.sha256(current.replace(marker,original).encode()).hexdigest();changes={}
        audit.source_compatibility(repo,rel,expected,changes);self.assertIn(rel,changes)
    def test_unapproved_source_digest_rejected(self):
        repo=P.parents[1];rel='chisel/continuous_prefill/scripts/run_owner_replay_gate.py'
        with self.assertRaises(ValueError):audit.source_compatibility(repo,rel,'0'*64,{})
if __name__=='__main__':unittest.main()

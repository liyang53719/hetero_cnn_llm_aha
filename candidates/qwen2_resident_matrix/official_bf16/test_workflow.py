"""The new tee-backed test steps must propagate the producer exit status."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[3]


class WorkflowGuards(unittest.TestCase):
    def test_both_tee_test_steps_select_explicit_bash(self):
        for file,label in [('qwen2-prefill-model-contract.yml','Check model contracts and scalar software recipe without RTL'),
                           ('qwen2-matrix-interface-frontend.yml','Independent control contracts and negative identity guards')]:
            source=(ROOT/'.github/workflows'/file).read_text()
            step=source.split('      - name: '+label+'\n')[1].split('\n      - ')[0]
            self.assertIn('        shell: bash\n',step)
            self.assertIn('official_bf16.test_',step)
            self.assertIn(' | tee ',step)

    def test_explicit_actions_bash_propagates_failed_tests_through_tee(self):
        for code in (0,1,7):
            r=subprocess.run(['bash','--noprofile','--norc','-eo','pipefail','-c',f'(exit {code}) | tee /dev/null'],capture_output=True)
            self.assertEqual(r.returncode,code)


if __name__=='__main__':unittest.main()

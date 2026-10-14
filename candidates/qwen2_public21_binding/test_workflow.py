"""Exact dependency coverage and bounded dedicated control-only CI wiring."""
from pathlib import Path
import re
import unittest
import compose as c

ROOT=Path(__file__).resolve().parents[2]
WORKFLOW='.github/workflows/qwen2-public21-binding-control.yml'

class DedicatedWorkflow(unittest.TestCase):
    def test_all_consumed_paths_trigger_the_dedicated_gate(self):
        m,o,a,e=c.load_inputs()
        expected={name for _,pins in c.repo_inputs(m,o,e) for name in pins}
        expected.update(['candidates/qwen2_public21_binding/**',WORKFLOW,'scripts/setup_hetero_chisel_loan_toolchain.sh'])
        text=(ROOT/WORKFLOW).read_text()
        actual=re.findall(r"^      - '([^']+)'$",text,re.M)
        self.assertEqual(len(actual),len(set(actual)))
        self.assertEqual(set(actual),expected)
        self.assertFalse(any(path.startswith('!') for path in actual))

    def test_fixed_fetch_cold_modes_and_fresh_rtl_are_ordered(self):
        text=(ROOT/WORKFLOW).read_text()
        commands=[
          'git fetch --no-tags --depth=1 origin '+c.BASE_COMMIT,
          'git fetch --no-tags --depth=1 origin 36dd2c473815a931e1f74463e9d43e538c11f2f6',
          "python -m pip install --index-url https://pypi.org/simple 'numpy==2.3.5' 'PyYAML==6.0.3'",
          "python -m unittest discover -s candidates/qwen2_public21_binding -p 'test_*.py' -v",
          "python -O -m unittest discover -s candidates/qwen2_public21_binding -p 'test_*.py' -v",
          'python -S candidates/qwen2_public21_binding/run_control.py',
          'run: bash scripts/setup_hetero_chisel_loan_toolchain.sh',
          'python candidates/qwen2_public21_binding/run_control.py --run-rtl --out "$PWD/work/public21-binding-control" --toolchain-root "$PWD/work/chisel_toolchain" --hardfloat-source "$HARDFLOAT_SOURCE"',
        ]
        for command in commands:self.assertEqual(text.count(command),1)
        self.assertEqual([text.index(x) for x in commands],sorted(text.index(x) for x in commands))
        for literal in ['timeout-minutes: 25','cancel-in-progress: false','if: always()',"with: {ref: '${{ github.sha }}'}"]:
            self.assertIn(literal,text)
        self.assertNotIn('continue-on-error',text)
        self.assertNotIn('workflow_dispatch:',text.split('jobs:',1)[1])

    def test_upload_excludes_fixtures_binary_build_and_payloads(self):
        text=(ROOT/WORKFLOW).read_text();paths=text.split('          path: |\n',1)[1].splitlines()
        paths={line.strip() for line in paths if line.strip()}
        self.assertEqual(paths,{'work/public21-binding-cold/*.log','work/public21-binding-cold/default.json',
          'work/public21-binding-control/summary.json','work/public21-binding-control/fixture_generation.log',
          'work/public21-binding-control/test.log','work/public21-binding-control/sources/source_receipt.json',
          'work/public21-binding-control/rtl/','work/chisel_toolchain/logs/'})

if __name__=='__main__':unittest.main()

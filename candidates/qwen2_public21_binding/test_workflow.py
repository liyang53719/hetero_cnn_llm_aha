"""Exact dependency coverage and bounded dedicated control-only CI wiring."""
from pathlib import Path
import json
import re
import unittest
import compose as c

ROOT=Path(__file__).resolve().parents[2]
WORKFLOW='.github/workflows/qwen2-public21-binding-control.yml'
MAVEN_LOCK='chisel/rope_hardware_oracle/maven-lock.json'
BRIDGE='org/scala-lang/scala2-sbt-bridge/2.13.16/scala2-sbt-bridge-2.13.16'
PREFETCH='      - name: Prefetch fixed Scala compiler bridge before offline snapshot\n'

class DedicatedWorkflow(unittest.TestCase):
    def test_all_consumed_paths_trigger_the_dedicated_gate(self):
        m,o,a,e=c.load_inputs()
        expected={name for _,pins in c.repo_inputs(m,o,e) for name in pins}
        expected.update(['candidates/qwen2_public21_binding/**',WORKFLOW,MAVEN_LOCK,'scripts/setup_hetero_chisel_loan_toolchain.sh'])
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
          'cd "$CHISEL_TOOLCHAIN/bootstrap_project"',
          'sbt \'show scalaCompilerBridgeBinaryJar\' 2>&1 | tee "$CHISEL_TOOLCHAIN/logs/scala_compiler_bridge.log"',
          'python candidates/qwen2_public21_binding/run_control.py --run-rtl --out "$PWD/work/public21-binding-control" --toolchain-root "$PWD/work/chisel_toolchain" --hardfloat-source "$HARDFLOAT_SOURCE"',
        ]
        for command in commands:self.assertEqual(text.count(command),1)
        self.assertEqual([text.index(x) for x in commands],sorted(text.index(x) for x in commands))
        for literal in ['timeout-minutes: 25','cancel-in-progress: false','if: always()',"with: {ref: '${{ github.sha }}'}"]:
            self.assertIn(literal,text)
        self.assertNotIn('continue-on-error',text)
        self.assertNotIn('workflow_dispatch:',text.split('jobs:',1)[1])

    def check_bridge_preparation(self,workflow):
        self.assertEqual(workflow.count(PREFETCH),1)
        preparation=workflow.split(PREFETCH,1)[1].split('      - name:',1)[0]
        resolve="sbt 'show scalaCompilerBridgeBinaryJar'"
        self.assertIn(resolve,preparation)
        self.assertIn('set -euo pipefail',preparation)
        self.assertIn('source work/chisel_toolchain/env.sh',preparation)
        self.assertIn('cd "$CHISEL_TOOLCHAIN/bootstrap_project"',preparation)
        self.assertIn('bridge="$COURSIER_CACHE/https/repo.maven.apache.org/maven2/'+BRIDGE+'"',preparation)
        check=re.search(r"printf '([0-9a-f]{64})  %s.jar\\n([0-9a-f]{64})  %s.pom\\n' "
                        r'"\$bridge" "\$bridge" \| sha256sum --check \| tee -a "\$CHISEL_TOOLCHAIN/logs/scala_compiler_bridge.log"',preparation)
        self.assertIsNotNone(check)
        lock=json.loads((ROOT/MAVEN_LOCK).read_text())['artifacts']
        self.assertEqual(check.group(1),lock[BRIDGE+'.jar'])
        self.assertEqual(check.group(2),lock[BRIDGE+'.pom'])
        self.assertLess(preparation.index(resolve),check.start())
        self.assertLess(workflow.index(PREFETCH),workflow.index('python candidates/qwen2_public21_binding/run_control.py --run-rtl '))
        self.assertNotIn('compile',preparation.replace('scalaCompilerBridgeBinaryJar','').replace('scala_compiler_bridge.log',''))
        self.assertNotIn('testOnly',preparation)

    def test_bridge_preparation_keeps_fixed_version_and_offline_execution(self):
        setup=(ROOT/'scripts/setup_hetero_chisel_loan_toolchain.sh').read_text()
        runner=(ROOT/'candidates/qwen2_public21_binding/run_control.py').read_text()
        for text in (setup,runner):
            self.assertIn('ThisBuild / scalaVersion := "2.13.16"',text)
        self.assertIn('ThisBuild / offline := true',runner)
        self.assertIn("COURSIER_MODE='offline'",runner)
        self.check_bridge_preparation((ROOT/WORKFLOW).read_text())

    def test_missing_tampered_or_late_bridge_checks_rejected(self):
        workflow=(ROOT/WORKFLOW).read_text()
        lock=json.loads((ROOT/MAVEN_LOCK).read_text())['artifacts']
        start=workflow.index(PREFETCH)
        end=workflow.index('      - name:',start+len(PREFETCH))
        preparation=workflow[start:end]
        late=workflow.replace(preparation,'').replace('      - name: Preserve bounded control evidence',
            preparation+'      - name: Preserve bounded control evidence')
        mutations=[workflow.replace(preparation,''),late,workflow.replace('sha256sum --check','cat')]
        for suffix in ('.jar','.pom'):
            digest=lock[BRIDGE+suffix]
            mutations.extend([workflow.replace(digest,''),workflow.replace(digest,'0'*64)])
        for index,changed in enumerate(mutations):
            with self.subTest(mutation=index),self.assertRaises(AssertionError):
                self.check_bridge_preparation(changed)

    def test_upload_excludes_fixtures_binary_build_and_payloads(self):
        text=(ROOT/WORKFLOW).read_text();paths=text.split('          path: |\n',1)[1].splitlines()
        paths={line.strip() for line in paths if line.strip()}
        self.assertEqual(paths,{'work/public21-binding-cold/*.log','work/public21-binding-cold/default.json',
          'work/public21-binding-control/summary.json','work/public21-binding-control/fixture_generation.log',
          'work/public21-binding-control/test.log','work/public21-binding-control/sources/source_receipt.json',
          'work/public21-binding-control/rtl/','work/chisel_toolchain/logs/'})

if __name__=='__main__':unittest.main()

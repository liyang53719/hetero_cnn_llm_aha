"""Parse the real launch workflow; no qualification process or arithmetic imports.

The generic frontend already installs PyYAML and discovers this top-level test.
The isolated qualification job keeps its original NumPy-only environment.
"""
import hashlib
import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/portable-consumer-qualification-launch-r1.yml'
CONTRACT = 'candidates/qwen2_resident_matrix/portable_consumer_qualification/input-contract.json'
OLD_WORKFLOW_SHA = '6ca2109c52fc9e8c8cdba920b6c66ec43afeeb9786f62902a509eb6d6f80265b'
OLD_CONTRACT_SHA = '91c6a1ab6a793a5a46e9ae7def7654aa95ee2eef0b8f210c0f299ea5654774b8'
COMMAND = "timeout --signal=TERM --kill-after=5s 50s python -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: --retries 0 --timeout 20 --index-url https://pypi.org/simple 'numpy==2.3.5'"


class PortableWorkflowYamlTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / WORKFLOW).read_bytes()
        # BaseLoader retains the Actions key 'on' as text instead of applying
        # YAML 1.1 boolean conversion. It still performs actual YAML parsing.
        self.workflow = yaml.load(self.raw, Loader=yaml.BaseLoader)

    def test_real_full_workflow_parses_and_command_is_identical(self):
        job = self.workflow['jobs']['fixed-cases']
        install = next(s for s in job['steps'] if s.get('name') == 'Install bounded NumPy dependency')
        self.assertEqual(install['run'], COMMAND + '\n')
        root_node = yaml.compose(self.raw, Loader=yaml.BaseLoader)
        self.assertIsInstance(root_node, yaml.MappingNode)
        # A literal scalar protects embedded colon-space shell tokens.
        expected = ('        run: |\n          ' + COMMAND + '\n').encode()
        self.assertEqual(self.raw.count(expected), 1)

    def test_exact_published_pre_job_failure_is_reproduced(self):
        fixed = ('        run: |\n          ' + COMMAND).encode()
        original = self.raw.replace(fixed, ('        run: ' + COMMAND).encode())
        self.assertEqual(hashlib.sha256(original).hexdigest(), OLD_WORKFLOW_SHA)
        with self.assertRaises(yaml.scanner.ScannerError) as caught:
            yaml.load(original, Loader=yaml.BaseLoader)
        self.assertEqual(caught.exception.problem_mark.line + 1, 36)
        self.assertEqual(caught.exception.problem_mark.column + 1, 139)

    def test_contract_changes_only_the_workflow_digest(self):
        path = ROOT / CONTRACT
        contract = json.loads(path.read_bytes())
        self.assertEqual(contract['payload_sha256'][WORKFLOW], hashlib.sha256(self.raw).hexdigest())
        contract['payload_sha256'][WORKFLOW] = OLD_WORKFLOW_SHA
        original = (json.dumps(contract, indent=2, sort_keys=True) + '\n').encode()
        self.assertEqual(hashlib.sha256(original).hexdigest(), OLD_CONTRACT_SHA)

    def test_actual_trigger_job_and_artifact_guards_parse(self):
        job = self.workflow['jobs']['fixed-cases']
        self.assertEqual(self.workflow['on'], {'push': {'branches': ['main'], 'paths': [WORKFLOW]}})
        self.assertEqual(job['if'], "github.event_name == 'push' && github.run_attempt == 1")
        self.assertEqual(job['timeout-minutes'], '10')
        self.assertEqual(len(job['steps']), 6)
        self.assertTrue(all(isinstance(s['run'], str) for s in job['steps'] if 'run' in s))
        artifact = job['steps'][-1]
        self.assertEqual(artifact['if'], 'always() && github.run_attempt == 1')
        self.assertEqual(artifact['with']['path'].splitlines(), [
            '${{ runner.temp }}/portable-consumer-qualification-r1/evidence/' + name
            for name in ('summary.json', 'identities.json', 'source_hashes.json')])


if __name__ == '__main__':
    unittest.main()

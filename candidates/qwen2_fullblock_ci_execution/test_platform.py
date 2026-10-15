"""Cold contract and mocked initialization tests. Never loads native packages."""
from contextlib import ExitStack
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from candidates.qwen2_fullblock_ci_execution import platform as P
from candidates.qwen2_fullblock_ci_prepare import initialize_platform as published


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = P.sources(P.ROOT)

    def setup_live(self, stack, summaries=None):
        executable = P.PYTHON_HOME / 'bin/python3.12'
        stack.enter_context(patch.object(P, 'location', return_value=executable))
        stack.enter_context(patch.object(P, 'sources', return_value=copy.deepcopy(self.pins)))
        stack.enter_context(patch.object(published, 'ROOT', P.CI_ROOT))
        stack.enter_context(patch.object(published, '__file__', str(P.CI_ROOT / 'candidates/qwen2_fullblock_ci_prepare/initialize_platform.py')))
        stack.enter_context(patch.object(published.inventory, '__file__', str(P.CI_ROOT / 'candidates/qwen2_fullblock_ci_prepare/platform_inventory.py')))
        identity = stack.enter_context(patch.object(published.inventory, 'identity', return_value=copy.deepcopy(P.PYTHON_IDENTITY)))
        probe = stack.enter_context(patch.object(published, 'initialize', side_effect=summaries if summaries is not None else [P._expected(self.pins)]))
        return identity, probe

    def test_default_and_cli_are_no_io(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('read')), \
             patch.object(Path, 'resolve', side_effect=AssertionError('resolve')), \
             patch.object(published, 'initialize', side_effect=AssertionError('native init')):
            self.assertEqual(P.initialize(), {'status':'NOT_EXECUTED','numeric_execution_allowed':False})
            with patch('sys.stdout', new_callable=io.StringIO) as output:
                P.main([])
            self.assertEqual(json.loads(output.getvalue())['status'], 'NOT_EXECUTED')
            for execute in (1, 'yes', None):
                with self.assertRaises(ValueError): P.initialize(execute=execute)

    def test_real_source_pins_and_only_python_identity_delta(self):
        result = P._expected(self.pins)
        self.assertEqual(result['runtime'], self.pins['runtime_requirements'])
        for name, actual in result['native_files'].items():
            expected = P.PYTHON_IDENTITY if name == 'python' else {
                k:self.pins['runtime_native_files'][name][k] for k in ('bytes','sha256')}
            self.assertEqual(actual, expected)
            self.assertEqual(set(actual), {'bytes','sha256'})

    def test_fresh_success_calls_initializer_not_old_summary(self):
        fresh = P._expected(self.pins)
        with ExitStack() as stack:
            identity, probe = self.setup_live(stack, [fresh])
            result = P.initialize(P.CI_ROOT, execute=True)
            probe.assert_called_once_with()
            self.assertEqual(identity.call_count, 2)
            self.assertEqual(result, fresh)
            self.assertIsNot(result, fresh)
            self.assertFalse(result['numeric_execution_allowed'])
            self.assertNotIn('/home/', json.dumps(result))
            self.assertNotIn('/opt/', json.dumps(result))

    def test_old_summary_cannot_be_passed_or_used_as_cached_success(self):
        with self.assertRaises(TypeError): P.initialize(summary=P._expected(self.pins))
        with ExitStack() as stack:
            _, probe = self.setup_live(stack)
            probe.side_effect = ValueError('fresh initialization failed')
            with self.assertRaisesRegex(ValueError, 'fresh initialization failed'):
                P.initialize(execute=True)

    def test_each_identity_and_runtime_drift_rejected(self):
        bad = []
        for name in P.NAMES:
            for key, value in (('bytes',True), ('sha256','0'*64), ('path','/local/private')):
                result=P._expected(self.pins);result['native_files'][name][key]=value;bad.append(result)
        for key in self.pins['runtime_requirements']:
            result=P._expected(self.pins);result['runtime'][key]=None;bad.append(result)
        for key, value in (('schema',True),('python_version',[3,12,13]),('environment_matches',False),
                           ('native_five_match',False),('status','RUNTIME_INITIALIZED_INCOMPATIBLE'),
                           ('numeric_execution_allowed',True),('model_executed',True),
                           ('reference_executed',True),('rtl_executed',True),('incompatibilities',['drift']),
                           ('extra','bad')):
            result=P._expected(self.pins);result[key]=value;bad.append(result)
        for result in bad:
            with self.subTest(result=result), ExitStack() as stack:
                self.setup_live(stack,[result])
                with self.assertRaisesRegex(ValueError,'summary drift'): P.initialize(execute=True)

    def test_python_identity_checked_before_and_after(self):
        for records, calls in (([{'bytes':17752,'sha256':'0'*64}],0),
                               ([P.PYTHON_IDENTITY, {'bytes':17753,'sha256':P.PYTHON_IDENTITY['sha256']}],1)):
            with ExitStack() as stack:
                identity, probe=self.setup_live(stack)
                identity.side_effect=records
                with self.assertRaises(ValueError):P.initialize(execute=True)
                self.assertEqual(probe.call_count,calls)

    def test_initializer_and_inventory_origin_drift(self):
        for module in (published, published.inventory):
            with ExitStack() as stack:
                _,probe=self.setup_live(stack)
                stack.enter_context(patch.object(module,'__file__','/tmp/foreign.py'))
                with self.assertRaisesRegex(ValueError,'origin drift'):P.initialize(execute=True)
                probe.assert_not_called()

    def test_preimported_numeric_rejected(self):
        for name in ('torch','numpy','transformers.submodule'):
            with ExitStack() as stack:
                _,probe=self.setup_live(stack)
                stack.enter_context(patch.dict(sys.modules,{name:object()}))
                with self.assertRaisesRegex(ValueError,'fresh numeric'):P.initialize(execute=True)
                probe.assert_not_called()

    def test_wrong_root_before_probe(self):
        with patch.object(published,'initialize',side_effect=AssertionError('must not init')):
            with self.assertRaisesRegex(ValueError,'fixed CI platform root'):
                P.initialize('/tmp/foreign',execute=True)

    def test_location_exact_root_version_and_hosted_python(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(P,'ROOT',P.CI_ROOT))
            stack.enter_context(patch.object(Path,'resolve',lambda self, **kwargs:self))
            stack.enter_context(patch.object(Path,'is_symlink',return_value=False))
            stack.enter_context(patch.object(sys,'version_info',(3,12,14)))
            executable=str(P.PYTHON_HOME/'bin/python3.12')
            with patch.object(sys,'executable',executable):self.assertEqual(P.location(P.CI_ROOT),Path(executable))
            for executable in ('/usr/bin/python3.12',str(P.PYTHON_HOME)+'-foreign/bin/python3.12'):
                with patch.object(sys,'executable',executable), self.assertRaisesRegex(ValueError,'hostedtoolcache'):
                    P.location(P.CI_ROOT)
            with patch.object(sys,'version_info',(3,12,13)),self.assertRaisesRegex(ValueError,'3.12.14'):
                P.location(P.CI_ROOT)

    def test_source_drift_rejected(self):
        with patch.object(Path,'read_bytes',return_value=b'changed'):
            with self.assertRaisesRegex(ValueError,'source drift'):P.sources(P.ROOT)

    def test_changes_during_initialization_rejected(self):
        with ExitStack() as stack:
            self.setup_live(stack)
            P.location.side_effect=[P.PYTHON_HOME/'bin/python3.12', P.PYTHON_HOME/'bin/other']
            with self.assertRaisesRegex(ValueError,'path changed'):P.initialize(execute=True)
        with ExitStack() as stack:
            self.setup_live(stack)
            P.sources.side_effect=[self.pins,{}]
            with self.assertRaisesRegex(ValueError,'source changed'):P.initialize(execute=True)


if __name__=='__main__':unittest.main()

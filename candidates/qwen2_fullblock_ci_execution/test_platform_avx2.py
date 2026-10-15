"""Cold AVX2 candidate integration checks, without importing numerical packages."""
import inspect
import ast
import json
import subprocess
import sys
from contextlib import ExitStack
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from candidates.qwen2_fullblock_ci_execution import platform as P
from candidates.qwen2_fullblock_ci_execution import platform_avx2 as A
from candidates.qwen2_fullblock_ci_prepare import initialize_platform as O

ENV = {'QWEN2_CI_RUNTIME_PROFILE': 'avx2-candidate-v1', 'ATEN_CPU_CAPABILITY': 'avx2'}

class CandidateTests(unittest.TestCase):
    def test_body_is_original_except_explicit_pins_projection_and_hardware_precheck(self):
        body = inspect.getsource(A.initialize)
        body = body.replace("    need(runtime_profile.selected(), 'explicit AVX2 candidate required')\n    hardware_gate()\n", '')
        body = body.replace('runtime_profile.apply(load_pins())', 'load_pins()')
        self.assertEqual(body, inspect.getsource(O.initialize))

    def test_hardware_refuses_missing_capabilities(self):
        for text in ('', 'flags : avx2', 'flags : fma', 'flags : avx2 fma\nflags : fma'):
            with self.subTest(text=text), patch.object(Path, 'read_text', return_value=text):
                with self.assertRaises(ValueError): A.hardware_gate()
        with patch.object(Path, 'read_text', return_value='flags : avx2 fma sse\nflags : avx2 fma'):
            A.hardware_gate()

    def test_candidate_summary_expectation_keeps_native_and_all_other_runtime_pins(self):
        pins=P.sources(P.ROOT)
        with patch.dict(os.environ, {}, clear=True): original=P._expected(pins)
        with patch.dict(os.environ, ENV, clear=True): candidate=P._expected(pins)
        self.assertEqual(candidate['native_files'], original['native_files'])
        self.assertEqual(set(k for k in candidate['runtime'] if candidate['runtime'][k]!=original['runtime'][k]),
                         {'capability', 'torch_build_sha256'})
        for key in original:
            if key!='runtime': self.assertEqual(candidate[key],original[key])

    def test_default_cannot_execute_candidate_initializer(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(A, 'hardware_gate', side_effect=AssertionError('unexpected IO')):
            with self.assertRaises(ValueError): A.initialize()

    def test_original_guard_environment_rebuild_reaches_actual_fresh_child(self):
        source=(P.ROOT/'candidates/qwen2_fullblock_reference_m128/guard.py').read_text()
        function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='run_body')
        block=next(n for n in ast.walk(function) if isinstance(n,ast.Try) and any(
            isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='env' for t in x.targets)
            for x in n.body))
        index=next(i for i,n in enumerate(block.body) if isinstance(n,ast.Assign) and
                   any(isinstance(t,ast.Name) and t.id=='env' for t in n.targets))
        statements=block.body[index:index+3]
        self.assertIsInstance(statements[2],ast.For)
        with patch.dict(os.environ, ENV, clear=True):
            pins=P.runtime_profile.apply(P.sources(P.ROOT))
            namespace={'os':os,'pins':pins}
            exec(compile(ast.Module(body=statements,type_ignores=[]),'<original_guard_environment>','exec'),namespace)
            environment=namespace['env']
        self.assertEqual(environment['ATEN_CPU_CAPABILITY'],'avx2')
        self.assertEqual(environment['QWEN2_CI_RUNTIME_PROFILE'],'avx2-candidate-v1')
        result=subprocess.run([sys.executable,'-B','-c',
            "import json,os;print(json.dumps([os.environ.get('ATEN_CPU_CAPABILITY'),os.environ.get('QWEN2_CI_RUNTIME_PROFILE')]))"],
            env=environment,capture_output=True,text=True,timeout=5,check=True)
        self.assertEqual(json.loads(result.stdout),['avx2','avx2-candidate-v1'])

    def test_live_candidate_route_calls_only_candidate_initializer(self):
        pins=P.sources(P.ROOT)
        executable=P.PYTHON_HOME/'bin/python3.12'
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,ENV,clear=True))
            stack.enter_context(patch.object(P,'location',return_value=executable))
            stack.enter_context(patch.object(P,'sources',return_value=pins))
            stack.enter_context(patch.object(O,'ROOT',P.CI_ROOT))
            stack.enter_context(patch.object(O,'__file__',str(P.CI_ROOT/'candidates/qwen2_fullblock_ci_prepare/initialize_platform.py')))
            stack.enter_context(patch.object(O.inventory,'__file__',str(P.CI_ROOT/'candidates/qwen2_fullblock_ci_prepare/platform_inventory.py')))
            stack.enter_context(patch.object(O.inventory,'identity',return_value=P.PYTHON_IDENTITY))
            stack.enter_context(patch.object(A,'__file__',str(P.CI_ROOT/'candidates/qwen2_fullblock_ci_execution/platform_avx2.py')))
            stack.enter_context(patch.object(O,'initialize',side_effect=AssertionError('default route')))
            probe=stack.enter_context(patch.object(A,'initialize',return_value=P._expected(pins)))
            result=P.initialize(P.CI_ROOT,execute=True)
            self.assertEqual(result['runtime']['capability'],'AVX2')
            probe.assert_called_once_with()

if __name__ == '__main__': unittest.main()

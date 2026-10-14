"""Cold/source/control evidence only. No fullblock numeric permission is implied."""
import ast
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from . import gates,runner,launch,statistics


class ColdTests(unittest.TestCase):
    def test_defaults_never_initialize_numeric(self):
        for entry in (runner,launch):
            stream=io.StringIO()
            with patch.object(runner,'dependencies',side_effect=AssertionError('numeric forbidden')), \
                 patch.object(subprocess,'Popen',side_effect=AssertionError('spawn forbidden')), \
                 contextlib.redirect_stdout(stream):
                self.assertEqual(entry.main([]),0)
            result=json.loads(stream.getvalue())
            self.assertEqual(result['status'],'NOT_EXECUTED')
            self.assertFalse(result['input_loading'] or result['actual_execution_authorized'])

    def test_actual_requires_reviewed_whole_budget(self):
        with self.assertRaisesRegex(ValueError,'budget unreviewed'):gates.require_budget()
        with patch.object(runner,'dependencies',side_effect=AssertionError('numeric forbidden')):
            with self.assertRaisesRegex(ValueError,'budget unreviewed'):
                runner.run(gates.OUTPUT_ROOT/'must_not_exist',str(gates.DATA.relative_to(gates.ROOT)),
                    str(gates.REFERENCE.relative_to(gates.ROOT)),reviewed_source_manifest=gates.manifest(gates.sources()))
        self.assertFalse((gates.OUTPUT_ROOT/'must_not_exist').exists())

    def test_original_tail_algorithm_ast_equivalent(self):
        old_path=gates.ROOT/'candidates/qwen2_resident_matrix/ffn_public/fullgraph_execution.py'
        new_path=gates.HERE/'tail.py'
        def body(path,name):
            tree=ast.parse(path.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            start=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.For))
            return ast.Module(body=copy.deepcopy(fn.body[start:]),type_ignores=[])
        class StripReadOnlyAnnotations(ast.NodeTransformer):
            def visit_Expr(self,node):
                if isinstance(node.value,ast.Call):
                    call=node.value
                    if isinstance(call.func,ast.Name) and call.func.id=='stage':return None
                    if isinstance(call.func,ast.Name) and call.func.id=='require' and call.args and \
                        isinstance(call.args[-1],ast.Constant) and call.args[-1].value in (
                            'whole block has outstanding tail obligations','live physical buffer/resource replacement'):return None
                return self.generic_visit(node)
            def visit_Constant(self,node):
                if node.value=='NOT_EVALUATED_BY_EXECUTION_SEE_COMPARISON':node.value='UNCHANGED_FAIL_POLICY_PENDING'
                return node
        old=body(old_path,'execute_public_suffix');new=StripReadOnlyAnnotations().visit(body(new_path,'execute_tail'))
        self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(new,include_attributes=False))

    def test_runner_declares_no_saved_activation_source(self):
        source=(gates.HERE/'runner.py').read_text()
        self.assertNotIn('m128_pv32_bounded_actual_v2',source)
        self.assertIn('memory=FullGraphMemory(physical)',source)
        self.assertLess(source.index('memory=FullGraphMemory(physical)'),source.index('x=PV32PublicExecution('))
        self.assertIn('silu=ObservedSiluLibrary(selected,128)',source)
        self.assertEqual(source.count('selected.sf_reset()'),1)
        self.assertNotIn('gate.opened=True',source)

    def test_statistics_distinguish_issue_and_busy(self):
        before=dict(host={'host_model_ticks':2},matrix={'dense_steps':3,'owner_acquires':1})
        after=dict(host={'host_model_ticks':12},matrix={'dense_steps':7,'owner_acquires':2})
        d=statistics.delta(after,before)
        self.assertEqual(d,dict(host={'host_model_ticks':10},matrix={'dense_steps':4,'owner_acquires':1}))
        with self.assertRaises(ValueError):statistics.delta(before,after)
        source=(gates.HERE/'statistics.py').read_text()
        for field in ('hardware_cycles=None','hardware_busy_fraction=None','hardware_utilization=None',
                      'matrix_busy_ticks=None','matrix_owned_ticks=None'):
            self.assertIn(field,source)

    def test_real_initialized_dependencies_and_hook(self):
        argv=[sys.executable,'-B']
        if sys.flags.optimize:argv.append('-O')
        argv += [str(gates.HERE/'initialized_probe.py'),'--initialized-only']
        cp=subprocess.run(argv,cwd=gates.ROOT,text=True,capture_output=True,timeout=40)
        self.assertEqual(cp.returncode,0,cp.stdout+cp.stderr)
        r=json.loads(cp.stdout)
        self.assertEqual(r['status'],'PASS_REAL_INITIALIZED_FULLBLOCK_CONTROL_ONLY')
        self.assertEqual(r['model_owner_jobs'],0)
        self.assertFalse(r['matrix_fma_executed'] or r['model_inputs_loaded'] or r['reference_payloads_read'])
        self.assertGreaterEqual(len(r['negative_controls']),37)
        self.assertEqual(len(r['environment_events']),2)


if __name__=='__main__':unittest.main()

"""Mocked command/lifecycle tests only; no resource changes or child processes."""
import hashlib
import ast
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('launch_cold',Path(__file__).with_name('launch_cold.py'))
l=importlib.util.module_from_spec(spec);spec.loader.exec_module(l)


class LaunchTests(unittest.TestCase):
    def invoke(self, directory, *, denied=False, cpu=True, child_exit=0, include=False, conv_permission=False, clock_start=100.):
        base=Path(directory);runner=base/'runner.py'
        runner.write_text('def execute(*args, **kwargs):\n result='+repr(dict(exit=child_exit,error=None,cleanup_complete=True))+
            "\n result.update(argv=args[0], stage_stop=kwargs['stage_stop'], absolute_stop=kwargs['absolute_stop'], stdout_limit=kwargs['stdout_limit'], tree_limit=kwargs['tree_limit'])\n return result\n")
        interpreter=base/'python';interpreter.write_bytes(b'synthetic interpreter identity, never executed')
        ip=dict(bytes=interpreter.stat().st_size,sha256=hashlib.sha256(interpreter.read_bytes()).hexdigest(),resolved=str(interpreter))
        gate=dict(plan={'repository':str(base/'source'),'environment':{},'comparison':{'python':str(interpreter)},'inputs':{str(interpreter):ip}},_plan_path=base/'original/PLAN.json',
            native_manifest=base/'reference/native/manifest.json',include_conv_reference_arithmetic=conv_permission,
            _manifest_path=base/'handoff.json',config=dict(_path=base/'config.json',paths={'repository':base/'source'},terminal={'retained_exec_session':7}))
        fake=types.ModuleType('terminal_gate')
        def admit(*args,**kwargs):
            if denied:raise ValueError('original cleanup unverified')
            return gate
        fake.admit_terminal_manifest=admit;fake.recheck_terminal_manifest=lambda gate:None
        fake.read_source=lambda repository,name:(runner,runner.read_bytes())
        args=['--config',str(base/'config.json'),'--reviewed-config-sha256','c'*64,'--terminal-manifest',str(base/'handoff.json'),'--reviewed-terminal-sha256','a'*64,
              '--reviewed-code-pins-sha256','b'*64,'--output-dir',str(base/'result')]
        if include:args.append('--include-conv')
        with patch.object(l,'_load_gate',return_value=fake),patch.object(l,'check_code'),patch.object(l.sys,'executable',str(interpreter)), \
             patch.object(l.os,'sched_getaffinity',return_value={1} if cpu else {0}), \
             patch.object(l.os,'sched_setaffinity') as affinity,patch.object(l.resource,'setrlimit') as limits, \
             patch.object(l.signal,'signal'),patch.object(l.signal,'setitimer'), \
             patch.object(l.time,'monotonic',return_value=clock_start),patch('builtins.print'):
            result=l.main(args)
            return result,json.loads((base/'result/PROCESS.json').read_text()),affinity.call_args_list,limits.call_args_list

    def test_success_is_process_completion_not_numeric_pass(self):
        with tempfile.TemporaryDirectory() as d:
            code,report,affinity,limits=self.invoke(d)
            self.assertEqual(code,0);self.assertIsNone(report['numerical_acceptance'])
            self.assertIs(report['combined_full_run_acceptance'],False)
            self.assertEqual(report['status'],'DIAGNOSTIC_PROCESS_COMPLETE')
            self.assertEqual(report['outer_stop']-report['started_monotonic'],330)
            self.assertEqual(len(affinity),1);self.assertEqual(len(limits),3)
            command=report['supervision']['argv']
            self.assertEqual(command[:4],[str(Path(d)/'python'),'-I','-S','-B'])
            self.assertEqual(Path(command[4]).name,'cold_postterminal.py')
            self.assertNotIn('--include-conv',command)
            self.assertEqual(report['supervision']['stage_stop']-report['started_monotonic'],300)
            self.assertEqual(report['supervision']['absolute_stop']-report['started_monotonic'],325)
            self.assertEqual(report['supervision']['stdout_limit'],4<<20)
            self.assertEqual(report['supervision']['tree_limit'],128<<20)

    def test_deadlines_derive_from_representative_clock_starts(self):
        # The fractional sample reproduces lossy subtraction of absolute stops.
        # Compare exact deadline construction, without tolerances or live clocks.
        for start in (0., 200.00000000000006, (1 << 20) + .125, (1 << 40) + .125):
            with self.subTest(start=start),tempfile.TemporaryDirectory() as d:
                _,report,_,_=self.invoke(d,clock_start=start)
                self.assertEqual(report['started_monotonic'],start)
                self.assertEqual(report['outer_stop'],start+330)
                self.assertEqual(report['work_stop'],start+300)
                self.assertEqual(report['cleanup_stop'],start+325)
                self.assertEqual(report['supervision']['stage_stop'],start+300)
                self.assertEqual(report['supervision']['absolute_stop'],start+325)

    def test_original_cleanup_denial_creates_no_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'cleanup unverified'):self.invoke(d,denied=True)
            self.assertFalse((Path(d)/'result').exists())

    def test_cpu_unavailable_no_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'CPU1 unavailable'):self.invoke(d,cpu=False)
            self.assertFalse((Path(d)/'result').exists())

    def test_conv_requires_explicit_handoff_permission(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'Conv arithmetic not authorized'):self.invoke(d,include=True)
            self.assertFalse((Path(d)/'result').exists())

    def test_child_failure_never_qualifies(self):
        with tempfile.TemporaryDirectory() as d:
            code,report,_,_=self.invoke(d,child_exit=1)
            self.assertEqual(code,1);self.assertEqual(report['status'],'INCOMPLETE_DIAGNOSTIC_PROCESS')
            self.assertIsNone(report['numerical_acceptance']);self.assertIs(report['combined_full_run_acceptance'],False)

    def test_code_pin_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pins.json';p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'reviewed adapter pins changed'):l.check_code(p,'0'*64)

    def test_exact_local_code_inventory_and_source_pins(self):
        path=Path(__file__).with_name('CODE_PINS.json')
        pins=l.check_code(path,hashlib.sha256(path.read_bytes()).hexdigest())
        gate=l._load_gate(pins)
        self.assertEqual(Path(gate.__file__),Path(__file__).with_name('terminal_gate.py'))
        self.assertEqual(set(pins),{'cold_postterminal.py','launch_cold.py','terminal_gate.py'})

    def test_isolated_cli_missing_and_unreviewed_handoffs(self):
        smoke=Path(__file__).with_name('smoke_isolated_handoff.py')
        result=subprocess.run([sys.executable,'-I','-S','-B',str(smoke)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        record=json.loads(result.stdout)
        self.assertEqual(record['synthetic_cases'],2)
        self.assertEqual(record['status'],'PASS')
        self.assertFalse(record['actual_access'])
        self.assertFalse(record['model_native_execution'])
        self.assertFalse(record['output_created'])

    def test_bootstrap_implementations_remain_identical(self):
        here=Path(__file__).parent
        for name in ('check_code','_load_gate'):
            def function(file):
                tree=ast.parse((here/file).read_bytes())
                return next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
            self.assertEqual(ast.dump(function('cold_postterminal.py')),ast.dump(function('launch_cold.py')))

    def test_code_source_drift_and_alias_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            originals={name:(l.HERE/name).read_bytes() for name in ('cold_postterminal.py','launch_cold.py','terminal_gate.py')}
            for name,raw in originals.items():(base/name).write_bytes(raw)
            pins={name:dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) for name,raw in originals.items()}
            pinfile=base/'CODE_PINS.json';pinfile.write_text(json.dumps(pins));reviewed=hashlib.sha256(pinfile.read_bytes()).hexdigest()
            with patch.object(l,'HERE',base):
                l.check_code(pinfile,reviewed)
                (base/'terminal_gate.py').write_bytes(b'SYNTHETIC SOURCE DRIFT')
                with self.assertRaisesRegex(ValueError,'adapter source changed'):l.check_code(pinfile,reviewed)
                with self.assertRaisesRegex(ValueError,'source/origin mismatch'):l._load_gate(pins)
                (base/'terminal_gate.py').unlink()
                (base/'target.py').write_bytes(originals['terminal_gate.py'])
                (base/'terminal_gate.py').symlink_to(base/'target.py')
                with self.assertRaisesRegex(ValueError,'source path alias'):l.check_code(pinfile,reviewed)

    def test_incomplete_adapter_inventory_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'pins.json';path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'exact adapter code inventory'):
                l.check_code(path,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_reviewed_bindings_are_forwarded_to_isolated_child(self):
        with tempfile.TemporaryDirectory() as d:
            _,record,_,_=self.invoke(d)
            args=record['supervision']['argv']
            for flag,value in (('--config',str(Path(d)/'config.json')),('--reviewed-config-sha256','c'*64),
                ('--terminal-manifest',str(Path(d)/'handoff.json')),('--reviewed-terminal-sha256','a'*64),
                ('--reviewed-code-pins-sha256','b'*64)):
                self.assertEqual(args[args.index(flag)+1],value)
            self.assertEqual(record['original_exec_session'],7)
            self.assertEqual(record['reviewed_configuration_sha256'],'c'*64)

    def test_permitted_conv_is_still_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            _,record,_,_=self.invoke(d,include=True,conv_permission=True)
            self.assertEqual(record['supervision']['argv'].count('--include-conv'),1)


if __name__ == '__main__':unittest.main()

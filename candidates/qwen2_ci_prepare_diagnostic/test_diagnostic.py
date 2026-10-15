import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from candidates.qwen2_ci_prepare_diagnostic import diagnostic as d

class DiagnosticTests(unittest.TestCase):
    def test_default_no_io(self):
        with patch('io.open',side_effect=AssertionError('I/O')),patch.object(d.original,'prepare') as prepare:
            self.assertEqual(d.diagnose(),d.record());prepare.assert_not_called()
    def test_partial_optin_never_prepares(self):
        for args in ({'execute':True},{'download':True},{'execute':1,'download':True}):
            with patch.object(d.original,'prepare') as prepare:
                r=d.diagnose(**args);self.assertEqual(r['exception'],'VALUE_ERROR');prepare.assert_not_called()
    def test_error_text_not_used(self):
        class Evil(ValueError):
            def __str__(self):raise AssertionError('text accessed')
            def __repr__(self):raise AssertionError('repr accessed')
        self.assertEqual(d.sanitize(Evil('SECRET'))['exception'],'OTHER')
        self.assertNotIn('SECRET',json.dumps(d.sanitize(ValueError('SECRET'))))
    def test_only_approved_traceback_file(self):
        try:exec(compile("raise ValueError('SECRET')",'/secret/model.bin','exec'))
        except ValueError as error:r=d.sanitize(error)
        self.assertEqual(r['module'],'OTHER');self.assertEqual(r['line'],0)
    def test_approved_module_and_line(self):
        filename=str(d.ROOT/d.MODULE_FILES['PLATFORM'])
        try:exec(compile("raise ValueError('SECRET')",filename,'exec'))
        except ValueError as error:r=d.sanitize(error)
        self.assertEqual(r,dict(exception='VALUE_ERROR',module='PLATFORM',line=1))
    def test_skip_fixed_guard_frames_use_approved_callsite(self):
        filename=str(d.ROOT/d.MODULE_FILES['PLATFORM'])
        for guard in ('need','require'):
            source=f"def {guard}():\n    raise ValueError('SECRET')\ndef initialize():\n    {guard}()\ninitialize()\n"
            try:exec(compile(source,filename,'exec'),{})
            except ValueError as error:r=d.sanitize(error)
            self.assertEqual(r,dict(exception='VALUE_ERROR',module='PLATFORM',line=4))
    def test_only_guard_approved_frame_is_unknown(self):
        namespace={}
        exec(compile("def need():\n    raise ValueError('SECRET')\n",str(d.ROOT/d.MODULE_FILES['PLATFORM']),'exec'),namespace)
        try:namespace['need']()
        except ValueError as error:r=d.sanitize(error)
        self.assertEqual(r,dict(exception='VALUE_ERROR',module='OTHER',line=0))
    def test_schema_rejects_unapproved_output(self):
        for field,value in [('phase','SECRET'),('exception','SECRET'),('module','/secret'),
                            ('line',True),('line',-1),('line',1000001),('schema',True)]:
            r=d.record();r[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):d.checked(r)
        r=d.record();r['message']='SECRET'
        with self.assertRaises(ValueError):d.checked(r)
    def test_wrapper_forwards_exact_args_result_exception(self):
        state={};sentinel=object();f=Mock(return_value=sentinel)
        self.assertIs(d.wrap(f,'QKV_ACQUIRE',state)(1,a=sentinel),sentinel)
        f.assert_called_once_with(1,a=sentinel);self.assertEqual(state['phase'],'QKV_ACQUIRE')
        error=RuntimeError('SECRET');f=Mock(side_effect=error)
        try:d.wrap(f,'TAIL_MATERIALIZE',state)(sentinel)
        except RuntimeError as got:self.assertIs(got,error)
        else:self.fail('not raised')
    def test_nested_verifier_preserves_materialization_phase(self):
        state={}
        inner=d.wrap(Mock(side_effect=ValueError('SECRET')),'QKV_VERIFY',state)
        with self.assertRaises(ValueError):d.wrap(inner,'QKV_MATERIALIZE',state)()
        self.assertEqual(state['phase'],'QKV_MATERIALIZE');self.assertEqual(state['depth'],0)
    def test_instrument_restores_functions(self):
        state={};q={k:Mock(return_value=k) for k in ('acquire','materialize','read_subset','read_inputs')}
        tail={k:Mock(return_value=k) for k in ('materialize','input_metadata')};a=SimpleNamespace(acquire=Mock())
        originals=dict(q);original_tail=dict(tail);original_acquire=a.acquire
        result=(q,{},tail,a,{},{});contracts=Mock(return_value=result)
        with patch.object(d.original.inputs,'contracts',contracts):
            with d.instrument(state):
                self.assertIs(d.original.inputs.contracts(1,x=2),result)
                contracts.assert_called_once_with(1,x=2)
                for key,phase in [('acquire','QKV_ACQUIRE'),('materialize','QKV_MATERIALIZE'),('read_subset','QKV_VERIFY')]:
                    self.assertEqual(q[key](),key);self.assertEqual(state['phase'],phase)
                a.acquire();self.assertEqual(state['phase'],'TAIL_ACQUIRE')
                tail['input_metadata']();self.assertEqual(state['phase'],'INPUT_VERIFY')
            self.assertEqual(q,originals);self.assertEqual(tail,original_tail);self.assertIs(a.acquire,original_acquire)
    def test_failed_child_safe_record_retained(self):
        value=d.record('FAILED','PLATFORM');value.update(exception='VALUE_ERROR',module='INITIALIZE_PLATFORM',line=74)
        child=SimpleNamespace(stdout=json.dumps(value),stderr='SECRET',returncode=2)
        with patch.object(d.subprocess,'run',return_value=child) as run:
            log=io.StringIO();r=d.platform_diagnostic(log)
        self.assertEqual(r,dict(exception='VALUE_ERROR',module='INITIALIZE_PLATFORM',line=74))
        self.assertNotIn('SECRET',json.dumps(r));self.assertIn('SECRET',log.getvalue())
        self.assertEqual(run.call_args.kwargs['timeout'],60)
    def test_malicious_child_never_leaks(self):
        for output in ('SECRET',json.dumps({**d.record(),'message':'SECRET'})):
            with patch.object(d.subprocess,'run',return_value=SimpleNamespace(stdout=output,stderr='SECRET',returncode=0)):
                r=d.platform_diagnostic(io.StringIO());self.assertNotIn('SECRET',json.dumps(r))
    def test_diagnose_calls_original_prepare(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            @contextlib.contextmanager
            def sink(path):yield io.StringIO()
            with patch.object(d,'ROOT',root),patch.object(d.original.inputs,'preflight'), \
                 patch.object(d,'local_output',sink),patch.object(d.original,'prepare',return_value={}) as prepare:
                r=d.diagnose(execute=True,download=True)
            self.assertEqual(r['phase'],'COMPLETE');prepare.assert_called_once_with(execute=True,download=True)
    def test_platform_failure_only_invokes_child_on_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            @contextlib.contextmanager
            def sink(path):yield io.StringIO()
            def prepare(**kwargs):d.original.current_platform()
            with patch.object(d,'ROOT',Path(tmp)),patch.object(d.original.inputs,'preflight'), \
                 patch.object(d,'local_output',sink),patch.object(d.original,'prepare',prepare), \
                 patch.object(d.original,'current_platform',side_effect=ValueError('SECRET')), \
                 patch.object(d,'platform_diagnostic',return_value=dict(exception='VALUE_ERROR',module='PLATFORM',line=5)) as child:
                r=d.diagnose(execute=True,download=True)
            self.assertEqual(r['phase'],'PLATFORM');child.assert_called_once();self.assertNotIn('SECRET',json.dumps(r))
    def test_invalid_cli_cannot_echo_secret(self):
        out=io.StringIO();err=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(d.main(['--SECRET_TOKEN']),2)
        self.assertEqual(err.getvalue(),'');self.assertNotIn('SECRET',out.getvalue())
        d.checked(json.loads(out.getvalue()))
    def test_cli_default_json(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):self.assertEqual(d.main([]),0)
        self.assertEqual(json.loads(out.getvalue()),d.record())

if __name__=='__main__':unittest.main()

"""Mock-only worker tests. Never import Torch or execute tensor arithmetic."""
import contextlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from candidates.qwen2_ci_linear_backend_probe import worker as w


class WorkerTests(unittest.TestCase):
    def fake_torch(self):
        linear=Mock();linear.eval.return_value=linear
        mkldnn=SimpleNamespace(enabled=None)
        torch=SimpleNamespace(bfloat16=object(),backends=SimpleNamespace(mkldnn=mkldnn),
            no_grad=Mock(side_effect=contextlib.nullcontext),
            nn=SimpleNamespace(Linear=Mock(return_value=linear),Parameter=Mock(side_effect=lambda data,**kwargs:data)),
            full=Mock(side_effect=[object(),object(),object()]))
        return torch,linear

    def test_default_cold(self):
        with patch.object(w,'initialize',side_effect=AssertionError('native init')):
            self.assertEqual(w.run(),dict(schema=1,status='NOT_EXECUTED',mode='none'))

    def test_unknown_mode_rejected_before_initialization(self):
        for mode in ('','Enabled','avx2',True,1,[],{}):
            with self.subTest(mode=mode),patch.object(w,'initialize') as init,self.assertRaises(ValueError):
                w.run(mode)
            init.assert_not_called()

    def test_exact_one_forward_each_explicit_mode(self):
        for mode,enabled in [('enabled',True),('disabled',False)]:
            torch,linear=self.fake_torch()
            with patch.object(w,'initialize',return_value=torch) as init:
                result=w.run(mode)
            init.assert_called_once_with();self.assertIs(torch.backends.mkldnn.enabled,enabled)
            torch.nn.Linear.assert_called_once_with(1536,1536,bias=True,device='meta',dtype=torch.bfloat16)
            self.assertEqual(torch.full.call_count,3)
            expected=[((1536,1536),0.0625),((1536,),0.03125),((1,128,1536),0.125)]
            for call,(shape,value) in zip(torch.full.call_args_list,expected):
                self.assertEqual(call.args,(shape,value));self.assertEqual(call.kwargs,dict(dtype=torch.bfloat16,device='cpu'))
            self.assertEqual(torch.nn.Parameter.call_count,2)
            for call in torch.nn.Parameter.call_args_list:self.assertEqual(call.kwargs,{'requires_grad':False})
            linear.eval.assert_called_once_with();self.assertEqual(linear.call_count,1)
            self.assertEqual(result,dict(schema=1,status='SYNTHETIC_LINEAR_COMPLETED',mode=mode))

    def test_original_platform_all_strict_gates_retained(self):
        expected=dict(expected_runtime_matches=True,native_five_match=True,environment_matches=True)
        sentinel=object();pins=object()
        with patch.object(w.platform,'location',return_value='/fixed/python') as loc, \
             patch.object(w.platform,'sources',return_value=pins) as sources, \
             patch.object(w.platform_avx2,'initialize',return_value=expected) as initializer, \
             patch.object(w.platform,'_expected',return_value=expected) as expectation, \
             patch.object(w.importlib,'import_module',return_value=sentinel) as importer:
            self.assertIs(w.initialize(),sentinel)
        self.assertEqual(loc.call_count,2);sources.assert_called_once_with(w.ROOT)
        initializer.assert_called_once_with();expectation.assert_called_once_with(pins)
        importer.assert_called_once_with('torch')

    def test_incompatible_runtime_never_reaches_torch_operation(self):
        good=dict(expected_runtime_matches=True,native_five_match=True,environment_matches=True)
        for field in good:
            for bad in (False,1,None):
                observed=dict(good);observed[field]=bad
                with self.subTest(field=field,bad=bad), \
                     patch.object(w.platform,'location',return_value='/fixed/python'), \
                     patch.object(w.platform,'sources'), \
                     patch.object(w.platform_avx2,'initialize',return_value=observed), \
                     patch.object(w.importlib,'import_module') as importer,self.assertRaises(ValueError):
                    w.initialize()
                importer.assert_not_called()

    def test_full_runtime_summary_drift_rejected(self):
        summary=dict(expected_runtime_matches=True,native_five_match=True,environment_matches=True)
        with patch.object(w.platform,'location',return_value='/fixed/python'),patch.object(w.platform,'sources'), \
             patch.object(w.platform_avx2,'initialize',return_value={**summary,'extra':'drift'}), \
             patch.object(w.platform,'_expected',return_value=summary), \
             patch.object(w.importlib,'import_module') as importer,self.assertRaises(ValueError):
            w.initialize()
        importer.assert_not_called()

    def test_cli_errors_never_echo_secrets(self):
        for argv in (['--mode','SECRET'],['--SECRET'],['--mode','enabled']):
            out=io.StringIO();err=io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err), \
                 patch.object(w,'initialize',side_effect=RuntimeError('SECRET tensor values')):
                self.assertEqual(w.main(argv),2)
            self.assertEqual(err.getvalue(),'');self.assertNotIn('SECRET',out.getvalue())
            self.assertEqual(set(json.loads(out.getvalue())),{'schema','status','mode'})

    def test_cli_default_no_work(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),patch.object(w,'initialize') as init:
            self.assertEqual(w.main([]),0)
        init.assert_not_called();self.assertEqual(json.loads(out.getvalue())['status'],'NOT_EXECUTED')


if __name__=='__main__':unittest.main()

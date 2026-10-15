import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from candidates.qwen2_fullblock_ci_execution import prepare as p
class PrepareTests(unittest.TestCase):
    def test_default(self):
        with patch.object(p.inputs,'preflight',side_effect=AssertionError('must not run')):
            self.assertEqual(p.prepare()['status'],'NOT_EXECUTED')
    def test_optins(self):
        for a,b in ((True,False),(False,True),(1,True)):
            with self.subTest(a=a,b=b),self.assertRaises(ValueError):p.prepare(execute=a,download=b)
    def test_platform_failure_before_download(self):
        with tempfile.TemporaryDirectory() as d,patch.object(p.inputs,'preflight'),patch.object(p.inputs,'safe_path',return_value=Path(d)/'result'),patch.object(p,'current_platform',side_effect=ValueError('platform')),patch.object(p.inputs,'prepare',side_effect=AssertionError('network')):
            with self.assertRaisesRegex(ValueError,'platform'):p.prepare(execute=True,download=True)
    def test_stage_order_no_go(self):
        calls=[]
        with tempfile.TemporaryDirectory() as d,patch.object(p.inputs,'preflight'),patch.object(p.inputs,'safe_path',return_value=Path(d)/'result'),patch.object(p,'current_platform',side_effect=lambda **k:calls.append('runtime') or {}),patch.object(p.inputs,'prepare',side_effect=lambda **k:calls.append('inputs') or {}),patch.object(p.native,'build',side_effect=lambda **k:calls.append('native') or {}):
            r=p.prepare(execute=True,download=True)
            self.assertEqual(calls,['runtime','inputs','native']);self.assertFalse(r['reference_executed']);self.assertEqual([x.name for x in Path(d).iterdir()],['result'])
    def test_real_child_keeps_parent_clean(self):
        import subprocess,sys,json
        original=subprocess.run
        expected={'status':'mock_runtime'}
        def actual_child(argv,**kwargs):
            self.assertEqual(argv[1:],['-B','-m','candidates.qwen2_fullblock_ci_execution.platform','--initialize'])
            return original([sys.executable,'-B','-c',"import sys,json;sys.modules['torch']=object();print(json.dumps({'status':'mock_runtime'}))"],capture_output=True,text=True,timeout=5,check=True)
        before='torch' in sys.modules
        with patch.object(p.platform,'location',return_value=Path(sys.executable)),patch.object(p.platform,'sources',return_value={}),patch.object(p.platform,'_expected',return_value=expected),patch.object(p.subprocess,'run',side_effect=actual_child):
            self.assertEqual(p.current_platform(),expected)
        self.assertEqual('torch' in sys.modules,before)
    def test_child_failure_blocks(self):
        import subprocess,sys
        with patch.object(p.platform,'location',return_value=Path(sys.executable)),patch.object(p.platform,'sources',return_value={}),patch.object(p.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['fake'])):
            with self.assertRaises(subprocess.CalledProcessError):p.current_platform()
if __name__=='__main__':unittest.main()

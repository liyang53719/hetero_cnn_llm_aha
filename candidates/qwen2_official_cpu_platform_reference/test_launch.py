"""Cold entry checks. No tensor/runtime acquisition or numerical capture."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

class LaunchTests(unittest.TestCase):
    def run_entry(self,name,*args):
        return subprocess.run([sys.executable,'-B',str(HERE/name),*args],cwd=ROOT,
            env={k:v for k,v in os.environ.items() if not k.startswith('QWEN2_')},
            capture_output=True,text=True,timeout=20)

    def test_cold_guard(self):
        result=self.run_entry('guard.py')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('NOT_EXECUTED_NEW_CONTRACT_PENDING',result.stdout)

    def test_no_default_authority(self):
        result=self.run_entry('issuer.py','--validate-only')
        self.assertNotEqual(result.returncode,0)

    def test_real_standalone_wiring_and_platform_snapshot(self):
        script="""
import sys
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
import recipe as R, issuer as I, lifecycle as L
assert I.RUN_ID=='new01'
assert I.source_closure_digest()==R.V.source_digest(R.ROOT)
assert R.bootstrap_policy()['output_namespace']==R.WORK
assert L.WALL_SECONDS==120
platform={'python':{'path':'synthetic-python'},'libpython':{'path':'synthetic-libpython'}}
with patch.object(L,'_original_snapshot',return_value={'existing':'kept'}), patch.object(R,'observe_platform_before',return_value=platform) as before, patch.object(R,'observe_platform_after') as after:
    result=L.snapshot(R,{})
    assert result=={'existing':'kept','platform_files':platform}
    before.assert_called_once_with(execute=True)
    after.assert_called_once_with(platform)
assert 'torch' not in sys.modules
"""
        env={k:v for k,v in os.environ.items() if not k.startswith('QWEN2_')}
        env.update(QWEN2_CI_RUNTIME_PROFILE='avx2-aten-gemm-v1',ATEN_CPU_CAPABILITY='avx2')
        result=subprocess.run([sys.executable,'-B','-c',script,str(HERE)],cwd=ROOT,env=env,
            capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_original_env_filter_preserves_new02_certificate_pins(self):
        script="""
import ast, os, sys
sys.path.insert(0,sys.argv[1])
import recipe as R, issuer as I, lifecycle as L, guard as G
assert I.RUN_ID=='new02'
assert R.BINDING==R.C.BINDING=='work/qwen2_fullblock_ci_reference/BINDINGS.json'
assert R.load_pins.__globals__['WORK']==R.C.WORK
assert L.B.WORK==R.WORK=='work/qwen2_official_cpu_platform_reference'
assert L.run_path(R,'new02','bootstrap')==R.ROOT/R.WORK/'new02/bootstrap'
# Execute the exact original three AST statements that build worker env; no
# run_body, subprocess supervisor, runtime loading, or arithmetic is invoked.
tree=ast.parse(G.source)
run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_body')
body=next(n for n in run.body if isinstance(n,ast.Try)).body
index=next(i for i,n in enumerate(body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='env')
fragment=ast.fix_missing_locations(ast.Module(body=body[index:index+3],type_ignores=[]))
state={'os':os,'pins':{'capture_environment':{'ATEN_CPU_CAPABILITY':'avx2'}}}
exec(compile(fragment,'<original-worker-environment>','exec'),state)
for key in ('QWEN2_NEW_REFERENCE_RUN','QWEN2_CI_RUNTIME_PROFILE','QWEN2_BOOTSTRAP_CERTIFICATE_SHA256','QWEN2_BOOTSTRAP_SOURCE_CLOSURE_SHA256'):
    assert state['env'][key]==os.environ[key]
assert state['env']['ATEN_CPU_CAPABILITY']=='avx2'
assert 'torch' not in sys.modules
"""
        env={k:v for k,v in os.environ.items() if not k.startswith('QWEN2_')}
        env.update(QWEN2_NEW_REFERENCE_RUN='new02',QWEN2_CI_RUNTIME_PROFILE='avx2-aten-gemm-v1',
            ATEN_CPU_CAPABILITY='avx2',QWEN2_BOOTSTRAP_CERTIFICATE_SHA256='a'*64,
            QWEN2_BOOTSTRAP_SOURCE_CLOSURE_SHA256='b'*64)
        result=subprocess.run([sys.executable,'-B','-c',script,str(HERE)],cwd=ROOT,env=env,
            capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_frozen_mode_unavailable(self):
        result=self.run_entry('guard.py','--mode','frozen','--run-id','new01')
        self.assertNotEqual(result.returncode,0)

if __name__=='__main__':unittest.main()

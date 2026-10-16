"""Cold source/control tests for actual three-target Public integration."""
import ast
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from . import runtime as r,prepare


class RuntimeTests(unittest.TestCase):
    def test_real_composition_preserves_seven_overlays_and_blocks_launch(self):
        frozen=r.contract_snapshot()
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'composed';result=prepare.prepare(out)
            self.assertEqual(result['generated'],frozen['generated'])
            self.assertEqual(len(result['generated']),10)
            self.assertFalse(result['public_execution_enabled'])
            with self.assertRaises(ValueError):prepare.prepare(out)
        for args in ((),({'rows':128},)):
            with self.assertRaises(ValueError):r.authorize_run(*args,enable_raw_kv=True)

    def test_contract_scope_types_sources_and_unchanged_observer_reject(self):
        raw,value=r.contract_value();read=r.read_source
        for case in ('rows','budget','enabled','missing','foreign','observer','loaded'):
            v=copy.deepcopy(value)
            if case=='rows':v['rows']=True
            elif case=='budget':v['setup_budget']=901
            elif case=='enabled':v['public_execution_enabled']=True
            elif case=='missing':v['source_sha256'].pop(next(iter(v['source_sha256'])))
            elif case=='foreign':v['generated_sha256']['foreign.py']='0'*64
            elif case=='observer':v['generated_sha256']['scripts/observe_qwen2_attention_model.py']='0'*64
            else:v['source_sha256'][r.PREFIX+'runtime.py']='0'*64
            def source(n,limit=4194304):return json.dumps(v).encode() if n==r.PINS_PATH else read(n,limit)
            with self.subTest(case=case),patch.object(r,'read_source',side_effect=source),self.assertRaises(ValueError):r.contract_value()

    def test_context_derives_generated_identity_without_file_or_deadline_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace=Path(temp);end=time.monotonic_ns()+10**9
            c=dict(schema=1,workspace=str(workspace),checkout_commit='a'*40,enable_raw_kv=True,
                source_sha256={'fixed':'b'*64},asset_source_sha256={'fixed':'b'*64},work_deadline_ns=end)
            frozen=dict(sources=c['source_sha256'],contract_sha256='c'*64)
            with patch.object(r,'contract_snapshot',return_value=frozen):
                expanded=r.producer_context(c,workspace)
                self.assertEqual(expanded['work_deadline_ns'],end)
                self.assertFalse(Path(expanded['generated_module']).exists())
                self.assertEqual(expanded['generated_module_sha256'],r.GENERATED_MODULE_SHA256)
                for key,value in (('schema',True),('work_deadline_ns',True),('enable_raw_kv',1),('checkout_commit','bad'),('source_sha256',{})):
                    changed=dict(c);changed[key]=value
                    with self.subTest(key=key),self.assertRaises(ValueError):r.producer_context(changed,workspace)
                expired=dict(c,work_deadline_ns=1)
                with self.assertRaises(ValueError):r.producer_context(expired,workspace)
                self.assertEqual(r.producer_context(expired,workspace,check_deadline=False)['work_deadline_ns'],1)
                with self.assertRaises(TimeoutError):r.remaining(expired,1)
        for ceiling in (True,0,float('nan'),float('inf'),901):
            with self.assertRaises(ValueError):r.remaining({'work_deadline_ns':10**30},ceiling)

    def test_scope_projection_rejects_unrelated_arithmetic_or_new_top_level(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)/'base';prepare.previous.prepare(base,enable_raw_kv=True)
            new=Path(temp)/'new';prepare.prepare(new)
            old={n:(base/n).read_bytes() for n in r.TARGETS};after={n:(new/n).read_bytes() for n in r.TARGETS}
            prepare.check_scope(old,after)
            for name in r.TARGETS:
                changed=dict(after);changed[name]+=b'\ndef unreviewed_arithmetic(): return 1\n'
                with self.assertRaises(ValueError):prepare.check_scope(old,changed)

    def test_actual_composed_asset_setup_and_entry_source_closure(self):
        frozen=r.contract_snapshot()
        with tempfile.TemporaryDirectory() as temp:
            tree=Path(temp)/'tree';tree.mkdir();out=Path(temp)/'overlay';prepare.prepare(out)
            for name in frozen['sources']:
                target=tree/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(r.ROOT/name,target)
            for name in frozen['generated']:shutil.copyfile(out/name,tree/name)
            script=r'''
import ast,builtins,ctypes,importlib,importlib.util,sys,types
from pathlib import Path
root=Path.cwd()
original=builtins.__import__
def guard(name,*args,**kwargs):
    if name.split('.')[0] in ('torch','numpy','transformers'):raise AssertionError('numerical import forbidden')
    return original(name,*args,**kwargs)
builtins.__import__=guard
ctypes.CDLL=ctypes.PyDLL=lambda *a,**k:(_ for _ in ()).throw(AssertionError('native load forbidden'))
from candidates.qwen2_resident_matrix.raw_kv_public_recipe_runtime import runtime as r
from candidates.qwen2_resident_matrix.raw_kv_public_fresh import assets,setup
expected=r.source_snapshot()
assert assets.own_sources()==assets.source_snapshot(enable_raw_kv=True)==setup.source_snapshot(True)==setup.asset_sources(expected)==expected
assert setup.PHASES==tuple(r.PHASE_LIMITS) and len(setup.PHASES)==9
assert setup.TOTAL_SECONDS==900 and assets.PROFILE==r.ASSET_PROFILE

def load(relative,name):
    spec=importlib.util.spec_from_file_location(name,root/relative);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module

def extract(relative,assignments,methods,ns):
    nodes=[n for n in ast.parse((root/relative).read_bytes()).body if
        isinstance(n,ast.FunctionDef) and n.name in methods or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in assignments for t in n.targets)]
    assert {n.name for n in nodes if isinstance(n,ast.FunctionDef)}==set(methods)
    assert {t.id for n in nodes if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name)}==set(assignments)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(root/relative),'exec'),ns);return types.SimpleNamespace(**ns)
prefix='candidates/qwen2_resident_matrix/ffn_public/'
helper=load(prefix+'check_numeric.py','candidates.qwen2_resident_matrix.ffn_public.check_numeric')
base=load(prefix+'check_prefix_numeric.py','cold_prefix_identity')
full=extract(prefix+'check_fullgraph_numeric.py',('LIBRARY_SOURCES',),('source_hashes',),dict(ROOT=root,base=base,file_sha=base.file_sha,importlib=importlib,sys=sys))
assert len(full.source_hashes())==75
prior=extract('candidates/qwen2_resident_matrix/official_bf16/check_numeric.py',('PREFIX','NEW_SOURCES'),('source_hashes',),dict(ROOT=root,old=full,require=base.require,file_sha=base.file_sha,fresh_assets=assets))
entry=extract(r.prerequisite.ENTRY,('PREFIX','EXECUTION_FILES','RAW_KV_SOURCES','RAW_KV_COMPOSITION_SHA256'),('source_hashes','_verify_raw_kv_composition','_raw_kv_mode'),dict(ROOT=root,prior=prior,require=base.require,file_sha=base.file_sha))
assert entry.source_hashes(fresh_profile=True,enable_raw_kv=True)==expected
print('SOURCE_CLOSURE_ONLY',len(expected),len(r.contract_snapshot(composed=True)['generated']))
'''
            result=subprocess.run([sys.executable,'-B','-c',script],cwd=tree,text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('SOURCE_CLOSURE_ONLY',result.stdout)

if __name__=='__main__':unittest.main()

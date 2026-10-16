"""Cold final-source closure and linked authorization rejection tests."""
import ast
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from . import launch as r,prepare

class PreparationTests(unittest.TestCase):
    def test_contract_and_fresh_twelve_output_composition(self):
        frozen=r.contract_snapshot()
        self.assertEqual(len(frozen['sources']),r.SOURCE_COUNT)
        self.assertEqual(len(frozen['generated']),12)
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'out';result=prepare.prepare(out)
            self.assertEqual(result['generated'],frozen['generated'])
            with self.assertRaises(ValueError):prepare.prepare(out)

    def test_contract_rejects_budget_scope_types_and_helper_drift(self):
        raw,value=r.contract_value();reader=r.read_source
        for key, replacement in [('rows',True),('total_budget',3421),('profile','foreign'),('source_sha256',{}),('generated_sha256',{})]:
            v=copy.deepcopy(value);v[key]=replacement
            with self.subTest(key=key),patch.object(r,'read_source',side_effect=lambda n,limit=4194304:json.dumps(v).encode() if n==r.CONTRACT else reader(n,limit)),self.assertRaises(ValueError):r.contract_value()

    def test_original_or_unlinked_snapshot_never_authorizes(self):
        for value in ({},{'rows':True},{'rows':128,'enable_raw_kv':True,'fresh_profile':True,'m128_launch':{}}, {'rows':128,'enable_raw_kv':True,'fresh_profile':True,r.SNAPSHOT_KEY:{}}):
            with self.subTest(value=value),self.assertRaises(ValueError):r.authorize_run(value,wall_budget=2400,enable_raw_kv=True,fresh_profile=True)

    def test_linked_snapshot_requires_exact_current_receipt_and_source(self):
        from . import admission
        sources={'fixed.py':'b'*64};frozen=dict(sources=sources,contract_sha256='c'*64)
        identity=SimpleNamespace(checkout_commit='a'*40,receipt_sha256='d'*64,manifest=Path('/private/assets/ASSETS.json'),manifest_sha256='e'*64,source_sha256=sources)
        snapshot=dict(rows=128,enable_raw_kv=True,fresh_profile=True,source_sha256=sources,
            source_manifest_sha256=r.sha((json.dumps(sources,sort_keys=True,indent=2)+'\n').encode()),
            fresh_assets=dict(profile=r.ASSET_PROFILE,manifest=str(identity.manifest),manifest_sha256=identity.manifest_sha256,enable_raw_kv=True),
            independent_reference=dict(rows=128,past_tokens=0))
        context=dict(contract_sha256=frozen['contract_sha256'],checkout_commit=identity.checkout_commit)
        with patch.object(r,'contract_snapshot',return_value=frozen),patch.object(admission,'revalidate'),patch.object(admission,'verify_setup',return_value=identity):
            linked=r.bind_snapshot(snapshot,identity,context)
            self.assertIs(r.authorize_run(linked,wall_budget=2400,enable_raw_kv=True,fresh_profile=True),identity)
            for key,value in [('setup_receipt_sha256','0'*64),('launch_contract_sha256','0'*64),('profile','old')]:
                changed=copy.deepcopy(linked);changed[r.SNAPSHOT_KEY][key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):r.authorize_run(changed,wall_budget=2400,enable_raw_kv=True,fresh_profile=True)
            for budget in (True,2401,float('nan')):
                with self.assertRaises(ValueError):r.authorize_run(linked,wall_budget=budget,enable_raw_kv=True,fresh_profile=True)

    def test_bridge_rejects_every_nonimport_change(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'base';prepare.previous.prepare(out)
            before={n:(r.ROOT/n).read_bytes() if n in r.HELPERS else (out/n).read_bytes() for n in r.TARGETS}
            after={n:prepare.rewrite(n,raw) for n,raw in before.items()}
            prepare.check_bridge_scope(before,after)
            for name in r.TARGETS:
                changed=dict(after);changed[name]+=b'\ndef unreviewed_callback(): return 1\n'
                with self.assertRaises(ValueError):prepare.check_bridge_scope(before,changed)

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
from candidates.qwen2_resident_matrix.raw_kv_public_recipe_run import launch as r
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

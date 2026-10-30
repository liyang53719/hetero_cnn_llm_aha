import ast,json,pathlib,tempfile,types,unittest
from unittest.mock import patch
import connect_owned as c,consumer_owned as consumer
D=pathlib.Path(__file__).resolve().parent
class T(unittest.TestCase):
 def test_source_guard_new_closure(self):c.source_guard()
 def test_configured_module_exact_environment(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);cache=root/'cache';cache.mkdir();paths={}
   for key in ('HOME','TMPDIR','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME','TORCH_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR'):
    q=cache/key.lower();q.mkdir();paths[key]=str(q)
   identity=dict(run_id=7,source_commit='a'*40,launch_commit='b'*40);p=root/'ENV.json';p.write_text(json.dumps(dict(schema='OWNED_EXECUTION_ENVIRONMENT_V1',identity=identity,owner_root=str(root),watched_roots=[str(root)],cache_root=str(cache),cache_paths=paths)))
   consumer.OWNED_ENVIRONMENT=(p,consumer.sha(p),identity);m=consumer.runtime_abi_module();self.assertEqual(m.clean_env()['HOME'],paths['HOME']);self.assertEqual(set(m.clean_env()),set(paths)|{'PATH','LANG','LC_ALL','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'})
 def test_generated_owned_argv_contract(self):
  tree=ast.parse((D/'connect_owned.py').read_text());connect=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='connect');strings={x.value for x in ast.walk(connect)if isinstance(x,ast.Constant)and isinstance(x.value,str)}
  self.assertIn('--strict-outer-supervised',strings);self.assertIn('consumer_owned.py',strings);self.assertIn('--owned-environment',strings);self.assertIn('--owned-environment-sha256',strings)
if __name__=='__main__':unittest.main()

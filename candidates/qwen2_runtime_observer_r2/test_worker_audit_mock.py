"""Execute worker audit functions with mock module validation, no worker import/job."""
import ast,hashlib,json,os,resource,signal,sys,tempfile,time,types,unittest
from importlib.machinery import ModuleSpec
from pathlib import Path
from unittest.mock import patch
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(20,20));signal.alarm(25)
HERE=Path(__file__).resolve().parent
need=lambda ok,msg:None if ok else (_ for _ in ()).throw(ValueError(msg))
ns=dict(Path=Path,json=json,os=os,sys=sys,types=types,ModuleSpec=ModuleSpec,time=time,HERE=HERE,need=need,digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest())
tree=ast.parse((HERE/'worker.py').read_text());names={'audit_runtime','verify_maps','emit'};nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
if {n.name for n in nodes}!=names:raise ValueError('missing worker audit functions')
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(HERE/'worker.py'),'exec'),ns)
class WorkerAudit(unittest.TestCase):
    def run_failure(self,root,extra=None):
        failures=[{'module':'missing_one','code':'unknown_path'},{'module':'missing_two','code':'unknown_path'}]
        ns['collect_modules']=lambda *a,**k:dict(status='FAIL',failures=failures)
        def persist(report,path):
            with path.open('x') as f:json.dump(report,f)
            raise ValueError('two module differences')
        ns['persist_and_validate']=persist
        fake=types.ModuleType('runtime_observer');fake.load_observer=lambda:None
        added={'runtime_observer':fake};added.update(extra or {})
        with patch.dict(sys.modules,added):
            with self.assertRaisesRegex(ValueError,'complete module/maps evidence preserved'):
                ns['audit_runtime']({'files':{},'namespace_packages':{},'registered_module_objects':{},'mapping_allowlist':[]},root,'MOCK')
        d=root/'RUNTIME_MOCK'
        for name in ('MAPS_RAW.txt','MODULES_RAW.json','MODULE_AUDIT.json','MAPS_BEFORE_AUDIT.txt','MAP_AUDIT.json','SUMMARY.json'):self.assertTrue((d/name).is_file(),name)
        self.assertEqual(len(json.loads((d/'MODULE_AUDIT.json').read_text())['failures']),2)
        maps=json.loads((d/'MAP_AUDIT.json').read_text());self.assertGreater(len(maps['failures']),0)
        self.assertTrue(all('sha256' not in r for r in maps['failures']))
        self.assertEqual({r['audit'] for r in json.loads((d/'SUMMARY.json').read_text())['errors']},{'modules','maps'})
        return json.loads((d/'MODULES_RAW.json').read_text())
    def test_all_module_and_mapping_failures_saved_before_rejection(self):
        with tempfile.TemporaryDirectory() as d:self.run_failure(Path(d))
    def test_bad_spec_and_dynamic_getattr_do_not_break_snapshot(self):
        m=types.ModuleType('broken');m.__spec__=42
        def forbidden(name):raise AssertionError('module getattr executed')
        m.__getattr__=forbidden
        with tempfile.TemporaryDirectory() as d:
            rows=self.run_failure(Path(d),{'broken':m})
            self.assertEqual(next(r for r in rows if r['name']=='broken')['unexpected_spec_type'],'int')
    def test_no_task_or_numpy_loaded(self):
        self.assertNotIn('numpy',sys.modules)
        self.assertFalse(any(n.startswith('candidates.qwen2_resident_matrix') for n in sys.modules))
if __name__=='__main__':unittest.main()

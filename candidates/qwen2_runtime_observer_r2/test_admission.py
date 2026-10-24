"""Cold AST/mock gates only. No worker import, CDLL, job, or reference run."""
import ast,copy,hashlib,importlib.util,json,os,resource,signal,sys,tempfile,time,unittest
from pathlib import Path
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(20,20));signal.alarm(25)
HERE=Path(__file__).resolve(strict=True).parent
spec=importlib.util.spec_from_file_location('_prepared_admission',HERE/'admission.py');ad=importlib.util.module_from_spec(spec);spec.loader.exec_module(ad)
NAMES={'admission.py','harness.py','worker.py','launch.py','runtime_closure.py','runtime_observer.py','reference_capture.py','module_inventory.py','cold_import.py','run_cold.py'}
need=lambda ok,message:None if ok else (_ for _ in ()).throw(ValueError(message))
ns={'Path':Path,'hashlib':hashlib,'json':json,'os':os,'sys':sys,'time':time,'need':need,'digest':ad.sha}
for file,names in [('worker.py',{'Isolation','verify_maps','emit'}),('launch.py',{'claim'}),('harness.py',{'compare_fields'})]:
    tree=ast.parse((HERE/file).read_text());nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
    if {n.name for n in nodes}!=names:raise ValueError('missing mock definition')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(HERE/file),'exec'),ns)
def fixture(root):
    pins={}
    for name in NAMES:p=root/name;p.write_text('pass\n');pins[name]=ad.sha(p)
    c=root/'config.json';c.write_text(json.dumps({'files':{str(root/n):{'sha256':h} for n,h in pins.items()}}))
    r=root/'review.json';r.write_text(json.dumps(dict(status='PASS_STATIC_REVIEW_REQUIRES_ROOT_EXECUTION_AUTHORIZATION',config_sha256=ad.sha(c),limits=dict(cpus=1,address_space_bytes=1<<30,cpu_seconds=30,wall_seconds=45),executable_sources=pins)))
    return c,r,ad.sha(r)
class Admission(unittest.TestCase):
    def test_exact_review(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,r,h=fixture(root);ad.validate_review(c,r,h,root)
    def test_one_config_byte_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,r,h=fixture(root);c.write_bytes(c.read_bytes()+b' ')
            with self.assertRaises(ValueError):ad.validate_review(c,r,h,root)
    def test_changed_review_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,r,h=fixture(root);r.write_bytes(r.read_bytes()+b' ')
            with self.assertRaises(ValueError):ad.validate_review(c,r,h,root)
    def test_changed_executable_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,r,h=fixture(root);(root/'runtime_observer.py').write_text('changed')
            with self.assertRaises(ValueError):ad.validate_review(c,r,h,root)
    def test_missing_reference_executable_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,r,h=fixture(root);v=json.loads(r.read_text());del v['executable_sources']['reference_capture.py'];r.write_text(json.dumps(v))
            with self.assertRaises(ValueError):ad.validate_review(c,r,ad.sha(r),root)
    def guard(self):return ns['Isolation']({'elf':'/allowed/matrix.so','files':{},'inputs':{k:{'path':'/inputs/'+k+'.f32le'} for k in ('qr','kr','v')},'oracle_harness':'/ref/oracle.py','exact_helper':'/shared/exact.py','buffer_source':'/shared/capture.py','reference_sources':{'oracle':{'path':'/ref/oracle.py'},'helper':{'path':'/shared/exact.py'},'buffer':{'path':'/shared/capture.py'}}})
    def test_reference_before_terminal_rejected(self):
        with self.assertRaises(ValueError):self.guard().audit('open',('/ref/oracle.py','r',0))
    def test_shared_primitive_source_allowed(self):self.guard().audit('open',('/shared/exact.py','r',0))
    def test_shared_nonarithmetic_buffer_source_allowed(self):self.guard().audit('open',('/shared/capture.py','r',0))
    def test_foreign_tensor_rejected(self):
        with self.assertRaises(ValueError):self.guard().audit('open',('/ref/output.f32le','r',0))
    def test_reference_only_after_terminal(self):
        g=self.guard();g.terminal=True;g.audit('open',('/ref/oracle.py','r',0))
    def test_unknown_library_rejected_without_loading(self):
        with self.assertRaises(ValueError):self.guard().audit('ctypes.dlopen',('/bad/other.so',))
    def test_unknown_nonelf_mapping_saved_before_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);f=root/'locale';f.write_bytes(b'locale');st=f.stat();raw='100-200 r--p 0000 %x:%x %d %s\n'%(os.major(st.st_dev),os.minor(st.st_dev),st.st_ino,f)
            with self.assertRaises(ValueError):ns['verify_maps']({'files':{}},root,raw)
            self.assertEqual((root/'MAPS_BEFORE_AUDIT.txt').read_text(),raw)
            self.assertFalse(json.loads((root/'MAP_AUDIT.json').read_text())['mappings'][0]['elf'])
    def test_multiple_unknown_mappings_reported_together(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=''
            for name in ('one','two'):
                f=root/name;f.write_bytes(b'private-not-read');st=f.stat()
                raw+='100-200 r--p 0000 %x:%x %d %s\n'%(os.major(st.st_dev),os.minor(st.st_dev),st.st_ino,f)
            with self.assertRaises(ValueError):ns['verify_maps']({'files':{},'mapping_allowlist':[]},root,raw)
            report=json.loads((root/'MAP_AUDIT.json').read_text())
            self.assertEqual(len(report['failures']),2)
            self.assertTrue(all('sha256' not in r and 'contents not read' in r['error'] for r in report['failures']))
    def test_pinned_payload_not_a_runtime_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);f=root/'qr.f32le';f.write_bytes(b'input');st=f.stat()
            raw='100-200 r--p 0000 %x:%x %d %s\n'%(os.major(st.st_dev),os.minor(st.st_dev),st.st_ino,f)
            config={'files':{str(f):{'bytes':5,'sha256':ad.sha(f)}},'mapping_allowlist':[]}
            with self.assertRaises(ValueError):ns['verify_maps'](config,root,raw)
            self.assertNotIn('sha256',json.loads((root/'MAP_AUDIT.json').read_text())['failures'][0])
    def test_one_use_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'config';c.write_text('{}');ns['claim'](c,1,'hash',Path(d)/'out')
            with self.assertRaises(FileExistsError):ns['claim'](c,1,'hash',Path(d)/'again')
    def test_m2_without_m1_refused(self):
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'config';c.write_text('{}')
            with self.assertRaises(FileNotFoundError):ns['claim'](c,2,'hash',Path(d)/'out')
    def fields(self):
        names=('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16')
        return {n:dict(shape=(1,),observed=bytearray([1]),words=[0]) for n in names}
    def test_ten_field_words_exact(self):self.assertTrue(ns['compare_fields'](self.fields(),self.fields()))
    def test_field_bit_mismatch_rejected(self):
        a=self.fields();b=self.fields();b['scores_bf16']['words'][0]=1
        with self.assertRaises(ValueError):ns['compare_fields'](a,b)
        self.assertEqual(a['scores_bf16']['words'],[0])
    def test_missing_field_not_filled(self):
        a=self.fields();b=self.fields();del a['dot_parts']
        with self.assertRaises(ValueError):ns['compare_fields'](a,b)
        self.assertNotIn('dot_parts',a)
    def test_missing_observation_rejected(self):
        a=self.fields();b=self.fields();a['dot_parts']['observed'][0]=0
        with self.assertRaises(ValueError):ns['compare_fields'](a,b)
    def test_no_native_oracle_modules_imported(self):
        self.assertNotIn('numpy',sys.modules);self.assertNotIn('worker',sys.modules)
        self.assertFalse(any(n.startswith('candidates.qwen2_resident_matrix') for n in sys.modules))
if __name__=='__main__':unittest.main()

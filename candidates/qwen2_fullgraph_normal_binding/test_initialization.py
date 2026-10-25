"""Synthetic module/type/maps fixtures, not actual native initialization."""
import copy,importlib.machinery
from pathlib import Path
import sys,tempfile,types,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import initialization as gate
if Path(gate.__file__).resolve()!=HERE/'initialization.py':raise RuntimeError('foreign gate')
class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.elf=self.root/'yaml/_yaml.cpython-312-x86_64-linux-gnu.so';self.pin='a'*64
  y=types.ModuleType('yaml');y.__file__=str(self.root/'yaml/__init__.py');y.__with_libyaml__=True
  c=types.ModuleType('yaml.cyaml');c.__file__=str(self.root/'yaml/cyaml.py')
  native=types.ModuleType('yaml._yaml');loader=importlib.machinery.ExtensionFileLoader('yaml._yaml',str(self.elf));native.__file__=str(self.elf);native.__loader__=loader;native.__spec__=importlib.machinery.ModuleSpec('yaml._yaml',loader,origin=str(self.elf))
  meta=type('_common_types_metatype',(type,),{'__module__':'_cython_3_1_4'});fntype=meta('cython_function_or_method',(),{'__module__':'_cython_3_1_4'})
  shared=types.ModuleType('_cython_3_1_4');shared.cython_function_or_method=fntype;shared._common_types_metatype=meta
  runtime=types.ModuleType('cython_runtime');runtime.cline_in_traceback=True
  for name in ('get_version','get_version_string'):
   fn=fntype();fn.__module__='yaml._yaml';fn.__globals__=vars(native);setattr(native,name,fn)
  self.modules={'yaml':y,'yaml.cyaml':c,'yaml._yaml':native,'cython_runtime':runtime,'_cython_3_1_4':shared}
  self.before={name:False for name in gate.NAMES};self.events=[{'module':'yaml._yaml','origin':str(self.elf)}]
  self.maps={'mappings':[{'path':str(self.elf),'match':True,'sha256':self.pin,'reasons':[]}]}
  self.audit={'modules':[{'name':n,'object_id':hex(id(self.modules[n])),'errors':[{'code':'unregistered_no_file_module','detail':n}]} for n in gate.NAMES], 'failures':[{'name':n,'code':'unregistered_no_file_module','detail':n} for n in gate.NAMES]}
  self.targets={f'role{i}':f'module{i}' for i in range(15)}
  methods=('acquire','accept_group','accept_step','retire_result','retire_done','retire_legacy_reply','retire_owner_response','release','abort')
  service={n:{'class':'OfficialMatrixService' if n=='acquire' else 'MatrixService','method':n,'normal_source_bound':True} for n in methods}
  self.old={'status':'FAIL_NORMAL_BINDING','binding':{'module_targets':self.targets},'service_binding':service,'blocked':[], 'errors':[{'gate':'modules','qualification':{'remaining_failures':copy.deepcopy(self.audit['failures'])}}]}
 def tearDown(self):self.temp.cleanup()
 def qualify(self):return gate.qualify(self.modules,self.before,self.events,self.root,self.pin,self.maps,self.audit)
 def whole(self):return gate.whole_result(self.old,self.qualify(),self.audit,self.targets)
 def test_bounded_association(self):self.assertFalse(self.qualify()['internal_c_creation_call_observed'])
 def test_complete_roles_methods(self):self.assertEqual(self.whole()['status'],'PASS_NORMAL_FULLGRAPH_BINDING_ONLY')
 def test_preexisting_cython(self):
  self.before['cython_runtime']=True
  with self.assertRaisesRegex(ValueError,'preexisting'):self.qualify()
 def test_missing_import_event(self):
  self.events=[]
  with self.assertRaisesRegex(ValueError,'import not observed'):self.qualify()
 def test_foreign_import_event(self):
  self.events=[{'module':'yaml._yaml','origin':'/foreign.so'}]
  with self.assertRaisesRegex(ValueError,'import origin'):self.qualify()
 def test_only_none_import_event(self):
  self.events=[{'module':'yaml._yaml','origin':None}]
  with self.assertRaisesRegex(ValueError,'import origin'):self.qualify()
 def test_mixed_foreign_import_event(self):
  self.events.append({'module':'yaml._yaml','origin':'/foreign.so'})
  with self.assertRaisesRegex(ValueError,'import origin'):self.qualify()
 def test_silent_pure_python_fallback(self):
  self.modules['yaml'].__with_libyaml__=False
  with self.assertRaisesRegex(ValueError,'fallback'):self.qualify()
 def test_missing_extension_map(self):
  self.maps['mappings']=[]
  with self.assertRaisesRegex(ValueError,'map missing'):self.qualify()
 def test_changed_extension_map_hash(self):
  self.maps['mappings'][0]['sha256']='b'*64
  with self.assertRaisesRegex(ValueError,'map missing'):self.qualify()
 def test_foreign_loader(self):
  self.modules['yaml._yaml'].__loader__=None
  with self.assertRaisesRegex(ValueError,'loader'):self.qualify()
 def test_foreign_yaml_origin(self):
  self.modules['yaml'].__file__='/foreign/yaml.py'
  with self.assertRaisesRegex(ValueError,'source origin'):self.qualify()
 def test_replaced_canonical_object(self):
  self.modules['cython_runtime']=types.ModuleType('cython_runtime')
  with self.assertRaisesRegex(ValueError,'object differs'):self.qualify()
 def test_wrong_module_name(self):
  self.modules['cython_runtime'].__name__='foreign'
  with self.assertRaisesRegex(ValueError,'metadata differs'):self.qualify()
 def test_foreign_runtime_member(self):
  self.modules['cython_runtime'].foreign=lambda:None
  with self.assertRaisesRegex(ValueError,'foreign Cython runtime'):self.qualify()
 def test_nonstring_cython_member_name_rejected(self):
  vars(self.modules['cython_runtime'])[17]=object()
  with self.assertRaisesRegex(ValueError,'non-string'):self.qualify()
 def test_nonboolean_cline(self):
  self.modules['cython_runtime'].cline_in_traceback=1
  with self.assertRaisesRegex(ValueError,'foreign Cython runtime'):self.qualify()
 def test_foreign_shared_member(self):
  self.modules['_cython_3_1_4'].foreign=object()
  with self.assertRaisesRegex(ValueError,'foreign Cython shared'):self.qualify()
 def test_export_type_not_shared(self):
  self.modules['yaml._yaml'].get_version=lambda:None
  with self.assertRaisesRegex(ValueError,'dictionary export type not linked'):self.qualify()
 def test_internal_globals_value_not_claimed(self):
  self.modules['yaml._yaml'].get_version.__globals__={}
  result=self.qualify()
  self.assertFalse(result['function_globals_descriptor_evaluated'])
  self.assertFalse(result['function_internal_globals_identity_claimed'])
 def test_third_nofile_rejected(self):
  self.audit['failures'].append({'name':'unknown','code':'unregistered_no_file_module'})
  with self.assertRaisesRegex(ValueError,'additional module'):self.whole()
 def test_normal_import_exception_not_swallowed(self):
  self.old['errors'].append({'gate':'normal_import','error':'broken'})
  with self.assertRaisesRegex(ValueError,'non-Cython'):self.whole()
 def test_guard_task_violation_rejected(self):
  self.old['blocked']=[{'kind':'task_execution_forbidden'}]
  with self.assertRaisesRegex(ValueError,'non-cache'):self.whole()
 def test_missing_role(self):
  self.old['binding']['module_targets']={}
  with self.assertRaisesRegex(ValueError,'15 runtime roles'):self.whole()
 def test_missing_method(self):
  self.old['service_binding'].pop('acquire')
  with self.assertRaisesRegex(ValueError,'nine source'):self.whole()
 def test_wrong_acquire_class(self):
  self.old['service_binding']['acquire']['class']='MatrixService'
  with self.assertRaisesRegex(ValueError,'inheritance'):self.whole()
 def test_mapping_failure_not_swallowed(self):
  self.old['errors'].append({'gate':'maps','failures':['unknown']})
  with self.assertRaisesRegex(ValueError,'non-Cython'):self.whole()
 def test_old_report_unchanged(self):
  before=copy.deepcopy(self.old);self.whole();self.assertEqual(before,self.old)
if __name__=='__main__':unittest.main()

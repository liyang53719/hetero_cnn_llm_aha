"""Offline descriptor/type fixtures only, not an actual Cython runtime PASS."""
import json
from pathlib import Path
import sys,types,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import safe_metadata as safe
if Path(safe.__file__).resolve()!=HERE/'safe_metadata.py':raise RuntimeError('foreign safe_metadata')
class Tests(unittest.TestCase):
 def test_real_getset_descriptor_is_recorded_without_evaluation(self):
  d=type.__dict__['__module__'];self.assertIs(type(d),types.GetSetDescriptorType)
  self.assertEqual(safe.value_record(d)['builtin_kind'],'getset_descriptor')
 def test_same_failure_shape_metatype(self):
  meta=type('MetadataMeta',(type,),{'__module__':type.__dict__['__module__']})
  item=meta('Item',(),{})
  self.assertIs(type(type(item).__module__),types.GetSetDescriptorType)
  value=safe.value_record(item);self.assertEqual(value['type_object_id'],hex(id(meta)))
  json.dumps(value)
 def test_metadata_getters_not_called(self):
  touched=[]
  class Meta(type):
   def __getattribute__(self,name):
    if name in ('__module__','__qualname__','__name__','__globals__'):
     touched.append(name);raise RuntimeError('metadata getter invoked')
    return type.__getattribute__(self,name)
   def __repr__(self):raise RuntimeError('repr called')
   def __str__(self):raise RuntimeError('str called')
  class Value(metaclass=Meta):pass
  json.dumps(safe.value_record(Value));self.assertEqual(touched,[])
 def test_unknown_instance_hooks_not_called(self):
  class Unknown:
   def __getattribute__(self,name):raise RuntimeError('getattr called')
   def __str__(self):raise RuntimeError('str called')
   def __repr__(self):raise RuntimeError('repr called')
  json.dumps(safe.value_record(Unknown()))
 def test_descriptor_get_not_called(self):
  class Descriptor:
   def __get__(self,instance,owner):raise RuntimeError('descriptor evaluated')
  m=types.ModuleType('fixture');m.member=Descriptor()
  self.assertEqual(safe.snapshot({'fixture':m},['fixture'])[0]['errors'],[])
 def test_all_builtin_descriptor_categories(self):
  class Slots:__slots__=('x',)
  values=[type.__dict__['__module__'],Slots.__dict__['x'],str.upper,object.__str__,len,lambda:None]
  kinds=[safe.value_record(v)['builtin_kind'] for v in values]
  self.assertEqual(kinds,['getset_descriptor','member_descriptor','method_descriptor','wrapper_descriptor','builtin_function','python_function'])
 def test_scalar_only_known_exact_types(self):
  class S(str):
   def __str__(self):raise RuntimeError('str called')
  self.assertNotIn('scalar',safe.value_record(S('x')))
  self.assertEqual(safe.value_record('x')['scalar'],'x')
 def test_nonstring_member_key_preserved_by_id(self):
  m=types.ModuleType('fixture');vars(m)[17]=object()
  row=safe.snapshot({'fixture':m},['fixture'])[0]
  self.assertTrue(any(v['name'] is None and v['name_metadata']['builtin_kind']=='int' for v in row['members']))
 def test_unknown_module_subclass_not_dereferenced(self):
  class M(types.ModuleType):
   def __getattribute__(self,name):raise RuntimeError('module getter called')
  result=safe.snapshot({'fixture':M('fixture')},['fixture'])
  self.assertEqual(result[0]['members'],[])
 def test_missing_module_recorded(self):self.assertFalse(safe.snapshot({},['missing'])[0]['present'])
 def test_cycles_not_walked(self):
  d={};d['self']=d;m=types.ModuleType('fixture');m.cycle=d
  json.dumps(safe.snapshot({'fixture':m},['fixture']))
 def test_all_requested_modules_recorded_before_validation(self):
  a=types.ModuleType('a');b=types.ModuleType('b');a.bad=type.__dict__['__module__'];b.ok=True
  rows=safe.snapshot({'a':a,'b':b},['a','missing','b']);self.assertEqual(len(rows),3);json.dumps(rows)
 def test_no_dynamic_attribute_source_calls(self):
  import ast
  tree=ast.parse((HERE/'safe_metadata.py').read_text())
  funcs={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
  self.assertFalse(funcs & {'getattr','str','repr','isinstance'})
 def test_unknown_exception_not_formatted(self):
  class Error(Exception):
   def __str__(self):raise RuntimeError('exception str called')
   def __repr__(self):raise RuntimeError('exception repr called')
  json.dumps(safe.value_record(Error()))
 def test_ids_link_members_and_native_export_types(self):
  class Shared:pass
  fn=Shared();m=types.ModuleType('fixture');m.shared=Shared;m.export=fn
  rows=safe.snapshot({'fixture':m},['fixture'])[0]['members'];values={r['name']:r['value'] for r in rows}
  self.assertEqual(values['shared']['object_id'],values['export']['type_object_id'])
if __name__=='__main__':unittest.main()

import argparse,ast,hashlib,importlib.util,json,os,pathlib,tempfile,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('owned_abi',D/'runtime_abi_owned.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASE=D/'runtime_abi.py'
def normalized_workspace(test,text):
 tree=ast.parse(text);functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
 baseline={n.name:n for n in ast.parse(BASE.read_text()).body if isinstance(n,ast.FunctionDef)}
 dump=lambda node:ast.dump(node,include_attributes=False)
 for name,call in [('prepare','prepare_workspace(binary,binary_sha,tool_manifest,tool_sha,out)'),('verify','verify_workspace(receipt,receipt_sha,binary,binary_sha,tool_manifest,tool_sha)')]:
  f=functions[name];expected=ast.parse('if _WORKSPACE_LOADER_BINDING is not None:return '+call).body[0]
  test.assertEqual(dump(f.body[0]),dump(expected));f.body=f.body[1:]
 f=functions['_list'];test.assertEqual([x.arg for x in f.args.args],['loader','binary','workspace_prefix']);test.assertEqual(list(map(dump,f.args.defaults)),[dump(ast.Constant(None))]);f.args=baseline['_list'].args
 calls=[n for n in ast.walk(f)if isinstance(n,ast.Call)and ast.unparse(n.func)=='subprocess.Popen'];test.assertEqual(len(calls),1)
 expected=ast.parse("[str(loader),'--list',str(binary)]if workspace_prefix is None else [*workspace_prefix,'--list',str(binary)]",mode='eval').body
 test.assertEqual(dump(calls[0].args[0]),dump(expected));calls[0].args[0]=expected.body
 f=functions['elf_info'];test.assertEqual([x.arg for x in f.args.args],['path','require_interpreter']);test.assertEqual(list(map(dump,f.args.defaults)),[dump(ast.Constant(True))]);f.args=baseline['elf_info'].args
 test.assertEqual(dump(f.body[0]),dump(ast.parse("need(type(require_interpreter)is bool,'explicit interpreter policy')").body[0]));f.body=f.body[1:]
 block=next(n for n in f.body if isinstance(n,ast.With));oldblock=next(n for n in baseline['elf_info'].body if isinstance(n,ast.With))
 expected=ast.parse("""
interp=[q for q in ph if q[0]==3];need(len(interp)==1 if require_interpreter else len(interp)<=1,'bounded PT_INTERP count');loader=None
if interp:
 need(1<interp[0][5]<=4096,'bounded PT_INTERP');text=read(interp[0][2],interp[0][5]);need(text.endswith(b'\\0')and text.count(b'\\0')==1,'interpreter string');loader=text[:-1].decode('ascii');need(loader in INTERPRETERS,'reviewed system interpreter only')
""").body
 def index(body,name):return next(i for i,n in enumerate(body)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id==name for t in n.targets))
 start=index(block.body,'interp');stop=index(block.body,'dyn');test.assertEqual(list(map(dump,block.body[start:stop])),list(map(dump,expected)))
 oldstart=index(oldblock.body,'interp');oldstop=index(oldblock.body,'dyn');block.body[start:stop]=oldblock.body[oldstart:oldstop]
 calls=[n for n in ast.walk(f)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='need'and len(n.args)==2 and isinstance(n.args[1],ast.Constant)and n.args[1].value=='needed dependency count'];test.assertEqual(len(calls),1)
 expected=ast.parse('(0<len(names)if require_interpreter else 0<=len(names))and len(names)<=32 and len(set(names))==len(names)',mode='eval').body
 test.assertEqual(dump(calls[0].args[0]),dump(expected));calls[0].args[0]=ast.parse('0<len(names)<=32 and len(set(names))==len(names)',mode='eval').body
 f=functions['parse_list'];test.assertEqual([x.arg for x in f.args.args],['text','expected_interpreter']);test.assertEqual(list(map(dump,f.args.defaults)),[dump(ast.Constant(None))]);f.args=baseline['parse_list'].args
 test.assertEqual(dump(f.body[0]),dump(ast.parse("need(expected_interpreter is None or expected_interpreter in INTERPRETERS,'explicit reviewed PT_INTERP alias')").body[0]));f.body=f.body[1:]
 loop=next(n for n in f.body if isinstance(n,ast.For));oldloop=next(n for n in baseline['parse_list'].body if isinstance(n,ast.For))
 branch=next(n for n in loop.body if isinstance(n,ast.If)and isinstance(n.test,ast.Name)and n.test.id=='m')
 oldbranch=next(n for n in oldloop.body if isinstance(n,ast.If)and isinstance(n.test,ast.Name)and n.test.id=='m')
 expected=ast.parse(r"""
alias=re.fullmatch(r'(/[^\s]+) => (/[^\s]+) \(0x[0-9a-f]+\)',line)
if alias is not None:
 need(expected_interpreter is not None and alias[1]==expected_interpreter,'only actual workspace PT_INTERP alias')
 key=P(expected_interpreter).name;path=alias[2]
else:
 m=re.fullmatch(r'(/[^\s]+) \(0x[0-9a-f]+\)',line);need(m is not None,'unknown/unresolved loader output');path=m[1];key=P(path).name
""").body
 test.assertEqual(list(map(dump,branch.orelse)),list(map(dump,expected)));branch.orelse=oldbranch.orelse
 return tree

class T(unittest.TestCase):
 def setUp(self):m._OWNED_ENV_BINDING=None
 def fixture(self,t):
  root=pathlib.Path(t);cache=root/'cache';cache.mkdir();paths={}
  for k in m.CACHE_NAMES:p=cache/k.lower();p.mkdir();paths[k]=str(p)
  ident=dict(run_id=1,source_commit='a'*40,launch_commit='b'*40)
  doc=dict(schema='OWNED_EXECUTION_ENVIRONMENT_V1',identity=ident,owner_root=str(root),watched_roots=[str(root)],cache_root=str(cache),cache_paths=paths)
  p=root/'ENV.json';p.write_text(json.dumps(doc));return p,m.sha(p),ident,doc
 def test_only_base_plus_explicit_caches(self):
  with tempfile.TemporaryDirectory()as t:
   p,h,i,d=self.fixture(t)
   with patch.dict(os.environ,{'LD_PRELOAD':'/bad','PYTHONPATH':'/bad','GITHUB_TOKEN':'not-secret','HOME':'/outside'},clear=False):
    m.configure_owned_environment(p,h,i);env=m.clean_env()
   self.assertEqual(set(env),{'PATH','LANG','LC_ALL','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'}|set(m.CACHE_NAMES));self.assertEqual(env['HOME'],d['cache_paths']['HOME']);self.assertEqual(m.owned_environment_pin()['sha256'],h)
 def test_unconfigured_reject(self):
  with self.assertRaises(ValueError):m.clean_env()
 def test_wrong_identity(self):
  with tempfile.TemporaryDirectory()as t:
   p,h,i,d=self.fixture(t)
   with self.assertRaises(ValueError):m.configure_owned_environment(p,h,dict(i,run_id=2))
 def test_tamper_contract(self):
  with tempfile.TemporaryDirectory()as t:
   p,h,i,d=self.fixture(t);m.configure_owned_environment(p,h,i);p.write_text('{}')
   with self.assertRaises(ValueError):m.clean_env()
 def test_alias_after_configuration(self):
  with tempfile.TemporaryDirectory()as t:
   p,h,i,d=self.fixture(t);m.configure_owned_environment(p,h,i);q=pathlib.Path(d['cache_paths']['TMPDIR']);q.rmdir();q.symlink_to('/tmp')
   with self.assertRaises(ValueError):m.clean_env()
 def test_unwatched_cache(self):
  with tempfile.TemporaryDirectory()as t:
   p,h,i,d=self.fixture(t);other=pathlib.Path(t)/'other';other.mkdir();d['watched_roots']=[str(other)];p.write_text(json.dumps(d))
   with self.assertRaises(ValueError):m.configure_owned_environment(p,m.sha(p),i)
 def test_unknown_environment_field(self):
  with tempfile.TemporaryDirectory()as t:
   p,h,i,d=self.fixture(t);d['cache_paths']['LD_LIBRARY_PATH']='/bad';p.write_text(json.dumps(d))
   with self.assertRaises(ValueError):m.configure_owned_environment(p,m.sha(p),i)
 def test_preserve_parser_and_library_checks(self):
  old={n.name:ast.dump(n,include_attributes=False)for n in ast.parse(BASE.read_text()).body if isinstance(n,ast.FunctionDef)}
  new={n.name:ast.dump(n,include_attributes=False)for n in normalized_workspace(self,(D/'runtime_abi_owned.py').read_text()).body if isinstance(n,ast.FunctionDef)}
  for name in old:
   if name not in ('clean_env','prepare','verify','_list'):self.assertEqual(old[name],new[name],name)
 def test_only_declared_abi_deltas(self):
  old={n.name:ast.dump(n,include_attributes=False)for n in ast.parse(BASE.read_text()).body if isinstance(n,ast.FunctionDef)}
  text=(D/'runtime_abi_owned.py').read_text().replace("SAME_JOB_ELF_STARTUP_ABI_OWNED_ENV_V2","SAME_JOB_ELF_STARTUP_ABI_V1").replace("owned_environment=owned_environment_pin(),","").replace("r['owned_environment']==owned_environment_pin()and r['environment']==clean_env(),'same pinned owned execution environment contract'","r['environment']==clean_env(),'clean execution environment contract'").replace("tempfile.TemporaryFile(dir=clean_env()['TMPDIR'])","tempfile.TemporaryFile()")
  new={n.name:ast.dump(n,include_attributes=False)for n in normalized_workspace(self,text).body if isinstance(n,ast.FunctionDef)}
  for name in ('prepare','verify','_list'):self.assertEqual(old[name],new[name],name)
 def test_loader_mock_uses_owned_temp_and_env(self):
  with tempfile.TemporaryDirectory()as t:
   p,h,i,d=self.fixture(t);m.configure_owned_environment(p,h,i);created=[];real=m.tempfile.TemporaryFile
   def temp(*a,**kw):created.append(kw.get('dir'));return real(*a,**kw)
   class Proc:
    returncode=0
    def wait(self,timeout=None):return 0
    def poll(self):return 0
   def launch(argv,**kw):
    self.assertEqual(kw['env'],m.clean_env());self.assertNotIn('start_new_session',kw);kw['stdout'].write(b'fixture\n');return Proc()
   with patch.object(m.tempfile,'TemporaryFile',side_effect=temp),patch.object(m.subprocess,'Popen',side_effect=launch):self.assertEqual(m._list('/not-executed-loader','/not-executed-binary'),'fixture\n')
   self.assertEqual(created,[d['cache_paths']['TMPDIR']]*2)
 def test_metadata_alias_rejected(self):
  with tempfile.TemporaryDirectory()as t:
   p,h,i,d=self.fixture(t);alias=pathlib.Path(t)/'alias';alias.symlink_to(pathlib.Path(t),target_is_directory=True)
   with self.assertRaises(ValueError):m.configure_owned_environment(alias/p.name,h,i)
 def test_receipt_new_schema_not_old_qualification(self):
  text=(D/'runtime_abi_owned.py').read_text();self.assertNotIn("'SAME_JOB_ELF_STARTUP_ABI_V1'",text);self.assertIn("'SAME_JOB_ELF_STARTUP_ABI_OWNED_ENV_V2'",text);self.assertIn("later_dlopen='NOT_QUALIFIED'",text)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=pathlib.Path,required=True);args,rest=parser.parse_known_args();BASE=args.baseline
 unittest.main(argv=[__file__]+rest)

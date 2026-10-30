import copy,hashlib,importlib.util,json,pathlib,tempfile,types,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent;spec=importlib.util.spec_from_file_location('fresh',D/'owner_fresh.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v)+'\n');return pin(p)
def pin(p):
 p=pathlib.Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def checked(v):
 p=pathlib.Path(v['path'])
 if pin(p)!=v:raise ValueError('pin drift')
 return p
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
  self.identity=dict(run_id=123,source_commit='a'*40,launch_commit='b'*40)
  self.b=dict(schema='FRESH_JOB_THREE_RUNTIME_INSTALL_BINDING_V1',owner_root=str(self.root),identity=self.identity,scope='INSTALL_AND_SOURCE_BIND_ONLY_NO_REFERENCE_DUT',runtimes={},pins={},archives=[])
  for role in ('python','admitted_runner','phase_script','helper'):
   p=self.root/role;p.write_text(role);self.b[role]=str(p);self.b['pins'][str(p)]=pin(p)['sha256']
  phase=self.root/'phase.json';self.b['phase_binding']=write(phase,{'source_pins':dict(self.b['pins'])});self.b['pins'][str(phase)]=pin(phase)['sha256']
  for i in range(53):
   p=self.root/'archives'/str(i);p.parent.mkdir(exist_ok=True);p.write_text('archive'+str(i));self.b['archives'].append(pin(p));self.b['pins'][str(p)]=pin(p)['sha256']
  self.side={};self.entries={}
  for k in m.KEYS:
   root=self.root/'installs'/k;home=root if k=='qwen2'else root/'work/runtime';home.mkdir(parents=True);site=home/'site-packages';site.mkdir();(site/'tiny.py').write_text('x=1\n');(home/'python.sh').write_text('# original fixture wrapper\n')
   side=write(home/'SOURCE_SIDECAR.json',{'fixture':k});self.side[k]=side
   caps={'wall_seconds':60,'rss_bytes':1000000};argv=[self.b['python'],'-S','-B',self.b['phase_script'],'--binding',str(phase),'--binding-sha256',pin(phase)['sha256'],'--runtime',k]
   native=self.root/'runs'/k/'RESULT.json';phase_result=self.root/'results'/(k+'_RESULT.json')
   self.b['runtimes'][k]=dict(root=str(root),home=str(home),site=str(site),native_path=str(native),phase_result_path=str(phase_result),argv=argv,caps=caps)
   r=dict(status='PASS_PROCESS_ONLY',native_exit=0,errors=[],argv=argv,caps=caps,cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
   nativepin=write(native,r)
   if k=='qwen2':
    lock=write(self.root/'wheel_lock.json',{'packages':[dict(name='fixture',sha256='c'*64,role='runtime')]});self.lock_sha=lock['sha256']
    install=dict(status='INSTALLED_ISOLATED_NOT_REFERENCE_TESTED',python='3.12.14',wheel_lock=lock,installed_wheels=[dict(name='fixture',sha256='c'*64)],python_executable=pin(pathlib.Path(self.b['python'])))
   else:install=dict(status='PASS_OFFLINE_LOCKED_INSTALL',checks={'fixture':True},trust_boundary=dict(host_interpreter=self.b['python'],sha256=pin(pathlib.Path(self.b['python']))['sha256'],python='3.12.14'),artifacts={})
   ip=write(home/'runtime_install.json',install)
   result=dict(scope='FRESH_INSTALL_ARCHIVE_SOURCE_BOUND_NOT_REFERENCE_TESTED',runtime=k,installation=ip,wrapper=pin(home/'python.sh'),sidecar=side,python=pin(pathlib.Path(self.b['python'])),site=str(site))
   self.entries[k]=dict(native=nativepin,phase_result=write(phase_result,result),installation=ip,sidecar=side)
  self.bp=self.root/'BINDING.json';write(self.bp,self.b)
  self.index=self.root/'RECEIPTS.json';write(self.index,dict(schema='FRESH_JOB_THREE_RUNTIME_RECEIPTS_V1',identity=self.identity,binding=pin(self.bp),entries=self.entries))
  self.fake=types.SimpleNamespace(pin=pin,checked=checked,read=lambda p:json.loads(pathlib.Path(p).read_text()),QWEN2_LOCK_SHA=self.lock_sha,INSTALL_CHECKS=('fixture',),CONTRACT={k:('fixture-revision',self.side[k]['sha256'])for k in m.KEYS},wrapper_policy=lambda *a:None,sidecar=lambda *a:None,tree=lambda root,py:{str(p.relative_to(root)):dict(bytes=p.stat().st_size,sha256=pin(p)['sha256'])for p in pathlib.Path(root).rglob('*')if p.is_file()})
  self.addCleanup(patch.stopall);patch.object(m,'HELPER_SHA',self.b['pins'][self.b['helper']]).start();patch.object(m,'helper',return_value=self.fake).start()
 def evidence(self):return m.evidence(self.bp,pin(self.bp)['sha256'],self.index,pin(self.index)['sha256'])
 def mutate_native(self,field,value):
  r=self.entries['qwen2']['native'];p=pathlib.Path(r['path']);doc=json.loads(p.read_text());doc[field]=value;self.entries['qwen2']['native']=write(p,doc);idx=json.loads(self.index.read_text());idx['entries']=self.entries;write(self.index,idx)
 def test_real_small_receipt_chain(self):
  b,_,e=self.evidence();self.assertEqual(set(e),set(m.KEYS));out=self.root/'owner';row=m.bind(self.bp,pin(self.bp)['sha256'],self.index,pin(self.index)['sha256'],out);owner,helper=m.verify(row['path'],row['sha256'],self.root);self.assertEqual(owner['identity'],self.identity)
  for entry in owner['entries'].values():m.validate_tree(helper,entry)
 def test_native_cleanup_reject(self):
  self.mutate_native('cleanup_proof',{'status':'INCOMPLETE'})
  with self.assertRaises(ValueError):self.evidence()
 def test_native_wrong_argv(self):
  self.mutate_native('argv',['old','sample'])
  with self.assertRaises(ValueError):self.evidence()
 def test_native_wrong_caps(self):
  self.mutate_native('caps',{'wall_seconds':999})
  with self.assertRaises(ValueError):self.evidence()
 def test_native_eof_reject(self):
  self.mutate_native('log_capture',{'pipe_eof_observed':False,'gzip_finalized':True})
  with self.assertRaises(ValueError):self.evidence()
 def test_identity_swapped(self):
  idx=json.loads(self.index.read_text());idx['identity']=dict(self.identity,source_commit='b'*40,launch_commit='a'*40);write(self.index,idx)
  with self.assertRaises(ValueError):self.evidence()
 def test_sidecar_drift(self):
  pathlib.Path(self.side['qwen2']['path']).write_text('changed')
  with self.assertRaises(ValueError):self.evidence()
 def test_binding_tamper(self):
  h=pin(self.bp)['sha256'];self.bp.write_text('{}')
  with self.assertRaises(ValueError):m.binding(self.bp,h)
 def test_archive_drift(self):
  pathlib.Path(self.b['archives'][0]['path']).write_text('changed')
  with self.assertRaises(ValueError):self.evidence()
 def test_tree_drift(self):
  out=self.root/'owner';row=m.bind(self.bp,pin(self.bp)['sha256'],self.index,pin(self.index)['sha256'],out);owner,h=m.verify(row['path'],row['sha256'],self.root);entry=owner['entries']['qwen2'];(pathlib.Path(entry['site'])/'tiny.py').write_text('changed')
  with self.assertRaises(ValueError):m.validate_tree(h,entry)
 def test_schema_reject(self):
  b=dict(self.b,schema='SHARED_THREE_RUNTIME_OWNER_CURRENT_INSTALL_V2');write(self.bp,b)
  with self.assertRaises(ValueError):m.binding(self.bp,pin(self.bp)['sha256'])
if __name__=='__main__':unittest.main()

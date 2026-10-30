import ast,copy,importlib.util,json,pathlib,sys,tempfile,unittest
P=pathlib.Path(__file__).resolve().parent
B=P
sys.path.insert(0,str(P))
import frontend_observation_metadata as m
from unittest import mock
from driver_dependency_proof import OBSERVER_HEADER_PINS
import hashlib
def fixture():
 def pin(path,text=None,h=None):
  r=dict(path=path,bytes=4 if text is None else len(text.encode()),sha256=h or hashlib.sha256((text or 'fake').encode()).hexdigest())
  if text is not None:r['text']=text
  return r
 ident=dict(run_id=1,artifact_name='test-fixture',source_commit='a'*40,launch_commit='b'*40,launch_manifest_path='fixture.json',launch_manifest_blob_sha='c'*40)
 root='/owned/tool';obj='/owned/out/frontend/obj';driver='/owned/source/host_axi_driver_non_dpi.cpp';include='/owned/include';make={}
 globaltext='SYNTHETIC_GLOBAL_MAKE_TEST_ONLY\n'
 make[root+'/include/verilated.mk']=pin(root+'/include/verilated.mk',globaltext)
 for prefix in ['V'+n for n in m.CHILDREN]+[m.TOP]:
  host=prefix==m.TOP;at=obj if host else obj+'/'+prefix;name=prefix[1:]
  rows=[f'default: {m.TOP if host else "lib"+name}','PERL = perl','PYTHON3 = python3',f'VERILATOR_ROOT = {root}','SYSTEMC_INCLUDE ?=','SYSTEMC_LIBDIR ?=','VM_PROFC = 0','VM_SC = 0','VM_SP_OR_SC = $(VM_SC)','VM_PCLI = 1','VM_SC_TARGET_ARCH = linux',f'VM_PREFIX = {prefix}',f'VM_MODPREFIX = {prefix}','VM_USER_CFLAGS = '+('-std=c++17 -I'+include if host else '-fPIC'),'VM_USER_LDLIBS = '+('-lcrypto'if host else ''),'VM_USER_CLASSES = '+('host_axi_driver_non_dpi'if host else ''),'VM_USER_DIR = '+('/owned/source ..' if host else '../..'),f'include {prefix}_classes.mk']
  if host:rows+=['include '+m.TOP+'_hier.mk']
  rows+=['include $(VERILATOR_ROOT)/include/verilated.mk']
  if host:rows+=['VPATH += $(VM_USER_DIR)','host_axi_driver_non_dpi.o: '+driver,'$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST) -c -o $@ $<',m.TOP+': $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a $(VM_HIER_LIBS)','$(LINK) $(LDFLAGS) $^ $(LOADLIBES) $(LDLIBS) $(LIBS) $(SC_LIBS) -o $@']
  else:rows+=[f'lib{name}.a: $(VK_OBJS) $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) {name}.o $(VM_HIER_LIBS)',f'lib{name}: lib{name}.a']
  path=at+'/'+prefix+'.mk';make[path]=pin(path,'\n'.join(rows)+'\n')
  rows=[k+' = '+v for k,v in {'VM_C11':'1','VM_TIMING':'0','VM_COVERAGE':'0','VM_PARALLEL_BUILDS':'1','VM_TRACE':'0','VM_TRACE_VCD':'0','VM_TRACE_FST':'0'}.items()]+[k+' +='for k in ('VM_CLASSES_FAST','VM_CLASSES_SLOW','VM_SUPPORT_FAST','VM_SUPPORT_SLOW','VM_GLOBAL_FAST','VM_GLOBAL_SLOW')]
  path=at+'/'+prefix+'_classes.mk';make[path]=pin(path,'\n'.join(rows)+'\n')
 path=obj+'/'+m.TOP+'_hier.mk';make[path]=pin(path,'ifndef VM_HIER_VERILATION_INCLUDED\nVM_HIER_LIBS := '+' '.join('V'+n+'/lib'+n+'.a'for n in m.CHILDREN)+'\nendif\n')
 deps={driver:pin(driver,h=m.DRIVER_SHA),include+'/sparse_write_memory.hpp':pin(include+'/sparse_write_memory.hpp')}
 deps.update({'/owned/source/'+n:pin('/owned/source/'+n,h=h)for n,h in OBSERVER_HEADER_PINS.items()})
 dep=pin(obj+'/host_axi_driver_non_dpi.d','host_axi_driver_non_dpi.o: '+' '.join(deps)+'\n')
 argv=['/tools/make','-C',obj,'-f',m.TOP+'.mk','-j1','VM_HIER_VERILATION_INCLUDED=1',*m.O0]+[k+'=/tools/'+v for k,v in zip(('CXX','LINK','AR','RANLIB','PERL','PYTHON3'),('cxx','cxx','ar','ranlib','perl','python'))]+['OBJCACHE=','OPT=','USER_CPPFLAGS=','USER_LDLIBS=','USER_LDFLAGS=','VM_HIER_LIBS=','host_axi_driver_non_dpi.o']
 sv=dict(schema='OBSERVED_FRONTEND_SV_V1',status='OBSERVED_UNREVIEWED_NOT_ACCEPTED',raw_sha256='a'*64,normalized_sha256='b'*64,bytes=4,scanner_sha256=m.SCANNER_SHA,counts={},modules=[dict(module='fake_fixture',bytes=4,raw_sha256='a'*64,normalized_sha256='b'*64,sourceinfo_count=0)],numerical_pass=False)
 result=dict(schema='OBSERVED_FRONTEND_DRIVER_TU_V1',status='OBSERVED_UNREVIEWED_NO_BINARY_OR_NUMERICAL_PASS',artifact_identity=ident,source_commit=ident['source_commit'],matrix_macs=4096,vector_lanes=32,profiles=list(range(5)),canonical_manifest_sha256='00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c',sv=sv,ports=json.loads((m.D/'OBSERVER_HOST_PORTS_122.json').read_text()),host_header=pin(obj+'/'+m.TOP+'.h'),make_closure=make,make_closure_pins={p:v['sha256']for p,v in make.items()},native_dependency_metadata=[dict(relative_path=n,bytes=1,sha256="a"*64,targets=1,prerequisites=1)for n in sorted({m.TOP+"__ver.d",m.TOP+"__hierVer.d"}|{"V"+n+"/V"+n+"__ver.d"for n in m.CHILDREN})],driver_dependency=dict(schema='ACTUAL_DRIVER_TU_ONLY_DEPENDENCY_V1',depfile=dep,object=pin(obj+'/host_axi_driver_non_dpi.o'),dependencies=deps,argv=argv,supervisor=dict(native_exit=0,errors=[],cleanup_status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',pipe_eof_observed=True,gzip_finalized=True)),tool_manifest_sha256='a'*64,compiler_identity={k:dict(path='/tools/'+k,sha256='a'*64)for k in ('cxx','ar','ranlib','perl','python','make','cc1plus','as','ld','collect2')},stage_exits=[dict(name=n,status='PASS_PROCESS_ONLY',native_exit=0,rss=1024,elapsed=1)for n in m.STAGES],archive_link_executed=False,numerical_pass=False,sv_accepted=False,cpu_capability_observation=dict(avx512f=False,predicate='original_P0_runtime_cpuinfo_exact_token',runtime_qualified=False))
 return result,ident

def project_test(r,i):
 # Only test fixture global-make hash is mocked; production pins are unchanged.
 with mock.patch.object(m,"GLOBAL_MK_SHA",hashlib.sha256(b"SYNTHETIC_GLOBAL_MAKE_TEST_ONLY\n").hexdigest()):
  return m.project_qualification(r,i)
class Test(unittest.TestCase):
 def receipt(self):return dict(native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
 def test_complete(self):m.completed(self.receipt())
 def test_no_eof(self):
  r=self.receipt();r['log_capture']['pipe_eof_observed']=False
  with self.assertRaises(ValueError):m.completed(r)
 def test_no_gzip(self):
  r=self.receipt();r['log_capture']['gzip_finalized']=False
  with self.assertRaises(ValueError):m.completed(r)
 def test_no_cleanup(self):
  r=self.receipt();r['cleanup_proof']={}
  with self.assertRaises(ValueError):m.completed(r)
 def test_fail_native(self):
  r=self.receipt();r['native_exit']=1
  with self.assertRaises(ValueError):m.completed(r)
 def test_products(self):
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d);m.no_compiled(p);(p/'driver.o').write_bytes(b'fake');m.no_compiled(p,['driver.o']);(p/'bad.a').write_bytes(b'fake')
   with self.assertRaises(ValueError):m.no_compiled(p,['driver.o'])
 def test_caps(self):
  with self.assertRaises(ValueError):m.bounded({'data':'x'*500},100,'test')
 def test_fresh_metadata(self):
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d)/'result.json';m.write_new(p,{'numerical_pass':False})
   with self.assertRaises(FileExistsError):m.write_new(p,{})
 def test_abi(self):
  ports=json.loads((P/'OBSERVER_HOST_PORTS_122.json').read_text());old=json.loads((B/'HOST_PORTS.json').read_text());self.assertEqual(len(ports),122)
  self.assertTrue(all(ports[k]==v for k,v in old.items()));extra=set(ports)-set(old);self.assertEqual(len(extra),37);self.assertEqual(sum(ports[k][1]for k in extra),948)
 def test_entry_scope_ast(self):
  s=(P/'frontend_qualify_only.py').read_text();a=ast.parse(s);calls={n.func.id for n in ast.walk(a)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)}
  self.assertFalse({'admit_build','prepare','run','pack'}&calls);self.assertIn('qualify_frontend',calls)
  self.assertIn("21000-(time.monotonic()-b['job_started_monotonic'])",s);self.assertIn("cleanup_seconds=30",s)
 def test_old_guard_intact(self):
  s=(P/'CanonicalHighGate.scala').read_text();self.assertIn('if(a(0)=="baseline") 8985 else 9022',s)
  self.assertIn('c.modules.size==1056',s)
 def test_real_dep_contract_shape(self):
  from driver_dependency_proof import OBSERVER_HEADER_PINS
  driver='/owned/source/driver.cpp';paths=['/owned/source/driver.cpp','/owned/include/sparse_write_memory.hpp']+['/owned/source/'+n for n in OBSERVER_HEADER_PINS]
  deps=m.parse_dependencies('driver.o: '+' '.join(paths)+'\n','/owned/obj',driver)
  m.verify_observer_dependencies(deps,driver,{'/owned/source/'+n:h for n,h in OBSERVER_HEADER_PINS.items()})
 def test_missing_observer_dep(self):
  with self.assertRaises(ValueError):m.verify_observer_dependencies(['/owned/source/resident_observation.hpp'],'/owned/source/driver.cpp',{})
 def test_duplicate_observer_dep(self):
  with self.assertRaises(ValueError):m.verify_observer_dependencies(['/owned/source/resident_observation.hpp']*2,'/owned/source/driver.cpp',{})
 def test_observed_sv_not_accepted(self):
  mat=B.parent/'ci_frontend_materialization_r2_20261029'
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d);sv=p/'tiny.sv';sv.write_text('module tiny(\n  input clock\n);\nendmodule\n')
   r=m.observe_sv(sv,mat,p/'result.json');self.assertFalse(r['numerical_pass']);self.assertEqual(r['status'],'OBSERVED_UNREVIEWED_NOT_ACCEPTED');self.assertEqual(len(r['modules']),1)
 def test_projector_positive_mock_only(self):
  r,i=fixture();self.assertEqual(project_test(r,i),r)
 def test_projector_unknown_nested(self):
  r,i=fixture();r['sv']['payload']='forbidden'
  with self.assertRaises(ValueError):project_test(r,i)
 def test_projector_no_pass(self):
  r,i=fixture();r['numerical_pass']=True
  with self.assertRaises(ValueError):project_test(r,i)
 def test_projector_wrong_run(self):
  r,i=fixture();i=dict(i,run_id=2)
  with self.assertRaises(ValueError):project_test(r,i)
 def test_projector_archive_target(self):
  r,i=fixture();r['driver_dependency']['argv'][-1]='VHostBlockTopV4'
  with self.assertRaises(ValueError):project_test(r,i)
 def test_single_tu_only(self):
  s=(P/'frontend_observation_metadata.py').read_text();self.assertIn("'VM_HIER_LIBS=',stem+'.o'",s);self.assertNotIn("stage('host_link'",s)
if __name__=='__main__':unittest.main()

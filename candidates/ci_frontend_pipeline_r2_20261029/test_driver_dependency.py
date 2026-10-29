"""Metadata only. No compiler, loader, reference, or DUT process."""
import pathlib,tempfile,unittest,sys,json,copy,hashlib,shutil,resource
from unittest.mock import patch
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
P=pathlib.Path
import argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',type=P,required=True)
ap.add_argument('--pipeline-dir',type=P)
ap.add_argument('--global-mk',type=P,required=True)
args,unittest_args=ap.parse_known_args()
REPO=args.repo.resolve()
PIPELINE=(args.pipeline_dir or REPO/'candidates/ci_frontend_pipeline_r2_20261029').resolve()
sys.path.insert(0,str(PIPELINE))
import driver_dependency_proof as d
import build_producer as producer
import p0_source_evidence as evidence

def checked(p,want):
 p=P(p)
 if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=want:
  raise ValueError('portable test input pin mismatch: '+str(p))
 return p
DRIVER=checked(REPO/'candidates/five_profile_execution_v3_20261029T0148/host_axi_driver_non_dpi_final_dump.cpp','20df2692d41693491f0da03fa17f21886b9375ca599c83b5b75c0994841dc45e')
HEADER=checked(REPO/'candidates/host_runtime_non_dpi_backend/source/sparse_write_memory.hpp','63206761274600c98352aea72281cee305d33a96e406a74bc51f665484845368')
GLOBAL_MK=checked(args.global_mk,'74121398e5be12bf03721f1f0f5ce75e7c703635ec7e50920d43f9c4e31fcc0c')
CONTRACT=checked(REPO/'candidates/same_job_materialization_20261029/consumer/LOCKED_SOURCE_CONTRACT.json','9a0a4e8e7acb477b48e90afe0fc545d971f9fbaa87cf6586fe090f6f344c41f0')
PROGRAM=checked(REPO/'candidates/p0_newboundary_input_provider_20261028/PROGRAM_MANIFEST.json','4f201e1744b8aa2c604a478ca837076abaf41a7235b62d8aa7ef14fcdc830163')
OVERLAY=checked(REPO/'candidates/ci_frontend_materialization_r2_20261029/FIXED_SOURCE_OVERLAY_R2.json','f8cb8f64819e7f2dd4f3778cc6066e18d062ec1102832f53ef6eabfbcace4b39')
rows=json.loads(OVERLAY.read_text())['files'];contract=json.loads(CONTRACT.read_text())
BINDINGS={}
for role,name in evidence.SCALA.items():
 matches=[r for r in rows if r['name']==name]
 if len(matches)!=1:raise ValueError('unique source role '+role)
 row=matches[0];p=REPO/row['repo_path']
 if REPO not in p.resolve().parents:raise ValueError('source outside repo')
 checked(p,row['sha256']);checked(p,contract['sources'][role]['sha256'])
 BINDINGS[role]=p
class T(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=P(self.tmp.name);self.obj=root/'obj';self.obj.mkdir();self.driver=root/'driver/source.cpp';self.driver.parent.mkdir();shutil.copyfile(DRIVER,self.driver);self.header=root/'far/include/sparse_write_memory.hpp';self.header.parent.mkdir(parents=True);shutil.copyfile(HEADER,self.header)
  self.groot=root/'tool';(self.groot/'include').mkdir(parents=True);shutil.copyfile(GLOBAL_MK,self.groot/'include/verilated.mk')
  self.host=self.obj/'VHostBlockTopV4.mk';self.host.write_text('VM_USER_CLASSES = source\nsource.o: '+str(self.driver)+'\n\t$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST) -c -o $@ $<\nVHostBlockTopV4: $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a $(VM_HIER_LIBS)\n\t$(LINK) $(LDFLAGS) $^ $(LOADLIBES) $(LDLIBS) $(LIBS) $(SC_LIBS) -o $@\n')
  self.binary=self.obj/'VHostBlockTopV4';self.binary.write_bytes(b'\x7fELF\x02\x01'+b'\0'*10+b'\x02\0\0\0')
  (self.obj/'source.o').write_bytes(b'MOCK_OBJECT_NOT_COMPILED');self.dep=self.obj/'source.d';self.dep.write_text('source.o: '+str(self.driver)+' \\\n '+str(self.header)+'\n')
  self.libs=['V'+n+'/lib'+n+'.a'for n in producer.CHILDREN];self.hier=self.obj/'VHostBlockTopV4_hier.mk';self.hier.write_text('VM_HIER_LIBS := '+' '.join(self.libs)+'\n')
  self.tools=dict(make='/usr/bin/make',cxx='/usr/bin/g++',ar='/usr/bin/ar',ranlib='/usr/bin/ranlib',perl='/usr/bin/perl',python='/usr/bin/python3')
  flags=['-j1','VM_HIER_VERILATION_INCLUDED=1',*producer.O0,'CXX='+self.tools['cxx'],'LINK='+self.tools['cxx'],'AR='+self.tools['ar'],'RANLIB='+self.tools['ranlib'],'PERL='+self.tools['perl'],'PYTHON3='+self.tools['python'],'OBJCACHE=','OPT=','USER_CPPFLAGS=','USER_LDLIBS=','USER_LDFLAGS=']
  self.argv=[self.tools['make'],'-C',str(self.obj),'-f','VHostBlockTopV4.mk',*flags,'VM_HIER_LIBS='+' '.join(self.libs),'VHostBlockTopV4']
  self.receipt=dict(argv=self.argv,native_exit=0,errors=[],cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'))
  self.b=dict(obj=str(self.obj),driver=str(self.driver),verilator_root=str(self.groot),pins={str(p):d.sha(p)for p in (self.driver,self.header,self.host,self.hier,self.groot/'include/verilated.mk')},admission=dict(make_closure_pins={str(p):d.sha(p)for p in (self.host,self.hier)}))
  self.phase=dict(name='host_link',argv=self.argv,output=str(self.binary))
  self.record=d.capture(self.b,self.phase,self.receipt)
  self.m=dict(generation_input_pins=dict(self.b['pins'],**{'/producer/checkedout/candidates/ci_frontend_pipeline_r2_20261029/'+name:value for name,value in dict(d.PRODUCER_IMPLEMENTATION_PINS,**{'driver_dependency_proof.py':d.sha(d.__file__)}).items()}),derived_generated_pins={str(p):d.sha(p)for p in (self.host,self.hier)})
  self.policy={'source_pins':{'sparse_memory':d.pin(self.header)}}
  self.tool=root/'tool_manifest.json';self.tool.write_text(json.dumps(dict(schema='INSTALLED_GNU_BUILD_TOOLS_V1',compile_tools=self.tools,pins={str(P(p).resolve()):'mock'for p in self.tools.values()})))
  self.common=dict(binary=d.pin(self.binary),driver=d.pin(self.driver),build_receipt=dict(path=str(root/'build_receipt.json')))
  self.build=dict(tool_manifest_sha256=d.sha(self.tool),phases=[dict(phase='host_link',native_exit=0,output_sha256=d.sha(self.binary),supervisor_receipt_sha256=d.digest(json.dumps(self.receipt,sort_keys=True,separators=(',',':')).encode()))])
 def verify(self,r=None):return d.verify(r or self.record,self.m,self.policy,self.common,self.build,'/producer/checkedout')
 def test_split_dir_actual_rule(self):self.assertEqual(self.verify(),str(self.header))
 def test_grammars(self):
  for text in ['', 'wrong.o: '+str(self.driver)+' '+str(self.header)+'\n',self.dep.read_text()+'evil: x\n',self.dep.read_text().replace(str(self.header),'$(shell evil)'),self.dep.read_text().replace('\n','\r\n'),self.dep.read_text().replace(str(self.header),'../evil/sparse_write_memory.hpp'),self.dep.read_text().replace(str(self.driver),'/other.cpp')]:
   with self.subTest(text=text),self.assertRaises(ValueError):d.parse_dep(text,self.obj,self.driver)
 def test_duplicate_sparse(self):
  with self.assertRaises(ValueError):d.parse_dep(self.dep.read_text().rstrip()+' /near/sparse_write_memory.hpp\n',self.obj,self.driver)
 def test_old_producer_cannot_self_assert_new_capture(self):
  self.m['generation_input_pins']['/producer/checkedout/candidates/ci_frontend_pipeline_r2_20261029/build_producer.py']='0'*64
  with self.assertRaisesRegex(ValueError,'collection code'):self.verify()
 def test_unrelated_root_code_pins_do_not_authorize_capture(self):
  key='/producer/checkedout/candidates/ci_frontend_pipeline_r2_20261029/build_producer.py';self.m['generation_input_pins'][key.replace('/checkedout','/unrelated')]=self.m['generation_input_pins'].pop(key)
  with self.assertRaisesRegex(ValueError,'collection code'):self.verify()
 def test_missing_dependency_pin(self):
  del self.m['generation_input_pins'][str(self.header)]
  with self.assertRaises(ValueError):self.verify()
 def test_shadow_hash(self):
  self.record['resolved_sparse_header']['sha256']='0'*64
  with self.assertRaises(ValueError):self.verify()
 def test_binary_drift(self):
  self.common['binary']['sha256']='0'*64
  with self.assertRaises(ValueError):self.verify()
 def test_receipt_roles(self):
  for key,value in [('native_exit',1),('errors',['bad']),('cleanup_proof',{'status':'INCOMPLETE'})]:
   r=copy.deepcopy(self.record);r['host_link_receipt'][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.verify(r)
 def test_object_target_wrong(self):
  r=copy.deepcopy(self.record);r['object']['path']=str(self.obj/'else.o')
  with self.assertRaises(ValueError):self.verify(r)
 def test_compiler_wrong(self):
  self.argv[self.argv.index('CXX=/usr/bin/g++')]='CXX=/bad/compiler';self.build['phases'][0]['supervisor_receipt_sha256']=d.digest(json.dumps(self.receipt,sort_keys=True,separators=(',',':')).encode())
  with self.assertRaises(ValueError):self.verify()
 def test_make_override_injection(self):
  self.argv.insert(-1,'VM_USER_OBJS=');self.build['phases'][0]['supervisor_receipt_sha256']=d.digest(json.dumps(self.receipt,sort_keys=True,separators=(',',':')).encode())
  with self.assertRaisesRegex(ValueError,'exact actual host-link'):self.verify()
 def test_missing_link_chain(self):
  text=self.record['host_make']['text'].replace('$(VK_USER_OBJS) ','');self.record['host_make'].update(text=text,bytes=len(text.encode()),sha256=d.digest(text.encode()));self.m['derived_generated_pins'][str(self.host)]=self.record['host_make']['sha256'];self.record['make_closure_pins'][str(self.host)]=self.record['host_make']['sha256']
  with self.assertRaises(ValueError):self.verify()
 def enrich_fixture(self):
  import p0_source_evidence as e
  repo=self.obj.parent;bindings=BINDINGS;rows=[]
  for name,filename in e.SCALA.items():
   p=repo/'scala'/filename;p.parent.mkdir(exist_ok=True);shutil.copyfile(bindings[name],p);self.b['pins'][str(p)]=d.sha(p);rows.append(dict(name=filename,repo_path=str(p.relative_to(repo)),**{k:v for k,v in d.pin(p).items()if k!='path'}))
  contract=repo/'candidates/same_job_materialization_20261029/consumer/LOCKED_SOURCE_CONTRACT.json';contract.parent.mkdir(parents=True);shutil.copyfile(CONTRACT,contract)
  program=repo/'candidates/p0_newboundary_input_provider_20261028/PROGRAM_MANIFEST.json';program.parent.mkdir(parents=True);shutil.copyfile(PROGRAM,program)
  overlay=repo/'overlay.json';overlay.write_text(json.dumps(dict(files=rows)));self.b['pins'][str(overlay)]=d.sha(overlay)
  gates={}
  for stage in ('compile155','original_high'):
   p=repo/stage/'RESULT.json';p.parent.mkdir();p.write_text(json.dumps(dict(native_exit=0,errors=[],argv=['MOCK_RECEIPT_NOT_REAL_COMPILE'])));gates[str(p)]=d.sha(p)
  original=dict(repo=str(repo),driver=str(self.driver),pins=dict(self.b['pins'],**{str(p):d.sha(p)for p in (contract,program)}))
  old=repo/'original_source.json';old.write_text(json.dumps(dict(schema='FIXED_COMMON_SOURCE_IDENTITY_V1',fixed_source_overlay=str(overlay),generation_input_pins=self.b['pins'],verified_gate_pins=gates)))
  self.b['source_manifest']=str(old)
  built=dict(phases=[dict(phase='host_link',driver_dependency=self.record)])
  return e,original,built,old
 def test_enrich_retains_original_and_runtime_roles(self):
  e,original,built,old=self.enrich_fixture();before=old.read_bytes();m=e.enrich(original,self.b,built)
  self.assertEqual(old.read_bytes(),before);self.assertEqual(m['p0_retained_evidence']['original_source_manifest']['sha256'],d.digest(before));self.assertEqual(len(m['files']),12)
  rows={r['path']:r for r in m['files']};a=m['observation_policy_bindings']['P0']['anchors']
  for name in ('commands','descriptors'):self.assertEqual(rows[a[name]]['kind'],'RUNTIME_EXPECTATION_NOT_BUILD_INPUT')
 def test_enrich_depfile_drift_rejected(self):
  e,original,built,old=self.enrich_fixture();self.dep.write_text('stale')
  with self.assertRaisesRegex(ValueError,'evidence drift'):e.enrich(original,self.b,built)
 def test_fresh_host_link_captures_after_actual_stage_return(self):
  self.b.update(build_evidence_dir=str(self.obj));plan=dict(phases=[dict(self.phase,budget=dict(seconds=10,rss_gib=1,tree_bytes=100000))],pins=self.b['pins'],make_closure_pins=self.b['admission']['make_closure_pins'])
  raw=self.dep.read_text();self.dep.unlink();(self.obj/'source.o').unlink();calls=[]
  def stage(name,argv,**kwargs):
   self.assertFalse(self.dep.exists());self.assertFalse((self.obj/'source.o').exists());calls.append(name)
   self.dep.write_text(raw);(self.obj/'source.o').write_bytes(b'MOCK_NEW_OBJECT');return self.receipt
  with patch.object(producer,'prepare',return_value=plan):result=producer.run(self.b,stage)
  self.assertEqual(calls,['host_link']);r=result['phases'][0]['driver_dependency'];self.assertEqual(r['depfile']['text'],raw);self.assertEqual(r['object'],d.pin(self.obj/'source.o'))
 def test_failed_stage_cannot_capture_dependency(self):
  self.b.update(build_evidence_dir=str(self.obj));plan=dict(phases=[dict(self.phase,budget=dict(seconds=10,rss_gib=1,tree_bytes=100000))],pins=self.b['pins'],make_closure_pins=self.b['admission']['make_closure_pins'])
  self.dep.unlink();(self.obj/'source.o').unlink();bad=copy.deepcopy(self.receipt);bad['native_exit']=1
  with patch.object(producer,'prepare',return_value=plan):
   with self.assertRaisesRegex(ValueError,'incomplete'):producer.run(self.b,lambda *a,**kw:bad)
  self.assertFalse((self.obj/'completed_build_phases.json').exists())
 def test_stale_driver_products_pre_stage(self):
  self.b.update(build_evidence_dir=str(self.obj));plan=dict(phases=[dict(self.phase,budget=dict(seconds=10,rss_gib=1,tree_bytes=100000))],pins=self.b['pins'],make_closure_pins=self.b['admission']['make_closure_pins'])
  with patch.object(producer,'prepare',return_value=plan),patch.object(producer,'check_aliases'),patch.object(producer,'check_pins'),patch.object(producer,'pin',side_effect=d.pin):
   for ext in ('.o','.d'):
    for e in ('.o','.d'):(self.obj/('source'+e)).unlink(missing_ok=True)
    (self.obj/('source'+ext)).write_text('stale')
    stage=unittest.mock.Mock()
    with self.assertRaisesRegex(ValueError,'fresh'):producer.run(self.b,stage)
    stage.assert_not_called()
if __name__=='__main__':unittest.main(argv=[sys.argv[0],*unittest_args],verbosity=2)

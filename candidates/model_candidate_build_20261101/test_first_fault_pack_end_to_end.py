"""Real pack/seven/proof gates; synthetic ELF, GCC/header/receipt metadata.
No EDA and no numerical/actual compiler qualification. Real original SV is
read-only transmission input because its fixed raw SHA cannot be synthesized.
Run explicitly with FF_E2E_PAYLOAD and FF_E2E_SOURCE_ROOT pointing to verified
local original payload and original source checkout. Never reads original ELF.
"""
import copy,hashlib,importlib.util,json,os,pathlib,re,shutil,subprocess,sys,tempfile,unittest
import first_fault_policy as policy
import first_fault_probe as probe
import candidate_dependency_proof as proof
import pack_model_candidate as pack
from test_first_fault_probe import synthetic_header
P=pathlib.Path
D=P(__file__).resolve().parent
R=D.parents[1]
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,obj):
 p=P(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_bytes(obj if isinstance(obj,bytes)else (json.dumps(obj,indent=2)+'\n').encode());return p
def tp(p,text):return dict(path=str(p),bytes=len(text.encode()),sha256=hashlib.sha256(text.encode()).hexdigest(),text=text)
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def remap(x,pairs):
 if isinstance(x,str):
  for a,b in pairs:x=x.replace(a,b)
  return x
 if isinstance(x,list):return [remap(a,pairs)for a in x]
 if isinstance(x,dict):return {remap(k,pairs):remap(v,pairs)for k,v in x.items()}
 return x

def construct(w,payload,oldrepo):
 """Small real source-role files only, not thousands of synthetic pin slots."""
 need(shutil.disk_usage(w).free >= (8<<30)+(256<<20),'8GiB plus temporary SV copy reserve')
 host=payload/'hardware.sv';need(sha(host)==policy.ORIGINAL_SV_SHA,'original SV actual bytes')
 repo=w/'repo';obj=w/'obj';out=w/'run';obj.mkdir();out.mkdir()
 def copy_source(rel):
  choices=(R/rel,oldrepo/rel)
  q=next((q for q in choices if q.is_file()),None);need(q is not None,'missing source '+rel)
  return write(repo/rel,q.read_bytes())
 contract=policy.decode_contract((D/'FIRST_FAULT_DRIVER_CONTRACT.json').read_bytes())
 for row in contract.values():
  if isinstance(row,dict)and 'repo_path'in row:
   p=copy_source(row['repo_path']);need(pin(p)['sha256']==row['sha256']and p.stat().st_size==row['bytes'],'actual role source')
 for rel in (policy.CONTRACT_REPO_PATH,policy.SOURCE_CONTRACT_REPO_PATH):copy_source(rel)
 for p in D.glob('*.py'):write(repo/'candidates/model_candidate_build_20261101'/p.name,p.read_bytes())
 copy_source('candidates/model_candidate_build_20261101/MODEL_CANDIDATE_PRECONDITIONS.json')
 abi=copy_source('candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json')
 copy_source('candidates/split_build_only_20261031/seven_files.py')
 original=json.loads((payload/'source_manifest.json').read_text())
 ov=copy_source('candidates/model_candidate_build_20261101/MODEL_SOURCE_OVERLAY.json')
 rows=json.loads(ov.read_text())['files'];sc=__import__('model_source_evidence')
 for filename in sc.SCALA.values():copy_source(next(r['repo_path']for r in rows if r['name']==filename))
 for role in ('sparse_memory','program_manifest'):copy_source(original['model_source_evidence']['anchors'][role])
 for name in proof.OBSERVER_HEADER_PINS:copy_source(str(P(contract['diagnostic_driver']['repo_path']).parent/name))
 driver=repo/contract['diagnostic_driver']['repo_path'];helper=repo/contract['host_observer']['repo_path']
 olddep=original['model_candidate_build_evidence']['driver_dependency'];oldbuilder=olddep['driver'].split('/candidates/')[0]
 pairs=[(olddep['driver'],str(driver)),(olddep['cwd'],str(obj)),(oldbuilder,str(repo)),(P(olddep['driver']).stem,driver.stem)]
 dep=remap(olddep,pairs)
 # Original official global_make bytes retained exactly; other generated text is synthetic.
 for key in ('host_make','host_hierarchy','depfile'):
  r=dep[key];dep[key]=tp(P(r['path']),r['text'])
 gen={};derived={}
 for p in repo.rglob('*'):
  if p.is_file():gen[str(p)]=sha(p)
 # Frozen implementation hashes must match actual source bytes, never artifact-assigned values.
 for rel,h in proof.FIRST_FAULT_IMPLEMENTATION_PINS.items():
  q=copy_source(rel);need(sha(q)==h,'independently frozen implementation source '+rel);gen[str(q)]=h
 need(sha(D/'pack_model_candidate.py')==proof.LOCAL_PACK_READER_SHA,'actual local pack map')
 schema=repo/contract['probe_schema']['repo_path'];config=repo/contract['probe_config']['repo_path'];doc,_=probe.load_schema(schema)
 rh=write(obj/'VHostBlockTopV4___024root.h',synthetic_header(doc));accessor=obj/'readonly_first_fault_access.hpp';ep=w/'probe.json'
 generated=probe.generate(schema,config,rh,accessor,ep)
 ports=json.loads(abi.read_text());lines=[]
 for name,(direction,width)in ports.items():
  kind='8'if width<=8 else '16'if width<=16 else ''if width<=32 else '64'if width<=64 else 'W';suffix=','+str((width+31)//32)if width>64 else ''
  lines.append('VL_'+('IN'if direction=='input'else'OUT')+kind+'(&'+name+','+str(width-1)+',0'+suffix+');')
 hp=write(obj/'VHostBlockTopV4.h',('\n'.join(lines)+'\n').encode())
 dependencies={}
 for path,row in dep['dependencies'].items():
  p=P(path)
  if p==P(dep['driver']):p=driver
  if p.name=='VHostBlockTopV4.h':p=hp
  if p.exists():row=pin(p)
  else:row=dict(row,path=str(p)) # explicit synthetic compiler include metadata
  dependencies[str(p)]=row
 for p in (driver,hp,rh,accessor,helper):dependencies[str(p)]=pin(p)
 dep['dependencies']=dependencies
 dep['depfile']=tp(obj/(driver.stem+'.d'),driver.stem+'.o: '+' '.join(dependencies)+'\n')
 for path,row in dependencies.items():
  (derived if str(obj)in path else gen)[path]=row['sha256']
 for key in ('host_make','host_hierarchy'):
  row=dep[key];write(P(row['path']),row['text'].encode());derived[row['path']]=row['sha256'];dep['make_closure_pins'][row['path']]=row['sha256']
 gen[dep['global_make']['path']]=dep['global_make']['sha256']
 dep['resolved_sparse_header']=dependencies[next(p for p in dependencies if P(p).name=='sparse_write_memory.hpp')]
 tool=json.loads((payload/'tool_manifest.json').read_text());toolp=write(w/'tool.json',tool)
 libs=re.findall(r'^VM_HIER_LIBS\s*:=\s*(.*)$',dep['host_hierarchy']['text'].replace('\\\n',' '),re.M)[0].split()
 argvs=proof.expected_phase_argv(str(obj),tool['compile_tools'],proof.CPP_O1_OVERRIDES,libs)
 phases=[];stagepins={}
 for name in pack.STAGES:
  argv=argvs.get(name,['SYNTHETIC_NOT_EXECUTED',name]);r={'native_exit':0,'errors':[],'argv':argv,'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}}
  rp=write(out/name/'RESULT.json',r);stagepins[name]=pin(rp)
  if name in argvs:
   product=write(P(argv[2])/argv[-1],b'\x7fELF\x02\x01SYNTHETIC_NEVER_EXECUTE'if name=='host_link'else b'SYNTHETIC_ARCHIVE')
   phases.append(dict(phase=name,argv=argv,output=pin(product),supervisor=r))
 dep['host_link_receipt']=phases[-1]['supervisor'];dep['host_link_argv']=phases[-1]['argv'];dep['binary']=phases[-1]['output'];dep['compilation_phases']=copy.deepcopy(phases)
 phases[-1]['driver_dependency']=dep
 built={'status':'BUILT_UNQUALIFIED','scope':'ARCHIVE_LINK_ONLY_NOT_DUT_PASS','cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES,'phases':phases,'binary':phases[-1]['output'],'plan':{'phases':[dict(name=r['phase'],argv=r['argv'])for r in phases],'cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES}}
 # Minimal generation ledger keeps every actual dependency and contract/implementation join.
 obs=copy.deepcopy(original['model_candidate_observation']);obs['source_closure']['source_commit']='a'*40;obs['source_closure']['source_overlay']={k:pin(ov)[k]for k in ('bytes','sha256')}
 obs['stage_receipts']=[dict(name=n,bytes=stagepins[n]['bytes'],sha256=stagepins[n]['sha256'])for n in pack.STAGES]
 catalogfiles=[]
 for p in repo.rglob('*'):
  if p.is_file():catalogfiles.append(dict(path=str(p.relative_to(repo)),bytes=p.stat().st_size,sha256=sha(p)))
 cat=write(repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json',{'schema':'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','files':catalogfiles});obs['source_closure']['source_pins_sha256']=sha(cat)
 op=write(w/'observation.json',obs)
 source={'source_commit':'a'*40,'sv_sha256':sha(host),'driver_sha256':sha(driver),'cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES,'generation_input_pins':gen,'derived_generated_pins':derived,'physical_closure':{'initial_frontend_argv':['verilator','--hierarchical',str(repo/doc['original_hierarchy_pin']['repo_path']),str(config)]}}
 # Hierarchy exact source is retained as a role, not a synthesized implementation identity.
 hierarchy=copy_source(doc['original_hierarchy_pin']['repo_path']);gen[str(hierarchy)]=sha(hierarchy)
 sp=write(w/'source.json',source)
 identity=dict(run_id=1,artifact_name='SYNTHETIC_FIRST_FAULT_E2E',source_commit='a'*40,launch_commit='b'*40,launch_manifest_path='ci_launch/synthetic.json',launch_manifest_blob_sha='c'*40)
 actualpins={str(p):sha(p)for p in repo.rglob('*')if p.is_file()}
 actualpins[str(ep)]=sha(ep)
 b={'repo':str(repo),'repo_sha':'a'*40,'artifact_identity':identity,'driver':str(driver),'pins':actualpins,'first_fault_driver_contract':{'path':str(repo/policy.CONTRACT_REPO_PATH),'sha256':policy.CONTRACT_SHA},'generation_contract':str(repo/contract['hardware_generation_contract']['repo_path']),'generation_contract_sha256':contract['hardware_generation_contract']['sha256'],'model_source_contract':str(repo/policy.SOURCE_CONTRACT_REPO_PATH),'fixed_source_overlay':str(ov),'source_manifest':str(sp),'tool_manifest':str(toolp),'readonly_probe_evidence':pin(ep),'cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES,'admission':{'cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES,'make_closure_pins':{str(hp):sha(hp)}}}
 return dict(binding=b,built=built,host=host,overlay=ov,out=out,observation_pin=pin(op),repo=repo)

def pack_and_verify(f):
 r=pack.pack(f['binding'],f['binding'],f['built'],f['host'],f['overlay'],f['out'],lambda n:need(n<=256<<20,'bounded test copy'),f['observation_pin'])
 root=P(r['manifest']['path']).parent
 # Load the real checkout-local seven validator; it must source-pin its proof.
 spec=importlib.util.spec_from_file_location('_first_fault_e2e_pack',f['repo']/'candidates/model_candidate_build_20261101/pack_model_candidate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 verified=m.verify_candidate_seven(root,f['binding']['artifact_identity'],sha(root/'frozen_artifact.json'))
 # Fresh interpreter ensures candidate_seven_files uses the copied actual pack,
 # not the test interpreter's cached module. No validator mocking or EDA.
 code="import json,sys;from candidate_seven_files import verify;print(json.dumps(verify(sys.argv[1],json.loads(sys.argv[2]),sys.argv[3])))"
 env=dict(os.environ,PYTHONPATH=str(f['repo']/'candidates/model_candidate_build_20261101'),PYTHONDONTWRITEBYTECODE='1')
 argv=[sys.executable,*(['-O']if sys.flags.optimize else []),'-c',code,str(root),json.dumps(f['binding']['artifact_identity']),sha(root/'frozen_artifact.json')]
 q=subprocess.run(argv,cwd=f['repo'],env=env,capture_output=True,text=True,timeout=30)
 need(q.returncode==0,'actual candidate_seven_files subprocess: '+q.stderr[-2000:])
 need(json.loads(q.stdout)==verified,'same actual seven-file entry result')
 return root,verified

@unittest.skipUnless(os.environ.get('FF_E2E_PAYLOAD')and os.environ.get('FF_E2E_SOURCE_ROOT'),'explicit read-only original metadata/SV and source fixture required')
class EndToEnd(unittest.TestCase):
 def test_complete_new_seven_and_negative_joins(self):
  with tempfile.TemporaryDirectory(prefix='first_fault_e2e_',dir=os.environ.get('FF_E2E_WORKSPACE',os.getcwd()))as tmp:
   f=construct(P(tmp).resolve(),P(os.environ['FF_E2E_PAYLOAD']).resolve(strict=True),P(os.environ['FF_E2E_SOURCE_ROOT']).resolve(strict=True))
   root,result=pack_and_verify(f);self.assertFalse(result['numerical_pass'])
   manifest=json.loads((root/'frozen_artifact.json').read_text());source=json.loads((root/'source_manifest.json').read_text());receipt=json.loads((root/'build_receipt.json').read_text())
   def reseal(m,s,r):
    write(root/'source_manifest.json',s);r['source_manifest_sha256']=sha(root/'source_manifest.json');write(root/'build_receipt.json',r)
    for row in m['common'].values():p=root/row['path'];row.update(bytes=p.stat().st_size,sha256=sha(p))
    write(root/'frozen_artifact.json',m)
   mutations=[('wrong_sv',lambda m,s,r:s.update(sv_sha256='0'*64)),('missing_config',lambda m,s,r:s['physical_closure']['initial_frontend_argv'].pop()),('missing_accessor_dependency',lambda m,s,r:s['model_candidate_build_evidence']['driver_dependency']['dependencies'].pop(s['readonly_probe']['accessor_generation']['accessor']['path'])),('wrong_contract',lambda m,s,r:m['readonly_probe_contract'].update(sha256='0'*64)),('old_schema_new_scope',lambda m,s,r:m.update(schema='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'))]
   for name,mutate in mutations:
    with self.subTest(name=name):
     m,s,r=copy.deepcopy((manifest,source,receipt));mutate(m,s,r);reseal(m,s,r)
     with self.assertRaises(ValueError):proof.verify_candidate_compilation(m,s,r,root)
   reseal(manifest,source,receipt)
   self.assertEqual(proof.verify_candidate_compilation(manifest,source,receipt,root)['actual_header_ports'],122)
if __name__=='__main__':unittest.main()

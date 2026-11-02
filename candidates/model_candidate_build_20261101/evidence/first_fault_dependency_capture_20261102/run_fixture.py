"""Actual Python producer/capture/pack/export gates with SYNTHETIC build stages.
Only GCC preprocessing is executed; archives/ELF/20-stage receipts are fixtures.
No EDA, model execution, ELF execution, or claim of compiler/numerical PASS.
"""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,re,resource,shutil,subprocess,sys,time,types
P=pathlib.Path;C='candidates/model_candidate_build_20261101';N='candidates/same_job_execution_20261030'
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):p=P(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def write(p,v):
 p=P(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v if type(v)is bytes else(json.dumps(v,indent=2)+'\n').encode());return p

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source-root',type=P,required=True);ap.add_argument('--payload',type=P,required=True);ap.add_argument('--old-source',type=P,required=True);ap.add_argument('--verilator-root',type=P,required=True);ap.add_argument('--output',type=P,required=True);a=ap.parse_args();source=a.source_root.resolve(strict=True);w=a.output.resolve();need(not w.exists(),'fresh output');w.mkdir(parents=True)
 sys.path.insert(0,str(source/C));sys.path.append(str(source/'candidates/ci_frontend_pipeline_r2_20261029'))
 import test_first_fault_pack_end_to_end as base
 import candidate_build_producer as producer
 import candidate_dependency_proof as proof
 import first_fault_compilation as capture_module
 import pack_model_candidate as pack
 f=base.construct(w,a.payload.resolve(strict=True),a.old_source.resolve(strict=True));b=f['binding'];repo=f['repo'];obj=w/'obj'
 work=w/'work';front=work/'shared/build/frontend';front.parent.mkdir(parents=True);f['out'].rename(front);f['out']=front
 for row in f['built']['phases']:
  P(row['output']['path']).unlink()
 toolp=P(b['tool_manifest']);tool=json.loads(toolp.read_text());tools={k:str(P(shutil.which(v)).resolve())for k,v in {'make':'make','cxx':'g++','ar':'ar','ranlib':'ranlib','perl':'perl','python':'python3'}.items()}
 tool['compile_tools'].update(tools)
 for v in tools.values():tool['pins'][v]=sha(v)
 write(toolp,tool)
 b.update(schema='MODEL_CANDIDATE_BINARY_BUILD_BINDING_V1',source_commit=b['repo_sha'],obj=str(obj),sv=str(f['host']),make=tools['make'],cxx=tools['cxx'],ar=tools['ar'],compile_tools=tools,compile_aliases={},verilator_root=str(a.verilator_root.resolve()),build_evidence_dir=str(w/'build_evidence'),shared_tree_cap=512<<20,candidate_status='UNREVIEWED_MODEL_BUILD',numeric_execution_authorized=False,unchanged_module_contract=str(repo/C/'MODEL_CANDIDATE_PRECONDITIONS.json'),host_port_contract=str(repo/'candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json'))
 for header_name in ('affine_readonly_memory.hpp','affine_tsv_loader.hpp','sparse_write_memory.hpp'):
  rel=P('candidates/host_runtime_non_dpi_backend/source')/header_name;extra=repo/rel;write(extra,(source/rel).read_bytes());need(sha(extra)==sha(source/rel),'actual fixed runtime header copy');b['pins'][str(extra)]=sha(extra)
 P(b['build_evidence_dir']).mkdir();b['budgets']={n:dict(seconds=30,rss_gib=1,tree_bytes=512<<20)for n in pack.STAGES[-5:]}
 b['admission'].update(source_commit=b['source_commit'],status='ACTUAL_MAKE_CLOSURE_REVIEWED',no_implicit_frontend=True,header_122_observation_ports_and_driver_ABI_reviewed=True)
 # Admission fields above are fixture input only, not a reviewed actual Make build.
 dep=f['built']['phases'][-1]['driver_dependency'];source_doc=json.loads(P(b['source_manifest']).read_text())
 globalmk=P(b['verilator_root'])/'include/verilated.mk';need(sha(globalmk)==dep['global_make']['sha256'],'original global recipe real bytes')
 source_doc['generation_input_pins'].pop(dep['global_make']['path'],None);source_doc['generation_input_pins'][str(globalmk)]=sha(globalmk)
 # Fixture-only relocation of original generated relative VM_USER_DIR.
 # Actual Make verifier remains unchanged and checks this current driver path.
 host_make=obj/'VHostBlockTopV4.mk';ht=host_make.read_text();start=ht.index('VM_USER_DIR =');end=ht.index('\n\n',start)
 ht=ht[:start]+'VM_USER_DIR = '+str(P(b['driver']).parent)+ht[end:];host_make.write_text(ht)
 source_doc['derived_generated_pins'][str(host_make)]=sha(host_make)
 for child in producer.CHILDREN:
  q=obj/('V'+child)/('V'+child+'.mk');write(q,('lib'+child+'.a:\n\t@false # SYNTHETIC_NOT_EXECUTED\n').encode())
 for p in list(obj.glob('*.mk'))+list(obj.glob('V*/*.mk')):b['admission']['make_closure_pins'][str(p)]=sha(p)
 for p in [P(v)for v in tools.values()]+[f['host'],P(b['source_manifest']),toolp,globalmk]+[p for p in obj.rglob('*')if p.is_file()]:b['pins'][str(p)]=sha(p)
 # Full preprocessor known input tree is locally pinned before its actual invocation.
 # Only .h/.hpp/.cpp code files, never weights or binary artifacts.
 for root in (repo,a.verilator_root.resolve()/'include'):
  for p in root.rglob('*'):
   if p.is_file()and p.suffix in('.h','.hpp','.cpp'):b['pins'][str(p.resolve())]=sha(p)
 # Statically precheck the entire reachable quoted include closure; system
 # includes remain actual GCC/toolchain responsibility, not fake local headers.
 include_dirs=[obj,P(b['driver']).parent,repo/'candidates/host_runtime_non_dpi_backend/source',P(b['verilator_root'])/'include',P(b['verilator_root'])/'include/vltstd'];pending=[P(b['driver'])];seen_headers={}
 while pending:
  current=pending.pop().resolve()
  if current in seen_headers:continue
  need(current.is_file()and b['pins'].get(str(current))==sha(current),'actual quoted include is fully pre-pinned')
  seen_headers[current]=sha(current)
  # Tool headers have platform-conditional quoted includes (e.g. windows.h);
  # stop static recursion at the fully pinned tool tree. Actual GCC resolves
  # its active branches and capture checks every emitted dependency afterward.
  if current.is_relative_to(P(b['verilator_root'])/'include'):continue
  for header_name in re.findall(r'^\s*#\s*include\s+"([^"\n]+)"',current.read_text(),re.M):
   choices=[d/header_name for d in [current.parent,*include_dirs]];found=next((x.resolve()for x in choices if x.is_file()),None);need(found is not None,'missing quoted include '+header_name);pending.append(found)
 write(w/'QUOTED_INCLUDE_CLOSURE.json',dict(scope='STATIC_LOCAL_QUOTED_GRAPH_PINNED_TOOL_TERMINALS_GCC_RESOLVES_ACTIVE_TOOL_INCLUDES',files={str(k):v for k,v in seen_headers.items()}))
 source_doc['generation_input_pins'].update({p:h for p,h in b['pins'].items()if p not in source_doc.get('derived_generated_pins',{})})
 # Do not self-pin source ledger: pack binds its actual bytes separately.
 source_doc['generation_input_pins'].pop(str(P(b['source_manifest'])),None)
 write(P(b['source_manifest']),source_doc);b['pins'][b['source_manifest']]=sha(P(b['source_manifest']))
 # Synchronize tool source pins once, before prepare/run; no execution result promoted.
 for v in tools.values():source_doc['generation_input_pins'][v]=sha(v)
 write(P(b['source_manifest']),source_doc);b['pins'][b['source_manifest']]=sha(P(b['source_manifest']))
 # all copied helper sources must belong to independent fixture catalog.
 support=repo/'candidates/split_build_only_20261031/TRANSFER_APPROVAL.json';write(support,(source/'candidates/split_build_only_20261031/TRANSFER_APPROVAL.json').read_bytes())
 cat=repo/N/'SOURCE_PINS.json';catalog={'schema':'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','files':[dict(path=str(p.relative_to(repo)),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(repo.rglob('*'))if p.is_file()and p!=cat and '__pycache__'not in p.parts]};write(cat,catalog)
 b['pins'][str(cat)]=sha(cat);source_doc['generation_input_pins'][str(cat)]=sha(cat)
 write(P(b['source_manifest']),source_doc);b['pins'][b['source_manifest']]=sha(P(b['source_manifest']))
 obs=json.loads(P(f['observation_pin']['path']).read_text());obs['source_closure']['source_pins_sha256']=sha(cat)
 gcc_result={};stages=[]
 def stage(name,argv,**kwargs):
  nonlocal gcc_result
  if name=='host_link':
   driver=P(b['driver']);dfile=obj/(driver.stem+'.d')
   gccargv=[tools['cxx'],'-std=c++17','-E','-MMD','-MF',str(dfile),'-MT',driver.stem+'.o','-I',str(obj),'-I',str(repo/'candidates/host_runtime_non_dpi_backend/source'),'-I',str(P(b['verilator_root'])/'include'),'-I',str(P(b['verilator_root'])/'include/vltstd'),str(driver),'-o','/dev/null']
   def limits():
    resource.setrlimit(resource.RLIMIT_AS,(512<<20,512<<20));resource.setrlimit(resource.RLIMIT_CPU,(10,10));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<20,1<<20))
   start=time.monotonic();r=subprocess.run(gccargv,env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},preexec_fn=limits,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=15);elapsed=time.monotonic()-start
   write(w/'GCC_STDERR.local.txt',r.stderr);need(r.returncode==0,'actual tiny GCC preprocessor native0')
   raw=dfile.read_text();tokens=raw.replace('\\\n',' ').split(':',1)[1].split();need(len(tokens)>len(set(tokens)),'actual GCC must produce an exact duplicate; never inject text')
   full=capture_module.parse_dependencies(raw,obj,driver);need(len(full)==len(set(tokens)),'all raw exact unique dependencies preserved')
   need(set(full)<=set(b['pins']),'all GCC dependencies pinned before callback')
   gcc_result=dict(scope='ACTUAL_GCC_PREPROCESS_ONLY_NOT_OBJECT_BUILD',native_exit=r.returncode,elapsed_seconds=elapsed,argv=gccargv,compiler_sha256=sha(P(tools['cxx'])),raw_count=len(tokens),unique_count=len(full),repeated_count=len(tokens)-len(full),raw_depfile=pin(dfile),all_dependency_pins={p:pin(P(p))for p in full})
   write(obj/(driver.stem+'.o'),b'SYNTHETIC_OBJECT_NOT_GCC_COMPILED')
  product=P(argv[2])/argv[-1];raw=b'!<arch>\nSYNTHETIC_NOT_COMPILED'if name!='host_link'else b'\x7fELF\x02\x01'+b'\0'*10+b'\x02\0'+b'\0'*8
  write(product,raw)
  result=dict(native_exit=0,errors=[],argv=argv,cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True))
  write(front/name/'RESULT.json',result);stages.append(name);return result
 built=producer.run(b,stage);need(stages==list(pack.STAGES[-5:]),'all actual Python producer phases traversed')
 actual=built['phases'][-1]['driver_dependency'];need(actual['depfile']['sha256']==gcc_result['raw_depfile']['sha256']and actual['depfile']['text']==P(gcc_result['raw_depfile']['path']).read_text(),'real capture preserves actual GCC rawtext')
 need(actual['dependencies']==gcc_result['all_dependency_pins'],'capture exact full dependency pinset no omission')
 need(actual['dependency_rule_policy']=='GCC_MMD_EXACT_REPEATED_PREREQUISITES_V1','new explicit capture contract')
 obs['stage_receipts']=[dict(name=n,bytes=(front/n/'RESULT.json').stat().st_size,sha256=sha(front/n/'RESULT.json'))for n in pack.STAGES];write(P(f['observation_pin']['path']),obs);f['observation_pin']=pin(P(f['observation_pin']['path']))
 # Captured real GCC list is reflected in source ledger; all were pre-pinned.
 source_doc=json.loads(P(b['source_manifest']).read_text())
 for p,row in actual['dependencies'].items():
  (source_doc['derived_generated_pins']if P(p).is_relative_to(obj)else source_doc['generation_input_pins'])[p]=row['sha256']
 write(P(b['source_manifest']),source_doc);b['pins'][b['source_manifest']]=sha(P(b['source_manifest']))
 f['built']=built
 # Real pack/seven consumer gates, one bounded original SV transmission copy.
 root,verified=base.pack_and_verify(f)
 # Mutate only bounded metadata; reuse the one packed original SV copy.
 manifest=json.loads((root/'frozen_artifact.json').read_text());captured_source=json.loads((root/'source_manifest.json').read_text());receipt=json.loads((root/'build_receipt.json').read_text());negative_results=[]
 def reseal(m,sd,rc):
  write(root/'source_manifest.json',sd);rc['source_manifest_sha256']=sha(root/'source_manifest.json');write(root/'build_receipt.json',rc)
  for row in m['common'].values():q=root/row['path'];row.update(bytes=q.stat().st_size,sha256=sha(q))
  write(root/'frozen_artifact.json',m)
 def mutate_dep_text(sd,fn):
  dd=sd['model_candidate_build_evidence']['driver_dependency'];v=dd['depfile'];v['text']=fn(v['text']);v['bytes']=len(v['text'].encode());v['sha256']=hashlib.sha256(v['text'].encode()).hexdigest()
 def reject(name,mutate):
  m,sd,rc=copy.deepcopy((manifest,captured_source,receipt));mutate(m,sd,rc);reseal(m,sd,rc)
  try:proof.verify_candidate_compilation(m,sd,rc,root)
  except ValueError as e:negative_results.append(dict(case=name,reason=str(e)[:180]))
  else:raise ValueError('negative unexpectedly accepted '+name)
  finally:reseal(manifest,captured_source,receipt)
 dd=captured_source['model_candidate_build_evidence']['driver_dependency'];helper_path=next(p for p in dd['dependencies']if P(p).name=='readonly_first_fault.hpp');root_path=next(p for p in dd['dependencies']if P(p).name=='VHostBlockTopV4___024root.h')
 extra=write(w/'unreviewed_extra.hpp',b'// UNPINNED FIXTURE ONLY\n')
 def extra_dep(m,sd,rc):
  mutate_dep_text(sd,lambda t:t.rstrip()+' '+str(extra)+'\n');sd['model_candidate_build_evidence']['driver_dependency']['dependencies'][str(extra)]=pin(extra)
 reject('raw_extra_unpinned_dependency',extra_dep)
 reject('missing_unique_source_pin',lambda m,sd,rc:sd['generation_input_pins'].pop(helper_path))
 reject('different_token_same_normalized_path',lambda m,sd,rc:mutate_dep_text(sd,lambda t:t.rstrip()+' '+str(obj)+'/./VHostBlockTopV4.h\n'))
 reject('raw_token_limit_4097_even_duplicates',lambda m,sd,rc:mutate_dep_text(sd,lambda t:P(b['driver']).stem+'.o: '+' '.join([str(P(b['driver']))]*4097)+'\n'))
 reject('wrong_dependency_policy',lambda m,sd,rc:sd['model_candidate_build_evidence']['driver_dependency'].update(dependency_rule_policy='UNKNOWN'))
 def remove_dep(m,sd,rc,path):
  v=sd['model_candidate_build_evidence']['driver_dependency'];v['dependencies'].pop(path);mutate_dep_text(sd,lambda t:t.replace(path,''))
 reject('missing_actual_root_header_dependency',lambda m,sd,rc:remove_dep(m,sd,rc,root_path))
 reject('missing_actual_readonly_helper_dependency',lambda m,sd,rc:remove_dep(m,sd,rc,helper_path))
 reject('wrong_fixed_sv',lambda m,sd,rc:sd.update(sv_sha256='0'*64))
 reject('missing_config',lambda m,sd,rc:sd['physical_closure']['initial_frontend_argv'].pop())
 reject('wrong_fixed_contract',lambda m,sd,rc:m['readonly_probe_contract'].update(sha256='0'*64))
 old_manifest=json.loads((a.payload/'frozen_artifact.json').read_text());old_source=json.loads((a.payload/'source_manifest.json').read_text());old_receipt=json.loads((a.payload/'build_receipt.json').read_text());legacy_dep=copy.deepcopy(old_source['model_candidate_build_evidence']['driver_dependency']);legacy_dep['dependency_rule_policy']=capture_module.DEPENDENCY_RULE_POLICY
 try:proof.compilation_policy(legacy_dep,old_source,old_receipt,old_manifest)
 except ValueError as e:need('legacy dependency rule unchanged'in str(e),'legacy field refusal reason');negative_results.append(dict(case='new_policy_in_legacy_artifact',reason=str(e)))
 else:raise ValueError('legacy accepted new parser policy')
 # Invoke actual capture against a removed unique prebuild pin, not only verifier.
 noncontract_header=next(p for p in dd['dependencies']if P(p).name=='verilated.h')
 bad=copy.deepcopy(b);bad['pins'].pop(noncontract_header)
 try:capture_module.capture(bad,dict(name='host_link',argv=built['phases'][-1]['argv'],output=built['binary']['path']),built['phases'][-1]['supervisor'],built['phases'][:-1])
 except ValueError as e:need('all actual non-system dependencies were prebuild pinned'in str(e),'capture failed specifically for missing actual pin');negative_results.append(dict(case='capture_missing_unique_pin',reason=str(e)))
 else:raise ValueError('capture accepted missing pin')
 need(proof.verify_candidate_compilation(manifest,captured_source,receipt,root)['actual_header_ports']==122,'restored full proof still passes')
 # Actual exporter CLI using copied real current code and source catalog.
 import export_model_build as exporter
 for name in exporter.PREP:write(work/'shared/build'/('stage_'+name)/'RESULT.json',dict(native_exit=0,errors=[],cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True)))
 ident=write(w/'identity.json',b['artifact_identity']);write(work/'BUILD_INVOCATION.json',dict(artifact_identity=b['artifact_identity'],source_pins_sha256=sha(cat),job_started_monotonic=time.monotonic()));write(front/'stage_exits.json',[dict(name=n)for n in pack.STAGES]);write(front/'BUILD_ONLY_RESULT.json',dict(status='UNREVIEWED_MODEL_BUILD',artifact=dict(manifest=pin(root/'frozen_artifact.json'),expanded_bytes=sum(p.stat().st_size for p in root.iterdir()))))
 exportout=w/'EXPORT_SUMMARY.json';ghout=w/'GITHUB_OUTPUT';argv=[sys.executable,*(['-O']if sys.flags.optimize else[]),'-B',str(repo/C/'export_model_build.py'),'--repo',str(repo),'--work',str(work),'--identity',str(ident),'--output',str(exportout)]
 rr=subprocess.run(argv,env=dict(os.environ,GITHUB_RUN_ID=str(b['artifact_identity']['run_id']),GITHUB_SHA=b['artifact_identity']['launch_commit'],GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(ghout),PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=45);write(w/'EXPORT_STDERR.local.txt',rr.stderr.encode());need(rr.returncode==0,'real export CLI '+rr.stderr[-700:])
 need(dict(line.split('=',1)for line in ghout.read_text().splitlines())['artifact_dir']==str(root),'exact actual exported directory')
 result=dict(scope='SYNTHETIC_BUILD_PHASES_WITH_REAL_PRODUCER_CAPTURE_PACK_EXPORT_AND_GCC_PREPROCESSOR_NOT_DUT',producer_source_sha256=sha(source/C/'candidate_build_producer.py'),capture_source_sha256=sha(source/C/'first_fault_compilation.py'),gcc_preprocessor=gcc_result,dependency_capture_policy=actual['dependency_rule_policy'],true_python_producer_run=True,quoted_include_closure_count=len(seen_headers),quoted_include_closure_sha256=sha(w/'QUOTED_INCLUDE_CLOSURE.json'),negative_results=negative_results,prepare_mocked=False,capture_mocked=False,build_stages_synthetic=True,export_cli_native_exit=rr.returncode,export_summary_sha256=sha(exportout),verified_seven=verified,numerical_pass=False)
 write(w/'RESULT.json',result);print(json.dumps({k:v for k,v in result.items()if k!='gcc_preprocessor'},indent=2))
if __name__=='__main__':main()

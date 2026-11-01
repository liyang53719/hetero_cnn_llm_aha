"""ALL_SYNTHETIC_CANDIDATE_EVIDENCE: no compile/ELF/SV execution or old ELF/SV reads.
Full historical input inventory is represented by synthetic small local files;
only explicitly identified source-role bytes and empty files retain real content.
"""
import argparse,ast,copy,os,time,types,subprocess,hashlib,importlib.util,json,pathlib,re,shutil,sys
P=pathlib.Path
C='candidates/model_candidate_build_20261101';N='candidates/same_job_execution_20261030'
OLD_TEMPLATE_PINS={'source_manifest.json': '663f9c63a8bd1738d908321643ae9023162ad9cd0d27874941b1a038dd7438b4', 'tool_manifest.json': '6192d4ea0ac421e52178b86d731334067ad124084c9dc8644da08703dca93126', 'build_receipt.json': '336471882ee266884a78fb3f4eb2021e0d3572ea8cfc208b1ad97fcb4c53d043', 'frozen_artifact.json': '84dd24abf3567370c51e3f065bb5f192eb723061a3506a2c30d981870107698b', 'driver.cpp': '343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61'}

def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):p=P(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def scan(x,fn):
 if isinstance(x,dict):return {fn(k):scan(v,fn)for k,v in x.items()}
 if isinstance(x,list):return [scan(v,fn)for v in x]
 return fn(x)if isinstance(x,str)else x

def need(v,m):
 if not v:raise ValueError(m)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=P,required=True);ap.add_argument('--source-root',type=P,required=True);ap.add_argument('--old-payload',type=P,required=True);ap.add_argument('--old-exporter',type=P,required=True);args=ap.parse_args()
 ORIG=args.source_root.resolve(strict=True);old=args.old_payload.resolve(strict=True);out=args.output.resolve();final_source=True
 need(not out.exists(),'fresh output directory')
 old_exporter_path=args.old_exporter.resolve(strict=True)
 need(sha(old_exporter_path)=='3fbaf4a22155759fb66e1a5ff4e97fd4df1cba8365ceb931d1c472172262daa1','exact old exporter regression source')
 source_catalog=ORIG/N/'SOURCE_PINS.json';source_catalog_doc=json.loads(source_catalog.read_text())
 for row in source_catalog_doc['files']:
  actual=ORIG/row['path'];need(actual.is_file()and actual.stat().st_size==row['bytes']and sha(actual)==row['sha256'],'actual current source catalog '+row['path'])
 for name,want in OLD_TEMPLATE_PINS.items():need(sha(old/name)==want,'independently pinned old metadata template '+name)
 # Import test constructor only from explicit current source, never installed names.
 sys.path.insert(0,str(ORIG/C))
 from synthetic_complete_candidate_fixture import make_fixture,load_module,write,textpin
 info=make_fixture(out/'template',old);root=P(info['payload_root']);source=json.loads((root/'source_manifest.json').read_text());tool=json.loads((root/'tool_manifest.json').read_text());obs=source.pop('model_candidate_observation');source.pop('model_source_evidence');ev=source.pop('model_candidate_build_evidence');dep=ev['driver_dependency']
 # Remap historical builder filesystem locations only into an isolated mirror.
 prefix=str(out.resolve()/'mirror')
 replace=lambda s:s.replace('/home/runner/',prefix+'/home/runner/')
 source=scan(source,replace);dep=scan(dep,replace);tool=scan(tool,replace)
 replacements={}
 def text_fix(x):
  if isinstance(x,dict):
   if set(('text','bytes','sha256','path'))<=set(x):
    h=hashlib.sha256(x['text'].encode()).hexdigest();replacements[x['sha256']]=h;x.update(bytes=len(x['text'].encode()),sha256=h)
   for v in x.values():text_fix(v)
  elif isinstance(x,list):
   for v in x:text_fix(v)
 text_fix(dep)
 source=scan(source,lambda s:replacements.get(s,s));dep=scan(dep,lambda s:replacements.get(s,s))
 suffix='/'+C+'/candidate_build_producer.py';roots=[p[:-len(suffix)]for p in source['generation_input_pins']if p.endswith(suffix)];need(len(roots)==1,'one original builder root')
 repo=P(roots[0]);cd=repo/C;cd.mkdir(parents=True,exist_ok=True)
 for current in sorted((ORIG/C).glob('*.py')):shutil.copyfile(current,cd/current.name)
 support=repo/'candidates/split_build_only_20261031';support.mkdir(parents=True,exist_ok=True)
 for name in ('seven_files.py','TRANSFER_APPROVAL.json'):shutil.copyfile(ORIG/'candidates/split_build_only_20261031'/name,support/name)
 for name in ('candidate_dependency_proof.py','MODEL_CANDIDATE_PRECONDITIONS.json','model_source_evidence.py','MODEL_SOURCE_OVERLAY.json'):
  shutil.copyfile(ORIG/C/name,cd/name)
 shutil.copyfile(ORIG/C/'pack_model_candidate.py',cd/'pack_model_candidate.py')
 contract=repo/N/'numeric/MODEL_P0_SOURCE_CONTRACT.json';contract.parent.mkdir(parents=True);shutil.copyfile(ORIG/N/'numeric/MODEL_P0_SOURCE_CONTRACT.json',contract)
 cp=json.loads(contract.read_text());overlay=cd/'MODEL_SOURCE_OVERLAY.json';ov=json.loads(overlay.read_text());fixed={r['name']:r for r in ov['files']}
 evidence=load_module('_actual_record_under_test',cd/'model_source_evidence.py');actual_role_paths={}
 for role,name in evidence.SCALA.items():
  rel=fixed[name]['repo_path'];p=repo/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ORIG/rel,p);actual_role_paths[role]=p
 driver=P(dep['driver']);driver.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old/'driver.cpp',driver);actual_role_paths['driver']=driver
 sparse=P(dep['resolved_sparse_header']['path']);sparse.parent.mkdir(parents=True,exist_ok=True)
 original_sparse=ORIG/'candidates/host_runtime_non_dpi_backend/source/sparse_write_memory.hpp';shutil.copyfile(original_sparse,sparse);actual_role_paths['sparse_memory']=sparse
 program=repo/'candidates/p0_newboundary_input_provider_20261028/PROGRAM_MANIFEST.json';program.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ORIG/'candidates/p0_newboundary_input_provider_20261028/PROGRAM_MANIFEST.json',program);actual_role_paths['program_manifest']=program
 rolepins={str(p):sha(p)for p in actual_role_paths.values()};rolepins[str(contract)]=sha(contract);rolepins[str(overlay)]=sha(overlay)
 for name,p in actual_role_paths.items():need(pin(p)['bytes']==cp['sources'][name]['bytes']and sha(p)==cp['sources'][name]['sha256'],'exact real role '+name)
 source['generation_input_pins'].update(rolepins)
 # Exact current checker map, except its test-only pack byte identity explicitly updated.
 proof_path=cd/'candidate_dependency_proof.py';text=proof_path.read_text();tree=ast.parse(text);impl=next(ast.literal_eval(n.value)for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='CANDIDATE_IMPLEMENTATION_PINS'for t in n.targets))
 for rel,want in impl.items():need(sha(ORIG/rel)==want,'final actual source map '+rel)
 need(impl[C+'/pack_model_candidate.py']==sha(cd/'pack_model_candidate.py'),'actual final pack map')
 for rel,h in impl.items():source['generation_input_pins'][str(repo/rel)]=h
 # Complete original generation + tool inventory: old identity retained in ledger,
 # every local check operates actual small bytes. No claim of rehydrated runner data.
 originals=json.loads((old/'source_manifest.json').read_text())['generation_input_pins'];oldtools=json.loads((old/'tool_manifest.json').read_text())['pins'];inventory={};ledger=[];empty=[]
 for group,rows in [('generation',originals),('tools',oldtools)]:
  for i,(origin,h)in enumerate(rows.items()):
   p=out/'input_inventory'/group/(str(i)+'_'+P(origin).name);p.parent.mkdir(parents=True,exist_ok=True)
   raw=b''if h==hashlib.sha256(b'').hexdigest()else('ALL_SYNTHETIC_INPUT_SLOT\n'+origin+'\n'+h+'\n').encode();p.write_bytes(raw);inventory[str(p.resolve())]=sha(p);ledger.append(dict(group=group,origin_path=origin,origin_sha256=h,local=pin(p.resolve()),content_kind='REAL_EMPTY_BYTES'if not raw else'SYNTHETIC_SLOT_NOT_ORIGINAL_BYTES'))
   if not raw:empty.append(ledger[-1])
 need(len(originals)==13529 and len(empty)==2,'full original inventory shape')
 inventory.update(rolepins)
 # Emit actual small local header from the explicitly synthetic 122-port template.
 hp=P(next(p for p in dep['dependencies']if P(p).name=='VHostBlockTopV4.h'));hp.parent.mkdir(parents=True,exist_ok=True);hp.write_text(ev['actual_host_header']['text']);dep['dependencies'][str(hp)]=pin(hp);source['derived_generated_pins'][str(hp)]=sha(hp)
 # All metadata grammar templates remain internally pinned; no compilation occurs.
 phases=dep['compilation_phases']
 for phase in phases:
  p=P(phase['output']['path']);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'\x7fELF\x02\x01ALL_SYNTHETIC_NOT_EXECUTABLE'if phase['phase']=='host_link'else b'ALL_SYNTHETIC_ARCHIVE_NOT_LINKABLE');phase['output']=pin(p)
 dep['binary']=phases[-1]['output'];dep['host_link_receipt']=phases[-1]['supervisor'];source['p0_retained_evidence']['driver_dependency']=dep
 host=out/'synthetic.sv';host.write_bytes((root/'hardware.sv').read_bytes());source['sv_sha256']=sha(host);source['driver_sha256']=sha(driver)
 work=out/'work';run=work/'shared/build/frontend';run.mkdir(parents=True);pack=load_module('_actual_pack_under_test',cd/'pack_model_candidate.py')
 for name in pack.STAGES:
  r=copy.deepcopy(next((p['supervisor']for p in phases if p['phase']==name),json.loads(ev['actual_stage_receipts'][name]['text'])));p=run/name/'RESULT.json';write(p,r)
 obs['source_closure'].update(source_overlay={'bytes':overlay.stat().st_size,'sha256':sha(overlay)},source_count=len(ov['files']))
 obs['stage_receipts']=[dict(name=n,bytes=(run/n/'RESULT.json').stat().st_size,sha256=sha(run/n/'RESULT.json'))for n in pack.STAGES]
 obs['sv'].update(raw_sha256=sha(host),bytes=host.stat().st_size);obs['sv']['modules'][0].update(raw_sha256=sha(host),bytes=host.stat().st_size);obs['structure']['sv']={'bytes':host.stat().st_size,'sha256':sha(host)}
 public=repo/'candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json';public.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ORIG/'candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json',public)
 cat=repo/N/'SOURCE_PINS.json';write(cat,dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=[dict(path=str(p.relative_to(repo)),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(set(cd.glob('*.py'))|{cd/'MODEL_CANDIDATE_PRECONDITIONS.json',public,support/'seven_files.py',support/'TRANSFER_APPROVAL.json'})]))
 obs['source_closure']['source_pins_sha256']=sha(cat);obsp=out/'observation.json';write(obsp,obs);srcp=out/'source_manifest.json';write(srcp,source);toolp=out/'tool_manifest.json';write(toolp,tool)
 original=dict(repo=str(repo),repo_sha=source['source_commit'],artifact_identity=info['identity'],driver=str(driver),model_source_contract=str(contract),fixed_source_overlay=str(overlay),pins=rolepins)
 b=dict(cpp_build_policy=pack.CPP_POLICY,cpp_build_overrides=pack.CPP_OVERRIDES,pins=inventory,source_manifest=str(srcp),tool_manifest=str(toolp),admission=dict(cpp_build_policy=pack.CPP_POLICY,cpp_build_overrides=pack.CPP_OVERRIDES,make_closure_pins={str(hp):sha(hp)}))
 built=dict(status='BUILT_UNQUALIFIED',scope='ARCHIVE_LINK_ONLY_NOT_DUT_PASS',cpp_build_policy=pack.CPP_POLICY,cpp_build_overrides=pack.CPP_OVERRIDES,phases=copy.deepcopy(phases),binary=phases[-1]['output'],plan=dict(cpp_build_policy=pack.CPP_POLICY,cpp_build_overrides=pack.CPP_OVERRIDES,phases=[dict(name=p['phase'],argv=p['argv'])for p in phases]))
 built['phases'][-1]['driver_dependency']=dep
 # Real record import, no mock return/implementation, source hash retained below.
 sys.path.insert(0,str(cd));sys.modules.pop('model_source_evidence',None)
 negatives=[]
 def callpack():return pack.pack(original,b,built,host,overlay,run,lambda n:None,pin(obsp))
 def rejected(name):
  try:callpack()
  except (ValueError,FileNotFoundError)as e:
   negatives.append(dict(case=name,error_type=type(e).__name__,reason=str(e)[:180]));return
  raise AssertionError('negative accepted: '+name)
 empty_path=P(empty[0]['local']['path']);original_hash=inventory[str(empty_path)];inventory[str(empty_path)]='f'*64
 rejected('wrong_empty_source_hash');inventory[str(empty_path)]=original_hash
 hidden=empty_path.with_name(empty_path.name+'.temporarily_hidden');empty_path.rename(hidden)
 try:rejected('missing_source')
 finally:hidden.rename(empty_path)
 binary=P(built['binary']['path']);binary_bytes=binary.read_bytes();binary.write_bytes(b'')
 try:rejected('empty_artifact_stays_forbidden')
 finally:binary.write_bytes(binary_bytes)
 savedsource=b['source_manifest'];oversize=out/'OVERSIZE_METADATA_SYNTHETIC';
 with oversize.open('wb')as f:f.truncate((16<<20)+1)
 b['source_manifest']=str(oversize)
 try:rejected('source_metadata_cap_unchanged')
 finally:b['source_manifest']=savedsource
 role=actual_role_paths['helper'];saved=role.read_bytes();role.write_bytes(saved+b'// SYNTHETIC ROLE DRIFT\n');old_role_pin=rolepins[str(role)];rolepins[str(role)]=sha(role);inventory[str(role)]=sha(role)
 try:rejected('role_drift_even_when_general_pins_rehashed')
 finally:role.write_bytes(saved);rolepins[str(role)]=old_role_pin;inventory[str(role)]=old_role_pin
 result=callpack();payload=P(result['manifest']['path']).parent
 seven=pack.verify_candidate_seven(payload,info['identity'],result['manifest']['sha256']);finalsource=json.loads((payload/'source_manifest.json').read_text());need(len(finalsource['model_source_evidence']['files'])==12,'all12 real recorded roles')
 # Real export API, normal filesystem layout and full 8+20 strict receipts.
 for module_name in ('export_model_build','candidate_seven_files','pack_model_candidate','prepare_model_build','validate_model_launch','seven_files'):
  sys.modules.pop(module_name,None)
 exporter=load_module('_actual_export_under_test',cd/'export_model_build.py')
 need(sha(cd/'export_model_build.py')==sha(ORIG/C/'export_model_build.py'),'exact actual exporter source')
 for name in exporter.PREP:
  write(work/'shared/build'/('stage_'+name)/'RESULT.json',dict(native_exit=0,errors=[],cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True)))
 write(work/'BUILD_INVOCATION.json',dict(schema='MODEL_CANDIDATE_BUILD_INVOCATION_V1',artifact_identity=info['identity'],source_pins_sha256=sha(cat),job_started_monotonic=time.monotonic(),maximum_build_seconds=7200,whole_seconds=9000,numerical_pass=False))
 write(run/'stage_exits.json',[dict(name=n,native_exit=0)for n in pack.STAGES]);write(run/'BUILD_ONLY_RESULT.json',dict(status='UNREVIEWED_MODEL_BUILD',artifact=result))
 identity_path=out/'identity.json';write(identity_path,info['identity']);github_output=out/'GITHUB_OUTPUT';safe_export=out/'export_summary.json'
 env=dict(GITHUB_RUN_ID=str(info['identity']['run_id']),GITHUB_SHA=info['identity']['launch_commit'],GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(github_output));old_env={k:os.environ.get(k)for k in env};os.environ.update(env)
 args=types.SimpleNamespace(repo=repo,work=work,identity=identity_path,output=safe_export)
 export_negatives=[]
 def export_reject(name):
  try:exporter.run(args)
  except (ValueError,FileNotFoundError)as e:
   need(not safe_export.exists()and not github_output.exists(),'rejected export must not publish outputs')
   export_negatives.append(dict(case=name,error_type=type(e).__name__));return
  raise AssertionError('export accepted negative '+name)
 try:
  wrong=run/'frozen_artifact';payload.rename(wrong)
  try:export_reject('wrong_old_payload_directory')
  finally:wrong.rename(payload)
  # Unread old-layout bait must not be selected, even if it exists.
  wrong.mkdir();(wrong/'frozen_artifact.json').write_text('UNREAD_OLD_LAYOUT_BAIT')
  result_path=run/'BUILD_ONLY_RESULT.json';result_bytes=result_path.read_bytes();changed=json.loads(result_bytes)
  same_manifest=out/'same_bytes_wrong_manifest.json';same_manifest.write_bytes((payload/'frozen_artifact.json').read_bytes());changed['artifact']['manifest']['path']=str(same_manifest);write(result_path,changed)
  try:export_reject('self_reported_wrong_manifest_path_same_hash')
  finally:result_path.write_bytes(result_bytes)
  extra=payload/'unexpected.txt';extra.write_text('synthetic extra')
  try:export_reject('extra_payload')
  finally:extra.unlink()
  target=payload/'driver.cpp';saved=target.read_bytes();target.write_bytes(b'')
  try:export_reject('empty_payload')
  finally:target.write_bytes(saved)
  missing=payload.parent/'temporarily_hidden_driver';target.rename(missing)
  try:export_reject('missing_payload')
  finally:missing.rename(target)
  same_bytes=out/'same_bytes_external_driver.cpp';same_bytes.write_bytes(saved);target.unlink();target.symlink_to(same_bytes)
  try:export_reject('payload_symlink_same_exact_bytes')
  finally:target.unlink();target.write_bytes(saved)
  target.write_bytes(saved+b'// SYNTHETIC HASH DRIFT\n')
  try:export_reject('payload_hash_drift')
  finally:target.write_bytes(saved)
  os.environ['GITHUB_RUN_ID']=str(info['identity']['run_id']+1)
  try:export_reject('wrong_external_run_identity')
  finally:os.environ['GITHUB_RUN_ID']=env['GITHUB_RUN_ID']
  strict_path=work/'shared/build/stage_jdk/RESULT.json';strict_bytes=strict_path.read_bytes();v=json.loads(strict_bytes);v['log_capture']['pipe_eof_observed']=False;write(strict_path,v)
  try:export_reject('missing_strict_prep_eof')
  finally:strict_path.write_bytes(strict_bytes)
  # Original bug comparison: pinned old script outside reviewed source closure;
  # imports real current source-pins/verify gates, preserving that closure exactly.
  old_script=out/'ORIGINAL_OLD_EXPORTER.py';shutil.copyfile(old_exporter_path,old_script)
  old_summary=out/'OLD_EXPORT_SUMMARY_MUST_NOT_EXIST.json';old_github=out/'OLD_GITHUB_OUTPUT_MUST_NOT_EXIST'
  old_cli=[sys.executable,*(['-O']if sys.flags.optimize else[]),'-B',str(old_script),'--repo',str(repo),'--work',str(work),'--identity',str(identity_path),'--output',str(old_summary)]
  old_process=subprocess.run(old_cli,env=dict(os.environ,PYTHONPATH=str(cd),GITHUB_OUTPUT=str(old_github)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=False)
  need(old_process.returncode!=0 and not old_summary.exists()and not old_github.exists(),'old exact exporter must fail with original layout bug')
  need(b'independently expected manifest bytes'in old_process.stderr,'old exporter reached actual wrong-layout digest rejection')
  # Genuine exporter CLI process: actual argparse/import/source/strict/verify gates.
  cli=[sys.executable,*(['-O']if sys.flags.optimize else[]),'-B',str(cd/'export_model_build.py'),'--repo',str(repo),'--work',str(work),'--identity',str(identity_path),'--output',str(safe_export)]
  completed=subprocess.run(cli,env=dict(os.environ),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=False)
  need(completed.returncode==0,'export CLI native success: '+completed.stderr.decode(errors='replace')[-160:])
  need(safe_export.stat().st_size<=65536,'bounded CLI summary')
  exports=dict(line.split('=',1)for line in github_output.read_text().splitlines());need(exports==dict(artifact_dir=str(payload),artifact_name=info['identity']['artifact_name']),'GITHUB_OUTPUT exact directory and identity')
  workflow_paths=[]
  for wf in sorted((ORIG/'.github/workflows').glob('*.yml')):
   text=wf.read_text()
   if 'export_model_build.py'in text:
    workflow_paths.extend(re.findall(r'\$\{\{ steps\.export\.outputs\.artifact_dir \}\}/([A-Za-z0-9_.-]+)',text))
  need(len(workflow_paths)==7 and set(workflow_paths)==set(p.name for p in payload.iterdir()),'workflow exact seven paths from actual artifact_dir')
  need(all((P(exports['artifact_dir'])/n).is_file()and(P(exports['artifact_dir'])/n).stat().st_size>0 for n in workflow_paths),'workflow files all exist nonempty')
  exported=json.loads(safe_export.read_text());need(exported['payload']['manifest_sha256']==sha(payload/'frozen_artifact.json')and len(exported['stages'])==28,'export actual digest and8+20 strict stages')
 finally:
  for k,v in old_env.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
 safe=dict(scope='ALL_SYNTHETIC_CANDIDATE_PACK_EXPORT_E2E_NOT_ACTUAL_BUILD_OR_NUMERICAL_PASS',record_mocked=False,verifiers_mocked=False,final_source_mode=final_source,source_root=str(ORIG),actual_current_source_catalog=pin(source_catalog),actual_current_source_count=len(source_catalog_doc['files']),implementation_map=impl,negative_cases=negatives,export_negative_cases=export_negatives,export_source=pin(cd/'export_model_build.py'),export_summary_sha256=sha(safe_export),exported_stage_count=len(exported['stages']),export_cli_native_exit=completed.returncode,old_exporter_sha256=sha(old_script),old_exporter_cli_native_exit=old_process.returncode,old_exporter_no_outputs=True,old_exporter_failure_category='WRONG_LAYOUT_MANIFEST_DIGEST',export_cli_summary_bytes=safe_export.stat().st_size,old_layout_bait_preserved=(wrong/'frozen_artifact.json').read_text()=='UNREAD_OLD_LAYOUT_BAIT',workflow_exact_names=workflow_paths,github_output_artifact_dir_matches_actual=True,export_source_pins_gate_mocked=False,export_verify_mocked=False,original_generation_inventory_count=len(originals),original_tool_inventory_count=len(oldtools),local_pin_count=len(inventory),empty_inputs=empty,real_source_roles={k:pin(p)for k,p in actual_role_paths.items()},record_source=pin(cd/'model_source_evidence.py'),pack_source=pin(cd/'pack_model_candidate.py'),proof_source=pin(proof_path),seven=seven,payload_root=str(payload),actual_new_candidate_pass=False)
 write(out/'INVENTORY_PROVENANCE.json',ledger);write(out/'SAFE_RESULT.json',safe);print(json.dumps(safe,indent=2))
if __name__=='__main__':main()

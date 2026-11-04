"""CI-only fresh Scala compile, no elaboration, runtime, cache or upload.
Requires separately reviewed source revision and existing production runner-JDK provenance policy.
"""
import argparse,hashlib,json,os,pathlib,sys,re,subprocess,stat
P=pathlib.Path;HERE=P(__file__).resolve().parent
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def need(v,s):
 if not v:raise ValueError(s)
def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=P);p.add_argument('--candidate',required=True,type=P);p.add_argument('--output',required=True,type=P);p.add_argument('--java',required=True,type=P);p.add_argument('--identity',required=True,type=P);a=p.parse_args()
 repo=a.repo.resolve();candidate=a.candidate.resolve();output=a.output.resolve();java=a.java.resolve()
 identity=json.loads(a.identity.read_text())
 need(identity['schema']=='GDN32_COMPILE_JOB_IDENTITY_V1' and identity['nonce']=='gdn32_compile_only_20261104_once','exact launch identity')
 need(str(identity['run_id'])==os.environ.get('GITHUB_RUN_ID') and identity['launch_commit']==os.environ.get('GITHUB_SHA') and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','actual first owning job')
 need(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==identity['source_commit'],'exact reviewed source checkout')
 need(sha(repo/'.github/workflows/gdn32-compile-only.yml')==identity['workflow_sha256'],'workflow identity preserved in source checkout')
 need(not output.exists(),'fresh compile output required');output.mkdir(parents=True)
 # Fixed reviewed tooling hashes, not newly observed values as authority.
 pinfile=HERE/'TOOL_PINS.json';toolpins=json.loads(pinfile.read_text())
 for rel,h in toolpins['local'].items():need(sha(HERE/rel)==h,'local tool source drift')
 for rel,h in toolpins['repo'].items():need(sha(repo/rel)==h,'repository tool source drift')
 sys.path.insert(0,str(candidate));import select_sources
 selection=select_sources.select(repo,'gdn-chunk32-abort-v2');sources=selection['source_paths']
 need(len(sources)==162 and sources.count(selection['helper'])==1,'fresh unique162 including actual enabled helper')
 need(not selection['numeric_execution_authorized'] and selection['generation_identity']==identity['generation_sha256'],'new exact compile-only generation')
 sys.path.insert(0,str(HERE/'supervisor'));import supervise_multiroot
 original=repo/'candidates/fresh_original_top_recovery_20261028';restore=original/'restore_inputs.py';manifest=original/'SOURCE_AND_TOOLCHAIN_PINS.json';m=json.loads(manifest.read_text())
 env={k:os.environ[k] for k in ('GITHUB_RUN_ID','GITHUB_SHA','GITHUB_RUN_ATTEMPT','ImageVersion','ImageOS') if k in os.environ}
 env.update({'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
 caps=dict(wall_seconds=1200,cleanup_seconds=30,per_process_cpu_seconds=900,cpu_seconds=900,rss_bytes=2304<<20,per_process_as_bytes=8<<30,file_bytes=32<<20,log_bytes=8<<20,raw_log_bytes=8<<20,tree_bytes=160<<20,watch_tree_bytes=512<<20,extra_watch_roots=[str(original/'cache')],max_entries=20000,min_free_disk_bytes=2<<30,min_available_memory_bytes=3<<30,jdk_aliases=[],supervisor_rss_bytes=96<<20,combined_cpu_seconds=960)
 resource_gate={'min_available_memory':3<<30,'min_disk_free':2<<30}
 commonpins={str(a.identity.resolve()):sha(a.identity),str(manifest):sha(manifest),str(restore):sha(restore),str(pinfile):sha(pinfile)}
 for rel in toolpins['local']:commonpins[str(HERE/rel)]=sha(HERE/rel)
 # Same production provenance path: exact Eclipse Adoptium21.0.13+9,
 # existing fresh-host contract permits a newly inventoried runner image.
 # This trusts GitHub's official hosted image supply chain, not a preapproved
 # archive hash and not an inherited toolchain/numerical qualification.
 production=repo/'candidates/ci_frontend_materialization_r2_20261029'
 sys.path.insert(0,str(production));from fresh_host import reject_injection
 reject_injection(os.environ)
 contract=dict(schema='BOUNDED_FRESH_HOST_V1',run_id=identity['run_id'],source_commit=identity['source_commit'],launch_commit=identity['launch_commit'])
 contract_path=output/'FRESH_HOST_CONTRACT.json';contract_path.write_text(json.dumps(contract,sort_keys=True)+'\n')
 inventory_path=output/'JDK_INVENTORY.json';inventory_script=production/'inventory_runner_jdk.py'
 jdkpins=dict(commonpins);jdkpins[str(inventory_script)]=sha(inventory_script);jdkpins[str(production/'fresh_host.py')]=sha(production/'fresh_host.py');jdkpins[str(contract_path)]=sha(contract_path)
 jdkcaps=dict(caps,wall_seconds=120,per_process_cpu_seconds=60,cpu_seconds=60,combined_cpu_seconds=90,rss_bytes=512<<20)
 jdk=supervise_multiroot.execute([sys.executable,'-B',str(inventory_script),'--java-home',str(java.parent.parent),'--output',str(inventory_path),'--fresh-host-contract',str(contract_path),'--fresh-host-contract-sha256',sha(contract_path)],str(output/'jdk'),str(output/'owner.lock'),pins=jdkpins,caps=jdkcaps,env=env,resource_gate=resource_gate)
 (output/'JDK_RECEIPT.json').write_text(json.dumps(jdk,indent=2)+'\n');
 from safe_compile_summary import summarize_stage
 if jdk['status']!='PASS_PROCESS_ONLY':print(json.dumps(summarize_stage('JDK_INVENTORY',jdk,output/'jdk/frontend.log.gz',{}),sort_keys=True))
 need(jdk['status']=='PASS_PROCESS_ONLY','runner JDK inventory failed')
 inventory=json.loads(inventory_path.read_text());need(inventory['status']=='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION' and inventory['old_pass_transfer'] is False,'new JDK provenance only')
 aliases=[];home=java.parent.parent
 for row in inventory['files']:
  q=home/row['path']
  if 'symlink' in row:
   need(q.is_symlink() and os.readlink(q)==row['symlink'] and str(q.resolve(strict=True))==row['resolved_target'],'JDK alias drift')
   aliases.append(dict(path=str(q),link=row['symlink'],target=row['resolved_target']))
   if 'external_dependency' in row:
    e=row['external_dependency'];target=P(e['resolved_target']);need(row['path']=='lib/security/cacerts' and str(target)=='/etc/ssl/certs/adoptium/cacerts' and target.is_file() and not target.is_symlink() and target.stat().st_size==e['bytes'] and sha(target)==e['sha256'],'only bounded public JDK truststore external');commonpins[str(target)]=e['sha256']
  else:
   need(q.is_file() and q.stat().st_size==row['bytes'] and sha(q)==row['sha256'],'JDK tree drift');commonpins[str(q)]=row['sha256']
 commonpins[str(inventory_path)]=sha(inventory_path);commonpins[str(java)]=sha(java)
 caps['jdk_aliases']=aliases
 # Actual compile-only host inventory, including loader/libc and interpreter/
 # stdlib extension dependencies. No fake Verilator path or second scope.
 host_path=output/'HOST_INVENTORY.json';host_script=HERE/'fresh_compile_host.py'
 hostpins=dict(commonpins);hostpins[str(host_script)]=sha(host_script);hostpins[str(contract_path)]=sha(contract_path)
 hostcaps=dict(caps,wall_seconds=300,per_process_cpu_seconds=240,cpu_seconds=240,combined_cpu_seconds=270,rss_bytes=512<<20)
 host_receipt=supervise_multiroot.execute([sys.executable,'-B',str(host_script),'--contract',str(contract_path),'--contract-sha256',sha(contract_path),'--java-home',str(home),'--output',str(host_path)],str(output/'host'),str(output/'owner.lock'),pins=hostpins,caps=hostcaps,env=env,resource_gate=resource_gate)
 (output/'HOST_RECEIPT.json').write_text(json.dumps(host_receipt,indent=2)+'\n')
 from safe_compile_summary import summarize_stage
 if host_receipt['status']!='PASS_PROCESS_ONLY':print(json.dumps(summarize_stage('HOST_INVENTORY',host_receipt,output/'host/frontend.log.gz',{}),sort_keys=True))
 need(host_receipt['status']=='PASS_PROCESS_ONLY','actual host inventory failed')
 host=json.loads(host_path.read_text());need(host['schema']=='BOUNDED_FRESH_HOST_IDENTITY_V1' and host['contract']==contract and host['old_pass_transfer'] is False,'new host identity only')
 for path,h in host['pins'].items():need(sha(path)==h,'fresh host file drift')
 commonpins.update(host['pins']);commonpins[str(host_path)]=sha(host_path)
 host_aliases=host['aliases'];segments={r['path']:r for r in aliases}
 for raw,target in host_aliases.items():
  need(str(P(raw).resolve(strict=True))==target and target in host['pins'],'canonical host alias')
  for segment in (P(raw),*P(raw).parents):
   if segment.is_symlink():
    row=dict(path=str(segment),link=os.readlink(segment),target=str(segment.resolve(strict=True)))
    need(row['path'] not in segments or segments[row['path']]==row,'consistent alias segment');segments[row['path']]=row
 caps['jdk_aliases']=list(segments.values())
 def check_host_aliases():
  for raw,target in host_aliases.items():need(str(P(raw).resolve(strict=True))==target,'host alias drift')
  supervise_multiroot.verify_aliases(caps['jdk_aliases'])
 def execute_qualified(*args,**kwargs):
  check_host_aliases()
  try:return supervise_multiroot.execute(*args,**kwargs)
  finally:check_host_aliases()
 # Reuse repository's exact official Maven downloader; do NOT run the compiler
 # command it prints. All download bytes are hash/size checked there and below.
 fetchpins=dict(commonpins)
 for row in m['sources']:fetchpins[str(original/row['path'])]=row['sha256']
 fetchcaps=dict(caps,wall_seconds=600,per_process_cpu_seconds=60,cpu_seconds=60,combined_cpu_seconds=90,rss_bytes=256<<20,per_process_as_bytes=2<<30)
 fetch=execute_qualified([sys.executable,'-B',str(restore),'--download-jars','--java',str(java)],str(output/'fetch'),str(output/'owner.lock'),pins=fetchpins,caps=fetchcaps,env=env,resource_gate=resource_gate)
 (output/'FETCH_RECEIPT.json').write_text(json.dumps(fetch,indent=2)+'\n')
 if fetch['status']!='PASS_PROCESS_ONLY':print(json.dumps(summarize_stage('DEPENDENCIES',fetch,output/'fetch/frontend.log.gz',{}),sort_keys=True))
 need(fetch['status']=='PASS_PROCESS_ONLY','dependency stage failed')
 jars=[];plugin=None;pins=dict(commonpins)
 for row in m['jars']:
  q=original/'cache'/row['maven_path'];need(q.stat().st_size==row['bytes'] and sha(q)==row['sha256'],'jar integrity');pins[str(q)]=row['sha256']
  if row['role']=='plugin':need(plugin is None,'one official plugin');plugin=str(q)
  else:jars.append(str(q))
 need(plugin is not None,'official plugin required');cp=':'.join(jars)
 for s in sources:pins[s]=sha(s)
 for name in ('select_sources.py','GENERATION_CONTRACT.json','MODEL_SOURCE_OVERLAY.json','PUBLICATION_MANIFEST.json'):pins[str(candidate/name)]=sha(candidate/name)
 run=output/'compile';argv=[str(java),'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:+UseSerialGC','-Xms32m','-Xmx1536m','-XX:ReservedCodeCacheSize=64m','-XX:InitialCodeCacheSize=2m','-XX:CompressedClassSpaceSize=64m','-XX:MaxMetaspaceSize=192m','-Xss2m',f'-Djava.io.tmpdir={run}/tmp','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.',*sources]
 # Both classpaths contain ONLY official pinned JARs. No old project classes,
 # no earlier candidate leaf classes, no '.', no source-generated class cache.
 need(all(x.endswith('.jar') for x in cp.split(':')),'no project classes on compiler classpath')
 plan=dict(scope='FRESH_SCALA_COMPILE_ONLY_NOT_ELABORATION',generation_identity=selection['generation_identity'],source_count=162,argv=argv,pins=pins,caps=caps,old_class_reuse=False,numeric_execution_authorized=False)
 (output/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
 result=execute_qualified(argv,str(run),str(output/'owner.lock'),pins=pins,caps=caps,env=env,resource_gate=resource_gate)
 (output/'COMPILE_RECEIPT.json').write_text(json.dumps(result,indent=2)+'\n')
 classes=list(run.rglob('*.class'))
 # Safe stdout contains typed bounded numbers/hashes only, never raw logs,
 # compiler input text, environment, credentials, paths, FIRRTL or binaries.
 summary=dict(schema='GDN32_COMPILE_ONLY_SUMMARY_V1',status=result['status'],native_exit=result['native_exit'],generation_identity=selection['generation_identity'],source_count=162,fresh_class_count=len(classes),fresh_class_bytes=sum(p.stat().st_size for p in classes),elapsed_seconds=result['elapsed_seconds'],observed_peak_rss=result['observed_peak_rss'],elaboration_run=False,dut_run=False,numerical_pass=False)
 summary['diagnostics']=summarize_stage('SCALA_COMPILE',result,run/'frontend.log.gz',{p:str(P(p).relative_to(repo)) for p in sources})
 print(json.dumps(summary,sort_keys=True))
 need(result['status']=='PASS_PROCESS_ONLY' and classes,'fresh compile failed')
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'status':'FAIL_COMPILE_ONLY','error_class':type(e).__name__,'numerical_pass':False}));sys.exit(1)

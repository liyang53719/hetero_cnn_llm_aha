"""Explicit synthetic authority/ELF/receipts + actual immutable SV/retained inputs.
PREPARED ONLY: requires review and an external bounded supervisor to execute.
No model, compiler, download, mutations of existing inputs, or mocked validators.
"""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,resource,shutil,sys
P=pathlib.Path;E='candidates/same_job_execution_20261030';C='candidates/model_candidate_build_20261101'
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(P(p).read_text())
def pin(p):return dict(path=str(P(p).resolve()),bytes=P(p).stat().st_size,sha256=sha(p))
def put(p,v):
 p=P(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v if isinstance(v,bytes)else(json.dumps(v,indent=2)+'\n').encode());return pin(p)
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def catalog(repo):
 cp=repo/E/'SOURCE_PINS.json';files=[]
 for p in sorted(repo.rglob('*')):
  if p.is_file()and p!=cp and '__pycache__'not in p.parts:files.append(dict(pin(p),path=str(p.relative_to(repo))))
 return put(cp,dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=files)),{str(repo/r['path']):r['sha256']for r in files}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=P,required=True);ap.add_argument('--catalog-sha256',required=True);ap.add_argument('--original-binding',type=P,required=True);ap.add_argument('--original-binding-sha256',required=True);ap.add_argument('--payload',type=P,required=True);ap.add_argument('--output',type=P,required=True);a=ap.parse_args()
 repo=a.repo.resolve(strict=True);original=a.original_binding.resolve(strict=True);payload=a.payload.resolve(strict=True);w=a.output.absolute()
 need(not w.exists(),'fresh test output');need(sha(repo/E/'SOURCE_PINS.json')==a.catalog_sha256,'reviewed final joint catalog');need(sha(original)==a.original_binding_sha256,'approved original binding')
 need(shutil.disk_usage(w.parent).free >= (8<<30)+(256<<20),'8GiB reserve plus copy')
 mem={k:int(v.split()[0])*1024 for k,v in (line.split(':',1)for line in P('/proc/meminfo').read_text().splitlines())};need(mem['MemAvailable']>=7<<30,'old5 plus system1 plus test1 memory')
 resource.setrlimit(resource.RLIMIT_AS,(8<<30,)*2);resource.setrlimit(resource.RLIMIT_CPU,(60,)*2)
 w.mkdir();old=read(original);retained_pin=old['retained_materials'];ret=read(retained_pin['path']);need(sha(retained_pin['path'])==retained_pin['sha256'],'retained metadata actual pin')
 # C fixture creates actual frozen seven-file proof, only ELF/compiler metadata synthetic.
 sys.path.insert(0,str(repo/C));fixture=load('ff_join_pack_fixture',repo/C/'test_first_fault_pack_end_to_end.py');f=fixture.construct(w,payload,repo);r=f['repo'];e=r/E;n=e/'numeric';ctl=w/'control';ctl.mkdir()
 # Copy only reviewed source catalog files; inputs/weights are never copied.
 for row in read(repo/E/'SOURCE_PINS.json')['files']:
  src=repo/row['path'];need(src.stat().st_size==row['bytes']and sha(src)==row['sha256'],'joint source bytes');put(r/row['path'],src.read_bytes())
 cp,pins=catalog(r)
 # Refresh synthetic generation ledger to the actual augmented test repo closure before pack.
 b=f['binding'];b['pins'].update(pins);b['pins'][cp['path']]=cp['sha256'];put(ctl/'synthetic_fixture_pin_ledger.json',{'scope':'SYNTHETIC_TEST_SOURCE_PINS_NOT_EXECUTION_AUTHORITY','pins':b['pins']});src=read(b['source_manifest']);src['generation_input_pins'].update(pins);put(b['source_manifest'],src)
 obs=read(f['observation_pin']['path']);obs['source_closure']['source_pins_sha256']=cp['sha256'];f['observation_pin']=put(f['observation_pin']['path'],obs)
 root,verified=fixture.pack_and_verify(f);artifact=read(root/'frozen_artifact.json');source=read(root/'source_manifest.json');artifact_pin=pin(root/'frozen_artifact.json');ident=artifact['artifact_identity']
 # Use existing N fixture metadata recipes, not their simplified artifact as authority.
 os.environ['FIRST_FAULT_TEST_REPO']=str(repo);support=load('ff_join_support',repo/E/'numeric/test_support_first_fault.py');seed=support.build(w/'seed')
 review=copy.deepcopy(seed['review']);doc=copy.deepcopy(seed['doc']);contract=pin(r/C/'FIRST_FAULT_DRIVER_CONTRACT.json');probe=source['readonly_probe'];canon=lambda o:hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
 review.update(builder_identity=ident,artifact_manifest=artifact_pin,source_manifest_sha256=sha(root/'source_manifest.json'),observation_sha256=artifact['model_candidate_observation_sha256'],source_overlay=pin(r/C/'MODEL_SOURCE_OVERLAY.json'),source_contract=pin(n/'MODEL_P0_FIRST_FAULT_SOURCE_CONTRACT.json'))
 st=read(review['structural_review']['path']);st.update(artifact_manifest_sha256=artifact_pin['sha256'],observation_sha256=review['observation_sha256'],source_overlay_sha256=review['source_overlay']['sha256'],source_contract_sha256=review['source_contract']['sha256']);review['structural_review']=put(ctl/'structural.json',st)
 oldreview=read(old['model_candidate_review']['path']);dc=copy.deepcopy(oldreview['data_reference_contract']);dc.update(schema='MODEL_CANDIDATE_DATA_REFERENCE_ONLY_READONLY_DRIVER_V1',new_artifact_manifest_sha256=artifact_pin['sha256'],readonly_driver_contract_sha256=contract['sha256']);review['data_reference_contract']=dc
 doc.update(artifact_manifest_sha256=artifact_pin['sha256'],readonly_driver_contract=contract,readonly_probe_evidence_sha256=canon(probe));doc['stimulus']['retained_materials_sha256']=retained_pin['sha256']
 wr=read(doc['basis']['independent_watchdog_review']['path']);wr.update(artifact_manifest_sha256=artifact_pin['sha256'],readonly_driver_contract_sha256=contract['sha256']);doc['basis']['independent_watchdog_review']=put(ctl/'watchdog.json',wr);review['first_fault_diagnostic']=put(ctl/'diagnostic.json',doc);reviewpin=put(ctl/'review.json',review)
 # Canonical identity shape is synthetic and deliberately not an owner liveness claim.
 host=put(ctl/'host.json',dict(schema='CLOUD_EXECUTOR_HOST_OBSERVATION_V1',boot_id='11111111-1111-1111-1111-111111111111',architecture='x86_64',python_version=[3,12],avx512f=True,physical_memtotal_bytes=10<<30,observed_memavailable_bytes=8<<30,observed_monotonic=1))
 identity=dict(schema='CLOUD_EXECUTOR_IDENTITY_V1',source_commit=ident['source_commit'],execution_id='22222222-2222-2222-2222-222222222222',boot_id='11111111-1111-1111-1111-111111111111',controller_pid=12345,start_tick=123,host_identity_sha256=host['sha256'],started_monotonic=2)
 ev=put(ctl/'synthetic_review.json',{'scope':'SYNTHETIC_TEST_NOT_OPERATOR_EXECUTION_AUTHORITY'});mode=load('ff_join_mode',e/'execution_mode.py');cloud=load('ff_join_cloud',e/'cloud_budget.py')
 # Reuse the original well-tested E budget shape; all values explicitly synthetic.
 budget=dict(runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',archive_mode='READ_EXISTING_PINNED_ARCHIVES',runtime_reuse_manifest=put(ctl/'runtime_inventory.json',{'synthetic':True}),stage_resources={k:dict(rss_bytes=2684354560,as_bytes=2684354560)for k in ('install','reference')},resource_scope='CURRENT_HOST_P0_FIRST_FAULT_DIAGNOSTIC',consumer_address_space_bytes=512<<20,reserved_other_owner_bytes=5<<30,schema='FIVE_M128_CLOUD_LIFECYCLE_BUDGET_V1',ready=True,source_commit=identity['source_commit'],host_identity=host,artifact_manifest_sha256=artifact_pin['sha256'],basis=dict(resource_audit=ev,independent_review=ev),job_budget_seconds=12300,budgets=dict(archives=600,weights=3600,install=180,owner_bind=120,reference=180,provider=180,parent=600,calibration_seconds={str(i):300 for i in range(5)}),dut_rss_bytes=2684354560,dut_address_space_bytes=2684354560,numeric_reserved_increment_bytes=512<<20,execution_mode=mode.FIRST_FAULT,full_block_budget=None,model_candidate_review=reviewpin,retained_materials=retained_pin)
 budgetpin=put(ctl/'budget.json',budget);approval=put(ctl/'approval.json',dict(schema='OPERATOR_REVIEWED_CLOUD_INVOCATION_V1',approved=True,authority='USER_AUTHORIZED_OPERATOR_REVIEW',purpose=mode.FIRST_FAULT,source_commit=identity['source_commit'],budget_sha256=budgetpin['sha256'],artifact_manifest_sha256=artifact_pin['sha256'],model_candidate_review_sha256=reviewpin['sha256'],retained_materials_sha256=retained_pin['sha256'],execution_id=identity['execution_id'],host_identity_sha256=host['sha256'],review_evidence=ev))
 handoff=put(ctl/'handoff.json',dict(schema='VERIFIED_SEVEN_FILE_BUILD_HANDOFF_V1',scope='BUILD_BYTES_ONLY_REVALIDATE_EXECUTOR_ABI_AND_NUMERICS',builder_identity=ident,source_pins_sha256=cp['sha256'],artifact_manifest_sha256=artifact_pin['sha256'],artifact_expanded_bytes=sum(p.stat().st_size for p in root.iterdir()),remote_receipt=dict(artifact_id=1,archive_sha256='1'*64,verified_api_receipt_sha256='2'*64,source_commit=ident['source_commit'],run_id=ident['run_id']),numerical_pass=False,final_rtl_executed=False))
 job=w/'synthetic_job';job.mkdir();binding=dict(execution_context='CLOUD_EXECUTOR_V1',execution_mode=mode.FIRST_FAULT,full_block_budget=None,model_candidate_review=reviewpin,artifact_manifest=artifact_pin,artifact_identity=ident,builder_handoff=handoff,repo=str(r),source_pins=cp,pins=pins,retained_materials=retained_pin,identity=identity,cloud_budget=budgetpin,execution_approval=approval,job_root=str(job),profiles=list(range(5)))
 bp=ctl/'BINDING.json';put(bp,binding);admission=mode.admit(binding);ca=cloud.admit(binding)
 # Close synthetic consumer evidence via original required_acceptance/dut_evidence.
 sys.path.insert(0,str(n));accept=load('required_acceptance',n/'required_acceptance.py');sys.modules['required_acceptance']=accept;de=load('ff_join_evidence',n/'dut_evidence.py')
 out=job/'materials/numeric/profile0/material/dut_result';nr=job/'materials/numeric';out.mkdir(parents=True)
 leader=dict(pid=12346,start=456,group=12346);outer=dict(worker_started=True,native_exit=2,errors=[],owner_identity=leader,cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',owner_identity=leader,session=12346),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True));outerpin=put(nr/'runs/p0_dut/RESULT.json',outer)
 start=dict(schema='ACTUAL_DUT_POPEN_V1',binary_sha256=artifact['common']['binary']['sha256'],runtime_sha256='3'*64,pid=12347,consumer_pid=leader['pid'],consumer_start_tick=leader['start'],inherited_group=leader['group'],inherited_session=12346);put(out/'profile0.started.json',start)
 row=dict(profile=0,complete_block_tokens=128,exit_code=1,execution_evidence={},numerical_pass=False);inner=accept.evaluate(row);row.update(status=inner['status'],qualification=inner)
 original_limits=dict(address_space_bytes=12<<30,cpu_seconds=18000,wall_seconds=20000,file_bytes=64<<20,max_active_cycles=1000000000)
 ea=dict(execution_mode=mode.FIRST_FAULT,reviewed_budget_sha256=admission['reviewed_budget_sha256'],outer_cleanup_proof_required=True,stage_budget_sha256=None,first_fault_document_sha256=admission['reviewed_budget_sha256'],diagnostic_profiles=[0],original_limits=original_limits,effective_limits=cloud.consumer_resource_limits(mode.consumer_limits(original_limits,admission,0),ca),scope=review['scope'])
 report=dict(status='INCOMPLETE',layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',final_rtl_executed=False,numerical_pass=False,profiles=[row],artifact_manifest_sha256=artifact_pin['sha256'],runtime_bundle_sha256='4'*64,common=artifact['common'],matrix_macs=4096,vector_lanes=32,executor_identity=identity,artifact_identity=ident,builder_handoff_sha256=handoff['sha256'],model_candidate_review_sha256=reviewpin['sha256'],candidate_scope=review['scope'],execution_admission=ea,resource_admission=dict(consumer_pre_fork_soft_bytes=ca['consumer_address_space_bytes'],consumer_pre_fork_hard_bytes=ca['dut_address_space_bytes'],consumer_after_popen_hard_bytes=ca['consumer_address_space_bytes'],dut_hard_address_space_bytes=ca['dut_address_space_bytes'],group_rss_is_sampled=True));put(out/'RESULT.json',report)
 record=de.verify(out,0,artifact_pin['sha256'],'4'*64,start['binary_sha256'],start['runtime_sha256'],outerpin);put(nr/'PROFILE_0_DIAGNOSTIC.json',record);q=accept.aggregate([record])
 numeric=dict(execution_mode=mode.FIRST_FAULT,first_fault_document_sha256=admission['reviewed_budget_sha256'],diagnostic_profiles=[0],not_selected_profiles=[1,2,3,4],full_budget_sha256=None,stage_budget_sha256=None,actual_dut_reports=[record],qualification=q,status=q['status'],numerical_pass=False);np=put(nr/'RESULT.json',numeric)
 flow=dict(identity=identity,execution_approval=approval,artifact_identity=ident,execution_binding=pin(bp),builder_handoff=handoff,artifact_manifest=artifact_pin,numeric_result=np,retained_materials=retained_pin,model_candidate_review=reviewpin,scope=review['scope'],hardware_definitions=1,profiles=list(range(5)),execution_mode=mode.FIRST_FAULT,qualification=q,status=q['status'],transport_exit_code=mode.transport_exit(mode.FIRST_FAULT,q));put(job/'FLOW_RESULT.json',flow)
 parser=load('ff_join_parser',n/'first_fault_records.py');ss=parser.schema();values=[0]*114;values[next(i for i,z in enumerate(ss['signals'])if z['module']=='HostBlockTopV4'and z['sv_var']=='io_resetRequired')]=1
 log=parser.HEADER+'\nHOST_FIRST_FAULT_SLOT_V1 slot=previous_healthy valid=0 cycle=0 active_cycle=0 completions=0 values='+','.join(['0']*114)+'\nHOST_FIRST_FAULT_SLOT_V1 slot=current_fault valid=1 cycle=10 active_cycle=8 completions=1 values='+','.join(map(str,values))+'\n';put(out/'profile0.log',log.encode())
 # No foreign cached C validators: summary loads its own real source-pinned modules.
 for name in ('first_fault_probe','first_fault_policy','pack_model_candidate','first_fault_compilation','candidate_dependency_proof'):sys.modules.pop(name,None)
 summary=load('ff_join_summary',e/'summarize_cloud_execution.py');results={}
 def project():return summary.project(job,bp,sha(bp))
 results['positive']=project();need(results['positive']['status']=='VERIFIED_REAGGREGATED','full project positive');need(results['positive']['fault_snapshot']['status']=='PRESENT_VALID'and not results['positive']['numerical_pass'],'finite first-fault only')
 # Negative evidence has isolated mutations of synthetic files only.
 extra=nr/'runs/p1_dut/RESULT.json';put(extra,{'synthetic':True});results['extra_p1']=project();need(results['extra_p1']['status']=='UNAVAILABLE','unselected profile rejection');extra.unlink();extra.parent.rmdir()
 diagnostic=P(review['first_fault_diagnostic']['path']);raw=diagnostic.read_bytes();diagnostic.unlink();results['missing_doc']=project();need(results['missing_doc']['status']=='UNAVAILABLE','missing document rejection');diagnostic.write_bytes(raw)
 put(out/'profile0.log',(log+'HOST_FIRST_FAULT_UNKNOWN\n').encode());results['malformed_snapshot']=project();need(results['malformed_snapshot']['status']=='VERIFIED_REAGGREGATED'and results['malformed_snapshot']['fault_snapshot']['status']=='MALFORMED','malformed snapshot preserves closed result')
 put(w/'RESULT_SAFE.json',dict(scope='SYNTHETIC_CONTROL_FLOW_WITH_REAL_RETAINED_BYTES_NOT_DUT_EXECUTION',models_executed=False,eda_executed=False,numerical_pass=False,results=results));print('SYNTHETIC_FULL_PROJECT_JOIN_COMPLETE_NO_DUT_PASS')
if __name__=='__main__':main()

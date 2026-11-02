"""Pinned external MODEL_CANDIDATE review; never promotes a build to production.
The review hash is supplied by a trusted invocation and independently bound by
cloud budget/approval. File contents alone are not authentication. No execution.
"""
import hashlib,json,pathlib,re,types
P=pathlib.Path
SCHEMA='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
SCOPE='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL'
REVIEW_SCHEMA='INDEPENDENT_MODEL_CANDIDATE_EXECUTION_REVIEW_V1'
POLICY=['OPT_FAST=-O1','OPT_SLOW=-O1','OPT_GLOBAL=-O1','CXXFLAGS=-O1 -fno-fast-math -ffp-contract=off']
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def canonical_sha(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
def pin(row,limit):
 need(type(row)is dict and set(row)=={'path','bytes','sha256'},'exact candidate evidence pin')
 p=P(row['path']);need(p.is_absolute()and p==p.resolve()and all(not x.is_symlink()for x in(p,*p.parents))and p.is_file(),'canonical candidate evidence file')
 need(type(row['bytes'])is int and 0<row['bytes']<=limit and p.stat().st_size==row['bytes']and isinstance(row['sha256'],str)and re.fullmatch('[0-9a-f]{64}',row['sha256'])and sha(p)==row['sha256'],'bounded actual candidate evidence bytes')
 return p
def load(row,limit):return json.loads(pin(row,limit).read_text())
FIRST_FAULT_SCHEMA='MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1'
FIRST_FAULT_REVIEW='MODEL_CANDIDATE_FIRST_FAULT_REVIEW_V1'
FIRST_FAULT_SCOPE='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'
def first_fault_module(repo,catalog_pin):
 need(repo is not None and catalog_pin is not None,'diagnostic actual source authority required')
 catalog=load(catalog_pin,2<<20);need(catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','actual diagnostic source catalog')
 rel='candidates/same_job_execution_20261030/numeric/first_fault_driver_contract.py'
 rows=[r for r in catalog['files']if r['path']==rel];need(len(rows)==1,'unique diagnostic checker role')
 path=P(repo)/rel;need(path==P(__file__).resolve().with_name('first_fault_driver_contract.py'),'fixed local diagnostic checker')
 raw=pin(dict(rows[0],path=str(path)),1<<20).read_bytes()
 m=types.ModuleType('reviewed_first_fault_driver_contract');m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def verify_review(review_pin,artifact_manifest_pin,builder_identity,*,repo=None,current_source_pins_pin=None):
 r=load(review_pin,2<<20);f=load(artifact_manifest_pin,65536)
 first_fault=r.get('schema')==FIRST_FAULT_REVIEW
 scope=FIRST_FAULT_SCOPE if first_fault else SCOPE
 fields={'schema','status','scope','builder_identity','artifact_manifest','source_manifest_sha256','observation_sha256','source_overlay','source_contract','structural_review','data_reference_contract','numerical_pass','final_rtl_executed'}
 if first_fault:fields=fields|{'first_fault_diagnostic'}
 need(set(r)==fields and r['schema']==(FIRST_FAULT_REVIEW if first_fault else REVIEW_SCHEMA) and r['status']==('REVIEWED_FOR_P0_FIRST_FAULT_DIAGNOSTIC'if first_fault else'REVIEWED_FOR_MODEL_NUMERICAL_EVALUATION'),'independent candidate review, not observation self-approval')
 need(r['scope']==scope and r['numerical_pass']is False and r['final_rtl_executed']is False,'candidate review grants no numerical or final RTL result')
 need(r['builder_identity']==builder_identity==f['artifact_identity']and r['artifact_manifest']==artifact_manifest_pin,'exact reviewed builder and artifact')
 exact={'schema','status','cpp_build_policy','cpp_build_overrides','profiles','layer','matrix_macs','vector_lanes','moe_reference_contract','artifact_identity','common','tool_manifest','model_candidate_observation_sha256','numerical_pass','final_rtl_executed','model_numerical_evaluation_authorized','external_review_required'}
 if first_fault:exact=exact|{'readonly_probe_contract','scope'}
 need(set(f)==exact and f['schema']==(FIRST_FAULT_SCHEMA if first_fault else SCHEMA) and f['status']=='UNREVIEWED_MODEL_BUILD','separate immutable candidate artifact schema')
 if first_fault:need(f['scope']==FIRST_FAULT_SCOPE,'artifact diagnostic scope')
 need(f['profiles']==list(range(5))and all(type(x)is int for x in f['profiles'])and type(f['matrix_macs'])is int and f['matrix_macs']==4096 and type(f['vector_lanes'])is int and f['vector_lanes']==32,'unchanged five-profile shared hardware dimensions')
 need(f['layer']=='CHISEL_EMITTED_SV_NUMERICAL_BACKEND'and f['cpp_build_policy']=='CPP_O1_STRICT_V1'and f['cpp_build_overrides']==POLICY,'explicit generated SV backend strict compile policy')
 need(f['moe_reference_contract']=='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE','unchanged original routing')
 need(all(f[k]is False for k in('numerical_pass','final_rtl_executed','model_numerical_evaluation_authorized'))and f['external_review_required']is True,'builder cannot authorize itself')
 root=pin(artifact_manifest_pin,65536).parent;row=f['common']['source_manifest'];need(set(row)=={'path','bytes','sha256'}and row['path']=='source_manifest.json','fixed source manifest role')
 srcpin=dict(row,path=str(root/row['path']));source=load(srcpin,16<<20)
 need(r['source_manifest_sha256']==srcpin['sha256']and source['source_commit']==builder_identity['source_commit'],'actual candidate source manifest')
 observation=source['model_candidate_observation'];need(observation['schema']=='MODEL_CANDIDATE_OBSERVATION_V1'and observation['status']=='OBSERVED_UNREVIEWED','observations are not acceptance')
 need(r['observation_sha256']==f['model_candidate_observation_sha256']==canonical_sha(observation),'all actual observation bytes reviewed')
 overlay=load(r['source_overlay'],2<<20);contract=load(r['source_contract'],65536);structural=load(r['structural_review'],2<<20)
 need(overlay['schema']=='MODEL_SOURCE_OVERLAY_V1'and type(overlay['source_count'])is int and overlay['source_count']==len(overlay['files']),'explicit actual source closure count')
 closure=observation['source_closure'];need(closure['source_commit']==builder_identity['source_commit']and type(closure['source_count'])is int and closure['source_count']==overlay['source_count']and closure['source_overlay']=={k:r['source_overlay'][k]for k in('bytes','sha256')},'reviewed overlay equals actual observed source closure')
 need(contract['schema']==('MODEL_CANDIDATE_P0_FIRST_FAULT_OBSERVATION_CONTRACT_V1'if first_fault else'MODEL_CANDIDATE_P0_OBSERVATION_CONTRACT_V1'),'separate source/program observation contract')
 evidence=source['model_source_evidence'];need(evidence['schema']==('MODEL_CANDIDATE_P0_FIRST_FAULT_SOURCE_EVIDENCE_V1'if first_fault else'MODEL_CANDIDATE_P0_SOURCE_EVIDENCE_V1'),'actual recorded candidate source roles')
 embedded=evidence['contract'];raw=embedded['text'].encode();need(len(raw)==embedded['bytes']==r['source_contract']['bytes']and hashlib.sha256(raw).hexdigest()==embedded['sha256']==r['source_contract']['sha256'],'recorded exact new source contract')
 need(source['generation_input_pins'].get(embedded['path'])==embedded['sha256'],'actual source contract generation input pin')
 need(structural=={'schema':'MODEL_CANDIDATE_STRUCTURAL_REVIEW_V1','status':'VERIFIED_SOURCE_AND_ACTUAL_STRUCTURE_NOT_NUMERICAL','artifact_manifest_sha256':artifact_manifest_pin['sha256'],'observation_sha256':r['observation_sha256'],'source_overlay_sha256':r['source_overlay']['sha256'],'source_contract_sha256':r['source_contract']['sha256'],'matrix_macs':4096,'shared_vector_banks':1,'bank_alu_instances':32,'profiles':[0,1,2,3,4],'typed_port_count':122,'numerical_pass':False,'final_rtl_executed':False},'exact independent actual structural review')
 need(all(type(structural[k])is int for k in('matrix_macs','shared_vector_banks','bank_alu_instances','typed_port_count'))and all(type(x)is int for x in structural['profiles']),'typed structural counts, no bool aliases')
 roots=sorted({str(root),*[str(P(r[k]['path']).parent)for k in('source_overlay','source_contract','structural_review')],str(P(review_pin['path']).parent)})
 if first_fault:
  probe=first_fault_module(repo,current_source_pins_pin).verify_probe(r,artifact_manifest_pin,repo,current_source_pins_pin)
  roots=sorted(set(roots)|set(probe['roots']))
 return dict(r,roots=roots,artifact_manifest_sha256=artifact_manifest_pin['sha256'],model_candidate_review_sha256=review_pin['sha256'])
def verify(review_pin,b):
 need(b.get('execution_context')=='CLOUD_EXECUTOR_V1'and b.get('model_candidate_review')==review_pin,'explicit admitted candidate context')
 approval=load(b['execution_approval'],65536);budget=load(b['cloud_budget'],65536)
 need(approval.get('schema')=='OPERATOR_REVIEWED_CLOUD_INVOCATION_V1'and approval.get('approved')is True and approval.get('authority')=='USER_AUTHORIZED_OPERATOR_REVIEW','trusted operator invocation approval required')
 need(approval.get('model_candidate_review_sha256')==review_pin['sha256']and budget.get('model_candidate_review')==review_pin and approval.get('budget_sha256')==b['cloud_budget']['sha256'],'review independently pinned by approved budget')
 need(approval.get('source_commit')==b['identity']['source_commit']and approval.get('execution_id')==b['identity']['execution_id']and approval.get('artifact_manifest_sha256')==b['artifact_manifest']['sha256'],'same actual invocation authority')
 f=load(b['artifact_manifest'],65536)
 if f.get('schema')==FIRST_FAULT_SCHEMA:need(b.get('execution_mode')=='P0_FIRST_FAULT_DIAGNOSTIC'and approval.get('purpose')=='P0_FIRST_FAULT_DIAGNOSTIC'and budget.get('execution_mode')=='P0_FIRST_FAULT_DIAGNOSTIC','diagnostic review only explicit diagnostic mode')
 return verify_review(review_pin,b['artifact_manifest'],f['artifact_identity'],repo=b.get('repo'),current_source_pins_pin=b.get('source_pins'))

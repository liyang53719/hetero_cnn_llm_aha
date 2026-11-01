"""Required P0 coverage contract; does not execute DUT or reference arithmetic."""
import hashlib,importlib.util,json,pathlib,types
HERE=pathlib.Path(__file__).resolve().parent
CORRECTOR_SHA='77e948cdf9fa9e923ae3861d3505a93f3ecb44b204b03d56bd19a19a8037bb86'
CONTRACT_SHA='7b46242a1206f651e8fac111436b6cb515b6a69f981b6f01c1e1f26bd7f51f13'
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(v):
 p=pathlib.Path(v['path']);need(p.is_absolute() and p==p.resolve() and p.is_file() and all(not q.is_symlink()for q in(p,*p.parents)),'absolute regular policy pin');need(p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],'policy pin mismatch');return p

SCOPE='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL'
def reviewed_module(name,context):
 need(name in ('candidate_artifact_handoff','candidate_observation_contract'),'fixed candidate module role')
 catalog_path=pin(context['current_source_pins_pin']);need(catalog_path.stat().st_size<=2<<20,'bounded admitted catalog')
 catalog=json.loads(catalog_path.read_text());need(catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','reviewed current source catalog')
 relative='candidates/same_job_execution_20261030/numeric/'+name+'.py'
 rows=[r for r in catalog['files']if r['path']==relative];need(len(rows)==1,'unique candidate module source role')
 path=pathlib.Path(context['repo'])/relative
 need(path==HERE/(name+'.py')and path==path.resolve()and all(not q.is_symlink()for q in(path,*path.parents)),'actual admitted local module')
 raw=path.read_bytes();need(len(raw)==rows[0]['bytes']and hashlib.sha256(raw).hexdigest()==rows[0]['sha256'],'candidate module bytes before import')
 module=types.ModuleType('reviewed_'+name);module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__);return module

def admitted_context(context):
 # Only the caller's independently admitted invocation creates this mapping.
 # There is deliberately no bundle/CLI deserializer for this authority.
 need(type(context)is dict and context.get('candidate_scope')==SCOPE,'independently admitted model context required')
 review_path=pin(context['model_candidate_review']);need(review_path.stat().st_size<=2<<20,'bounded independent review')
 review=json.loads(review_path.read_text())
 contract=pin(context['model_source_contract'])
 # The external review pins builder provenance; the executor's fixed local role
 # is independently source-catalogued. Equal bytes do not rewrite either path.
 need(sha(contract)==CONTRACT_SHA,'fixed reviewed candidate source contract')
 local=HERE/'MODEL_P0_SOURCE_CONTRACT.json';relative='candidates/same_job_execution_20261030/numeric/MODEL_P0_SOURCE_CONTRACT.json'
 need(pathlib.Path(context['repo'])/relative==local,'fixed executor contract source role')
 local_pin=dict(path=str(local),bytes=context['model_source_contract']['bytes'],sha256=CONTRACT_SHA);pin(local_pin)
 catalog_path=pin(context['current_source_pins_pin']);need(catalog_path.stat().st_size<=2<<20,'bounded admitted contract catalog')
 catalog=json.loads(catalog_path.read_text());need(catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','reviewed current contract source catalog')
 rows=[r for r in catalog['files']if r['path']==relative]
 need(len(rows)==1 and set(rows[0])=={'path','bytes','sha256'}and rows[0]['bytes']==local_pin['bytes']and rows[0]['sha256']==CONTRACT_SHA,'exact admitted local contract bytes')
 need(review['scope']==SCOPE and review['source_contract']==context['model_source_contract']and review['builder_identity']['source_commit']==context['builder_identity']['source_commit']and review['source_manifest_sha256']==context['source_manifest_sha256'],'same independently reviewed source domain')
 return review

def source_view(manifest,context):
 admitted_context(context)
 e=manifest['model_source_evidence']
 need(set(e)=={'schema','contract','files','anchors','program_contract'}and e['schema']=='MODEL_CANDIDATE_P0_SOURCE_EVIDENCE_V1','exact candidate source evidence domain')
 raw=e['contract']['text'].encode();need(len(raw)==e['contract']['bytes']and hashlib.sha256(raw).hexdigest()==e['contract']['sha256']==CONTRACT_SHA,'actual embedded candidate contract')
 # Private projection for shared12-role checks; never rewrites the artifact.
 return dict(manifest,files=e['files'],observation_policy_bindings={'P0':dict(schema='MODEL_CANDIDATE_P0_SOURCE_LINK_V1',contract_sha256=CONTRACT_SHA,corrector_sha256=CORRECTOR_SHA,anchors=e['anchors'])},p0_retained_evidence={'program_contract':e['program_contract']})

def verify_build(manifest,common,identity,evidence,context):
 review=admitted_context(context)
 artifact_path=pin(context['artifact_manifest']);need(review['artifact_manifest']==context['artifact_manifest'],'reviewed candidate payload')
 artifact=json.loads(artifact_path.read_text());root=artifact_path.parent
 need(artifact_path.name=='frozen_artifact.json'and artifact['artifact_identity']==identity,'actual candidate builder identity')
 for key in common:
  row=artifact['common'][key];need(common[key]==dict(row,path=str(root/row['path'])),'same common payload '+key)
 need(json.loads(pin(common['source_manifest']).read_text())==manifest,'actual source manifest bytes')
 module=reviewed_module('candidate_artifact_handoff',context)
 receipt=json.loads(pin(common['build_receipt']).read_text())
 module.verify_compilation_policy(artifact,root,receipt,context['current_source_pins_pin'],context['repo'])
 need(set(evidence)=={'schema','files','driver_dependency'}and evidence['schema']=='MODEL_CANDIDATE_RETAINED_PRODUCER_EVIDENCE_V1','new candidate retained evidence domain')
 stage_rows=manifest['model_candidate_build_evidence']['actual_stage_receipts']
 expected={r['path']:r for r in stage_rows.values()}
 need(len(expected)==len(stage_rows)and set(evidence['files'])==set(expected),'all actual candidate stage evidence retained')
 for original,row in evidence['files'].items():
  path=pin(row);need(path.stat().st_size<=2<<20,'bounded retained stage receipt')
  raw=path.read_bytes();actual=expected[original]
  need(raw==actual['text'].encode()and len(raw)==actual['bytes']and hashlib.sha256(raw).hexdigest()==actual['sha256'],'exact actual stage copy')
 dep=json.loads(pin(evidence['driver_dependency']).read_text())
 need(dep==manifest['model_candidate_build_evidence']['driver_dependency'],'same actual candidate dependency retained in bundle')

def corrector(source_relocation):
 admitted_context(source_relocation)
 p=HERE/'correct_model_observation_policy.py';need(sha(p)==CORRECTOR_SHA,'reviewed r2 corrector source')
 need(sha(HERE/'MODEL_P0_SOURCE_CONTRACT.json')==CONTRACT_SHA,'reviewed independent contract')
 spec=importlib.util.spec_from_file_location('p0_model_corrector',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def relocation_records(manifest,repo,current_pins,current_catalog,source_relocation):
 """Pure byte/path projection, NOT execution approval. Caller admits invocation.
 Never modifies frozen origin_path or any generation/consumption evidence.
 """
 manifest=source_view(manifest,source_relocation)
 root=pathlib.Path(repo);need(root.is_absolute()and root==root.resolve()and root.is_dir()and all(not p.is_symlink()for p in(root,*root.parents)),'canonical admitted executor source root')
 need(sha(HERE/'MODEL_P0_SOURCE_CONTRACT.json')==CONTRACT_SHA,'locked original source contract')
 locked=json.loads((HERE/'MODEL_P0_SOURCE_CONTRACT.json').read_text())['sources']
 rows={}
 for r in manifest['files']:
  key=r['path'];rel=pathlib.PurePosixPath(key)
  need(not rel.is_absolute()and key==str(rel)and '..'not in rel.parts and key not in rows,'unique canonical artifact source path');rows[key]=r
 catalog={}
 need(current_catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','actual executor source catalog')
 for r in current_catalog['files']:
  need(r['path']not in catalog,'unique actual executor source catalog');catalog[r['path']]=r
 anchors=manifest['observation_policy_bindings']['P0']['anchors'];programs={'commands','descriptors','program_manifest'}
 need(set(anchors)==set(locked)and len(set(anchors.values()))==12,'all original distinct locked anchor roles')
 result={}
 for name,key in anchors.items():
  if name in programs:
   row=rows[key];expected='RUNTIME_ONLY_CONTRACT'if name=='program_manifest'else'RUNTIME_EXPECTATION_NOT_BUILD_INPUT'
   need(row['kind']==expected,'program anchors remain runtime-only, never relocated source')
   continue
  r=rows[key];need(r['kind']=='ACTUAL_BUILD_INPUT'and {k:r[k]for k in('bytes','sha256')}==locked[name],'exact locked actual source role')
  origin=r['origin_path'];need(manifest['generation_input_pins'].get(origin)==r['sha256'],'original builder origin generation pin unchanged')
  local=root/key;need(local.is_file()and local==local.resolve()and all(not p.is_symlink()for p in(local,*local.parents)),'canonical local source no aliases')
  need(key in catalog and catalog[key]['bytes']==r['bytes']and catalog[key]['sha256']==r['sha256']and current_pins.get(str(local))==r['sha256'],'same independently admitted source catalog and pin')
  row=dict(path=str(local),bytes=r['bytes'],sha256=r['sha256']);pin(row)
  result[name]=dict(relative_path=key,origin_path=origin,local=row)
 need(len(result)==9,'exact nine source anchors, no runtime programs relocated')
 return result

def source_links(manifest,policy,identity,common,evidence,source_relocation=None):
 verify_build(manifest,common,identity,evidence,source_relocation)
 manifest=source_view(manifest,source_relocation)
 need(manifest['source_commit']==identity['source_commit'],'actual shared artifact source commit')
 records=manifest['files'];need(type(records)is list,'source manifest explicit files')
 files={}
 for r in records:
  name=r['path'];p=pathlib.PurePosixPath(name)
  need(not p.is_absolute() and '..' not in p.parts and name not in files,'unique relative source manifest file')
  files[name]=r
 link=manifest['observation_policy_bindings']['P0']
 need(link['schema']=='MODEL_CANDIDATE_P0_SOURCE_LINK_V1' and link['contract_sha256']==CONTRACT_SHA and link['corrector_sha256']==CORRECTOR_SHA,'actual source manifest policy binding')
 anchors=link['anchors'];need(set(anchors)==set(policy['source_pins']),'all 12 actual artifact anchors')
 if source_relocation is not None:
  need(source_relocation['schema']=='ADMITTED_CLOUD_P0_SOURCE_RELOCATION_V1'and source_relocation['builder_source_commit']==identity['source_commit']and source_relocation['source_manifest_sha256']==common['source_manifest']['sha256'],'same independently admitted frozen source relocation')
  need(set(source_relocation['anchors'])==set(anchors)-{'commands','descriptors','program_manifest'},'exact nine admitted source roles')
 for name,p in policy['source_pins'].items():
  key=anchors[name];need(key in files,'anchor missing actual source manifest file: '+name)
  r=files[key];need(r['bytes']==p['bytes'] and r['sha256']==p['sha256'],'actual artifact anchor identity: '+name)
  expected_kind='RUNTIME_EXPECTATION_NOT_BUILD_INPUT' if name in ('commands','descriptors') else ('RUNTIME_ONLY_CONTRACT' if name=='program_manifest' else 'ACTUAL_BUILD_INPUT')
  need(r['kind']==expected_kind,'actual versus runtime-only role '+name)
  if name not in ('commands','descriptors','program_manifest'):
   if source_relocation is None:need(r['origin_path']==p['path'],'actual source role path '+name)
   else:
    local=source_relocation['anchors'][name]
    need(local==dict(relative_path=key,origin_path=r['origin_path'],local=p),'exact admitted original/local source domains '+name)
    need(manifest['generation_input_pins'].get(r['origin_path'])==r['sha256'],'original source generation pin '+name)
    path=pin(p);need(path==path.resolve()and all(not q.is_symlink()for q in(path,*path.parents)),'actual local source remains canonical')
 program_record=files[anchors['program_manifest']]
 retained_program=manifest['p0_retained_evidence']['program_contract'];raw=retained_program['text'].encode()
 need(len(raw)==retained_program['bytes']==program_record['bytes'] and hashlib.sha256(raw).hexdigest()==retained_program['sha256']==program_record['sha256'],'actual retained program bytes/hash')
 need(retained_program['path']==program_record['origin_path'] and manifest['generation_input_pins'].get(retained_program['path'])==retained_program['sha256'],'actual original program generation pin/path')
 program=json.loads(raw)
 for name,filename,lo,hi in [('commands','host_commands.bin','commandBase','commandLimit'),('descriptors','host_descriptors.bin','descriptorBase','descriptorLimit')]:
  row=files[anchors[name]];need(row['derived_from']==anchors['program_manifest'] and row['sha256']==program['table_sha256'][filename] and row['bytes']==program[hi]-program[lo],'runtime expected tables independently derived from original manifest')
 need(len(set(anchors.values()))==12,'12 distinct source/program anchors')

def validate(profile,common,identity,bundle_root,source_relocation=None):
 admitted_context(source_relocation)
 extras={'observation_policy','original_runtime','consumption_evidence'}
 if profile['id']!=0:
  need(not (extras&set(profile)),'P1-P4 cannot waive observations')
  return dict(status='NO_P0_OVERLAY_NOT_COVERAGE_ACCEPTANCE',required_hidden_gates={})
 need(extras<=set(profile),'P0 requires mandatory independently verified coverage sidecar')
 root=pathlib.Path(bundle_root).resolve()
 for key in extras:
  p=pin(profile[key]);need(p.resolve().is_relative_to(root),'policy/original runtime outside bundle output')
 policy_path=pin(profile['observation_policy']);need(policy_path.stat().st_size<=65536,'bounded policy sidecar')
 policy=json.loads(policy_path.read_text());m=corrector(source_relocation)
 need(policy['schema']=='P0_RESIDENT_OBSERVATION_CORRECTION_V1' and policy['status']=='CORRECTED_METADATA_ONLY_REQUIRED_GATES_INCOMPLETE','required policy status')
 need(policy['hardware_executed'] is False and policy['numeric_acceptance'] is False,'metadata-only policy')
 for field in ('zero_fill','reference_fill','other_ddr_borrowing','raw_payloads_read'):need(policy[field] is False,'no fabricated internal gate '+field)
 need(policy['corrector_source_sha256']==CORRECTOR_SHA and policy['independent_source_contract_sha256']==CONTRACT_SHA,'reviewed r2 policy source pins')
 for key,bkey in [('original_runtime','original_runtime'),('corrected_runtime','runtime'),('views','views')]:
  p=pin(profile[bkey]);need(all(policy[key][f]==profile[bkey][f] for f in ('path','bytes','sha256')),'sidecar/bundle '+key+' mismatch')
 for key in ('original_runtime','views'):need(policy[key]['unchanged'] is True,'original input retained')
 bindings={name:r['path'] for name,r in policy['source_pins'].items()}
 _,locked=m.anchors(bindings);need(locked==policy['source_pins'],'independent 12 source pins exact')
 for key in ('original_runtime','runtime','views'):need(pin(profile[key]).stat().st_size<=65536,'bounded runtime/view metadata')
 original=pin(profile['original_runtime']).read_bytes();corrected=pin(profile['runtime']).read_bytes();views=pin(profile['views'])
 m.verify_delta(original,corrected,profile['original_runtime']['sha256'],views)
 m.validate_views(views.read_bytes(),profile['views']['sha256'],bindings)
 need(policy['independent_original_runtime_semantic_sha256']==m.RUNTIME_SEMANTIC_SHA and policy['independent_input_weight_program_view_semantic_sha256']==m.VIEWS_SEMANTIC_SHA,'locked original runtime/view semantics')
 required={name:dict(required=True,actual_observation='UNOBSERVED',status='INCOMPLETE_INTERNAL_RESIDENT_VALUE_NOT_DDR_OBSERVED',reference_key='stage.mlp.'+name+'_proj.0',numeric_pass=False) for name in ('gate','up')}
 need(policy['required_hidden_gates']==required and policy['preserved_observation_count']==18,'required gates cannot be waived')
 need(policy['corrections']==['allocation gate rw -> virtual','allocation up rw -> virtual','omit observe PC16 gate','omit observe PC17 up'],'exact correction declaration')
 source=pin(common['source_manifest']);need(source.stat().st_size<=16*1024**2,'source manifest size cap')
 evidence_path=pin(profile['consumption_evidence']);need(evidence_path.stat().st_size<=65536,'bounded retained evidence index')
 evidence=json.loads(evidence_path.read_text());need(pin(evidence['driver_dependency']).resolve().is_relative_to(root),'dependency metadata outside selected bundle output')
 source_links(json.loads(source.read_text()),policy,identity,common,evidence,source_relocation)
 return dict(status='INCOMPLETE_REQUIRED_INTERNAL_GATES_UNOBSERVED',observation_policy=profile['observation_policy'],original_runtime=profile['original_runtime'],declared_ddr_observations=18,required_hidden_gates=required,coverage_acceptance=False,consumption_evidence=profile['consumption_evidence'],program_anchor_role='RUNTIME_ONLY_NOT_ELABORATION_INPUT')

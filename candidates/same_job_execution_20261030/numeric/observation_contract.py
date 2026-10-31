"""Required P0 coverage contract; does not execute DUT or reference arithmetic."""
import hashlib,importlib.util,json,pathlib
HERE=pathlib.Path(__file__).resolve().parent
CORRECTOR_SHA='dc2708cb5d258fff64f1e6aca4620ddd69d8410119f3aa00230a3e9fe907da58'
CONTRACT_SHA='ac2db97abc2dec264fd8e5d0eda06da11c1b955017075d7a2c79c49d1efdccd4'
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(v):
 p=pathlib.Path(v['path']);need(p.is_absolute() and p.is_file() and not p.is_symlink(),'absolute regular policy pin');need(p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],'policy pin mismatch');return p

def corrector():
 p=HERE/'correct_observation_policy.py';need(sha(p)==CORRECTOR_SHA,'reviewed r2 corrector source')
 need(sha(HERE/'LOCKED_SOURCE_CONTRACT.json')==CONTRACT_SHA,'reviewed independent contract')
 spec=importlib.util.spec_from_file_location('p0_locked_corrector_r2',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def source_links(manifest,policy,identity,common,evidence):
 proof_path=HERE/'consumption_proof.py';need(sha(proof_path)=='4c05ae18e34c41a3df1ee6690c12c39483df11bd7e9da6924498ee888e843e10','reviewed existing-producer consumption verifier')
 spec=importlib.util.spec_from_file_location('existing_producer_consumption',proof_path);proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)
 proof.validate(manifest,policy,identity,common,evidence)
 need(manifest['source_commit']==identity['source_commit'],'actual shared artifact source commit')
 records=manifest['files'];need(type(records)is list,'source manifest explicit files')
 files={}
 for r in records:
  name=r['path'];p=pathlib.PurePosixPath(name)
  need(not p.is_absolute() and '..' not in p.parts and name not in files,'unique relative source manifest file')
  files[name]=r
 link=manifest['observation_policy_bindings']['P0']
 need(link['schema']=='P0_RESIDENT_OBSERVATION_SOURCE_LINK_V2' and link['contract_sha256']==CONTRACT_SHA and link['corrector_sha256']==CORRECTOR_SHA,'actual source manifest policy binding')
 anchors=link['anchors'];need(set(anchors)==set(policy['source_pins']),'all 12 actual artifact anchors')
 for name,p in policy['source_pins'].items():
  key=anchors[name];need(key in files,'anchor missing actual source manifest file: '+name)
  r=files[key];need(r['bytes']==p['bytes'] and r['sha256']==p['sha256'],'actual artifact anchor identity: '+name)
  expected_kind='RUNTIME_EXPECTATION_NOT_BUILD_INPUT' if name in ('commands','descriptors') else ('RUNTIME_ONLY_CONTRACT' if name=='program_manifest' else 'ACTUAL_BUILD_INPUT')
  need(r['kind']==expected_kind,'actual versus runtime-only role '+name)
  if name not in ('commands','descriptors','program_manifest'):need(r['origin_path']==p['path'],'actual source role path '+name)
 program_record=files[anchors['program_manifest']]
 retained_program=manifest['p0_retained_evidence']['program_contract'];raw=retained_program['text'].encode()
 need(len(raw)==retained_program['bytes']==program_record['bytes'] and hashlib.sha256(raw).hexdigest()==retained_program['sha256']==program_record['sha256'],'actual retained program bytes/hash')
 need(retained_program['path']==program_record['origin_path'] and manifest['generation_input_pins'].get(retained_program['path'])==retained_program['sha256'],'actual original program generation pin/path')
 program=json.loads(raw)
 for name,filename,lo,hi in [('commands','host_commands.bin','commandBase','commandLimit'),('descriptors','host_descriptors.bin','descriptorBase','descriptorLimit')]:
  row=files[anchors[name]];need(row['derived_from']==anchors['program_manifest'] and row['sha256']==program['table_sha256'][filename] and row['bytes']==program[hi]-program[lo],'runtime expected tables independently derived from original manifest')
 need(len(set(anchors.values()))==12,'12 distinct source/program anchors')

def validate(profile,common,identity,bundle_root):
 extras={'observation_policy','original_runtime','consumption_evidence'}
 if profile['id']!=0:
  need(not (extras&set(profile)),'P1-P4 cannot waive observations')
  return dict(status='NO_P0_OVERLAY_NOT_COVERAGE_ACCEPTANCE',required_hidden_gates={})
 need(extras<=set(profile),'P0 requires mandatory independently verified coverage sidecar')
 root=pathlib.Path(bundle_root).resolve()
 for key in extras:
  p=pin(profile[key]);need(p.resolve().is_relative_to(root),'policy/original runtime outside bundle output')
 policy_path=pin(profile['observation_policy']);need(policy_path.stat().st_size<=65536,'bounded policy sidecar')
 policy=json.loads(policy_path.read_text());m=corrector()
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
 source_links(json.loads(source.read_text()),policy,identity,common,evidence)
 return dict(status='INCOMPLETE_REQUIRED_INTERNAL_GATES_UNOBSERVED',observation_policy=profile['observation_policy'],original_runtime=profile['original_runtime'],declared_ddr_observations=18,required_hidden_gates=required,coverage_acceptance=False,consumption_evidence=profile['consumption_evidence'],program_anchor_role='RUNTIME_ONLY_NOT_ELABORATION_INPUT')

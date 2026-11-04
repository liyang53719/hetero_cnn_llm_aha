"""Bounded same-run observations. Integrity is not structural/numeric approval."""
import hashlib,json,pathlib,re
from candidate_generation_gate import require_generation_binding
from observe_model_sv import SCANNER_SHA,INVENTORY_SHA
P=pathlib.Path
STAGES=('compile_model_sources','helper_compile','original_high','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4','archive_bf16_context_lane_cluster16_rev8b_b_candidate_d','archive_qwen2_matrix_command_endpoint_0','archive_TransposedDenseDownOwner','host_archive','host_link')
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p,cap=2<<20):
 p=P(p);need(p.is_file()and not any(q.is_symlink()for q in(p,*p.parents))and 0<p.stat().st_size<=cap,'bounded regular observation');return json.loads(p.read_text())
def hex64(x):return type(x)is str and re.fullmatch('[0-9a-f]{64}',x)is not None
def verify_sv_observation(d,host):
 keys={'schema','status','phase','scope','raw_sha256','actual_normalized_sha256','bytes','counts','modules','scanner_sha256','inventory_sha256','numerical_pass','sv_accepted'}
 need(set(d)==keys and d['schema']=='MODEL_CANDIDATE_SV_OBSERVATION_V1'and d['status']=='OBSERVED_UNREVIEWED'and d['phase']=='complete','complete candidate SV observation')
 need(d['numerical_pass']is False and d['sv_accepted']is False and d['scanner_sha256']==SCANNER_SHA and d['inventory_sha256']==INVENTORY_SHA,'non-authorizing exact scanner')
 host=P(host);need(host.is_file()and not host.is_symlink()and host.stat().st_size==d['bytes']and sha(host)==d['raw_sha256']and hex64(d['actual_normalized_sha256']),'same actual generated SV')
 need(type(d['modules'])is list and 0<len(d['modules'])<=2048,'complete bounded module inventory')
 names=[]
 for row in d['modules']:
  need(set(row)=={'module','bytes','raw_sha256','normalized_sha256','sourceinfo_count'}and type(row['module'])is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_$]{0,127}',row['module']),'typed module observation')
  need(all(hex64(row[k])for k in ('raw_sha256','normalized_sha256'))and type(row['bytes'])is int and row['bytes']>0 and type(row['sourceinfo_count'])is int and row['sourceinfo_count']>=0,'bounded module hashes/counts');names.append(row['module'])
 need(len(set(names))==len(names)and sum(r['bytes']for r in d['modules'])==d['bytes'],'exhaustive unique module bytes')
 return d

def collect_observation(b,out,host):
 contract=require_generation_binding(b);out=P(out)
 detail=read(out/'canonical_full/details.json');ports=read(out/'emit_host/model-low-ports.json',128<<10);structure=read(out/'emit_host/model-structure.json');sv=verify_sv_observation(read(out/'sv_identity/sv-identity.json'),host)
 need(set(detail)=={'schema','scope','main','high','annotations','canonical_tsv','circuit_sha256','modules'}and detail['schema']=='MODEL_CANDIDATE_HIGH_DESCRIPTOR_V1'and detail['main']=='HostBlockTopV4','actual HIGH descriptor')
 for key,path in [('high',out/'original_high/host-diagnostic/original-high.fir'),('canonical_tsv',out/'canonical_full/canonical.tsv')]:
  need(set(detail[key])=={'bytes','sha256'}and path.stat().st_size==detail[key]['bytes']and sha(path)==detail[key]['sha256'],'descriptor actual file binding')
 ann=detail['annotations'];need(set(ann)=={'bytes','sha256','count','target_dir_count','ordered_sha256','ordered_bytes'}and ann['target_dir_count']==1,'actual annotation scope')
 rawann=out/'original_high/host-diagnostic/high-annotations.json';ordered=out/'canonical_full/ordered-annotations.json'
 need(sha(rawann)==ann['sha256']and rawann.stat().st_size==ann['bytes']and sha(ordered)==ann['ordered_sha256']and ordered.stat().st_size==ann['ordered_bytes']<=2<<20,'all annotation bytes preserved')
 ordered_text=ordered.read_text();ordered_values=json.loads(ordered_text);need(type(ordered_values)is list and len(ordered_values)==ann['count']-1,'ordered complete annotations excluding TargetDir only')
 need(ports['schema']=='MODEL_CANDIDATE_LOW_PORTS_OBSERVATION_V1'and ports['abi_accepted_for_execution']is False and len(ports['ports'])==122,'observed typed ABI not execution permission')
 need(structure['schema']=='MODEL_CANDIDATE_STRUCTURE_OBSERVATION_V1'and structure['numerical_pass']is False and structure['post_build_structure_accepted']is False and structure['preconditions_sha256']==contract['unchanged_module_contract_sha256'],'fixed generation constraints not acceptance')
 need(structure['sv']=={'bytes':sv['bytes'],'sha256':sv['raw_sha256']},'structure/scan same actual SV')
 shape=structure['structure'];need(shape['shared_vector_bank_instances']==1 and shape['bank_alu_instances']==32,'actual root-reachable original shared bank')
 stages=[]
 for name in STAGES:
  p=out/name/'RESULT.json';r=read(p,2<<20);need(r['native_exit']==0 and r['errors']==[]and r['cleanup_proof']['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and r['log_capture']['pipe_eof_observed']is True and r['log_capture']['gzip_finalized']is True,'strict actual candidate stage '+name)
  stages.append({'name':name,'bytes':p.stat().st_size,'sha256':sha(p)})
 from candidate_generation_gate import MODEL162_SOURCE,MODEL162_CATALOG_REL
 overlay=P(b['fixed_source_overlay']);repo=P(b['repo']);catalog=repo/(MODEL162_CATALOG_REL if b.get('hardware_source')==MODEL162_SOURCE else 'candidates/same_job_execution_20261030/SOURCE_PINS.json')
 d={'schema':'MODEL_CANDIDATE_OBSERVATION_V1','status':'OBSERVED_UNREVIEWED','source_closure':{'source_commit':b['repo_sha'],'source_count':contract['source_count'],'source_overlay':{'bytes':overlay.stat().st_size,'sha256':sha(overlay)},'generation_contract_sha256':b['generation_contract_sha256'],'source_pins_sha256':sha(catalog)},'high':detail,'annotations':{**ann,'ordered_json_text':ordered_text},'low_ports':ports,'sv':sv,'structure':structure,'stage_receipts':stages}
 raw=(json.dumps(d,indent=2,allow_nan=False)+'\n').encode();need(len(raw)<=8<<20,'complete bounded observation within16MiB package budget')
 p=out/'MODEL_CANDIDATE_OBSERVATION.json'
 with p.open('xb')as f:f.write(raw)
 return {'path':str(p.resolve()),'bytes':len(raw),'sha256':sha(p)}

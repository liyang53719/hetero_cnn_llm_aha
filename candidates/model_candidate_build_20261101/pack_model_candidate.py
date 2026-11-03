"""Seven-file MODEL_CANDIDATE bytes only. Never grants numerical execution.
The observation is integrity-bound, NOT an accepted canonical/RTL baseline.
No subprocess, network, ELF execution, weight/reference or raw-log collection.
"""
import hashlib,json,pathlib,re,shutil,importlib.util
P=pathlib.Path
DRIVER_SHA='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61'
CPP_POLICY='CPP_O1_STRICT_V1'
CPP_OVERRIDES=['OPT_FAST=-O1','OPT_SLOW=-O1','OPT_GLOBAL=-O1','CXXFLAGS=-O1 -fno-fast-math -ffp-contract=off']
NAMES={'binary':'dut.bin','sv':'hardware.sv','driver':'driver.cpp','source_manifest':'source_manifest.json','tool_manifest':'tool_manifest.json','build_receipt':'build_receipt.json'}
STAGES=('compile_model_sources','helper_compile','original_high','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4','archive_bf16_context_lane_cluster16_rev8b_b_candidate_d','archive_qwen2_matrix_command_endpoint_0','archive_TransposedDenseDownOwner','host_archive','host_link')
MANIFEST_SCHEMA='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
STATUS='UNREVIEWED_MODEL_BUILD'
ROUTE='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE'
OBS_SECTIONS={'source_closure','high','annotations','low_ports','sv','structure','stage_receipts'}

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def regular(p,cap=4<<30):
 p=P(p).absolute();need(p==p.resolve(strict=True) and p.is_file() and not p.is_symlink(),'canonical regular file')
 need(0<p.stat().st_size<=cap,'bounded regular file');return p
def pin(p):
 p=regular(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def json_file(p,cap):
 p=regular(p,cap)
 def pairs(rows):
  d={}
  for k,v in rows:
   need(k not in d,'duplicate JSON key');d[k]=v
  return d
 return json.loads(p.read_text(),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
PACK_PHASES=('IDENTITY','SOURCE_PINS','OBSERVATION','STAGE_RECEIPTS','COMPILE_OUTPUTS','ENRICH','COPY','FINAL')
PACK_REASONS=('SOURCE_PIN_SET','SOURCE_PIN_HASH_FORMAT','SOURCE_PIN_PATH','SOURCE_PIN_SIZE','SOURCE_PIN_HASH_MISMATCH','STAGE_VALIDATION_FAILED')
PACK_EXCEPTION_CLASSES=('ValueError','TypeError','FileNotFoundError','PermissionError','OSError','JSONDecodeError','UnicodeDecodeError','OTHER')
class ModelPackFailure(ValueError):
 def __init__(self,phase,reason,exception_class='ValueError',index=None,size=None,expected=None,actual=None):
  super().__init__('model candidate pack rejected: '+reason)
  self.model_pack_diagnostic=dict(schema='MODEL_PACK_FAILURE_V1',phase=phase,reason=reason,exception_class=exception_class if exception_class in PACK_EXCEPTION_CLASSES else 'OTHER',index=index,bytes=size if type(size)is int and 0<=size<=4<<30 else None,expected_sha256=expected,actual_sha256=actual)
def check_pins(pins):
 # Source/tool inputs may legitimately be empty; seven payload files still use
 # unchanged regular()/pin()/json_file() nonempty gates. Never trust just size.
 if type(pins)is not dict or not pins:raise ModelPackFailure('SOURCE_PINS','SOURCE_PIN_SET')
 for index,(raw,h)in enumerate(pins.items()):
  if type(h)is not str or re.fullmatch('[0-9a-f]{64}',h)is None:raise ModelPackFailure('SOURCE_PINS','SOURCE_PIN_HASH_FORMAT',index=index)
  try:
   if type(raw)is not str:raise ValueError('source path type')
   p=P(raw).absolute()
   if p!=p.resolve(strict=True)or not p.is_file()or p.is_symlink():raise ValueError('source regular path')
   size=p.stat().st_size
  except (ValueError,TypeError,OSError)as e:raise ModelPackFailure('SOURCE_PINS','SOURCE_PIN_PATH',type(e).__name__,index=index,expected=h)from e
  if not 0<=size<=4<<30:raise ModelPackFailure('SOURCE_PINS','SOURCE_PIN_SIZE',index=index,size=size,expected=h)
  try:actual=sha(p)
  except OSError as e:raise ModelPackFailure('SOURCE_PINS','SOURCE_PIN_PATH',type(e).__name__,index=index,size=size,expected=h)from e
  if actual!=h:raise ModelPackFailure('SOURCE_PINS','SOURCE_PIN_HASH_MISMATCH',index=index,size=size,expected=h,actual=actual)
def identity(i):
 need(type(i)is dict and set(i)=={'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'},'builder identity fields')
 need(type(i['run_id'])is int and i['run_id']>0,'actual run id')
 for k in ('source_commit','launch_commit','launch_manifest_blob_sha'):need(type(i[k])is str and re.fullmatch('[0-9a-f]{40}',i[k]),'git identity')
 need(i['source_commit']!=i['launch_commit'],'source and launch identity distinct')
 need(type(i['artifact_name'])is str and re.fullmatch('[A-Za-z0-9_.-]{1,128}',i['artifact_name']),'artifact name')
 need(type(i['launch_manifest_path'])is str and re.fullmatch('ci_launch/[A-Za-z0-9_.-]+\\.json',i['launch_manifest_path']),'launch path')
def strict(r):
 need(type(r)is dict and r.get('native_exit')==0 and type(r.get('native_exit'))is int and r.get('errors')==[],'strict native zero')
 need(r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','strict cleanup')
 need(r.get('log_capture',{}).get('pipe_eof_observed')is True and r.get('log_capture',{}).get('gzip_finalized')is True,'strict captured EOF')
ADDRESS_GENERATION_SHA='0a5e09a27a447b028697a631e5207fc0af6cae15d4c324a55524f9d41a46a753'
ADDRESS_OVERLAY_SHA='5ff6c6ee4887700b79f8bd3982250743575c3e3624d294d240b7bd92378bfc02'
ADDRESS_SOURCE_DIR='candidates/transposed_tile_address_fix_20261103'
SUPPLY_GENERATION_SHA='d6b8f476cb4f586ff47a44d4f2155891f15e3bac99f56e45039c459093feaabb'
SUPPLY_OVERLAY_SHA='a43e536bc0d0af808429f0730e4ad5fd6f949f4b4e1deb8194c1518eeacb521b'
SUPPLY_SOURCE_DIR='candidates/prefill_supply_overlap_20261103'
SOURCE_GENERATIONS={'transposed-tile-address-v1':(ADDRESS_GENERATION_SHA,ADDRESS_OVERLAY_SHA,ADDRESS_SOURCE_DIR),'prefill-supply-overlap-v1':(SUPPLY_GENERATION_SHA,SUPPLY_OVERLAY_SHA,SUPPLY_SOURCE_DIR)}
PRECONDITIONS_SHA='80c1426efa4a8f2740dadc1757a35d01913233e86c5fc5c2a35f9d3a8d044f0e'
SCANNER_SHA='b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b'
INVENTORY_SHA='685b15b4f9bee8d23ac25ffc7d26aa718d55621e5fe1b9b2f3519669f24768d4'
def hex64(v):return type(v)is str and re.fullmatch('[0-9a-f]{64}',v)is not None
def sizehash(v):
 need(type(v)is dict and set(v)=={'bytes','sha256'}and type(v['bytes'])is int and 0<v['bytes']<=4<<30 and hex64(v['sha256']),'bounded size/hash')
def named_hashes(rows):
 need(type(rows)is list and 0<len(rows)<=4096,'bounded module rows');names=[]
 for r in rows:
  need(type(r)is dict and set(r)=={'name','sha256'}and type(r['name'])is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_$]{0,127}',r['name'])and hex64(r['sha256']),'module identity');names.append(r['name'])
 need(len(set(names))==len(names),'unique module names')
def source_generation(c):
 matches=[(name,pair)for name,pair in SOURCE_GENERATIONS.items()if c.get('generation_contract_sha256')==pair[0]or c.get('source_overlay',{}).get('sha256')==pair[1]]
 if not matches:return None
 need(len(matches)==1,'one new source generation pair')
 name,(generation,overlay,directory)=matches[0]
 need(c.get('generation_contract_sha256')==generation and c.get('source_overlay',{}).get('sha256')==overlay and type(c.get('source_count'))is int and c['source_count']==159,'new hardware generation/overlay exact pair')
 return name,generation,overlay,directory

def address_generation_observation(c):
 """Known new source pairs only; never learn from emitted IR/SV."""
 return source_generation(c)is not None

def address_source_identity(source,obs,readonly=False):
 selected=source_generation(obs['source_closure'])
 if selected is None:return
 _,generation,overlay_sha,directory=selected
 need(readonly is False and 'readonly_probe'not in source,'new hardware is not unchanged-SV diagnostic evidence')
 pins=source.get('generation_input_pins');need(type(pins)is dict,'new hardware full generation input pins')
 suffix='/'+directory+'/GENERATION_CONTRACT.json'
 matches=[p for p in pins if p.endswith(suffix)];need(len(matches)==1 and pins[matches[0]]==generation,'new hardware pinned generation contract')
 repo=matches[0][:-len(suffix)];need(repo.startswith('/')and str(P(repo))==repo and '..'not in P(repo).parts,'canonical new hardware producer root')
 overlay=repo+'/'+directory+'/MODEL_SOURCE_OVERLAY.json'
 need(source.get('fixed_source_overlay')==overlay and pins.get(overlay)==overlay_sha,'new hardware exact selected overlay identity')
 pre=repo+'/candidates/model_candidate_build_20261101/MODEL_CANDIDATE_PRECONDITIONS.json'
 need(pins.get(pre)==PRECONDITIONS_SHA,'new hardware preserves reviewed physical/interface preconditions')
 evidence=source.get('model_candidate_build_evidence',{}).get('fixed_source_overlay',{})
 text=evidence.get('text');need(type(text)is str and evidence.get('path')==overlay and evidence.get('sha256')==overlay_sha and evidence.get('bytes')==len(text.encode()) and hashlib.sha256(text.encode()).hexdigest()==overlay_sha,'new hardware retained exact overlay bytes')
 rows=json.loads(text)['files'];need(len(rows)==159,'new hardware actual159 selected source rows')
 for row in rows:need(pins.get(repo+'/'+row['repo_path'])==row['sha256'],'new hardware all159 source inputs pinned')

def validate_observation(o):
 need(type(o)is dict and set(o)=={'schema','status',*OBS_SECTIONS},'observation exact sections')
 need(o['schema']=='MODEL_CANDIDATE_OBSERVATION_V1'and o['status']=='OBSERVED_UNREVIEWED','observation not acceptance')
 prepath=P(__file__).with_name('MODEL_CANDIDATE_PRECONDITIONS.json');need(sha(prepath)==PRECONDITIONS_SHA,'fixed preconditions source bytes');pre=json_file(prepath,2<<20)
 c=o['source_closure'];need(type(c)is dict and set(c)=={'source_commit','source_count','source_overlay','generation_contract_sha256','source_pins_sha256'},'source closure fields')
 need(type(c['source_commit'])is str and re.fullmatch('[0-9a-f]{40}',c['source_commit'])and type(c['source_count'])is int and c['source_count']==159,'actual159 closure')
 sizehash(c['source_overlay']);need(hex64(c['generation_contract_sha256'])and hex64(c['source_pins_sha256']),'source contracts');address_generation_observation(c)
 h=o['high'];need(type(h)is dict and set(h)=={'schema','scope','main','high','annotations','canonical_tsv','circuit_sha256','modules'},'HIGH exact fields')
 need(h['schema']=='MODEL_CANDIDATE_HIGH_DESCRIPTOR_V1'and h['scope']=='OBSERVED_UNREVIEWED_NOT_NUMERICAL_OR_STRUCTURE_ACCEPTANCE'and h['main']=='HostBlockTopV4'and hex64(h['circuit_sha256']),'HIGH identity')
 sizehash(h['high']);sizehash(h['canonical_tsv']);named_hashes(h['modules'])
 a=o['annotations'];ak={'bytes','sha256','count','target_dir_count','ordered_sha256','ordered_bytes'}
 need(type(a)is dict and set(a)==ak|{'ordered_json_text'}and h['annotations']=={k:a[k]for k in ak},'exact annotation identity')
 sizehash({k:a[k]for k in ('bytes','sha256')});need(type(a['count'])is int and 0<a['count']<=100000 and type(a['target_dir_count'])is int and a['target_dir_count']==1,'annotation counts')
 text=a['ordered_json_text'];need(type(text)is str and type(a['ordered_bytes'])is int and 0<len(text.encode())==a['ordered_bytes']<=2<<20 and hashlib.sha256(text.encode()).hexdigest()==a['ordered_sha256'],'complete ordered annotations')
 ordered=json.loads(text);need(type(ordered)is list and len(ordered)==a['count']-1 and all(type(r)is dict for r in ordered),'ordered annotations list')
 l=o['low_ports'];need(type(l)is dict and set(l)=={'schema','scope','port_observation_stage','ports','low','abi_accepted_for_execution'},'LOW exact fields')
 need(l['schema']=='MODEL_CANDIDATE_LOW_PORTS_OBSERVATION_V1'and l['scope']=='CANDIDATE_GENERATION_PRECONDITIONS_ONLY_UNREVIEWED'and l['port_observation_stage']=='OFFICIAL_LOW_AND_TERMINAL_AST_EXACT_ORDERED_TYPES'and l['abi_accepted_for_execution']is False,'LOW nonauthorizing identity')
 need(l['ports']==pre['typed_ports']and len(l['ports'])==122,'exact original typed122 ABI');sizehash(l['low'])
 s=o['sv'];sk={'schema','status','phase','scope','raw_sha256','actual_normalized_sha256','bytes','counts','modules','scanner_sha256','inventory_sha256','numerical_pass','sv_accepted'}
 need(type(s)is dict and set(s)==sk and s['schema']=='MODEL_CANDIDATE_SV_OBSERVATION_V1'and s['status']=='OBSERVED_UNREVIEWED'and s['phase']=='complete'and s['scope']=='ACTUAL_BYTES_ONLY_NOT_STRUCTURE_OR_NUMERICAL_ACCEPTANCE','SV exact schema')
 need(s['scanner_sha256']==SCANNER_SHA and s['inventory_sha256']==INVENTORY_SHA and s['numerical_pass']is False and s['sv_accepted']is False and hex64(s['actual_normalized_sha256']),'SV observer identity');sizehash({'bytes':s['bytes'],'sha256':s['raw_sha256']})
 need(type(s['counts'])is dict and all(type(k)is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}',k)and type(v)is int and 0<=v<=4<<30 for k,v in s['counts'].items()),'bounded scanner counters')
 need(type(s['modules'])is list and 0<len(s['modules'])<=2048,'bounded SV modules');names=[]
 for r in s['modules']:
  need(type(r)is dict and set(r)=={'module','bytes','raw_sha256','normalized_sha256','sourceinfo_count'}and type(r['module'])is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_$]{0,127}',r['module']),'SV module fields')
  need(type(r['bytes'])is int and 0<r['bytes']<=4<<30 and type(r['sourceinfo_count'])is int and 0<=r['sourceinfo_count']<=4<<30 and hex64(r['raw_sha256'])and hex64(r['normalized_sha256']),'SV module scalars');names.append(r['module'])
 need(len(set(names))==len(names)and sum(r['bytes']for r in s['modules'])==s['bytes'],'complete SV module byte partition')
 st=o['structure'];need(type(st)is dict and set(st)=={'schema','scope','sv','preconditions_sha256','fixed_module_checks','structure','numerical_pass','post_build_structure_accepted'},'structure exact fields')
 need(st['schema']=='MODEL_CANDIDATE_STRUCTURE_OBSERVATION_V1'and st['scope']=='CANDIDATE_GENERATION_PRECONDITIONS_ONLY_UNREVIEWED'and st['preconditions_sha256']==PRECONDITIONS_SHA and st['numerical_pass']is False and st['post_build_structure_accepted']is False,'structure not approval')
 need(st['sv']=={'bytes':s['bytes'],'sha256':s['raw_sha256']}and st['fixed_module_checks']==pre['unchanged_modules'],'fixed original module structural evidence')
 q=st['structure'];need(type(q)is dict and set(q)=={'reachable_instance_count','providers','shared_vector_bank_path','shared_vector_bank_instances','bank_alu_instances','all_reachable_alu_instances','bank_subtree_modules','instances'},'complete reachable hierarchy fields')
 for k in ('reachable_instance_count','shared_vector_bank_instances','bank_alu_instances','all_reachable_alu_instances'):need(type(q[k])is int and 0<q[k]<=100000,'bounded actual hierarchy counts')
 need(q['shared_vector_bank_instances']==1 and q['bank_alu_instances']==32 and q['all_reachable_alu_instances']>=32,'actual one32 bank not totalALU claim')
 need(type(q['shared_vector_bank_path'])is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_.$]{0,511}',q['shared_vector_bank_path']),'bank hierarchy path');named_hashes(q['bank_subtree_modules'])
 for role,rows in (('providers',q['providers']),('instances',q['instances'])):
  need(type(rows)is list and 0<len(rows)<=100000,'bounded hierarchy rows')
  for index,r in enumerate(rows):
   need(type(r)is dict and set(r)=={'path','module','defname'}and all(type(r[k])is str and re.fullmatch('[A-Za-z0-9_.$]{0,512}',r[k])for k in r)and bool(r['module']),'instance identities')
   need(bool(r['path']) or (role=='instances' and index==0 and r=={'path':'','module':'HostBlockTopV4','defname':''}),'only first exact root has empty path')
 need(q['instances'][0]=={'path':'','module':'HostBlockTopV4','defname':''},'actual helper root is first')
 need(len(q['providers'])==17 and len(q['instances'])==q['reachable_instance_count']and len({r['path']for r in q['instances']})==len(q['instances'])and all(r in q['instances']for r in q['providers']),'actual provider/instance partition')
 actual_modules={r['name']:r['sha256']for r in h['modules']}
 need(all(actual_modules.get(r['name'])==r['sha256']for r in st['fixed_module_checks']+q['bank_subtree_modules']),'HIGH actual module hashes match structural rows')
 original_bank={r['name']:r['sha256']for r in pre['bank_subtree_reference_modules']}
 need(all(original_bank.get(r['name'])==r['sha256']for r in q['bank_subtree_modules']),'original bank subtree definition bytes through canonical hashes')
 need(all(r['module']in actual_modules for r in q['instances']),'reachable instance module definitions exist')
 need(q['providers']==[r for r in q['instances']if r['defname']],'exhaustive actual external providers')
 need({k:sum(r['defname']==k for r in q['providers'])for k in ('qwen2_matrix_command_endpoint','tc_clk_gating','idma_backend_rw_axi_flat_wrap')}=={'qwen2_matrix_command_endpoint':8,'tc_clk_gating':8,'idma_backend_rw_axi_flat_wrap':1},'original8 physical512 providers/8gates/1DMA')
 banks=[r for r in q['instances']if r['module'].startswith('UnifiedVectorElement32BankV4')]
 need(len(banks)==1 and banks[0]['path']==q['shared_vector_bank_path'],'actual unique shared bank path')
 bank_rows=[r for r in q['instances']if r['path']==banks[0]['path']or r['path'].startswith(banks[0]['path']+'.')]
 need({r['module']for r in bank_rows}=={r['name']for r in q['bank_subtree_modules']},'complete observed bank subtree modules')
 need(sum(r['module'].startswith('HeteroFP32Alu')for r in bank_rows)==q['bank_alu_instances']and sum(r['module'].startswith('HeteroFP32Alu')for r in q['instances'])==q['all_reachable_alu_instances'],'actual ALU counts recomputed from hierarchy')
 stages=o['stage_receipts'];need(type(stages)is list and len(stages)==20,'20 observed stages')
 for row,name in zip(stages,STAGES):
  need(type(row)is dict and set(row)=={'name','bytes','sha256'}and row['name']==name,'stage exact order');sizehash({k:row[k]for k in ('bytes','sha256')})
 need(len(canonical(o))<=8<<20,'bounded complete observation');return o

def observation(row,original,host,overlay):
 need(type(row)is dict and set(row)=={'path','bytes','sha256'},'independently pinned observation input')
 p=regular(row['path'],8<<20);need(type(row['bytes'])is int and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'observation file drift');o=validate_observation(json_file(p,8<<20))
 need(o['source_closure']['source_commit']==original['repo_sha']and o['source_closure']['source_overlay']=={'bytes':overlay.stat().st_size,'sha256':sha(overlay)},'observed actual source and overlay')
 need(o['sv']['raw_sha256']==sha(host)and o['sv']['bytes']==host.stat().st_size,'observed actual emitted SV');return o

def _pack_impl(original,b,built,host,overlay,out,budget_check,observation_pin,_mark):
 """Inputs are checked candidate collector output; out is same-job stage root.
 New model_source_evidence.record supplies source-role evidence, not old P0 enrich.
 Export remains unreviewed even if all integrity checks succeed.
 """
 identity(original['artifact_identity']);need(original['repo_sha']==original['artifact_identity']['source_commit'],'source identity')
 need(built.get('status')=='BUILT_UNQUALIFIED' and built.get('scope')=='ARCHIVE_LINK_ONLY_NOT_DUT_PASS','actual build only')
 for v in (b,b.get('admission',{}),built,built.get('plan',{})):need(v.get('cpp_build_policy')==CPP_POLICY and v.get('cpp_build_overrides')==CPP_OVERRIDES,'strict exact O1 policy')
 _mark('SOURCE_PINS')
 check_pins(b['pins']);check_pins(b['admission']['make_closure_pins'])
 _mark('OBSERVATION')
 out=P(out).resolve(strict=True);host=regular(host);overlay=regular(overlay);obs=observation(observation_pin,original,host,overlay)
 if address_generation_observation(obs['source_closure']) or original.get('hardware_source')in SOURCE_GENERATIONS or original.get('generation_contract_sha256')in (ADDRESS_GENERATION_SHA,SUPPLY_GENERATION_SHA):
  from candidate_generation_gate import require_generation_binding
  selected=source_generation(obs['source_closure']);need(selected is not None and original.get('hardware_source')==b.get('hardware_source')==selected[0],'new hardware explicit same original/admitted source selection')
  require_generation_binding(original);require_generation_binding(b)
  catalog=P(original['repo'])/'candidates/same_job_execution_20261030/SOURCE_PINS.json'
  need(obs['source_closure']['source_pins_sha256']==sha(catalog),'pack exact selected source catalog identity')
  need(obs['source_closure']['generation_contract_sha256']==original['generation_contract_sha256']==b['generation_contract_sha256'] and str(overlay)==original['fixed_source_overlay']==b['fixed_source_overlay'],'pack exact new generation/overlay join')
 obs_hash=hashlib.sha256(canonical(obs)).hexdigest()
 _mark('STAGE_RECEIPTS')
 actual_stages={};stage_texts={};stage_summary=[]
 for name in STAGES:
  p=regular(out/name/'RESULT.json',2<<20);r=json_file(p,2<<20);strict(r);actual_stages[name]=r;stage_texts[name]=dict(pin(p),text=p.read_text())
  stage_summary.append(dict(name=name,receipt_sha256=sha(p),native_exit=0,errors=[],cleanup_complete=True,pipe_eof_observed=True,gzip_finalized=True))
 need(obs['stage_receipts']==[dict(name=n,bytes=stage_texts[n]['bytes'],sha256=stage_texts[n]['sha256'])for n in STAGES],'observed complete20 receipt pins')
 _mark('COMPILE_OUTPUTS')
 phases=built['phases'];plan=built['plan']['phases'];need(len(phases)==len(plan)==5,'five actual build phases');summaries=[]
 for actual,planned,name in zip(phases,plan,STAGES[-5:]):
  need(actual['phase']==planned['name']==name and actual['argv']==planned['argv'],'exact phase/argv')
  need(type(actual['argv'])is list and all(type(a)is str for a in actual['argv']),'argv strings')
  need(actual['supervisor']==actual_stages[name] and actual_stages[name].get('argv')==actual['argv'],'same actual phase receipt and executed argv')
  q=actual['output'];need(pin(q['path'])==q,'actual output immutable')
  summaries.append(dict(phase=name,argv=actual['argv'],output_sha256=q['sha256'],native_exit=0,supervisor_receipt_sha256=hashlib.sha256(canonical(actual['supervisor'])).hexdigest()))
 need(built['binary']==phases[-1]['output'],'final linked binary');binary=regular(built['binary']['path'])
 with binary.open('rb')as f:need(f.read(6)==b'\x7fELF\x02\x01','actual ELF64LE')
 _mark('ENRICH')
 from first_fault_policy import binding_policy,FIRST_FAULT_MANIFEST_SCHEMA,FIRST_FAULT_SCOPE
 from finite_watchdog_policy import binding_policy as finite_binding
 from host_profile_policy import expected_driver_sha,binding_policy as profile_binding,retained_relation
 readonly=binding_policy(original);need(binding_policy(b)==readonly,'same original/admitted readonly policy')
 finite=finite_binding(original);need(finite_binding(b)==finite,'same original/admitted finite watchdog policy')
 profile=profile_binding(original);need(profile_binding(b)==profile,'same original/admitted profiled mapper source policy')
 driver=regular(original['driver']);need(sha(driver)==expected_driver_sha(original),'frozen policy driver')
 source_path=regular(b['source_manifest'],16<<20);source=json_file(source_path,16<<20)
 need(source.get('source_commit')==original['repo_sha'],'source ledger commit')
 need(source.get('sv_sha256')==sha(host)and source.get('driver_sha256')==sha(driver),'source ledger actual SV/driver')
 need('model_source_evidence'not in source,'no prefilled source evidence override')
 from model_source_evidence import record
 source['model_source_evidence']=record(original,b,built)
 need(type(source['model_source_evidence'])is dict and bool(source['model_source_evidence']),'new complete source evidence required')
 need('model_candidate_observation'not in source,'no prefilled observation override')
 need('model_candidate_build_evidence'not in source,'no prefilled actual build evidence')
 need('readonly_probe'not in source,'no prefilled readonly evidence override')
 if readonly is not None:
  cp=regular(original['first_fault_driver_contract']['path'],256<<10)
  ep=b['readonly_probe_evidence'];need(type(ep)is dict and set(ep)=={'path','bytes','sha256'},'readonly actual evidence pin')
  actual=regular(ep['path'],128<<10);need(pin(actual)==ep and b['pins'].get(str(actual))==ep['sha256'],'readonly generated evidence prebuild pin/drift')
  source['readonly_probe']={'schema':'FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1','status':'OBSERVED_UNREVIEWED','contract':dict(pin(cp),text=cp.read_text()),'accessor_generation':json_file(actual,128<<10)}
  if readonly['schema']=='FIRST_FAULT_DRIVER_CONTRACT_V2':
   tp=b['terminal_probe_evidence'];need(type(tp)is dict and set(tp)=={'path','bytes','sha256'},'terminal actual evidence pin')
   terminal_actual=regular(tp['path'],4<<20);need(pin(terminal_actual)==tp and b['pins'].get(str(terminal_actual))==tp['sha256'],'terminal actual evidence prebuild pin/drift')
   source['readonly_probe'].update(schema='FIRST_FAULT_READONLY_BUILD_EVIDENCE_V2',terminal_accessor_generation=json_file(terminal_actual,4<<20))
  else:need('terminal_probe_evidence'not in b,'old readonly contract cannot carry terminal evidence')
 dep=built['phases'][-1].get('driver_dependency');need(type(dep)is dict,'actual GCC dependency evidence required')
 headers=[p for p in dep.get('dependencies',{})if P(p).name=='VHostBlockTopV4.h'];need(len(headers)==1,'one actual generated Host header')
 header_path=regular(headers[0],2<<20);need(pin(header_path)==dep['dependencies'][headers[0]],'captured actual Host header bytes')
 def retained_text(path,cap):
  path=regular(path,cap);raw=path.read_bytes();need(b'\0'not in raw,'retained metadata text only');return dict(pin(path),text=raw.decode('utf-8'))
 source['model_candidate_build_evidence']={'schema':'MODEL_CANDIDATE_ACTUAL_BUILD_EVIDENCE_V1','driver_dependency':dep,'actual_stage_receipts':stage_texts,'fixed_source_overlay':retained_text(overlay,2<<20),'actual_host_header':retained_text(header_path,2<<20)}
 need('finite_watchdog_driver'not in source,'no prefilled watchdog relation')
 if finite is not None:source['finite_watchdog_driver']=finite
 need('host_profile_driver'not in source,'no prefilled profiled driver source relation')
 if profile is not None:source['host_profile_driver']=retained_relation(original)
 source['model_candidate_observation']=obs;address_source_identity(source,obs,readonly is not None);enriched=(json.dumps(source,indent=2,allow_nan=False)+'\n').encode();need(len(enriched)<=16<<20,'source metadata16MiB')
 _mark('COPY')
 copies={'binary':binary,'sv':host,'driver':driver,'tool_manifest':regular(b['tool_manifest'],32<<20)}
 before={k:pin(p)for k,p in copies.items()};source_before=pin(source_path)
 root=out/'model_candidate_artifact';need(not root.exists(),'fresh export directory')
 budget_check(sum(p.stat().st_size for p in copies.values())+len(enriched)+131072);root.mkdir();files={}
 for k,p in copies.items():
  target=root/NAMES[k];shutil.copyfile(p,target);target.chmod(0o600);need(sha(target)==before[k]['sha256']and pin(p)==before[k],'copy drift');files[k]=target
 files['source_manifest']=root/NAMES['source_manifest'];files['source_manifest'].write_bytes(enriched)
 need(pin(source_path)==source_before,'collector source drift')
 receipt=dict(schema='MODEL_CANDIDATE_BUILD_RECEIPT_V1',status=STATUS,cpp_build_policy=CPP_POLICY,cpp_build_overrides=list(CPP_OVERRIDES),source_commit=original['repo_sha'],launch_commit=original['artifact_identity']['launch_commit'],**{k+'_sha256':sha(files[k])for k in files},model_candidate_observation_sha256=obs_hash,phases=summaries,stages=stage_summary,scope='CHISEL_TEST_BACKEND_NOT_FINAL_RTL_REPLAY',config_only=False,software_arithmetic_substitution=False,numerical_pass=False,final_rtl_executed=False)
 if readonly is not None:
  receipt['readonly_probe_contract_sha256']=source['readonly_probe']['contract']['sha256'];receipt['scope']=FIRST_FAULT_SCOPE
 raw=(json.dumps(receipt,indent=2,allow_nan=False)+'\n').encode();need(len(raw)<=65536,'receipt64KiB');files['build_receipt']=root/NAMES['build_receipt'];files['build_receipt'].write_bytes(raw)
 entries={k:dict(path=NAMES[k],bytes=p.stat().st_size,sha256=sha(p))for k,p in files.items()}
 manifest=dict(schema=MANIFEST_SCHEMA,status=STATUS,cpp_build_policy=CPP_POLICY,cpp_build_overrides=list(CPP_OVERRIDES),profiles=list(range(5)),layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',matrix_macs=4096,vector_lanes=32,moe_reference_contract=ROUTE,artifact_identity=original['artifact_identity'],common={k:entries[k]for k in ('binary','sv','source_manifest','driver','build_receipt')},tool_manifest=entries['tool_manifest'],model_candidate_observation_sha256=obs_hash,numerical_pass=False,final_rtl_executed=False,model_numerical_evaluation_authorized=False,external_review_required=True)
 if readonly is not None:
  manifest['schema']=FIRST_FAULT_MANIFEST_SCHEMA;manifest['scope']=FIRST_FAULT_SCOPE
  manifest['readonly_probe_contract']={k:source['readonly_probe']['contract'][k]for k in ('bytes','sha256')}
 mf=root/'frozen_artifact.json';mf.write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n');need(mf.stat().st_size<=65536,'manifest64KiB')
 _mark('FINAL')
 result=validate_export(root)
 check_pins(b['pins']);check_pins(b['admission']['make_closure_pins']);need(sha(regular(observation_pin['path']))==observation_pin['sha256'],'observation changed during pack');budget_check(0)
 return dict(manifest=pin(mf),files=7,expanded_bytes=result['expanded_bytes'],payload_identity=result['payload_identity'],scope='UNREVIEWED_MODEL_BUILD_BYTES_NOT_UPLOADED_NOT_EXECUTED')

def pack(original,b,built,host,overlay,out,budget_check,observation_pin):
 # Local, per-call diagnostics: no global mutable state or caller callback.
 # Every failure still propagates; no diagnostic grants packaging acceptance.
 phase=['IDENTITY']
 def mark(value):
  need(value in PACK_PHASES,'fixed internal pack phase');phase[0]=value
 try:return _pack_impl(original,b,built,host,overlay,out,budget_check,observation_pin,mark)
 except ModelPackFailure as e:
  e.model_pack_diagnostic['phase']=phase[0];raise
 except Exception as e:
  raise ModelPackFailure(phase[0],'STAGE_VALIDATION_FAILED',type(e).__name__)from e

def validate_export(root):
 root=P(root).resolve(strict=True);need(root.is_dir(),'artifact directory')
 need({p.name for p in root.iterdir()}==set(NAMES.values())|{'frozen_artifact.json'},'exact seven names')
 mf=regular(root/'frozen_artifact.json',65536);m=json_file(mf,65536)
 fields={'schema','status','cpp_build_policy','cpp_build_overrides','profiles','layer','matrix_macs','vector_lanes','moe_reference_contract','artifact_identity','common','tool_manifest','model_candidate_observation_sha256','numerical_pass','final_rtl_executed','model_numerical_evaluation_authorized','external_review_required'}
 FIRST_FAULT_MANIFEST_SCHEMA='MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1'
 readonly_schema=m.get('schema')==FIRST_FAULT_MANIFEST_SCHEMA
 if readonly_schema:
  from first_fault_policy import FIRST_FAULT_SCOPE,artifact_policy
 need(set(m)==(fields|{'scope','readonly_probe_contract'}if readonly_schema else fields)and m['schema'] in (MANIFEST_SCHEMA,FIRST_FAULT_MANIFEST_SCHEMA)and m['status']==STATUS,'unreviewed candidate schema')
 if readonly_schema:need(m['scope']==FIRST_FAULT_SCOPE,'readonly diagnostic artifact scope')
 need(all(m[k]is False for k in ('numerical_pass','final_rtl_executed','model_numerical_evaluation_authorized'))and m['external_review_required']is True,'never grants evaluation')
 need(m['profiles']==list(range(5))and all(type(v)is int for v in m['profiles'])and type(m['matrix_macs'])is int and m['matrix_macs']==4096 and type(m['vector_lanes'])is int and m['vector_lanes']==32,'one fixed fiveprofile hardware')
 need(m['cpp_build_policy']==CPP_POLICY and m['cpp_build_overrides']==CPP_OVERRIDES and m['moe_reference_contract']==ROUTE and m['layer']=='CHISEL_EMITTED_SV_NUMERICAL_BACKEND','fixed contracts');identity(m['artifact_identity'])
 need(set(m['common'])=={'binary','sv','driver','source_manifest','build_receipt'},'common five fields');rows=dict(m['common'],tool_manifest=m['tool_manifest']);actual={}
 for k,row in rows.items():
  need(type(row)is dict and set(row)=={'path','bytes','sha256'}and row['path']==NAMES[k],'flat canonical payload pin')
  cap=65536 if k=='build_receipt' else 16<<20 if k=='source_manifest' else 32<<20 if k=='tool_manifest' else 4<<30
  p=regular(root/NAMES[k],cap);need(type(row['bytes'])is int and row['bytes']==p.stat().st_size and row['sha256']==sha(p),'payload drift');actual[k]={'bytes':row['bytes'],'sha256':row['sha256']}
 source=json_file(root/NAMES['source_manifest'],16<<20)
 if readonly_schema:readonly=artifact_policy(m,source)
 else:
  need('readonly_probe'not in source and 'readonly_probe_contract'not in m,'original artifact cannot carry readonly evidence');readonly=None
 finite=None
 if 'finite_watchdog_driver'in source or actual['driver']['sha256']=='def22c17427b929a8e339224799845d729ad56d24b9646d99390b25a4ecd6f59':
  from finite_watchdog_policy import artifact_policy as finite_artifact
  finite=finite_artifact(source,actual['driver']['sha256'])
 from host_profile_policy import artifact_policy as profile_artifact
 profile=profile_artifact(source,actual['driver']['sha256'])
 need(sum(x is not None for x in (readonly,finite,profile))<=1,'exclusive driver policy')
 need(actual['driver']['sha256']==(profile['driver_sha256']if profile is not None else finite['finite_driver_sha256']if finite is not None else DRIVER_SHA if readonly is None else readonly['diagnostic_driver']['sha256']),'fixed policy driver');need(source.get('sv_sha256')==actual['sv']['sha256']and source.get('driver_sha256')==actual['driver']['sha256'],'source ledger exact actual SV/driver');obs=source.get('model_candidate_observation')
 validate_observation(obs);address_source_identity(source,obs,readonly is not None);need(hashlib.sha256(canonical(obs)).hexdigest()==m['model_candidate_observation_sha256'],'observation canonical integrity')
 r=json_file(root/NAMES['build_receipt'],65536);need(r.get('status')==STATUS and r.get('schema')=='MODEL_CANDIDATE_BUILD_RECEIPT_V1','candidate receipt')
 need(r.get('source_commit')==source.get('source_commit')==m['artifact_identity']['source_commit']and r.get('launch_commit')==m['artifact_identity']['launch_commit'],'receipt git chain')
 need(r.get('model_candidate_observation_sha256')==m['model_candidate_observation_sha256']and r.get('cpp_build_policy')==CPP_POLICY and r.get('cpp_build_overrides')==CPP_OVERRIDES,'receipt observation/policy')
 for k in ('binary','sv','driver','source_manifest','tool_manifest'):need(r.get(k+'_sha256')==actual[k]['sha256'],'receipt payload chain')
 if readonly is None:need('readonly_probe_contract_sha256'not in r and 'readonly_probe'not in source,'no readonly evidence in original branch')
 else:need(r.get('readonly_probe_contract_sha256')==m['readonly_probe_contract']['sha256']and r.get('scope')==FIRST_FAULT_SCOPE,'readonly receipt contract/scope')
 need(r.get('numerical_pass')is False and r.get('final_rtl_executed')is False and r.get('config_only')is False and r.get('software_arithmetic_substitution')is False,'receipt scope')
 need([s.get('name')for s in r.get('stages',[])]==list(STAGES),'all20 stages ordered')
 for s in r['stages']:need(type(s.get('native_exit'))is int and s.get('native_exit')==0 and s.get('errors')==[]and all(s.get(k)is True for k in ('cleanup_complete','pipe_eof_observed','gzip_finalized')),'strict stage projection')
 expanded=sum(p.stat().st_size for p in root.iterdir());need(expanded<=4<<30,'expanded4GiB')
 return dict(status=STATUS,files=7,expanded_bytes=expanded,payload_identity=actual,numerical_pass=False,final_rtl_executed=False)

def verify_candidate_seven(root,expected_identity,expected_manifest_sha):
 """Pure seven-file + complete compilation validation; no execution permission.
 expected_identity comes from verified GitHub API/launch/source, not this ZIP.
 """
 identity(expected_identity);need(hex64(expected_manifest_sha),'external manifest pin')
 root=P(root).resolve(strict=True);mf=regular(root/'frozen_artifact.json',65536)
 need(sha(mf)==expected_manifest_sha,'independently expected manifest bytes')
 result=validate_export(root);manifest=json_file(mf,65536)
 need(manifest['artifact_identity']==expected_identity,'external builder identity exact')
 source=json_file(root/'source_manifest.json',16<<20);receipt=json_file(root/'build_receipt.json',65536)
 # Builder/export/receive use precisely the original reviewed builder source.
 # Cross-source executors must use their independently pinned proof API instead.
 here=P(__file__).resolve();repo=here.parents[2]
 catalog_path=regular(repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json',4<<20)
 need(sha(catalog_path)==source['model_candidate_observation']['source_closure']['source_pins_sha256'],'same builder source catalog required')
 catalog=json_file(catalog_path,4<<20);need(catalog.get('schema')=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1'and type(catalog.get('files'))is list,'source catalog schema')
 proof_path=regular(here.with_name('candidate_dependency_proof.py'),2<<20)
 for target in (here,proof_path):
  rel=str(target.relative_to(repo));rows=[r for r in catalog['files']if type(r)is dict and r.get('path')==rel]
  need(len(rows)==1 and rows[0].get('bytes')==target.stat().st_size and rows[0].get('sha256')==sha(target),'actual candidate pack/proof source closure')
 spec=importlib.util.spec_from_file_location('_same_builder_candidate_compilation_proof',proof_path)
 proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)
 need(P(proof.__file__).resolve()==proof_path,'exact explicit proof import')
 proof.verify_candidate_compilation(manifest,source,receipt,root)
 return dict(manifest_sha256=expected_manifest_sha,expanded_bytes=result['expanded_bytes'],files=7,numerical_pass=False,final_rtl_replay=False)

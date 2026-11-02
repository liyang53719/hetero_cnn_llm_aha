"""Pinned read-only diagnostic driver relation. No compiler, model or subprocess API."""
import hashlib,json,pathlib,re,types
P=pathlib.Path
SCOPE='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'
ARTIFACT_SCHEMA='MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1'
REVIEW_SCHEMA='MODEL_CANDIDATE_FIRST_FAULT_REVIEW_V1'
LEGACY_SHA='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61'
GENERATION_SHA='3354827c1c9d2ac167b3b325dc07acbd50ea663ddd384dddfea1b1d037ae3851'
ORIGINAL_SV_SHA='3d148277114ff5d968d0e200f4ab117839a3b6c0c0d33e5388e6e5268d42d029'
CONTRACT_SHA='79cd00d5f9d0dd95c160b6de35c1d1c2e174171933b98721168d818eb6fcbff2'
PORTS_SHA='289f230ec8fc85e7aee0396ab34424f505855074a762707e874fbf8a2f45ca08'
D='candidates/moe_router_score_observation_20261030/driver/'
C='candidates/model_candidate_build_20261101/'
ROLES={'legacy_driver':D+'host_axi_driver_non_dpi.cpp','diagnostic_driver':D+'host_axi_driver_first_fault.cpp','host_observer':D+'readonly_first_fault.hpp','probe_schema':C+'FIXED_NONHIER_SCHEMA.json','probe_config':C+'FIRST_FAULT_READONLY.vlt','probe_generator':C+'first_fault_probe.py','inverse_verifier':D+'verify_first_fault_driver.py','hardware_generation_contract':C+'GENERATION_CONTRACT.json'}
def need(v,s):
 if not v:raise ValueError(s)
def digest(b):return hashlib.sha256(b).hexdigest()
def canonical_sha(v):return digest(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode())
def regular(p,cap):
 p=P(p);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=cap,'bounded canonical first fault evidence');return p

def pin(r,cap=2<<20):
 need(type(r)is dict and set(r)=={'path','bytes','sha256'}and type(r['bytes'])is int,'exact first fault evidence pin')
 p=regular(r['path'],cap);need(p.stat().st_size==r['bytes']and digest(p.read_bytes())==r['sha256'],'first fault evidence bytes');return p

def embedded(r,cap):
 need(type(r)is dict and set(r)=={'path','bytes','sha256','text'}and type(r['bytes'])is int and type(r['text'])is str,'exact embedded text')
 raw=r['text'].encode();need(0<len(raw)<=cap and len(raw)==r['bytes']and digest(raw)==r['sha256'],'embedded exact bytes');return raw

def source_module(path,raw):
 m=types.ModuleType('first_fault_'+path.stem);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m

def verify_source_contract(contract_pin,repo,catalog_pin):
 cp=pin(contract_pin,65536);need(contract_pin['sha256']==CONTRACT_SHA,'independently fixed readonly driver contract');doc=json.loads(cp.read_text())
 fields={'schema','scope',*ROLES,'host_ports_sha256','control_semantics_changed','extra_eval_or_clock','payload_data_or_addresses'}
 need(set(doc)==fields and doc['schema']=='FIRST_FAULT_DRIVER_CONTRACT_V1'and doc['scope']==SCOPE,'exact read-only driver contract')
 need(all(doc[k]is False for k in('control_semantics_changed','extra_eval_or_clock','payload_data_or_addresses'))and doc['host_ports_sha256']==PORTS_SHA,'fixed unchanged-control scope')
 root=P(repo);need(root.is_absolute()and root==root.resolve()and root.is_dir()and all(not p.is_symlink()for p in(root,*root.parents)),'actual source root')
 cat=json.loads(pin(catalog_pin).read_text());need(cat['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','actual source catalog')
 rows={r['path']:r for r in cat['files']};need(len(rows)==len(cat['files']),'unique source roles')
 sources={};paths={}
 for role,rel in ROLES.items():
  r=doc[role];need(type(r)is dict and set(r)=={'repo_path','bytes','sha256'}and r['repo_path']==rel and type(r['bytes'])is int,'fixed exact source role')
  p=pin(dict(path=str(root/rel),bytes=r['bytes'],sha256=r['sha256']),16<<20);need(rows.get(rel)==dict(path=rel,bytes=r['bytes'],sha256=r['sha256']),'actual unique catalog source role');sources[role]=p.read_bytes();paths[role]=p
 need(doc['legacy_driver']['sha256']==LEGACY_SHA and doc['legacy_driver']['bytes']==27317 and doc['hardware_generation_contract']['sha256']==GENERATION_SHA,'fixed baseline driver/generation')
 inverse=source_module(paths['inverse_verifier'],sources['inverse_verifier']);result=inverse.verify_driver(sources['legacy_driver'],sources['diagnostic_driver'])
 need(result==dict(legacy_driver_sha256=LEGACY_SHA,diagnostic_driver_sha256=doc['diagnostic_driver']['sha256'],exact_inverse=True),'actual exact inverse driver proof')
 generator=source_module(paths['probe_generator'],sources['probe_generator']);schema,schema_raw=generator.load_schema(paths['probe_schema']);need(sources['probe_config']==generator.config_bytes(schema),'exact regenerated read-only config')
 return dict(contract=doc,sources=sources,paths=paths,generator=generator,schema=schema,roots=sorted({str(cp.parent),str(pin(catalog_pin).parent),str(root)}))

def verify_probe(review,artifact_pin,repo,catalog_pin):
 """Review provenance must be checked by candidate_admission before this call."""
 artifact=json.loads(pin(artifact_pin,65536).read_text());need(artifact['schema']==ARTIFACT_SCHEMA and review['schema']==REVIEW_SCHEMA and review['scope']==SCOPE,'explicit new review/artifact domains')
 dp=pin(review['first_fault_diagnostic']);doc=json.loads(dp.read_text())
 need(doc.get('schema')=='P0_FIRST_FAULT_DIAGNOSTIC_V1'and doc.get('scope')==SCOPE and type(doc.get('profile'))is int and doc['profile']==0 and doc.get('artifact_manifest_sha256')==artifact_pin['sha256']and doc.get('numerical_pass')is False and doc.get('final_rtl_executed')is False,'exact diagnostic artifact scope')
 checked=verify_source_contract(doc['readonly_driver_contract'],repo,catalog_pin);contract=checked['contract']
 need(artifact['readonly_probe_contract']=={k:doc['readonly_driver_contract'][k]for k in('bytes','sha256')},'artifact read-only contract pin')
 root=P(artifact_pin['path']).parent;source_row=artifact['common']['source_manifest'];source=json.loads(pin(dict(source_row,path=str(root/source_row['path'])),16<<20).read_text())
 need(artifact['common']['sv']['sha256']==source['sv_sha256']==ORIGINAL_SV_SHA,'exact original raw SV identity')
 obs=source['readonly_probe'];need(set(obs)=={'schema','status','contract','accessor_generation'}and obs['schema']=='FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1'and obs['status']=='OBSERVED_UNREVIEWED','observation not authority')
 raw=embedded(obs['contract'],65536);need(raw==pin(doc['readonly_driver_contract'],65536).read_bytes()and source['generation_input_pins'].get(obs['contract']['path'])==digest(raw),'actual embedded source contract')
 need(doc['readonly_probe_evidence_sha256']==canonical_sha(obs),'independent review binds actual generated evidence')
 e=obs['accessor_generation'];keys={'schema','scope','schema_input','config','root_header','accessor','mappings','field_count','reads_hier_child_internals','extra_eval_or_clock'}
 need(set(e)==keys and e['schema']=='ACTUAL_NONHIER_READONLY_ACCESSOR_EVIDENCE_V1'and e['scope']=='READ_ONLY_GENERATED_HEADER_DECLARATIONS_NOT_NUMERICAL_ACCEPTANCE'and e['reads_hier_child_internals']is False and e['extra_eval_or_clock']is False and type(e['field_count'])is int and e['field_count']==114,'exact generated evidence')
 need({k:e['schema_input'][k]for k in('bytes','sha256')}=={k:contract['probe_schema'][k]for k in('bytes','sha256')}and embedded(e['config'],65536)==checked['sources']['probe_config'],'actual schema/config source bytes')
 mappings=e['mappings'];need(type(mappings)is list and len(mappings)==114,'complete fixed mapping')
 for m,r in zip(mappings,checked['schema']['signals']):
  expected={k:r[k]for k in('symbol_key','module','instance_path','sv_var','width_bits')};expected['member']=checked['generator'].expected_member(r)[0]
  need(set(m)==set(expected)|{'declaration'}and all(m[k]==v for k,v in expected.items())and type(m['declaration'])is str,'exact mapped nonhier identity')
 need(embedded(e['accessor'],128<<10)==checked['generator'].accessor_bytes(mappings),'actual accessor exact generated bytes')
 for row in(e['root_header'],e['schema_input']):
  need(type(row)is dict and set(row)=={'path','bytes','sha256'}and type(row['bytes'])is int and row['bytes']>0 and re.fullmatch('[0-9a-f]{64}',row['sha256']),'observed exact generated pin')
 driver=artifact['common']['driver'];actual=pin(dict(driver,path=str(root/driver['path'])),1<<20).read_bytes()
 need(driver['path']=='driver.cpp'and actual==checked['sources']['diagnostic_driver'],'actual new driver source bytes')
 return dict(driver_sha256=driver['sha256'],readonly_driver_contract_sha256=doc['readonly_driver_contract']['sha256'],readonly_probe_evidence_sha256=doc['readonly_probe_evidence_sha256'],roots=sorted({*checked['roots'],str(dp.parent),str(root)}))

def require_driver(frozen,context,driver_row):
 """No bundle or command line may construct diagnostic authority."""
 need(frozen.get('schema')==ARTIFACT_SCHEMA and type(context)is dict and context.get('candidate_scope')==SCOPE,'explicit admitted diagnostic context')
 rp=pin(context['model_candidate_review']);review=json.loads(rp.read_text());need(review['artifact_manifest']==context['artifact_manifest']and review['builder_identity']==frozen['artifact_identity'],'same actual reviewed artifact')
 checked=verify_probe(review,context['artifact_manifest'],context['repo'],context['current_source_pins_pin']);need(driver_row['sha256']==checked['driver_sha256'],'actual approved diagnostic driver');return checked

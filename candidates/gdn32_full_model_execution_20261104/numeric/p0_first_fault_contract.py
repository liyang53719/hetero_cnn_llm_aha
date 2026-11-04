"""P0-only diagnostic watchdog document and authority join. No live/model APIs."""
import hashlib,json,pathlib,types
P=pathlib.Path;D=P(__file__).resolve().parent
SCOPE='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'
MODE='P0_FIRST_FAULT_DIAGNOSTIC'
RUNTIME='184bd5c1785b8ef756838a60c90aa38906372041c018f0acce5e469b48e494f6'
VIEWS='06ce2ef0332a5dc14385b353c15ad57a5d26c305a57cd38dc848e9d2c4c9bb0d'
STIMULUS={'program_manifest':(15000,'4f201e1744b8aa2c604a478ca837076abaf41a7235b62d8aa7ef14fcdc830163'),'commands':(384,'618cd4db94fbc5f0e3829182a72d5e298b5a42d2a3840ec2b9f9be639cd884c4'),'descriptors':(3456,'1e4d35da18b21a4d9de05d2f3129e5bd9717cd923837c83c8d5eb320bfcddb02')}
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def pin(r,cap=2<<20):
 need(type(r)is dict and set(r)=={'path','bytes','sha256'}and type(r['bytes'])is int,'exact P0 diagnostic pin')
 p=P(r['path']);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file()and 0<r['bytes']<=cap and p.stat().st_size==r['bytes']and sha(p)==r['sha256'],'canonical actual P0 diagnostic evidence');return p

def module(binding,name):
 p=D/(name+'.py');need(binding['pins'].get(str(p))==sha(p),'source-pinned P0 diagnostic helper')
 m=types.ModuleType('p0_diagnostic_'+name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m

def verify_document(binding,reviewed):
 need(binding.get('execution_context')=='CLOUD_EXECUTOR_V1'and binding.get('execution_mode')==MODE,'explicit cloud P0 diagnostic')
 need(binding.get('full_block_budget')is None and 'stage_coverage_budget'not in binding,'not CAL/STAGE/FULL admission')
 need(reviewed['schema']=='MODEL_CANDIDATE_FIRST_FAULT_REVIEW_V1'and reviewed['scope']==SCOPE and reviewed['artifact_manifest_sha256']==binding['artifact_manifest']['sha256']and reviewed['model_candidate_review_sha256']==binding['model_candidate_review']['sha256'],'actual independently reviewed diagnostic domain')
 # The caller must supply verify_review's result; production admit obtains it itself.
 raw_review=json.loads(pin(binding['model_candidate_review']).read_text());need(all(raw_review[k]==reviewed[k]for k in raw_review),'reviewed document exact bytes')
 row=reviewed['first_fault_diagnostic'];doc=json.loads(pin(row).read_text())
 fields={'schema','scope','profile','tokens','matrix_macs','vector_lanes','artifact_manifest_sha256','readonly_driver_contract','readonly_probe_evidence_sha256','stimulus','watchdog','basis','numerical_pass','final_rtl_executed'}
 need(set(doc)==fields and doc['schema']=='P0_FIRST_FAULT_DIAGNOSTIC_V1'and doc['scope']==SCOPE,'exact P0 document')
 for k,v in(('profile',0),('tokens',128),('matrix_macs',4096),('vector_lanes',32)):need(type(doc[k])is int and doc[k]==v,'fixed unchanged P0 full stimulus')
 need(doc['artifact_manifest_sha256']==binding['artifact_manifest']['sha256']and doc['numerical_pass']is False and doc['final_rtl_executed']is False,'diagnostic not acceptance')
 pin(doc['readonly_driver_contract'],65536)
 s=doc['stimulus'];need(set(s)==set(STIMULUS)|{'runtime_semantic_sha256','views_semantic_sha256','retained_materials_sha256'},'complete original stimulus contract')
 for k,(size,h)in STIMULUS.items():
  pin(s[k],65536);need(s[k]['bytes']==size and s[k]['sha256']==h,'original complete P0 program bytes')
 need(s['runtime_semantic_sha256']==RUNTIME and s['views_semantic_sha256']==VIEWS,'original runtime/view semantics')
 pin(binding['retained_materials']);need(s['retained_materials_sha256']==binding['retained_materials']['sha256'],'actual approved retained data')
 w=doc['watchdog'];need(type(w)is dict and set(w)=={'wall_seconds','max_active_cycles'}and all(type(x)is int and x>0 for x in w.values())and w['wall_seconds']<=18000 and w['max_active_cycles']<=1000000000,'reviewed bounded watchdog, not completion estimate')
 basis=doc['basis'];need(set(basis)=={'historical_stage_binding','historical_stage_summary','independent_watchdog_review'},'historical stage evidence not calibration')
 old=json.loads(pin(basis['historical_stage_binding']).read_text());summary=json.loads(pin(basis['historical_stage_summary']).read_text());review=json.loads(pin(basis['independent_watchdog_review']).read_text())
 need(old.get('execution_mode')=='STAGE_COVERAGE_DIAGNOSTIC'and summary.get('execution_mode')=='STAGE_COVERAGE_DIAGNOSTIC'and summary.get('schema')=='CLOUD_EXECUTION_SAFE_SUMMARY_V1'and summary.get('status')=='VERIFIED_REAGGREGATED','actual closed historical STAGE only')
 need(type(summary.get('transport_exit_code'))is int and summary['transport_exit_code']==2 and summary.get('numerical_pass')is False and summary.get('final_rtl_executed')is False,'historical diagnostic not numerical qualification')
 need(summary.get('binding_sha256')==basis['historical_stage_binding']['sha256']and summary.get('artifact_manifest_sha256')==old['artifact_manifest']['sha256']and summary.get('model_candidate_review_sha256')==old['model_candidate_review']['sha256'],'historical identity joins')
 need(old['artifact_manifest']['sha256']!=doc['artifact_manifest_sha256'],'new diagnostic artifact not historical identity')
 rows=summary['profiles'];closed={'STARTED_TIMEOUT_INCOMPLETE','STARTED_NATIVE_FAILED','COMPLETE_TERMINAL_DIAGNOSTIC_NOT_PASS','COMPLETE_FULL128_EXACT_REFERENCE_NOT_FINAL_RTL','COMPLETE_EXACT_REFERENCE_FAILED'}
 need(type(rows)is list and len(rows)==5 and all(type(r)is dict and type(r.get('profile'))is int and r.get('state')in closed for r in rows)and {r['profile']for r in rows}==set(range(5)),'five actually closed historical profiles')
 want={'schema':'P0_FIRST_FAULT_WATCHDOG_REVIEW_V1','status':'REVIEWED_WATCHDOG_NOT_FULL_ESTIMATE','artifact_manifest_sha256':doc['artifact_manifest_sha256'],'readonly_driver_contract_sha256':doc['readonly_driver_contract']['sha256'],'historical_stage_binding_sha256':basis['historical_stage_binding']['sha256'],'historical_stage_summary_sha256':basis['historical_stage_summary']['sha256'],'watchdog':w}
 need(review==want,'exact independent diagnostic watchdog review')
 return dict(doc_sha=row['sha256'],watchdog=dict(w),diagnostic_profiles=[0],scope=SCOPE)

def admit(binding):
 reviewed=module(binding,'candidate_admission').verify(binding.get('model_candidate_review'),binding)
 return verify_document(binding,reviewed)

def document_roots(binding,reviewed):
 """Exact directories of files actually read by the pure document check."""
 verify_document(binding,reviewed)
 row=reviewed['first_fault_diagnostic'];doc=json.loads(pin(row).read_text())
 rows=[row,doc['readonly_driver_contract'],binding['model_candidate_review'],binding['retained_materials'],*doc['basis'].values(),*(doc['stimulus'][key]for key in STIMULUS)]
 return sorted({str(pin(v).parent)for v in rows})

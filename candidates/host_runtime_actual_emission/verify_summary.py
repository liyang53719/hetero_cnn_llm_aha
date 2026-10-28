"""Validate identity/scope metadata only. No compiler, DUT or numerical execution."""
from pathlib import Path
import hashlib,json

def need(x,m):
 if not x:raise ValueError(m)
def verify(root):
 def read(n):return json.loads((root/n).read_text())
 a=read('ACTUAL_FACTS.json');s=read('SOURCE_PINS.json');p=read('EVIDENCE_PINS.json');c=read('PHYSICAL_CLOSURE.json');e=read('EMITTED_ARTIFACT_PINS.json')
 need(a['scope']=='CHISEL_SIMULATION_BACKEND_EMISSION_ONLY_NOT_FINAL_RTL','scope')
 for k in ['physical_frontend_run','physical_link_run','dut_run','utilization_measured','moe_tie_contract_approved']:need(a[k] is False,k)
 need(a['full_m128_numeric_pass']==a['full_m128_rtl_pass']==0 and a['profiles']==['Qwen2-1.5B','Qwen3.5-0.8B L0','Qwen3.5-0.8B L3','Qwen3.5-35B-A3B L0','Qwen3.5-35B-A3B L3'],'0/5')
 need(set(a['stages'])=={'fma','capture','tool_compile','lower'},'four stages')
 for k,v in a['stages'].items():need(v['exit_code']==0 and v['baseline_unchanged'] is True and v['preflight_checks']==v['postflight_checks'],k)
 need(len(p['members'])==79 and len({r['path'] for r in p['members']})==79,'raw inventory')
 need(p['freeze']['sha256']=='801924629a6db25424054017e2139b2a387f5ff4bade10badbb40055cd0ff546','freeze')
 need(c['provider_count']==13 and c['idma_source_entries']==294 and c['include_tree_files']==52 and c['pins_count']==367,'closure')
 need(c['actual_frontend_run'] is False and c['actual_link_run'] is False,'not link')
 need(len(c['review_summary']['unreferenced_include_tree_DPI_testbench_files'])==4,'DPI caveat')
 need(len(e['host']['artifacts'])==12 and e['host']['fullblock_pass']==e['host']['rtl_pass']==0,'host')
 h=next(x for x in e['host']['artifacts'] if x['path'].endswith('HostBlockTopV4.sv'))
 need(h['bytes']==194990051 and h['sha256']=='d88192158fce78c4adb0a732e84757d471009396a8a4f0c0b0c5411a6e03802b','host hash')
 need(s['requires_parent'] is True and s['public_template_compiled'] is False,'requires parent')
 need(s['compiled_source_count']==2 and s['new_class_count']==24 and s['baseline_class_count']==1033,'lineage')
 need(len(s['files'])==2,'two sources')
 for r in s['files']:
  b=(root/r['path']).read_bytes();q=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest());need(q==r['public'],'source pin')
  if r['projection']=='exact':need(q==r['original'] and r['redactions']==0,'exact')
  else:need(r['projection']=='two_literal_redacted_uncompiled_template' and q!=r['original'] and r['redactions']==2 and b.count(b'REQUIRES_PARENT_LITERAL_')==2,'template')
 return {'status':'PASS_METADATA_IDENTITY_ONLY_NOT_NUMERICAL','sources':2,'raw_members':79,'full_m128_numeric_rtl':'0/5'}
if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parent)))

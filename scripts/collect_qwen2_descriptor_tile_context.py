#!/usr/bin/env python3
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
log=(ROOT/'work/results/qwen2_descriptor_tile_context/tb.log').read_text();m=re.search(r'QWEN2_DESCRIPTOR_TILE_CONTEXT_PASS roots=(\d+) descriptor_fetches=(\d+) shapes=(\d+) address_continuity=(\d+) q1024=(\d+) invalid_preissue=(\d+) stable_backpressure=(\d+)',log)
if not m or tuple(map(int,m.groups()))!=(6,12,6,1,1,1,1):raise SystemExit('tile context PASS missing')
image=json.loads((ROOT/'reports/execution/qwen2_descriptor_image_result.json').read_text())
r={'schema_version':1,'status':'PASS_DESCRIPTOR_BACKED_TILE_CONTEXT','evidence_class':'production_descriptor_port_and_qwen2_RMS_to_Q_context_RTL','commands':2,'tensor_roots':6,'descriptor_fetches':12,'shapes':6,'q1024':True,'address_continuity':True,'invalid_rejected_preissue':True,'stable_under_backpressure':True,'formal_image_sha256':image['packed_records_sha256'],'provenance':{'rtl_log_sha256':sha('work/results/qwen2_descriptor_tile_context/tb.log'),'context_rtl_sha256':sha('rtl/integration/qwen2_descriptor_tile_context.sv'),'formal_image_report_sha256':sha('reports/execution/qwen2_descriptor_image_result.json')},'non_claims':['context snapshot does not move tensor payload bytes','two-command context does not close one full layer']};out=ROOT/'reports/execution/qwen2_descriptor_tile_context_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'roots':6,'fetches':12},sort_keys=True))

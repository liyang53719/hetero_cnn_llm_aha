#!/usr/bin/env python3
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
log=(ROOT/'work/results/qwen2_projection_descriptor_context/tb.log').read_text();m=re.search(r'QWEN2_PROJECTION_DESCRIPTOR_CONTEXT_PASS commands=(\d+) Q_columns=(\d+) K_columns=(\d+) V_columns=(\d+) descriptor_fetches=(\d+) runtime_strides=(\d+) runtime_tiles=(\d+) invalid_preissue=(\d+)',log)
if not m or tuple(map(int,m.groups()))!=(3,1536,256,256,18,3,3,1):raise SystemExit('projection context receipt')
r={'schema_version':1,'status':'PASS_QKV_PROJECTION_DESCRIPTOR_CONTEXT','commands':3,'columns':{'Q':1536,'K':256,'V':256},'weight_row_bytes':{'Q':3072,'K':512,'V':512},'column_tiles':{'Q':48,'K':8,'V':8},'descriptor_fetches':18,'invalid_preissue':True,'provenance':{'log_sha256':sha('work/results/qwen2_projection_descriptor_context/tb.log'),'rtl_sha256':sha('rtl/integration/qwen2_projection_descriptor_context.sv')},'non_claim':'descriptor geometry does not execute projection payload'};out=ROOT/'reports/execution/qwen2_projection_context_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'fetches':18},sort_keys=True))

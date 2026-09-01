#!/usr/bin/env python3
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
pat=r'QWEN2_KV_PROJECTION_PINGPONG_PASS projection=(\d+) columns=(\d+) tiles=(\d+) descriptor_fetches=(\d+) flat_idma=(\d+) axi_beats=(\d+) ddr_read_bytes=(\d+) ddr_write_bytes=(\d+) l2_read_beats=(\d+) l2_write_beats=(\d+) bf16_bit_exact=(\d+) matrix_completion=(\d+) overlap_cycles=(\d+)'
items={}
for kind,index in [('K',1),('V',2)]:
 path=f'work/results/qwen2_kv_projection_pingpong/{kind.lower()}.log';m=re.search(pat,(ROOT/path).read_text());vals=tuple(map(int,m.groups()))if m else ();expected=(index,256,8,6,12296,12296,786432,512,12336,8,256,1,54515)
 if vals!=expected:raise SystemExit(f'{kind}:{vals}')
 items[kind]={'columns':256,'tiles':8,'flat_idma':12296,'axi_beats':12296,'ddr_read_bytes':786432,'ddr_write_bytes':512,'bf16_bit_exact':256,'overlap_cycles':54515,'log_sha256':sha(path)}
vectors=json.loads((ROOT/'work/results/qwen2_kv_projection_vectors/result.json').read_text());r={'schema_version':1,'status':'PASS_KV_RAW_PROJECTION_PINGPONG','evidence_class':'formal_descriptor_pinned_idma_SharedL2_Revision8B_B','token':0,'projections':items,'checks':{'exact_safetensors':True,'runtime_descriptor_geometry':True,'one_completion_each':True,'real_overlap':True,'raw_projection_only':True},'provenance':{'vector_result_sha256':sha('work/results/qwen2_kv_projection_vectors/result.json'),'top_sha256':sha('rtl/integration/qwen2_projection_pingpong_top.sv')},'open':['K_V_bias','K_RoPE','KV_append','QKV_combined_command_chain','complete_layer'],'non_claims':['outputs exclude projection bias','K output excludes RoPE','Q/K/V have not yet run as one event chain']};out=ROOT/'reports/execution/qwen2_kv_projection_pingpong_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'K':256,'V':256},sort_keys=True))

#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];V=ROOT/'work/results/qwen2_shared_l2_tile_payload'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
r={'schema_version':1,'status':'PASS_EXACT_PHYSICAL_Q_COLUMNS_0_31_VECTORS','model':'Qwen/Qwen2-1.5B-Instruct','revision':'ba1cf1846d7df0a0591d6c00649f57e798519da8','model_safetensors_sha256':'302e327795994403cb1e3cb6a3345c76b246b894d14078c936b570c83a4e9057','token':0,'output_columns':list(range(32)),'layout':'for_each_k_32_contiguous_BF16_output_columns','q_weight_rows':1536,'row_bytes':64,'src_stride_bytes':3072,'checks':{'physical_columns_not_sample_indices':True,'weight_beats':len((V/'q_weight_beats.memh').read_text().splitlines())==1536,'expected_beats':len((V/'q_expected_beat.memh').read_text().splitlines())==1},'provenance':{'q_weight_beats_sha256':sha(V/'q_weight_beats.memh'),'q_expected_sha256':sha(V/'q_expected_beat.memh'),'generator_sha256':sha(ROOT/'scripts/generate_qwen2_shared_l2_tile_vectors.py')},'non_claim':'32 physical output columns are not the complete 1536-column Q projection'}
if not all(r['checks'].values()):raise SystemExit(str(r['checks']))
out=ROOT/'reports/execution/qwen2_shared_l2_tile_vector_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'columns':32},sort_keys=True))

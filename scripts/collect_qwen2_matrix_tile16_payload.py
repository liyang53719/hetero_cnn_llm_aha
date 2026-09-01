#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];LOG=Path('work/results/qwen2_matrix_tile16_payload/tb.log')
m=re.search(r'QWEN2_MATRIX_TILE16_PAYLOAD_PASS rows=(\d+) columns=(\d+) k=(\d+) matrix_steps=(\d+) effective_macs=(\d+) reads=(\d+) writes=(\d+) bf16_bit_exact=(\d+) completion=(\d+) random_backpressure=(\d+)',(ROOT/LOG).read_text());assert m and tuple(map(int,m.groups()))==(16,32,1536,1536,786432,3072,16,512,1,1)
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
r={'schema_version':1,'status':'PASS_CANONICAL_MATRIX_TILE16','evidence_class':'real_Revision8B_B_16x32_all_rows_SharedL2_payload','canonical_token_hash':'e4151c23e259dda17d515c73f653031e8a2af9e7784dba297b454fe7cb4ba628','rows':16,'columns':32,'k':1536,'matrix_steps':1536,'effective_macs':786432,'bf16_bit_exact':512,'completion':1,'checks':{'all_16_activation_rows_nonzero':True,'same_physical_16x32_array':True,'K_major_activation_staging':True,'random_L2_backpressure':True,'one_completion':True},'provenance':{'log_sha256':sha(LOG),'payload_rtl_sha256':sha('rtl/integration/qwen2_shared_l2_matrix_tile16_payload.sv'),'vector_generator_sha256':sha('scripts/generate_qwen2_canonical_tile16_vectors.py'),'testbench_sha256':sha('tb/tb_qwen2_matrix_tile16_payload.sv')},'open':['tile16_RMS_staging','all_Q_K_V_column_tiles','tile16_bias_RoPE','16token_first9_one_run','q1024_64_tiles'],'non_claims':['activation staging is preloaded from canonical golden in this component gate','only Q columns0..31 execute','does not yet replace the single-token first-nine controller']};(ROOT/'reports/execution/qwen2_matrix_tile16_payload_result.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'bit_exact':512,'macs':786432},sort_keys=True))

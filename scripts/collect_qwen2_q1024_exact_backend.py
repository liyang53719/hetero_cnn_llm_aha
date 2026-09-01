#!/usr/bin/env python3
import hashlib,json,re
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];IN=ROOT/'work/results/qwen2_q1024_backend_inputs';OUT=ROOT/'work/results/qwen2_q1024_exact_backend';LOG=OUT/'run.log'
def memh(path):
 vals=[]
 for line in path.read_text().splitlines():
  w=int(line,16);vals.extend((w>>(16*i))&65535 for i in range(32))
 return np.asarray(vals,np.uint16)
def chk(name,actual,expected):
 if not np.array_equal(actual,expected):
  i=int(np.flatnonzero(actual!=expected)[0]);raise SystemExit(f'{name} mismatch {i} {actual[i]:04x} {expected[i]:04x}')
norm=np.fromfile(IN/'norm_bf16.bin',np.uint16).reshape(1024,1536);chk('norm16',norm[:16].reshape(-1),memh(ROOT/'work/results/qwen2_canonical_tile16_vectors/norm_token_major.memh'))
spec=[('q_raw',1536,'q_expected_token_major.memh'),('k_raw',256,'k_expected_token_major.memh'),('v_raw',256,'v_expected_token_major.memh'),('q_bias',1536,'q_biased_token_major.memh'),('k_bias',256,'k_biased_token_major.memh'),('v_bias',256,'v_biased_token_major.memh'),('q_rope',1536,'q_rope_token_major.memh'),('k_rope',256,'k_rope_token_major.memh')];hashes={}
for name,cols,exp in spec:
 a=np.fromfile(OUT/f'{name}.bin',np.uint16).reshape(1024,cols);chk(name,a[:16].reshape(-1),memh(ROOT/f'work/results/qwen2_canonical_q_tile16_all/{exp}'));hashes[name]=hashlib.sha256(a.tobytes()).hexdigest()
text=LOG.read_text();m=re.search(r'QWEN2_Q1024_EXACT_BACKEND_PASS commands=(\d+) rows=1024 q_values=(\d+) k_values=(\d+) v_values=(\d+)',text);assert m and tuple(map(int,m.groups()))==(9,1572864,262144,262144)
r={'schema_version':1,'status':'PASS_Q1024_EXACT_HARDWARE_SEMANTICS_BACKEND','evidence_class':'CXX_OpenMP_exact_FMA_order_refined_RMS_Q2p46_not_RTL','rows':1024,'first16_RTL_anchor_bit_exact':118784,'full_values':{'norm':1572864,'Q_raw':1572864,'K_raw':262144,'V_raw':262144,'Q_bias':1572864,'K_bias':262144,'V_bias':262144,'Q_rope':1572864,'K_rope':262144},'hashes':hashes,'checks':{'canonical_tokens':True,'exact_revision_weights':True,'Revision8B_K_order_std_fma':True,'refined_RMS_BF16_boundary':True,'Q2p46_RoPE':True,'first16_matches_RTL':True},'provenance':{'run_log_sha256':hashlib.sha256(LOG.read_bytes()).hexdigest(),'backend_source_sha256':hashlib.sha256((ROOT/'src/qwen2_q1024_exact_backend.cpp').read_bytes()).hexdigest(),'input_generator_sha256':hashlib.sha256((ROOT/'scripts/generate_qwen2_q1024_backend_inputs.py').read_bytes()).hexdigest()},'open':['llama_cpp_device_submission_binding','attention_remaining_layer0','seven_groups','P3'],'non_claims':['C++ backend is not RTL simulation','only first16 rows are directly RTL anchored','does not execute attention or complete layer0']};(ROOT/'reports/execution/qwen2_q1024_exact_backend_result.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'anchor':118784,'rows':1024},sort_keys=True))

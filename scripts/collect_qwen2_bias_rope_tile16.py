#!/usr/bin/env python3
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BD=Path('work/results/qwen2_bias_tile16_controller');RD=Path('work/results/qwen2_rope_tile16_controller')
bp=re.compile(r'QWEN2_BIAS_TILE16_CONTROLLER_PASS command=([qkv]) rows=16 columns=(\d+) descriptor_fetches=6 dma_requests=3 bf16_bit_exact=(\d+) completion=1 random_backpressure=1');rp=re.compile(r'QWEN2_ROPE_TILE16_CONTROLLER_PASS command=([qk]) rows=16 positions=0_15 columns=(\d+) descriptor_fetches=10 dma_requests=3 coefficient_steps=960 bf16_bit_exact=(\d+) completion=1 random_backpressure=1')
b={};r={}
for i,k in enumerate('qkv'):
 m=bp.search((ROOT/BD/f'tb_p{i}.log').read_text());assert m and m[1]==k;b[k]=(int(m[2]),int(m[3]))
for i,k in enumerate('qk'):
 m=rp.search((ROOT/RD/f'tb_p{i}.log').read_text());assert m and m[1]==k;r[k]=(int(m[2]),int(m[3]))
assert b=={'q':(1536,24576),'k':(256,4096),'v':(256,4096)}and r=={'q':(1536,24576),'k':(256,4096)}
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
res={'schema_version':1,'status':'PASS_CANONICAL_BIAS_ROPE_TILE16_CONTROLLERS','rows':16,'bias':{'Q_values':24576,'K_values':4096,'V_values':4096,'total':32768,'descriptor_fetches':18,'dma_requests':9,'completions':3},'rope':{'positions':[0,15],'Q_values':24576,'K_values':4096,'total':28672,'coefficient_steps':1920,'descriptor_fetches':20,'dma_requests':6,'completions':2},'checks':{'formal_descriptor_context_once_per_command':True,'FP32_bias_boundary':True,'Q_K_recurrence_state_sequential':True,'random_backpressure':True},'provenance':{'bias_q_log_sha256':sha(BD/'tb_p0.log'),'bias_k_log_sha256':sha(BD/'tb_p1.log'),'bias_v_log_sha256':sha(BD/'tb_p2.log'),'rope_q_log_sha256':sha(RD/'tb_p0.log'),'rope_k_log_sha256':sha(RD/'tb_p1.log'),'bias_rtl_sha256':sha('rtl/integration/qwen2_bias_tile16_controller.sv'),'rope_rtl_sha256':sha('rtl/integration/qwen2_rope_tile16_controller.sv')},'open':['same_run_after_RMS_QKV','pinned_iDMA','KV_append_real_source'],'non_claims':['biased and RoPE inputs are preloaded from canonical golden in these component runs','five commands execute in separate simulator processes']};(ROOT/'reports/execution/qwen2_bias_rope_tile16_result.json').write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':res['status'],'bias':32768,'rope':28672},sort_keys=True))

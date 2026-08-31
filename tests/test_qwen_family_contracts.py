from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.qwen_family_contracts import family_contract_report

def test_families_are_not_conflated():
 r=family_contract_report(ROOT/'config/model_profiles/qwen3_5_35b_a3b.json',ROOT/'config/model_profiles/qwen3_8_flash_next.json');assert r['status']=='PASS';a=r['qwen3_5_35b_a3b'];b=r['qwen3_8_flash_next'];assert a['hf_model_type']=='qwen3_5_moe';assert b['hf_model_type']=='qwen4_exp';assert a['layer_type_counts']=={'full_attention':10,'gated_deltanet':30};assert b['layer_type_counts']=={'linear_attention':36,'qwen_sparse_attention':12};assert 'dense_full_attention_mlo' in r['qwen3_5_only'];assert all(x in r['qwen3_8_flash_next_only'] for x in ('gated_residual_read','ple_sparse_row_fetch','qsa_streaming_topk'));assert 'qsa_streaming_topk' not in a['schedule_operator_counts'];assert 'dense_full_attention_mlo' not in b['schedule_operator_counts']

def test_schedules_are_deterministic():
 a=family_contract_report(ROOT/'config/model_profiles/qwen3_5_35b_a3b.json',ROOT/'config/model_profiles/qwen3_8_flash_next.json');b=family_contract_report(ROOT/'config/model_profiles/qwen3_5_35b_a3b.json',ROOT/'config/model_profiles/qwen3_8_flash_next.json');assert a['sha256']==b['sha256']

from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.attention_sfu_balance import balance_report,predict_candidate,numerical_vector_report
from heteronpu.qwen_model_resource_envelope import resource_envelope_report

def test_measured_candidate_reproduces_remote_result():
 c=predict_candidate(4,4);assert abs(c.nominal_tps-315.48870639174635)<1e-9;assert abs(c.stress_tps-314.44809739590767)<1e-9;assert not c.hard_floor_pass

def test_balanced_8x8_clears_preferred_floor():
 c=predict_candidate(8,8);assert c.balanced and c.hard_floor_pass and c.preferred_floor_pass;assert c.stress_tps>322;assert c.tile_stress_cycles<336;assert c.merge_stress_cycles<516

def test_sfu_numerical_vectors():
 r=numerical_vector_report();assert r['status']=='PASS';assert r['rows_checked']==80;assert r['max_output_error']<=2e-6

def test_sfu_report_has_measured_and_recommended():
 r=balance_report();assert r['status']=='PASS_SANDBOX_BALANCED_8X8_PREFLIGHT';assert r['recommended_8x8']['preferred_floor_pass'];assert len(r['candidate_table'])==9

def test_distinct_model_resource_envelopes():
 r=resource_envelope_report(ROOT/'config/model_profiles/qwen3_5_35b_a3b.json',ROOT/'config/model_profiles/qwen3_8_flash_next.json');assert r['status']=='PASS_DISTINCT_QWEN_MODEL_RESOURCE_ENVELOPES';q35=r['qwen3_5_35b_a3b'];q38=r['qwen3_8_flash_next'];assert q35['gdn']['state_bytes_all_layers_fp32']==60*1024*1024;assert q38['gdn']['state_bytes_all_layers_fp32']==108*1024*1024;assert q35['kv_and_index']['bf16_bytes_full_context_all_layers']==5*1024**3;assert q38['kv_and_index']['bf16_bytes_full_context_all_layers']==6*1024**3;assert q38['kv_and_index']['qsa_index_bytes_all_layers_bf16']==192*1024**2;assert q35['activation_and_ple']['layout']=='single_residual_stream';assert q38['activation_and_ple']['layout']=='four_branch_hyper_stream'

def test_merge8_source_contract():
 text=(ROOT/'rtl/attention/fp32_mlo_merge8_candidate.sv').read_text();assert text.count('module ')==1;assert text.count('endmodule')==1;assert 'row<8' in text.replace(' ','');assert 'logic [1023:0] oa_i' in text;assert "beat_last==8'hff" in text.replace(' ','')

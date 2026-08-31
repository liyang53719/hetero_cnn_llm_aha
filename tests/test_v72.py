from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.attention_adversarial import adversarial_attention_report
from heteronpu.quant_frontend_integrated import integrated_frontend_report
from heteronpu.state_multislot import stress
from heteronpu.qwen38_multilayer_trace import multilayer_trace_report
from heteronpu.service_curve_importer import import_report,sample_curve

def test_attention_adversarial():
 r=adversarial_attention_report();assert r['status']=='PASS';assert r['random_seed_count']==4;assert r['adversarial_pattern_count']==7;assert r['max_abs']<5e-5

def test_quant_integrated():
 r=integrated_frontend_report(200);assert r['status']=='PASS';assert r['cases']==800;assert r['tag_scale_alignment']=='PASS'

def test_state_multislot():
 r=stress(1000);assert r['status']=='PASS';assert r['max_active_slots']>1;assert r['dirty_mask_merges']>0;assert r['page_leak']==0

def test_qwen38_trace():
 r=multilayer_trace_report();assert r['status']=='PASS';assert r['layers']==4;assert r['prefill_decode_diff']==0;assert r['partition']['fallback']==0

def test_service_curve_importer():
 good=import_report(sample_curve());bad=import_report(sample_curve(degraded=True));assert good['status']=='PASS_REVIEW';assert good['calibration']['tokens_per_second']>=315;assert bad['status'].startswith('FAIL') or bad['status'].startswith('PASS_TARGET_ONLY')

def test_rtl_source_contracts():
 paths=(ROOT/'rtl/quant/ggml_quant_frontend_top.sv',ROOT/'rtl/state/state_multislot_commit_arbiter.sv',ROOT/'rtl/state/state_refcount_cow_table.sv')
 for p in paths:
  text=p.read_text();assert text.count('module ')==text.count('endmodule');assert 'set_false_path' not in text;assert 'multicycle' not in text.lower()
 q=paths[0].read_text();assert 'ggml_quant_k_tail_sequencer' in q and 'ggml_operand_group_decode' in q;assert '$stable(beat_tag_o)' in q
 s=paths[1].read_text();assert 'SLOTS = 8' in s and 'dirty_word_mask_i' in s

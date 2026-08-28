from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.blocked_attention_cycle import AttentionGeometry,blocked_attention_report,sweep_reports

def test_blocked_attention_frozen_counts():
 r=sweep_reports();assert r['status']=='PASS';assert r['frozen_checks']['q1024_summary_merges']==43008;assert r['frozen_checks']['all_score_DDR_materialization_zero'];assert r['cases']['384']['summary_merges']==4608;assert r['cases']['384']['serialized_cycles']==656644;assert r['cases']['384']['serialized_cycles']<1500000

def test_blocked_attention_live_set_and_gqa_reuse():
 c=blocked_attention_report(AttentionGeometry(384));assert c['single_active_head_live_bytes']==31872;assert c['four_head_pingpong_upper_bound_bytes']==254976;assert c['head_microtiles']==c['kv_microtile_uses_after_GQA_reuse']*6

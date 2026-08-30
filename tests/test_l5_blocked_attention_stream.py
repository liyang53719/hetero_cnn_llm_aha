from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.blocked_attention_stream import Geometry,blocked_attention_stream_report,simulate_stream

def test_geometry():
 assert Geometry(128).query_key_pairs==20;assert Geometry(384).query_key_pairs==156;assert Geometry(1024).query_key_pairs==1056;assert Geometry(1024).summary_merges==43008;assert Geometry(128).matrix_pipeline_stages==5

def test_bounded():
 r=simulate_stream(Geometry(384),score_fifo_depth=2,probability_fifo_depth=2);assert r.status=='PASS' and r.overhead_fraction<=.01

def test_stalls():
 r=simulate_stream(Geometry(128),score_fifo_depth=2,probability_fifo_depth=2,matrix_stall_probability=.02,sfu_stall_probability=.05,max_cycles_factor=8);assert r.status=='PASS'

def test_report():
 r=blocked_attention_stream_report();assert r['status']=='PASS';assert r['frozen_invariants']['accepted_matrix_revision']=='Revision8B-B';assert r['frozen_invariants']['matrix_pipeline_stages']==5

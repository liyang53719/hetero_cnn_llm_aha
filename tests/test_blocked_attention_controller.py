import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.blocked_attention_controller import Geometry,build_microtasks,ControllerModel,ServiceConfig,protocol_report

def test_task_geometry_and_merges():
 expected_tasks={128:240,384:1872,1024:12672};expected_merges={128:0,384:4608,1024:43008}
 for sequence in expected_tasks:
  tasks=build_microtasks(Geometry(sequence));assert len(tasks)==expected_tasks[sequence]
  assert sum(task.summary_merge_rows for task in tasks)==expected_merges[sequence]
  assert all(task.kv_head==task.q_head//6 for task in tasks)

def test_random_backpressure_preserves_order():
 r=ControllerModel(Geometry(384),ServiceConfig(matrix_cycles=7,sfu_base_cycles=3,sfu_merge_cycles_per_row=1,matrix_stall_probability=.07,sfu_stall_probability=.11,matrix_command_block_probability=.09,sfu_command_block_probability=.13),seed=44).run(max_cycles_factor=24)
 assert r.status=='PASS' and r.qk_completed==r.total_tasks and r.pv_completed==r.total_tasks
 assert r.max_score_fifo<=2 and r.max_probability_fifo<=2 and r.score_ddr_bytes==0 and r.probability_ddr_bytes==0

def test_q1024_merge_count_and_completion():
 r=ControllerModel(Geometry(1024),ServiceConfig(matrix_cycles=3,sfu_base_cycles=2,sfu_merge_cycles_per_row=1),seed=1024).run(max_cycles_factor=12)
 assert r.status=='PASS' and r.summary_merge_rows==43008 and r.total_tasks==12672

def test_report(): assert protocol_report()['status']=='PASS'

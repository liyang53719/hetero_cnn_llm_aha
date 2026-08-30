from heteronpu.system_e3_model import *
def test_basic():
 g=TaskGraph((Task('read','dma_read',read_bytes=1000,bank_mask=1),Task('matrix','matrix',('read',),100,bank_mask=2),Task('sfu','sfu',('matrix',),20,bank_mask=1)));r=SystemScheduler(SystemConfig()).schedule(g);x={i.name:i for i in r.tasks};assert x['matrix'].start>=x['read'].finish and x['sfu'].start>=x['matrix'].finish
def test_deterministic():
 c=SystemConfig();assert SystemScheduler(c).schedule(build_qwen2_block(128,c))==SystemScheduler(c).schedule(build_qwen2_block(128,c))
def test_report():
 r=system_preflight_report();assert r['status']=='PASS';assert r['sweep']['r100_b16']['block_cycles']<=r['sweep']['r50_b16']['block_cycles'];assert r['selected_preflight']['matrix_duty_cycle']>.7

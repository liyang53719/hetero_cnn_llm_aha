"""Small Python-only full21 self-test evidence, never Chisel/RTL qualification."""
import time,json,hashlib
import numpy as np
import legacy_reference as c
from test_complete import fixture
reports=[]
for cfg in [dict(m=2,hd=16,heads=1,kvheads=1,zero=False),dict(m=1,hd=128,heads=2,kvheads=1,zero=False)]:
 x=fixture(**cfg);budget=c.Budget(500000);trace=[];start=time.monotonic()
 y=c.run(x,budget,cfg['hd'],trace)
 hashes={}
 for name,value in trace:
  values=value if isinstance(value,tuple) else (value,)
  hashes[name]=hashlib.sha256(b''.join(v.astype('<u4').tobytes() for v in values)).hexdigest()
 reports.append(dict(config=cfg,stages=len(trace),seconds=time.monotonic()-start,scalar_budget_consumed=500000-budget.remaining,stage_sha256=hashes))
print(json.dumps(dict(status='PASS_PYTHON_SMALL_SELF_TEST_ONLY',scope='synthetic small full21 mathematical schedule; not original model weights/shapes, Chisel, RTL or numerical cross-comparison',full_m128_hardware_pass=0,reports=reports),indent=2))

"""Synthetic representative forms + targeted synthetic negatives.
Never reads the real SV or invokes a native/EDA/JVM tool.
"""
import copy,importlib.util,json,tempfile
from pathlib import Path
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('new_checker',R/'check_sv.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
# Tiny legacy fixture function is copied in memory, not run against real data.
legacy=R/'test_check_sv.py'
source=legacy.read_text();a=source.index('def module(');b=source.index('\ncount=0',a)
E=json.loads((R/'STRUCTURE_EXPECTATION.json').read_text());E['top_ports']={x:dict(direction='input',width=1,signed=False) for x in ['clock','reset']}
ns={'E':E};exec(compile(source[a:b],str(legacy),'exec'),ns);base=ns['fixture']()
representatives=[{'text':'state <=\n clock ? reset : clock;'}, {'text':'x =\n reset;'}]
count=0
with tempfile.TemporaryDirectory(prefix='proc_syntax_controls_',dir='/tmp') as td:
 p=Path(td)/'tiny.sv'
 def run(body,fail=False):
  global count
  p.write_text(base.replace('wire x = clock;',body,1))
  try:r=c.parse_sv(p,copy.deepcopy(E))
  except ValueError:
   if not fail:raise
  else:
   if fail:raise RuntimeError('negative accepted: '+body)
  count+=1
 for item in representatives:run('always @(posedge clock) begin\n'+item['text']+'\nend')
 run('always @(posedge clock)\nstate <=\n clock ? reset : clock;')
 run('always @* begin\n if (clock) begin\n x =\n reset;\n end\n else begin\n x <=\n clock;\n end\nend')
 for bad in [
  'always @* begin\n if (\n x =\n clock;\n ) reset;\nend',
  'always @* begin\n for (\n x =\n clock;\n ) reset;\nend',
  'always @* begin\n x[clock] <=\n clock;\nend',
  'always @* begin\n x.y <=\n clock;\nend',
  'always @* begin\n x ==\n clock;\nend',
  'always @* begin\n x >=\n clock;\nend',
  'always @* begin\n wire =\n clock;\nend',
  'always @* begin\n x <=\n Unknown u (clock);\nend',
  'always @* begin\n x =\n Unknown(clock);\nend',
  'always @* begin\n x <=\n clock; Hidden h (clock);\nend',
  'always @* begin\n x =\n clock\n end',
  'always @* begin\n x <=\n begin\n clock;\nend',
  'end\nwire x = clock;',
  'always @* begin\n {x,y} <=\n clock;\nend',
  'wire x = clock;\n)',
  'always @* begin\nwire x = clock;',
 ]:run(bad,True)
print(json.dumps(dict(status='PASS_SMALL_PROCEDURAL_SYNTAX_CONTROLS_ONLY',controls=count,synthetic_representative_statements=2,real_sv_read=False,native_EDA_JVM=False)))

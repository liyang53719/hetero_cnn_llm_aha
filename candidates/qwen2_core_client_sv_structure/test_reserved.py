"""Exhaust one pinned reserved-name table on tiny SV; no actual stream reads."""
import copy,hashlib,importlib.util,json,re,tempfile
from pathlib import Path
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('checker',R/'check_sv.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
source=(R/'source/ReservedWords.def').read_text();words=set(re.findall(r'"([A-Za-z_][A-Za-z_0-9$]*)"',re.sub(r'//[^\n]*','',source)))
if words!=c.PINNED_RESERVED_NAMES or sorted(words)!=json.loads((R/'RESERVED_NAMES.json').read_text())['names']:raise RuntimeError('source table mismatch')
E=json.loads((R/'STRUCTURE_EXPECTATION.json').read_text());E['top_ports']={x:dict(direction='input',width=1,signed=False) for x in ['clock','reset']}
s=(R/'test_check_sv.py').read_text();ns={'E':E};a=s.index('def module(');b=s.index('\ncount=0',a);exec(compile(s[a:b],'fixed_tiny_fixture','exec'),ns);base=ns['fixture']();count=0
with tempfile.TemporaryDirectory(prefix='reserved_tiny_',dir='/tmp') as td:
 p=Path(td)/'tiny.sv'
 for name in sorted(words):
  p.write_text(base.replace('wire x = clock;',f'always @* begin\n{name} =\n clock;\nend',1))
  try:c.parse_sv(p,copy.deepcopy(E))
  except ValueError:pass
  else:raise RuntimeError('reserved accepted '+name)
  count+=1
 for name in ['signed_0','_signed','Signed','posedge_value','SYNTHESIS_0']:
  p.write_text(base.replace('wire x = clock;',f'always @* begin\n{name} <=\n clock;\nend',1));c.parse_sv(p,copy.deepcopy(E));count+=1
print(json.dumps(dict(status='PASS_PINNED_RESERVED_TABLE_TINY_CONTROLS_ONLY',table_names=len(words),controls=count,real_SV_read=False,native_EDA_JVM=False)))

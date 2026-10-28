import importlib.util, tempfile, json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('asm',root/'assemble_sv.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
checks=0
def check(x):
 global checks
 if not x:raise RuntimeError('failed')
 checks+=1
def reject(f):
 try:f()
 except ValueError:check(True);return
 raise RuntimeError('negative accepted')
for life in ('','automatic ','static '):check(list(m.modules('module '+life+'foo; endmodule'))==['foo'])
for text in ('module foo;','endmodule','module foo; module bar; endmodule endmodule','module foo; endmodule module foo; endmodule'):reject(lambda:m.modules(text))
check(list(m.modules('// module fake; endmodule\nmodule foo; initial $display("module fake; endmodule"); endmodule'))==['foo'])
with tempfile.TemporaryDirectory() as d:
 a=Path(d)/'a.sv';b=Path(d)/'b.sv'
 for decl in ('import "DPI-C"','import /* gap */ "DPI-C"','export //gap\n "DPI-C"'):
  a.write_text('module foo; '+decl+' function void x(); endmodule');reject(lambda:m.inventory([a]))
 a.write_text('`define X 1\nmodule foo; wire x=`X; endmodule');b.write_text('`define X 0\nmodule foo; wire x=`X; endmodule');v=m.inventory([a,b]);check(v['duplicates'][0]['status']=='EXACT_BODY_ONLY_CONTEXT_UNVERIFIED_NO_DEDUP');check(v['status']=='DEFINITION_INVENTORY_ONLY_NOT_LINK_OR_NUMERIC_PASS')
 b.write_text('module foo; wire y; endmodule');reject(lambda:m.inventory([a,b]))
print(json.dumps({'checks':checks,'status':'PASS_INVENTORY_UNIT_ONLY_NOT_PREPROCESSED_LINK_OR_DUT'}))

import ast,json,hashlib,tempfile,unittest
from pathlib import Path
from check_components import check,ports
import run_components
P=Path(__file__).resolve().parent
class Cold(unittest.TestCase):
 def test_source_closure(self):
  b=json.loads((P/'BASELINE_CLASS_PINS.json').read_text());s=json.loads((P/'SOURCE_PINS.json').read_text());self.assertEqual(len(s),93);self.assertEqual({k:v for k,v in s.items() if not k.startswith('components/')},b['source_sha256']);self.assertEqual(s['components/ProductionFmaComponents.scala'],hashlib.sha256((P/'source/ProductionFmaComponents.scala').read_bytes()).hexdigest())
 def test_no_execute_default(self):
  class A:execute=False
  with self.assertRaises(ValueError):run_components.run(A())
 def test_four_existing_modules(self):
  s=(P/'source/ProductionFmaComponents.scala').read_text();self.assertEqual(s.count('()=>new HeteroBF16Fma'),4);self.assertNotIn('HostBlockTop',s);self.assertIn('--firtool-binary-path',s);self.assertIn('emitSystemVerilog',s)
 def test_parse(self):
  for f in P.glob('*.py'):ast.parse(f.read_text())
 def fixture(self,p):
  expected=json.loads((P/'PORTS.json').read_text());lines=[]
  for i,(name,ps) in enumerate(expected.items()):
   pp=[direction+' '+('' if width==1 else '['+str(width-1)+':0] ')+n for n,(direction,width) in ps.items()];(p/(name+'.sv')).write_text('module '+name+'('+',\n'.join(pp)+');\nendmodule\n')
   names={n:'s'+str(i)+'_'+n for n in ps}
   for n,(direction,width) in ps.items():lines.append('logic '+('' if width==1 else '['+str(width-1)+':0] ')+names[n]+';')
   lines.append(name+' u'+str(i)+'('+','.join('.'+n+'('+names[n]+')' for n in ps)+');')
  lane=p.parent/(p.name+'_lane.txt');lane.write_text('\n'.join(lines));self.addCleanup(lane.unlink,missing_ok=True);return lane
 def test_ports_inventory_and_width_mutants(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);lane=self.fixture(p);self.assertEqual(len(check(p,lane)['files']),4)
   f=p/'HeteroBF16FmaPre.sv';s=f.read_text();f.write_text(s.replace('[53:0] io_meta','[52:0] io_meta'))
   with self.assertRaises(ValueError):check(p,lane)
   f.write_text(s);lane.write_text(lane.read_text().replace('[53:0] s0_io_meta','[52:0] s0_io_meta'))
   with self.assertRaises(ValueError):check(p,lane)
 def test_indented_same_line_and_comment_modules(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);lane=self.fixture(p)
   pre=p/'HeteroBF16FmaPre.sv';mul=p/'HeteroBF16FmaMul.sv';a=pre.read_text();b=mul.read_text()
   pre.write_text(a+'/* module ignored(); endmodule */\n// module ignored2(); endmodule\n');self.assertEqual(len(check(p,lane)['files']),4)
   for extra in ['  module duplicate(); endmodule\n','module duplicate(); endmodule module duplicate(); endmodule\n']:
    pre.write_text(a+extra);mul.write_text(b+extra)
    with self.assertRaises(ValueError):check(p,lane)
   pre.write_text(a+'module unsupported; endmodule\n');mul.write_text(b)
   with self.assertRaises(ValueError):check(p,lane)
 def test_extra_inventory_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'components';p.mkdir();lane=self.fixture(p);extra=p/'sub';extra.mkdir();(extra/'x.sv').write_text('module x(); endmodule')
   with self.assertRaises(ValueError):check(p,lane)
   (extra/'x.sv').unlink();extra.rmdir();target=p/'HeteroBF16FmaPre.sv';saved=Path(d)/'saved';target.rename(saved);target.symlink_to(saved)
   with self.assertRaises(ValueError):check(p,lane)
 def test_duplicate_helper_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);lane=self.fixture(p)
   for name in ['Pre','Mul']:
    f=p/('HeteroBF16Fma'+name+'.sv');f.write_text(f.read_text()+'module duplicate();\nendmodule\n')
   with self.assertRaises(ValueError):check(p,lane)
if __name__=='__main__':unittest.main()

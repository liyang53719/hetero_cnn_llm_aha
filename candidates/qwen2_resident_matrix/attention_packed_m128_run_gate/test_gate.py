import ast,unittest,tempfile
from pathlib import Path
from . import prepare as p
class Tests(unittest.TestCase):
 def test_exact_single_guard_delta(self):
  with tempfile.TemporaryDirectory() as d:
   root=p.prior.compose(Path(d)/'old');before=(root/p.TARGET).read_text();after=p.repair(before)
   self.assertEqual(after.replace(p.NEW,p.OLD),before)
   self.assertNotIn(p.OLD,after)
   for text in (after,before.replace(p.OLD,p.OLD+'\n'+p.OLD)):
    with self.assertRaises(ValueError):p.repair(text)
   a=ast.parse(before);b=ast.parse(after)
   ar=next(n for n in a.body if isinstance(n,ast.FunctionDef) and n.name=='run')
   br=next(n for n in b.body if isinstance(n,ast.FunctionDef) and n.name=='run')
   # Only the exact guard's row literal and diagnostic string can differ.
   for n in ast.walk(br):
    if isinstance(n,ast.Constant) and n.value=='linked packed M128 requires exact M128 snapshot and verified M16 prerequisite':n.value='enabled raw KV execution is limited to M16 pending a reviewed same-source M16 receipt'
   gate=next(n for n in ast.walk(br) if isinstance(n,ast.Compare) and isinstance(n.left,ast.Call) and isinstance(n.left.func,ast.Name) and n.left.func.id=='validate_rows')
   gate.comparators[0].value=16
   self.assertEqual(ast.dump(ar,include_attributes=False),ast.dump(br,include_attributes=False))
 def test_closed_composition(self):
  with tempfile.TemporaryDirectory() as d:
   root=p.compose(Path(d)/'new')
   import json
   pin=json.loads((root/p.ENTRY).read_bytes());m={**pin['sources'],**pin['own'],**pin['generated'],p.ENTRY:p.sha(root/p.ENTRY)}
   self.assertEqual(len(m),350)
   self.assertEqual({str(x.relative_to(root)) for x in root.rglob('*') if x.is_file()},set(m))
   self.assertTrue(all(p.sha(root/n)==h for n,h in m.items()))
if __name__=='__main__':unittest.main()

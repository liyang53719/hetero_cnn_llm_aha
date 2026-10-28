import ast,types,unittest
from pathlib import Path
class CacheDictionary(unittest.TestCase):
 def setUp(self):
  tree=ast.parse((Path(__file__).parent/'run_reference.py').read_text());nodes=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='flatten'];self.assertEqual(len(nodes),1)
  self.Tensor=type('Tensor',(),{});self.state={}
  def require(ok,msg):
   if not ok:raise ValueError(msg)
  env=dict(torch=types.SimpleNamespace(Tensor=self.Tensor),state=self.state,require=require)
  exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'isolated_actual_flatten','exec'),env);self.flatten=env['flatten']
 def test_original_dictionary(self):
  t=self.Tensor();self.flatten('conv_states',{0:t});self.assertEqual(self.state,{'conv_states.0':t})
 def test_two_states(self):
  a,b=self.Tensor(),self.Tensor();self.flatten('r',{1:b,0:a});self.assertEqual(list(self.state),['r.0','r.1'])
 def test_invalid_keys(self):
  for d in ({'0':self.Tensor()},{True:self.Tensor()},{-1:self.Tensor()},{}):
   with self.assertRaises(ValueError):self.flatten('r',d)
 def test_tensor_list_and_none(self):
  t=self.Tensor();self.flatten('r',[t,None]);self.assertEqual(self.state,{'r.0':t})
if __name__=='__main__':unittest.main()

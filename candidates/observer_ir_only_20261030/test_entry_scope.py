"""Source scope regression and no-process synthetic census boundaries."""
import ast,os,pathlib,stat,tempfile,unittest
from unittest.mock import Mock,patch
import run_ir_only as m
class EntryScope(unittest.TestCase):
 def caps_ast(self):
  tree=ast.parse(pathlib.Path(m.__file__).read_text())
  return next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='caps' for t in n.targets))
 def test_all_stages_same_aggregate_cap(self):
  c=self.caps_ast();row=next(k.value for k in c.keywords if k.arg=='max_entries');self.assertEqual(ast.literal_eval(row),100000)
  roots=next(k.value for k in c.keywords if k.arg=='extra_watch_roots');self.assertEqual(ast.unparse(roots),'[str(repo), str(work)]')
 def census(self,count):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);repo=root/'repo';work=root/'work';repo.mkdir();work.mkdir()
   caps=dict(max_entries=100000,watch_tree_bytes=1024,file_bytes=1024,min_free_disk_bytes=0,extra_watch_roots=[str(repo),str(work)])
   def walk(path,**kw):
    self.assertFalse(kw['followlinks']);return iter([(str(path),[],[str(i) for i in range(count)] if path==repo else [])])
   row=os.stat_result((stat.S_IFREG|0o600,1,1,1,0,0,0,0,0,0));supervisor=Mock();supervisor.execute.return_value={'old_execute':True}
   with patch.object(m.os,'walk',side_effect=walk),patch.object(pathlib.Path,'lstat',return_value=row):
    try:result=m.admitted_execute(supervisor,['not-launched'],str(work/'stage'),str(work/'lock'),caps,{}, {},resource_gate={})
    except ValueError:
     supervisor.execute.assert_not_called();raise
    supervisor.execute.assert_called_once();return result
 def test_more_than_old_local20k_reuses_aggregate_contract(self):self.assertEqual(self.census(20001),{'old_execute':True})
 def test_aggregate_limit_with_eight_reserved_accepts(self):self.assertEqual(self.census(99992),{'old_execute':True})
 def test_aggregate_limit_with_eight_reserved_rejects(self):
  with self.assertRaisesRegex(ValueError,'preflight entry cap'):self.census(99993)
 def test_over_aggregate100k_rejects(self):
  with self.assertRaisesRegex(ValueError,'preflight entry cap'):self.census(100001)
if __name__=='__main__':unittest.main()

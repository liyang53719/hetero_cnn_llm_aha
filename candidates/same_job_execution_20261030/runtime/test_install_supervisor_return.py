"""Execute actual small AST call sites with a synthetic supervisor only."""
import ast,hashlib,json
from pathlib import Path
import tempfile,types,unittest
D=Path(__file__).resolve().parent
SOURCE=D/'install_job.py'
BASE='e19df40b9d1832a579e2ea3e3ea97c9b0dc37a23e3288a46f7cd211347d76404'
def tree():return ast.parse(SOURCE.read_text())
def callsite(body):
 for i,n in enumerate(body):
  if isinstance(n,ast.Assign)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Attribute)and n.value.func.attr=='execute':return i
 return None
class Tests(unittest.TestCase):
 def test_only_two_saves_added(self):
  t=tree();count=0
  for parent in ast.walk(t):
   for name,value in ast.iter_fields(parent):
    if isinstance(value,list):
     removed=[]
     for i,n in enumerate(value):
      if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='save'and 'SUPERVISOR_RETURN.json'in ast.unparse(n):
       self.assertEqual(callsite(value[i-1:i]),0);removed.append(i);count+=1
     for i in reversed(removed):del value[i]
  self.assertEqual(count,2)
  self.assertEqual(hashlib.sha256(ast.dump(t,include_attributes=False).encode()).hexdigest(),BASE)
 def test_actual_sites_success_failure_and_prelaunch(self):
  for role in ('install','bind'):
   for status in ('prelaunch','failure','success'):
    with self.subTest(role=role,status=status),tempfile.TemporaryDirectory()as tmp:
     root=Path(tmp);(root/'results').mkdir();key='qwen35_08b';out=root/'runs'/(key if role=='install'else'bind')
     receipt={'native_exit':0 if status=='success'else 1 if status=='failure'else None,'errors':[]if status=='success'else['synthetic failure detail'],
      'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'}if status!='prelaunch'else{},
      'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}if status!='prelaunch'else{}}
     if status!='prelaunch':out.mkdir(parents=True);(out/'RESULT.json').write_text(json.dumps(receipt))
     original=(out/'RESULT.json').read_bytes()if status!='prelaunch'else None
     env={'P':Path,'json':json,'root':root,'k':key,'r':None,'owner_binding':{'runtimes':{key:{'argv':['synthetic']}}},
      'b':{'lock':'synthetic','python':'synthetic'},'caps':{},'env':{},'execution_pins':{},'resource_limits':{},
      'bindrun':out,'D':D,'metadata':D/'unread.json','bindcaps':{},'bindpins':{},'sha':lambda p:'synthetic',
      'pending':1,'live':types.SimpleNamespace(census=None),'supervisor':types.SimpleNamespace(execute=lambda *a,**k:receipt)}
     t=tree();defs=[n for n in t.body if isinstance(n,ast.FunctionDef)and n.name in('save','complete','need','bind_resource_gate')]
     exec(compile(ast.Module(body=defs,type_ignores=[]),str(SOURCE),'exec'),env)
     name=(key if role=='install'else'bind')+'_SUPERVISOR_RETURN.json'
     snapshots=[]
     def snapshot(*args):
      self.assertEqual(json.loads((root/'results'/name).read_text()),receipt);snapshots.append(True)
     env['snapshot']=snapshot
     if role=='install':
      tr=next(n for n in ast.walk(t)if isinstance(n,ast.Try)and callsite(n.body)is not None)
      parent=next(n for n in ast.walk(t)if hasattr(n,'body')and isinstance(n.body,list)and tr in n.body)
      block=[tr,parent.body[parent.body.index(tr)+1]]
     else:
      run=next(n for n in t.body if isinstance(n,ast.FunctionDef)and n.name=='run');i=callsite(run.body);block=run.body[i:i+3]
     code=compile(ast.Module(body=block,type_ignores=[]),str(SOURCE),'exec')
     if status=='success':exec(code,env)
     else:
      with self.assertRaises(ValueError):exec(code,env)
     self.assertEqual(json.loads((root/'results'/name).read_text()),receipt)
     if role=='install':self.assertEqual(snapshots,[True])
     if original is None:self.assertFalse(out.exists())
     else:self.assertEqual((out/'RESULT.json').read_bytes(),original)
if __name__=='__main__':unittest.main()

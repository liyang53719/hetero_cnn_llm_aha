"""Portable, synthetic-only differential census tests. Never imports execute.
Run: python test_supervisor_lowobject.py; python -O test_supervisor_lowobject.py.
Place next to supervise_multiroot.py. Baseline is a bounded function fragment,
not a runnable supervisor. No actual project roots are traversed.
"""
import ast, os, stat, shutil, tempfile, types, resource, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASELINE_SUPERVISOR_SHA256='8cbc6858c71feb821723ee1954902b59f046c31bfe2d1fa561529dc422035684'
BASELINE_OUTPUT_SAMPLE="def output_sample():\n total=largest=count=stage_total=0\n roots=[run]+[Path(x).absolute() for x in caps.get('extra_watch_roots',[])]\n unique=[]\n for root in sorted(set(roots),key=lambda p:len(p.parts)):\n  if not any(root.is_relative_to(q) for q in unique):unique.append(root)\n seen=set()\n for root in unique:\n  for base,dirs,files in os.walk(root,followlinks=False):\n   for name in dirs+files:\n    p=Path(base)/name\n    try:s=p.lstat()\n    except FileNotFoundError:continue\n    count+=1;need(count<=caps['max_entries'],'entry cap')\n    if stat.S_ISLNK(s.st_mode):\n     need(not p.is_relative_to(run),'output link forbidden');continue\n    need(stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode),'nonregular output')\n    if stat.S_ISREG(s.st_mode):\n     key=(s.st_dev,s.st_ino)\n     if key not in seen:\n      seen.add(key);total+=s.st_size;largest=max(largest,s.st_size)\n      if p.is_relative_to(run):stage_total+=s.st_size\n for root in unique:\n  if root.exists():need(shutil.disk_usage(root).free>=caps.get('min_free_disk_bytes',0),'sampled disk reserve')\n report['peak_tree_bytes']=max(report['peak_tree_bytes'],total);report['peak_file_bytes']=max(report['peak_file_bytes'],largest)\n need(total<=caps.get('watch_tree_bytes',caps['tree_bytes']),'sampled aggregate writable-root cap');need(stage_total<=caps['tree_bytes'],'sampled stage output tree cap');need(largest<=caps['file_bytes'],'file cap');need(os.fstat(log.fileno()).st_size<=caps['log_bytes'],'sampled log cap')\n"

def extract(text, filename):
 tree=ast.parse(text)
 functions=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='output_sample']
 if len(functions)!=1:raise ValueError('unique output_sample required')
 return compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),filename,'exec')
CODES=[extract(BASELINE_OUTPUT_SAMPLE,'baseline_output_sample'),extract((HERE/'supervise_multiroot.py').read_text(),'supervise_multiroot.py')]

def trial(code, run, roots, caps_update=None, missing=None):
 caps=dict(extra_watch_roots=list(map(str,roots)),max_entries=1000,file_bytes=100000,tree_bytes=100000,watch_tree_bytes=100000,log_bytes=100000,min_free_disk_bytes=0)
 caps.update(caps_update or {});report={'peak_tree_bytes':0,'peak_file_bytes':0};trace=[]
 old=os.lstat;oldstat=os.stat
 def fresh(path,*a,**k):
  trace.append(os.fspath(path))
  if missing and os.fspath(path)==str(missing):raise FileNotFoundError(str(path))
  return old(path,*a,**k)
 def fresh_stat(path,*a,**k):
  if k.get("follow_symlinks") is False:return fresh(path,*a)
  return oldstat(path,*a,**k)
 def need(ok,msg):
  if not ok:raise ValueError(msg)
 with tempfile.TemporaryFile() as log:
  env=dict(Path=Path,os=os,stat=stat,shutil=shutil,run=run,caps=caps,report=report,log=log,need=need)
  exec(code,env);os.lstat=fresh;os.stat=fresh_stat
  try:
   try:env['output_sample']();error=None
   except (ValueError,OSError) as e:error=(type(e).__name__,str(e))
  finally:os.lstat=old;os.stat=oldstat
 return report,error,trace


class CensusDifferential(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='lowobject-portable-')
  self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.run=self.root/'stage';self.run.mkdir()
  self.outside=self.root/'stage_suffix';self.outside.mkdir()
  (self.run/'dir').mkdir();(self.run/'dir'/'nested').write_bytes(b'n'*11)
  (self.run/'a').write_bytes(b'a'*17);(self.outside/'b').write_bytes(b'b'*23)
  os.link(self.run/'a',self.outside/'hardlink')
  os.symlink(self.run/'a',self.outside/'allowed_link')
  self.roots=[self.root,self.run,self.run/'dir',self.outside]
 def compare(self,expected=None,**kw):
  a=trial(CODES[0],self.run,self.roots,**kw)
  b=trial(CODES[1],self.run,self.roots,**kw)
  self.assertEqual(a,b) # includes ordered fresh-lstat trace, not merely final totals
  self.assertEqual(a[1],expected)
  return a
 def test_nested_hardlink_symlink_prefix_and_order(self):
  a=self.compare();self.assertEqual(a[0],{'peak_tree_bytes':51,'peak_file_bytes':23})
 def test_disappearance_at_fresh_stat(self):
  self.compare(missing=self.run/'a')
 def test_entry_limit(self):self.compare(('ValueError','entry cap'),caps_update={'max_entries':1})
 def test_file_limit(self):self.compare(('ValueError','file cap'),caps_update={'file_bytes':1})
 def test_aggregate_limit(self):self.compare(('ValueError','sampled aggregate writable-root cap'),caps_update={'watch_tree_bytes':1})
 def test_stage_limit(self):self.compare(('ValueError','sampled stage output tree cap'),caps_update={'tree_bytes':1})
 def test_free_disk_limit(self):self.compare(('ValueError','sampled disk reserve'),caps_update={'min_free_disk_bytes':2**80})
 def test_log_limit(self):self.compare(('ValueError','sampled log cap'),caps_update={'log_bytes':-1})
 def test_stage_symlink(self):
  os.symlink(self.outside/'b',self.run/'forbidden');self.compare(('ValueError','output link forbidden'))
 def test_fifo(self):
  os.mkfifo(self.run/'fifo');self.compare(('ValueError','nonregular output'))
 def test_lexical_containment_all_anchors(self):
  for r in ['/', '//', '/tmp/stage', '/tmp/stage/../stage']:
   rp=Path(r);parts=rp.parts
   for base in ['/', '//', '/tmp', '/tmp/stage', '/tmp/stage_suffix','/tmp/stage/..']:
    bp=Path(base).parts
    for name in ['stage','a']:
     with self.subTest(run=r,base=base,name=name):
      actual=bp[:len(parts)]==parts or (bp==parts[:-1] and name==parts[-1])
      self.assertEqual(actual,(Path(base)/name).is_relative_to(rp))

if __name__=='__main__':
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
 resource.setrlimit(resource.RLIMIT_CPU,(15,)*2)
 unittest.main(verbosity=2)

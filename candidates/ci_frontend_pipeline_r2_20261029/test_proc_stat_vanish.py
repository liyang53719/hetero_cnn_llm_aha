"""Tiny portable Linux regression fixture, no build/EDA or supervisor launch.

Run with --source <supervise_multiroot.py>. Only the census for-loop is extracted
with AST and executed over one explicitly owned synthetic PID. A real stat
file is opened, that child exits normally, and its real read returns ESRCH.
Other I/O errors must propagate. No retry or project-state changes.
"""
import argparse,ast,errno,os,pathlib,resource,subprocess,sys,types,unittest
parser=argparse.ArgumentParser();parser.add_argument('--source',type=pathlib.Path,default=pathlib.Path(__file__).with_name('supervise_multiroot.py'));args,rest=parser.parse_known_args();sys.argv=[sys.argv[0]]+rest
source=args.source.read_text();tree=ast.parse(source)
samples=[n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='process_sample']
if len(samples)!=1:raise RuntimeError('unique process_sample')
loops=[n for n in samples[0].body if isinstance(n,ast.For)and isinstance(n.target,ast.Name)and n.target.id=='name'and isinstance(n.iter,ast.Name)and n.iter.id=='names']
if len(loops)!=1:raise RuntimeError('unique census enumeration')
code=compile(ast.Module(body=loops,type_ignores=[]),str(args.source),'exec')

def trial(path_cls,pid):
 report={};ns={'Path':path_cls,'names':[str(pid)],'strict':types.SimpleNamespace(parse_stat=lambda raw: {'pid':pid}),'snapshot':{},'rawfields':{},'report':report};exec(code,ns);return report

class Tests(unittest.TestCase):
 def test_real_linux_process_exit_during_stat_read(self):
  child=subprocess.Popen([sys.executable,'-B','-c','import sys;sys.stdin.buffer.read(1)'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  errors=[]
  class NativeRacePath(type(pathlib.Path())):
   def read_bytes(self):
    with self.open('rb') as stream:
     child.stdin.write(b'x');child.stdin.close();child.wait(timeout=3)
     try:return stream.read()
     except OSError as error:errors.append((type(error).__name__,error.errno));raise
  try:
   report=trial(NativeRacePath,child.pid)
   self.assertEqual(errors,[('ProcessLookupError',errno.ESRCH)])
   self.assertEqual(child.returncode,0)
   self.assertEqual(report.get('proc_stat_vanished_count'),1)
  finally:
   if child.poll() is None:child.kill();child.wait(timeout=3)
 def test_enoent_same_absence_semantics(self):
  class MissingPath(type(pathlib.Path())):
   def read_bytes(self):raise FileNotFoundError(errno.ENOENT,'synthetic vanished before open')
  self.assertEqual(trial(MissingPath,1).get('proc_stat_vanished_count'),1)
 def test_permission_and_io_remain_fail_closed(self):
  for error in (PermissionError(errno.EACCES,'synthetic denied'),OSError(errno.EIO,'synthetic I/O error')):
   class ErrorPath(type(pathlib.Path())):
    def read_bytes(self):raise error
   with self.subTest(errno=error.errno),self.assertRaises(type(error)) as caught:trial(ErrorPath,1)
   self.assertEqual(caught.exception.errno,error.errno)
if __name__=='__main__':
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(10,10));resource.setrlimit(resource.RLIMIT_AS,(128<<20,128<<20));unittest.main(verbosity=2)

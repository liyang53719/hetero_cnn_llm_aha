import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import builtins,hashlib,json,tempfile,types
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).absolute().parent
PIN=(2623,'aa7c51ac72cc79cb7622d522a2dd1221db8d2144a9917010f93014777fbf13bb')
raw=(ROOT/'run_entry.py').read_bytes()
if (len(raw),hashlib.sha256(raw).hexdigest())!=PIN:raise ValueError('entry pin')
def audit(event,args):
 if event.startswith(('subprocess.','socket.')) or event in ('os.system','os.fork','os.exec','os.posix_spawn','urllib.Request'):raise RuntimeError('native/network forbidden')
sys.addaudithook(audit)
anchor=b'p=argparse.ArgumentParser';ns={'__name__':'_entry','__file__':str(ROOT/'run_entry.py')}
exec(compile(raw.split(anchor)[0],'fixed_entry_prefix','exec'),ns)
checks=[]
def need(ok,why):
 if not ok:raise ValueError(why)
def compile_read(path):return compile(ns['read'](path,ns['PINS']['qualification_entry.py']),str(path),'exec')
def rejects(fn):
 try:fn()
 except (ValueError,OSError):return
 raise ValueError('missing reject')
compile_read(ROOT/'qualification_entry.py');checks.append('valid_same_buffer_compile_only_no_execution')
data=(ROOT/'qualification_entry.py').read_bytes()
for kind in ('hash','short','symlink'):
 with tempfile.TemporaryDirectory(dir=ROOT) as t:
  p=Path(t)/'qualification_entry.py'
  if kind=='hash':p.write_bytes(bytes([data[0]^1])+data[1:])
  elif kind=='short':p.write_bytes(data[:-1])
  else:
   real=Path(t)/'real';real.write_bytes(data);p.symlink_to(real)
  with mock.patch.object(builtins,'compile',side_effect=AssertionError('unverified entry compiled')):rejects(lambda:compile_read(p))
 checks.append(kind+'_before_compile')
seen=[]
def importer(name,*a,**k):
 seen.append(name)
 if name=='sys':return types.SimpleNamespace(flags=types.SimpleNamespace(isolated=False,no_site=True,dont_write_bytecode=True))
 raise AssertionError('late import')
try:exec(compile(raw,'flag_test','exec'),{'__builtins__':dict(vars(builtins),__import__=importer)})
except SystemExit:pass
else:raise ValueError('missing flags')
need(seen==['sys'],'guard before read');checks.append('flags_before_source_loading')
print(json.dumps({'status':'PASS_QUALIFICATION_ENTRY_COLD','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False},sort_keys=True))

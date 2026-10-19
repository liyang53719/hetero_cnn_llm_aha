"""Pinned source-entry positive/negative checks. No child processes or network."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import builtins,contextlib,hashlib,io,json,os,tempfile,types
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).absolute().parent
ENTRY_PIN=(1963, 'ec8c5b95d5a70dbbdbbe53d3cab230f2a5298b1cb69e2cdce653959b582fee04')
entry=(ROOT/'source_entry.py').read_bytes()
if (len(entry),hashlib.sha256(entry).hexdigest())!=ENTRY_PIN:raise ValueError('entry pin')
repo=Path(sys.argv[1]);checks=[]
def audit(event,args):
 if event.startswith(('subprocess.','socket.')) or event in ('os.system','os.fork','os.exec','os.posix_spawn','urllib.Request'):raise RuntimeError('native/network forbidden')
sys.addaudithook(audit)
def need(ok,reason):
 if not ok:raise ValueError(reason)
def run(entry_path,compile_forbidden=False):
 code=compile(entry,str(entry_path),'exec',dont_inherit=True)
 scope={'__name__':'entry_cold','__file__':str(entry_path)}
 with mock.patch.object(sys,'argv',[str(entry_path),'--repo',str(repo)]),contextlib.redirect_stdout(io.StringIO()) as out:
  if compile_forbidden:
   with mock.patch.object(builtins,'compile',side_effect=AssertionError('unverified bootstrap reached compile')):exec(code,scope)
  else:exec(code,scope)
 return out.getvalue()
def rejects(fn):
 try:fn()
 except (ValueError,OSError):return
 raise ValueError('expected entry rejection')
need(json.loads(run(ROOT/'source_entry.py'))['status']=='SOURCE_ONLY_UNBOUND_NO_ACQUISITION_OR_NATIVE','positive entry');checks.append('valid_control_source_only')
raw=(ROOT/'bootstrap.py').read_bytes()
for variant in ('same_size_hash','short_size','symlink'):
 with tempfile.TemporaryDirectory(dir=ROOT) as t:
  p=Path(t);target=p/'bootstrap.py'
  if variant=='same_size_hash':target.write_bytes(bytes([raw[0]^1])+raw[1:])
  elif variant=='short_size':target.write_bytes(raw[:-1])
  else:
   (p/'real').write_bytes(raw);target.symlink_to(p/'real')
  rejects(lambda:run(p/'source_entry.py',True));checks.append(variant+'_before_compile')
with tempfile.TemporaryDirectory(dir=ROOT) as t:
 p=Path(t);(p/'real').mkdir();(p/'real/bootstrap.py').write_bytes(raw);(p/'alias').symlink_to(p/'real',target_is_directory=True)
 rejects(lambda:run(p/'alias/source_entry.py',True));checks.append('parent_symlink_before_compile')
seen=[]
def importer(name,*a,**k):
 seen.append(name)
 if name=='sys':return types.SimpleNamespace(flags=types.SimpleNamespace(isolated=False,no_site=True,dont_write_bytecode=True))
 raise AssertionError('late import before guard')
try:exec(compile(entry,'entry_guard','exec'),{'__builtins__':dict(vars(builtins),__import__=importer),'__name__':'guard'})
except SystemExit:pass
else:raise ValueError('missing guard rejection')
need(seen==['sys'],'guard must precede project read');checks.append('early_flags_before_import_or_source_read')
print(json.dumps({'status':'PASS_PINNED_ENTRY_COLD_ONLY','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'network_started':False,'native_child_started':False},sort_keys=True))

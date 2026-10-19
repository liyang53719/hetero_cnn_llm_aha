import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import builtins,hashlib,json,tempfile,types
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).absolute().parent
PIN=(3370, 'c7ff5dea6fa5ff11c08cde9f265531ae610abf4b5e141fb587c4a72dffdb7abf')
raw=(ROOT/'observer_entry.py').read_bytes()
if (len(raw),hashlib.sha256(raw).hexdigest())!=PIN:raise ValueError('entry source identity')
def audit(event,args):
 if event.startswith(('subprocess.','socket.')) or event in ('os.system','os.fork','os.exec','os.posix_spawn','urllib.Request'):raise RuntimeError('native/network forbidden')
sys.addaudithook(audit)
anchor=b'p=argparse.ArgumentParser(allow_abbrev=False)'
if raw.count(anchor)!=1:raise ValueError('one prefix anchor')
ns={'__name__':'_entry_cold','__file__':str(ROOT/'observer_entry.py')}
exec(compile(raw.split(anchor)[0],'same_buffer_entry_prefix','exec',dont_inherit=True),ns)
checks=[]
def need(ok,why):
 if not ok:raise ValueError(why)
def rejects(fn):
 try:fn()
 except (ValueError,OSError):return
 raise ValueError('expected refusal')
for name in ('binding_observer.py','local_mount_profile.py'):
 obj=ns['loaded'](ROOT/name,name);need(obj.__file__==str(ROOT/name),'valid load');checks.append(name+'_valid_control')
 data=(ROOT/name).read_bytes()
 for kind in ('same_size_hash','short','symlink'):
  with tempfile.TemporaryDirectory(dir=ROOT) as t:
   path=Path(t)/name
   if kind=='same_size_hash':path.write_bytes(bytes([data[0]^1])+data[1:])
   elif kind=='short':path.write_bytes(data[:-1])
   else:
    other=Path(t)/'real';other.write_bytes(data);path.symlink_to(other)
   with mock.patch.object(builtins,'compile',side_effect=AssertionError('unverified source reached compile')):rejects(lambda:ns['loaded'](path,name))
  checks.append(name+'_'+kind+'_before_compile')
seen=[]
def importer(name,*a,**k):
 seen.append(name)
 if name=='sys':return types.SimpleNamespace(flags=types.SimpleNamespace(isolated=False,no_site=True,dont_write_bytecode=True))
 raise AssertionError('late import')
try:exec(compile(raw,'flag_guard','exec'),{'__builtins__':dict(vars(builtins),__import__=importer)})
except SystemExit:pass
else:raise ValueError('guard missing')
need(seen==['sys'],'guard before source');checks.append('flags_before_project_read')
print(json.dumps({'status':'PASS_PINNED_BINDING_ENTRY_COLD','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False},sort_keys=True))

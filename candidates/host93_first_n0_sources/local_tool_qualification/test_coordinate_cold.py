import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import ast,copy,json,os,tempfile,time,types
from pathlib import Path
from unittest import mock
# Whole parent state machine with synthetic source modules/callbacks; actual
# package helper/adapter contracts are tested separately against real code.
checks=[]
def need(ok,text):
 if not ok:raise ValueError(text)
def rejects(fn,text):
 try:fn()
 except ValueError as e:need(text in str(e),'wrong failure '+str(e));return
 raise ValueError('missing rejection')
raw=ENTRY_SOURCE
nodes={n.name:n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)};lines=raw.splitlines(keepends=True)
function=b''.join(lines[nodes['parent_run'].lineno-1:nodes['parent_run'].end_lineno])+b'\n'

def case(bad=None):
 with tempfile.TemporaryDirectory(dir=ROOT) as t:
  root=Path(t);q=root/'qualification';dep=root/'dependency';records=[];saved={};loaded_phases=[];callbacks=[]
  class FS:
   def fresh_directory(self,p):p.mkdir(mode=0o700)
  fs=FS();stage={'files':69,'synthetic':True};result={'stage_result':stage};b={'work_root':str(dep)}
  def write(name,value):
   saved[name]=value;(q/name).write_bytes(json.dumps(value).encode());return {'bytes':len((q/name).read_bytes()),'sha256':'f'*64}
  g=types.SimpleNamespace(child_environment=lambda b:{'HOME':'unused','TMPDIR':'unused'},system_identities=lambda *x:{},STAGE_LIMITS={'total_seconds':60},decode=json.loads,checked=lambda p,*args:(q/p.name).read_bytes())
  def fixed_support(repo):return fs,{},{}
  def run_phase(support,base,name,argv,cwd,evidence,environment,limits,stop,owner):
   loaded_phases.append(name)
   if name.startswith('local_dependencies_'):
    need(argv[:5]==['/usr/bin/python3','-I','-S','-B','-c'],'pinned Python child argv')
    need('ENTRY_BYTES' in argv[5] and 'PRIOR_PINS' in argv[5],'same-buffer child and same-parent data pins')
    val=result if name=='local_dependencies_stage_preset' else {'synthetic':True}
    out=json.dumps(val).encode()
   else:out=b'probe synthetic'
   if bad==name:return {'exit_code':1,'cleanup_confirmed':False},out,{}
   return {'exit_code':0,'cleanup_confirmed':True},out,{}
  supervisor=types.SimpleNamespace(fixed_support=fixed_support,run_phase=run_phase)
  def qualify(support,tools,buffers,work,callback,env):
   for kind in ('version','micro'):
    for tool in ('autoconf','autom4te','m4','flex','bison'):
     callback('host_'+tool+'-'+kind,['/synthetic/private/'+tool],work,env,{'total_seconds':30})
   return {'version_count':5,'tiny_count':5}
  component=types.SimpleNamespace(load_sources=lambda repo:(None,None,{}),qualify_tools=qualify,host_identities=lambda s:{},environment=lambda q:{},unchanged_tools=lambda *args:None)
  adapter=types.SimpleNamespace(bind=lambda *args:(component,{}))
  args=types.SimpleNamespace(repo=root/'repo',binding_source=root/'binding_source',caller_source=root/'caller_source',binding=root/'binding',profile=root/'profile',binding_bytes=1,binding_sha='a'*64,profile_bytes=1,profile_sha='b'*64)
  scope={'__name__':'mock_parent','__file__':str(ROOT/'qualification_entry.py'),'need':need,'os':os,'fs':fs,'q':q,'dep':dep,'g':g,'b':b,'a':args,'read':lambda *x:None,'PINS':{'SUPPORT_PINS.json':(806,'fixed')},'loaded':lambda *x:supervisor,'expired':lambda *x:None,'stop':time.monotonic()+480,'started':time.monotonic(),'time':time,'Path':Path,'source':root/'source','preset':types.SimpleNamespace(PHASE='local_dependencies_accept_cached'),'ENTRY_BYTES':raw,'write':write,'adapter':adapter,'o':None,'l':None,'braw':b'{}','bpin':{},'praw':b'{}','ppin':{},'s':None,'json':json}
  # Local code uses need(ok) like its pinned entry, so adapt only the test shim.
  scope['need']=lambda ok:need(ok,'entry fixed contract rejection')
  exec(compile(function,'exact_parent_state_machine','exec'),scope)
  if bad:
   rejects(scope['parent_run'],'entry fixed contract rejection');need('RESULT.json' not in saved,'no success on failed actual phase')
  else:
   out=scope['parent_run']();need(out['phases']==13 and len(loaded_phases)==13,'exact thirteen phases')
   need(loaded_phases[:3]==['local_dependencies_accept_cached','local_dependencies_stage_preset','local_dependencies_prepare_private'],'fixed data phase order')
   need(saved['RESULT.json']['backend_build_started'] is False and saved['RESULT.json']['host_started'] is False,'qualification only')
   need(set(saved)>= {'accept_phase.json','stage_phase.json','prepare_phase.json','RESULT.json'},'actual phase evidence coupled')
case();checks.append('exact_parent_thirteen_phase_positive_without_native')
for name in ('local_dependencies_accept_cached','local_dependencies_stage_preset','local_dependencies_prepare_private','host_autoconf-version','host_bison-micro'):
 case(name);checks.append(name+'_failure_stops_without_success')
print(json.dumps({'status':'PASS_FIXED_QUALIFICATION_COORDINATOR_MOCK','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False},sort_keys=True))

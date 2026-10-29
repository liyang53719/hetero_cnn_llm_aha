"""Diagnostic only. No installation, compilation, downloads or hardware acceptance."""
import argparse,hashlib,json,os,pathlib,platform,re,resource,subprocess,time,tempfile
LIMIT=65536
KEYS=('JAVA_VERSION','JAVA_RUNTIME_VERSION','IMPLEMENTOR','OS_ARCH')
def bounded(s):
 if isinstance(s,bytes):s=s.decode('utf-8','replace')
 return (s or '')[:LIMIT]
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30));resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(LIMIT,LIMIT))
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
def probe(java,extra,home):
 env={'PATH':'/usr/bin:/bin','HOME':str(home),'TMPDIR':str(home),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
 cmd=[str(java),*extra,'-XshowSettings:properties','-version'];t=time.monotonic()
 with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
  try:
   p=subprocess.run(cmd,env=env,stdout=stdout,stderr=stderr,timeout=20,preexec_fn=limits)
   result={'native_exit':p.returncode,'timeout':False}
  except subprocess.TimeoutExpired:
   result={'native_exit':None,'timeout':True}
  except OSError as e:
   result={'native_exit':None,'timeout':False,'exception_class':type(e).__name__,'errno':e.errno}
  stdout.seek(0);stderr.seek(0)
  result.update(stdout=bounded(stdout.read(LIMIT)),stderr=bounded(stderr.read(LIMIT)),elapsed_seconds=time.monotonic()-t,per_output_file_limit_bytes=LIMIT)
  return result

def diagnose(out):
 out.mkdir();(out/'probe_home').mkdir();r={'scope':'DIAGNOSTIC_ONLY_NO_QUALIFICATION_NO_EDA','root_cause':'NOT_ESTABLISHED','phase':'environment','image_version':bounded(os.environ.get('ImageVersion')),'image_os':bounded(os.environ.get('ImageOS')),'architecture':platform.machine(),'address_space_bytes':4<<30,'probe_timeout_seconds':20,'environment_note':'Isolated diagnostic HOME and TMPDIR; not byte-identical original bootstrap environment. Java option environment variables omitted.'}
 try:
  home=pathlib.Path(os.environ['JAVA_HOME_21_X64']).resolve(strict=True);r['phase']='release'
  release={}
  for line in (home/'release').read_text().splitlines():
   m=re.fullmatch(r'([A-Z_]+)="([^"\n]*)"',line)
   if m and m[1] in KEYS:release[m[1]]=bounded(m[2])
  r['release']=release;r['phase']='original_plain_probe';r['plain_probe']=probe(home/'bin/java',[],out/'probe_home')
  if r['plain_probe'].get('native_exit')!=0:
   r['phase']='secondary_bounded_heap_probe';r['secondary_flags']=['-Xms16m','-Xmx64m','-XX:MaxMetaspaceSize=64m','-XX:ReservedCodeCacheSize=32m','-XX:ActiveProcessorCount=1'];r['secondary_probe']=probe(home/'bin/java',r['secondary_flags'],out/'probe_home')
  r['phase']='tree_inventory';total=0;files=0;links=0;external=0;t=time.monotonic();r['tree']={'bytes':0,'files':0,'symlinks':0,'external_symlinks':0,'complete':False}
  for p in home.rglob('*'):
   if time.monotonic()-t>60:raise TimeoutError('tree')
   if p.is_symlink():
    links+=1
    if not p.resolve(strict=True).is_relative_to(home):external+=1
   elif p.is_file():
    total+=p.stat().st_size;files+=1
    r['tree'].update(bytes=total,files=files,symlinks=links,external_symlinks=external)
    if total>600_000_000:raise OverflowError('tree')
  r['tree']={'bytes':total,'files':files,'symlinks':links,'external_symlinks':external,'complete':True};r['phase']='diagnostics_complete'
 except Exception as e:
  if r['phase']=='tree_inventory':r['tree'].update(bytes=total,files=files,symlinks=links,external_symlinks=external,complete=False)
  r['exception']={'class':type(e).__name__,'errno':getattr(e,'errno',None)}
 raw=json.dumps(r,indent=2)+'\n'
 if len(raw.encode())>300000:raise ValueError('diagnostic bound')
 (out/'JDK_DIAGNOSTIC.json').write_text(raw)
 # Only return success for diagnostic collection, explicitly NOT JDK qualification.
 return r
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();r=diagnose(a.output);print(json.dumps({'scope':r['scope'],'phase':r['phase'],'root_cause':r['root_cause']}))

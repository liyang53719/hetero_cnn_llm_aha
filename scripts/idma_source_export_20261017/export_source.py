#!/usr/bin/env python3
"""Review candidate: source-only replay of existing export-pinned-idma workflow.
No EDA invocation. No global installation. No branch/push/workflow changes.
"""
import argparse, hashlib, io, json, os, re, signal, subprocess, tarfile, time
from pathlib import Path
import bounded_run,shutil,shlex,stat,sys
PIN='2e0b0fe53b6f8823319e2428e2e9abc2db149b7d'
LOCK_SHA='9e6c33f898dad20fd1b29cf8b07647b7d55fe8b42c36bd5cd72586fc2606557e'
CLOCK_SHA='93e9747504fa1da6473560341febbfae6c5e917768633a84fc9ef12299293207'
DEPS={'apb':'6ae8bf8d5eab5dc70d032231c01ab95e1c5774b9','axi':'0ccc838fe06aeeb857eb83c6be9a915c4bf99566','axi_stream':'ce1547861f99ab3d8834d04aa36d2d4184a28df7','common_cells':'63b7c50d43e462b59506f69d341ff1e40202866d','common_verification':'fb1885f48ea46164a10568aeff51884389f67ae3','obi':'b69af4aa00630efd14b1c5cbf9bac977f23ce840','tech_cells_generic':'3a3de73632a06826b1bd9c65a0a2e92b32016845'}
EXCLUDED_SYMLINKS={p:{'mode':'120000','blob_sha1':'cbe7c334ae570ba7cb8529f09c572e4a8eff81df','target':'../../../jobs','target_sha256':'0622eec76eb89432908d18c9d711c5eb05703e83cc2d77c7f0b90c1c8acd1d9d','reason':'non-RTL simulator jobs convenience link; excluded from zero-symlink source-only export'} for p in ('target/sim/vcs/jobs','target/sim/vsim/jobs')}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def check_lock(path):
 need(sha(path)==LOCK_SHA,'Bender.lock hash drift')
def tool(path,digest):
 p=Path(path);need(p.is_absolute() and p.is_file(),'absolute existing tool required')
 need(re.fullmatch('[0-9a-f]{64}',digest) is not None,'reviewed tool SHA256 required')
 need(sha(p)==digest,'tool hash drift');return p.resolve()
def stages(bender,uv):
 return [(['git','init','idma'],'root'),(['git','-C','idma','remote','add','origin','https://github.com/pulp-platform/iDMA.git'],'root'),(['git','-C','idma','fetch','--depth=1','origin',PIN],'root'),(['git','-C','idma','checkout','--detach','FETCH_HEAD'],'root'),([str(bender),'sources','-f'],'idma'),(['make','BENDER='+str(bender),'UV='+str(uv),'target/rtl/idma_generated.sv','target/rtl/include/idma/compute.svh'],'idma'),([str(bender),'script','verilator','-t','rtl','-t','asic'],'idma')]
def unpack_archive(data,dest,exclusions=None):
 # git archive may include harmless source symlinks. tarfile data filter rejects
 # escaping links, absolute paths and device entries. Output must be fresh.
 dest.mkdir(parents=True,exist_ok=False)
 with tarfile.open(fileobj=io.BytesIO(data)) as t:
  members=t.getmembers();exclusions=exclusions or {};seen=set();kept=[];member_names=set()
  for member in members:
   need(member.name not in member_names,'duplicate archive member');member_names.add(member.name)
   if member.name in exclusions:
    pin=exclusions[member.name]
    need(member.issym() and member.linkname==pin['target'] and hashlib.sha256(member.linkname.encode()).hexdigest()==pin['target_sha256'],'excluded link target drift')
    seen.add(member.name)
   else:
    need(not member.issym() and not member.islnk(),'unexpected source archive link');kept.append(member)
  need(seen==set(exclusions),'missing explicitly excluded source links')
  t.extractall(dest,members=kept,filter='data')
def verify_export(root):
 root=Path(root).resolve();manifest=json.loads((root/'SHA256SUMS.json').read_text());commits=json.loads((root/'COMMITS.json').read_text())
 need(commits=={'idma':PIN,**DEPS},'export commit set drift')
 actual=set()
 for p in root.rglob('*'):
  need(not p.is_symlink(),'export symlink forbidden')
  need(p.is_dir() or stat.S_ISREG(p.stat().st_mode),'nonregular export entry')
  need(p.name!='SHA256SUMS.json' or p==root/'SHA256SUMS.json','nested manifest name forbidden')
  if p.is_file() and p!=root/'SHA256SUMS.json':actual.add(str(p.relative_to(root)))
 need(actual==set(manifest),'extra or missing export files')
 for n,h in manifest.items():
  p=(root/n).resolve();need(p.is_relative_to(root) and p.is_file(),'unsafe/missing export path');need(sha(p)==h,'export hash drift '+n)
 need(sha(root/'deps/tech_cells_generic/src/rtl/tc_clk.sv')==CLOCK_SHA,'ICG drift')
 check_lock(root/'idma/Bender.lock')
 need((root/'idma/target/rtl/idma_generated.sv').is_file(),'missing generated RTL source')
 need((root/'idma/target/rtl/include/idma/compute.svh').is_file(),'missing generated header')
 policy=json.loads((root/'SOURCE_EXPORT_POLICY.json').read_text())
 need(policy=={'schema':1,'excluded_idma_symlinks':EXCLUDED_SYMLINKS},'source exclusion policy drift')
 for path in EXCLUDED_SYMLINKS:need(not os.path.lexists(root/'idma'/path),'excluded link reintroduced')
 need(json.loads((root/'SOURCE_CLOSURE.json').read_text())==check_filelist(root/'idma.f.in',root),'filelist/include closure receipt mismatch')
 return len(manifest)
def check_filelist(path,root):
 root=Path(root).resolve();count=0;sources=[];includes=[]
 for raw in Path(path).read_text().splitlines():
  line=raw.strip()
  if not line or line.startswith('//'):continue
  for word in shlex.split(line):
   if word.startswith('+define+'):continue
   include=word.startswith('+incdir+')
   names=word[len('+incdir+'):].split('+') if include else [word]
   for name in names:
    need(name.startswith('@ROOT@/'),'unapproved filelist token '+name)
    q=(root/name[len('@ROOT@/'):]).resolve()
    need(q.is_relative_to(root),'filelist path escape')
    need(q.is_dir() if include else q.is_file(),'missing filelist source/include '+name);count+=1
    (includes if include else sources).append(q)
 need(count>0,'empty filelist')
 closure_count=verify_include_closure(sources,includes,root)
 return {'source_files':len(set(sources)),'include_directories':len(set(includes)),'source_and_transitive_include_files':closure_count,'excluded_links_unreferenced':True}

def include_literals(text):
 # Preserve strings while blanking comments; never find directives inside strings.
 clean=list(text);i=0;tokens=[];length=len(text)
 while i<length:
  if text.startswith('//',i):
   end=text.find('\n',i);end=length if end<0 else end
   for j in range(i,end):clean[j]=' '
   i=end;continue
  if text.startswith('/*',i):
   end=text.find('*/',i+2);need(end>=0,'unterminated block comment');end+=2
   for j in range(i,end):
    if clean[j]!='\n':clean[j]=' '
   i=end;continue
  if text[i]=='"':
   i+=1
   while i<length:
    if text[i]=='\\':i+=2;continue
    if text[i]=='"':i+=1;break
    i+=1
   continue
  if text.startswith('`include',i) and (i+8==length or not(text[i+8].isalnum() or text[i+8]=='_')):tokens.append(i)
  i+=1
 clean=''.join(clean);result=[]
 for pos in tokens:
  start=clean.rfind('\n',0,pos)+1;end=clean.find('\n',pos);end=length if end<0 else end
  line=clean[start:end]
  literal=re.fullmatch(r'\s*`include\s+"([^"\n\\]+)"\s*',line)
  need(literal is not None,'unsupported inline/macro/continued include')
  result.append(literal[1])
 return result

def merge_generated(source,dest,root):
 need(source.resolve().is_relative_to(root.resolve()) and dest.resolve().is_relative_to(root.resolve()),'generated merge path escapes output')
 for p in source.rglob('*'):
  need(not p.is_symlink() and (p.is_dir() or p.is_file()),'generated source link/nonregular')
  q=dest/p.relative_to(source)
  if q.exists():
   need(not q.is_symlink(),'generated merge destination symlink')
   need((p.is_dir() and q.is_dir()) or (p.is_file() and q.is_file() and sha(p)==sha(q)),'generated merge conflict')
 shutil.copytree(source,dest,dirs_exist_ok=True)

def verify_include_closure(sources,include_dirs,root):
 queue=list(sources);seen=set()
 excluded={root/'idma'/p for p in EXCLUDED_SYMLINKS}
 while queue:
  p=queue.pop()
  if p in seen:continue
  need(len(seen)<100000,'include closure entry cap');seen.add(p)
  need(p.is_relative_to(root) and p not in excluded and p.is_file() and not p.is_symlink(),'invalid include/source closure path')
  for rel in include_literals(p.read_text()):
   need(not Path(rel).is_absolute(),'absolute include forbidden')
   candidates=[(base/rel).resolve() for base in [p.parent,*include_dirs]]
   resolved=next((q for q in candidates if q.is_file()),None)
   need(resolved is not None and resolved.is_relative_to(root) and resolved not in excluded,'unresolved/escaped include '+rel)
   queue.append(resolved)
 return len(seen)

def remove_temporary(root,stop):
 # Only self-created fixed children. No removal if process absence was unverified.
 deleted=[]
 for name in ['idma','idma_export','uv-cache','home','tmp']:
  need(time.monotonic()<stop,'failure file cleanup deadline')
  p=root/name
  if p.exists():
   need(not p.is_symlink() and p.resolve().is_relative_to(root.resolve()),'unsafe failure cleanup')
   shutil.rmtree(p);deleted.append(name)
 return deleted
def run_inner(a,stop):
 need(a.execute,'--execute required after independent review')
 out=Path(a.out);need(out.is_absolute() and not out.exists() and not out.is_symlink(),'fresh absolute output required')
 bender=tool(a.bender,a.bender_sha256);uv=tool(a.uv,a.uv_sha256)
 out.mkdir();work_stop=stop-30
 interpreter=Path(sys.executable).resolve();interpreter_sha=sha(interpreter)
 receipt={'status':'IN_PROGRESS','scope':'SOURCE_EXPORT_ONLY','eda_executed':False,'idma_pin':PIN,'deadline_monotonic':stop,'python_sha256':interpreter_sha,'python_version':sys.version.split()[0],'bender_sha256':sha(bender),'uv_sha256':sha(uv),'stages':[]}
 for n in ['home','tmp']:(out/n).mkdir()
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8','TZ':'UTC','HOME':str(out/'home'),'TMPDIR':str(out/'tmp'),'UV_CACHE_DIR':str(out/'uv-cache'),'BENDER':str(bender),'UV':str(uv),'MAKEFLAGS':'-j1','GIT_TERMINAL_PROMPT':'0','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_SYSTEM':'/dev/null','PYTHONNOUSERSITE':'1','UV_NO_PROGRESS':'1','UV_PYTHON':str(interpreter),'UV_PYTHON_DOWNLOADS':'never'}
 clean=True
 def alarm(sig,frame):raise TimeoutError('original source-export wall deadline')
 old_alarm=signal.signal(signal.SIGALRM,alarm)
 def arm():
  need(time.monotonic()<work_stop,'source-export work deadline');signal.setitimer(signal.ITIMER_REAL,work_stop-time.monotonic())
 def save(): (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 def cmd(argv,cwd):
  nonlocal clean
  signal.setitimer(signal.ITIMER_REAL,0)
  remaining=work_stop-time.monotonic();need(remaining>10,'source-export total deadline')
  argv=list(argv);argv[0]=str(Path(argv[0]).resolve()) if '/' in argv[0] else shutil.which(argv[0],path=env['PATH'])
  need(argv[0] is not None,'missing system command')
  index=len(receipt['stages']);output=out/f'{index:02d}.stdout.log';error=out/f'{index:02d}.stderr.log'
  clean=False
  result=bounded_run.execute(argv,cwd=cwd,env=env,out=output,err=error,root=out,absolute_stop=work_stop,stage_stop=min(time.monotonic()+180,work_stop-10),stdout_limit=64*1024*1024 if argv[1:2]==['archive'] else 2*1024*1024)
  clean=result['cleanup_complete'];arm();receipt['stages'].append(result);save()
  need(clean and result['error'] is None and result['exit']==0,'source stage failed')
  return output.read_bytes()

 try:
  arm();save();need(cmd([str(bender),'--version'],out).decode().strip()=='bender 0.32.0','Bender version drift')
  need(re.match(r'^uv 0\.8\.17(?:\s|$)',cmd([str(uv),'--version'],out).decode()) is not None,'uv version drift')
  recipe=stages(bender,uv)
  for argv,_ in recipe[:4]:cmd(argv,out)
  src=out/'idma';need(cmd(['git','rev-parse','HEAD'],src).decode().strip()==PIN,'iDMA commit drift');check_lock(src/'Bender.lock')
  (out/'all_sources.txt').write_bytes(cmd(recipe[4][0],src));check_lock(src/'Bender.lock')
  # Verify all resolved repositories before invoking the pinned source generator.
  roots={'idma':src}
  for name,rev in DEPS.items():
   p=Path(cmd([str(bender),'path',name],src).decode().strip()).resolve()
   need(p.is_relative_to(out.resolve()),'dependency path escapes isolated export root')
   need(cmd(['git','rev-parse','HEAD'],p).decode().strip()==rev,'dependency revision drift '+name)
   need(not cmd(['git','status','--porcelain'],p).strip(),'dirty dependency '+name);roots[name]=p
  (src/'target/rtl').mkdir(parents=True,exist_ok=True)  # Original workflow required this before shell redirections.
  cmd(recipe[5][0],src);filelist=cmd(recipe[6][0],src).decode();check_lock(src/'Bender.lock')
  need(not cmd(['git','status','--porcelain'],src).strip(),'dirty upstream tracked/unignored files')
  export=out/'idma_export';export.mkdir()
  # Revalidate every source and helper after generation, immediately before archive.
  need(sha(bender)==a.bender_sha256 and sha(uv)==a.uv_sha256,'postflight tool drift')
  for name,p in roots.items():
   need(cmd(['git','rev-parse','HEAD'],p).decode().strip()==({'idma':PIN,**DEPS}[name]),'postflight dependency drift')
   need(not cmd(['git','status','--porcelain'],p).strip(),'postflight dirty source')
  for name,p in roots.items():
   target=export/('idma' if name=='idma' else 'deps/'+name)
   archive=cmd(['git','archive','HEAD'],p)
   with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
    need(bounded_run.tree_bytes(out)+sum(m.size for m in tf.getmembers())<=bounded_run.TREE_LIMIT,'archive expansion tree budget')
   if name=='idma':
    rows=cmd(['git','ls-tree','-r','HEAD','--',*EXCLUDED_SYMLINKS],p).decode().splitlines()
    actual={}
    for row in rows:
     info,path=row.split('\t',1);mode,kind,blob=info.split();actual[path]=(mode,kind,blob)
    need(actual=={k:(v['mode'],'blob',v['blob_sha1']) for k,v in EXCLUDED_SYMLINKS.items()},'excluded upstream git identity drift')
   unpack_archive(archive,target,EXCLUDED_SYMLINKS if name=='idma' else None)
  need(bounded_run.tree_bytes(out)+bounded_run.tree_bytes(src/'target/rtl')<=bounded_run.TREE_LIMIT,'generated source copy tree budget')
  merge_generated(src/'target/rtl',export/'idma/target/rtl',out)
  for name,p in sorted(roots.items(),key=lambda x:-len(str(x[1]))):filelist=filelist.replace(str(p),'@ROOT@/'+('idma' if name=='idma' else 'deps/'+name))
  need(str(out) not in filelist,'unrelocated build path')
  (export/'idma.f.in').write_text(filelist)
  (export/'SOURCE_EXPORT_POLICY.json').write_text(json.dumps({'schema':1,'excluded_idma_symlinks':EXCLUDED_SYMLINKS},indent=2)+'\n')
  (export/'SOURCE_CLOSURE.json').write_text(json.dumps(check_filelist(export/'idma.f.in',export.resolve()),indent=2)+'\n')
  (export/'COMMITS.json').write_text(json.dumps({'idma':PIN,**DEPS},indent=2)+'\n')
  manifest={str(p.relative_to(export)):sha(p) for p in export.rglob('*') if p.is_file()}
  (export/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
  need(sha(bender)==a.bender_sha256 and sha(uv)==a.uv_sha256 and sha(interpreter)==interpreter_sha,'final tool/interpreter drift')
  need(bounded_run.tree_bytes(out)<=bounded_run.TREE_LIMIT,'final aggregate tree sampled limit')
  receipt.update(status='PASS_SOURCE_EXPORT_ONLY',files_verified=verify_export(export),manifest_sha256=sha(export/'SHA256SUMS.json'))
 except BaseException as e:
  receipt.update(status='FAILED',error=repr(e));signal.setitimer(signal.ITIMER_REAL,0)
  if hasattr(e,'evidence'):receipt['cleanup_failure_evidence']=e.evidence
  try:
   if clean:
    signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()));receipt['failure_deleted']=remove_temporary(out,stop)
   else:receipt['failure_cleanup_blocked']='process absence unverified; preserve filesystem'
  except BaseException as cleanup_error:receipt['failure_file_cleanup_error']=repr(cleanup_error)
  raise
 finally:
  signal.signal(signal.SIGALRM,old_alarm)
  need(time.monotonic()<stop,'final receipt deadline')
  signal.setitimer(signal.ITIMER_REAL,stop-time.monotonic());save()
def run(a):
 # Includes initial tool hashes, source work, and final receipt; the same deadline
 # is retained privately for the separate final verification step.
 stop=time.monotonic()+900
 if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise ValueError('existing source alarm')
 def expired(sig,frame):raise TimeoutError('source export total deadline')
 previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,900)
 try:return run_inner(a,stop)
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['out','bender','uv','bender-sha256','uv-sha256']:p.add_argument('--'+n,required=True)
 p.add_argument('--execute',action='store_true');run(p.parse_args())

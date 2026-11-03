"""Pin official runner host compiler/JDK/headers; no source compilation or install."""
import pathlib,hashlib,json,subprocess,re,sys,os
P=pathlib.Path;out=P(sys.argv[1]);root=out.parent;java=P(os.environ['JAVA_HOME_21_X64'])/'bin/java';cxx=P('/usr/bin/g++-14');pins={};aliases=[]
def query(args):return subprocess.check_output(list(map(str,args)),text=True,stderr=subprocess.STDOUT,timeout=10).strip()
def add(p):
 p=P(p);q=p.resolve(strict=True)
 with q.open('rb')as f:pins[str(q)]=hashlib.file_digest(f,'sha256').hexdigest()
 if p!=q:aliases.append({'requested':str(p),'resolved':str(q)})
 return q
assert query([cxx,'-dumpfullversion'])=='14.2.0'
jv=query([java,'-Xmx32m','-version']);assert re.search(r'version "21[.\"]',jv),jv
bins=[cxx,java,root/'acquire/firtool',P('/workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/bin/verilator_bin'),P('/usr/bin/python3'),P('/usr/bin/readelf'),P('/usr/bin/nm'),P('/usr/bin/dpkg-deb'),P('/usr/bin/as'),P('/usr/bin/ld')]
for name in ['cc1plus','collect2']:bins.append(P(query([cxx,'-print-prog-name='+name])))
queue=[add(p)for p in bins]
for name in ['crtbeginS.o','crtendS.o','libgcc.a','libgcc_s.so','libstdc++.so','libatomic.so','liblto_plugin.so']:
 p=query([cxx,'-print-file-name='+name]);assert p!=name;queue.append(add(p))
for name in ['Scrt1.o','crti.o','crtn.o','libm.so','libc.so','libpthread.a','libc_nonshared.a','libmvec.so.1','libgcc_s.so.1']:queue.append(add(P('/usr/lib/x86_64-linux-gnu')/name))
for p in [java.parent.parent/'lib/server/libjvm.so',java.parent.parent/'lib/libjli.so',P('/lib64/ld-linux-x86-64.so.2')]:queue.append(add(p))
jdk=java.resolve().parent.parent
add(jdk/'release')
for p in (jdk/'lib').rglob('*'):
 if p.is_file():
  add(p)
  if p.suffix=='.so':queue.append(p.resolve())
seen=set();needed={};search_paths={};interpreters={}
while queue:
 p=queue.pop()
 if p in seen:continue
 seen.add(p)
 with p.open('rb')as f:magic=f.read(4)
 if magic!=b'\x7fELF':continue
 dynamic=query(['/usr/bin/readelf','-d',p]);names=re.findall(r'\(NEEDED\).*?\[([^]]+)\]',dynamic);needed[str(p)]=names
 runs=re.findall(r'\((?:RPATH|RUNPATH)\).*?\[([^]]+)\]',dynamic);search_paths[str(p)]=runs
 expanded=[]
 for run in runs:
  for component in run.split(':'):
   path=component.replace('${ORIGIN}',str(p.parent)).replace('$ORIGIN',str(p.parent));assert '$'not in path and P(path).is_absolute();expanded.append(P(path))
 ph=query(['/usr/bin/readelf','-l',p]);interps=re.findall(r'Requesting program interpreter: ([^\]]+)\]',ph)
 for name in interps:queue.append(add(name))
 interpreters[str(p)]=interps
 for n in names:
  q=next((d/n for d in [*expanded,p.parent,jdk/'lib',jdk/'lib/server',P('/lib/x86_64-linux-gnu'),P('/usr/lib/x86_64-linux-gnu')]if(d/n).is_file()),None);assert q,n;queue.append(add(q))
add('/etc/ld.so.cache')
roots=['/usr/include/c++/14','/usr/include/x86_64-linux-gnu/c++/14',query([cxx,'-print-file-name=include']),'/usr/include/x86_64-linux-gnu/bits','/usr/include/x86_64-linux-gnu/sys','/usr/include/x86_64-linux-gnu/gnu','/usr/include/x86_64-linux-gnu/asm','/usr/include/asm-generic','/usr/include/linux']
headers=set(P('/usr/include').glob('*.h'))|set(P('/usr/include/x86_64-linux-gnu').glob('*.h'))
for d in roots:headers.update(p for p in P(d).rglob('*')if p.is_file())
assert len(headers)<=10000 and sum(p.stat().st_size for p in headers)<128<<20
for p in sorted(headers):add(p)
out.write_text(json.dumps({'pins':pins,'aliases':aliases,'DT_NEEDED':needed,'RUNPATH_RPATH':search_paths,'PT_INTERP':interpreters,'JDK_runtime_root':str(jdk),'JDK_lib_tree_and_release_pinned':True,'java':str(java.resolve()),'cxx':str(cxx.resolve()),'java_version':jv,'gcc_version':'14.2.0','ImageOS':os.getenv('ImageOS'),'ImageVersion':os.getenv('ImageVersion'),'headers':len(headers),'scope':'New official GitHub runner toolchain; not local Debian byte identity'},indent=2)+'\n')

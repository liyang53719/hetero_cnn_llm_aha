"""Installed GNU tool identity inventory; no compile/link or package installation.
Future invocation runs only version/path/package queries and bounded file hashing.
"""
import argparse,subprocess,shutil,pathlib,json,os,re,time,hashlib
P=pathlib.Path

def need(x,m):
 if not x:raise ValueError(m)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def query(argv):
 r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
 need(r.returncode==0 and len(r.stdout)+len(r.stderr)<131072,'tool inventory query failed')
 return r.stdout.decode().strip()
def inventory():
 start=time.monotonic();tools={k:str(P(shutil.which(v,path='/usr/bin:/bin') or '/MISSING').resolve(strict=True)) for k,v in dict(cxx='g++',ar='ar',ranlib='ranlib',perl='perl',python='python3',make='make').items()}
 version=query([tools['cxx'],'-dumpfullversion']);major=version.split('.')[0]
 need(major in ('13','14'),'reviewed GNU C++ major 13/14 only; other compiler requires review')
 need(query([tools['cxx'],'-dumpmachine'])=='x86_64-linux-gnu','unsupported compiler target')
 versions={k:query([p,'--version']) for k,p in tools.items()}
 need('GNU Make 4.' in versions['make'] and 'GNU ar' in versions['ar'],'GNU tools required')
 pins={};aliases={};total=0
 def add(p):
  nonlocal total
  p=P(p);r=p.resolve(strict=True);need(r.is_file(),'tool/header regular file')
  if p!=r:aliases[str(p)]=str(r)
  if str(r) in pins:return
  total+=r.stat().st_size;need(total<3*1024**3 and len(pins)<100000 and time.monotonic()-start<240,'inventory bounded cap')
  pins[str(r)]=sha(r)
 for p in tools.values():add(p)
 for n in ('cc1plus','as','ld','collect2'):
  value=query([tools['cxx'],'-print-prog-name='+n]);p=P(value)
  if not p.is_absolute():p=P(shutil.which(value,path='/usr/bin:/bin') or '/MISSING')
  add(p);tools[n]=str(p.resolve())
 for n in ('libstdc++.so','libgcc_s.so','libgcc.a','libgcc_eh.a','libatomic.so','crtbeginS.o','crtendS.o'):
  p=query([tools['cxx'],'-print-file-name='+n]);need(p!=n,'missing compiler runtime '+n);add(p)
 roots=[P('/usr/include'),P('/usr/lib/gcc/x86_64-linux-gnu')/major/'include',P('/usr/include/c++')/major]
 for root in roots:
  need(root.is_dir(),'missing system headers')
  visited=set()
  for parent,dirs,files in os.walk(root,followlinks=True):
   real=P(parent).resolve(strict=True)
   if P(parent)!=real:aliases[str(P(parent))]=str(real)
   if str(real) in visited:dirs[:]=[];continue
   visited.add(str(real))
   for n in files:add(P(parent)/n)
 # Link-input/runtime closure used by this fixed Linux GNU/libcrypto build.
 for pattern in ('libcrypto.so*','libc.so*','libm.so*','libpthread.so*','libpthread.a','libdl.so*','libdl.a','librt.so*','librt.a','libmvec.so*','libatomic.so*','libstdc++.so*','libgcc_s.so*','ld-linux-x86-64.so*','crt1.o','Scrt1.o','crti.o','crtn.o','libc_nonshared.a'):
  hits=list(P('/usr/lib/x86_64-linux-gnu').glob(pattern));need(hits,'missing link dependency '+pattern)
  for p in hits:add(p)
 # Dynamic loader closure of admitted system tool binaries; ldd only on these
 # trusted distro tools, never on an untrusted produced binary.
 dynamic={}
 for name,p in tools.items():
  text=query(['/usr/bin/ldd',p]);dynamic[name]=text
  for match in re.findall(r'(?:=>\s*)?(/[^\s]+)\s+\(',text):add(match)
 packages=query(['/usr/bin/dpkg-query','-W','-f=${Package}\t${Version}\n','g++-'+major,'gcc-'+major,'binutils','libc6-dev','libssl-dev','make','perl','python3'])
 return dict(schema='INSTALLED_GNU_BUILD_TOOLS_V1',qualification='IDENTITY_AND_SUPPORTED_OPTIONS_ONLY_NOT_COMPILE_OR_NUMERICAL_PASS',compile_tools=tools,pins=pins,aliases=aliases,versions=versions,dynamic_dependencies=dynamic,package_versions=packages,header_roots=list(map(str,roots)),hashed_bytes=total,elapsed_seconds=time.monotonic()-start)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=P,required=True);a=ap.parse_args();need(not a.output.exists(),'new output only');a.output.write_text(json.dumps(inventory(),indent=2)+'\n')

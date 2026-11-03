"""Only immutable official Maven/Debian tool bytes, no model/data acquisition."""
import hashlib,json,pathlib,sys,urllib.request,zipfile,subprocess
P=pathlib.Path;cfg=P(sys.argv[1]);root=P(sys.argv[2]);repo=P(sys.argv[3]);d=json.loads(cfg.read_text());cache=root/'cache';cache.mkdir()
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**k):raise ValueError('redirect not admitted')
def get(url,p,size,h):
 assert url.startswith(('https://repo.maven.apache.org/maven2/','https://deb.debian.org/debian/'))
 with urllib.request.build_opener(NoRedirect()).open(url,timeout=30)as r,p.open('xb')as f:
  n=0
  while True:
   b=r.read(1<<20)
   if not b:break
   n+=len(b);assert n<=size;f.write(b)
 assert n==size and sha(p)==h
seen=set()
for x in d['classpath']+[d['plugin']]:
 if x['sha256']in seen:continue
 seen.add(x['sha256']);get(x['url'],cache/(x['sha256']+'.jar'),x['bytes'],x['sha256'])
f=d['firtool_archive'];jar=root/'firtool.jar';get(f['origin_url'],jar,f['size_bytes'],f['sha256']);binary=root/'firtool'
with zipfile.ZipFile(jar)as z,z.open(d['firtool_member'])as src,binary.open('xb')as dst:
 n=0
 while True:
  b=src.read(1<<20)
  if not b:break
  n+=len(b);assert n<=d['firtool_binary_bytes'];dst.write(b)
assert n==d['firtool_binary_bytes']and sha(binary)==d['firtool_binary_sha256'];binary.chmod(0o500)
v=P('/workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools');v.mkdir(parents=True);deb=v/'verilator.deb';get(d['verilator_url'],deb,d['verilator_package_bytes'],d['verilator_package_sha256']);package=v/'verilator-package';subprocess.run(['/usr/bin/dpkg-deb','--extract',str(deb),str(package)],check=True,timeout=30)
m=json.loads((repo/d['verilator_manifest_repo_path']).read_text())
for r in m['files']:
 if r['path'].startswith(('usr/bin/','usr/share/verilator/')):
  p=package/r['path'];assert p.is_file()and p.stat().st_size==r['bytes']and sha(p)==r['sha256']
print('OFFICIAL_TOOL_BYTES_VERIFIED',len(seen),'unique jars; no compiler or model run')

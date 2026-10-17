"""Static extraction only; never executes archive contents."""
import argparse,hashlib,io,json,os,tarfile,zipfile
from pathlib import Path,PurePosixPath
SHA={'verilator_5.032-1+b2_amd64.deb':'238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2','llvm-firtool-1.62.1-linux-x64.jar':'63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(archives,out):
 if out.exists():raise ValueError('fresh tools directory required')
 for n,h in SHA.items():
  if sha(archives/n)!=h:raise ValueError('archive drift')
 out.mkdir();b=(archives/'verilator_5.032-1+b2_amd64.deb').read_bytes();i=8
 if b[:8]!=b'!<arch>\n':raise ValueError('ar magic')
 while i<len(b):
  h=b[i:i+60];n=h[:16].decode().strip().rstrip('/');s=int(h[48:58]);d=b[i+60:i+60+s];i+=60+s+s%2
  if n=='data.tar.xz':
   t=tarfile.open(fileobj=io.BytesIO(d));total=0
   for m in t:
    rel=PurePosixPath(m.name)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe member')
    p=out/rel
    if m.isdir():p.mkdir(parents=True,exist_ok=True)
    elif m.isfile():
     total+=m.size
     if total>64*1024**2:raise ValueError('extraction cap')
     p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read());p.chmod(0o700 if m.mode&0o111 else 0o600)
    elif m.issym():
     target=PurePosixPath(m.linkname)
     # Require normalized target to remain inside the extraction root.
     resolved=(p.parent/str(target)).resolve()
     if target.is_absolute() or not resolved.is_relative_to(out.resolve()):raise ValueError('unsafe symlink')
     p.parent.mkdir(parents=True,exist_ok=True);p.symlink_to(m.linkname)
    else:raise ValueError('unsupported tar member')
 with zipfile.ZipFile(archives/'llvm-firtool-1.62.1-linux-x64.jar') as z:
  p=out/'firtool';p.write_bytes(z.read('org.chipsalliance/llvm-firtool/linux-x64/bin/firtool'));p.chmod(0o700)
 files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
 system={n:sha(Path(n)) for n in ['/usr/bin/make','/usr/bin/perl','/usr/bin/x86_64-linux-gnu-g++-14','/usr/bin/x86_64-linux-gnu-gcc-14']}
 return dict(archives=SHA,files=files,system=system,executed=False)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--archives',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--pins',type=Path,required=True);a=p.parse_args()
 a.pins.write_text(json.dumps(prepare(a.archives,a.out),indent=2)+'\n')

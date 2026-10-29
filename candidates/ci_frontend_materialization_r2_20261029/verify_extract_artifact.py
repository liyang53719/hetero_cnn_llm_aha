"""Exact known Actions artifact, local verification/extraction only; no network/run."""
from pathlib import Path,PurePosixPath
import argparse,zipfile,stat,hashlib,json
SIZE=9926876
DIGEST='a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'
MANIFEST='a699b8074b8099e00859d5174c0a5fb6b5a171a28cad30bab8dd96226dc67b19'
def need(ok,msg):
 if not ok:raise ValueError(msg)
def run(archive,out):
 need(archive.is_file() and not archive.is_symlink(),'regular archive');need(archive.stat().st_size==SIZE,'size')
 need(hashlib.sha256(archive.read_bytes()).hexdigest()==DIGEST,'archive sha');need(not out.exists() and not out.is_symlink(),'fresh destination')
 for parent in out.parents:need(not parent.is_symlink(),'destination parent link')
 z=zipfile.ZipFile(archive);seen=set();total=0
 for i in z.infolist():
  p=PurePosixPath(i.filename);mode=i.external_attr>>16
  need(not p.is_absolute() and '..' not in p.parts and str(p)==i.filename and i.filename not in seen,'member path')
  need(not stat.S_ISLNK(mode) and stat.S_IFMT(mode) in (0,stat.S_IFREG,stat.S_IFDIR),'member type')
  seen.add(i.filename);total+=i.file_size;need(total<=40*1024*1024,'expansion cap')
 need(len(seen)==929 and total==33777372,'exact archive inventory')
 out.mkdir()
 for i in z.infolist():
  p=out/i.filename;p.parent.mkdir(parents=True,exist_ok=True)
  if i.is_dir():p.mkdir(exist_ok=True)
  else:p.write_bytes(z.read(i))
 root=out/'idma_export';raw=(root/'SHA256SUMS.json').read_bytes();need(hashlib.sha256(raw).hexdigest()==MANIFEST,'manifest sha');m=json.loads(raw)
 actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p!=root/'SHA256SUMS.json'};need(actual==set(m) and len(m)==927,'manifest exact set')
 for n,h in m.items():need(hashlib.sha256((root/n).read_bytes()).hexdigest()==h,'member sha '+n)
 return {'artifact_id':12099239717,'archive_sha256':DIGEST,'manifest_sha256':MANIFEST,'manifest_members_verified':927,'status':'VERIFIED_SOURCE_BYTES_ONLY'}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('archive',type=Path);a.add_argument('out',type=Path);v=a.parse_args();print(json.dumps(run(v.archive,v.out),indent=2))

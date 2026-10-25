"""Restore one hash-locked official Debian package, never install or execute its contents."""
import hashlib,io,json,os,posixpath,tarfile,time,urllib.request
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
URL='https://deb.debian.org/debian/pool/main/v/verilator/verilator_5.032-1+b2_amd64.deb'
SIZE=7565144
SHA='238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2'

def need(ok,why):
 if not ok:raise ValueError(why)
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def save(name,value):
 with (ROOT/name).open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def members_ar(raw):
 need(raw.startswith(b'!<arch>\n'),'ar magic');out={};off=8
 while off<len(raw):
  head=raw[off:off+60];need(len(head)==60 and head[58:]==b'`\n','ar header')
  name=head[:16].decode('ascii').strip().rstrip('/');n=int(head[48:58]);off+=60
  need(name not in out and 0<=n<=SIZE and off+n<=len(raw),'ar size/unique name')
  out[name]=raw[off:off+n];off+=n+(n%2)
 need(off==len(raw),'ar trailing');return out

def unpack(blob,destination):
 destination.mkdir(mode=0o700)
 records=[]
 with tarfile.open(fileobj=io.BytesIO(blob),mode='r:*') as tf:
  entries=tf.getmembers();need(len(entries)<=4096,'tar member count');seen=set();total=0
  for m in entries:
   name=m.name.removeprefix('./').rstrip('/')
   if not name:need(m.isdir(),'root is directory');continue
   path=PurePosixPath(name);need(not path.is_absolute() and '..' not in path.parts and str(path)==name and name not in seen,'safe unique tar path');seen.add(name)
   need(m.isdir() or m.isfile() or m.issym() or m.islnk(),'no special archive members')
   need(0<=m.size<=64*1024**2,'member bound');total+=m.size;need(total<=128*1024**2,'expanded byte bound')
   records.append(dict(path=name,type=('directory' if m.isdir() else 'file' if m.isfile() else 'symlink' if m.issym() else 'hardlink'),bytes=m.size,mode=oct(m.mode),linkname=m.linkname))
  # Never use tarfile.extract; no extraction through any archive-created symlink.
  dirs=sorted((r for r in records if r['type']=='directory'),key=lambda r:len(PurePosixPath(r['path']).parts))
  for r in dirs:(destination/r['path']).mkdir(parents=True,exist_ok=True)
  for m in entries:
   name=m.name.removeprefix('./').rstrip('/')
   if not name or not m.isfile():continue
   target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
   with tf.extractfile(m) as src,target.open('xb') as out:
    h=hashlib.sha256();n=0
    for block in iter(lambda:src.read(1048576),b''):out.write(block);h.update(block);n+=len(block)
   need(n==m.size,'member exact bytes');target.chmod(m.mode&0o777)
   next(r for r in records if r['path']==name)['sha256']=h.hexdigest()
  for r in records:
   if r['type'] not in ('symlink','hardlink'):continue
   target=destination/r['path'];target.parent.mkdir(parents=True,exist_ok=True);link=r['linkname']
   need(not PurePosixPath(link).is_absolute(),'no absolute archive links')
   normalized=posixpath.normpath(posixpath.join(posixpath.dirname(r['path']),link) if r['type']=='symlink' else link.removeprefix('./'))
   need(normalized!='..' and not normalized.startswith('../'),'archive link stays in extracted tree')
   need(normalized in seen or (r['type']=='symlink' and r['path'].startswith('usr/share/doc/verilator/')),'only documentation symlinks may target unprovided package members')
   r['target_member_present']=normalized in seen;r['normalized_private_target']=normalized
   if r['type']=='symlink':target.symlink_to(link)
   else:os.link(destination/normalized,target)
  for r in reversed(dirs):(destination/r['path']).chmod(int(r['mode'],8)&0o777)
 return records

def main():
 started=time.monotonic();package=ROOT/'verilator_5.032-1+b2_amd64.deb'
 report=dict(schema='official-debian-verilator-extraction-recovery-v1',no_download=True,prior_failure_retained='RESTORE_RECEIPT.json',execution=False,system_install=False)
 try:
  need(package.stat().st_size==SIZE and digest(package)==SHA,'exact previously downloaded package')
  ar=members_ar(package.read_bytes());need(set(ar)=={'debian-binary','control.tar.xz','data.tar.xz'} and ar['debian-binary']==b'2.0\n','exact archive layout')
  files=unpack(ar['data.tar.xz'],ROOT/'extracted_r2')
  report.update(status='PASS_OFFICIAL_PACKAGE_STDLIB_EXTRACTION_NO_EXECUTION',package_bytes=SIZE,package_sha256=SHA,extraction_root=str(ROOT/'extracted_r2'),regular_count=sum(r['type']=='file' for r in files),regular_bytes=sum(r['bytes'] for r in files if r['type']=='file'),absent_documentation_link_targets=[r for r in files if r.get('target_member_present') is False])
  save('PACKAGE_FILES.json',dict(schema='exact-debian-data-member-manifest-v1',root=str(ROOT/'extracted_r2'),package_sha256=SHA,members=files))
 except BaseException as e:
  report.update(status='FAIL_EXTRACTION_RECOVERY_RETAINED',error=repr(e));raise
 finally:
  report['elapsed_seconds']=time.monotonic()-started;save('EXTRACTION_RECEIPT.json',report)
  print(json.dumps({k:v for k,v in report.items() if k!='absent_documentation_link_targets'},indent=2))

if __name__=='__main__':main()

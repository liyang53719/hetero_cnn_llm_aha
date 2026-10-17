#!/usr/bin/env python3
"""Pinned helper bootstrap. Extract only Verilator binary, never install a deb.
No tool is executed here. All decompression and writes share the 180 s deadline.
"""
import argparse, hashlib, io, json, tarfile, urllib.request, signal, lzma, zlib
from pathlib import Path, PurePosixPath
ASSETS={
'bender':('https://github.com/pulp-platform/bender/releases/download/v0.32.0/bender-x86_64-unknown-linux-gnu.tar.xz','05c2c9c82ddc0b3f45141a1e30dbcfba3b9a98a7d2ad0f9003651c0655c7a2fe'),
'uv':('https://github.com/astral-sh/uv/releases/download/0.8.17/uv-x86_64-unknown-linux-gnu.tar.gz','920cbcaad514cc185634f6f0dcd71df5e8f4ee4456d440a22e0f8c0f142a8203'),
'verilator':('https://deb.debian.org/debian/pool/main/v/verilator/verilator_5.032-1+b2_amd64.deb','238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2')}
VERILATOR_SHA='619464a17a8c212219abceeeee23f529b72801ef594814ae32f4b9747fd38703'
DOWNLOAD_LIMIT=64*1024*1024
EXPANDED_LIMIT=128*1024*1024
MEMBER_LIMIT=64*1024*1024

def need(ok, message):
 if not ok:raise ValueError(message)

def unpack_compression(data):
 """Bound output allocation before tarfile sees bytes; reject trailing streams."""
 need(len(data)<=DOWNLOAD_LIMIT,'compressed archive cap')
 if data.startswith(b'\xfd7zXZ\x00'):
  decoder=lzma.LZMADecompressor(format=lzma.FORMAT_XZ,memlimit=EXPANDED_LIMIT)
  raw=decoder.decompress(data,max_length=EXPANDED_LIMIT+1)
 elif data.startswith(b'\x1f\x8b'):
  decoder=zlib.decompressobj(31)
  raw=decoder.decompress(data,EXPANDED_LIMIT+1)
 else:raise ValueError('unsupported archive compression')
 need(len(raw)<=EXPANDED_LIMIT,'expanded archive cap')
 need(decoder.eof and not decoder.unused_data,'incomplete or trailing compressed stream')
 return raw

def ar_data(data):
 need(len(data)<=DOWNLOAD_LIMIT and data[:8]==b'!<arch>\n','invalid deb ar header')
 offset=8;members={}
 while offset<len(data):
  need(len(members)<16 and offset+60<=len(data),'ar member/header cap')
  header=data[offset:offset+60];need(header[58:60]==b'`\n','invalid ar header')
  name=header[:16].decode('ascii').strip().removesuffix('/')
  need(name in ('debian-binary','control.tar.xz','data.tar.xz') and name not in members,'unexpected/duplicate ar member')
  size_text=header[48:58].strip();need(size_text.isdigit(),'invalid ar size')
  size=int(size_text);start=offset+60;end=start+size
  need(size<=DOWNLOAD_LIMIT and end<=len(data),'ar size cap')
  members[name]=data[start:end]
  if size%2:need(end<len(data) and data[end:end+1]==b'\n','invalid ar padding')
  offset=end+size%2
 need(set(members)=={'debian-binary','control.tar.xz','data.tar.xz'} and members['debian-binary']==b'2.0\n','unsupported deb layout')
 return members['data.tar.xz']

def normalized(name):
 need(isinstance(name,str) and '\\' not in name and '\x00' not in name,'invalid tar path')
 p=PurePosixPath(name)
 need(not p.is_absolute() and '..' not in p.parts,'unsafe tar path')
 return p.as_posix()

def tar_members(raw, allow_unmaterialized_links=False):
 need(len(raw)<=EXPANDED_LIMIT,'tar byte cap')
 stream=tarfile.open(fileobj=io.BytesIO(raw),mode='r:')
 members={};total=0
 try:
  for member in stream:
   name=normalized(member.name)
   need(len(members)<1000 and name not in members,'duplicate/member count cap')
   need(0<=member.size<=MEMBER_LIMIT,'tar member size cap');total+=member.size
   need(total<=EXPANDED_LIMIT,'expanded member cap')
   need(not member.sparse,'sparse tar unsupported')
   need(member.isfile() or member.isdir() or (allow_unmaterialized_links and (member.issym() or member.islnk())),'unsupported tar type')
   need(name!='.' or member.isdir(),'non-directory archive root')
   members[name]=member
  # No regular or link entry may serve as an ancestor of another entry.
  for name in members:
   for parent in PurePosixPath(name).parents:
    key=parent.as_posix()
    need(key not in members or members[key].isdir(),'non-directory tar ancestor')
  return stream,members
 except BaseException:
  stream.close();raise

def extract_binary(data, name, target):
 raw=unpack_compression(ar_data(data) if name=='verilator' else data)
 stream,members=tar_members(raw,allow_unmaterialized_links=name=='verilator')
 try:
  matches=[m for key,m in members.items() if (key=='usr/bin/verilator_bin' if name=='verilator' else PurePosixPath(key).name==name) and m.isfile()]
  need(len(matches)==1,'ambiguous/missing tool binary')
  member=matches[0]
  with stream.extractfile(member) as f:binary=f.read(MEMBER_LIMIT+1)
  need(len(binary)==member.size and len(binary)<=MEMBER_LIMIT,'binary size mismatch')
  digest=hashlib.sha256(binary).hexdigest()
  if name=='verilator':need(digest==VERILATOR_SHA,'Verilator binary drift')
  # Never extract archive links, paths, ownership or permissions. Only one known
  # regular file is created, in a fresh directory owned by this bootstrap.
  target=Path(target);target.mkdir()
  path=target/('verilator_bin' if name=='verilator' else name)
  with path.open('xb') as f:f.write(binary)
  path.chmod(0o755)
  return path.resolve(),digest
 finally:stream.close()

def main(out):
 need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'existing bootstrap deadline')
 def expired(sig,frame):raise TimeoutError('bootstrap total wall deadline')
 previous=signal.signal(signal.SIGALRM,expired)
 try:
  signal.setitimer(signal.ITIMER_REAL,180)
  out=Path(out);out.mkdir(parents=True,exist_ok=False);identity={}
  for name,(url,digest) in ASSETS.items():
   with urllib.request.urlopen(url,timeout=60) as r:data=r.read(DOWNLOAD_LIMIT+1)
   need(len(data)<=DOWNLOAD_LIMIT,'tool archive exceeds 64MiB')
   need(hashlib.sha256(data).hexdigest()==digest,'official tool archive drift')
   binary,binary_digest=extract_binary(data,name,out/name)
   identity[name]={'path':str(binary),'sha256':binary_digest,'archive_sha256':digest,'url':url}
  (out/'TOOLS.json').write_text(json.dumps(identity,indent=2)+'\n')
 finally:
  signal.setitimer(signal.ITIMER_REAL,0)
  signal.signal(signal.SIGALRM,previous)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('out');main(p.parse_args().out)

"""Offline trusted ZIP -> seven files. No network, ldd, imports from artifact or execution.
Caller supplies independently verified GitHub API receipt hash and ZIP digest;
these cannot be taken from the ZIP. New files are mode0600, including the ELF.
Readelf/static resource review + fresh live ABI are later gates, not this step.
"""
import argparse,json,os,pathlib,re,stat,zipfile
from seven_files import CAP,NAMES,need,sha,regular,verify
P=pathlib.Path

def receive(archive,archive_sha,api_receipt,api_sha,dest,identity,manifest_sha):
 archive=regular(archive,CAP+(64<<20));api=regular(api_receipt,65536)
 need(re.fullmatch('[0-9a-f]{64}',archive_sha)and sha(archive)==archive_sha and sha(api)==api_sha,'independently trusted archive/API pins')
 r=json.loads(api.read_text())
 need(set(r)=={'schema','artifact_id','name','run_id','source_commit','launch_commit','expired','api_size_in_bytes','downloaded_zip_bytes','archive_sha256','api_verified'},'exact outer API receipt')
 need(r['schema']=='AUTHENTICATED_GITHUB_ARTIFACT_RECEIPT_V1'and r['api_verified']is True and r['expired']is False,'outer authenticated remote observation required; fields not self-authority')
 need(type(r['artifact_id'])is int and r['artifact_id']>0 and type(r['run_id'])is int and r['run_id']==identity['run_id']and r['name']==identity['artifact_name']and r['source_commit']==identity['source_commit']and r['launch_commit']==identity['launch_commit'],'exact actual source/run/name')
 need(type(r['api_size_in_bytes'])is int and r['api_size_in_bytes']>0,'bounded original API storage-size observation')
 need(type(r['downloaded_zip_bytes'])is int and r['downloaded_zip_bytes']==archive.stat().st_size and r['archive_sha256']==archive_sha,'actual independently observed download ZIP size/digest')
 dest=P(dest);need(dest.is_absolute()and dest==dest.resolve()and not dest.exists()and all(not q.is_symlink()for q in(dest,*dest.parents))and dest.parent.is_dir(),'fresh canonical destination')
 expected=set(NAMES.values())|{'frozen_artifact.json'}
 with zipfile.ZipFile(archive)as z:
  infos=z.infolist();need(len(infos)==7 and {x.filename for x in infos}==expected,'exact flat seven names, no duplicates/directories/extra payload')
  total=0
  for x in infos:
   mode=x.external_attr>>16
   need(not x.is_dir()and x.filename==P(x.filename).name and not(x.flag_bits&1)and x.compress_type in(zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'plain supported flat payload')
   need(stat.S_IFMT(mode)in(0,stat.S_IFREG),'no symlink/device/directory')
   cap=65536 if x.filename in('frozen_artifact.json','build_receipt.json')else 32<<20 if x.filename in('driver.cpp','source_manifest.json','tool_manifest.json')else CAP
   need(type(x.file_size)is int and 0<x.file_size<=cap and x.compress_size>0,'bounded ZIP entry');total+=x.file_size
  need(total<=CAP,'expanded total cap before extraction')
  dest.mkdir(mode=0o700)
  for x in infos:
   path=dest/x.filename;fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);count=0
   with os.fdopen(fd,'wb')as out,z.open(x)as source:
    while True:
     data=source.read(min(1<<20,x.file_size-count+1))
     if not data:break
     count+=len(data);need(count<=x.file_size,'expanded overrun');out.write(data)
   need(count==x.file_size and stat.S_IMODE(path.stat().st_mode)==0o600,'complete non-executable local bytes')
 payload=verify(dest,identity,manifest_sha)
 need(sha(archive)==archive_sha and sha(api)==api_sha,'inputs unchanged after read')
 return dict(schema='RECEIVED_SEVEN_FILES_BYTES_ONLY_V1',artifact_id=r['artifact_id'],archive_sha256=archive_sha,verified_api_receipt_sha256=api_sha,payload=payload,numerical_pass=False,executable_permission_granted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for name in('archive','api-receipt','dest','identity','output'):p.add_argument('--'+name,type=P,required=True)
 for name in('archive-sha256','api-receipt-sha256','manifest-sha256'):p.add_argument('--'+name,required=True)
 a=p.parse_args();identity=json.loads(regular(a.identity,65536).read_text());result=receive(a.archive,a.archive_sha256,a.api_receipt,a.api_receipt_sha256,a.dest,identity,a.manifest_sha256)
 with a.output.open('x')as f:json.dump(result,f,sort_keys=True,indent=2);f.write('\n')

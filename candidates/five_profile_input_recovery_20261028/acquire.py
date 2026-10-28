#!/usr/bin/env python3
"""Pinned-revision range acquisition only. Never a numerical qualification."""
import concurrent.futures, hashlib, json, os, shutil, sys, threading, time, urllib.request, urllib.parse
from pathlib import Path
HERE=Path(__file__).resolve().parent
OUT=None
MAX=8*1024*1024
stop=threading.Event(); lock=threading.Lock(); totals={'requested':0,'received':0,'requests':0}
def need(v,s):
 if not v: raise ValueError(s)
def digest(b):return hashlib.sha256(b).hexdigest()
def write_json(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def log(v):
 with lock:
  with (OUT/'requests.jsonl').open('a') as f:f.write(json.dumps(v,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
def fetch(url,start,end,total,identity):
 need(not stop.is_set(),'another acquisition failed; stop before request')
 need(urllib.parse.urlsplit(url).scheme=='https' and urllib.parse.urlsplit(url).hostname=='huggingface.co','canonical URL not allowed')
 n=end-start+1;need(0<n<=MAX and 0<=start<=end<total,'range bounds')
 r={'identity':identity,'url':url,'start':start,'end':end,'expected_bytes':n,'started':time.time()}
 with lock:
  need(totals['requested']+n<=BODY_CAP,'aggregate body cap');totals['requested']+=n;totals['requests']+=1
 try:
  req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity','User-Agent':'hetero-pinned-recovery/1.0'})
  with urllib.request.urlopen(req,timeout=90) as response:
   r.update(status=response.status,content_range=response.headers.get('Content-Range'),content_length=response.headers.get('Content-Length'),final_host=urllib.parse.urlsplit(response.url).hostname,etag=response.headers.get('ETag'))
   need(urllib.parse.urlsplit(response.url).scheme=='https','non-HTTPS redirect refused')
   need(response.status==206,'range status must be 206')
   need(response.headers.get('Content-Range')==f'bytes {start}-{end}/{total}','Content-Range mismatch')
   need(response.headers.get('Content-Length')==str(n),'Content-Length mismatch')
   need(response.headers.get('Content-Encoding','identity')=='identity','encoded response refused')
   b=response.read(n+1);need(len(b)==n,'body size mismatch')
  with lock:totals['received']+=len(b)
  r.update(bytes=len(b),sha256=digest(b),status_check='PASS_RANGE_BYTES_ONLY',ended=time.time());log(r);return b
 except BaseException as e:
  r.update(error=type(e).__name__+': '+str(e),ended=time.time());log(r);stop.set();raise

def acquire(spec):
 model=spec['model']; name=spec['name']; folder=OUT/model;folder.mkdir(exist_ok=True)
 partial=folder/(name+'.partial'); final=folder/(name+'.bin');h=hashlib.sha256();done=0
 try:
  with partial.open('xb') as f:
   for start in range(spec['start'],spec['end']+1,MAX):
    b=fetch(spec['url'],start,min(start+MAX-1,spec['end']),spec['shard_bytes'],name);f.write(b);h.update(b);done+=len(b)
   f.flush();os.fsync(f.fileno())
  need(done==spec['bytes'],'full tensor size mismatch');sha=h.hexdigest()
  if spec['verification']=='EXACT_NAME_SHA256':need(sha==spec['expected_sha256'],'exact tensor hash mismatch')
  elif spec['verification']=='PUBLISHED_RAW_SOURCE_SET_MEMBERSHIP':need(sha in spec['allowed_sha256'],'raw source set hash mismatch')
  partial.rename(final)
  receipt={**spec,'actual_sha256':sha,'actual_bytes':done,'file':str(final.relative_to(OUT)),'status':'ACQUIRED_ORIGINAL_TENSOR_BYTES_ONLY_NOT_REFERENCE_OR_DUT'}
  write_json(folder/(name+'.receipt.json'),receipt)
  print(json.dumps({'tensor':name,'model':model,'bytes':done,'sha256':sha,'verification':spec['verification']}),flush=True)
  return receipt
 except BaseException as e:
  stop.set();log({'tensor':name,'model':model,'error':type(e).__name__+': '+str(e),'partial_bytes':done});raise


def reuse_verified(previous,spec):
 """Explicit offline reuse only; independently hash exact completed semantic receipt."""
 from reconstruct_plan import same, checked_path
 previous=Path(previous).resolve();model=spec['model'];name=spec['name']
 receipt=previous/model/(name+'.receipt.json')
 if not receipt.exists():return None
 r=json.loads(receipt.read_text())
 need(all(same(r.get(k),v) for k,v in spec.items()),'reuse receipt semantic/verification drift')
 p=checked_path(previous,r['file']);need(p.is_file() and p.stat().st_size==spec['bytes'],'reuse size')
 with p.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
 need(sha==r['actual_sha256'],'reuse current SHA')
 if spec['verification']=='EXACT_NAME_SHA256':need(sha==spec['expected_sha256'],'reuse exact pin')
 elif spec['verification']=='PUBLISHED_RAW_SOURCE_SET_MEMBERSHIP':need(sha in spec['allowed_sha256'],'reuse source set')
 folder=OUT/model;folder.mkdir(exist_ok=True);dest=folder/(name+'.bin')
 with p.open('rb') as src,dest.open('xb') as dst:shutil.copyfileobj(src,dst,8*1024*1024)
 with dest.open('rb') as f:need(hashlib.file_digest(f,'sha256').hexdigest()==sha,'copied reuse SHA')
 r=dict(r,file=str(dest.relative_to(OUT)),reuse='independently rehashed completed prior receipt; no payload request')
 write_json(folder/(name+'.receipt.json'),r);return r

def main():
 import argparse
 from reconstruct_plan import verified_plan
 global OUT,BODY_CAP
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--execute',action='store_true',help='Only after authorized network access is restored; no automatic retry')
 ap.add_argument('--reuse-from',type=Path,help='Explicit prior partial acquisition; only completed exact receipts are rehashed and copied, partial bytes are never resumed')
 args=ap.parse_args();need(args.execute,'explicit --execute required; metadata-only check is reconstruct_plan.py')
 OUT=args.output.resolve();need(not OUT.exists(),'fresh output required; no overwrite or blind retry')
 need(shutil.disk_usage(OUT.parent).free>=8*1024**3,'need 8 GiB free')
 plan=verified_plan();BODY_CAP=plan['body_cap'];OUT.mkdir();write_json(OUT/'ACQUISITION_PLAN.json',plan)
 try:
  for sh in plan['headers']:
   b=fetch(sh['url'],0,sh['header']['bytes']-1,sh['file_bytes'],'shard-header')
   need(digest(b)==sh['header']['sha256'],'downloaded header SHA mismatch')
   d=OUT/'headers';d.mkdir(exist_ok=True);(d/(digest(b)+'.bin')).write_bytes(b)
  specs=sorted(plan['specs'],key=lambda t:(t['bytes'],t['model'],t['name']))
  results=[];pending=[]
  for t in specs:
   reused=reuse_verified(args.reuse_from,t) if args.reuse_from else None
   if reused is None:pending.append(t)
   else:results.append(reused)
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   futures=[pool.submit(acquire,t) for t in pending]
   for f in concurrent.futures.as_completed(futures):results.append(f.result())
  write_json(OUT/'SUMMARY.json',{'status':'ACQUIRED_70_ORIGINAL_TENSORS_ONLY','tensors':len(results),'tensor_bytes':sum(r['actual_bytes'] for r in results),'totals':totals,'reference_executed':False,'dut_executed':False})
 except BaseException as e:
  stop.set();write_json(OUT/'FAILURE.json',{'status':'FAIL_ACQUISITION_PRESERVE_PARTIALS_NO_RETRY','error':type(e).__name__+': '+str(e),'totals':totals});raise
if __name__=='__main__':main()

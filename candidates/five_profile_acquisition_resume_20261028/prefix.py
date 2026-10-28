"""Offline fail-closed reuse of successful exact-range contiguous partial prefixes."""
import hashlib,json
from pathlib import Path

def need(v,s):
 if not v:raise ValueError(s)

def validate_prefix(previous,spec,current_etag,current_header_sha):
 previous=Path(previous).resolve()
 p=previous/spec['model']/(spec['name']+'.partial')
 if not p.exists() or p.stat().st_size==0:return None
 need(p.resolve().is_relative_to(previous),'prefix path escape')
 size=p.stat().st_size;need(0<size<spec['bytes'],'partial size not incomplete')
 plan=json.loads((previous/'ACQUISITION_PLAN.json').read_text())
 candidates=[s for s in plan['specs'] if s['model']==spec['model'] and s['name']==spec['name']]
 need(len(candidates)==1 and json.dumps(candidates[0],sort_keys=True)==json.dumps(spec,sort_keys=True),'prior semantic plan drift')
 rows=[json.loads(x) for x in (previous/'requests.jsonl').read_text().splitlines()]
 hdr=[r for r in rows if r.get('identity')=='shard-header' and r.get('url')==spec['url'] and r.get('status_check')=='PASS_RANGE_BYTES_ONLY']
 need(len(hdr)==1 and bool(current_etag) and hdr[0].get('etag')==current_etag and hdr[0].get('sha256')==current_header_sha,'pinned header/ETag drift')
 rows=[r for r in rows if r.get('identity')==spec['name'] and r.get('url')==spec['url'] and r.get('status_check')=='PASS_RANGE_BYTES_ONLY']
 rows.sort(key=lambda r:r['start']);offset=spec['start'];total=0
 with p.open('rb') as f:
  for r in rows:
   n=r['end']-r['start']+1
   need(r['start']==offset and 0<n<=8*1024*1024 and r['end']<=spec['end'],'noncontiguous/overlap/outside range')
   need(r.get('status')==206 and r.get('etag')==current_etag and r.get('bytes')==n and r.get('expected_bytes')==n and r.get('content_length')==str(n) and r.get('content_range')==f"bytes {r['start']}-{r['end']}/{spec['shard_bytes']}",'range receipt drift')
   b=f.read(n);need(len(b)==n and hashlib.sha256(b).hexdigest()==r['sha256'],'prefix truncation/hash drift');offset+=n;total+=n
  need(total==size and not f.read(1),'unreceipted prefix bytes')
 need(rows,'missing successful prefix ranges')
 return p,rows

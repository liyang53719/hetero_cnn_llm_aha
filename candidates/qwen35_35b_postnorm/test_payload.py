"""Pinned postnorm selection, bounded fake HTTP206; no network."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import payload as c

class PayloadTests(unittest.TestCase):
 def test_only_original_postnorm(self):
  p=c.selection();self.assertEqual(p['payload_bytes'],4096);self.assertEqual(len(p['shards']),1)
  self.assertEqual([(x['dtype'],x['shape'],x['start'],x['end']) for x in p['tensors']],
   [('BF16',[2048],7884248,7888343)])
  self.assertFalse(any('expert' in x['name'] or 'in_proj' in x['name'] for x in p['tensors']))
 def fake(self):
  p=c.selection();shards={s['url']:s for s in p['shards']};calls=[]
  def fetch(url,start,end,total,**kwargs):
   s=shards[url];self.assertEqual(total,s['file_bytes']);self.assertLessEqual(end-start+1,c.p.MAX_RANGE_BYTES)
   calls.append((url,start,end));h=c.p.read_record(c.ROOT,s['header']);raw=h if (start,end)==(0,len(h)-1) else bytes(end-start+1)
   return raw,dict(requested_url=url,request_range=f'bytes={start}-{end}',status=206,content_range=f'bytes {start}-{end}/{total}',bytes=len(raw),sha256=c.p.sha256(raw),acquired_at='fixture')
  return fetch,calls
 def test_bounded_collect_verify_and_tamper(self):
  fetch,calls=self.fake()
  with tempfile.TemporaryDirectory() as tmp,patch.object(c.p,'fetch_range',side_effect=fetch):
   out=Path(tmp)/'payload';c.collect(out);digest=c.p.sha256((out/'manifest.json').read_bytes());_,values=c.load(out,digest)
   self.assertEqual(sum(map(len,values.values())),4096);self.assertEqual(len(calls),2)
   self.assertEqual([(a,b) for _,a,b in calls[-1:]],[(7884248,7888343)])
   with self.assertRaises(ValueError):c.collect(out)
   f=out/'layers.0.post_attention_layernorm.weight.bin';f.write_bytes(b'X'+f.read_bytes()[1:])
   with self.assertRaisesRegex(ValueError,'payload hash'):c.load(out,digest)
 def test_manifest_receipt_and_external_pin_required(self):
  fetch,_=self.fake()
  with tempfile.TemporaryDirectory() as tmp,patch.object(c.p,'fetch_range',side_effect=fetch):
   out=Path(tmp)/'payload';c.collect(out)
   with self.assertRaises(ValueError):c.load(out,'0'*64)
   m=json.loads((out/'manifest.json').read_text());m['tensors'][0]['http_ranges'][0]['status']=200
   (out/'manifest.json').write_text(json.dumps(m))
   with self.assertRaisesRegex(ValueError,'HTTP range receipt'):c.load(out,c.p.sha256((out/'manifest.json').read_bytes()))
if __name__=='__main__':unittest.main()

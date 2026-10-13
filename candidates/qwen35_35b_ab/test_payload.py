"""Offline pinned metadata and strict fake-range acquisition; no network."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import payload as c

class PayloadTests(unittest.TestCase):
    def test_only_exact_ab_log_bias_metadata_not_z_or_experts(self):
        p=c.selection();self.assertEqual((p['payload_bytes'],len(p['tensors']),len(p['shards'])),(262336,4,1))
        self.assertEqual([t['dtype'] for t in p['tensors']],['BF16','BF16','F32','BF16'])
        self.assertEqual([(t['start'],t['end']) for t in p['tensors']],[(277976,409047),(409048,540119),(189080,189207),(277912,277975)])
        self.assertTrue(all('expert' not in t['name'] and 'in_proj_z' not in t['name'] for t in p['tensors']))

    def fixture(self):
        p=c.selection();s=p['shards'][0]
        header=c.p.read_record(c.ROOT,s['header']);calls=[]
        def fetch(url,start,end,total,**kwargs):
            self.assertEqual(url,s['url']);self.assertEqual(total,s['file_bytes'])
            calls.append((start,end))
            raw=header if (start,end)==(0,len(header)-1) else bytes(end-start+1)
            self.assertEqual(len(raw),end-start+1)
            return raw,dict(requested_url=url,request_range=f'bytes={start}-{end}',status=206,
                content_range=f'bytes {start}-{end}/{total}',bytes=len(raw),sha256=c.p.sha256(raw),acquired_at='fixture')
        return fetch,calls

    def test_fake_ranges_recheck_data_manifest_and_no_reuse(self):
        fetch,calls=self.fixture()
        with tempfile.TemporaryDirectory() as tmp, patch.object(c.p,'fetch_range',side_effect=fetch):
            out=Path(tmp)/'payload';c.collect(out)
            sha=c.p.sha256((out/'manifest.json').read_bytes())
            _,v=c.load(out,sha);self.assertEqual(sum(map(len,v.values())),262336)
            self.assertEqual(calls,[(0,189079),(277976,409047),(409048,540119),(189080,189207),(277912,277975)])
            with self.assertRaises(ValueError):c.collect(out)
            data=out/'layers.0.linear_attn.in_proj_a.weight.bin';data.write_bytes(b'X'+data.read_bytes()[1:])
            with self.assertRaisesRegex(ValueError,'payload hash'):c.load(out,sha)

    def test_manifest_alias_and_digest_rejected(self):
        fetch,_=self.fixture()
        with tempfile.TemporaryDirectory() as tmp, patch.object(c.p,'fetch_range',side_effect=fetch):
            out=Path(tmp)/'payload';c.collect(out)
            sha=c.p.sha256((out/'manifest.json').read_bytes())
            with self.assertRaisesRegex(ValueError,'digest pin'):c.load(out,'0'*64)
            alias=Path(tmp)/'alias';alias.symlink_to(out,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlink/alias'):c.load(alias,sha)
            m=json.loads((out/'manifest.json').read_bytes());m['tensors'][0]['http_ranges'][0]['status']=200
            (out/'manifest.json').write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'HTTP range receipt'):
                c.load(out,c.p.sha256((out/'manifest.json').read_bytes()))

if __name__=='__main__':unittest.main()

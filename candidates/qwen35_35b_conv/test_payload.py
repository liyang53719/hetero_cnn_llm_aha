"""Offline pinned metadata and strict fake-range acquisition; no network."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import payload as c

class PayloadTests(unittest.TestCase):
    def test_only_exact_conv_metadata_not_experts(self):
        p=c.selection();t=p['tensors'][0]
        self.assertEqual((p['payload_bytes'],len(p['tensors']),len(p['shards'])),(65536,1,1))
        self.assertEqual((t['start'],t['end'],t['shape']),(212376,277911,[8192,1,4]))
        self.assertEqual(p['header_preflight_bytes'],189080)
        self.assertNotIn('expert',t['name'])

    def fixture(self):
        p=c.selection();s=p['shards'][0]
        header=c.p.read_record(c.ROOT,s['header']);calls=[]
        def fetch(url,start,end,total,**kwargs):
            self.assertEqual(url,s['url']);self.assertEqual(total,s['file_bytes'])
            calls.append((start,end))
            raw=header if (start,end)==(0,len(header)-1) else bytes(65536)
            self.assertEqual(len(raw),end-start+1)
            return raw,dict(requested_url=url,request_range=f'bytes={start}-{end}',status=206,
                content_range=f'bytes {start}-{end}/{total}',bytes=len(raw),sha256=c.p.sha256(raw),acquired_at='fixture')
        return fetch,calls

    def test_fake_ranges_recheck_data_manifest_and_no_reuse(self):
        fetch,calls=self.fixture()
        with tempfile.TemporaryDirectory() as tmp, patch.object(c.p,'fetch_range',side_effect=fetch):
            out=Path(tmp)/'payload';c.collect(out)
            sha=c.p.sha256((out/'manifest.json').read_bytes())
            _,v=c.load(out,sha);self.assertEqual(v[c.LOCAL],bytes(65536))
            self.assertEqual(calls,[(0,189079),(212376,277911)])
            with self.assertRaises(ValueError):c.collect(out)
            data=out/(c.LOCAL+'.bin');data.write_bytes(b'X'+data.read_bytes()[1:])
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

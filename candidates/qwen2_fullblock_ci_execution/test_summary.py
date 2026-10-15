import unittest
from candidates.qwen2_fullblock_ci_execution import summary as s
class SummaryTests(unittest.TestCase):
    def outputs(self):
        return {n:{**{k:r[k] for k in s.FIXED},**{k:'a'*64 for k in s.DIGESTS},'file':n+'.f32le',
                   'native_stride':[1]*len(r['shape']),'is_contiguous':True,'storage_offset':0} for n,r in s.specs().items()}
    def call(self,o):return s.observations(o,git_sha='a'*40,source_digest='b'*64)
    def test_minimal(self):
        r=self.call(self.outputs());self.assertEqual(r['reference_outputs_checked'],29);self.assertFalse(r['independently_approved']);self.assertNotIn('outputs',r)
    def test_extra_metadata(self):
        for k in ('path','source_pins','payload','receipt'):
            o=self.outputs();o['act'][k]='forbidden'
            with self.subTest(k=k),self.assertRaises(ValueError):self.call(o)
    def test_wrong_names(self):
        o=self.outputs();o['evil']=o.pop('act')
        with self.assertRaises(ValueError):self.call(o)
    def test_digest_payload(self):
        for v in ('x'*64,{'path':'x'},'abc',True):
            o=self.outputs();o['act']['sha256']=v
            with self.subTest(v=v),self.assertRaises(ValueError):self.call(o)
    def test_geometry(self):
        for k,v in (('shape',[1,1,8960]),('bytes',True),('native_stride',[True]*3),('storage_offset',1),('file','/secret')):
            o=self.outputs();o['act'][k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):self.call(o)
    def test_no_alias(self):
        o=self.outputs();r=self.call(o);self.assertFalse(any(n in r for n in o));self.assertNotIn('act',str(r));self.assertNotIn('shape',str(r))
    def test_existing_expectations_local_only(self):
        import json
        o=json.loads((s.ROOT/s.FROZEN).read_bytes())['outputs']
        r=s.checked_aggregate(o,git_sha='a'*40,source_digest='b'*64)
        self.assertTrue(r['fixed_expectations_match']);self.assertNotIn('outputs',r)
        o['act']['sha256']='a'*64
        with self.assertRaisesRegex(ValueError,'local inspection required'):
            s.checked_aggregate(o,git_sha='a'*40,source_digest='b'*64)
if __name__=='__main__':unittest.main()

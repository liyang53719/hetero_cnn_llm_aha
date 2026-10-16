"""Bound exact safe native receipts to the reviewed source closure."""
import hashlib,json,os,unittest
from pathlib import Path
from ..attention_packed_native import prepare
HERE=Path(__file__).resolve().parent
class EvidenceTests(unittest.TestCase):
    def test_receipts_and_sources(self):
        e=json.loads((HERE/'EVIDENCE.json').read_bytes())
        self.assertEqual(set(e['receipts']),{'BUILD.json','SMOKE.json','executed_pins.json'})
        parsed={}
        for n,item in e['receipts'].items():
            raw=item['exact_json'].encode();self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256']);parsed[n]=json.loads(raw)
        b,s=parsed['BUILD.json'],parsed['SMOKE.json']
        self.assertEqual(b['status'],s['status']);self.assertEqual(s['status'],'PASS_TINY_PACKED_NATIVE_MODEL')
        self.assertEqual(b['source_sha256'],prepare.snapshot());self.assertEqual(s['source_sha256'],prepare.snapshot())
        self.assertEqual(b['generated_sha256'],prepare.check()['generated']);self.assertEqual(s['generated_sha256'],b['generated_sha256'])
        self.assertEqual(b['library_sha256'],s['library_sha256']);self.assertEqual(b['smoke_sha256'],e['receipts']['SMOKE.json']['sha256'])
        self.assertEqual(b['pins_sha256'],e['receipts']['executed_pins.json']['sha256'])
        self.assertEqual((prepare.HERE/'pins.json').read_bytes(),e['receipts']['executed_pins.json']['exact_json'].encode())
        self.assertEqual(b['flags'],['-std=c++17','-O2','-shared','-fPIC','-fno-fast-math','-ffp-contract=off','-frounding-math'])
        self.assertLess(b['elapsed_seconds'],30)
        self.assertEqual([(x['profile'],x['steps'],x['fmas']) for x in s['checks'] if 'profile' in x],[(2,8,32768),(2,3,6144),(2,128,262144),(1,3,12288)])
        for key in ('full_public_admission','selected_fault_timing_qualified','rtl_execution','independent_goldens_changed'):self.assertIs(s[key],False)
        self.assertEqual({x['case'] for x in s['checks']},{'qk','pv','pv128_boundary','legacy_default','selected_nonfinite','nonselected_nonfinite'})
    def test_actual_originals_if_supplied(self):
        folder=os.environ.get('PACKED_NATIVE_RECEIPTS')
        if not folder:self.skipTest('original receipts not supplied')
        e=json.loads((HERE/'EVIDENCE.json').read_bytes());w=Path(folder)
        for n,item in e['receipts'].items():self.assertEqual((w/n).read_bytes(),item['exact_json'].encode())
        b=json.loads((w/'BUILD.json').read_bytes())
        self.assertEqual(hashlib.sha256((w/'libpacked.so').read_bytes()).hexdigest(),b['library_sha256'])
if __name__=='__main__':unittest.main()

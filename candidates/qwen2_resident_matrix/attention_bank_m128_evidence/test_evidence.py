import hashlib,json,os,tempfile,unittest
from pathlib import Path
from ..attention_bank_m128 import check_sources,run_numeric
HERE=Path(__file__).resolve().parent
class EvidenceTests(unittest.TestCase):
    def test_actual_full128_receipt_and_prerequisite(self):
        e=json.loads((HERE/'EVIDENCE.json').read_bytes());self.assertEqual(set(e['receipts']),{'m32.json','m128.json'})
        for name,item in e['receipts'].items():
            self.assertEqual(hashlib.sha256(item['exact_json'].encode()).hexdigest(),item['sha256'])
            r=json.loads(item['exact_json']);self.assertEqual(r['source_sha256'],check_sources.snapshot())
            self.assertEqual(r['status'],'PASS_BANK_TILED_ATTENTION');self.assertIs(r['source_postflight_complete'],True)
        r=json.loads(e['receipts']['m128.json']['exact_json']);self.assertEqual(r['rows'],128)
        self.assertEqual(r['m32_prerequisite_sha256'],e['receipts']['m32.json']['sha256'])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'m32.json';p.write_text(e['receipts']['m32.json']['exact_json'])
            self.assertEqual(run_numeric.prerequisite(p,check_sources.snapshot()),r['m32_prerequisite_sha256'])
        x=run_numeric.expected_counts(128);c=r['counts']
        self.assertEqual(c['matrix_steps'],71808);self.assertEqual(c['matrix_returns'],71808)
        self.assertEqual(c['matrix_groups'],7168);self.assertEqual(c['matrix_result_acks'],7168)
        self.assertEqual(c['scratch_read_requests']+c['scratch_write_requests'],693504)
        self.assertEqual(c['scratch_acks'],693504);self.assertEqual(c['scratch_edges'],2080514)
        self.assertEqual(c['selected_fmas'],256*x['pairs']);self.assertEqual(c['scalar_packets'],c['scalar_packet_acks'])
        self.assertEqual(r['reference_matrix_requests'],16*x['pairs'])
        self.assertEqual(c['scratch_bank_reads'],2*c['scratch_read_requests']);self.assertEqual(c['scratch_bank_writes'],2*c['scratch_write_requests'])
        self.assertEqual(c['max_comparisons'],99072)
        self.assertEqual(hashlib.sha256((check_sources.HERE/'pins.json').read_bytes()).hexdigest(),e['executed_pins_sha256'])
    def test_exact_original_files_if_supplied(self):
        source=os.environ.get('BANK_TILED_RECEIPTS')
        if not source:self.skipTest('original receipts not supplied')
        e=json.loads((HERE/'EVIDENCE.json').read_bytes())
        for name,item in e['receipts'].items():self.assertEqual((Path(source)/name).read_bytes(),item['exact_json'].encode())
if __name__=='__main__':unittest.main()

"""Validate safe exact receipts; optional original-file verification is explicit."""
import hashlib,json,os,unittest
from pathlib import Path
from ..attention_bank_panel import check_sources,run_numeric
HERE=Path(__file__).resolve().parent
class EvidenceTests(unittest.TestCase):
    def test_whole_receipts_sources_counts(self):
        e=json.loads((HERE/'EVIDENCE.json').read_bytes())
        self.assertEqual(set(e['receipts']),{'m17.json','m32.json'})
        for name,item in e['receipts'].items():
            raw=item['exact_json'].encode();self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
            r=json.loads(raw);self.assertEqual(r['status'],'PASS_BANK_PANEL_ATTENTION');self.assertIs(r['source_postflight_complete'],True)
            self.assertEqual(r['source_sha256'],check_sources.snapshot())
            x=run_numeric.expected_counts(r['rows']);c=r['counts']
            self.assertEqual(c['matrix_steps'],x['matrix_steps']);self.assertEqual(c['matrix_result_acks'],x['matrix_groups'])
            self.assertEqual(c['scratch_read_requests']+c['scratch_write_requests'],x['transactions'])
            self.assertEqual(c['scratch_edges'],x['bank_edges']);self.assertEqual(c['selected_fmas'],x['selected_fmas'])
            self.assertEqual(c['matrix_returns'],c['matrix_steps']);self.assertEqual(c['scalar_packets'],c['scalar_packet_acks'])
        self.assertEqual(hashlib.sha256((check_sources.HERE/'pins.json').read_bytes()).hexdigest(),e['executed_pins_sha256'])
    def test_original_files_if_provided(self):
        path=os.environ.get('BANK_PANEL_RECEIPTS')
        if not path:self.skipTest('original receipts not supplied')
        e=json.loads((HERE/'EVIDENCE.json').read_bytes())
        for name,item in e['receipts'].items():self.assertEqual((Path(path)/name).read_bytes(),item['exact_json'].encode())
if __name__=='__main__':unittest.main()

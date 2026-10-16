import hashlib,json,os,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
EXPECTED={
'm4.json':'decda9a07268c697f0fbcd79e2d5a05eee6e276de93946de3284790bcb6835b7',
'm4-corrected.json':'959cb6612c02bd16023c7963f7dbccda5283cccb36528924b2e5e77030a89966',
'm8.json':'5075b4953a47ac24ef4f2068c61719e51ae1b4bd1abe990f2c313c595ca346d8',
'm16.json':'fcdf2ee533cdf5ad1551cb101d535af6fbc867bb9e0efc91bca2c5565879714b'}


class EvidenceTests(unittest.TestCase):
    def load(self):return json.loads((HERE/'EVIDENCE.json').read_bytes())
    def test_exact_receipt_bytes_and_optional_external_originals(self):
        data=self.load();self.assertEqual(set(data['entries']),set(EXPECTED))
        external=os.environ.get('BANK_CALIBRATION_RECEIPTS')
        for name,expected in EXPECTED.items():
            entry=data['entries'][name];raw=entry['json_utf8'].encode()
            self.assertEqual(entry['sha256'],expected)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),expected)
            if external:self.assertEqual((Path(external)/name).read_bytes(),raw)
        self.assertFalse(data['m128_executed']);self.assertFalse(data['rtl_execution'])
        self.assertFalse(data['original_arithmetic_changed'])

    def test_actual_success_counts_and_shared_frozen_source(self):
        data=self.load();sources=[]
        for name,m in (('m4-corrected.json',4),('m8.json',8),('m16.json',16)):
            receipt=json.loads(data['entries'][name]['json_utf8']);counts=receipt['counts'];p=6*m*(m+1)
            self.assertEqual(receipt['status'],'PASS_MULTIROW_FRACTION_CALIBRATION')
            self.assertEqual(receipt['rows'],m);self.assertTrue(receipt['one_job_per_pass'])
            self.assertEqual(receipt['reference_matrix_requests'],16*p)
            self.assertEqual(counts['selected_fmas'],256*p)
            self.assertEqual(counts['matrix_steps'],96*m+m*(m+1))
            self.assertEqual(counts['matrix_returns'],counts['matrix_steps'])
            self.assertEqual(counts['matrix_result_acks'],14*m)
            self.assertEqual(counts['scratch_read_requests']+counts['scratch_write_requests'],7*p)
            self.assertEqual(counts['scratch_acks'],7*p)
            self.assertEqual(counts['scratch_edges'],21*p+2)
            self.assertEqual(counts['scratch_bank_reads'],2*counts['scratch_read_requests'])
            self.assertEqual(counts['scratch_bank_writes'],2*counts['scratch_write_requests'])
            self.assertEqual(counts['scalar_packets'],counts['scalar_packet_acks'])
            self.assertFalse(receipt['modeled_ticks_are_hardware'])
            self.assertFalse(receipt['native_arithmetic']);self.assertFalse(receipt['m128_executed'])
            self.assertGreater(receipt['cpu_seconds'],0);self.assertLess(receipt['elapsed_seconds'],25)
            self.assertGreater(receipt['peak_rss_kib'],0)
            sources.append(receipt['source_sha256'])
        self.assertEqual(sources[0],sources[1]);self.assertEqual(sources[1],sources[2])
        self.assertEqual(sources[0]['candidates/qwen2_resident_matrix/attention_bank_multirow/pins.json'],data['successful_execution_profile_pin'])
        execution_pins=data['execution_pin_file_utf8'].encode()
        self.assertEqual(hashlib.sha256(execution_pins).hexdigest(),data['successful_execution_profile_pin'])
        pins=json.loads(execution_pins)
        expected=dict(pins['sources']);expected.update(pins['own'])
        for name,digest in expected.items():self.assertEqual(sources[0][name],digest)
        from ..attention_bank_multirow.check_sources import check,snapshot
        check();current=snapshot()
        metadata={'candidates/qwen2_resident_matrix/attention_bank_multirow/README.md','candidates/qwen2_resident_matrix/attention_bank_multirow/pins.json'}
        self.assertEqual({k:v for k,v in current.items() if k not in metadata},{k:v for k,v in sources[0].items() if k not in metadata})
        failed=json.loads(data['entries']['m4.json']['json_utf8'])
        self.assertEqual(failed['status'],'FAILED_CALIBRATION')
        self.assertEqual(failed['error_class'],'NumericalFault')
        self.assertFalse(failed['numerical_acceptance'])
        self.assertFalse(data['first_failure_source_manifest_available'])

if __name__=='__main__':unittest.main()

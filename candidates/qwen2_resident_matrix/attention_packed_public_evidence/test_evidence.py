import hashlib,json,os,unittest
from pathlib import Path
from ..attention_packed_public import prepare
HERE=Path(__file__).resolve().parent
class EvidenceTests(unittest.TestCase):
    def test_exact_safe_receipts_and_accounting(self):
        e=json.loads((HERE/'EVIDENCE.json').read_bytes());rs=e['receipts']
        self.assertEqual(set(rs),{'normal.json','normal.log','executed_pins.json','POSTFLIGHT.json'})
        for v in rs.values():self.assertEqual(hashlib.sha256(v['exact_text'].encode()).hexdigest(),v['sha256'])
        r=json.loads(rs['normal.json']['exact_text']);p=json.loads(rs['executed_pins.json']['exact_text']);current=prepare.check()
        self.assertEqual(r['status'],'PASS_BOUNDED_PUBLIC_TRANSPORT')
        self.assertEqual(len(r['source_sha256']),166)
        for k in ('new_compilation','full_public_graph','rtl'):self.assertIs(r[k],False)
        self.assertEqual(r['library_sha256'],'1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811')
        now=prepare.snapshot();readme=prepare.PREFIX+'README.md';pin=prepare.PREFIX+'pins.json'
        for n,h in r['source_sha256'].items():
            if n not in (readme,pin):self.assertEqual(now[n],h,n)
        self.assertEqual(r['source_sha256'][pin],rs['executed_pins.json']['sha256'])
        self.assertEqual(p['sources'],current['sources']);self.assertEqual(p['generated'],current['generated'])
        for n,h in p['own'].items():
            if n!=readme:self.assertEqual(current['own'][n],h,n)
        for c in r['cases'][:2]:
            m=c['rows'];self.assertIn(m,(1,2));self.assertEqual(c['owner_edges'],c['parent_edges'])
            self.assertEqual(c['owner_class'],'candidates.qwen2_resident_matrix.official_bf16.owners.OfficialAttentionOwner')
            self.assertEqual(c['all_enabled_fmas'],96*m*4096+m*(m+1)*2048)
            self.assertEqual(c['ddr_reads'],128*m);self.assertEqual(c['ddr_writes'],96*m)
            kv=c['kv'];self.assertEqual(kv['core_requests'],56*m*(m+1));self.assertEqual(kv['core_responses'],kv['core_requests'])
            self.assertEqual(kv['ddr_requests'],32*m);self.assertEqual(kv['ddr_responses'],32*m);self.assertEqual(kv['fills'],32*m)
            self.assertEqual(kv['hits'],kv['core_requests']-kv['fills']);self.assertEqual(kv['releases'],1)
            a=c['scratch'];self.assertEqual(a['raw_requests'],48*m);self.assertEqual(a['raw_acks'],a['raw_requests'])
            self.assertEqual(a['responses'],a['response_fires']);self.assertEqual(a['physical_acquires'],1);self.assertEqual(a['releases'],1)
            matrix=c['matrix'];self.assertEqual(matrix['normal_steps'],96*m+m*(m+1))
            self.assertEqual(matrix['normal_done'],14*m);self.assertEqual(matrix['normal_results'],14*m)
            self.assertEqual(matrix['packed_write_debts'],108*m);self.assertEqual(matrix['packed_write_acks'],108*m)
        faults=r['cases'][2:];self.assertEqual([x['fault'] for x in faults],['selected_overflow','foreign_ddr','output_error','scratch_abort'])
        for c in faults:self.assertIs(c['failed'],True);self.assertIs(c['drained'],True)
        post=json.loads(rs['POSTFLIGHT.json']['exact_text']);self.assertEqual(post['receipt_sha256'],rs['normal.json']['sha256'])
        self.assertEqual(post['executed_pins_sha256'],rs['executed_pins.json']['sha256']);self.assertEqual(post['source_count'],166)
        self.assertIn('Ran 1 test',rs['normal.log']['exact_text']);self.assertTrue(rs['normal.log']['exact_text'].endswith('OK\n'))
    def test_original_bytes_if_available(self):
        folder=os.environ.get('PACKED_PUBLIC_RECEIPTS')
        if not folder:self.skipTest('original receipts not supplied')
        for n,v in json.loads((HERE/'EVIDENCE.json').read_bytes())['receipts'].items():self.assertEqual((Path(folder)/n).read_bytes(),v['exact_text'].encode())

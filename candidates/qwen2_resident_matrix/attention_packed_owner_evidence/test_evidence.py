import hashlib,json,os,unittest
from pathlib import Path
from ..attention_packed_owner import prepare
HERE=Path(__file__).resolve().parent
class EvidenceTests(unittest.TestCase):
    def test_safe_receipts(self):
        e=json.loads((HERE/'EVIDENCE.json').read_bytes());rs=e['receipts']
        self.assertEqual(set(rs),{'normal.json','optimized.json','executed_pins.json','normal.log','optimized.log'})
        for item in rs.values():self.assertEqual(hashlib.sha256(item['exact_text'].encode()).hexdigest(),item['sha256'])
        cases=[]
        for n in ('normal.json','optimized.json'):
            r=json.loads(rs[n]['exact_text']);self.assertEqual(r['status'],'PASS_BOUNDED_ORIGINAL_PACKED_OWNER')
            self.assertEqual(r['source_sha256'],prepare.snapshot());self.assertIs(r['reused_qualified_library'],True)
            for key in ('new_compilation','full_public_admission','rtl_execution'):self.assertIs(r[key],False)
            self.assertEqual(r['library_sha256'],'1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811')
            for c in r['cases']:
                m=c['rows'];self.assertIn(m,(1,2));self.assertEqual(c['owner_type'],'OfficialAttentionOwner')
                self.assertEqual(c['parent_edges'],c['owner_edges']);self.assertIs(c['one_parent_edge_per_owner_edge'],True)
                self.assertIs(c['same_parent_banks'],True);self.assertIs(c['terminal_after_bank_release'],True)
                self.assertEqual(c['all_enabled_fmas'],96*m*4096+m*(m+1)*2048)
                self.assertEqual(c['useful_selected_fmas'],6*m*(m+1)*256)
                self.assertEqual(c['ddr_reads'],96*m+56*m*(m+1));self.assertEqual(c['ddr_writes'],96*m)
                self.assertEqual(c['output_ack_bytes'],6144*m);self.assertEqual(c['matrix_counts']['normal_steps'],96*m+m*(m+1))
                self.assertEqual(c['matrix_counts']['normal_results'],14*m);self.assertEqual(c['matrix_counts']['normal_done'],14*m)
                self.assertEqual(c['matrix_counts']['packed_write_debts'],c['matrix_counts']['packed_write_acks'])
            cases.append(r['cases'])
        self.assertEqual(cases[0],cases[1]);self.assertEqual((prepare.HERE/'pins.json').read_text(),rs['executed_pins.json']['exact_text'])
        for n in ('normal.log','optimized.log'):
            self.assertIn('Ran 22 tests',rs[n]['exact_text']);self.assertTrue(rs[n]['exact_text'].endswith('OK\n'))
    def test_actual_originals_if_supplied(self):
        folder=os.environ.get('PACKED_OWNER_RECEIPTS')
        if not folder:self.skipTest('actual originals not supplied')
        for n,item in json.loads((HERE/'EVIDENCE.json').read_bytes())['receipts'].items():self.assertEqual((Path(folder)/n).read_bytes(),item['exact_text'].encode())
if __name__=='__main__':unittest.main()

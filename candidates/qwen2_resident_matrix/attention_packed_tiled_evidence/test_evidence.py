import hashlib,json,os,unittest
from pathlib import Path
from ..attention_packed_tiled_transport import prepare
HERE=Path(__file__).resolve().parent
class Tests(unittest.TestCase):
 def test_receipts_sources_and_counts(self):
  e=json.loads((HERE/'EVIDENCE.json').read_bytes());rs=e['receipts'];p=prepare.check()
  for v in rs.values():self.assertEqual(hashlib.sha256(v['exact_text'].encode()).hexdigest(),v['sha256'])
  self.assertEqual(json.loads(rs['EXECUTED_PINS.json']['exact_text']),p)
  for m in (17,32):
   r=json.loads(rs[f'm{m}.json']['exact_text']);s=json.loads(rs[f'm{m}_SUPERVISOR.json']['exact_text'])
   self.assertEqual(r['status'],'PASS_BOUNDED_TILED_PUBLIC_TRANSPORT');self.assertEqual(s['child_exit'],0);self.assertIs(s['timeout'],False);self.assertIs(s['cleanup_complete'],True)
   self.assertLess(s['wall_seconds'],95);self.assertLess(r['wall_seconds'],90);self.assertEqual(s['receipt_sha256'],rs[f'm{m}.json']['sha256'])
   mapping={**p['sources'],**p['own'],**p['generated'],prepare.PREFIX+'pins.json':prepare.sha(prepare.HERE/'pins.json')}
   self.assertEqual(r['source_sha256'],mapping);self.assertEqual(len(mapping),187)
   self.assertEqual(r['library_sha256'],'1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811')
   for k in ('new_compilation','full_public_graph','rtl','hardware_cycles'):self.assertIs(r[k],False)
   self.assertEqual(len(r['cases']),3 if m==17 else 1);c=r['cases'][0];g=12*sum((n+15)//16 for n in range(1,m+1))
   self.assertEqual(c['owner_edges'],c['parent_edges']);self.assertEqual(c['panel_ack_hold_edges'],7);self.assertIs(c['panel_boundary_seen'],True)
   self.assertEqual(c['all_enabled_fmas'],4096*8*g+2048*m*(m+1));self.assertEqual(c['matrix']['normal_steps'],8*g+m*(m+1))
   for k in ('normal_groups','normal_done','normal_results'):self.assertEqual(c['matrix'][k],g+2*m)
   self.assertEqual(c['matrix']['packed_write_acks'],c['matrix']['packed_write_debts'])
   self.assertEqual(c['ddr_reads'],128*m);self.assertEqual(c['ddr_writes'],96*m)
   for k in ('raw_requests','raw_acks'):self.assertEqual(c['scratch'][k],4*g)
   self.assertEqual(c['scratch']['responses'],c['scratch']['response_fires'])
   self.assertEqual(c['kv']['core_requests'],56*m*(m+1));self.assertEqual(c['kv']['core_requests'],c['kv']['core_responses'])
   self.assertEqual(c['kv']['ddr_requests'],32*m);self.assertEqual(c['kv']['ddr_responses'],32*m)
   if m==17:
    self.assertEqual([x['fault'] for x in r['cases'][1:]],['panel_abort','panel_ddr_error'])
    for x in r['cases'][1:]:
     self.assertIs(x['failed'],True);self.assertIs(x['drained'],True);self.assertIs(x['panel_boundary_seen'],True)
     self.assertEqual(x['scratch']['raw_requests'],x['scratch']['raw_acks']);self.assertEqual(x['scratch']['releases'],1)
     self.assertEqual(x['matrix']['packed_write_acks'],x['matrix']['packed_write_debts']);self.assertEqual(x['matrix']['owner_acquires'],x['matrix']['owner_releases'])
 def test_original_receipt_bytes(self):
  root=os.environ.get('PACKED_TILED_RECEIPTS')
  if not root:self.skipTest('original receipts not supplied')
  for n,v in json.loads((HERE/'EVIDENCE.json').read_bytes())['receipts'].items():self.assertEqual((Path(root)/n).read_bytes(),v['exact_text'].encode())

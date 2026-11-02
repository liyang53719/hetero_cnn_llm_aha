import copy,json,pathlib,unittest
import first_fault_policy as p
C=pathlib.Path(__file__).resolve().parent
class Tests(unittest.TestCase):
 def test_original_decode(self):
  d=p.decode_contract((C/'FIRST_FAULT_DRIVER_CONTRACT.json').read_bytes());self.assertFalse(p.terminal_contract(d));self.assertEqual(p.contract_sha(d),p.CONTRACT_SHA);self.assertEqual(len(p.contract_roles(d)),8)
 def test_terminal_decode(self):
  d=p.decode_contract((C/'FIRST_FAULT_TERMINAL_DRIVER_CONTRACT.json').read_bytes());self.assertTrue(p.terminal_contract(d));self.assertEqual(p.contract_sha(d),p.TERMINAL_CONTRACT_SHA);self.assertEqual(len(p.contract_roles(d)),12);self.assertTrue(d['terminal_payload_words_read']);self.assertFalse(d['raw_payload_values_emitted'])
 def test_changed_bytes(self):
  with self.assertRaises(ValueError):p.decode_contract((C/'FIRST_FAULT_TERMINAL_DRIVER_CONTRACT.json').read_bytes()+b' ')
 def test_unknown_version(self):
  with self.assertRaises(ValueError):p.contract_roles({'schema':'FIRST_FAULT_DRIVER_CONTRACT_V3'})
 def test_terminal_flag_bool(self):
  with self.assertRaises(ValueError):p.load_source_contract(C.parents[1],terminal=1)
if __name__=='__main__':unittest.main()

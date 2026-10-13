import unittest
import struct
from .verify import compare

class OriginalGateTests(unittest.TestCase):
    def test_two_ulp_tiny_difference_rejected_even_when_absolute_gate_passes(self):
        a=struct.pack('<H',0x100); b=struct.pack('<H',0x102)
        actual=dict(conv=a,silu=a,history=a)
        native=dict(conv=b,silu=b,history=a)
        result=compare(actual,actual,native,native)
        self.assertFalse(result['passed'])
        self.assertTrue(result['comparisons']['conv']['end_to_end']['passed'])
        self.assertEqual(result['comparisons']['conv']['same_input']['max_bf16_ulp'],2)
    def test_signed_zero_is_numeric_zero_but_history_is_bitexact(self):
        a=bytes(2); b=struct.pack('<H',0x8000)
        actual=dict(conv=a,silu=a,history=a)
        native=dict(conv=b,silu=b,history=a)
        result=compare(actual,actual,native,native)
        self.assertTrue(result['passed'])
        self.assertEqual(result['comparisons']['conv']['same_input']['signed_zero_only_mismatches'],1)
        native['history']=b
        self.assertFalse(compare(actual,actual,native,native)['passed'])

import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('tested_comparator',HERE/'comparator.py'); c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
assert Path(c.__file__).resolve()==HERE/'comparator.py'
def word(v): return struct.unpack('<I',struct.pack('<f',v))[0]
def exports():
 return {n:dict(shape=c.shape(n,128),native_dtype='float32' if n=='softmax_fp32' else 'bfloat16',fp32_file=n+'.f32.bin',fp32_bytes=4*c.math.prod(c.shape(n,128)),fp32_sha256='0'*64) for n in c.NODES}
class Tests(unittest.TestCase):
 def test_all_nodes(self): self.assertEqual(len(c.validate_exports(exports(),128)),29)
 def test_wrong_shape(self):
  e=exports();e['q']['shape'][2]=16
  with self.assertRaisesRegex(ValueError,'geometry'):c.validate_exports(e,128)
 def test_wrong_dtype(self):
  e=exports();e['q']['native_dtype']='float32'
  with self.assertRaisesRegex(ValueError,'dtype'):c.validate_exports(e,128)
 def test_path_escape(self):
  e=exports();e['q']['fp32_file']='../q.f32.bin'
  with self.assertRaisesRegex(ValueError,'filename'):c.validate_exports(e,128)
 def test_missing_node(self):
  e=exports();del e['mask']
  with self.assertRaises(ValueError):c.validate_exports(e,128)
 def test_construct_no_reads(self):
  with patch.object(Path,'read_bytes',side_effect=AssertionError('read')):c.make_comparator('/unused',exports(),terminal_guard=lambda:None)
 def test_guard_before_reads(self):
  def fail():raise ValueError('closed')
  cb=c.make_comparator('/unused',exports(),terminal_guard=fail)
  with patch.object(Path,'read_bytes',side_effect=AssertionError('read')):
   with self.assertRaisesRegex(ValueError,'closed'):cb({},None,{},terminal_values={})
 def test_bad_terminal_before_reads(self):
  cb=c.make_comparator('/unused',exports(),terminal_guard=lambda:None)
  with patch.object(Path,'read_bytes',side_effect=AssertionError('read')):
   with self.assertRaisesRegex(ValueError,'terminal'):cb({},None,{},terminal_values={})
 def test_single_use_even_failure(self):
  cb=c.make_comparator('/unused',exports(),terminal_guard=lambda:None)
  with self.assertRaises(ValueError):cb({},None,{},terminal_values={})
  with self.assertRaisesRegex(ValueError,'single-use'):cb({},None,{},terminal_values={})
 def test_m16_not_silent(self):
  with self.assertRaisesRegex(ValueError,'M128'):c.make_comparator('/unused',exports(),rows=16,terminal_guard=lambda:None)
 def test_nonfinite_actual(self):
  with self.assertRaisesRegex(ValueError,'nonfinite'):c.metric([(0x7f800000,0)],bf=True,limits=c.THRESHOLDS['operator_bf16'])
 def test_nonfinite_reference(self):
  with self.assertRaisesRegex(ValueError,'nonfinite'):c.metric([(0,0x7fc00000)],bf=True,limits=None)
 def test_bf16_low_bits(self):
  with self.assertRaisesRegex(ValueError,'low bits'):c.metric([(1,0)],bf=True,limits=None)
 def test_signed_zero(self): self.assertEqual(c.metric([(0x80000000,0)],bf=True,limits=None)['max_abs'],0)
 def test_subnormal(self): self.assertEqual(c.finite(0x10000,True),2**-133)
 def test_empty(self):
  with self.assertRaises(ValueError):c.metric([],bf=True,limits=None)
 def test_max_at_boundary_and_mean(self):
  r=c.metric([(word(.03125),0)]+[(0,0)]*7,bf=True,limits=c.THRESHOLDS['operator_bf16']);self.assertTrue(r['within_limits'])
 def test_above_max_even_low_mean(self):
  self.assertFalse(c.metric([(word(.031494140625),0)]+[(0,0)]*20,bf=True,limits=c.THRESHOLDS['operator_bf16'])['within_limits'])
 def test_above_mean_even_low_max(self):self.assertFalse(c.metric([(word(.0078125),0)],bf=True,limits=c.THRESHOLDS['operator_bf16'])['within_limits'])
 def test_fp32_no_invented_limit(self):self.assertIsNone(c.metric([(word(100),0)],bf=False,limits=None)['within_limits'])
 def test_q_layout(self):
  x=list(c.source_indices('q',2));self.assertEqual(x[128],(1536,128));self.assertEqual(x[256],(128,256))
 def test_cache_v_offset(self):self.assertEqual(next(c.source_indices('cache_v',2)),(512,0))
 def test_causal_count_and_order(self):
  x=list(c.source_indices('scores',128));self.assertEqual(len(x),99072);self.assertEqual(len(set(x)),99072);self.assertTrue(all(a==b and a%128<=(a//128)%128 for a,b in x))
 def test_rope_alias_not_tensor(self):
  x=list(c.source_indices('cos',2));self.assertEqual(x[64],(0,64));self.assertEqual(x[128],(64,128));self.assertEqual(len(set(i for i,j in x)),128)
 def test_bad_extent(self):
  with self.assertRaisesRegex(ValueError,'extent'):c.words(b'123',1,'x')
if __name__=='__main__':unittest.main()

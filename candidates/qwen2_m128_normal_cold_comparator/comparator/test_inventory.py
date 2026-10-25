from array import array
import importlib.util
from pathlib import Path
import unittest
s=importlib.util.spec_from_file_location('r2',Path(__file__).resolve().parent/'comparator.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
class Inventory(unittest.TestCase):
 def test_nine_previously_omitted_fp32_sources(self):
  for name in ('qraw','kraw','vraw','dot_parts','unrounded_dot_sum','dot_bf16','softmax_exp','normalizer','pv_raw'):
   for bad in (0x7f800000,0xff800000,0x7fc00000):
    with self.subTest(name=name,bad=bad):
     a=array('I',[bad]);
     with self.assertRaisesRegex(ValueError,'nonfinite'):c.check_words(a,1,name,bf=name=='dot_bf16',expected_digest=c.sha(a),observed=b'\1')
 def test_all_bf16_low_bits(self):
  for name in tuple(c.WIDTHS)+('kv','silu','cos','sin')+tuple(c.BF16_FIELDS):
   with self.subTest(name=name):
    a=array('I',[1])
    with self.assertRaisesRegex(ValueError,'low bits'):c.check_words(a,1,name,bf=True,expected_digest=c.sha(a))
 def test_fp32_low_bits_accepted(self):
  a=array('I',[1]);self.assertEqual(c.check_words(a,1,'qraw',bf=False,expected_digest=c.sha(a))[0],1)
 def test_unobserved_sentinel_not_finite_scan(self):
  a=array('I',[0xa5963cc3]);self.assertEqual(c.check_words(a,1,'dot_bf16',bf=True,expected_digest=c.sha(a),observed=b'\0')[0],a[0])
 def test_hash_must_match_even_unobserved(self):
  with self.assertRaisesRegex(ValueError,'digest'):c.check_words(array('I',[0]),1,'dot_parts',bf=False,expected_digest='0'*64,observed=b'\0')
 def fixture(self):
  actual={n:array('I',[0])*w for n,w in dict(c.WIDTHS,qraw=1536,kraw=256,vraw=256,kv=512).items()}
  fields={}
  for n in c.ATTENTION_FIELDS:
   shape=[12,1,1,16] if n=='dot_parts' else [12,1,3] if n=='normalizer' else [12,1,128] if n in ('pv_raw','pv_bf16') else [12,1,1]
   count=c.math.prod(shape);fields[n]=dict(shape=shape,words=array('I',[0])*count,observed=bytearray([1])*count,frequency=array('H',[8 if n in ('prob_bf16','softmax_fp32') else 1])*count)
  entries={n:{'raw_sha256':c.sha(v)} for n,v in actual.items()}
  entries.update({n:dict(raw_sha256=c.sha(v['words']),presence_sha256=c.sha(v['observed']),frequency_sha256=c.sha(v['frequency'])) for n,v in fields.items()});entries.update(silu={},cache_k={},cache_v={})
  return actual,fields,entries
 def test_complete_inventory(self):
  a,f,e=self.fixture();c.validate_inventory(a,f,e,1)
 def test_exact_kv_small_damage_and_signed_zero(self):
  for offset in (0,256):
   for damage in (0x10000,0x80000000):
    with self.subTest(offset=offset,damage=damage):
     a,f,e=self.fixture();a['kv'][offset]=damage;e['kv']['raw_sha256']=c.sha(a['kv'])
     with self.assertRaisesRegex(ValueError,'exact KV'):c.validate_inventory(a,f,e,1)
 def test_both_negative_zero_is_exact(self):
  a,f,e=self.fixture();a['kv'][0]=a['k'][0]=0x80000000
  for n in ('kv','k'):e[n]['raw_sha256']=c.sha(a[n])
  c.validate_inventory(a,f,e,1)
 def test_missing_diagnostic(self):
  a,f,e=self.fixture();del f['pv_raw']
  with self.assertRaisesRegex(ValueError,'inventory'):c.validate_inventory(a,f,e,1)
 def test_digest_all_nine(self):
  for name in ('qraw','kraw','vraw','dot_parts','unrounded_dot_sum','dot_bf16','softmax_exp','normalizer','pv_raw'):
   with self.subTest(name=name):
    a,f,e=self.fixture();e[name]['raw_sha256']='0'*64
    with self.assertRaisesRegex(ValueError,'digest'):c.validate_inventory(a,f,e,1)
if __name__=='__main__':unittest.main()

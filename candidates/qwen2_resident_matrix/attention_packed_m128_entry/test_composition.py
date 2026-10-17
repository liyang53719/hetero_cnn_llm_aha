"""Cold projection only; no library loads or numerical admission."""
import ast,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import composition as c,contract
from ..attention_packed_m16_host_job import prepare as prior
class Tests(unittest.TestCase):
 def test_exact_original_body_projection(self):
  with tempfile.TemporaryDirectory() as d:
   root=prior.compose(Path(d)/'source')
   for name in (c.REDUCED,c.OFFICIAL,c.FULL):
    before=(root/name).read_text();after=c.entry(before,name)
    compile(after,name,'exec')
    # Exact text transform has only enumerated selection/budget/metadata edits.
    # Original arithmetic helpers retain their full AST.
    names=('independent_bytes',) if name==c.REDUCED else ('load_inputs','_reference_bytes','retain_failed_run','prerequisite') if name==c.OFFICIAL else ('runtime','compare','run','load_inputs','input_spec','binary_identity')
    c.unchanged_functions(before,after,names)
    with self.assertRaises(ValueError):c.entry(after,name)
   after=c.transport((root/c.TRANSPORT).read_text());compile(after,c.TRANSPORT,'exec')
   with self.assertRaises(ValueError):c.transport(after)
 def test_canonical_m128_scope(self):
  with patch.object(contract,'snapshot',return_value={'checked':'source'}):
   self.assertEqual(contract.modes(fresh_profile=True,enable_raw_kv=True,enable_packed=True,rows=128),{'checked':'source'})
   for rows in (True,16,17,32,128.0):
    with self.assertRaises(ValueError):contract.modes(fresh_profile=True,enable_raw_kv=True,enable_packed=True,rows=rows)
   for key in ('fresh_profile','enable_raw_kv','enable_packed'):
    args=dict(fresh_profile=True,enable_raw_kv=True,enable_packed=True,rows=128);args[key]=False
    with self.assertRaises(ValueError):contract.modes(**args)
 def test_no_unbounded_or_foreign_context(self):
  for value in (None,{},dict(profile='qwen2-public-pv16-packed-m16-linked-v1')):
   with self.assertRaises(ValueError):contract.authorize_run(value)
if __name__=='__main__':unittest.main()

"""Finite current-acquirer receipt binding. Synthetic metadata, no payload/network."""
from __future__ import annotations
import argparse, ast, copy, hashlib, json, sys, tempfile, time, types, unittest
from pathlib import Path
from unittest import mock
P=argparse.ArgumentParser();P.add_argument('--repo',required=True,type=Path)
ARGS,REST=P.parse_known_args();HERE=Path(__file__).resolve().parent
PINS={
 'current_acquirer':('development_snapshots/canonical_raw_acquisition_source_20261018/acquire_raw.py',17991,'4cff91b1a5e76a6a1701426fd1e6cb1f8db32ee8b7e762bb17575364b12d932a'),
 'current_plan':('development_snapshots/canonical_raw_acquisition_source_20261018/ACQUISITION_PLAN.json',14096,'7af00f7b0ebe36a2d31cd18de72ff9da487197eb91ab671cb60a53b2c076d220'),
 'base_converter':('development_snapshots/canonical_provider_transform_source_20261018/convert_providers.py',17116,'104234daaec9bb37a1cdaefe428dd13abab4906bbc5fdf58a331c5520e632d57'),
 'base_spec':('development_snapshots/canonical_provider_transform_source_20261018/CONVERSION_SPEC.json',17884,'423fa7e23c1adfd12977b37c1a8d73e7ca9d812ba4876eeb5e9c28363333589d'),
 'derived_converter':('convert_providers.py',17116,'abcf7854796e6e90350ac832b53b070326f810d3a16bf1127919d59049768ee6'),
 'derived_spec':('CONVERSION_SPEC.json',17884,'ab1fabb72d69f0f196dafd19fe7324a1413b000952e0ee04baa3cbaaff4a14ac')}
def verified(name):
 rel,size,sha=PINS[name];root=HERE if name.startswith('derived') else ARGS.repo
 path=root/rel
 if path.is_symlink() or path.resolve()!=path.absolute():raise ValueError('source path drift')
 raw=path.read_bytes()
 if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('source pin drift')
 return raw
RAW={k:verified(k) for k in PINS}
def load(name):
 m=types.ModuleType('_receipt_'+name);m.__file__=str((HERE if name.startswith('derived') else ARGS.repo)/PINS[name][0]);sys.modules[m.__name__]=m
 exec(compile(RAW[name],m.__file__,'exec',dont_inherit=True),m.__dict__);return m
A=load('current_acquirer');C=load('derived_converter');OLD=load('base_converter')
PLAN=json.loads(RAW['current_plan']);SPEC=json.loads(RAW['derived_spec']);BASE=json.loads(RAW['base_spec'])
def receipt():
 # Evaluate only the exact verified report assignment from collect_fixed. No fetch or tensor functions.
 fn=next(n for n in ast.parse(RAW['current_acquirer']).body if isinstance(n,ast.FunctionDef) and n.name=='collect_fixed')
 nodes=[n for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='report' for t in n.targets)]
 if len(nodes)!=1:raise ValueError('fixed receipt constructor changed')
 env={'plan':copy.deepcopy(PLAN),'completed':list(range(22)),'PLAN_SHA256':A.PLAN_SHA256}
 exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'fixed-receipt','exec',dont_inherit=True),env)
 return A.json_bytes(env['report'])
def check(raw,spec=SPEC,module=C):
 with tempfile.TemporaryDirectory() as t:
  p=Path(t);(p/'ACQUIRED.json').write_bytes(raw);module.check_receipt(p,spec,time.monotonic()+30)
class Cold(unittest.TestCase):
 def test_01_current_exact_serialization(self):
  raw=receipt();self.assertEqual(len(raw),4335);self.assertEqual(hashlib.sha256(raw).hexdigest(),'0b319b9dc84a4c3942f3068b397e01f0e3493515b542ddf726d7d0677e01b6fa');check(raw)
 def test_02_old_converter_rejects_current(self):
  with self.assertRaisesRegex(ValueError,'receipt drift'):check(receipt(),BASE,OLD)
 def test_03_new_rejects_historical_metadata(self):
  r=json.loads(receipt());r['plan_sha256']=BASE['raw_receipt']['plan_sha256'];raw=A.json_bytes(r)
  self.assertEqual(hashlib.sha256(raw).hexdigest(),BASE['raw_receipt']['sha256'])
  with self.assertRaisesRegex(ValueError,'receipt drift'):check(raw)
 def test_04_only_source_binding_delta(self):
  x=copy.deepcopy(SPEC);x['raw_receipt']=BASE['raw_receipt'];self.assertEqual(x,BASE)
  self.assertEqual(RAW['derived_converter'].replace(hashlib.sha256(RAW['derived_spec']).hexdigest().encode(),hashlib.sha256(RAW['base_spec']).hexdigest().encode()),RAW['base_converter'])
 def test_05_tamper_order_and_payload_identity_rejected(self):
  for key in ('completed_segment_indices','tensors'):
   r=json.loads(receipt());r[key].reverse()
   with self.subTest(key=key),self.assertRaises(ValueError):check(A.json_bytes(r))
  r=json.loads(receipt());r['tensors'][0]['sha256']='0'*64
  with self.assertRaises(ValueError):check(A.json_bytes(r))
 def test_06_missing_truncated_trailing_rejected(self):
  for raw in (b'',receipt()[:-1],receipt()+b' '):
   with self.subTest(size=len(raw)),self.assertRaises(ValueError):check(raw)
 def test_07_provider_source_preflight(self):
  got=C.check_sources(ARGS.repo);self.assertEqual(got,SPEC);self.assertEqual(got['raw_payload_bytes'],94382080);self.assertEqual(got['provider_payload_bytes'],94916608)
 def test_08_all_function_bytes_unchanged(self):
  def funcs(raw):
   lines=raw.splitlines(keepends=True)
   return {n.name:b''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)}
  self.assertEqual(funcs(RAW['base_converter']),funcs(RAW['derived_converter']))
if __name__=='__main__':unittest.main(argv=[sys.argv[0],*REST])

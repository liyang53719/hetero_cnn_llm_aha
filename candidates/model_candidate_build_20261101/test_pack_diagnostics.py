"""Finite failure diagnostics only. No compiler, ELF or network."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('actual_pack_diagnostics',D/'pack_model_candidate.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
# Exact reviewed readonly additions, not a blanket branch/name deletion.
READONLY_INVERSE = (('17e1d27e7c2ec8c517ea9df4faf5e243b77cc2e7c3b00fa8d35d8c4c82c9c8d4', "from first_fault_policy import binding_policy, expected_driver_sha, FIRST_FAULT_MANIFEST_SCHEMA, FIRST_FAULT_SCOPE\nreadonly = binding_policy(original)\nneed(binding_policy(b) == readonly, 'same original/admitted readonly policy')", ''), ('e502e8b9d6636b44e14fb1afa37b91498b0c66e319eff96309f6e5aa7f7578b2', "need(sha(driver) == expected_driver_sha(original), 'frozen policy driver')", "need(sha(driver) == DRIVER_SHA, 'frozen driver')"), ('cc8d67bb415d3ed91d3a52d4bb2b432697d00db735dfe6bd2440ef90d5cae8e0', "need('readonly_probe' not in source, 'no prefilled readonly evidence override')\nif readonly is not None:\n    cp = regular(original['first_fault_driver_contract']['path'], 256 << 10)\n    ep = b['readonly_probe_evidence']\n    need(type(ep) is dict and set(ep) == {'path', 'bytes', 'sha256'}, 'readonly actual evidence pin')\n    actual = regular(ep['path'], 128 << 10)\n    need(pin(actual) == ep and b['pins'].get(str(actual)) == ep['sha256'], 'readonly generated evidence prebuild pin/drift')\n    source['readonly_probe'] = {'schema': 'FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1', 'status': 'OBSERVED_UNREVIEWED', 'contract': dict(pin(cp), text=cp.read_text()), 'accessor_generation': json_file(actual, 128 << 10)}", ''), ('eebfb5dd2ea1c262106b688a9dbbd5bb01462e47b7036dc845746822dcb2e11e', "if readonly is not None:\n    receipt['readonly_probe_contract_sha256'] = source['readonly_probe']['contract']['sha256']\n    receipt['scope'] = FIRST_FAULT_SCOPE", ''), ('7f63203f664ea24a84c732855fb1f9f97b4f0de9fc7dfbd15c942f8e5442e656', "if readonly is not None:\n    manifest['schema'] = FIRST_FAULT_MANIFEST_SCHEMA\n    manifest['scope'] = FIRST_FAULT_SCOPE\n    manifest['readonly_probe_contract'] = {k: source['readonly_probe']['contract'][k] for k in ('bytes', 'sha256')}", ''))
def restore_original_pack(tree):
 fs=[x for x in ast.walk(tree)if isinstance(x,ast.FunctionDef)and x.name=='_pack_impl']
 if len(fs)!=1:raise ValueError('unique actual pack implementation')
 f=fs[0]
 for expected,newtext,oldtext in READONLY_INVERSE:
  parsed=ast.parse(newtext)
  if hashlib.sha256(ast.dump(parsed,include_attributes=False).encode()).hexdigest()!=expected:raise ValueError('fixed readonly inverse fragment')
  wanted=[ast.dump(x,include_attributes=False)for x in parsed.body]
  actual=[ast.dump(x,include_attributes=False)for x in f.body]
  hits=[i for i in range(len(actual)-len(wanted)+1)if actual[i:i+len(wanted)]==wanted]
  if len(hits)!=1:raise ValueError('unique exact readonly fragment')
  i=hits[0];f.body[i:i+len(wanted)]=ast.parse(oldtext).body
 return f

class Tests(unittest.TestCase):
 def test_original_pack_algorithm_ast_exact_after_stage_markers(self):
  tree=ast.parse((D/'pack_model_candidate.py').read_text());f=restore_original_pack(tree)
  f.name='pack';self.assertEqual(f.args.args[-1].arg,'_mark');f.args.args.pop()
  marks=[x for x in f.body if isinstance(x,ast.Expr)and isinstance(x.value,ast.Call)and isinstance(x.value.func,ast.Name)and x.value.func.id=='_mark']
  self.assertEqual([x.value.args[0].value for x in marks],['SOURCE_PINS','OBSERVATION','STAGE_RECEIPTS','COMPILE_OUTPUTS','ENRICH','COPY','FINAL'])
  f.body=[x for x in f.body if x not in marks]
  self.assertEqual(hashlib.sha256(ast.dump(f,include_attributes=False).encode()).hexdigest(),'c62ca11efa3c23acfb78c52da14d372c81ff75ccc61a4bd11528864bc23487a1')
 def test_readonly_inverse_duplicate_rejected(self):
  tree=ast.parse((D/'pack_model_candidate.py').read_text());f=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='_pack_impl')
  f.body.extend(ast.parse(READONLY_INVERSE[-1][1]).body)
  with self.assertRaises(ValueError):restore_original_pack(tree)
 def test_readonly_inverse_mutation_rejected(self):
  tree=ast.parse((D/'pack_model_candidate.py').read_text())
  matches=[x for x in ast.walk(tree)if isinstance(x,ast.Constant)and x.value=='same original/admitted readonly policy']
  self.assertEqual(len(matches),1);matches[0].value='changed policy'
  with self.assertRaises(ValueError):restore_original_pack(tree)
 def test_identity_failure_has_no_raw_message_or_path(self):
  with self.assertRaises(m.ModelPackFailure)as cm:m.pack({'artifact_identity':{}},{},{},'/secret/input','/secret/overlay','/secret/out',lambda _:None,{})
  d=cm.exception.model_pack_diagnostic;self.assertEqual(d['phase'],'IDENTITY');self.assertEqual(d['reason'],'STAGE_VALIDATION_FAILED');self.assertNotIn('secret',json.dumps(d));self.assertEqual(set(d),{'schema','phase','reason','exception_class','index','bytes','expected_sha256','actual_sha256'})
 def test_source_hash_mismatch_diagnostic(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'secret-name';p.write_bytes(b'')
   with self.assertRaises(m.ModelPackFailure)as cm:m.check_pins({str(p):'f'*64})
   d=cm.exception.model_pack_diagnostic;self.assertEqual(d['index'],0);self.assertEqual(d['bytes'],0);self.assertEqual(d['reason'],'SOURCE_PIN_HASH_MISMATCH');self.assertEqual(d['actual_sha256'],hashlib.sha256(b'').hexdigest());self.assertNotIn('secret-name',json.dumps(d))
 def test_size_over_limit_is_not_reported_as_in_range(self):
  d=m.ModelPackFailure('SOURCE_PINS','SOURCE_PIN_SIZE',size=(4<<30)+1).model_pack_diagnostic;self.assertIsNone(d['bytes'])
if __name__=='__main__':unittest.main()

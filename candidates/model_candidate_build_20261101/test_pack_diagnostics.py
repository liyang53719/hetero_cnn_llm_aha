# Only historical source/AST assertions use the exact finite-layer inverse.
# Runtime tests still import and execute the actual candidate implementations.
import pathlib as _finite_pathlib, importlib.util as _finite_importlib
_finite_path=_finite_pathlib.Path(__file__).resolve().parents[2]/'candidates/model_candidate_build_20261101/finite_watchdog_test_inverse.py'
_finite_spec=_finite_importlib.spec_from_file_location('finite_watchdog_test_inverse',_finite_path)
_finite_module=_finite_importlib.module_from_spec(_finite_spec);_finite_spec.loader.exec_module(_finite_module)
prior_text=_finite_module.prior_text;prior_sha=_finite_module.prior_sha
"""Finite failure diagnostics only. No compiler, ELF or network."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('actual_pack_diagnostics',D/'pack_model_candidate.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
# Exact reviewed readonly additions, not a blanket branch/name deletion.
READONLY_INVERSE = (('17e1d27e7c2ec8c517ea9df4faf5e243b77cc2e7c3b00fa8d35d8c4c82c9c8d4', "from first_fault_policy import binding_policy, expected_driver_sha, FIRST_FAULT_MANIFEST_SCHEMA, FIRST_FAULT_SCOPE\nreadonly = binding_policy(original)\nneed(binding_policy(b) == readonly, 'same original/admitted readonly policy')", ''), ('e502e8b9d6636b44e14fb1afa37b91498b0c66e319eff96309f6e5aa7f7578b2', "need(sha(driver) == expected_driver_sha(original), 'frozen policy driver')", "need(sha(driver) == DRIVER_SHA, 'frozen driver')"), ('cc8d67bb415d3ed91d3a52d4bb2b432697d00db735dfe6bd2440ef90d5cae8e0', "need('readonly_probe' not in source, 'no prefilled readonly evidence override')\nif readonly is not None:\n    cp = regular(original['first_fault_driver_contract']['path'], 256 << 10)\n    ep = b['readonly_probe_evidence']\n    need(type(ep) is dict and set(ep) == {'path', 'bytes', 'sha256'}, 'readonly actual evidence pin')\n    actual = regular(ep['path'], 128 << 10)\n    need(pin(actual) == ep and b['pins'].get(str(actual)) == ep['sha256'], 'readonly generated evidence prebuild pin/drift')\n    source['readonly_probe'] = {'schema': 'FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1', 'status': 'OBSERVED_UNREVIEWED', 'contract': dict(pin(cp), text=cp.read_text()), 'accessor_generation': json_file(actual, 128 << 10)}", ''), ('eebfb5dd2ea1c262106b688a9dbbd5bb01462e47b7036dc845746822dcb2e11e', "if readonly is not None:\n    receipt['readonly_probe_contract_sha256'] = source['readonly_probe']['contract']['sha256']\n    receipt['scope'] = FIRST_FAULT_SCOPE", ''), ('7f63203f664ea24a84c732855fb1f9f97b4f0de9fc7dfbd15c942f8e5442e656', "if readonly is not None:\n    manifest['schema'] = FIRST_FAULT_MANIFEST_SCHEMA\n    manifest['scope'] = FIRST_FAULT_SCOPE\n    manifest['readonly_probe_contract'] = {k: source['readonly_probe']['contract'][k] for k in ('bytes', 'sha256')}", ''))

TERMINAL_PACK_FRAGMENT = "if readonly['schema'] == 'FIRST_FAULT_DRIVER_CONTRACT_V2':\n    tp = b['terminal_probe_evidence']\n    need(type(tp) is dict and set(tp) == {'path', 'bytes', 'sha256'}, 'terminal actual evidence pin')\n    terminal_actual = regular(tp['path'], 4 << 20)\n    need(pin(terminal_actual) == tp and b['pins'].get(str(terminal_actual)) == tp['sha256'], 'terminal actual evidence prebuild pin/drift')\n    source['readonly_probe'].update(schema='FIRST_FAULT_READONLY_BUILD_EVIDENCE_V2', terminal_accessor_generation=json_file(terminal_actual, 4 << 20))\nelse:\n    need('terminal_probe_evidence' not in b, 'old readonly contract cannot carry terminal evidence')"
TERMINAL_PACK_AST_SHA256 = 'be64053e73f6320bd1eaeb52073642086ab930fb1674ea9a3bbc121173246a20'
def restore_terminal_pack(tree):
 expected=ast.parse(TERMINAL_PACK_FRAGMENT).body[0]
 if hashlib.sha256(ast.dump(expected,include_attributes=False).encode()).hexdigest()!=TERMINAL_PACK_AST_SHA256:raise ValueError('fixed terminal AST')
 wanted=ast.dump(expected,include_attributes=False)
 hits=[n for n in ast.walk(tree)if ast.dump(n,include_attributes=False)==wanted]
 if len(hits)!=1:raise ValueError('unique exact terminal pack branch')
 class Strip(ast.NodeTransformer):
  def visit_If(self,n):return None if n is hits[0]else self.generic_visit(n)
 return Strip().visit(tree)

# Exact additional new-hardware source checks; legacy algorithm hash stays frozen.
ADDRESS_PACK_INVERSE = (('b2d18046fcd73a3f818789f9de75fa56d2567133e9ed6f20f7e3f46b145aa3c8', "if address_generation_observation(obs['source_closure']) or original.get('hardware_source') == 'transposed-tile-address-v1' or original.get('generation_contract_sha256') == ADDRESS_GENERATION_SHA:\n    from candidate_generation_gate import require_generation_binding\n    need(original.get('hardware_source') == b.get('hardware_source') == 'transposed-tile-address-v1', 'new hardware explicit same original/admitted source selection')\n    require_generation_binding(original)\n    require_generation_binding(b)\n    catalog = P(original['repo']) / 'candidates/same_job_execution_20261030/SOURCE_PINS.json'\n    need(obs['source_closure']['source_pins_sha256'] == sha(catalog), 'pack exact selected source catalog identity')\n    need(obs['source_closure']['generation_contract_sha256'] == original['generation_contract_sha256'] == b['generation_contract_sha256'] and str(overlay) == original['fixed_source_overlay'] == b['fixed_source_overlay'], 'pack exact new generation/overlay join')"), ('e59928f4655ffa6b8f77220e3e92987768d0f894310eec4cba0331e1818728a6', 'address_source_identity(source, obs, readonly is not None)'))

def restore_address_pack(tree):
 f=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='_pack_impl')
 for expected,text in ADDRESS_PACK_INVERSE:
  parsed=ast.parse(text)
  if hashlib.sha256(ast.dump(parsed,include_attributes=False).encode()).hexdigest()!=expected:raise ValueError('fixed address source AST')
  wanted=ast.dump(parsed.body[0],include_attributes=False)
  hits=[i for i,n in enumerate(f.body)if ast.dump(n,include_attributes=False)==wanted]
  if len(hits)!=1:raise ValueError('unique exact address source branch')
  f.body.pop(hits[0])
 return tree

def restore_original_pack(tree):
 tree=restore_terminal_pack(restore_address_pack(tree))
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
  tree=ast.parse(prior_text(D/'pack_model_candidate.py'));f=restore_original_pack(tree)
  f.name='pack';self.assertEqual(f.args.args[-1].arg,'_mark');f.args.args.pop()
  marks=[x for x in f.body if isinstance(x,ast.Expr)and isinstance(x.value,ast.Call)and isinstance(x.value.func,ast.Name)and x.value.func.id=='_mark']
  self.assertEqual([x.value.args[0].value for x in marks],['SOURCE_PINS','OBSERVATION','STAGE_RECEIPTS','COMPILE_OUTPUTS','ENRICH','COPY','FINAL'])
  f.body=[x for x in f.body if x not in marks]
  self.assertEqual(hashlib.sha256(ast.dump(f,include_attributes=False).encode()).hexdigest(),'c62ca11efa3c23acfb78c52da14d372c81ff75ccc61a4bd11528864bc23487a1')
 def test_address_inverse_duplicate_and_mutation_rejected(self):
  tree=ast.parse(prior_text(D/'pack_model_candidate.py'));f=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='_pack_impl');f.body.extend(ast.parse(ADDRESS_PACK_INVERSE[0][1]).body)
  with self.assertRaises(ValueError):restore_address_pack(tree)
  tree=ast.parse(prior_text(D/'pack_model_candidate.py'));hits=[n for n in ast.walk(tree)if isinstance(n,ast.Constant)and n.value=='pack exact selected source catalog identity'];self.assertEqual(len(hits),1);hits[0].value='mutated'
  with self.assertRaises(ValueError):restore_address_pack(tree)
 def test_readonly_inverse_duplicate_rejected(self):
  tree=ast.parse(prior_text(D/'pack_model_candidate.py'));f=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='_pack_impl')
  f.body.extend(ast.parse(READONLY_INVERSE[-1][1]).body)
  with self.assertRaises(ValueError):restore_original_pack(tree)
 def test_readonly_inverse_mutation_rejected(self):
  tree=ast.parse(prior_text(D/'pack_model_candidate.py'))
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
 def test_terminal_inverse_duplicate_and_mutation_rejected(self):
  tree=ast.parse(prior_text(D/'pack_model_candidate.py'))
  f=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='_pack_impl')
  f.body.extend(ast.parse(TERMINAL_PACK_FRAGMENT).body)
  with self.assertRaises(ValueError):restore_terminal_pack(tree)
  tree=ast.parse(prior_text(D/'pack_model_candidate.py'))
  hits=[n for n in ast.walk(tree)if isinstance(n,ast.Constant)and n.value=='terminal actual evidence pin']
  self.assertEqual(len(hits),1);hits[0].value='mutated terminal pin'
  with self.assertRaises(ValueError):restore_terminal_pack(tree)
if __name__=='__main__':unittest.main()

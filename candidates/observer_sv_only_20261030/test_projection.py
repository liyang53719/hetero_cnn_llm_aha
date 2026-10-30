import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
try:
 import sv_difference_projection as p
except ModuleNotFoundError:
 import project_key_ports as p

def fixture(name,new=True,change=''):
 ports,assigns=p.contract(name)
 decl=['input clock','output [31:0] result']
 if new:decl += [f'{d} [{w-1}:0] {n}'for n,(d,w)in ports.items()]
 body=['wire [31:0] existing;','assign existing = 32\'h0;','assign result = existing;']
 if new:body += [f'assign {d} = {s};'for d,s in assigns.items()]
 return ('module '+name+'(\n'+',\n'.join(decl)+'\n);\n'+'\n'.join(body)+'\n'+change+'\nendmodule\n').encode()
class T(unittest.TestCase):
 def test_two_modules_exact_added61bits(self):
  for name in p.MODULES:
   old=p.projected_hash(fixture(name,False),name,False);new=p.projected_hash(fixture(name),name,True)
   self.assertEqual(old['projected_normalized_sha256'],new['projected_normalized_sha256']);self.assertEqual(old['projected_normalized_bytes'],new['projected_normalized_bytes']);self.assertEqual(len(new['removed_assignments']),4)
 def test_wrong_width(self):
  name=p.MODULES[0];v=fixture(name).replace(b'input [31:0] io_tiles_response_bits_key_identity',b'input [30:0] io_tiles_response_bits_key_identity')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_wrong_direction(self):
  name=p.MODULES[0];v=fixture(name).replace(b'input [31:0] io_tiles_response_bits_key_identity',b'output [31:0] io_tiles_response_bits_key_identity')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_arithmetic_not_direct(self):
  name=p.MODULES[1];v=fixture(name).replace(b'= banks_io_tiles_response_bits_key_identity;',b'= banks_io_tiles_response_bits_key_identity + 1;')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_control_feedback_rejected(self):
  name=p.MODULES[0];v=fixture(name,change='always @(posedge clock) if (io_tiles_response_bits_key_slot) result <= 0;')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_new_input_used_elsewhere_rejected(self):
  name=p.MODULES[0];v=fixture(name,change='assign existing = io_tiles_response_bits_key_ng;')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_missing_field_rejected(self):
  name=p.MODULES[0];v=fixture(name).replace(b'assign io_residentTiles_response_bits_key_slot = io_tiles_response_bits_key_slot;',b'')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_duplicate_assign_rejected(self):
  name=p.MODULES[0];v=fixture(name,change='assign io_residentTiles_response_bits_key_slot = io_tiles_response_bits_key_slot;')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_old_already_projected_port_rejected(self):
  name=p.MODULES[0]
  with self.assertRaises(ValueError):p.projected_hash(fixture(name),name,False)
 def test_extra_logic_changes_hash(self):
  name=p.MODULES[0];old=p.projected_hash(fixture(name,False),name,False);new=p.projected_hash(fixture(name,change='wire unwanted;'),name,True);self.assertNotEqual(old['projected_normalized_sha256'],new['projected_normalized_sha256'])
 def test_no_numeric_normalization(self):
  self.assertNotEqual(list(p.tokens(b'32\'h0')),list(p.tokens(b'32\'h00')))
 def test_operator_tokens(self):
  self.assertNotEqual(list(p.tokens(b'a <= b')),list(p.tokens(b'a < = b')))
 def test_string_comments_preserved(self):
  self.assertEqual(list(p.tokens(b'"//not comment"')), [b'"//not comment"'])
  self.assertNotEqual(list(p.tokens(b'"a"')),list(p.tokens(b'"b"')))
 def test_preprocessor_line_boundary_preserved(self):
  self.assertNotEqual(list(p.tokens(b'`define A 1\nwire x;')),list(p.tokens(b'`define A\n1 wire x;')))
 def test_comments_preserved(self):
  self.assertNotEqual(list(p.tokens(b'wire /* comment */ x; // comment\n')),list(p.tokens(b'wire x;')))
 def test_semantic_pragma_change_not_equal(self):
  name=p.MODULES[0];a=p.projected_hash(fixture(name,False,change='/* verilator lint_off WIDTH */'),name,False);b=p.projected_hash(fixture(name,True,change='/* verilator lint_on WIDTH */'),name,True);self.assertNotEqual(a['projected_normalized_sha256'],b['projected_normalized_sha256'])
 def test_pragma_on_removed_line_rejected(self):
  name=p.MODULES[0];v=fixture(name).replace(b'assign io_residentTiles_response_bits_key_slot = io_tiles_response_bits_key_slot;',b'assign io_residentTiles_response_bits_key_slot = io_tiles_response_bits_key_slot; // synthesis translate_off')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_block_comment_fake_assign_rejected(self):
  name=p.MODULES[0];v=fixture(name);first=b'assign io_residentTiles_response_bits_key_identity';v=v.replace(first,b'/*\n'+first).replace(b'\nendmodule',b'\n*/\nendmodule')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_block_comment_fake_ports_rejected(self):
  name=p.MODULES[0];v=fixture(name).replace(b'input [31:0] io_tiles_response_bits_key_identity',b'/*\ninput [31:0] io_tiles_response_bits_key_identity').replace(b'\n);',b'\n*/\n);')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_conditional_assign_rejected(self):
  name=p.MODULES[0];v=fixture(name).replace(b'assign io_residentTiles_response_bits_key_identity',b'`ifdef OPTIONAL\nassign io_residentTiles_response_bits_key_identity').replace(b'\nendmodule',b'\n`endif\nendmodule')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_generate_assign_rejected(self):
  name=p.MODULES[0];v=fixture(name).replace(b'assign io_residentTiles_response_bits_key_identity',b'generate if (0) begin\nassign io_residentTiles_response_bits_key_identity').replace(b'\nendmodule',b'\nend endgenerate\nendmodule')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_old_trailing_comma_rejected(self):
  name=p.MODULES[0];v=fixture(name,False).replace(b'output [31:0] result\n',b'output [31:0] result,\n')
  with self.assertRaises(ValueError):p.projected_hash(v,name,False)
 def test_all_procedural_scopes_reject(self):
  name=p.MODULES[0]
  for scope in ('initial begin','always @(posedge clock) begin','function automatic f;','task t;'):
   v=fixture(name).replace(b'assign io_residentTiles_response_bits_key_identity',scope.encode()+b'\nassign io_residentTiles_response_bits_key_identity')
   with self.subTest(scope=scope),self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_operator_and_attribute_bytes_not_normalized(self):
  name=p.MODULES[0]
  for a,b in [('wire x = a &&& b;','wire x = a && & b;'),('wire x = a |-> b;','wire x = a | -> b;'),('(* keep = 1 *)','( * keep = 1 * )')]:
   old=p.projected_hash(fixture(name,False,change=a),name,False);new=p.projected_hash(fixture(name,True,change=b),name,True)
   self.assertNotEqual(old['projected_normalized_sha256'],new['projected_normalized_sha256'])
 def test_other_whitespace_is_exact(self):
  name=p.MODULES[0];old=p.projected_hash(fixture(name,False),name,False);new=p.projected_hash(fixture(name).replace(b'assign existing =',b'assign  existing ='),name,True);self.assertNotEqual(old['projected_normalized_sha256'],new['projected_normalized_sha256'])
 def test_attribute_before_forwarder_rejects(self):
  name=p.MODULES[0];v=fixture(name).replace(b'assign io_residentTiles_response_bits_key_identity',b'(* keep = 1 *)\nassign io_residentTiles_response_bits_key_identity')
  with self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def proof_fixture(self):
  modules={}
  for name in p.MODULES:
   rows={kind:p.projected_hash(fixture(name,kind=='new'),name,kind=='new')for kind in ('old','new')}
   for kind,row in rows.items():row['normalized_module_sha256']=p.MOD_NORMALIZED[kind][name]
   modules[name]=rows
  return dict(schema='EXACT_TWO_MODULE_KEY_PROJECTION_V1',status='PASS_ONLY_61BIT_OBSERVATION_PORT_FORWARDING_NORMALIZED_BYTE_PROJECTION',scope='TWO_SPECIFIC_MODULES_NOT_GENERAL_SV_EQUIVALENCE_OR_NUMERICAL_PASS',full_sv={k:dict(bytes=1,raw_sha256='a'*64,normalized_sha256=p.FULL[k],metadata_sha256='b'*64,scan_receipt_sha256='c'*64)for k in ('old','new')},modules=modules,scanner_sha256=p.SCANNER,projection_source_sha256=p.sha(p.__file__),full_m128_numeric_pass=False,final_rtl_pass=False,numerical_pass=False,sv_repin_authorized=False,remaining_bytes_compared=True)
 def test_proof_projector_mock(self):
  r=self.proof_fixture();self.assertEqual(p.project_proof(r),r)
 def test_proof_extra_payload_rejected(self):
  r=self.proof_fixture();r['modules'][p.MODULES[0]]['new']['payload']='rawtext'
  with self.assertRaises(ValueError):p.project_proof(r)
 def test_proof_auto_repin_rejected(self):
  r=self.proof_fixture();r['sv_repin_authorized']=True
  with self.assertRaises(ValueError):p.project_proof(r)
 def test_proof_wrong_fullhash_rejected(self):
  r=self.proof_fixture();r['full_sv']['new']['normalized_sha256']='0'*64
  with self.assertRaises(ValueError):p.project_proof(r)
 def test_backtick_location_sensitive_macros_rejected(self):
  name=p.MODULES[0]
  for macro in ('`__LINE__','`__FILE__'):
   v=fixture(name,change='initial $display('+macro+');')
   with self.subTest(macro=macro),self.assertRaises(ValueError):p.projected_hash(v,name,True)
 def test_sink_captures_exact_remaining_bytes(self):
  import io
  name=p.MODULES[0];out=io.BytesIO();p.projected_hash(fixture(name),name,True,sink=out);self.assertEqual(out.getvalue(),fixture(name,False))
 def test_unknown_module(self):
  with self.assertRaises(ValueError):p.contract('AnyOtherModule')
 def test_known_actual_hashes_not_fixture_overrides(self):
  self.assertEqual(p.FULL['old'],'6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5');self.assertEqual(p.FULL['new'],'ec70f91181b0422ca7cf2bc845a2a1f04c9d862f4f27d265c5a064a969058d72')
if __name__=='__main__':unittest.main()

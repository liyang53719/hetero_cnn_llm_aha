import pathlib,tempfile,json,hashlib,unittest
from unittest.mock import patch
import check_fresh_sv as c
from summarize_frontend import summarize
class Tests(unittest.TestCase):
 def run_case(self,mode):
  with tempfile.TemporaryDirectory() as d:
   D=pathlib.Path(d);sv=D/'input.sv';sv.write_bytes(b'module A(); endmodule\n');out=D/'receipt.json';scanner=hashlib.sha256((pathlib.Path(c.__file__).parent/'sv_comment_only_identity.py').read_bytes()).hexdigest()
   if mode=='missing':sv.unlink()
   with patch.object(c,'EXPECTED','a'*64),patch.object(c,'SCANNER_SHA','0'*64 if mode=='scanner' else scanner),patch.object(c,'digest',side_effect=ValueError('unterminated lexical token/comment') if mode=='syntax' else None,return_value='b'*64):r=c.check(sv,out)
   self.assertTrue(out.is_file());self.assertEqual(r['status'],'FAIL_OR_INCOMPLETE');self.assertLess(len(out.read_bytes()),8192);return r
 def test_scanner(self):self.assertEqual(self.run_case('scanner')['error_code'],'SCANNER_SOURCE_PIN_MISMATCH')
 def test_missing(self):self.assertEqual(self.run_case('missing')['exception_class'],'FileNotFoundError')
 def test_syntax(self):self.assertEqual(self.run_case('syntax')['error_code'],'unterminated lexical token/comment')
 def test_mismatch(self):
  r=self.run_case('mismatch');self.assertEqual(r['actual_normalized_sha256'],'b'*64);self.assertEqual(r['expected_normalized_sha256'],'a'*64);self.assertEqual(len(r['raw_sha256']),64)
 def test_exporter_bad_fields(self):
  with tempfile.TemporaryDirectory() as d:
   D=pathlib.Path(d);p=D/'frontend/sv_identity';p.mkdir(parents=True);(p/'sv-identity.json').write_text(json.dumps({'schema':'SV_DIRECTORY_IDENTITY_RECEIPT_V2','status':'FAIL_OR_INCOMPLETE','phase':'/private/token','error_code':'secret=abc','exception_class':'/private','raw_sha256':'notsha','counts':{'recognized_sourceinfo_comments':10**20,'secret':123}}));r=summarize(D,'a'*40)['sv_identity'];self.assertNotIn('/private',json.dumps(r));self.assertNotIn('secret',json.dumps(r));self.assertEqual(r['counts'],{});self.assertNotIn('raw_sha256',r)
 def test_module_diagnostic_exact_coverage(self):
  from module_fingerprints import fingerprints
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'m.sv';p.write_bytes(b'module A(); // @[a/A.scala 1:{2,3} 4:5]\nendmodule\n');rows=fingerprints(p);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['bytes'],p.stat().st_size);self.assertEqual(rows[0]['sourceinfo_count'],1)
   p.write_bytes(b'unknown outside module\n'+p.read_bytes())
   with self.assertRaises(ValueError):fingerprints(p)
 def test_module_line_and_name_caps(self):
  from module_fingerprints import fingerprints
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'x.sv'
   for b in [b'module A();'+b'x'*65536+b'\nendmodule\n',b'module '+b'A'*129+b'();\nendmodule\n']:
    p.write_bytes(b)
    with self.assertRaises(ValueError):fingerprints(p)
 def test_malformed_diagnostics_do_not_erase_identity(self):
  with tempfile.TemporaryDirectory() as d:
   D=pathlib.Path(d);p=D/'frontend/sv_identity';p.mkdir(parents=True)
   for bad in [[],{'status':'COMPLETE_DIAGNOSTIC_ONLY','first_differences':42}]:
    (p/'sv-identity.json').write_text(json.dumps({'schema':'SV_DIRECTORY_IDENTITY_RECEIPT_V2','status':'FAIL_OR_INCOMPLETE','counts':[],'module_diagnostics':bad}))
    r=summarize(D,'a'*40);self.assertEqual(r['sv_identity']['status'],'FAIL_OR_INCOMPLETE')
if __name__=='__main__':unittest.main()

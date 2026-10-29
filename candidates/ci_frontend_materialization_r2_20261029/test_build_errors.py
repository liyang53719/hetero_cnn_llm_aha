import pathlib,tempfile,gzip,hashlib,unittest
from build_error_samples import full_build_errors
class Test(unittest.TestCase):
 def scan(self,raw,change=False):
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d)/'log.gz';z=gzip.compress(raw);p.write_bytes(z)
   c=dict(raw_sha256=hashlib.sha256(raw).hexdigest(),compressed_sha256=hashlib.sha256(z).hexdigest(),raw_bytes=len(raw),compressed_bytes=len(z),lines=len(raw.splitlines()),error_lines=sum(x.startswith(b'%Error')for x in raw.splitlines()),pipe_eof_observed=True,gzip_finalized=True,capture_cap_hit=False)
   if change:c['lines']+=1
   return full_build_errors(dict(log_capture=c),p)
 def test_cpp_link_after_prefix(self):
  r=self.scan(b'warning\n'*1100000+b'/private/generated.cpp:5:9: error: io_token_valid missing\n/usr/bin/ld: undefined reference to `run_dut`\nmake: *** [host_link] Error 1\n')
  self.assertEqual(r['status'],'VERIFIED_COMPLETE_CAPTURE');self.assertEqual(r['matched_compiler_link_lines'],3);self.assertEqual(r['scanned_error_lines'],0);self.assertNotIn('/private',str(r));self.assertIn('io_token_valid',str(r))
 def test_census_reject(self):
  r=self.scan(b'x.cpp:1: error: failure\n',True);self.assertEqual(r['samples'],[]);self.assertEqual(r['reason'],'RAW_CENSUS_MISMATCH')
 def test_tool_failure_terminal_only(self):
  r=self.scan(b'Traceback (most recent call last):\nValueError: missing system headers\n');self.assertEqual(r['matched_compiler_link_lines'],1);self.assertEqual(len(r['samples']),1)
 def test_secret_redacted(self):
  r=self.scan(b'x.cpp:1: error: token=fixture\n');self.assertEqual(r['samples'][0]['text_status'],'REDACTED_UNSAFE')
if __name__=='__main__':unittest.main()

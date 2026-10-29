import gzip,hashlib,json,pathlib,tempfile,unittest
from verilator_errors import full_errors,sample
class Tests(unittest.TestCase):
 def run_raw(self,raw,mutate=None,corrupt=False):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'log.gz';p.write_bytes(gzip.compress(raw));c={'raw_sha256':hashlib.sha256(raw).hexdigest(),'compressed_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'raw_bytes':len(raw),'compressed_bytes':p.stat().st_size,'lines':len(raw.splitlines()),'error_lines':sum(x.startswith(b'%Error')for x in raw.splitlines()),'pipe_eof_observed':True,'gzip_finalized':True,'capture_cap_hit':False}
   if corrupt:
    p.write_bytes(p.read_bytes()[:-6]);c.update(compressed_bytes=p.stat().st_size,compressed_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
   if mutate:mutate(c)
   return full_errors({'log_capture':c},p)
 def test_beyond_prefix(self):
  raw=(b'warning x\n'*900000)+b'%Error: /private/tree/Host.sv:19: bad port\n%Error: Exiting due to 1 error(s)\n'
  r=self.run_raw(raw);self.assertEqual(r['status'],'VERIFIED_COMPLETE_CAPTURE');self.assertEqual(r['scanned_error_lines'],2);self.assertNotIn('/private',json.dumps(r));self.assertIn('Host.sv',json.dumps(r))
 def test_first_last_bound(self):
  r=self.run_raw(b''.join(b'%Error: failure '+str(i).encode()+b'\n'for i in range(20)))
  self.assertEqual(len(r['samples']),8);self.assertEqual([x['line_number']for x in r['samples']],[1,2,3,4,17,18,19,20]);self.assertTrue(r['samples_truncated'])
 def test_hash_census_reject(self):
  for mutate in [lambda c:c.update(raw_sha256='0'*64),lambda c:c.update(error_lines=2),lambda c:c.update(compressed_sha256='0'*64),lambda c:c.update(pipe_eof_observed=False)]:
   r=self.run_raw(b'%Error: bad\n',mutate);self.assertEqual(r['status'],'INCOMPLETE');self.assertEqual(r['samples'],[])
 def test_unsafe_and_unicode(self):
  self.assertEqual(sample(b'%Error: token=abc',1)['text_status'],'REDACTED_UNSAFE')
  r=self.run_raw((''.join('%Error: '+'字'*500+'\n'for _ in range(12))).encode());self.assertEqual(r['status'],'VERIFIED_COMPLETE_CAPTURE');self.assertLessEqual(len(json.dumps(r['samples'],ensure_ascii=True).encode()),4096)
 def test_final_line_no_newline(self):
  self.assertEqual(self.run_raw(b'%Error: bad')['status'],'VERIFIED_COMPLETE_CAPTURE')
 def test_long_line_fail(self):
  r=self.run_raw(b'%Error: '+b'a'*1048576+b'\n');self.assertEqual(r['reason'],'LINE_BOUND');self.assertEqual(r['samples'],[])
 def test_corrupt_gzip(self):
  r=self.run_raw(b'%Error: bad\n',corrupt=True);self.assertEqual(r['reason'],'UNREADABLE_CAPTURE');self.assertEqual(r['samples'],[])
 def test_token_signal_preserved(self):
  r=self.run_raw(b'%Error: io_token_valid tokenWrite io_token=bad port\n');self.assertIn('io_token_valid',r['samples'][0]['error_text']);self.assertIn('tokenWrite',r['samples'][0]['error_text'])
 def test_missing(self):
  self.assertEqual(full_errors({},'/missing')['status'],'INCOMPLETE')
if __name__=='__main__':unittest.main()

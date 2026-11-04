"""Source-only finite diagnostics tests. No DUT, compiler, weights or network."""
import gzip,hashlib,importlib.util,json,pathlib,sys,tempfile,unittest
P=pathlib.Path;HERE=P(__file__).resolve().parent;REPO=P(sys.argv.pop(1)).resolve()if len(sys.argv)>1 and not sys.argv[1].startswith('-')else HERE.parents[1]
N=REPO/'candidates/gdn32_first_model_execution_20261104/numeric';sys.path.insert(0,str(N))
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
c=load(N/'consumer_owned.py','tested_consumer');d=load(HERE/'safe_phase_diagnostics.py','tested_diagnostics')
class DiagnosticsTests(unittest.TestCase):
 def event(self):
  c.execution_phase('DUT_CAPTURE');return c.execution_failure(TimeoutError('PRIVATE_NOT_TO_PROJECT'))
 def test_fixed_timeout_class(self):
  e=self.event();self.assertEqual(d.project_line(json.dumps(e).encode()),dict(sorted(e.items())));self.assertNotIn('PRIVATE_NOT_TO_PROJECT',json.dumps(e));self.assertFalse(e['numerical_pass']);self.assertIsNone(e['dut_started'])
 def test_negative_event_fields(self):
  for key,value in [('phase','UNKNOWN'),('exception_class','UNKNOWN'),('native_started',True),('dut_started',True),('numerical_pass',True),('code','BAD'),('stage','PASSED')]:
   with self.subTest(key=key):e=self.event();e[key]=value;self.assertIsNone(d.project_line(json.dumps(e).encode()))
 def test_schema_emitter_catalog_connection_pins(self):
  self.assertEqual(sha(HERE/'EXECUTION_SCHEMA.json'),d.EXECUTION_SCHEMA_SHA256)
  self.assertEqual(sha(N/'consumer_owned.py'),d.EXECUTION_EMITTER_SOURCE_PINS['consumer_owned.py'])
  schema=json.loads((HERE/'EXECUTION_SCHEMA.json').read_text());self.assertEqual(schema['components']['CONSUMER_OWNED'],list(c._EXECUTION_PHASES));self.assertEqual(schema['classes'],list(c._EXECUTION_CLASSES))
  rows=json.loads((N.parent/'GDN32_FULL_SOURCE_PINS.json').read_text())['files'];self.assertEqual(len(rows),1211)
  for row in rows:self.assertEqual(sha(REPO/row['path']),row['sha256']);self.assertEqual((REPO/row['path']).stat().st_size,row['bytes'])
  for rel,digest in json.loads((N/'CONNECTION_OWNED_SOURCE_PINS.json').read_text()).items():self.assertEqual(sha((N/rel).resolve()),digest)
 def test_complete_outer_capture_and_refusals(self):
  with tempfile.TemporaryDirectory()as tmp:
   work=P(tmp);stage=work/'materials/numeric/runs/p1_dut';stage.mkdir(parents=True);raw=(json.dumps(self.event())+'\n').encode();blob=gzip.compress(raw,mtime=0);(stage/'frontend.log.gz').write_bytes(blob)
   base=dict(native_exit=2,worker_started=True,cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'),log_capture=dict(format='gzip-lossless',pipe_eof_observed=True,gzip_finalized=True,capture_cap_hit=False,compressed_bytes=len(blob),raw_bytes=len(raw),compressed_sha256=hashlib.sha256(blob).hexdigest(),raw_sha256=hashlib.sha256(raw).hexdigest()))
   for name,mutate in [('valid',lambda r:None),('no_cleanup',lambda r:r['cleanup_proof'].update(status='INCOMPLETE')),('wrong_raw_hash',lambda r:r['log_capture'].update(raw_sha256='0'*64)),('false_native_success',lambda r:r.update(native_exit=0)),('gzip_not_final',lambda r:r['log_capture'].update(gzip_finalized=False))]:
    with self.subTest(case=name):
     r=json.loads(json.dumps(base));mutate(r);(stage/'RESULT.json').write_text(json.dumps(r));result=d.capture(work,'p1_dut',1);self.assertEqual(result['status'],'OBSERVED'if name=='valid'else'REFUSED');self.assertFalse(result['numerical_pass'])
if __name__=='__main__':unittest.main(verbosity=2)

import json,os,pathlib,subprocess,tempfile,unittest
from unittest.mock import patch
import diagnose_runner_jdk as j
class Tests(unittest.TestCase):
 def test_original_then_secondary_only_on_failure(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);h=p/'jdk';h.mkdir();(h/'release').write_text('JAVA_VERSION="21.0.13"\nIMPLEMENTOR="Eclipse Adoptium"\nSECRET="do_not_export"\n')
   with patch.dict(os.environ,{'JAVA_HOME_21_X64':str(h)}),patch.object(j,'probe',side_effect=[{'native_exit':1},{'native_exit':0}]) as probe:
    r=j.diagnose(p/'out');self.assertEqual(probe.call_count,2);self.assertEqual(probe.call_args_list[0].args[1],[]);self.assertEqual(r['root_cause'],'NOT_ESTABLISHED');self.assertNotIn('SECRET',json.dumps(r))
 def test_plain_success_no_secondary(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);h=p/'jdk';h.mkdir();(h/'release').write_text('')
   with patch.dict(os.environ,{'JAVA_HOME_21_X64':str(h)}),patch.object(j,'probe',return_value={'native_exit':0}) as probe:
    r=j.diagnose(p/'out');self.assertEqual(probe.call_count,1);self.assertEqual(r['phase'],'diagnostics_complete')
 def test_timeout_records_bounded_output(self):
  with patch.object(subprocess,'run',side_effect=subprocess.TimeoutExpired(['java'],20,output=b'x'*70000,stderr=b'timeout')):
   r=j.probe(pathlib.Path('/java'),[],pathlib.Path('/tmp'));self.assertTrue(r['timeout']);self.assertEqual(len(r['stdout']),0);self.assertEqual(r['per_output_file_limit_bytes'],65536)
if __name__=='__main__':unittest.main()

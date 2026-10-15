import contextlib,hashlib,io,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from candidates.qwen2_fullblock_ci_execution import bootstrap as b,closure
class BootstrapTests(unittest.TestCase):
    def test_default_no_actions(self):
        with patch('sys.argv',['bootstrap']),patch.object(b,'pins',side_effect=AssertionError('must not run')),contextlib.redirect_stdout(io.StringIO()) as o:
            self.assertEqual(b.main(),0);self.assertEqual(o.getvalue(),'NOT_EXECUTED\n')
    def test_failure_redacted(self):
        with patch('sys.argv',['bootstrap','--capture']),patch.object(b,'capture',side_effect=ValueError('private tensor hash')),contextlib.redirect_stdout(io.StringIO()) as o:
            self.assertEqual(b.main(),1);self.assertNotIn('private',o.getvalue())
    def test_certificate_bytes_checked(self):
        with patch.object(b,'pins',return_value=('a'*64,'b'*64)),patch.object(b,'external_authorization',return_value=({},b'wrong')):
            with self.assertRaisesRegex(ValueError,'certificate bytes'):b.admit()
    def test_actual_closure_sources_only(self):
        m=closure.source_manifest();self.assertTrue(m);self.assertTrue(all(not n.startswith('work/') for n in m));self.assertEqual(len(closure.digest()),64)
    def test_admit_fresh_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'certificate';raw=b'fixture';sha=hashlib.sha256(raw).hexdigest()
            with patch.object(b,'pins',return_value=(sha,'b'*64)),patch.object(b,'external_authorization',return_value=({},raw)),patch.object(b.inputs,'safe_path',return_value=p),patch.object(b,'call') as call:
                self.assertEqual(b.admit(),'BOOTSTRAP_SOURCE_POLICY_ADMITTED');self.assertEqual(p.read_bytes(),raw)
                self.assertEqual(call.call_args.args[0],'issuer.py');self.assertEqual(call.call_args.args[1][0],'--validate-only')
                with self.assertRaises(FileExistsError):b.admit()
    def test_external_schema_and_hash(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/b.AUTH;folder.mkdir(parents=True)
            cert=folder/'SOURCE_CERTIFICATE.json';cert.write_bytes(b'certificate-fixture')
            pin=folder/'EXTERNAL_PINS.json'
            values={'schema':1,'certificate_sha256':hashlib.sha256(cert.read_bytes()).hexdigest(),'source_closure_sha256':'b'*64}
            pin.write_text(json.dumps(values))
            with patch.object(b,'ROOT',root):
                self.assertEqual(b.external_authorization()[0],values)
                values['unexpected']='metadata';pin.write_text(json.dumps(values))
                with self.assertRaisesRegex(ValueError,'schema'):b.external_authorization()
                del values['unexpected'];pin.write_text(json.dumps(values));cert.write_bytes(b'drift')
                with self.assertRaisesRegex(ValueError,'bytes drift'):b.external_authorization()
if __name__=='__main__':unittest.main()

import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B before any project source read')
import hashlib
from pathlib import Path
import types
import unittest
from unittest import mock
HERE=Path(__file__).absolute().parent
SOURCE=HERE/'ci_toolchain.py'
RAW=SOURCE.read_bytes()
if len(RAW)!=32715 or hashlib.sha256(RAW).hexdigest()!='fcec5c2d6917cdfe460ff01d8a922500497971459d4269aabdbf3610e43f9b2d':
    raise ValueError('fixed module identity before compile')
g=types.ModuleType('verified_transport_only');g.__file__=str(SOURCE)
exec(compile(RAW,str(SOURCE),'exec',dont_inherit=True),g.__dict__)

class Cold(unittest.TestCase):
    def test_exact_allowlist_acquisition_only(self):
        values={key:'https://fixed.invalid/value/'+str(i) for i,key in enumerate(g.TRANSPORT_KEYS)}
        values['no_proxy']=''
        with mock.patch.dict(g.os.environ,values,clear=True):
            for name in g.ACQUISITION_PHASES:
                self.assertEqual(g.phase_environment(name,{'PATH':'/usr/bin:/bin'}),{'PATH':'/usr/bin:/bin',**values})
    def test_native_remains_clean(self):
        with mock.patch.dict(g.os.environ,{key:'private fixture' for key in g.TRANSPORT_KEYS},clear=True):
            for name in ('fresh_configure','fresh_make','derived_tiny_run','class','sv','java_version'):
                self.assertEqual(g.phase_environment(name,{'PATH':'/usr/bin:/bin'}),{'PATH':'/usr/bin:/bin'})
    def test_no_credentials_or_unlisted_env_copied(self):
        with mock.patch.dict(g.os.environ,{'GITHUB_TOKEN':'never-copy','OTHER_SECRET':'never-copy','HTTPS_PROXY':'as-is'},clear=True):
            self.assertEqual(g.phase_environment(g.ACQUISITION_PHASES[0],{}),{'HTTPS_PROXY':'as-is'})
    def test_absent_transport_not_synthesized(self):
        with mock.patch.dict(g.os.environ,{},clear=True):
            self.assertEqual(g.phase_environment(g.ACQUISITION_PHASES[0],{'PATH':'/usr/bin:/bin'}),{'PATH':'/usr/bin:/bin'})
    def test_base_environment_not_mutated(self):
        base={'PATH':'/usr/bin:/bin'}
        with mock.patch.dict(g.os.environ,{'HTTPS_PROXY':'fixture'},clear=True):
            actual=g.phase_environment(g.ACQUISITION_PHASES[0],base)
            self.assertIsNot(base,actual)
            self.assertEqual(base,{'PATH':'/usr/bin:/bin'})
    def test_transport_case_and_empty_values_preserved(self):
        values={'HTTPS_PROXY':'UPPER','https_proxy':'lower','NO_PROXY':'','SSL_CERT_FILE':'relative-ca'}
        with mock.patch.dict(g.os.environ,values,clear=True):
            self.assertEqual(g.phase_environment(g.ACQUISITION_PHASES[0],{}),values)
    def test_named_nonacquisition_cannot_request_transport(self):
        with mock.patch.dict(g.os.environ,{'HTTPS_PROXY':'fixture'},clear=True):
            self.assertEqual(g.phase_environment('arbitrary_acquisition',{}),{})

if __name__=='__main__':unittest.main(verbosity=2)

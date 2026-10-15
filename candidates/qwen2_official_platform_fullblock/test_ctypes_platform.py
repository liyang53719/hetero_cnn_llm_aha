"""Exact public stdlib bytes/path checks; compile only, never execute a fixture."""
import contextlib
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import gates as g

HERE=Path(__file__).resolve().parent
OFFICIAL=(HERE/'fixtures/cpython_3_12_14_ctypes.txt').read_bytes()
EVIDENCE=json.loads((HERE/'STDLIB_SOURCE_EVIDENCE.json').read_bytes())
PATCH=EVIDENCE['exact_legacy_to_official_replacement']
LEGACY=OFFICIAL.replace(PATCH['after'].encode(),PATCH['before'].encode())


class CtypesPlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)/'fixed-python'
        self.path=self.home/'lib/python3.12/ctypes/__init__.py'
        self.path.parent.mkdir(parents=True);self.path.write_bytes(OFFICIAL)

    @contextlib.contextmanager
    def installed(self,**kwargs):
        # Only installation-location/module metadata is synthetic. The file
        # bytes and production expected hash/size are the actual official source.
        with patch.object(g,'CTYPES_PYTHON_HOME',self.home),patch.object(g,'CTYPES_SOURCE',self.path), \
             patch.object(g.sys,'base_prefix',kwargs.get('prefix',str(self.home))), \
             patch.object(g.ctypes,'__file__',kwargs.get('file',str(self.path))), \
             patch.object(g.ctypes.__spec__,'origin',kwargs.get('origin',str(self.path))), \
             patch.object(g.ctypes,'__path__',[str(self.path.parent)]):yield

    def test_exact_public_source_evidence_and_fixed_ci_paths(self):
        self.assertEqual(str(g.CTYPES_PYTHON_HOME),'/opt/hostedtoolcache/Python/3.12.14/x64')
        self.assertEqual(str(g.CTYPES_SOURCE),'/opt/hostedtoolcache/Python/3.12.14/x64/lib/python3.12/ctypes/__init__.py')
        self.assertEqual(len(OFFICIAL),g.CTYPES_SOURCE_BYTES)
        self.assertEqual(hashlib.sha256(OFFICIAL).hexdigest(),g.CTYPES_SOURCE_SHA256)
        self.assertEqual(EVIDENCE['ctypes'],dict(bytes=len(OFFICIAL),sha256=g.CTYPES_SOURCE_SHA256))
        self.assertEqual(EVIDENCE['legacy_ctypes'],dict(bytes=len(LEGACY),sha256=g.v2.pins()['ctypes_runtime']['sha256']))
        self.assertEqual(LEGACY.count(PATCH['before'].encode()),1)
        self.assertEqual(LEGACY.replace(PATCH['before'].encode(),PATCH['after'].encode()),OFFICIAL)
        self.assertFalse(EVIDENCE['ci_installed_source_observed'])
        self.assertEqual(EVIDENCE['shutil']['sha256'],g.SHUTIL_SOURCE_SHA256)
        license=(HERE/EVIDENCE['license']['file']).read_bytes()
        self.assertEqual(len(license),EVIDENCE['license']['bytes'])
        self.assertEqual(hashlib.sha256(license).hexdigest(),EVIDENCE['license']['sha256'])

    def test_exact_official_source_accepted(self):
        with self.installed():self.assertEqual(g._ctypes_runtime_source(),(self.path,OFFICIAL))

    def test_old_local_patch_refused_even_at_exact_platform_path(self):
        self.path.write_bytes(LEGACY)
        with self.installed(),self.assertRaisesRegex(ValueError,'full source identity'):g._ctypes_runtime_source()

    def test_fullfile_tamper_outside_three_methods_refused(self):
        self.path.write_bytes(OFFICIAL.replace(b'create and manipulate',b'Create and manipulate',1))
        with self.installed(),self.assertRaisesRegex(ValueError,'full source identity'):g._ctypes_runtime_source()

    def test_wrong_python_root_refused(self):
        with self.installed(prefix=str(self.home.parent)),self.assertRaisesRegex(ValueError,'Python root'):g._ctypes_runtime_source()

    def test_wrong_loaded_module_path_and_spec_refused(self):
        for kwargs in ({'file':str(self.path.parent/'other.py')},{'origin':str(self.path.parent/'other.py')}):
            with self.installed(**kwargs),self.assertRaisesRegex(ValueError,'loaded ctypes source path'):g._ctypes_runtime_source()

    def test_alias_refused_even_with_exact_hash(self):
        real=self.path.with_suffix('.real');self.path.rename(real);self.path.symlink_to(real)
        with self.installed(),self.assertRaisesRegex(ValueError,'aliased path'):g._ctypes_runtime_source()

    def test_three_frame_code_objects_unchanged_both_optimizations(self):
        filename=str(g.CTYPES_SOURCE)
        for optimize in (0,1):
            old=g.v2.code_in(compile(LEGACY,filename,'exec',dont_inherit=True,optimize=optimize),'CDLL')
            new=g.v2.code_in(compile(OFFICIAL,filename,'exec',dont_inherit=True,optimize=optimize),'CDLL')
            for name in ('__init__','__getattr__','__getitem__'):
                self.assertEqual(g.v2.code_in(old,name),g.v2.code_in(new,name))
        self.assertIs(g.OracleGate._ctypes_frame,g.v2.OracleGate._ctypes_frame)
        self.assertIs(g.OracleGate._original_environment_frames,g.v2.OracleGate._original_environment_frames)

if __name__=='__main__':unittest.main()

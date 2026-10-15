"""Cold mocks only: no NumPy/YAML import, frozen execution or arithmetic."""
import contextlib
import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from candidates.qwen2_fullblock_ci_dut import runtime_adapter as a

class AdapterTests(unittest.TestCase):
    @contextlib.contextmanager
    def environment(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
            root=Path(tmp);package=root/'work/runtime_recovery/site-packages'
            helper_path=root/'candidates/qwen2_resident_matrix/ffn_public/check_numeric.py'
            helper_path.parent.mkdir(parents=True);helper_path.write_bytes(b'cold helper fixture')
            modules={};pins={}
            for name in ('numpy','yaml'):
                path=package/name/'__init__.py';path.parent.mkdir(parents=True)
                data=('cold '+name).encode();path.write_bytes(data);pins[name]=hashlib.sha256(data).hexdigest()
                spec=SimpleNamespace(origin=str(path),submodule_search_locations=[str(path.parent)])
                modules[name]=SimpleNamespace(__file__=str(path),__path__=[str(path.parent)],__spec__=spec)
            original=Mock(side_effect=lambda filename:('ORIGINAL',filename))
            helper=SimpleNamespace(__file__=str(helper_path),ROOT=root,repository_source_path=original)
            stack.enter_context(patch.multiple(a,ROOT=root,CI_ROOT=root,PACKAGE_ROOT=package,PINS=pins,
                HELPER_PATH=helper_path,HELPER_SHA=hashlib.sha256(helper_path.read_bytes()).hexdigest(),
                _MODULES=None,_CLASSIFIER=None,_ORIGINAL=None))
            stack.enter_context(patch.dict(a.sys.modules,modules))
            finder=stack.enter_context(patch.object(a.importlib.util,'find_spec',side_effect=lambda name:modules[name].__spec__))
            importer=stack.enter_context(patch.object(a.importlib,'import_module',side_effect=lambda name:helper if name==a.HELPER else modules[name]))
            yield root,package,modules,helper,original,finder,importer
    def test_only_two_exact_root_strings_exempt(self):
        with self.environment() as (root,package,modules,helper,original,_,importer):
            np,yaml=a.initialize();self.assertIs(np,modules['numpy']);self.assertIs(yaml,modules['yaml'])
            for name in modules:self.assertIsNone(helper.repository_source_path(str(package/name/'__init__.py')))
            original.assert_not_called()
            for path in (package/'fakepkg/__init__.py',package/'numpy/core.py',root/'scripts/source.py',
                         package/'numpy/__init__.py'):
                # Path object does not get the exact-string exemption either.
                value=path if path.name=='__init__.py' and path.parent.name=='numpy' else str(path)
                self.assertEqual(helper.repository_source_path(value),('ORIGINAL',value))
            alias=str(package/'numpy')+'/./__init__.py'
            self.assertEqual(helper.repository_source_path(alias),('ORIGINAL',alias))
            self.assertEqual([c.args[0] for c in importer.call_args_list],['numpy','yaml',a.HELPER])
    def test_repeated_initialize_is_idempotent_and_verifies(self):
        with self.environment() as (_,package,modules,helper,*rest):
            first=a.initialize();wrapper=helper.repository_source_path
            self.assertEqual(a.initialize(),first);self.assertIs(helper.repository_source_path,wrapper)
            (package/'numpy/__init__.py').write_bytes(b'drift')
            with self.assertRaisesRegex(ValueError,'identity drift'):a.initialize()
    def test_wrapper_rechecks_hash(self):
        with self.environment() as (_,package,modules,helper,*rest):
            a.initialize();path=package/'yaml/__init__.py';path.write_bytes(b'drift')
            with self.assertRaisesRegex(ValueError,'identity drift'):helper.repository_source_path(str(path))
    def test_wrong_spec_origin_or_search_path_rejected_before_import(self):
        for field,value in [('origin','/tmp/foreign'),('submodule_search_locations',['/tmp/foreign'])]:
            with self.environment() as (_,_,modules,helper,_,_,importer):
                setattr(modules['numpy'].__spec__,field,value)
                with self.assertRaises(ValueError):a.initialize()
                importer.assert_not_called()
    def test_loaded_origin_rejected(self):
        with self.environment() as (_,_,modules,*rest):
            modules['yaml'].__file__='/tmp/foreign'
            with self.assertRaisesRegex(ValueError,'loaded fixed'):a.initialize()
    def test_classifier_replacement_rejected(self):
        with self.environment() as (_,_,_,helper,*rest):
            a.initialize();helper.repository_source_path=lambda x:None
            with self.assertRaisesRegex(ValueError,'classifier replaced'):a.initialize()
    def test_helper_source_drift_rejected(self):
        with self.environment() as _:
            a.HELPER_PATH.write_bytes(b'drift')
            with self.assertRaisesRegex(ValueError,'identity drift'):a.initialize()
    def test_symlink_root_rejected(self):
        with self.environment() as (_,package,*rest):
            p=package/'numpy/__init__.py';target=p.with_name('real.py');p.rename(target);p.symlink_to(target)
            with self.assertRaisesRegex(ValueError,'alias'):a.initialize()
    def test_delegation_preserves_exception(self):
        with self.environment() as (_,_,_,helper,original,*rest):
            a.initialize();error=RuntimeError('original');original.side_effect=error
            with self.assertRaises(RuntimeError) as got:helper.repository_source_path('repo.py')
            self.assertIs(got.exception,error)
    def test_wrong_workspace_no_import(self):
        with patch.object(a,'ROOT',Path('/wrong')),patch.object(a.importlib,'import_module') as importer:
            with self.assertRaisesRegex(ValueError,'workspace'):a.initialize()
            importer.assert_not_called()

if __name__=='__main__':unittest.main()

"""Cold synthetic/metadata tests; no native imports, raw data, or model execution."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

import runtime as A


class RuntimeRelocationTests(unittest.TestCase):
    def setUp(self):
        self.pins = A.load_original('full29')
        self.moved = copy.deepcopy(self.pins)
        self.moved['capture_environment']['PYTHONPATH'] = A.NEW_PYTHONPATH
        self.identities = {}
        for pin in self.pins['runtime_native_files'].values():
            path = Path(pin['path'])
            self.identities[path if path.is_absolute() else A.ROOT/path] = {k:pin[k] for k in ('bytes','sha256')}

    def fake_identity(self, path):
        return copy.deepcopy(self.identities[path])

    def test_exact_relocation_for_both_contracts_preserves_input(self):
        for family in A.SOURCES:
            original = A.load_original(family)
            before = copy.deepcopy(original)
            with mock.patch.object(A,'identity',side_effect=self.fake_identity) as read:
                moved = A.relocate_runtime(original,family=family)
            self.assertEqual(read.call_count,6)
            self.assertEqual(original,before)
            self.assertEqual(moved['capture_environment']['PYTHONPATH'],A.NEW_PYTHONPATH)
            moved['capture_environment']['PYTHONPATH'] = A.OLD_PYTHONPATH
            self.assertTrue(A.same(moved,original))

    def test_any_unreviewed_pin_change_rejected_before_native_read(self):
        changes = [
            lambda p:p['runtime_native_files']['torch_C'].__setitem__('path','/tmp/torch.so'),
            lambda p:p['runtime_native_files']['torch_C'].__setitem__('sha256','0'*64),
            lambda p:p['runtime_native_files']['torch_C'].__setitem__('bytes',True),
            lambda p:p['runtime_requirements'].__setitem__('torch','2.10.1+cpu'),
            lambda p:p['contract'].__setitem__('rows',16),
            lambda p:p['capture_environment'].__setitem__('PYTHONPATH',A.NEW_PYTHONPATH),
            lambda p:p['capture_environment'].__setitem__('OMP_NUM_THREADS','1'),
        ]
        for change in changes:
            pins = copy.deepcopy(self.pins)
            change(pins)
            with mock.patch.object(A,'identity') as read:
                with self.assertRaises(A.Rejected): A.relocate_runtime(pins,family='full29')
                read.assert_not_called()

    def test_native_mismatch_rejected(self):
        for wrong in ({'bytes':1,'sha256':'0'*64}, {'bytes':True,'sha256':'0'*64}):
            with mock.patch.object(A,'identity',return_value=wrong):
                with self.assertRaises(A.Rejected): A.check_native(self.moved,family='full29')

    def test_arbitrary_new_prefix_rejected(self):
        for path in ('/tmp/site-packages',A.NEW_PYTHONPATH+':/tmp',A.OLD_PYTHONPATH,A.NEW_PYTHONPATH+'/../site-packages'):
            moved = copy.deepcopy(self.moved)
            moved['capture_environment']['PYTHONPATH'] = path
            with mock.patch.object(A,'identity') as read:
                with self.assertRaises(A.Rejected): A.check_native(moved,family='full29')
                read.assert_not_called()

    def test_unknown_family_rejected_without_read(self):
        with mock.patch.object(Path,'read_bytes') as read:
            for family in ('other','../qkv',False,None):
                with self.assertRaises(A.Rejected): A.load_original(family)
            read.assert_not_called()

    def test_original_source_drift_rejected(self):
        with mock.patch.object(Path,'read_bytes',return_value=b'changed source'):
            with self.assertRaises(A.Rejected): A.load_original('qkv')

    def test_preimported_numeric_package_rejected(self):
        for name in ('torch','numpy','transformers','torch.fake'):
            with mock.patch.dict(sys.modules,{name:types.ModuleType(name)}), mock.patch.object(A,'identity') as read:
                with self.assertRaises(A.Rejected): A.initialize_runtime('full29')
                read.assert_not_called()

    def test_symlink_refused(self):
        with mock.patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaises(A.Rejected): A.regular(Path('/tmp/fake'))

    def test_z_default_has_no_work_native_write_or_numeric_activity(self):
        def audit(event,args):
            if event == 'open':
                path,mode,flags = args
                if isinstance(path,(str,bytes)):
                    value = str(path)
                    if '/work/' in value or (isinstance(mode,str) and any(m in mode for m in 'wax+')):
                        raise AssertionError('cold forbidden open: '+value)
            if event == 'import' and args[0].split('.')[0] in ('torch','numpy','transformers'):
                raise AssertionError('cold numeric import')
            if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.fork','os.exec'):
                raise AssertionError('cold external action')
        sys.addaudithook(audit)
        for family in A.SOURCES:
            out = io.StringIO()
            with contextlib.redirect_stdout(out): A.main(['--family',family])
            value = json.loads(out.getvalue())
            self.assertEqual(value['status'],'NOT_EXECUTED_SOURCE_CHECK_PASS')
            self.assertFalse(value['native_read'])
            self.assertFalse(value['raw_read'])


if __name__ == '__main__':
    unittest.main()

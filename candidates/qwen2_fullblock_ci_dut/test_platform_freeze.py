"""Cold maps/metadata mocks and tiny temporary bytes; never initializes runtime."""
from contextlib import ExitStack
import copy
import hashlib
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from candidates.qwen2_fullblock_ci_dut import platform_freeze as P


def maps(path=None, inode=42, device='08:01', perms='r-xp'):
    return f'1000-2000 {perms} 00001000 {device} {inode} {path or P.LIBPYTHON}\n'


class FreezeTests(unittest.TestCase):
    def setup_live(self, stack):
        executable = P.PYTHON_HOME/'bin/python3.12'
        python = dict(path=str(executable),device=os.makedev(8,1),inode=41,**P.PYTHON_IDENTITY)
        library = dict(path=str(P.LIBPYTHON),device=os.makedev(8,1),inode=42,bytes=73,sha256='a'*64)
        loc = stack.enter_context(patch.object(P,'location',return_value=executable))
        read = stack.enter_context(patch.object(P,'read_maps',return_value=maps()))
        identify = stack.enter_context(patch.object(P,'identity',side_effect=lambda path:copy.deepcopy(python if path==executable else library)))
        return python,library,read,identify,loc

    def test_default_no_io(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('read')), \
             patch.object(Path,'resolve',side_effect=AssertionError('resolve')), \
             patch.object(P,'read_maps',side_effect=AssertionError('maps')), \
             patch.object(P,'identity',side_effect=AssertionError('native read')):
            self.assertEqual(P.observe(),dict(status='NOT_EXECUTED',numeric_execution_allowed=False))
            for value in (1,None,'yes'):
                with self.assertRaises(ValueError):P.observe(execute=value)

    def test_valid_mapping_multiple_segments(self):
        self.assertEqual(P.mapped_libpython(maps()+maps(perms='rw-p')),
                         dict(device=os.makedev(8,1),inode=42))

    def test_missing_deleted_second_alias_mappings_rejected(self):
        for text in ('',maps(perms='rw-p'),maps(path=str(P.LIBPYTHON)+' (deleted)'),
                     maps(path=str(P.LIBPYTHON.parent)+'/../lib/libpython3.12.so.1.0'),
                     maps()+maps(path='/other/libpython3.12.so.1.0'),
                     maps()+maps(path=str(P.PYTHON_HOME/'lib/libpython3.13.so.1.0')),
                     maps()+maps(inode=43),maps(inode=0),maps(device='bad'),maps(perms='xxxx'),
                     maps().replace('1000-2000','2000-1000')):
            with self.subTest(text=text),self.assertRaises(ValueError):P.mapped_libpython(text)

    def test_real_tiny_file_stream_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'library';path.write_bytes(b'cold-test-bytes')
            result=P.identity(path);actual=path.stat()
            self.assertEqual(result,dict(path=str(path),bytes=15,sha256=hashlib.sha256(b'cold-test-bytes').hexdigest(),
                                         device=actual.st_dev,inode=actual.st_ino))
            alias=Path(directory)/'alias';alias.symlink_to(path)
            with self.assertRaisesRegex(ValueError,'canonical'):P.identity(alias)
            with self.assertRaisesRegex(ValueError,'regular'):P.identity(Path(directory))

    def test_stat_drift_during_hash_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'library';path.write_bytes(b'cold')
            original=path.stat()
            changed=types.SimpleNamespace(**{k:getattr(original,k) for k in (*P.STAT_KEYS,'st_mode')})
            changed.st_ino+=1
            with patch.object(P.os,'fstat',side_effect=[original,changed]),self.assertRaisesRegex(ValueError,'changed during'):
                P.identity(path)
            with patch.object(P.os,'fstat',return_value=changed),self.assertRaisesRegex(ValueError,'changed before'):
                P.identity(path)

    def test_fresh_observation_and_verify_same(self):
        with ExitStack() as stack:
            python,library,read,identify,_=self.setup_live(stack)
            fresh=P.observe(execute=True)
            self.assertEqual(fresh['python'],python)
            self.assertEqual(fresh['libpython'],library)
            self.assertFalse(fresh['independently_reviewed'])
            self.assertFalse(fresh['historical_equivalence_claimed'])
            self.assertFalse(fresh['full_system_closure'])
            self.assertFalse(fresh['numeric_execution_allowed'])
            self.assertEqual(read.call_count,2)
            self.assertEqual(identify.call_count,4)
            same=P.verify_same(fresh)
            self.assertEqual(same,fresh)
            self.assertIsNot(same,fresh)

    def test_unexpected_python_or_mapped_file_identity_rejected(self):
        for field,value in (('sha256','0'*64),('bytes',True)):
            with ExitStack() as stack:
                python,_,_,_,_=self.setup_live(stack);python[field]=value
                with self.assertRaisesRegex(ValueError,'Python ELF drift'):P.observe(execute=True)
        for field,value in (('device',os.makedev(9,1)),('inode',99)):
            with ExitStack() as stack:
                _,library,_,_,_=self.setup_live(stack);library[field]=value
                with self.assertRaisesRegex(ValueError,'stat identity mismatch'):P.observe(execute=True)

    def test_maps_and_libpython_bytes_drift_during_observe(self):
        with ExitStack() as stack:
            _,_,read,_,_=self.setup_live(stack);read.side_effect=[maps(),maps(inode=99)]
            with self.assertRaisesRegex(ValueError,'maps changed'):P.observe(execute=True)
        with ExitStack() as stack:
            python,library,_,identity,_=self.setup_live(stack)
            changed=copy.deepcopy(library);changed['sha256']='b'*64
            identity.side_effect=[python,library,changed]
            with self.assertRaisesRegex(ValueError,'libpython changed'):P.observe(execute=True)

    def test_verify_rejects_other_run_or_changed_library(self):
        with ExitStack() as stack:
            _,library,_,_,_=self.setup_live(stack)
            frozen=P.observe(execute=True)
            library['sha256']='b'*64
            with self.assertRaisesRegex(ValueError,'freeze drift'):P.verify_same(frozen)
        with ExitStack() as stack:
            self.setup_live(stack);frozen=P.observe(execute=True);frozen['process_id']+=1
            with self.assertRaisesRegex(ValueError,'freeze drift'):P.verify_same(frozen)
        for frozen in (None,{},P.observe()):
            with self.assertRaisesRegex(ValueError,'executed local'):P.verify_same(frozen)

    def test_wrong_root_fails_before_native_or_maps_read(self):
        with patch.object(P,'ROOT',Path('/tmp/not-ci')),patch.object(P,'read_maps',side_effect=AssertionError('maps')):
            with self.assertRaisesRegex(ValueError,'fixed CI'):P.observe(execute=True)


if __name__=='__main__':unittest.main()

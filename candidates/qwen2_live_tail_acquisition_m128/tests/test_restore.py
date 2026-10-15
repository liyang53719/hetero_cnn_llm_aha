import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

p=Path(__file__).resolve().parents[1]/'restore.py'
s=importlib.util.spec_from_file_location('per_segment_restore',p)
r=importlib.util.module_from_spec(s);s.loader.exec_module(r)


class RestoreTests(unittest.TestCase):
    def test_default_cold(self):
        with patch.object(r.a,'download',side_effect=AssertionError('network')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(r.main([])['status'],'NOT_EXECUTED')

    def test_segment_bounds_before_network(self):
        for value in (-1,0,1,14,True):
            with self.subTest(value=value),patch.object(r,'state_read',return_value=(Path('/tmp'),{})),\
                 patch.object(r.a,'download',side_effect=AssertionError('network')):
                with self.assertRaises(ValueError):r.fetch('ignored',value,{}, {})

    def test_missing_flags_before_contract(self):
        args_list=[['--action','init','--execute','--out','abc'],
            ['--action','segment','--execute','--download','--out','abc'],
            ['--action','segment','--execute','--out','abc','--index','2'],
            ['--action','audit','--execute','--out','abc','--download']]
        with patch.object(r.a,'load_contract',side_effect=AssertionError('contract')):
            for args in args_list:
                with self.subTest(args=args),self.assertRaises(ValueError):r.main(args)

    def test_child_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'work';out.mkdir();(out/'data').symlink_to('/tmp')
            with patch.object(r,'ROOT',root),self.assertRaises(ValueError):r.child(out,'data/receipt')

    def test_actual_fixed_segment_map(self):
        _,pins=r.a.load_contract();flat=r.segments(pins)
        self.assertEqual(len(flat),14)
        self.assertEqual([t['role'] for t,s in flat[:2]],['wo','gamma1'])
        self.assertEqual(sum(s['bytes'] for t,s in flat[2:]),82575360)
        self.assertEqual([t['role'] for t,s in flat[2:]],['wg']*4+['wu']*4+['wd']*4)

    def test_existing_init_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);relative=r.PREFIX+'/r/raw';(root/relative).mkdir(parents=True)
            with patch.object(r,'ROOT',root),self.assertRaises(ValueError):r.initialize(relative,'unused',{}, {})


if __name__=='__main__':unittest.main()

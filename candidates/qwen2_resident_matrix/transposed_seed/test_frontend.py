"""Frozen composition/source contracts. Does not run a compiler or emit RTL."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('prefix_frontend_check',HERE/'check_frontend.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)


class SourceCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        work=check.ROOT/'work/qwen2_transposed_seed_20261011';work.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(prefix='source_test_',dir=work)
        cls.out=Path(cls.temp.name)
        cls.paths,cls.pins=check.compose(cls.out)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_frozen_source_patch_and_postimage_pins(self):
        self.assertEqual(self.pins,json.loads((HERE/'source_pins.json').read_text()))
        self.assertEqual(check.COMMIT,'825caff3a6c618419c49c7da452e009ce86ae8b5')

    def test_default_owner_body_and_optional_workspace(self):
        path='candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseOwner.scala'
        actual=(self.out/path).read_bytes();original=check.frozen(path)
        self.assertTrue(actual.startswith(original))
        kernel=(self.out/check.PREFIX/'QwenOwnerProtocol.scala').read_text()
        self.assertIn('enableTransposedSeed:Boolean=false',kernel)
        self.assertIn('prefixWorkspace=if(enableTransposedSeed)Some(Input(new TransposedPrefixWorkspace))else None',kernel)
        self.assertIn('Module(new TransposedDenseSeedOwner',kernel)
        owner=actual.decode().split('class TransposedDenseSeedOwner',1)[1]
        self.assertNotIn('job.c',owner)
        self.assertIn('val seedHold=Reg(UInt(512.W))',owner)
        self.assertIn('prefixAckBytes=/=((nBase.pad(64)>>5)+contexts)*16384.U',owner)
        self.assertIn('groupDone && written===contexts',owner)

    def test_controller_reuse_and_no_added_sram(self):
        for name in ('MatrixAccumulatorSeedProtocol.scala','MatrixAccumulatorSeedController.scala'):
            path='candidates/qwen2_resident_matrix/'+name
            self.assertEqual((self.out/path).read_bytes(),check.frozen(path))
        path='candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseBanks.scala'
        self.assertEqual((self.out/path).read_bytes(),check.frozen(path))
        owner=(self.out/'candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseOwner.scala').read_text()
        seeded=owner.split('class TransposedDenseSeedOwner',1)[1]
        self.assertEqual(seeded.count('Module(new TransposedDenseBanks)'),1)
        self.assertEqual(seeded.count('val finalValue=Reg(Vec(16,Vec(256,UInt(32.W))))'),1)
        self.assertNotIn('SyncReadMem',seeded)


if __name__=='__main__':unittest.main()

"""Frozen layered source and Down's physical bank/address contracts."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('down_frontend_check',HERE/'check_frontend.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)

class SourceCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        work=check.ROOT/'work/qwen2_transposed_down_20261011';work.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(prefix='source_test_',dir=work)
        cls.out=Path(cls.temp.name);cls.paths,cls.pins=check.compose(cls.out)
        cls.owner=(cls.out/'candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseOwner.scala').read_text()
        cls.down=cls.owner.split('class TransposedDenseDownOwner',1)[1]
        cls.banks=(cls.out/'candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseBanks.scala').read_text()
        cls.kernel=(cls.out/check.PREFIX/'QwenOwnerProtocol.scala').read_text()
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_frozen_composition_and_postimages(self):
        self.assertEqual(self.pins,json.loads((HERE/'source_pins.json').read_text()))
        self.assertEqual(check.COMMIT,'825caff3a6c618419c49c7da452e009ce86ae8b5')
    def test_original_owner_and_banks_remain_exact_prefix(self):
        for name,actual in [('TransposedDenseOwner.scala',self.owner),('TransposedDenseBanks.scala',self.banks)]:
            original=check.frozen('candidates/qwen2_resident_matrix/transposed_owner/'+name).decode()
            self.assertTrue(actual.startswith(original))
        self.assertIn('enableTransposedDown:Boolean=false',self.kernel)
        self.assertIn('require(!enableTransposedDown || enableTransposedSeed',self.kernel)
        self.assertIn('if(enableTransposedDown)\n      Module(new TransposedDenseDownOwner',self.kernel)
    def test_local_widths_and_global_stride_are_separate(self):
        for token in ('aBeat=RegInit(0.U(8.W))','aHighKWord=Reg(UInt(8.W))',
          'halfK=Reg(Vec(2,UInt(12.W)))','loadK=Reg(UInt(12.W))',
          'readK=RegInit(0.U(12.W))','pendingK=Reg(UInt(12.W))',
          'Cat(readK(11,7),0.U(7.W))',
          'job.a+(aRow.pad(64)*job.k+chunkBase)*activationBytes',
          '((chunkBase.pad(64)+loadK+loadDepth)*job.n',
          '(chunkDepth>>4)*8.U','banks.io.read.bits.k:=readK'):
            self.assertIn(token,self.down)
        bank=self.banks.split('class TransposedDownDenseBanks',1)[1]
        for token in ('gatherK(11,4)','bits.kWord<160.U','bits.k<2560.U'):
            self.assertIn(token,bank)
        self.assertNotIn('h780',self.down)
    def test_same_sram_ports_buffers_service_and_leaf(self):
        bank=self.banks.split('class TransposedDownDenseBanks',1)[1]
        for token in ('Seq.fill(16)(SyncReadMem(1376,UInt(256.W)))','Seq.fill(16)(SyncReadMem(160,UInt(256.W)))'):
            self.assertIn(token,bank)
        for call in ('aBanks(bank).read(','aBanks(bank).write(','bBanks(bank).read(','bBanks(bank).write('):
            self.assertEqual(bank.count(call),1)
        self.assertEqual(self.down.count('Module(new TransposedDownDenseBanks)'),1)
        self.assertEqual(self.down.count('val finalValue=Reg(Vec(16,Vec(256,UInt(32.W))))'),1)
        self.assertEqual(self.down.count('new Queue(new MatrixStreamStep,4,pipe=true)'),1)
        self.assertNotIn('SyncReadMem',self.down)
        seed=json.loads((HERE.parent/'transposed_seed/source_pins.json').read_text())
        for path,sha in seed['patched_sources'].items():
            if '/transposed_owner/' not in path and not path.endswith('QwenOwnerProtocol.scala'):
                self.assertEqual(self.pins['patched_sources'][path],sha)
    def test_shared_prefix_read_before_overwrite_and_sweep_fence(self):
        for token in ('committedPrefixEnd===chunkBase','seedContext===restoredContexts',
          'seedContext>=savedContexts','writeContext===savedContexts','writeContext<restoredContexts',
          'groupDone && written===contexts','savedContexts=/=nextContext',
          'sweepAckBytes=/=nextContext*16384.U','restoredContexts=/=nextContext',
          'committedPrefixEnd:=chunkEnd;chunkBase:=chunkEnd',
          'restoredContexts:=0.U;savedContexts:=0.U;sweepAckBytes:=0.U',
          '(!savingPrefix || prefixStoreLegal)'):
            self.assertIn(token,self.down)
        self.assertNotIn('job.c',self.down)
        self.assertNotIn('w.splitK>=j.k',self.down)
        self.assertIn('(j.k>w.splitK && w.extent<(j.n.pad(64)>>5)*16384.U)',self.down)
        self.assertIn('seed.ack.ready:=seedOutstanding &&',self.down)
        self.assertNotIn('UIntToOH(seedContext,48)',self.down)
    def test_clear_last_conversion_and_bytes_only_final(self):
        for token in ('step.clear:=chunkBase===0.U && pendingK===0.U',
          'step.last:=pendingK+1.U===chunkDepth','step.finish:=step.last && pendingContext+1.U===contexts',
          'Mux(savingPrefix,prefix,Mux(job.outputBf16,bf16,fp32))',
          'when(savingPrefix){prefixAckBytes:=prefixAckBytes+64.U;sweepAckBytes:=sweepAckBytes+64.U}.otherwise{bytes:=bytes+(ackBeats.pad(64)<<6)}',
          'prefixValid:=false.B;halfReady:=VecInit', 'j.k>8960.U','w.splitK>2560.U',
          'seedOutstanding:=true.B','seedOutstanding:=false.B','!burstOutstanding && !seedOutstanding'):
            self.assertIn(token,self.down)

if __name__=='__main__':unittest.main()

"""Source identity/isolation guards; executable lifecycle coverage is test_model.

These checks do not simulate Scala or establish numerical hardware acceptance.
The bounded frontend separately typechecks all owners and audits actual CHIRRTL.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ffn_window_frontend',HERE/'check_frontend.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)

class WindowSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=check.ROOT/'work')
        cls.out=Path(cls.temp.name)
        cls.paths,cls.pins=check.compose(cls.out)
        cls.before=json.loads((HERE.parent/'ffn_tiles/source_pins.json').read_text())
        cls.owner=(cls.out/check.OWNER/'TransposedDenseOwner.scala').read_text().split('class TransposedDenseDownOwner(',1)[1]
        cls.banks=(cls.out/check.OWNER/'TransposedDenseBanks.scala').read_text()
        cls.io=(cls.out/check.OWNER/'DenseOwnerIO.scala').read_text()
        cls.kernel=(cls.out/check.PREFIX/'QwenOwnerProtocol.scala').read_text()
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_exact_preimages_postimages_and_only_four_actual_sources_changed(self):
        self.assertEqual(self.pins,json.loads((HERE/'source_pins.json').read_text()))
        changed={p for p,h in self.before['patched_sources'].items() if self.pins['patched_sources'][p]!=h}
        self.assertEqual(changed,{check.OWNER+p for p in ('DenseOwnerIO.scala','TransposedDenseBanks.scala','TransposedDenseOwner.scala')}|{check.PREFIX+'QwenOwnerProtocol.scala'})
        for p,h in self.before['patches'].items(): self.assertEqual(self.pins['patches'][p],h)

    def test_host_math_and_sfu_are_byte_identical(self):
        for p in ('HostBlockTop.scala','HostBlockCommands.scala','BlockFloat.scala','VectorSilu.scala','OverlappedSilu.scala','MatrixPipeline.scala','RetainedMatrix.scala'):
            self.assertEqual(self.pins['patched_sources'][check.PREFIX+p],self.before['patched_sources'][check.PREFIX+p])
        self.assertNotIn('bias_index',(HERE/'window.patch').read_text())
        self.assertNotIn('SyncReadMem',self.owner)
        self.assertEqual(self.owner.count('val finalValue=Reg(Vec(16,Vec(256,UInt(32.W))))'),1)
        self.assertEqual(self.owner.count('val prefixWriteIndex=RegInit(0.U(8.W))'),1)

    def test_order_extension_is_absent_in_original_profile(self):
        self.assertIn('class FfnTileControl(enableMatrixProducerOrder:Boolean=false)',self.banks)
        self.assertIn('val matrixProducerOrder=if(enableMatrixProducerOrder)Some(Bool())else None',self.banks)
        self.assertIn('new TransposedDownDenseBanks(enableFfnTiles,enableMatrixProducerOrder=enableFfnWindow)',self.owner)
        self.assertIn('enableFfnWindow:Boolean=false',self.owner)
        self.assertIn('enableFfnWindow:Boolean=false',self.kernel)
        self.assertIn("'tiles_on_window_off_ir'",(HERE/'check_frontend.py').read_text())
        self.assertIn('TransposedDenseDownOwnerTilesBaseline',(HERE/'FfnWindowElaboration.scala').read_text())

    def test_window_is_typed_and_retains_original_job_stride(self):
        for fragment in ('class FfnWindowRequest','val job=new QwenOwnerJob','class FfnWindowResult','val ddrWriteBytes=UInt(64.W)','val invalidateLease=Input(Bool())'):
            self.assertIn(fragment,self.io)
        self.assertIn('r.ng.pad(17)+&r.cols.pad(17)<=j.n.pad(18)',self.owner)
        self.assertIn('job:=j;',self.owner)
        self.assertIn('(chunkBase.pad(64)+loadK+loadDepth)*job.n+nBase',self.owner)
        self.assertNotIn('job.n:=',self.owner)
        self.assertIn('useful:=useful+job.m.pad(64)*32.U',self.owner)
        self.assertIn('w.result.bits.ddrWriteBytes:=0.U',self.owner)
        self.assertIn('state===finish && !windowActive.get',self.owner)

    def test_common_admission_and_real_fenced_lease(self):
        for fragment in ('val workspaceOK=ws.valid','!prefixAliases','j.writeBytes===j.m.pad(64)*j.n*4.U','j.dst(5,0)===0.U && !aliases',
                         'lease.base===j.a','lease.activationBf16===j.activationBf16','lease.rows===j.m && lease.k===j.k','lease.rowStride===rowStride && lease.identity===r.identity',
                         'state===aFence && !aHighPending && !banks.io.activationBusy',
                         '!io.tiles.get.abort && !w.invalidateLease','when(w.invalidateLease || io.job.fire || banks.io.zero.valid || banks.io.activation.fire'):
            self.assertIn(fragment,self.owner)
        self.assertIn('dense.window.get.invalidateLease:=io.window.get.invalidateLease || io.job.fire',self.kernel)
        self.assertIn('!active && !w.request.valid',self.owner)
        self.assertIn('dense.window.get.busy || io.window.get.request.valid else false.B',self.kernel)

    def test_exact_matrix_mapping_commit_order_and_no_extra_payload(self):
        self.assertIn('finalValue(prefixWriteIndex(3,0))(Cat(prefixWriteIndex(4),prefixWriteIndex(7,5),l.U(4.W)))',self.owner)
        self.assertIn('prefixWriteIndex(7,5)*windowCols.get+(writeContext.pad(11)<<5)+prefixWriteIndex(4,0)',self.owner)
        for fragment in ('tag.produced>>5,tag.produced>>8','tag.produced(7,5)','producerGroup*tag.cols+(producerContext<<5)+tag.produced(4,0)',
                         'key.index===tag.consumed','when(pendingWrite){tags(selectedTile.slot).produced:='):
            self.assertIn(fragment,self.banks)
        self.assertIn('writeState===writeWait && p.drained',self.owner)
        self.assertIn('t.produced=/=committedBefore+1.U',self.owner)
        self.assertIn('when(windowActive.get && writeState=/=writeIdle){banks.io.read.valid:=false.B}',self.owner)
        self.assertIn('writeState===writeReq && !banks.io.response.valid',self.owner)
        self.assertIn('r.context=/=written || !terminalIssued(r.context)',self.owner)

    def test_completion_revalidates_and_abort_drains(self):
        self.assertIn('when(active && status===0.U && state=/=finish && !p.resetRequired && !io.tiles.get.abort)',self.owner)
        self.assertIn('when(phase===5.U)',self.owner)
        self.assertIn('exact && t.sealedTile && t.produced===expected && t.consumed===0.U',self.owner)
        self.assertIn('groupDone && captured===contexts && written===contexts && p.drained && operandsEmpty',self.owner)
        self.assertIn('ackFire:=false.B;io.response.ready:=false.B',self.owner)
        self.assertIn('when(active && status=/=0.U && writeState===writeWait && p.drained){writeState:=writeIdle}',self.owner)
        self.assertIn('!burstOutstanding && !seedOutstanding && (!groupStarted || groupDone)',self.owner)
        self.assertIn('when(w.result.valid){assert(!io.done.valid && bytes===0.U',self.owner)

    def test_all_geometries_matrix_order_are_bijective_and_match_fp32_slots(self):
        for rows in (16,128):
            for cols in (32,64,96,128,160):
                indices=[]
                for q in range(rows//16*cols):
                    c=q>> (5 if rows==16 else 8)
                    g=0 if rows==16 else (q>>5)&7
                    j=q&31
                    index=g*cols+32*c+j
                    indices.append(index)
                    for lane in range(16):
                        physical_col=128*(j//16)+16*g+lane
                        self.assertEqual(physical_col&127,16*g+lane)
                        self.assertEqual(physical_col>>7,j//16)
                        self.assertEqual((index//cols,index%cols),(g,32*c+j))
                self.assertEqual(sorted(indices),list(range(rows//16*cols)))

if __name__=='__main__': unittest.main()

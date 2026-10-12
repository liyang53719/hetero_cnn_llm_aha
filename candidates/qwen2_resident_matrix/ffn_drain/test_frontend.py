"""Pinned source/ABI/storage guards; executable lifecycle tests are test_model.

No Scala/RTL execution is claimed here. The bounded frontend audits CHIRRTL.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ffn_drain_frontend',HERE/'check_frontend.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)

class DrainSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=check.ROOT/'work')
        cls.out=Path(cls.temp.name);cls.paths,cls.pins=check.compose(cls.out)
        cls.before=json.loads((HERE.parent/'ffn_window/source_pins.json').read_text())
        cls.owner=(cls.out/check.OWNER/'TransposedDenseOwner.scala').read_text().split('class TransposedDenseDownOwner(',1)[1]
        cls.io=(cls.out/check.OWNER/'DenseOwnerIO.scala').read_text()
        cls.kernel=(cls.out/check.PREFIX/'QwenOwnerProtocol.scala').read_text()
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_exact_composition_and_three_sources_only(self):
        self.assertEqual(self.pins,json.loads((HERE/'source_pins.json').read_text()))
        changed={p for p,h in self.before['patched_sources'].items() if self.pins['patched_sources'][p]!=h}
        self.assertEqual(changed,{check.OWNER+'DenseOwnerIO.scala',check.OWNER+'TransposedDenseOwner.scala',check.PREFIX+'QwenOwnerProtocol.scala'})
        for p,h in self.before['patches'].items():self.assertEqual(self.pins['patches'][p],h)

    def test_separate_default_off_typed_port_and_optional_window_counters(self):
        for text in (self.io,self.owner,self.kernel):self.assertIn('enableFfnDrain:Boolean=false',text)
        for token in ('class FfnDrainRequest','class FfnDrainResult','class FfnDrainPort','val job=new QwenOwnerJob',
                      'val consumedBeats=UInt(11.W)','val ddrWriteBytes=UInt(64.W)',
                      'class FfnWindowResult(enableCounters:Boolean=false)','class FfnWindowPort(enableCounters:Boolean=false)'):
            self.assertIn(token,self.io)
        self.assertIn('when(if(enableFfnDrain)ackFire && !drainActive.get else ackFire)',self.owner)
        self.assertIn('!drainActive.get && !windowActive.getOrElse(false.B)',self.owner)

    def test_activation_contract_preserves_full_spans(self):
        for token in ('j.kind===QwenOwnerKind.Activation.U','j.n===8960.U && j.k===8960.U',
                      '!j.activationBf16 && !j.weightBf16 && !j.outputBf16',
                      'val size=j.m.pad(66)*j.n*4.U','j.writeBytes===size && disjoint && workspaceOK',
                      'r.ng.pad(17)+&r.cols.pad(17)<=j.n.pad(18)','t.consumed===0.U'):
            self.assertIn(token,self.owner)
        self.assertNotIn('job.n:=',self.owner)
        self.assertIn('t.matrixProducerOrder.getOrElse(false.B)',self.owner)

    def test_no_extra_payload_or_arithmetic_resources(self):
        for token in ('val finalValue=Reg(Vec(16,Vec(256,UInt(32.W))))','val prefixWriteIndex=RegInit(0.U(8.W))',
                      'val writeRow=RegInit(0.U(7.W))','val writeBeat=RegInit(false.B)'):
            self.assertEqual(self.owner.count(token),1)
        patch=(HERE/'drain.patch').read_text()
        added='\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
        for forbidden in ('privateCommand128','bias_index','SyncReadMem','new SiluVectorUnit','new BlockScalarFloat','new MatrixPipelineService'):
            self.assertNotIn(forbidden,added)
        self.assertIn('finalValue(l)(prefixWriteIndex):=p.response.bits.value(l)',self.owner)

    def test_actual_response_and_ack_retirement(self):
        for token in ('when(p.response.fire)','when(matching){drainConsumed.get:=drainConsumed.get+1.U}',
                      'val ackGood=ackFire && !ackBits.error && ackBits.tag===writeTag',
                      'bytes:=bytes+(ackBeats.pad(64)<<6)','io.writeData.get.valid:=writeState===writeData',
                      'writeState=/=writeWait && writeState=/=writeData',
                      'when(!pending && p.drained && writeState=/=writeData && writeState=/=writeWait)',
                      'when(phase===5.U)','!t.live && !t.sealedTile && p.drained && !pending',
                      'io.memory.bits.mask:=Fill(64,1.U(1.W))'):
            self.assertIn(token,self.owner)
        self.assertIn('val idleUnexpected=state===idle',self.owner)
        self.assertIn('status=/=0.U || (active && activeUnexpected)',self.owner)
        self.assertIn('d.abort || idleUnexpected || (active && activeUnexpected)',self.owner)
        self.assertIn('p.read.valid:=true.B',self.owner)
        self.assertIn('when(!bad && state=/=finish)',self.owner)
        self.assertIn('noExternal && !bad && !idleUnexpected',self.owner)
        self.assertIn('state=/=locked && !drainActive.get else',self.owner)

    def test_kernel_routes_nonburst_without_normal_active(self):
        self.assertIn('when(dense.drain.get.busy)',self.kernel)
        self.assertIn('io.memory.valid:=dense.memory.valid;io.memory.bits:=dense.memory.bits;dense.memory.ready:=io.memory.ready',self.kernel)
        self.assertIn('io.response.ready:=dense.response.ready;dense.response.valid:=io.response.valid',self.kernel)
        self.assertIn('dense.drain.get.abort:=io.drain.get.abort || io.tiles.get.abort || io.tileSilu.get.abort',self.kernel)
        self.assertIn('!tileBusy && !windowBusy && !drainBusy',self.kernel)

    def test_all_geometry_transport_and_burst_addresses(self):
        for rows in (16,128):
            for cols in (32,64,96,128,160):
                for ng in range(0,8960-cols+1,32):
                    emitted=0
                    for row in range(rows):
                        beat=0
                        while beat<cols//16:
                            address=0x2000000+(row*8960+ng+beat*16)*4
                            count=min(cols//16-beat,16-(address>>6&15))
                            self.assertEqual(address%64,0)
                            self.assertLessEqual((address&1023)+count*64,1024)
                            self.assertGreater(count,0)
                            for b in range(count):
                                for lane in range(16):
                                    n=(beat+b)*16+lane
                                    tile_index=(row//16)*cols+n
                                    self.assertEqual(divmod(tile_index,cols),(row//16,n))
                                    self.assertEqual((row%16,n),(row&15,16*(beat+b)+lane))
                                    self.assertLess(n,cols)
                            emitted+=count*64;beat+=count
                    self.assertEqual(emitted,rows*cols*4)

if __name__=='__main__':unittest.main()

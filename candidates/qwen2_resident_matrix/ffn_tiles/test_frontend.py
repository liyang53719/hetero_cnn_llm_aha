"""Frozen FFN tile composition, public ABI isolation and physical port contracts.

These are source/auditor guards. Executable lifecycle tests are in test_model;
Scala frontend emission and numerical checks are separate evidence gates.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ffn_frontend_check', HERE/'check_frontend.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class FfnSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        work = check.ROOT/'work/ffn_tiles_source_tests_20261011';work.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=work)
        cls.out = Path(cls.temp.name)
        cls.paths, cls.pins = check.compose(cls.out)
        cls.banks = (cls.out/check.OWNER/'TransposedDenseBanks.scala').read_text()
        cls.selected = cls.banks.split('class TransposedDownDenseBanks(', 1)[1].split('/** Internal typed tile ABI.', 1)[0]
        cls.owner = (cls.out/check.OWNER/'TransposedDenseOwner.scala').read_text().split('class TransposedDenseDownOwner(', 1)[1]
        cls.kernel = (cls.out/check.PREFIX/'QwenOwnerProtocol.scala').read_text()
        cls.vector = (cls.out/check.PREFIX/'VectorSilu.scala').read_text()
        cls.harness = (HERE/'FfnTileElaboration.scala').read_text()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exact_host_composition_and_postimages(self):
        self.assertEqual(self.pins, json.loads((HERE/'source_pins.json').read_text()))
        before = json.loads((HERE.parent/'transposed_host/source_pins.json').read_text())
        changed = {p for p, digest in before['patched_sources'].items() if self.pins['patched_sources'][p] != digest}
        self.assertEqual(changed, {check.OWNER+'DenseOwnerIO.scala', check.OWNER+'TransposedDenseBanks.scala',
            check.OWNER+'TransposedDenseOwner.scala', check.PREFIX+'VectorSilu.scala',
            check.PREFIX+'OverlappedSilu.scala', check.PREFIX+'QwenOwnerProtocol.scala'})
        for path, digest in before['patches'].items():
            self.assertEqual(self.pins['patches'][path], digest)

    def test_public_abi_and_numerical_implementation_are_unchanged(self):
        for name in ('HostBlockCommands.scala', 'HostBlockTop.scala', 'Protocol.scala', 'HostResidualCommands.scala', 'BlockFloat.scala'):
            self.assertEqual(self.pins['patched_sources'][check.PREFIX+name], json.loads((HERE.parent/'transposed_host/source_pins.json').read_text())['patched_sources'][check.PREFIX+name])
        original = check.frozen(check.PREFIX+'VectorSilu.scala').decode()
        arithmetic = lambda s: s.split('class SiluVectorUnit', 1)[1].split('/** Existing owner job', 1)[0]
        self.assertEqual(arithmetic(original), arithmetic(self.vector))
        self.assertIn('val kind=UInt(4.W)', self.kernel)
        self.assertNotIn('bias_index', (HERE/'tile_ports.patch').read_text())
        self.assertEqual(self.kernel.split('object QwenOwnerKind {',1)[1].split('}',1)[0],
                         check.frozen(check.PREFIX+'QwenOwnerProtocol.scala').decode().split('object QwenOwnerKind {',1)[1].split('}',1)[0])

    def test_optionality_and_actual_owner_kernel_wiring(self):
        self.assertIn('enableFfnTiles:Boolean=false', self.selected)
        self.assertIn('new TransposedDownDenseBanks(enableFfnTiles)', self.owner)
        self.assertIn('banks.io.tiles.get<>io.tiles.get', self.owner)
        self.assertIn('banks.io.tileEnable.get:=state===idle', self.owner)
        self.assertIn('dense.tiles.get<>io.tiles.get;silu.get.io.loan.get<>io.tileSilu.get', self.kernel)
        self.assertIn('new ScheduledSiluOwner(overlapSilu,enableTileLoan=enableFfnTiles)', self.kernel)
        self.assertIn('enableFfnTiles:Boolean=false', self.kernel)
        self.assertIn('!active && !sharedPoison && !rejected', self.kernel)

    def test_existing_memory_geometry_and_single_call_sites(self):
        self.assertEqual(self.selected.count('SyncReadMem(1376,UInt(256.W))'), 1)
        self.assertEqual(self.selected.count('SyncReadMem(160,UInt(256.W))'), 1)
        self.assertEqual(self.selected.count('aBanks(bank).read('), 1)
        self.assertEqual(self.selected.count('bBanks(bank).read('), 1)
        # A has one write in each mutually exclusive Scala elaboration branch.
        self.assertEqual(self.selected.count('aBanks(bank).write('), 2)
        self.assertEqual(self.selected.count('bBanks(bank).write('), 1)
        for text in ('val writeValue=Reg(Vec(16,UInt(32.W)))', 'val responseValue=Reg(Vec(16,UInt(32.W)))',
                     'response.asTypeOf(Vec(8,UInt(32.W)))', 'tileMerged(x.commitLane):=x.writeValue(bank)'):
            self.assertIn(text, self.selected)
        self.assertNotIn('Reg(Vec(16,UInt(256.W)))', self.selected)

    def test_ordered_lifecycle_and_fp32_address(self):
        for text in ('c.op===0.U && beginOK', 'c.op===1.U && identity', 'c.op===2.U && identity',
                     't.produced===t.expected', 't.consumed===t.expected',
                     'key.index===tag.produced', 'key.index===tag.consumed',
                     'c.rows===16.U || c.rows===128.U', 'c.cols(4,0)===0.U', 'c.identity=/=0.U && c.ng(4,0)===0.U',
                     '768.U+key.slot*160.U+rowGroup*20.U+n/8.U', 'x.lane:=n(2,0)',
                     'p.write.bits.value.map(v=>v(30,23)=/=255.U)',
                     'p.write.ready:=admit && !p.control.valid',
                     'p.read.ready:=admit && !p.control.valid && !p.write.valid'):
            self.assertIn(text, self.selected)
        self.assertIn('when(pendingWrite){tags(selectedTile.slot).produced:=', self.selected)
        self.assertIn('when(p.response.fire){\n      tags(selectedTile.slot).consumed:=', self.selected)
        self.assertNotIn('0x7fc00001', self.selected)

    def test_resident_tiles_allow_low_a_dense_and_reject_conflicting_k(self):
        for text in ('p.busy:=outstanding || poison || p.abort;p.leased:=occupied',
                     '!tileSignals.get.leased || io.activation.bits.kWord<96.U',
                     '!tileSignals.get.leased || io.read.bits.k<1536.U',
                     '!x.leased || io.zero.bits<768.U'):
            self.assertIn(text, self.selected)
        self.assertIn('banks.io.tiles.get.leased && j.k>1536.U', self.owner)
        self.assertIn('status:=Status.Bounds.U;state:=finish', self.owner)
        self.assertIn('io.tiles.get.leased && io.job.bits.kind=/=QwenOwnerKind.Dense.U,7.U', self.kernel)
        self.assertIn('when(zeroWord+1.U===(chunkDepth>>4)*8.U)', self.owner)

    def test_poison_does_not_drop_rmw_or_stalled_read_and_reaches_owner_drain(self):
        self.assertIn('x.commit:=pendingWrite', self.selected)
        self.assertIn('responseValid:=true.B;responseError:=poison || p.abort || nonfinite', self.selected)
        self.assertIn('p.response.valid:=responseValid', self.selected)
        self.assertIn('when(p.abort){poison:=true.B}', self.selected)
        self.assertIn('when((banks.io.tiles.get.resetRequired || io.tiles.get.abort) && state=/=idle && state=/=finish && state=/=locked){fail(Status.Protocol.U)}', self.owner)
        for text in ('io.matrix.abort:=(state===drain || status=/=0.U)',
                     'operands.io.deq.ready:=Mux(status=/=0.U,true.B',
                     'seed.ack.ready:=seedOutstanding && (state===drain',
                     'status=/=0.U || !burstIsA', 'state:=drain;aCommitted:=false.B'):
            self.assertIn(text, self.owner)

    def test_one_existing_vector_arithmetic_and_exclusive_loan(self):
        self.assertEqual(self.vector.count('Module(new SiluVectorUnit(16))'), 1)
        self.assertIn('loanActive=RegInit(false.B);val loanPoison=RegInit(false.B)', self.vector)
        self.assertIn('when(loanActive){vector.io.result.ready:=p.result.ready}', self.vector)
        self.assertIn('!loanActive && !loanPoison && !p.request.valid && !p.abort', self.vector)
        self.assertIn('state===waitCompute else vector.io.result.fire', self.vector)
        self.assertIn('new ScheduledSiluOwner(enableTileLoan=true)', self.harness)
        self.assertNotIn('new SiluVectorUnit', self.harness)
        self.assertIn('owner.io.loan.get<>bridge.io.silu', self.harness)

    def test_harness_stalls_start_until_external_response_drains(self):
        self.assertIn('val route=bridge.io.busy', self.harness)
        self.assertNotIn('val route=bridge.io.busy || io.start.valid', self.harness)
        self.assertIn('io.start.ready:=bridge.io.start.ready && p.drained', self.harness)
        self.assertIn('p.response.ready:=Mux(route,b.response.ready,io.tiles.response.ready)', self.harness)
        self.assertIn('io.tiles.control.valid && !io.start.valid', self.harness)
        self.assertIn('io.tiles.response.ready:=bad || state===gateWait', self.harness)
        self.assertIn('io.silu.result.ready:=bad ||', self.harness)
        self.assertIn('io.tiles.drained && io.silu.drained', self.harness)
        self.assertIn('io.busy:=state=/=idle && state=/=locked', self.harness)
        self.assertIn('state:=Mux(state===idle || state===locked,locked,drain)', self.harness)

    def test_bridge_checks_both_complete_input_geometries_and_observes_release(self):
        for text in ('def same(t:FfnTileState,c:FfnTileInvocation)', 't.rows===c.rows && t.cols===c.cols',
                     't.expected===(c.rows>>4)*c.cols', 'val inputsReady=Seq(0,1)',
                     't.live && t.sealedTile && same(t,io.start.bits)',
                     't.produced===t.expected && t.consumed===0.U', '!io.tiles.state(2).live',
                     'when(state===releaseUp){state:=retire}', 'when(state===retire && !bad)',
                     '!io.tiles.state(0).live && !io.tiles.state(1).live',
                     't.live && t.sealedTile && same(t,call)',
                     'when(committed){io.complete:=true.B;state:=idle}'):
            self.assertIn(text, self.harness)
        self.assertNotIn('when(state===releaseUp){state:=idle;io.complete:=true.B}', self.harness)
        self.assertIn('banks.io.tiles.get.resetRequired || io.tiles.get.abort else status=/=0.U', self.owner)

    def test_normalizer_only_drops_assertion_diagnostic_location(self):
        helper = type('Helper', (), {'normalized_chirrtl': staticmethod(lambda s: s)})
        a = 'printf(clock, en, "    at Before.scala:12 assert(x<8)\\n")'
        b = 'printf(clock, en, "    at After.scala:99 assert(x<8)\\n")'
        self.assertEqual(check.normalized(a, helper), check.normalized(b, helper))
        self.assertNotEqual(check.normalized(a, helper), check.normalized(b.replace('x<8', 'x<9'), helper))

    def test_memory_auditor_rejects_duplicate_ports_and_extra_arrays(self):
        lines = []
        for index in range(32):
            name = 'bank'+str(index)
            lines.extend(['    smem '+name+' : UInt<256> ['+str(1376 if index<16 else 160)+']',
                          '    read mport r'+str(index)+' = '+name+'[addr], clock',
                          '    write mport w'+str(index)+' = '+name+'[addr], clock'])
        fir = '\n'.join(lines)
        self.assertEqual(len(check.memory_audit(fir)), 32)
        with self.assertRaises(ValueError):
            check.memory_audit(fir+'\n    read mport extra = bank0[addr], clock')
        with self.assertRaises(ValueError):
            check.memory_audit(fir+'\n    cmem hidden : UInt<512> [8]')


if __name__ == '__main__':
    unittest.main()

// Scope: actual bridge + synthetic finite tile/vector protocol, not arithmetic/B/full block.
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
class DenseTileSumBridgeDriveOrderSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def zero(x:Data):Unit=x match {case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U);case v:Vec[_]=>v.foreach(zero);case r:Record=>r.elements.values.foreach(zero);case _=>fail("unsupported input")}
  "Original DenseTileSumBridge" should "distinguish stale post-edge mock valid from a clocked illegal response" in {
    test(new DenseTileSumBridgeDriveOrderHarness).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val p=d.io
      def initialize():Unit={
        p.start.valid.poke(false.B);zero(p.start.bits);p.abort.poke(false.B);p.bankGranted.poke(true.B)
        p.tiles.control.ready.poke(true.B);p.tiles.read.ready.poke(true.B);p.tiles.write.ready.poke(true.B)
        p.tiles.response.valid.poke(false.B);zero(p.tiles.response.bits)
        p.tiles.busy.poke(false.B);p.tiles.leased.poke(true.B);p.tiles.drained.poke(true.B);p.tiles.resetRequired.poke(false.B)
        zero(p.tiles.state)
        p.vector.request.ready.poke(true.B);p.vector.result.valid.poke(false.B);zero(p.vector.result.bits)
        p.vector.busy.poke(false.B);p.vector.drained.poke(true.B);p.vector.resetRequired.poke(false.B)
        d.reset.poke(true.B);d.clock.step();d.reset.poke(false.B)
        for(i<-0 until 2){val t=p.tiles.state(i);t.live.poke(true.B);t.sealedTile.poke(true.B);t.identity.poke(2.U);t.ng.poke(0.U);t.rows.poke(128.U);t.cols.poke(160.U);t.expected.poke(1280.U);t.produced.poke(1280.U);t.consumed.poke(0.U);t.matrixProducerOrder.get.poke(true.B)}
        p.start.bits.identity.poke(2.U);p.start.bits.ng.poke(0.U);p.start.bits.rows.poke(128.U);p.start.bits.cols.poke(160.U)
        p.start.bits.lhsSlot.poke(0.U);p.start.bits.rhsSlot.poke(1.U);p.start.bits.outputSlot.poke(2.U)
        p.start.valid.poke(true.B);p.start.ready.expect(true.B);d.clock.step();p.start.valid.poke(false.B)
        p.tiles.control.valid.expect(true.B);p.tiles.control.bits.op.expect(0.U);p.tiles.control.bits.slot.expect(2.U);d.clock.step()
        val t=p.tiles.state(2);t.live.poke(true.B);t.identity.poke(2.U);t.rows.poke(128.U);t.cols.poke(160.U);t.expected.poke(1280.U)
        // Each response follows its own real read.fire; zero data is protocol-only.
        p.tiles.read.valid.expect(true.B);p.tiles.read.bits.slot.expect(0.U);p.tiles.read.bits.index.expect(0.U);d.clock.step()
        p.tiles.response.bits.key.slot.poke(0.U);p.tiles.response.bits.key.identity.poke(2.U);p.tiles.response.bits.key.ng.poke(0.U);p.tiles.response.bits.key.index.poke(0.U)
        p.tiles.response.valid.poke(true.B);p.tiles.response.ready.expect(true.B);d.clock.step();p.tiles.response.valid.poke(false.B);p.tiles.state(0).consumed.poke(1.U)
        p.tiles.read.valid.expect(true.B);p.tiles.read.bits.slot.expect(1.U);p.tiles.read.bits.index.expect(0.U);d.clock.step()
        p.tiles.response.bits.key.slot.poke(1.U);p.tiles.response.valid.poke(true.B)
        p.vector.request.valid.expect(true.B);p.vector.request.ready.expect(true.B);p.tiles.response.ready.expect(true.B);p.vector.request.bits.binaryAdd.get.expect(true.B)
        d.clock.step();p.tiles.response.valid.poke(false.B);p.tiles.state(1).consumed.poke(1.U)
        d.diagnostic.inflight.expect(true.B)
        p.vector.result.valid.poke(true.B);p.vector.busy.poke(true.B);p.vector.drained.poke(false.B)
        p.vector.result.ready.expect(true.B);p.tiles.write.valid.expect(true.B);p.tiles.write.ready.expect(true.B)
        p.tiles.write.bits.key.slot.expect(2.U);p.tiles.write.bits.key.index.expect(0.U)
        d.clock.step() // accepted vector result clears real bridge.inflight
        // Deliberately do NOT update the mock vector valid here.
      }
      def driveNextInputs():Unit={
        p.vector.result.valid.poke(false.B);p.vector.busy.poke(false.B);p.vector.drained.poke(true.B)
        p.tiles.state(2).produced.poke(1.U)
      }
      // Negative sampling-order demonstration: no extra edge at stale inputs.
      initialize()
      d.diagnostic.inflight.expect(false.B);d.diagnostic.unexpected.expect(true.B)
      p.tiles.abort.expect(true.B);p.resetRequired.expect(false.B)
      println("B_BRIDGE_OLD_SAMPLE stale_unexpected=true tile_abort=true registered_reset=false")
      driveNextInputs();d.diagnostic.unexpected.expect(false.B);p.tiles.abort.expect(false.B);p.resetRequired.expect(false.B)
      d.clock.step();p.resetRequired.expect(false.B)
      // Positive: drive the complete new mock state BEFORE reading fault outputs.
      initialize();driveNextInputs()
      d.diagnostic.inflight.expect(false.B);d.diagnostic.unexpected.expect(false.B);p.tiles.abort.expect(false.B);p.resetRequired.expect(false.B)
      d.clock.step();p.resetRequired.expect(false.B)
      println("B_BRIDGE_DRIVE_FIRST stable_unexpected=false tile_abort=false registered_reset=false")
      // A truly held unsolicited response across an edge must still poison.
      initialize();d.diagnostic.unexpected.expect(true.B);p.tiles.abort.expect(true.B)
      d.clock.step();p.resetRequired.expect(true.B)
      driveNextInputs();p.resetRequired.expect(true.B)
      println("B_BRIDGE_CLOCKED_INVALID registered_reset=true protocol_only=true")
    }
  }
}

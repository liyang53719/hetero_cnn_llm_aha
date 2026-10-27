// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
class HeldDecoupledOfferHarness extends Module {
  val io=IO(new Bundle{val intent=Input(Bool());val suppress=Input(Bool());val payload=Input(UInt(16.W));val offer=Decoupled(UInt(16.W));val held=Output(Bool())})
  val control=HeldDecoupledOffer(io.intent,io.offer.ready,io.suppress)
  io.offer.valid:=control.valid;io.offer.bits:=io.payload;io.held:=control.held
}
/** Control only. Caller keeps its intent/payload while held, just as the
  * coordinator keeps the original issue state until that exact offer fires. */
class HeldDecoupledOfferSpec extends AnyFlatSpec with ChiselScalatestTester {
  it should "preserve an offered job through a late suppress until real fire" in {
    test(new HeldDecoupledOfferHarness){d=>
      d.io.intent.poke(false.B);d.io.suppress.poke(false.B);d.io.payload.poke(23.U);d.io.offer.ready.poke(false.B)
      d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B)
      d.io.intent.poke(true.B);d.io.suppress.poke(true.B);d.io.offer.valid.expect(false.B);d.clock.step()
      d.io.suppress.poke(false.B);d.io.offer.valid.expect(true.B);d.clock.step()
      d.io.held.expect(true.B);d.io.suppress.poke(true.B)
      for(_<-0 until 4){d.io.offer.valid.expect(true.B);d.io.offer.bits.expect(23.U);d.clock.step()}
      d.io.offer.ready.poke(true.B);d.io.offer.valid.expect(true.B);d.clock.step()
      d.io.held.expect(false.B);d.io.offer.valid.expect(false.B)
      d.io.intent.poke(false.B);d.clock.step()
    }
  }
}

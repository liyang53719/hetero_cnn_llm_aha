// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

/** Short protocol controls, not RMS arithmetic/numerical qualification. */
class GdnRuntimeRmsNormControlV3Spec extends AnyFlatSpec with ChiselScalatestTester {
  it should "hold rejected terminal immutable under late fault without external norm completion injection" in {
    test(new GdnRuntimeRmsNormOwnerV3).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      d.io.parentFault.poke(false.B);d.io.done.ready.poke(false.B);d.io.job.valid.poke(false.B)
      d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
      d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B)
      d.io.formatRequest.ready.poke(false.B);d.io.formatResult.valid.poke(false.B)
      d.io.response.bits.tag.poke(0.U);d.io.response.bits.data.poke(0.U);d.io.response.bits.error.poke(false.B)
      d.io.scalar.result.bits.policy.poke(0.U);d.io.scalar.result.bits.value.poke(0.U)
      d.io.scalar.result.bits.flags.poke(0.U);d.io.scalar.result.bits.primitiveFlagsValid.poke(false.B);d.io.scalar.result.bits.error.poke(false.B)
      d.io.formatResult.bits.value.poke(0.U);d.io.formatResult.bits.error.poke(false.B)
      d.io.job.bits.tokens.poke(128.U);d.io.job.bits.hiddenWidth.poke(1024.U);d.io.job.bits.reductionRecipe.poke(0.U)
      d.io.job.bits.input.poke("h100000".U);d.io.job.bits.weight.poke("h200000".U);d.io.job.bits.output.poke("h300000".U);d.io.job.bits.tag.poke(0.U)
      d.io.job.valid.poke(true.B);d.io.job.ready.expect(true.B);d.clock.step();d.io.job.valid.poke(false.B)
      d.clock.step();d.io.done.valid.expect(true.B);val held=Seq(d.io.done.bits.tag.peek().litValue,d.io.done.bits.status.peek().litValue,d.io.done.bits.writeBytes.peek().litValue,d.io.done.bits.cycles.peek().litValue,d.io.done.bits.outputCommitted.peek().litValue)
      d.io.done.bits.status.expect(Status.Unsupported.U);d.io.done.bits.outputCommitted.expect(false.B)
      d.io.parentFault.poke(true.B)
      for(_<-0 until 3){d.io.done.valid.expect(true.B);assert(Seq(d.io.done.bits.tag.peek().litValue,d.io.done.bits.status.peek().litValue,d.io.done.bits.writeBytes.peek().litValue,d.io.done.bits.cycles.peek().litValue,d.io.done.bits.outputCommitted.peek().litValue)==held);d.io.memory.valid.expect(false.B);d.clock.step()}
      d.io.done.ready.poke(true.B);d.clock.step();d.io.job.ready.expect(false.B)
    }
  }
  it should "retain a stalled real input read and retire only its matching response after abort for both widths" in {
    test(new GdnRuntimeRmsNormOwnerV3).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      for(width<-Seq(1024,2048)){
        d.io.job.valid.poke(false.B);d.io.done.ready.poke(false.B);d.io.parentFault.poke(false.B)
        d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
        d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B)
        d.io.formatRequest.ready.poke(false.B);d.io.formatResult.valid.poke(false.B)
        d.io.response.bits.tag.poke(0.U);d.io.response.bits.data.poke(0.U);d.io.response.bits.error.poke(false.B)
        d.io.scalar.result.bits.policy.poke(0.U);d.io.scalar.result.bits.value.poke(0.U);d.io.scalar.result.bits.flags.poke(0.U)
        d.io.scalar.result.bits.primitiveFlagsValid.poke(false.B);d.io.scalar.result.bits.error.poke(false.B)
        d.io.formatResult.bits.value.poke(0.U);d.io.formatResult.bits.error.poke(false.B)
        // Testbench reset only with no request ever issued or after true reply retirement.
        d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.clock.step()
        d.io.job.bits.tokens.poke(128.U);d.io.job.bits.hiddenWidth.poke(width.U);d.io.job.bits.reductionRecipe.poke(1.U)
        d.io.job.bits.input.poke("h100000".U);d.io.job.bits.weight.poke("h200000".U);d.io.job.bits.output.poke("h300000".U);d.io.job.bits.tag.poke(width.U)
        d.io.job.valid.poke(true.B);d.io.job.ready.expect(true.B);d.clock.step();d.io.job.valid.poke(false.B)
        d.io.memory.valid.expect(true.B);val held=Seq(d.io.memory.bits.write.peek().litValue,d.io.memory.bits.address.peek().litValue,d.io.memory.bits.data.peek().litValue,d.io.memory.bits.mask.peek().litValue,d.io.memory.bits.tag.peek().litValue);val tag=d.io.memory.bits.tag.peek().litValue
        d.clock.step();d.io.parentFault.poke(true.B)
        for(_<-0 until 3){d.io.memory.valid.expect(true.B);assert(Seq(d.io.memory.bits.write.peek().litValue,d.io.memory.bits.address.peek().litValue,d.io.memory.bits.data.peek().litValue,d.io.memory.bits.mask.peek().litValue,d.io.memory.bits.tag.peek().litValue)==held);d.io.done.valid.expect(false.B);d.clock.step()}
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        d.io.done.valid.expect(false.B);d.io.resourcesDrained.expect(false.B)
        d.io.response.bits.tag.poke(tag.U);d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B)
        d.clock.step();d.io.response.valid.poke(false.B);d.clock.step()
        d.io.done.valid.expect(true.B);d.io.done.bits.status.expect(Status.Protocol.U);d.io.done.bits.outputCommitted.expect(false.B)
        d.io.done.bits.writeBytes.expect(0.U);d.io.resourcesDrained.expect(true.B)
        d.io.done.ready.poke(true.B);d.clock.step();d.io.done.ready.poke(false.B)
      }
    }
  }
}

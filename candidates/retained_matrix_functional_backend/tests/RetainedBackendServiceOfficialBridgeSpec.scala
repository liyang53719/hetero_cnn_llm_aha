// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model
import heteronpu.continuous.MatrixPipelineService
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import chiseltest.simulator.RetainedServiceOfficialBridge
import treadle2.{BlackBoxFactoriesAnnotation, TreadleTester}

/** The original service, not an external-enable imitation. One actual Chisel
  * elaboration supplies BOTH the preflight Circuit AST and the simulator FIR.
  * All eight full512 endpoints remain present; only unseeded ABI is qualified
  * by this first service test. Seeded service handshake feedback is still an
  * explicit blocker for the original Qwen2 resident/restore path.
  */
class RetainedBackendServiceOfficialBridgeSpec extends AnyFlatSpec with Matchers {
  it should "execute original needsClock feedback with eight512 live endpoints and bounded backpressure" in {
    val (state, preparedAnnos) = RetainedServiceOfficialBridge.prepare(() => new MatrixPipelineService(
      returnTagBits = 32, enableTransposedDense = true, enableAccumulatorSeed = false,
      enablePackedDrainStatus = true))
    val circuit = state.circuit
    val factory = new RetainedMatrixModelFactory(seedEnabled = false, circuit = circuit)
    // This is the final constructor used by official CreateTester; using the
    // companion apply here would repeat the official preparation phases.
    val t = new TreadleTester(BlackBoxFactoriesAnnotation(Seq(factory)) +: preparedAnnos)
    try {
      require(t.engine.ast eq circuit, "simulator uses the exact strictly gated prepared Circuit object")
      factory.requireCompleteBinding()
      def poke(n: String, x: BigInt): Unit = t.poke("io_" + n, x)
      def peek(n: String): BigInt = t.peek("io_" + n)
      def expect(n: String, x: BigInt): Unit = t.expect("io_" + n, x)
      def waitFor(n: String): Unit = {
        var cycles = 0
        while (peek(n) == 0 && cycles < 128) { t.step(); cycles += 1 }
        expect(n, 1)
      }
      def bf(n: Int): BigInt = BigInt((java.lang.Float.floatToRawIntBits(n.toFloat) >>> 16) & 65535)
      def fp(n: Int): BigInt = BigInt(java.lang.Float.floatToRawIntBits(n.toFloat).toLong & 0xffffffffL)
      poke("port_group_valid", 0); poke("port_step_valid", 0); poke("port_abort", 0)
      poke("port_result_ready", 0); poke("port_done_ready", 0)
      poke("port_group_bits_opcode", 0x20); poke("port_group_bits_sliceMask", 255)
      poke("port_group_bits_tag", 1); poke("port_group_bits_transposedDense", 0)
      poke("port_step_bits_context", 0); poke("port_step_bits_clear", 1)
      poke("port_step_bits_last", 0); poke("port_step_bits_finish", 0)
      poke("port_step_bits_emit", 0); poke("port_step_bits_returnTag", 0)
      for (r <- 0 until 16) poke(s"port_step_bits_a_$r", bf(r + 1))
      for (c <- 0 until 256) poke(s"port_step_bits_b_$c", bf(c + 1))
      t.poke("reset", 1); t.step(2); t.poke("reset", 0); t.step(3)
      expect("acceptedSteps", 0); expect("resetRequired", 0)
      def group(tag: Int, transposed: Boolean): Unit = {
        poke("port_group_bits_tag", tag); poke("port_group_bits_transposedDense", if (transposed) 1 else 0)
        poke("port_group_valid", 1); waitFor("port_group_ready"); t.step(); poke("port_group_valid", 0)
      }
      def step(ctx: Int, clear: Boolean, last: Boolean, finish: Boolean, emit: Boolean, tag: Int): Unit = {
        poke("port_step_bits_context", ctx); poke("port_step_bits_clear", if (clear) 1 else 0)
        poke("port_step_bits_last", if (last) 1 else 0); poke("port_step_bits_finish", if (finish) 1 else 0)
        poke("port_step_bits_emit", if (emit) 1 else 0); poke("port_step_bits_returnTag", tag)
        poke("port_step_valid", 1); waitFor("port_step_ready"); t.step(); poke("port_step_valid", 0)
      }
      group(1, false)
      for (ctx <- 0 until 5) step(ctx, true, true, ctx == 4, true, 100 + ctx)
      waitFor("port_result_valid")
      val held = peek("port_result_bits_value_0_0")
      t.step(4); expect("port_result_valid", 1); expect("port_result_bits_value_0_0", held)
      expect("port_done_valid", 0)
      for (ctx <- 0 until 5) {
        waitFor("port_result_valid"); expect("port_result_bits_context", ctx)
        expect("port_result_bits_returnTag", 100 + ctx); expect("port_result_bits_error", 0)
        for (r <- 0 until 16; c <- 0 until 256) expect(s"port_result_bits_value_${r}_$c", fp((r + 1) * (c + 1)))
        poke("port_result_ready", 1); t.step(); poke("port_result_ready", 0)
      }
      waitFor("port_done_valid"); expect("port_done_bits_tag", 1); expect("port_done_bits_error", 0)
      poke("port_done_ready", 1); t.step(); poke("port_done_ready", 0)
      // A second group keeps the SAME hardware, uses transposed routing and
      // two true accumulator updates without reset. No reference injection.
      for (c <- 0 until 256) poke(s"port_step_bits_b_$c", bf(if (c < 128) c + 1 else if (c < 144) c - 111 else 1))
      group(2, true)
      step(0, true, false, false, false, 200)
      step(0, false, true, true, true, 201)
      waitFor("port_result_valid"); expect("port_result_bits_returnTag", 201)
      for (r <- 0 until 16; c <- 0 until 256) {
        val slice = c / 32; val lane = c % 32
        expect(s"port_result_bits_value_${r}_$c", fp(2 * (r + 1 + 16 * (slice / 4)) * (32 * (slice % 4) + lane + 1)))
      }
      poke("port_result_ready", 1); t.step(); poke("port_result_ready", 0)
      waitFor("port_done_valid"); expect("port_done_bits_tag", 2); expect("port_done_bits_error", 0)
      poke("port_done_ready", 1); t.step(); poke("port_done_ready", 0)
      expect("wideSteps", 7); expect("acceptedSteps", 56); expect("resetRequired", 0)
      t.step(8); expect("wideSteps", 7); expect("acceptedSteps", 56)
      // Reset while the service naturally stops all gated clocks.
      t.poke("reset", 1); t.step(2); t.poke("reset", 0)
      expect("acceptedSteps", 0); expect("port_result_valid", 0); expect("resetRequired", 0)
      factory.requireCompleteBinding()
    } finally { t.finish }
  }
}

// SPDX-License-Identifier: Apache-2.0
package heteronpu.experimental

import chisel3._
import chisel3.util._
import hardfloat._
import gemmini.{HeteroBF16FmaMul, HeteroBF16FmaPost, HeteroBF16FmaRound}

/** New full-width front end; the original BF16 configuration is not edited. */
class HeteroFullFp32FmaPre extends RawModule {
  val io = IO(new Bundle {
    val a = Input(UInt(32.W)); val b = Input(UInt(32.W)); val c = Input(UInt(32.W))
    val mulAddA = Output(UInt(24.W)); val mulAddB = Output(UInt(24.W))
    val mulAddC = Output(UInt(48.W)); val meta = Output(UInt(54.W))
  })
  val pre = Module(new MulAddRecFNToRaw_preMul(8, 24))
  pre.io.op := 0.U
  pre.io.a := recFNFromFN(8, 24, io.a)
  pre.io.b := recFNFromFN(8, 24, io.b)
  pre.io.c := recFNFromFN(8, 24, io.c)
  require(pre.io.toPostMul.getWidth == 54)
  io.mulAddA := pre.io.mulAddA; io.mulAddB := pre.io.mulAddB
  io.mulAddC := pre.io.mulAddC; io.meta := pre.io.toPostMul.asUInt
}

object StrictFp32LaneMode {
  val LegacyBf16Fma = 0
  val StrictFp32MulAdd = 1
}
object StrictFp32LaneStatus {
  val Ok = 0; val BadMode = 1; val BadEncoding = 2
  val NonFiniteInput = 3; val MulFatal = 4; val AddFatal = 5
}
class StrictFp32LaneRequest extends Bundle {
  val tag = UInt(32.W); val mode = UInt(2.W)
  val a = UInt(32.W); val b = UInt(32.W); val acc = UInt(32.W)
}
class StrictFp32LaneResponse extends Bundle {
  val tag = UInt(32.W); val mode = UInt(2.W); val status = UInt(3.W)
  val product = UInt(32.W); val productValid = Bool()
  val value = UInt(32.W); val valueValid = Bool(); val accCommit = Bool()
  val mulFlags = UInt(5.W); val mulFlagsValid = Bool()
  val addFlags = UInt(5.W); val addFlagsValid = Bool()
  val fmaFlags = UInt(5.W); val fmaFlagsValid = Bool()
  val passesCompleted = UInt(2.W)
}

/** Isolated single-request experiment, NOT an integrated Matrix endpoint.
  * ONE original Mul/Post/Round chain is traversed twice in strict mode.
  * No persistent accumulator bank, external transport, service or second ALU.
  * The request's acc is unchanged; only successful reply.accCommit proposes a
  * new accumulator. A future owner must preserve ascending K itself.
  * HardFloat's original RNE and unbounded-exponent after-rounding tininess are
  * retained; no delivered-result-exponent approximation is inserted here.
  */
class StrictFp32MatrixLane extends Module {
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new StrictFp32LaneRequest))
    val result = Decoupled(new StrictFp32LaneResponse)
    val busy = Output(Bool())
  })
  val idle :: preStep :: mulStep :: postStep :: roundStep :: replyStep :: Nil = Enum(6)
  val state = RegInit(idle)
  val job = RegInit(0.U.asTypeOf(new StrictFp32LaneRequest))
  val reply = RegInit(0.U.asTypeOf(new StrictFp32LaneResponse))
  val addPass = RegInit(false.B)
  val preA = RegInit(0.U(24.W)); val preB = RegInit(0.U(24.W))
  val preC = RegInit(0.U(48.W)); val preMeta = RegInit(0.U(54.W))
  val mulValue = RegInit(0.U(49.W)); val mulMeta = RegInit(0.U(54.W))
  val postRaw = RegInit(0.U(41.W)); val postInvalid = RegInit(false.B)

  // No original BF16 Pre or separate full Mul/Add is instantiated in parallel.
  val pre = Module(new HeteroFullFp32FmaPre)
  val mul = Module(new HeteroBF16FmaMul)
  val post = Module(new HeteroBF16FmaPost)
  val round = Module(new HeteroBF16FmaRound)
  val legacy = job.mode === StrictFp32LaneMode.LegacyBf16Fma.U
  val activePre = state === preStep && !reset.asBool
  val signedProductZero = Cat(job.a(31) ^ job.b(31), 0.U(31.W))
  pre.io.a := Mux(activePre,
    Mux(legacy, Cat(job.a(15, 0), 0.U(16.W)), Mux(addPass, reply.product, job.a)), 0.U)
  pre.io.b := Mux(activePre,
    Mux(legacy, Cat(job.b(15, 0), 0.U(16.W)), Mux(addPass, "h3f800000".U(32.W), job.b)), 0.U)
  pre.io.c := Mux(activePre, Mux(legacy || addPass, job.acc, signedProductZero), 0.U)
  mul.io.mulAddA := preA; mul.io.mulAddB := preB; mul.io.mulAddC := preC
  post.io.meta := mulMeta; post.io.mulAddResult := mulValue
  round.io.raw := postRaw; round.io.invalid := postInvalid
  def finite(x: UInt): Bool = x(30, 23) =/= 255.U
  val fatal = round.io.exceptionFlags(4, 1).orR || !finite(round.io.out)

  // Reset edges cannot be observed as accepted or retired handshakes.
  io.request.ready := state === idle && !reset.asBool
  io.result.valid := state === replyStep && !reset.asBool
  io.result.bits := reply
  io.busy := state =/= idle && !reset.asBool

  when(io.request.fire) {
    val r = io.request.bits
    job := r; addPass := false.B
    reply := 0.U.asTypeOf(new StrictFp32LaneResponse)
    reply.tag := r.tag; reply.mode := r.mode
    when(r.mode > StrictFp32LaneMode.StrictFp32MulAdd.U) {
      reply.status := StrictFp32LaneStatus.BadMode.U; state := replyStep
    }.elsewhen(r.mode === StrictFp32LaneMode.LegacyBf16Fma.U &&
      (r.a(31, 16).orR || r.b(31, 16).orR)) {
      reply.status := StrictFp32LaneStatus.BadEncoding.U; state := replyStep
    }.elsewhen(r.mode === StrictFp32LaneMode.StrictFp32MulAdd.U &&
      (!finite(r.a) || !finite(r.b) || !finite(r.acc))) {
      // Rejected inputs did NOT execute arithmetic: no synthetic NV flag.
      reply.status := StrictFp32LaneStatus.NonFiniteInput.U; state := replyStep
    }.otherwise { state := preStep }
  }
  when(state === preStep) {
    preA := pre.io.mulAddA; preB := pre.io.mulAddB
    preC := pre.io.mulAddC; preMeta := pre.io.meta; state := mulStep
  }
  when(state === mulStep) {
    mulValue := mul.io.mulAddResult; mulMeta := preMeta; state := postStep
  }
  when(state === postStep) {
    postRaw := post.io.raw; postInvalid := post.io.invalid; state := roundStep
  }
  when(state === roundStep) {
    when(legacy) {
      // Raw legacy IEEE result, not the strict GDN finite/fatal policy.
      reply.value := round.io.out; reply.valueValid := true.B
      reply.fmaFlags := round.io.exceptionFlags; reply.fmaFlagsValid := true.B
      reply.passesCompleted := 1.U; reply.accCommit := true.B
      state := replyStep
    }.elsewhen(!addPass) {
      reply.product := round.io.out; reply.productValid := true.B
      reply.mulFlags := round.io.exceptionFlags; reply.mulFlagsValid := true.B
      reply.passesCompleted := 1.U
      when(fatal) {
        reply.status := StrictFp32LaneStatus.MulFatal.U; state := replyStep
      }.otherwise {
        // Registered rounded product, same arithmetic chain, original acc.
        addPass := true.B; state := preStep
      }
    }.otherwise {
      reply.value := round.io.out; reply.valueValid := true.B
      reply.addFlags := round.io.exceptionFlags; reply.addFlagsValid := true.B
      reply.passesCompleted := 2.U
      when(fatal) { reply.status := StrictFp32LaneStatus.AddFatal.U }
        .otherwise { reply.accCommit := true.B }
      state := replyStep
    }
  }
  when(io.result.fire) { state := idle }
}

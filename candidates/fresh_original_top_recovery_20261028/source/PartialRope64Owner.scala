// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Internal decoded job, not a Host command encoding. BF16 tensors have shape
  * [tokens,heads,256]. Trig is BF16 [trigTokens,64], with cos[0:32] then
  * sin[0:32]. Token t uses trig[positionBase+t], shared across its heads.
  */
class PartialRope64Job extends Bundle {
  val tokens = UInt(16.W)
  val heads = UInt(16.W)
  val headDim = UInt(16.W)
  val rotaryDim = UInt(16.W)
  val policy = UInt(8.W)
  val input = UInt(64.W)
  val trig = UInt(64.W)
  val output = UInt(64.W)
  val positionBase = UInt(32.W)
  val trigTokens = UInt(32.W)
  val tag = UInt(32.W)
}

class PartialRope64Result extends Bundle {
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val outputCommitted = Bool()
  // NV,DZ,OF,UF,NX. Successful jobs may retain NX; bits[4:1] are fatal.
  val exceptionFlags = UInt(5.W)
}

class PartialRope64OwnerPort extends Bundle {
  val job = Flipped(Decoupled(new PartialRope64Job))
  val done = Decoupled(new PartialRope64Result)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  // The external shared Scalar must hold these together with result/error.
  val scalarFlags = Input(UInt(5.W))
  val scalarFlagsValid = Input(Bool())
  val resetRequired = Output(Bool())
}

/** Exact fp32_to_bf16_rne_candidate.sv encoding and flags. This is deliberately
  * separate from FP32 HardFloat tininess and TensorMath's flag-free cast.
  */
object PartialRope64Math {
  def bf16RneFlags(x: UInt): (UInt, UInt) = {
    val discarded = x(15, 0).orR
    val increment = x(15) && (x(14, 0).orR || x(16))
    val rounded = (x(31, 16) + increment)(15, 0)
    val result = WireDefault(rounded)
    val flags = WireDefault(0.U(5.W))
    when(x(30, 23) === 255.U) {
      when(x(22, 0).orR) {
        result := "h7fc0".U
        flags := Mux(x(22), 0.U, 16.U)
      }.otherwise { result := Cat(x(31), 255.U(8.W), 0.U(7.W)) }
    }.otherwise {
      flags := Cat(0.U(3.W), discarded && rounded(14, 7) === 0.U, discarded)
      when(rounded(14, 7) === 255.U) { flags := 5.U }
    }
    (result, flags)
  }
}

/** Partial64 split-half RoPE, using only the external shared Scalar Add0/Mul1.
  * Per pair (i,i+32): four separate FP32 products ec,os,es,oc, each rounded
  * to BF16 then widened; FP32 ec-signflip(os) and es+oc, each rounded to BF16.
  * The six conversion boundaries and operation order are frozen. No FMA,
  * reciprocal, Matrix, SFU or memory transport is instantiated here.
  *
  * One head is buffered; its untouched 192-element tail is copied bit for bit,
  * including nonfinite encodings. Only arithmetic inputs must be finite.
  * Every write is aligned/full64 and output is disjoint from both full input
  * and trig allocations. Only the final matching write ACK commits output.
  * Any error locks new jobs until reset. Reset must reset/drain the external
  * Scalar and memory transport as well; acknowledged staging writes persist.
  */
class PartialRope64Owner(maxHeads: Int = 8, maxTokens: Int = 128) extends Module {
  require(maxHeads >= 1 && maxHeads <= 8)
  require(maxTokens >= 1 && maxTokens <= 65535)
  val io = IO(new PartialRope64OwnerPort)
  val idle :: readTrig :: waitTrig :: readInput :: waitInput :: scalarIssue :: scalarWait :: writeOutput :: waitOutput :: finish :: locked :: Nil = Enum(11)
  val state = RegInit(idle)
  val mulEc :: mulOs :: mulEs :: mulOc :: sumEven :: sumOdd :: Nil = Enum(6)
  val operation = RegInit(mulEc)
  val job = Reg(new PartialRope64Job)
  val coefficients = Reg(Vec(2, UInt(512.W)))
  val input = Reg(Vec(8, UInt(512.W)))
  val evenOutput = Reg(Vec(32, UInt(16.W)))
  val oddOutput = Reg(Vec(32, UInt(16.W)))
  val products = Reg(Vec(4, UInt(16.W)))
  val token = RegInit(0.U(16.W))
  val head = RegInit(0.U(16.W))
  val beat = RegInit(0.U(3.W))
  val pair = RegInit(0.U(5.W))
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))
  val flags = RegInit(0.U(5.W))

  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.tag := job.tag
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.outputCommitted := state === finish && status === Status.Ok.U
  io.done.bits.exceptionFlags := flags
  io.resetRequired := status =/= Status.Ok.U

  val headOffset = ((token * job.heads).pad(64) + head.pad(64)) << 9
  val beatOffset = beat.pad(64) << 6
  val trigOffset = (job.positionBase.pad(65) + token.pad(65)) << 7
  io.memory.valid := state === readTrig || state === readInput || state === writeOutput
  io.memory.bits.write := state === writeOutput
  io.memory.bits.address := MuxLookup(state, job.input + headOffset + beatOffset)(Seq(
    readTrig -> (job.trig + trigOffset + beatOffset),
    writeOutput -> (job.output + headOffset + beatOffset)))
  io.memory.bits.data := Mux(state === writeOutput,
    MuxLookup(beat, input(beat))(Seq(0.U -> evenOutput.asUInt, 1.U -> oddOutput.asUInt)), 0.U)
  io.memory.bits.mask := Mux(state === writeOutput, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitTrig || state === waitInput || state === waitOutput

  val even = Cat(input(0).asTypeOf(Vec(32, UInt(16.W)))(pair), 0.U(16.W))
  val odd = Cat(input(1).asTypeOf(Vec(32, UInt(16.W)))(pair), 0.U(16.W))
  val cos = Cat(coefficients(0).asTypeOf(Vec(32, UInt(16.W)))(pair), 0.U(16.W))
  val sin = Cat(coefficients(1).asTypeOf(Vec(32, UInt(16.W)))(pair), 0.U(16.W))
  def widened(index: Int): UInt = Cat(products(index), 0.U(16.W))
  io.scalar.request.valid := state === scalarIssue
  io.scalar.request.bits.op := Mux(operation < sumEven, ScalarOp.Mul.U, ScalarOp.Add.U)
  io.scalar.request.bits.a := MuxLookup(operation, even)(Seq(
    mulOs -> odd, mulOc -> odd, sumEven -> widened(0), sumOdd -> widened(2)))
  io.scalar.request.bits.b := MuxLookup(operation, cos)(Seq(
    mulOs -> sin, mulEs -> sin,
    sumEven -> (widened(1) ^ "h80000000".U), sumOdd -> widened(3)))
  io.scalar.result.ready := state === scalarWait
  val (roundedScalarResult, conversionFlags) = PartialRope64Math.bf16RneFlags(io.scalar.result.bits)

  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }
  when(io.job.fire) {
    job := io.job.bits
    token := 0.U; head := 0.U; beat := 0.U; pair := 0.U; operation := mulEc
    sequence := 0.U; status := Status.Ok.U; bytes := 0.U; cycles := 0.U; flags := 0.U
    val j = io.job.bits
    val vectorBytes = ((j.tokens * j.heads) << 9).pad(65)
    val trigBytes = (j.trigTokens << 7).pad(65)
    val positionEnd = j.positionBase.pad(65) + j.tokens.pad(65)
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || (base.pad(65) +& size) > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = badSpan(j.input, vectorBytes) || badSpan(j.trig, trigBytes) || badSpan(j.output, vectorBytes)
    val unsafeWrites = overlap(j.output, vectorBytes, j.input, vectorBytes) ||
      overlap(j.output, vectorBytes, j.trig, trigBytes)
    when(j.tokens === 0.U || j.tokens > maxTokens.U || j.heads === 0.U || j.heads > maxHeads.U ||
      j.headDim =/= 256.U || j.rotaryDim =/= 64.U || j.policy =/= "hb1".U ||
      positionEnd > j.trigTokens.pad(65) || badAddress || unsafeWrites) {
      fail(Status.Bounds.U)
    }.otherwise { state := readTrig }
  }
  when(io.memory.fire) {
    state := MuxLookup(state, waitInput)(Seq(readTrig -> waitTrig, writeOutput -> waitOutput))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        when(state === waitTrig || state === waitInput) {
          val nonfinite = (0 until 32).map(i => r.data(i * 16 + 14, i * 16 + 7) === 255.U).reduce(_ || _)
          when(state === waitTrig) { coefficients(beat(0)) := r.data }
            .otherwise { input(beat) := r.data }
          when(nonfinite && (state === waitTrig || beat < 2.U)) { fail(Status.Numerical.U) }
            .elsewhen(state === waitTrig && beat === 1.U) { beat := 0.U; state := readInput }
            .elsewhen(state === waitInput && beat === 7.U) {
              beat := 0.U; pair := 0.U; operation := mulEc; state := scalarIssue
            }.otherwise { beat := beat + 1.U; state := Mux(state === waitTrig, readTrig, readInput) }
        }
        when(state === waitOutput) {
          bytes := bytes + 64.U
          when(beat === 7.U) {
            beat := 0.U
            when(head +& 1.U === job.heads) {
              head := 0.U
              when(token +& 1.U === job.tokens) { state := finish }
                .otherwise { token := token + 1.U; state := readTrig }
            }.otherwise { head := head + 1.U; state := readInput }
          }.otherwise { beat := beat + 1.U; state := writeOutput }
        }
      }
  }
  when(io.scalar.request.fire) { state := scalarWait }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits
    val rounded = roundedScalarResult
    val combinedFlags = io.scalarFlags | conversionFlags
    when(!io.scalarFlagsValid) { fail(Status.Protocol.U) }
      .otherwise {
        flags := flags | combinedFlags
        when(io.scalar.error || combinedFlags(4, 1).orR || !TensorMath.finite(r) || rounded(14, 7) === 255.U) {
          fail(Status.Numerical.U)
        }.otherwise {
          state := scalarIssue
          switch(operation) {
            is(mulEc) { products(0) := rounded; operation := mulOs }
            is(mulOs) { products(1) := rounded; operation := mulEs }
            is(mulEs) { products(2) := rounded; operation := mulOc }
            is(mulOc) { products(3) := rounded; operation := sumEven }
            is(sumEven) { evenOutput(pair) := rounded; operation := sumOdd }
            is(sumOdd) {
              oddOutput(pair) := rounded
              when(pair === 31.U) { beat := 0.U; state := writeOutput }
                .otherwise { pair := pair + 1.U; operation := mulEc }
            }
          }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}

// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Private runtime shape, never Host authority. BF16 tensors are
  * [tokens,heads,256]; trig is [trigTokens,64], cos[0:32] then sin[0:32].
  * The same fixed owner supports Q8/Q16 and K2. No profile constructor exists.
  * Full-width heads are retained here: no narrowing can turn bad geometry into
  * a valid head count. Full Host/txn64/epoch/owner provenance belongs to the
  * original Guard/Prefix and tagged Scalar8 adapter, not this raw client tag.
  */
class PartialRopeRuntimeJobV12 extends Bundle {
  val tokens = UInt(16.W)
  val role = UInt(2.W)
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
object PartialRopeRuntimeJobV12 {
  def fromOwner(j:QwenOwnerJob):PartialRopeRuntimeJobV12={
    val r=Wire(new PartialRopeRuntimeJobV12)
    r.tokens:=j.m;r.role:=j.qkRole;r.heads:=j.n;r.headDim:=j.k;r.rotaryDim:=64.U
    // Explicit decoded per-kind policy; a raw port cannot manufacture B1.
    r.policy:=j.qkNormPolicy;r.input:=j.a;r.trig:=j.b;r.output:=j.dst
    r.positionBase:=j.qkPositionBase;r.trigTokens:=j.qkTrigTokens;r.tag:=j.tag
    r
  }
}
class PartialRopeRuntimeResultV12 extends Bundle {
  val accepted = new PartialRopeRuntimeJobV12
  val scalarAccepted = UInt(32.W)
  val scalarReturned = UInt(32.W)
  val memoryAccepted = UInt(32.W)
  val memoryReturned = UInt(32.W)
  val outputAckBytes = UInt(64.W)
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val outputCommitted = Bool()
  val exceptionFlags = UInt(5.W)
}
class PartialRopeRuntimePortV12 extends Bundle {
  val job = Flipped(Decoupled(new PartialRopeRuntimeJobV12))
  val done = Decoupled(new PartialRopeRuntimeResultV12)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new UnifiedScalarClientV2
  val parentFault = Input(Bool())
  val resourcesDrained = Output(Bool())
  val resetRequired = Output(Bool())
}
object PartialRopeRuntimeAbiV12 {
  val MaxTokens=128
  val MaxQueryHeads=16
  val ScalarOperationsPerHead=192
}
/** Exact frozen PartialRope64Owner six-operation numerical recipe:
  * mulEc, mulOs, mulEs, mulOc, sumEven, sumOdd. EVERY returned FP32 node
  * materializes BF16 by the original PartialRope64Math.bf16RneFlags before
  * reuse. No FMA, reassociation, approximate arithmetic or formatter is added.
  * The last 192 BF16 elements are copied opaque, including nonfinite bits.
  *
  * Fixed payload is trig2*512 + input8*512 + output2*32*16 + products4*16
  * = 6208 bits, independent of runtime Q8/Q16/K2. There is no new FPU,
  * Matrix, DMA or service instance. Each success requires exactly
  * M*heads*192 Scalar8 requests/returns, M*(2+16*heads) memory accepts/returns
  * and M*heads*512 successful output write ACK bytes.
  *
  * A late fault cannot retract an exposed request; accepted debt drains only
  * on its matching real response. Unknown returns are quarantined and never
  * retire debt. Later known replies can still drain, but unknown quarantine
  * requires joint transport reset; no local recovery/finite-drain claim.
  */
class PartialRopeRuntimeOwnerV12 extends Module {
  val io = IO(new PartialRopeRuntimePortV12)
  val idle :: readTrig :: waitTrig :: readInput :: waitInput :: scalarIssue :: scalarWait :: writeOutput :: waitOutput :: finish :: report :: locked :: Nil = Enum(12)
  val state = RegInit(idle)
  val mulEc :: mulOs :: mulEs :: mulOc :: sumEven :: sumOdd :: Nil = Enum(6)
  val operation = RegInit(mulEc)
  val job = Reg(new PartialRopeRuntimeJobV12)
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
  val poison = RegInit(false.B)
  val drainUnknown = RegInit(false.B)
  val memoryAccepted = RegInit(0.U(32.W))
  val scalarAccepted = RegInit(0.U(32.W))
  val scalarReturned = RegInit(0.U(32.W))
  val terminal = Reg(new PartialRopeRuntimeResultV12)

  val memoryOffer=state===readTrig || state===readInput || state===writeOutput
  val memoryDebt=state===waitTrig || state===waitInput || state===waitOutput
  val scalarDebt=state===scalarWait
  val requestPolicy=UnifiedScalarPolicyV2.Legacy.U(2.W)
  val expectedTag=Cat(job.tag,sequence)
  val unknownMemory=io.response.valid && (!memoryDebt || io.response.bits.tag=/=expectedTag)
  val unknownScalar=io.scalar.result.valid && (!scalarDebt || io.scalar.result.bits.policy=/=requestPolicy)
  val unknown=unknownMemory || unknownScalar
  val currentFault=io.parentFault || unknown
  when(unknown){drainUnknown:=true.B}
  when(currentFault){
    poison:=true.B
    when(state=/=report && state=/=locked && status===Status.Ok.U){status:=Status.Protocol.U}
  }
  val quiet= !io.response.valid && !io.scalar.result.valid
  val noService= !memoryOffer && !memoryDebt && state=/=scalarIssue && !scalarDebt
  io.resourcesDrained:=noService && quiet && !drainUnknown && !unknown
  io.job.ready:=state===idle && !poison && !currentFault && quiet
  io.done.valid:=state===report;io.done.bits:=terminal
  io.resetRequired:=status=/=Status.Ok.U || poison || drainUnknown || currentFault
  val rows=job.tokens.pad(64)*job.heads.pad(64)
  val expectedScalar=(rows*PartialRopeRuntimeAbiV12.ScalarOperationsPerHead.U)(31,0)
  val expectedMemory=(job.tokens.pad(64)*(2.U+job.heads.pad(64)*16.U))(31,0)
  val expectedBytes=(rows<<9)(63,0)

  val headOffset = ((token * job.heads).pad(64) + head.pad(64)) << 9
  val beatOffset = beat.pad(64) << 6
  val trigOffset = (job.positionBase.pad(65) + token.pad(65)) << 7
  val memoryHeld=HeldDecoupledOffer(memoryOffer,io.memory.ready,poison || currentFault || drainUnknown)
  io.memory.valid:=memoryHeld.valid
  io.memory.bits.write := state === writeOutput
  io.memory.bits.address := MuxLookup(state, job.input + headOffset + beatOffset)(Seq(
    readTrig -> (job.trig + trigOffset + beatOffset),
    writeOutput -> (job.output + headOffset + beatOffset)))
  io.memory.bits.data := Mux(state === writeOutput,
    MuxLookup(beat, input(beat))(Seq(0.U -> evenOutput.asUInt, 1.U -> oddOutput.asUInt)), 0.U)
  io.memory.bits.mask := Mux(state === writeOutput, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  // A sticky unknown quarantine is not permission to erase a known debt.
  // Unlike a new request, its exact matching response may continue to drain.
  io.response.ready:=memoryDebt && !unknownMemory

  val even = Cat(input(0).asTypeOf(Vec(32, UInt(16.W)))(pair), 0.U(16.W))
  val odd = Cat(input(1).asTypeOf(Vec(32, UInt(16.W)))(pair), 0.U(16.W))
  val cos = Cat(coefficients(0).asTypeOf(Vec(32, UInt(16.W)))(pair), 0.U(16.W))
  val sin = Cat(coefficients(1).asTypeOf(Vec(32, UInt(16.W)))(pair), 0.U(16.W))
  def widened(index: Int): UInt = Cat(products(index), 0.U(16.W))
  val scalarHeld=HeldDecoupledOffer(state===scalarIssue,io.scalar.request.ready,poison || currentFault || drainUnknown)
  io.scalar.request.valid:=scalarHeld.valid
  io.scalar.request.bits.policy:=requestPolicy
  io.scalar.request.bits.payload.op := Mux(operation < sumEven, ScalarOp.Mul.U, ScalarOp.Add.U)
  io.scalar.request.bits.payload.a := MuxLookup(operation, even)(Seq(
    mulOs -> odd, mulOc -> odd, sumEven -> widened(0), sumOdd -> widened(2)))
  io.scalar.request.bits.payload.b := MuxLookup(operation, cos)(Seq(
    mulOs -> sin, mulEs -> sin,
    sumEven -> (widened(1) ^ "h80000000".U), sumOdd -> widened(3)))
  io.scalar.result.ready:=scalarDebt && !unknownScalar
  val (roundedScalarResult, conversionFlags) = PartialRope64Math.bf16RneFlags(io.scalar.result.bits.value)

  when(state=/=idle && state=/=report && state=/=locked){cycles:=cycles+1.U}
  def fail(code:UInt):Unit={
    when(status===Status.Ok.U){status:=code}
    poison:=true.B;state:=finish
  }
  // Only an intent never made visible may be abandoned. Held payload and
  // issue-state counters remain unchanged until that original request fires.
  when(poison || currentFault || drainUnknown){
    when(memoryOffer && !memoryHeld.held && !io.memory.fire){state:=finish}
    when(state===scalarIssue && !scalarHeld.held && !io.scalar.request.fire){state:=finish}
  }
  when(io.job.fire) {
    job := io.job.bits
    token := 0.U; head := 0.U; beat := 0.U; pair := 0.U; operation := mulEc
    sequence := 0.U; status := Status.Ok.U; bytes := 0.U; cycles := 0.U; flags := 0.U
    memoryAccepted:=0.U;scalarAccepted:=0.U;scalarReturned:=0.U
    val j = io.job.bits
    val vectorBytes = (j.tokens.pad(66) * j.heads) << 9
    val trigBytes = j.trigTokens.pad(66) << 7
    val positionEnd = j.positionBase.pad(66) + j.tokens.pad(66)
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || base.pad(66) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = badSpan(j.input, vectorBytes) || badSpan(j.trig, trigBytes) || badSpan(j.output, vectorBytes)
    val unsafeWrites = overlap(j.output, vectorBytes, j.input, vectorBytes) ||
      overlap(j.output, vectorBytes, j.trig, trigBytes)
    val badHeads=Mux(j.role===0.U,j.heads=/=8.U && j.heads=/=16.U,j.heads=/=2.U)
    when(j.tokens===0.U || j.tokens>PartialRopeRuntimeAbiV12.MaxTokens.U || j.role>1.U || badHeads ||
      j.headDim=/=256.U || j.rotaryDim=/=64.U || j.policy=/="hb1".U ||
      positionEnd>j.trigTokens.pad(66) || badAddress || unsafeWrites){
      fail(Status.Bounds.U)
    }.otherwise { state := readTrig }
  }
  when(io.memory.fire) {
    memoryAccepted:=memoryAccepted+1.U
    state := MuxLookup(state, waitInput)(Seq(readTrig -> waitTrig, writeOutput -> waitOutput))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(sequence=/="hffffffff".U){sequence:=sequence+1.U}
    // Physical matching write success is an ACK even after independent fault;
    // it is retained as evidence but never converts a failed job to success.
    when(state===waitOutput && !r.error){bytes:=bytes+64.U}
    when(sequence==="hffffffff".U){fail(Status.Protocol.U)}
      .elsewhen(r.error){fail(Status.Memory.U)}
      .elsewhen(poison || currentFault || drainUnknown){state:=finish}
      .otherwise {
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
  when(io.scalar.request.fire){scalarAccepted:=scalarAccepted+1.U;state:=scalarWait}
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits.value
    val rounded = roundedScalarResult
    val combinedFlags = io.scalar.result.bits.flags | conversionFlags
    scalarReturned:=scalarReturned+1.U
    when(io.scalar.result.bits.primitiveFlagsValid){flags:=flags | combinedFlags}
    when(poison || currentFault || drainUnknown){state:=finish}
      .elsewhen(!io.scalar.result.bits.primitiveFlagsValid){fail(Status.Protocol.U)}
      .otherwise {
        when(io.scalar.result.bits.error || combinedFlags(4, 1).orR || !TensorMath.finite(r) || rounded(14, 7) === 255.U) {
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
  when(state===finish && io.resourcesDrained){
    val exact=memoryAccepted===expectedMemory && sequence===expectedMemory &&
      scalarAccepted===expectedScalar && scalarReturned===expectedScalar && bytes===expectedBytes
    val complete=status===Status.Ok.U && !poison && !currentFault && exact
    terminal.accepted:=job;terminal.tag:=job.tag
    terminal.status:=Mux(status===Status.Ok.U && (!exact || poison || currentFault),Status.Protocol.U,status)
    terminal.writeBytes:=bytes;terminal.outputAckBytes:=bytes;terminal.cycles:=cycles
    terminal.outputCommitted:=complete;terminal.exceptionFlags:=flags
    terminal.scalarAccepted:=scalarAccepted;terminal.scalarReturned:=scalarReturned
    terminal.memoryAccepted:=memoryAccepted;terminal.memoryReturned:=sequence
    when(status===Status.Ok.U && !exact){poison:=true.B}
    state:=report
  }
  // Terminal snapshot is immutable under consumer backpressure/late fault.
  // Original parent still applies its same-cycle fault veto before publication.
  when(io.done.fire){state:=Mux(io.resetRequired || terminal.status=/=Status.Ok.U,locked,idle)}
  assert(PopCount(Seq(io.memory.valid,io.scalar.request.valid))<=1.U)
}

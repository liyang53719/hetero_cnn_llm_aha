// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Q is [token,qHead,Q256+gate256], K is [token,kvHead,K256].
  * Original BF16 weights [256] are shared across heads. Output and the separate
  * Q gate output are contiguous [token,head,256] BF16 staging allocations.
  */
class QkNormRuntimeJobV11 extends Bundle {
  val tokens = UInt(16.W)
  val role = UInt(2.W)
  // Internal ABI v2: accepted profile supplies Q=8|16, K=2.
  val heads = UInt(6.W)
  val headDim = UInt(16.W)
  val policy = UInt(8.W)
  val epsilon = UInt(32.W)
  val input = UInt(64.W)
  val weight = UInt(64.W)
  val output = UInt(64.W)
  val gateOutput = UInt(64.W)
  val tag = UInt(32.W)
}

object QkNormRuntimeJobV11 {
  /** Internal mapping only; original Commands/Guard prove full-width shape and
    * producer provenance before this physical owner accepts the request. */
  def fromOwner(j:QwenOwnerJob):QkNormRuntimeJobV11={
    val x=Wire(new QkNormRuntimeJobV11)
    x.tokens:=j.m;x.role:=j.qkRole;x.heads:=j.n(5,0);x.headDim:=j.k
    x.policy:=j.qkNormPolicy;x.epsilon:="h358637bd".U
    x.input:=j.a;x.weight:=j.b;x.output:=j.dst;x.gateOutput:=j.c;x.tag:=j.tag
    x
  }
}
class QkNormRuntimeResultV11 extends Bundle {
  val accepted = new QkNormRuntimeJobV11
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
  // Frozen candidate statuses: 0 OK, 1 descriptor, 2 nonfinite operand,
  // 3 unsupported finite operand range, 4 arithmetic/domain failure.
  // A transport failure is carried by status and leaves normStatus unchanged.
  val normStatus = UInt(4.W)
  val exceptionFlags = UInt(5.W)
  val lastMeanEps = UInt(32.W)
  val lastInverse = UInt(32.W)
}

class QkNormRuntimePortV11 extends Bundle {
  val job = Flipped(Decoupled(new QkNormRuntimeJobV11))
  val done = Decoupled(new QkNormRuntimeResultV11)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  // Exactly one existing Scalar8 service; flags belong to its captured result,
  // never the current primitive wires. No formatter or extra arithmetic port.
  val scalar = new UnifiedScalarClientV2
  val parentFault = Input(Bool())
  val resourcesDrained = Output(Bool())
  val resetRequired = Output(Bool())
}

/** Serialized owner of the frozen C1 qk_norm256_bf16_candidate recipe.
  * It instantiates no Scalar, Matrix, SFU or DMA arithmetic. Each C1 square,
  * tree edge, running addition, mean/epsilon, PWL/Newton node and output node
  * is one request to the existing shared BlockScalarFloat using Add0/Mul1.
  *
  * The 16 squares of each chunk feed its balanced 8/4/2/1 addition tree; the
  * 16 roots are accumulated in chunk order from +0. The rsqrt ROM and eight
  * individually rounded nodes below are literal fp32_rsqrt_nr.sv semantics.
  * No sqrt, divide, FMA, reassociation, intermediate BF16 cast or new threshold
  * is substituted in C1. Gamma is FP32(1 + original BF16 weight).
  *
  * C1 and C2 (Torch210CpuDefault256) are always physically present.
  * The accepted job policy selects them at runtime; no per-model elaboration. It serially reduces eight lanes of four residues,
  * each residue summing eight separately rounded squares from +0 at indices
  * 32*t + 8*residue + vectorLane. Fold residues 0..3, then lanes 0..7 from +0.
  * Mean and epsilon remain FP32; existing Sqrt3 then Div2(1, root) replace the
  * C1 inverse nodes. Gamma, normalized/weighted FP32 nodes and final BF16 RNE
  * remain identical. There is no native-oracle operand or intermediate cast.
  *
  * Only signed zeros and BF16 exponents 95..158 are arithmetic operands.
  * Nonfinite rejection takes priority over finite range rejection per head,
  * including its weights. Q gates are opaque 16-bit payloads, never operands.
  * Actual Add/Mul flags and destination BF16 conversion flags are ORed for
  * the job. C2 Sqrt/Div expose error/result only; their unobservable raw flags
  * are not synthesized or added to exceptionFlags. A runtime fault retains
  * observed flags and uncommitted staging writes.
  * All norm AND gate write ACKs fence commit. Any failure locks until the same
  * reset also resets/drains the shared Scalar and memory transport.
  */
object QkNormRuntimeAbiV11 {
  val Version = 2
  val MaxTokens = 128
  val MaxQueryHeads = 16
}
/** Runtime installation of the pinned r3 owner: C1/C2 arithmetic, operand
  * mapping, ROM, lane order and integer BF16 RNE below are unchanged. Only
  * transport ownership, captured flags, drain and terminal evidence are added.
  * Q uses 8+32*M*heads memory ACKs; K uses 8+16*M*heads. Scalar success is
  * exactly M*heads*(C1:1290 | C2:1316), never inferred from the maximum cap.
  * Fixed payload is four BF16[256] banks plus FP32[16] reduction scratch;
  * counters and the accepted/terminal snapshots are explicit extra metadata.
  */
class QkNormRuntimeOwnerV11 extends Module {
  val io = IO(new QkNormRuntimePortV11)
  val idle :: readWeight :: waitWeight :: readInput :: waitInput :: scalarIssue :: scalarWait :: writeNorm :: waitNorm :: writeGate :: waitGate :: finish :: report :: locked :: Nil = Enum(14)
  val state = RegInit(idle)
  val square :: tree :: running :: mean :: epsilon :: slope :: intercept :: seedSquare :: normProduct :: half :: correction :: newton :: rescale :: gamma :: normalize :: weighted :: torchTermAdd :: torchResidueFold :: torchLaneFold :: torchSqrt :: torchDivide :: Nil = Enum(21)
  val operation = RegInit(square)
  val job = Reg(new QkNormRuntimeJobV11)
  val weights = Reg(Vec(8, UInt(512.W)))
  val input = Reg(Vec(8, UInt(512.W)))
  val gates = Reg(Vec(8, UInt(512.W)))
  val output = Reg(Vec(256, UInt(16.W)))
  // C1 retains its original sixteen-entry tree. C2 reuses entry 0 for the
  // current residue and entry 1 for completed residues of the current lane.
  // No C2 operand reads entries 2..15; neither scratch survives reduction.
  val treeValues = Reg(Vec(16, UInt(32.W)))
  val treeIndex = RegInit(0.U(4.W))
  val treeCount = RegInit(8.U(4.W))
  val token = RegInit(0.U(16.W))
  val head = RegInit(0.U(16.W))
  val beat = RegInit(0.U(4.W))
  val lane = RegInit(0.U(8.W))
  val accumulator = RegInit(0.U(32.W))
  val value = Reg(UInt(32.W))
  val seed = Reg(UInt(32.W))
  val norm = Reg(UInt(32.W))
  val scale = Reg(UInt(32.W))
  val coefficient = Reg(UInt(64.W))
  val invRms = Reg(UInt(32.W))
  val laneGamma = Reg(UInt(32.W))
  val weightNonfinite = RegInit(false.B)
  val weightRange = RegInit(false.B)
  val headNonfinite = RegInit(false.B)
  val headRange = RegInit(false.B)
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val poison = RegInit(false.B)
  val drainUnknown = RegInit(false.B)
  val normStatus = RegInit(0.U(4.W))
  val exceptionFlags = RegInit(0.U(5.W))
  val lastMeanEps = RegInit(0.U(32.W))
  val lastInverse = RegInit(0.U(32.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))

  val terminal=Reg(new QkNormRuntimeResultV11)
  val memoryAccepted=RegInit(0.U(32.W))
  val scalarAccepted=RegInit(0.U(32.W));val scalarReturned=RegInit(0.U(32.W))
  val memoryOffer=state===readWeight || state===readInput || state===writeNorm || state===writeGate
  val memoryDebt=state===waitWeight || state===waitInput || state===waitNorm || state===waitGate
  val scalarDebt=state===scalarWait
  val requestPolicy=UnifiedScalarPolicyV2.Legacy.U(2.W)
  val expectedTag=Cat(job.tag,sequence)
  // Both original shared services capture returns after request.fire. A return
  // offered outside its retained wait state is not a new correlation authority.
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
  val expectedScalar=(rows*Mux(job.policy==="hc2".U,1316.U,1290.U))(31,0)
  val expectedMemory=(8.U+rows*Mux(job.role===0.U,32.U,16.U))(31,0)
  val expectedBytes=Mux(job.role===0.U,rows<<10,rows<<9)

  val useTorchDefault = job.policy === "hc2".U
  val heads = job.heads.pad(16)
  val row = token.pad(64) * heads + head
  val normOffset = row << 9
  val inputOffset = Mux(job.role === 0.U, row << 10, normOffset)
  val beatOffset = beat.pad(64) << 6
  val memoryHeld=HeldDecoupledOffer(memoryOffer,io.memory.ready,poison || currentFault || drainUnknown)
  io.memory.valid:=memoryHeld.valid
  io.memory.bits.write := state === writeNorm || state === writeGate
  io.memory.bits.address := MuxLookup(state, job.input + inputOffset + beatOffset)(Seq(
    readWeight -> (job.weight + beatOffset),
    writeNorm -> (job.output + normOffset + beatOffset),
    writeGate -> (job.gateOutput + normOffset + beatOffset)))
  val outputBeats = output.asUInt.asTypeOf(Vec(8, UInt(512.W)))
  io.memory.bits.data := Mux(state === writeNorm, outputBeats(beat(2, 0)), Mux(state === writeGate, gates(beat(2, 0)), 0.U))
  io.memory.bits.mask := Mux(io.memory.bits.write, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready:=memoryDebt && !drainUnknown && !unknownMemory

  val inputLanes = input(lane(7, 5)).asTypeOf(Vec(32, UInt(16.W)))
  val weightLanes = weights(lane(7, 5)).asTypeOf(Vec(32, UInt(16.W)))
  val x = Cat(inputLanes(lane(4, 0)), 0.U(16.W))
  val w = Cat(weightLanes(lane(4, 0)), 0.U(16.W))
  val treeLeft = Cat(treeIndex(2, 0), 0.U(1.W))
  val scalarHeld=HeldDecoupledOffer(state===scalarIssue,io.scalar.request.ready,poison || currentFault || drainUnknown)
  io.scalar.request.valid:=scalarHeld.valid
  io.scalar.request.bits.policy:=requestPolicy
  val addOperation = operation === tree || operation === running || operation === epsilon ||
    operation === intercept || operation === correction || operation === gamma ||
    operation === torchTermAdd || operation === torchResidueFold || operation === torchLaneFold
  io.scalar.request.bits.payload.op := Mux(operation === torchSqrt, ScalarOp.Sqrt.U,
    Mux(operation === torchDivide, ScalarOp.Div.U, Mux(addOperation, ScalarOp.Add.U, ScalarOp.Mul.U)))
  io.scalar.request.bits.payload.a := MuxLookup(operation, value)(Seq(
    square -> x, tree -> treeValues(treeLeft), running -> accumulator, mean -> accumulator,
    slope -> coefficient(63, 32), normProduct -> norm, half -> "h3f000000".U,
    correction -> "h3fc00000".U, newton -> seed, gamma -> "h3f800000".U,
    normalize -> x, torchTermAdd -> treeValues(0), torchResidueFold -> treeValues(1),
    torchLaneFold -> accumulator, torchDivide -> "h3f800000".U))
  io.scalar.request.bits.payload.b := MuxLookup(operation, value)(Seq(
    square -> x, tree -> treeValues(treeLeft + 1.U), mean -> "h3b800000".U,
    epsilon -> "h358637bd".U, slope -> norm, intercept -> coefficient(31, 0),
    correction -> (value ^ "h80000000".U), rescale -> scale, gamma -> w,
    normalize -> invRms, weighted -> laneGamma, torchSqrt -> 0.U(32.W)))
  io.scalar.result.ready:=scalarDebt && !drainUnknown && !unknownScalar

  val rsqrtCoefficients = VecInit(Seq(
    "bef497b73fbd25ee", "bedfea6b3fb7a7e6", "becdff353fb29dbe", "bebe58e33fadf85e",
    "beb0956f3fa9ab4a", "bea4671b3fa5ac16", "be998f8e3fa1f1fe", "be8fdc3f3f9e758d",
    "be8723d63f9b3066", "be7e88713f981d0c", "be7042093f9536bf", "be6344ec3f92795b",
    "be5769013f8fe140", "be4c8c3f3f8d6b3c", "be42919b3f8b147d", "be3960253f88da83",
    "be2cf3ff3f85bf79", "be1e55123f81dd42", "be11a96c3f7c99f7", "be0698873f7607ef",
    "bdf9ba233f6ff2c6", "bde880283f6a4bc0", "bdd92aee3f650674", "bdcb73013f60185b",
    "bdbf1de73f5b7871", "bdb3fb643f571ef6", "bda9e3563f530530", "bda0b4203f4f2545",
    "bd9851683f4b7a15", "bd90a31d3f47ff1b", "bd8994b63f44b05a", "bd8314903f418a48"
  ).map(h => BigInt(h, 16).U(64.W)))

  when(state=/=idle && state=/=report && state=/=locked){cycles:=cycles+1.U}
  def fail(code:UInt):Unit={
    when(status===Status.Ok.U){status:=code}
    poison:=true.B;state:=finish
  }
  // A late fault cannot retract a published request. Once that exact request
  // fires, its original wait/tag is retained until its matching response drains.
  // A not-yet-published intent is safely abandoned without inventing a return.
  when((poison || currentFault) && !drainUnknown && !unknown){
    when(memoryOffer && !memoryHeld.held && !io.memory.fire){state:=finish}
    when(state===scalarIssue && !scalarHeld.held && !io.scalar.request.fire){state:=finish}
  }
  def rejectNorm(code: UInt): Unit = { normStatus := code; fail(Status.Numerical.U) }
  when(io.job.fire) {
    job := io.job.bits; token := 0.U; head := 0.U; beat := 0.U; lane := 0.U
    sequence := 0.U; status := Status.Ok.U; normStatus := 0.U; bytes := 0.U; cycles := 0.U
    memoryAccepted:=0.U;scalarAccepted:=0.U;scalarReturned:=0.U
    exceptionFlags := 0.U; lastMeanEps := 0.U; lastInverse := 0.U
    weightNonfinite := false.B; weightRange := false.B; headNonfinite := false.B; headRange := false.B
    val j = io.job.bits
    val count = j.heads
    val badHeads = Mux(j.role === 0.U, j.heads =/= 8.U && j.heads =/= 16.U, j.heads =/= 2.U)
    val vectorBytes = (j.tokens.pad(66) * count) << 9
    val inputBytes = Mux(j.role === 0.U, vectorBytes << 1, vectorBytes)
    val weightBytes = 512.U(66.W)
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || base.pad(66) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = badSpan(j.input, inputBytes) || badSpan(j.weight, weightBytes) || badSpan(j.output, vectorBytes) ||
      Mux(j.role === 0.U, badSpan(j.gateOutput, vectorBytes), j.gateOutput =/= 0.U)
    val unsafeNorm = overlap(j.output, vectorBytes, j.input, inputBytes) || overlap(j.output, vectorBytes, j.weight, weightBytes)
    val unsafeGate = j.role === 0.U && (overlap(j.gateOutput, vectorBytes, j.input, inputBytes) ||
      overlap(j.gateOutput, vectorBytes, j.weight, weightBytes) || overlap(j.gateOutput, vectorBytes, j.output, vectorBytes))
    val badPolicy = j.policy =/= "hc1".U && j.policy =/= "hc2".U
    when(j.tokens === 0.U || j.tokens > QkNormRuntimeAbiV11.MaxTokens.U || j.role > 1.U || j.headDim =/= 256.U ||
      j.epsilon =/= "h358637bd".U || badAddress || unsafeNorm || unsafeGate) {
      normStatus := 1.U; fail(Status.Bounds.U)
    }.elsewhen(badHeads || badPolicy) { normStatus := 1.U; fail(Status.Unsupported.U) }
      .otherwise { state := readWeight }
  }
  when(io.memory.fire) {
    memoryAccepted:=memoryAccepted+1.U
    state := MuxLookup(state, waitInput)(Seq(readWeight -> waitWeight, writeNorm -> waitNorm, writeGate -> waitGate))
  }
  def nextHead(): Unit = {
    beat := 0.U
    when(head + 1.U === heads) {
      head := 0.U
      when(token + 1.U === job.tokens) { state := finish }
        .otherwise { token := token + 1.U; state := readInput }
    }.otherwise { head := head + 1.U; state := readInput }
    headNonfinite := weightNonfinite; headRange := weightRange
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(sequence=/="hffffffff".U){sequence:=sequence+1.U}
    // Only a matching actual write response contributes ACK bytes, including
    // a successful write that physically completed after an independent fault.
    when((state===waitNorm || state===waitGate) && !r.error){bytes:=bytes+64.U}
    when(sequence==="hffffffff".U){fail(Status.Protocol.U)}
      .elsewhen(r.error){fail(Status.Memory.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise {
        val arithmeticBeat = state === waitWeight || (state === waitInput && !beat(3))
        val nonfinite = arithmeticBeat && (0 until 32).map(i => r.data(i * 16 + 14, i * 16 + 7) === 255.U).reduce(_ || _)
        val outOfRange = arithmeticBeat && (0 until 32).map { i =>
          val v = r.data(i * 16 + 15, i * 16)
          v(14, 0) =/= 0.U && (v(14, 7) < 95.U || v(14, 7) > 158.U)
        }.reduce(_ || _)
        when(state === waitWeight) {
          weights(beat(2, 0)) := r.data
          weightNonfinite := weightNonfinite || nonfinite; weightRange := weightRange || outOfRange
          when(beat === 7.U) {
            beat := 0.U; state := readInput
            headNonfinite := weightNonfinite || nonfinite; headRange := weightRange || outOfRange
          }.otherwise { beat := beat + 1.U; state := readWeight }
        }
        when(state === waitInput) {
          when(beat(3)) { gates(beat(2, 0)) := r.data }.otherwise { input(beat(2, 0)) := r.data }
          headNonfinite := headNonfinite || nonfinite; headRange := headRange || outOfRange
          when(beat === Mux(job.role === 0.U, 15.U, 7.U)) {
            beat := 0.U
            when(headNonfinite || nonfinite) { rejectNorm(2.U) }
              .elsewhen(headRange || outOfRange) { rejectNorm(3.U) }
              .otherwise {
                accumulator := 0.U; lane := 0.U; operation := square; state := scalarIssue
                when(useTorchDefault) { treeValues(0) := 0.U; treeValues(1) := 0.U }
              }
          }.otherwise { beat := beat + 1.U; state := readInput }
        }
        when(state === waitNorm || state === waitGate) {
          when(beat === 7.U) {
            when(state === waitNorm && job.role === 0.U) { beat := 0.U; state := writeGate }
              .otherwise { nextHead() }
          }.otherwise { beat := beat + 1.U; state := Mux(state === waitNorm, writeNorm, writeGate) }
        }
      }
  }
  when(io.scalar.request.fire){scalarAccepted:=scalarAccepted+1.U;state:=scalarWait}
  when(io.scalar.result.fire) {
    val r=io.scalar.result.bits.value
    scalarReturned:=scalarReturned+1.U
    // Identity/policy correlation is retained by the original tagged adapter.
    // A known return may drain after parent fault but cannot resume arithmetic.
    when(poison || currentFault){state:=finish}
      .otherwise {
    // BlockScalarFloat deliberately has flagsValid=false for Sqrt/Div.
    // Exempt only these two C2 states, never C1 or any primitive Add/Mul.
    val torchInverseOperation = useTorchDefault && (operation === torchSqrt || operation === torchDivide)
    when(!torchInverseOperation && !io.scalar.result.bits.primitiveFlagsValid) { fail(Status.Protocol.U) }
      .otherwise {
        when(!torchInverseOperation) { exceptionFlags := exceptionFlags | io.scalar.result.bits.flags }
        when(io.scalar.result.bits.error || (!torchInverseOperation && io.scalar.result.bits.flags(4, 1).orR) || !TensorMath.finite(r)) { rejectNorm(4.U) }
          .otherwise {
            state := scalarIssue; value := r
            switch(operation) {
              is(square) {
                when(useTorchDefault) { operation := torchTermAdd }
                  .otherwise {
                    treeValues(lane(3, 0)) := r
                    when(lane(3, 0) === 15.U) { treeIndex := 0.U; treeCount := 8.U; operation := tree }
                      .otherwise { lane := lane + 1.U }
                  }
              }
              is(torchTermAdd) {
                // lane is already the input address: Cat(t[2:0], residue[1:0], vectorLane[2:0]).
                // value holds the immediately preceding rounded square.
                treeValues(0) := r
                when(lane(7, 5) =/= 7.U) {
                  lane := lane + 32.U; operation := square
                }.elsewhen(lane(4, 3) === 0.U) {
                  // The first completed residue seeds the lane fold without an extra Add.
                  treeValues(1) := r; treeValues(0) := 0.U
                  lane := Cat(0.U(3.W), 1.U(2.W), lane(2, 0)); operation := square
                }.otherwise { operation := torchResidueFold }
              }
              is(torchResidueFold) {
                // value holds the completed residue; treeValues(1) holds residues before it.
                treeValues(1) := r
                when(lane(4, 3) === 3.U) { operation := torchLaneFold }
                  .otherwise {
                    treeValues(0) := 0.U
                    lane := Cat(0.U(3.W), (lane(4, 3) + 1.U)(1, 0), lane(2, 0))
                    operation := square
                  }
              }
              is(torchLaneFold) {
                // value holds the completed lane; accumulator folds lanes from +0.
                accumulator := r
                when(lane(2, 0) === 7.U) { lane := 0.U; operation := mean }
                  .otherwise {
                    treeValues(0) := 0.U
                    lane := Cat(0.U(5.W), (lane(2, 0) + 1.U)(2, 0)); operation := square
                  }
              }
              is(tree) {
                treeValues(treeIndex) := r
                when(treeIndex + 1.U === treeCount) {
                  treeIndex := 0.U; treeCount := treeCount >> 1
                  when(treeCount === 1.U) { operation := running }
                }.otherwise { treeIndex := treeIndex + 1.U }
              }
              is(running) {
                accumulator := r
                when(lane === 255.U) { lane := 0.U; operation := mean }
                  .otherwise { lane := lane + 1.U; operation := square }
              }
              is(mean) { operation := epsilon }
              is(epsilon) {
                lastMeanEps := r
                when(r(31) || r(30, 23) < 2.U || r(30, 23) > 253.U) { rejectNorm(4.U) }
                  .elsewhen(useTorchDefault) { operation := torchSqrt }
                  .otherwise {
                    val exponent = r(30, 23).zext - 127.S(10.W)
                    val odd = exponent(0)
                    val evenExponent = exponent - odd.asUInt.zext
                    val scaleExponent = 127.S(10.W) - (evenExponent >> 1)
                    norm := Cat(0.U(1.W), Mux(odd, 128.U(8.W), 127.U(8.W)), r(22, 0))
                    scale := Cat(0.U(1.W), scaleExponent.asUInt(7, 0), 0.U(23.W))
                    coefficient := rsqrtCoefficients(Cat(odd, r(22, 19)))
                    operation := slope
                  }
              }
              is(slope) { operation := intercept }
              is(intercept) { seed := r; operation := seedSquare }
              is(seedSquare) { operation := normProduct }
              is(normProduct) { operation := half }
              is(half) { operation := correction }
              is(correction) { operation := newton }
              is(newton) { operation := rescale }
              is(rescale) {
                lastInverse := r; invRms := r; operation := gamma
                when(r(31) || r(30, 23) === 0.U || r(30, 23) === 255.U) { rejectNorm(4.U) }
              }
              is(torchSqrt) {
                // Positive normal root is required before passing it as Div's denominator.
                when(r(31) || r(30, 23) === 0.U || r(30, 23) === 255.U) { rejectNorm(4.U) }
                  .otherwise { operation := torchDivide }
              }
              is(torchDivide) {
                lastInverse := r; invRms := r; operation := gamma
                when(r(31) || r(30, 23) === 0.U || r(30, 23) === 255.U) { rejectNorm(4.U) }
              }
              is(gamma) { laneGamma := r; operation := normalize }
              is(normalize) { operation := weighted }
              is(weighted) {
                // Exact fp32_to_bf16_rne_candidate finite-input conversion.
                val discarded = r(15, 0).orR
                val increment = r(15) && (r(14, 0).orR || r(16))
                val rounded = r(31, 16) + increment
                val overflow = rounded(14, 7) === 255.U
                val underflow = discarded && rounded(14, 7) === 0.U
                val conversionFlags = Cat(0.U(2.W), overflow, underflow && !overflow, discarded || overflow)
                exceptionFlags := exceptionFlags | io.scalar.result.bits.flags | conversionFlags
                output(lane) := rounded
                when(overflow || underflow) { rejectNorm(4.U) }
                  .elsewhen(lane === 255.U) { beat := 0.U; state := writeNorm }
                  .otherwise { lane := lane + 1.U; operation := gamma }
              }
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
    terminal.outputCommitted:=complete
    terminal.scalarAccepted:=scalarAccepted;terminal.scalarReturned:=scalarReturned
    terminal.memoryAccepted:=memoryAccepted;terminal.memoryReturned:=sequence
    terminal.normStatus:=normStatus;terminal.exceptionFlags:=exceptionFlags
    terminal.lastMeanEps:=lastMeanEps;terminal.lastInverse:=lastInverse
    when(status===Status.Ok.U && !exact){poison:=true.B}
    state:=report
  }
  // Registered terminal is immutable under downstream backpressure and a late
  // fault. The parent's same-cycle fault veto still forbids publication.
  when(io.done.fire){state:=Mux(io.resetRequired || terminal.status=/=Status.Ok.U,locked,idle)}
  assert(PopCount(Seq(io.memory.valid,io.scalar.request.valid))<=1.U)
}

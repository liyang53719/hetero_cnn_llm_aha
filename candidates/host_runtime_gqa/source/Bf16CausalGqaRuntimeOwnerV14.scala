// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Internal attention core job; no public Host encoding. Q/output are BF16
  * [tokens,queryHeads,headDim]. Cache is [2,capacityTokens,2,headDim], K then V.
  * The real original Guard/Prefix binds actual Q RoPE and complete KV ACK
  * provenance. Neither a matching raw job nor this leaf publishes cache roots.
  */
class Bf16CausalGqaRuntimeJobV14 extends Bundle {
  val tokens = UInt(16.W)
  val rowWidth = UInt(16.W) // exact original n; no division/truncation alias
  val queryHeads = UInt(16.W)
  val kvHeads = UInt(16.W)
  val headDim = UInt(16.W)
  // ABI v2 runtime order: 0 ascending, 1 adjacent pair high-first.
  val qkOrder = UInt(8.W) // retain full decoded policy; reject values other than0/1
  val queryInput = UInt(64.W)
  val cacheBase = UInt(64.W)
  val output = UInt(64.W)
  val queryStart = UInt(32.W)
  val cacheLength = UInt(32.W)
  val capacityTokens = UInt(32.W)
  val tag = UInt(32.W)
}
object Bf16CausalGqaRuntimeJobV14 {
  def fromOwner(j:QwenOwnerJob):Bf16CausalGqaRuntimeJobV14={
    val r=Wire(new Bf16CausalGqaRuntimeJobV14)
    r.tokens:=j.m;r.rowWidth:=j.n;r.queryHeads:=j.n>>8;r.kvHeads:=2.U;r.headDim:=j.k
    r.qkOrder:=j.qkNormPolicy;r.queryInput:=j.a;r.cacheBase:=j.b;r.output:=j.dst
    r.queryStart:=j.queryStart;r.cacheLength:=j.cacheLength;r.capacityTokens:=j.cacheCapacity;r.tag:=j.tag
    r
  }
}
class Bf16CausalGqaRuntimeResultV14 extends Bundle {
  val accepted = new Bf16CausalGqaRuntimeJobV14
  val scalarAccepted = UInt(32.W)
  val scalarReturned = UInt(32.W)
  val memoryAccepted = UInt(32.W)
  val memoryReturned = UInt(32.W)
  val matrixGroupsAccepted = UInt(32.W)
  val matrixGroupsReturned = UInt(32.W)
  val outputAckBytes = UInt(64.W)
  val drained = Bool()
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val outputCommitted = Bool()
  // 0 none; 1 nonfinite; 2 scalar/probability domain; 3 unsupported
  // unmasked score difference <= -80; 4 fully masked row.
  val attentionStatus = UInt(4.W)
}
/** Non-backpressured observation of actual successful BF16 score materialization.
  * The parent/test must consume every valid pulse; this is not a lease or receipt.
  */
class Bf16ScoreMaterializationV14 extends Bundle {
  val tag = UInt(32.W)
  val queryToken = UInt(16.W)
  val queryPosition = UInt(32.W)
  val queryHead = UInt(4.W)
  val key = UInt(9.W)
  val maskedStage = Bool()
  val value = UInt(16.W)
}
class Bf16CausalGqaRuntimePortV14 extends Bundle {
  val job = Flipped(Decoupled(new Bf16CausalGqaRuntimeJobV14))
  val done = Decoupled(new Bf16CausalGqaRuntimeResultV14)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val matrix = new MatrixStreamPort
  val scalar = new UnifiedScalarClientV2
  val parentFault = Input(Bool())
  // Read-only actual downstream publication observations from the original
  // Top/Kernel gates, never Host grants. Raw pre-gate signals are cancellable
  // intents; only genuinely published offers become Decoupled obligations.
  val memoryPublished = Input(Bool())
  val scalarPublished = Input(Bool())
  val matrixGroupPublished = Input(Bool())
  val matrixStepPublished = Input(Bool())
  val resourcesDrained = Output(Bool())
  val resetRequired = Output(Bool())
  val scoreMaterialized = Output(Valid(new Bf16ScoreMaterializationV14))
}

/** Derived from frozen r3 Bf16CausalGqaOwner.scala SHA
  * d1dc6e1707ec0ae303b439b90904adb37dbce9df53e0156011e167a11ae92d18.
  * Arithmetic, ordering, BF16 boundaries and all six Scalar operations/score
  * are unchanged. Only authority-facing transport/terminal metadata is added.
  * Bounded 16-query x32-key QK tiles and 16-query x256-column PV tiles.
  * Q:8 KiB, K:16 KiB, score/exp/prob:16 KiB at maxCacheTokens=256,
  * QK BF16 memory:1 KiB, PV BF16 memory:8 KiB, V vector:512 B.
  * Thirty-two terminal BF16 converters are reused per 64-byte output beat.
  * Q/K are banks of eight 512-bit words, not a full attention matrix.
  * No Matrix arithmetic, SFU, Scalar or iDMA instance is created here.
  *
  * QK: opcode0x23/slice0, increasing d0..255 FP32 FMA by default, terminal BF16 RNE.
  * Runtime qkOrder=1 selects d1,0,3,2,... operands; capacity is fixed.
  * Scale is separately rounded FP32 then BF16, followed by an actual shared
  * Add of BF16 minimum finite (future causal key) or +0 and BF16 RNE store.
  * All keys then execute subtraction/exp/sum/div; there is no masked-key skip.
  * Only a masked subtraction result exactly 0xff7f0000 may use the legacy
  * ExpNegative zero result; all other <=-80 differences remain unsupported.
  * Scale1/16 separately rounds FP32 then BF16. Softmax uses FP32 max,
  * subtract, shared degree7 ExpNegative, increasing-key sum/div, terminal
  * BF16 probabilities. Non-sentinel differences <= -80 are unsupported; the
  * shared exp truncation is never silently called native equality. PV:
  * opcode0x24/all8 slices, increasing key0..cacheLength-1 including masked
  * probability zero, terminal BF16. Runtime grouping is h/4 or h/8.
  * Legacy scalar exposes error only here: no raw UF/NX flags are invented.
  * Parent must bind geometry/order to accepted common profile, not host choice.
  * Fixed-order bit equality is distinct from official eager/native accuracy.
  *
  * Whole Q/cache/output allocations must be disjoint, aligned and legal in
  * the retained 56-bit aperture, including unused cache capacity. Successful
  * done follows every Matrix terminal done and every actual output write ACK.
  * Faults drain accepted memory/scalar work, abort/drain Matrix and poison
  * until joint reset of owner, services and transport. Reset alone cannot
  * cancel external work or roll back physical staging writes.
  */
object Bf16CausalGqaRuntimeAbiV14 {
  val Version = 14
  val MaxTokens = 128
  val MaxCacheTokens = 256
  val MaxQueryHeads = 16
  val MaxHeadDim = 256
}
class Bf16CausalGqaRuntimeOwnerV14 extends Module {
  private val maxCacheTokens = Bf16CausalGqaRuntimeAbiV14.MaxCacheTokens
  val io = IO(new Bf16CausalGqaRuntimePortV14)
  private val states = Enum(26)
  val idle = states(0)
  val readQ = states(1)
  val waitQ = states(2)
  val readK = states(3)
  val waitK = states(4)
  val groupQk = states(5)
  val stepQk = states(6)
  val resultQk = states(7)
  val doneQk = states(8)
  val scalarIssue = states(9)
  val scalarWait = states(10)
  val softBegin = states(11)
  val softExp = states(12)
  val softNorm = states(13)
  val groupPv = states(14)
  val readV = states(15)
  val waitV = states(16)
  val stepPv = states(17)
  val resultPv = states(18)
  val donePv = states(19)
  val writeOut = states(20)
  val waitOut = states(21)
  val drain = states(22)
  val finish = states(23)
  val locked = states(24)
  val report = states(25)
  val state = RegInit(idle)
  val scaleScore :: maskScore :: difference :: exponential :: sumExp :: divide :: Nil = Enum(6)
  val operation = RegInit(scaleScore)
  val job = Reg(new Bf16CausalGqaRuntimeJobV14)
  val qTile = RegInit(0.U(16.W))
  val head = RegInit(0.U(4.W))
  val row = RegInit(0.U(4.W))
  val beat = RegInit(0.U(3.W))
  val kTile = RegInit(0.U(9.W))
  val kLane = RegInit(0.U(5.W))
  val dimension = RegInit(0.U(8.W))
  val key = RegInit(0.U(9.W))
  val query = Seq.fill(16)(Mem(8, UInt(512.W)))
  val keys = Seq.fill(32)(Mem(8, UInt(512.W)))
  val scores = Seq.fill(16)(Mem(maxCacheTokens, UInt(32.W)))
  val qk = Mem(16, UInt(512.W))
  val output = Seq.fill(16)(Mem(8, UInt(512.W)))
  val collecting = RegInit(false.B)
  val value = Reg(Vec(8, UInt(512.W)))
  val maximum = Reg(Vec(16, UInt(32.W)))
  val seen = RegInit(VecInit(Seq.fill(16)(false.B)))
  val scalarValue = Reg(UInt(32.W))
  val sum = RegInit(0.U(32.W))
  val sequence = RegInit(0.U(32.W))
  val matrixTag = RegInit(0.U(32.W))
  val matrixActive = RegInit(false.B)
  val memoryPending = RegInit(false.B)
  val scalarPending = RegInit(false.B)
  val matrixTerminalUnsafe = RegInit(false.B)
  val memoryPendingWrite = RegInit(false.B)
  val memoryAccepted = RegInit(0.U(32.W))
  val scalarAccepted = RegInit(0.U(32.W))
  val scalarReturned = RegInit(0.U(32.W))
  val matrixGroupsAccepted = RegInit(0.U(32.W))
  val matrixGroupsReturned = RegInit(0.U(32.W))
  val terminal = Reg(new Bf16CausalGqaRuntimeResultV14)
  val status = RegInit(Status.Ok.U(8.W))
  // One shared-control poison, not a cancellation request. No wide offer skid.
  val poison = RegInit(false.B)
  val drainUnknown = RegInit(false.B)
  val faultNow = WireDefault(false.B)
  val faultCode = WireDefault(Status.Protocol.U(8.W))
  val attentionStatus = RegInit(0.U(4.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))
  val rows = Mux(job.tokens - qTile >= 16.U, 16.U(5.W), (job.tokens - qTile)(4, 0))
  val columns = Mux(job.cacheLength - kTile >= 32.U, 32.U(6.W), (job.cacheLength - kTile)(5, 0))
  val causalEnd = job.queryStart.pad(33) + qTile.pad(33) + row.pad(33)
  val allowed = key.pad(33) <= causalEnd
  val kvHead = Mux(job.queryHeads === 8.U, head(3, 2), head(3, 3))
  val scoreAddress = key(log2Ceil(maxCacheTokens).max(1) - 1, 0)
  val scoreReads = VecInit(scores.map(_.read(scoreAddress)))
  val score = scoreReads(row)

  io.scoreMaterialized.valid := false.B
  io.scoreMaterialized.bits.tag := job.tag
  io.scoreMaterialized.bits.queryToken := qTile + row
  io.scoreMaterialized.bits.queryPosition := causalEnd(31, 0)
  io.scoreMaterialized.bits.queryHead := head
  io.scoreMaterialized.bits.key := key
  io.scoreMaterialized.bits.maskedStage := operation === maskScore
  io.scoreMaterialized.bits.value := 0.U
  val requestPolicy = UnifiedScalarPolicyV2.Legacy.U(2.W)
  val awaitingMatrixDone = state === doneQk || state === donePv
  val unknownMemory = io.response.valid && (!memoryPending || io.response.bits.tag =/= Cat(job.tag,sequence))
  val unknownScalar = io.scalar.result.valid && (!scalarPending || io.scalar.result.bits.policy =/= requestPolicy)
  val unknownMatrixDone = io.matrix.done.valid && (!matrixActive || io.matrix.done.bits.tag =/= matrixTag ||
    (!awaitingMatrixDone && state =/= drain))
  val earlyMatrixDone = io.matrix.done.valid && matrixActive && !awaitingMatrixDone && state=/=drain
  when(earlyMatrixDone){matrixTerminalUnsafe:=true.B}
  val unknownMatrixResult = io.matrix.result.valid && (!matrixActive || io.matrix.result.bits.context =/= 0.U || !io.matrix.result.bits.last)
  val unknown = unknownMemory || unknownScalar || unknownMatrixDone || unknownMatrixResult
  val currentFault = io.parentFault || unknown
  val quiet = !io.response.valid && !io.scalar.result.valid && !io.matrix.result.valid && !io.matrix.done.valid
  io.job.ready := state === idle && !poison && !drainUnknown && !currentFault && quiet
  io.done.valid := state === report
  io.done.bits := terminal
  io.resetRequired := status =/= Status.Ok.U || poison || drainUnknown || faultNow || currentFault
  when(state =/= idle && state =/= finish && state =/= report && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { faultNow := true.B; faultCode := code }
  // Transport identity failure cannot retire an owned request/group.
  def unknownDebt(): Unit = { drainUnknown := true.B; fail(Status.Protocol.U) }
  def numerical(reason: Int): Unit = { attentionStatus := reason.U; fail(Status.Numerical.U) }
  when(unknown) { unknownDebt() }
  when(io.parentFault) { fail(Status.Protocol.U) }
  // Publication feeds registers/assertions only, never combinational raw
  // valid/resetRequired. This breaks rawValid -> outer fault -> veto loops.
  def publishedOffer(intent:Bool,ready:Bool,published:Bool):HeldDecoupledOfferSignals={
    val held=RegInit(false.B)
    val visible=intent && ((!poison && !drainUnknown && !currentFault) || held)
    when(published){held:= !ready}
    assert(!published || visible,"actual publication requires the same raw intent")
    assert(!(visible && ready) || published,"raw acceptance requires actual publication")
    assert(!held || intent,"actually published held intent must persist")
    HeldDecoupledOfferSignals(visible,held,visible && ready)
  }
  // Wide exact bounds are checked before narrowing into counted interfaces.
  val expectedScalarWide = job.tokens.pad(96) * job.cacheLength.pad(96) * job.queryHeads.pad(96) * 6.U
  val queryTiles = (job.tokens.pad(96) + 15.U) >> 4
  val keyTiles = (job.cacheLength.pad(96) + 31.U) >> 5
  val expectedMemoryWide = 16.U * job.queryHeads.pad(96) * (job.tokens.pad(96) + queryTiles * job.cacheLength.pad(96))
  val expectedGroupsWide = queryTiles * job.queryHeads.pad(96) * (keyTiles + 1.U)
  val expectedBytesWide = job.tokens.pad(96) * job.queryHeads.pad(96) * 512.U
  val scoreWrite = WireDefault(false.B)
  val scoreWriteData = WireDefault(0.U(32.W))
  for (r <- 0 until 16) {
    when(scoreWrite && row === r.U) { scores(r).write(scoreAddress, scoreWriteData) }
  }
  def storeScore(data: UInt): Unit = { scoreWrite := true.B; scoreWriteData := data }
  def nextSoftKey(): Unit = {
    when(key +& 1.U === job.cacheLength) { key := 0.U; state := softNorm }
      .otherwise { key := key + 1.U; state := softExp }
  }

  val queryRow = qTile.pad(65) + row.pad(65)
  val qOffset = Mux(job.queryHeads === 8.U, queryRow << 12, queryRow << 13) +
    (head.pad(65) << 9) + (beat.pad(65) << 6)
  val kOffset = ((kTile.pad(65) + kLane.pad(65)) << 10) + (kvHead.pad(65) << 9) + (beat.pad(65) << 6)
  val vOffset = (job.capacityTokens.pad(65) << 10) + (key.pad(65) << 10) +
    (kvHead.pad(65) << 9) + (beat.pad(65) << 6)
  val memoryIntent = state === readQ || state === readK || state === readV || state === writeOut
  val memoryHeld = publishedOffer(memoryIntent,io.memory.ready,io.memoryPublished)
  io.memory.valid := memoryHeld.valid
  io.memory.bits.write := state === writeOut
  io.memory.bits.address := MuxLookup(state, job.queryInput.pad(65) + qOffset)(Seq(
    readK -> (job.cacheBase.pad(65) + kOffset), readV -> (job.cacheBase.pad(65) + vOffset),
    writeOut -> (job.output.pad(65) + qOffset)))
  io.memory.bits.data := Mux(state === writeOut, VecInit(output.map(_.read(beat)))(row), 0.U)
  io.memory.bits.mask := Mux(state === writeOut, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := memoryPending && !unknownMemory

  val groupIntent = state === groupQk || state === groupPv
  val groupHeld = publishedOffer(groupIntent,io.matrix.group.ready,io.matrixGroupPublished)
  io.matrix.group.valid := groupHeld.valid
  io.matrix.group.bits.opcode := Mux(state === groupPv, 0x24.U, 0x23.U)
  io.matrix.group.bits.sliceMask := Mux(state === groupPv, 255.U, 1.U)
  io.matrix.group.bits.tag := matrixTag
  val stepIntent = state === stepQk || state === stepPv
  val stepHeld = publishedOffer(stepIntent,io.matrix.step.ready,io.matrixStepPublished)
  io.matrix.step.valid := stepHeld.valid
  io.matrix.step.bits.context := 0.U
  io.matrix.step.bits.clear := Mux(state === stepPv, key === 0.U, dimension === 0.U)
  val lastStep = Mux(state === stepPv, key +& 1.U === job.cacheLength, dimension === 255.U)
  io.matrix.step.bits.last := lastStep
  io.matrix.step.bits.finish := lastStep
  io.matrix.step.bits.emit := lastStep
  // Operand routing only: keep dimension as the original accepted-step counter.
  val qkDimension = Mux(job.qkOrder === 1.U, dimension ^ 1.U(8.W), dimension)
  for (r <- 0 until 16) {
    val q = query(r).read(qkDimension(7, 5)).asTypeOf(Vec(32, UInt(16.W)))(qkDimension(4, 0))
    io.matrix.step.bits.a(r) := Mux(r.U < rows, Mux(state === stepPv, scoreReads(r)(31, 16), q), 0.U)
  }
  for (c <- 0 until 256) {
    val k = if (c < 32) keys(c).read(qkDimension(7, 5)).asTypeOf(Vec(32, UInt(16.W)))(qkDimension(4, 0)) else 0.U
    val v = value(c / 32)(16 * (c % 32) + 15, 16 * (c % 32))
    io.matrix.step.bits.b(c) := Mux(state === stepPv, v, Mux(c.U < columns, k, 0.U))
  }
  val collectingResult = state === resultQk || state === resultPv
  val finalResultBeat = row +& 1.U === rows && (state === resultQk || beat === 7.U)
  // MatrixResultFifo holds valid/bits stable until fire. Collect provisional
  // beats under backpressure; only the final beat accepts the whole result.
  io.matrix.result.ready := matrixActive && !unknownMatrixResult && (state === drain || (collectingResult && finalResultBeat))
  io.matrix.done.ready := matrixActive && !unknownMatrixDone && !matrixTerminalUnsafe && (awaitingMatrixDone || state === drain)
  io.matrix.abort := state === drain && matrixActive

  val scalarHeld = publishedOffer(state===scalarIssue,io.scalar.request.ready,io.scalarPublished)
  io.scalar.request.valid := scalarHeld.valid
  io.scalar.request.bits.policy := requestPolicy
  io.scalar.request.bits.payload.op := MuxLookup(operation, ScalarOp.Add.U)(Seq(
    scaleScore -> ScalarOp.MulIeeeRne.U, exponential -> ScalarOp.ExpNegative.U, divide -> ScalarOp.Div.U))
  io.scalar.request.bits.payload.a := MuxLookup(operation, scalarValue)(Seq(
    scaleScore -> Cat(qk.read(row).asTypeOf(Vec(32, UInt(16.W)))(kLane), 0.U(16.W)), difference -> score, sumExp -> sum, divide -> score))
  io.scalar.request.bits.payload.b := MuxLookup(operation, 0.U)(Seq(
    scaleScore -> "h3d800000".U,
    maskScore -> Mux(allowed, 0.U(32.W), "hff7f0000".U), difference -> F32.neg(maximum(row)), sumExp -> scalarValue, divide -> sum))
  io.scalar.result.ready := scalarPending && !unknownScalar
  val noOffers = !io.memory.valid && !io.scalar.request.valid && !io.matrix.group.valid && !io.matrix.step.valid
  io.resourcesDrained := noOffers && !memoryPending && !scalarPending && !matrixActive && quiet &&
    memoryAccepted===sequence && scalarAccepted===scalarReturned &&
    matrixGroupsAccepted===matrixGroupsReturned && !drainUnknown && !unknown && !matrixTerminalUnsafe

  when(io.job.fire) {
    val j = io.job.bits
    job := j; qTile := 0.U; head := 0.U; row := 0.U; beat := 0.U; kTile := 0.U; kLane := 0.U
    dimension := 0.U; key := 0.U; sequence := 0.U; matrixTag := j.tag
    matrixActive := false.B; memoryPending := false.B; scalarPending := false.B; collecting := false.B
    status := Status.Ok.U; attentionStatus := 0.U; bytes := 0.U; cycles := 0.U
    poison := false.B; drainUnknown := false.B
    memoryPendingWrite:=false.B;memoryAccepted:=0.U;scalarAccepted:=0.U;scalarReturned:=0.U
    matrixGroupsAccepted:=0.U;matrixGroupsReturned:=0.U;matrixTerminalUnsafe:=false.B
    seen.foreach(_ := false.B)
    val vectorBytes = Mux(j.queryHeads === 8.U, j.tokens.pad(65) << 12, j.tokens.pad(65) << 13)
    val cacheBytes = j.capacityTokens.pad(65) << 11
    val validGeometry = j.kvHeads === 2.U && (j.queryHeads === 8.U || j.queryHeads === 16.U) && j.headDim === 256.U &&
      j.rowWidth === (j.queryHeads.pad(32)<<8) && j.qkOrder<=1.U
    val groupsWide = (((j.tokens.pad(65)+15.U)>>4)*j.queryHeads.pad(65))*(((j.cacheLength.pad(65)+31.U)>>5)+1.U)
    val tagsFit = j.tag.pad(96)+groupsWide.pad(96)<=(BigInt(1)<<32).U
    def badSpan(base: UInt, size: UInt): Bool = base(5, 0) =/= 0.U || base.pad(65) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(65) < b.pad(65) + nb && b.pad(65) < a.pad(65) + na
    val badAddress = badSpan(j.queryInput, vectorBytes) || badSpan(j.output, vectorBytes) || badSpan(j.cacheBase, cacheBytes)
    val alias = overlap(j.queryInput, vectorBytes, j.output, vectorBytes) ||
      overlap(j.queryInput, vectorBytes, j.cacheBase, cacheBytes) || overlap(j.output, vectorBytes, j.cacheBase, cacheBytes)
    when(j.tokens === 0.U || j.tokens > Bf16CausalGqaRuntimeAbiV14.MaxTokens.U ||
      j.cacheLength === 0.U || j.capacityTokens === 0.U || j.capacityTokens > maxCacheTokens.U ||
      j.cacheLength > j.capacityTokens || badAddress || alias) { fail(Status.Bounds.U) }
      .elsewhen(!validGeometry) { fail(Status.Unsupported.U) }
      .elsewhen(j.tag==="hffffffff".U || !tagsFit) { fail(Status.Protocol.U) }
      .elsewhen(j.queryStart.pad(33) + j.tokens.pad(33) =/= j.cacheLength.pad(33)) { fail(Status.Dependency.U) }
      .otherwise { state := readQ }
  }
  when(io.memory.fire) {
    memoryPending := true.B;memoryPendingWrite:=io.memory.bits.write;memoryAccepted:=memoryAccepted+1.U
    state := MuxLookup(state, waitQ)(Seq(readK -> waitK, readV -> waitV, writeOut -> waitOut))
  }
  when(io.response.fire) {
    val r = io.response.bits
    // Only the exact owned tag reaches fire. Sticky quarantine never cancels
    // known debt; matching returns still count, but cannot restore eligibility.
    memoryPending := false.B; sequence := sequence + 1.U
    when(memoryPendingWrite && !r.error) { bytes := bytes + 64.U }
    when(r.error) { fail(Status.Memory.U) }
    when(state =/= drain && !poison && !currentFault && !drainUnknown) {
      val badNumber = (0 until 32).map(i => r.data(i * 16 + 14, i * 16 + 7) === 255.U).reduce(_ || _)
      when(r.error) { fail(Status.Memory.U) }
        .elsewhen(state =/= waitOut && badNumber) { numerical(1) }
        .otherwise {
          when(state === waitQ) {
            for (i <- 0 until 16) { when(row === i.U) { query(i).write(beat, r.data) } }
            when(beat === 7.U) {
              beat := 0.U
              when(row +& 1.U === rows) { row := 0.U; kLane := 0.U; kTile := 0.U; state := readK }
                .otherwise { row := row + 1.U; state := readQ }
            }.otherwise { beat := beat + 1.U; state := readQ }
          }
          when(state === waitK) {
            for (i <- 0 until 32) { when(kLane === i.U) { keys(i).write(beat, r.data) } }
            when(beat === 7.U) {
              beat := 0.U
              when(kLane +& 1.U === columns) { kLane := 0.U; dimension := 0.U; state := groupQk }
                .otherwise { kLane := kLane + 1.U; state := readK }
            }.otherwise { beat := beat + 1.U; state := readK }
          }
          when(state === waitV) {
            value(beat) := r.data
            when(beat === 7.U) { beat := 0.U; state := stepPv }
              .otherwise { beat := beat + 1.U; state := readV }
          }
          when(state === waitOut) {
            when(beat === 7.U) {
              beat := 0.U
              when(row +& 1.U === rows) {
                row := 0.U; seen.foreach(_ := false.B)
                when(head +& 1.U === job.queryHeads) {
                  head := 0.U
                  when(qTile +& rows === job.tokens) { state := finish }
                    .otherwise { qTile := qTile + 16.U; state := readQ }
                }.otherwise { head := head + 1.U; state := readQ }
              }.otherwise { row := row + 1.U; state := writeOut }
            }.otherwise { beat := beat + 1.U; state := writeOut }
          }
        }
    }
  }
  when(io.matrix.group.fire) { matrixActive := true.B;matrixGroupsAccepted:=matrixGroupsAccepted+1.U; state := Mux(state === groupQk, stepQk, readV) }
  when(io.matrix.step.fire) {
    when(state === stepQk) {
      when(dimension === 255.U) { row := 0.U; beat := 0.U; collecting := false.B; state := resultQk }.otherwise { dimension := dimension + 1.U }
    }.otherwise {
      when(key +& 1.U === job.cacheLength) { row := 0.U; beat := 0.U; collecting := false.B; state := resultPv }
        .otherwise { key := key + 1.U; state := readV }
    }
  }
  val incomingFloats = GqaRuntimeMatrixResultSelectV14(io.matrix.result.bits.value,
    row, Mux(state === resultQk, 0.U(3.W), beat))

  val converted = VecInit(incomingFloats.map(TensorMath.bf16Rne))
  val badConversion = VecInit((0 until 32).map { c =>
    (state === resultPv || c.U < columns) &&
      (!TensorMath.finite(incomingFloats(c)) || converted(c)(14, 7) === 255.U)
  }).asUInt.orR
  when(collectingResult && io.matrix.result.valid && !currentFault && !poison && !drainUnknown) {
    val m = io.matrix.result.bits
    when(m.context =/= 0.U || !m.last) { unknownDebt() }
      .elsewhen(m.error) { fail(Status.Protocol.U) }
      .elsewhen(badConversion) { numerical(1) }
      .otherwise {
        collecting := true.B
        when(state === resultQk) { qk.write(row, converted.asUInt) }
          .otherwise {
            for (r <- 0 until 16) { when(row === r.U) { output(r).write(beat, converted.asUInt) } }
          }
        when(finalResultBeat) {
          // This transition coincides with result.fire. No scalar or output
          // store can observe these staging memories until terminal done.
          collecting := false.B; row := 0.U; beat := 0.U
          state := Mux(state === resultQk, doneQk, donePv)
        }.elsewhen(state === resultQk || beat === 7.U) { row := row + 1.U; beat := 0.U }
          .otherwise { beat := beat + 1.U }
      }
  }
  when(collectingResult && collecting && !io.matrix.result.valid) { fail(Status.Protocol.U) }
  when(io.matrix.done.fire) {
    // Exact group terminal retires its real debt even after another fault.
    {
        matrixActive := false.B; matrixTag := matrixTag + 1.U;matrixGroupsReturned:=matrixGroupsReturned+1.U
        when(io.matrix.done.bits.error) { fail(Status.Protocol.U) }
        when(state =/= drain && !poison && !currentFault && !drainUnknown) {
          when(io.matrix.done.bits.error || !(state === doneQk || state === donePv)) { fail(Status.Protocol.U) }
            .otherwise {
              row := 0.U; beat := 0.U
              when(state === doneQk) { kLane := 0.U; key := kTile; operation := scaleScore; state := scalarIssue }
                .otherwise { state := writeOut }
            }
        }
      }
  }
  when(state === softBegin) {
    sum := 0.U; key := 0.U
    when(!seen(row)) { numerical(4) }.otherwise { state := softExp }
  }
  when(state === softExp) { operation := difference; state := scalarIssue }
  when(state === softNorm) {
    when(sum(31) || sum(30, 0) === 0.U || !TensorMath.finite(sum)) { numerical(2) }
      .otherwise { operation := divide; state := scalarIssue }
  }
  when(io.scalar.request.fire) { scalarPending := true.B;scalarAccepted:=scalarAccepted+1.U; state := scalarWait }
  when(io.scalar.result.fire) {
    // Full txn/owner/stage/serial is authenticated by the one shared adapter.
    // This local policy match retires only that actually accepted raw request.
    scalarPending := false.B;scalarReturned:=scalarReturned+1.U
    when(state =/= drain && !poison && !currentFault && !drainUnknown) {
      val r = io.scalar.result.bits.value
      val bf = TensorMath.bf16Rne(r)
      when(io.scalar.result.bits.error || !TensorMath.finite(r)) { numerical(2) }
        .otherwise {
          scalarValue := r; state := scalarIssue
          switch(operation) {
            is(scaleScore) {
              when(bf(14, 7) === 255.U) { numerical(1) }
                .otherwise {
                  // Materialize the existing BF16 scale boundary before Add.
                  scalarValue := Cat(bf, 0.U(16.W)); operation := maskScore
                  io.scoreMaterialized.valid := true.B
                  io.scoreMaterialized.bits.value := bf
                }
            }
            is(maskScore) {
              when(bf(14, 7) === 255.U) { numerical(1) }
                .otherwise {
                  val rounded = Cat(bf, 0.U(16.W))
                  storeScore(rounded)
                  io.scoreMaterialized.valid := true.B
                  io.scoreMaterialized.bits.value := bf
                  operation := scaleScore
                  when(!seen(row) || F32.less(maximum(row), rounded)) { maximum(row) := rounded; seen(row) := true.B }
                  when(kLane +& 1.U === columns) {
                    kLane := 0.U; key := kTile
                    when(row +& 1.U === rows) {
                      row := 0.U
                      when(kTile +& columns === job.cacheLength) { state := softBegin }
                        .otherwise { kTile := kTile + 32.U; beat := 0.U; state := readK }
                    }.otherwise { row := row + 1.U }
                  }.otherwise { kLane := kLane + 1.U; key := key + 1.U }
                }
            }
            is(difference) {
              when(!r(31) && r(30, 0).orR) { numerical(2) }
                .elsewhen(r(30, 0) >= "h42a00000".U && !(!allowed && r === "hff7f0000".U)) { attentionStatus := 3.U; fail(Status.Unsupported.U) }
                .otherwise { operation := exponential }
            }
            is(exponential) {
              when(r(31) || (r(30, 0) === 0.U && !(!allowed && scalarValue === "hff7f0000".U)) || F32.less("h3f800000".U, r)) { numerical(2) }
                .otherwise { storeScore(r); operation := sumExp }
            }
            is(sumExp) { sum := r; nextSoftKey() }
            is(divide) {
              when(r(31) || F32.less("h3f800000".U, r) || bf(14, 7) === 255.U) { numerical(2) }
                .otherwise {
                  storeScore(Cat(bf, 0.U(16.W)))
                  when(key +& 1.U === job.cacheLength) {
                    key := 0.U
                    when(row +& 1.U === rows) { row := 0.U; beat := 0.U; state := groupPv }
                      .otherwise { row := row + 1.U; state := softBegin }
                  }.otherwise { key := key + 1.U; state := softNorm }
                }
            }
          }
        }
    }
  }
  // Finish only after pending flags clear and the actual Matrix done arrives.
  when(state === drain && !memoryPending && !scalarPending && !matrixActive && !drainUnknown) { state := finish }
  // A wrong/unsolicited return is never consumed as owned work. The sticky
  // quarantine requires joint transport reset even if later exact debts drain.

  // Freeze-in-place held-offer pattern. While any external offer is held, its
  // original issue state/counters/sources remain selected. The late fault is
  // sticky beside that offer; no implicit valid withdrawal/payload replacement.
  // Only after the held offer actually fires may abort/drain be entered.
  val heldOffer = (io.memoryPublished && !io.memory.ready) ||
    (io.scalarPublished && !io.scalar.request.ready) ||
    (io.matrixGroupPublished && !io.matrix.group.ready) ||
    (io.matrixStepPublished && !io.matrix.step.ready)
  when(faultNow || poison || currentFault) {
    when(state===idle && !io.job.fire){state:=locked}
    poison := true.B
    io.scoreMaterialized.valid := false.B
    // Once done.valid is published, its payload cannot change under backpressure.
    // The separate resetRequired sideband still poisons the parent's final fence.
    when((state =/= idle || io.job.fire) && state =/= finish && state =/= report && state =/= locked) {
      when(faultNow && status === Status.Ok.U) { status := faultCode }
      when(heldOffer) { state := state }
        .elsewhen(state =/= drain) { state := drain }
    }
  }
  // Snapshot only after every actual return and output ACK. Terminal bits
  // never vary under backpressure; current parent fault still vetoes publish.
  when(state===finish && io.resourcesDrained) {
    val widthsFit=expectedScalarWide<=(BigInt(1)<<32).U-1.U && expectedMemoryWide<=(BigInt(1)<<32).U-1.U &&
      expectedGroupsWide<=(BigInt(1)<<32).U-1.U && expectedBytesWide<=(BigInt(1)<<64).U-1.U
    val exact=widthsFit && scalarAccepted===expectedScalarWide && scalarReturned===expectedScalarWide &&
      memoryAccepted===expectedMemoryWide && sequence===expectedMemoryWide &&
      matrixGroupsAccepted===expectedGroupsWide && matrixGroupsReturned===expectedGroupsWide && bytes===expectedBytesWide
    val complete=status===Status.Ok.U && !poison && !faultNow && !currentFault && exact
    terminal.accepted:=job;terminal.tag:=job.tag
    terminal.status:=Mux(status===Status.Ok.U && !complete,Status.Protocol.U,status)
    terminal.writeBytes:=bytes;terminal.outputAckBytes:=bytes;terminal.cycles:=cycles
    terminal.outputCommitted:=complete;terminal.attentionStatus:=attentionStatus;terminal.drained:=io.resourcesDrained
    terminal.scalarAccepted:=scalarAccepted;terminal.scalarReturned:=scalarReturned
    terminal.memoryAccepted:=memoryAccepted;terminal.memoryReturned:=sequence
    terminal.matrixGroupsAccepted:=matrixGroupsAccepted;terminal.matrixGroupsReturned:=matrixGroupsReturned
    when(status===Status.Ok.U && !complete){poison:=true.B}
    state:=report
  }
  when(io.done.fire) {
    state := Mux(terminal.status === Status.Ok.U && !io.resetRequired, idle, locked)
  }
}
/** Select exactly 32 FP32 bit patterns without first packing the whole tile.
  * Every row/beat encoding is valid (four/three bits). This is purely a wire
  * selection; it is independent of valid/ready and performs no arithmetic.
  */
object GqaRuntimeMatrixResultSelectV14 {
  def apply(value: Vec[Vec[UInt]], row: UInt, beat: UInt): Vec[UInt] = {
    require(value.length == 16 && value.forall(_.length == 256))
    require(value.forall(_.forall(_.getWidth == 32)))
    require(row.getWidth == 4 && beat.getWidth == 3)
    VecInit((0 until 32).map { lane =>
      MuxLookup(row, 0.U(32.W))((0 until 16).map { r =>
        r.U -> MuxLookup(beat, 0.U(32.W))((0 until 8).map { b =>
          b.U -> value(r)(b * 32 + lane)
        })
      })
    })
  }
}


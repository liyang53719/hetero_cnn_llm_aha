// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Serial, numerical-first GDN recurrent core using the existing shared FP32
  * service and the existing memory/iDMA transport. No arithmetic, Matrix or
  * DMA instance is created here. Dk/Dv=128 and 16 heads are the pinned model;
  * smaller elaboration dimensions exist only for bounded protocol tests.
  *
  * Each operation separately rounds FP32 RNE, never FMA:
  * D=exp(g)*S; prediction=sum_k(D*k); delta=(v-prediction)*beta;
  * S'=D+k*delta; out=sum_k(S'*q). Reductions are left-to-right from +0.
  * Multiplications request explicit gradual-underflow/signed-zero semantics.
  * exp is the shared degree-7 recipe. g<=-80 is rejected rather than silently
  * committing the service's saturation approximation. Official Torch uses a
  * different sum tree/exp; passing the fixed oracle alone is not that gate.
  *
  * Only 16 value columns are retained in a 128x512-bit local state tile.
  * The tile is filled before reads; cold jobs never read stateIn. StateOut and
  * BF16 output are staged, acknowledged beat by beat, and committed together only
  * after the final output ACK. An error locks this owner until joint reset of
  * owner, shared arithmetic service and transport. M=1 jobs compose decode or
  * prefill one token at a time; multi-token jobs fail closed in this revision.
  */
class GdnRecurrentOwner(maxHeads: Int = 16, keyDim: Int = 128, valueDim: Int = 128) extends Module {
  require(maxHeads > 0 && maxHeads <= 16)
  require(keyDim > 0 && keyDim <= 128 && keyDim % 16 == 0)
  require(valueDim > 0 && valueDim <= 128 && valueDim % 32 == 0)
  val io = IO(new GdnRecurrentOwnerPort)
  val idle :: readQ :: waitQ :: readK :: waitK :: readV :: waitV :: readG :: waitG :: prepareTile :: readState :: waitState :: scalarIssue :: scalarWait :: saveRow :: loadRow :: writeState :: waitStateWrite :: writeOutput :: waitOutput :: finish :: locked :: Nil = Enum(22)
  val state = RegInit(idle)
  val exp :: decay :: predictMul :: predictAdd :: subtract :: betaMul :: rankMul :: update :: outputMul :: outputAdd :: Nil = Enum(10)
  val operation = RegInit(exp)
  val job = Reg(new GdnRecurrentJob)
  val head = RegInit(0.U(16.W))
  val vectorBeat = RegInit(0.U(3.W))
  val column = RegInit(0.U(8.W)) // value tile start, multiple of 16
  val rowIndex = RegInit(0.U(7.W))
  val lane = RegInit(0.U(4.W))
  val query = Reg(Vec(keyDim, UInt(32.W)))
  val key = Reg(Vec(keyDim, UInt(32.W)))
  val value = Reg(Vec(valueDim, UInt(32.W)))
  val tile = Mem(keyDim, UInt(512.W))
  val row = Reg(Vec(16, UInt(32.W)))
  val prediction = Reg(Vec(16, UInt(32.W)))
  val delta = Reg(Vec(16, UInt(32.W)))
  val output = Reg(Vec(16, UInt(32.W)))
  val logDecay = Reg(UInt(32.W))
  val beta = Reg(UInt(32.W))
  val decayFactor = Reg(UInt(32.W))
  val product = Reg(UInt(32.W))
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val cycles = RegInit(0.U(64.W))
  val bytes = RegInit(0.U(64.W))

  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.tag := job.tag
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.stateCommitted := state === finish && status === Status.Ok.U
  io.done.bits.generation := job.expectedGeneration + Mux(io.done.bits.stateCommitted, 1.U, 0.U)
  io.resetRequired := status =/= Status.Ok.U
  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }

  val qOffset = head.pad(64) * (keyDim * 4).U + (vectorBeat.pad(64) << 6)
  val vOffset = head.pad(64) * (valueDim * 4).U + (vectorBeat.pad(64) << 6)
  val stateOffset = head.pad(64) * (keyDim * valueDim * 4).U +
    rowIndex.pad(64) * (valueDim * 4).U + (column.pad(64) << 2)
  val outputOffset = head.pad(64) * (valueDim * 2).U + ((column.pad(64) >> 5) << 6)
  val outputBf16 = VecInit(output.map(TensorMath.bf16Rne)).asUInt
  val outputData = Mux(column(4), Cat(outputBf16, 0.U(256.W)), Cat(0.U(256.W), outputBf16))
  val outputMask = Mux(column(4), "hffffffff00000000".U(64.W), "h00000000ffffffff".U(64.W))
  io.memory.valid := state === readQ || state === readK || state === readV || state === readG ||
    state === readState || state === writeState || state === writeOutput
  io.memory.bits.write := state === writeState || state === writeOutput
  io.memory.bits.address := MuxLookup(state, job.query + qOffset)(Seq(
    readK -> (job.key + qOffset), readV -> (job.value + vOffset),
    readG -> (job.gates + (head.pad(64) << 6)), readState -> (job.stateIn + stateOffset),
    writeState -> (job.stateOut + stateOffset), writeOutput -> (job.output + outputOffset)))
  io.memory.bits.data := Mux(state === writeState, row.asUInt, Mux(state === writeOutput, outputData, 0.U))
  io.memory.bits.mask := Mux(state === writeOutput, outputMask, Mux(state === writeState, Fill(64, 1.U(1.W)), 0.U))
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitQ || state === waitK || state === waitV || state === waitG ||
    state === waitState || state === waitStateWrite || state === waitOutput

  val keyIndex = rowIndex(log2Ceil(keyDim) - 1, 0)
  val valueIndex = (column + lane)(log2Ceil(valueDim) - 1, 0)
  io.scalar.request.valid := state === scalarIssue
  io.scalar.request.bits.op := MuxLookup(operation, ScalarOp.MulIeeeRne.U)(Seq(
    exp -> ScalarOp.ExpNegative.U, predictAdd -> ScalarOp.Add.U,
    subtract -> ScalarOp.Add.U, update -> ScalarOp.Add.U, outputAdd -> ScalarOp.Add.U))
  io.scalar.request.bits.a := MuxLookup(operation, row(lane))(Seq(
    exp -> logDecay, predictAdd -> prediction(lane), subtract -> value(valueIndex),
    betaMul -> product, rankMul -> key(keyIndex), outputAdd -> output(lane)))
  io.scalar.request.bits.b := MuxLookup(operation, product)(Seq(
    exp -> 0.U, decay -> decayFactor, predictMul -> key(keyIndex),
    subtract -> F32.neg(prediction(lane)), betaMul -> beta, rankMul -> delta(lane),
    outputMul -> query(keyIndex)))
  io.scalar.result.ready := state === scalarWait

  when(io.job.fire) {
    val j = io.job.bits
    job := j; head := 0.U; vectorBeat := 0.U; column := 0.U; rowIndex := 0.U; lane := 0.U
    sequence := 0.U; status := Status.Ok.U; cycles := 0.U; bytes := 0.U
    val qBytes = j.heads.pad(66) * (keyDim * 4).U
    val vBytes = j.heads.pad(66) * (valueDim * 4).U
    val gBytes = j.heads.pad(66) << 6
    val sBytes = j.heads.pad(66) * (keyDim * valueDim * 4).U
    val reads = Seq((j.query, qBytes), (j.key, qBytes), (j.value, vBytes), (j.gates, gBytes), (j.stateIn, sBytes))
    val outBytes = j.heads.pad(66) * (valueDim * 2).U
    val writes = Seq((j.stateOut, sBytes), (j.output, outBytes))
    def badSpan(base: UInt, size: UInt): Bool = base(5, 0) =/= 0.U || base.pad(66) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = (reads ++ writes).map { case (b, n) => badSpan(b, n) }.reduce(_ || _)
    val aliases = writes.flatMap { case (w, nw) => reads.map { case (r, nr) => overlap(w, nw, r, nr) } }.reduce(_ || _) ||
      overlap(j.stateOut, sBytes, j.output, outBytes)
    when(j.expectedGeneration =/= io.currentGeneration || (j.cold && j.expectedGeneration =/= 0.U)) { fail(Status.Dependency.U) }
      .elsewhen(j.tokens =/= 1.U || j.heads === 0.U || j.heads > maxHeads.U || j.keyDim =/= keyDim.U ||
        j.valueDim =/= valueDim.U || j.expectedGeneration === "hffffffff".U || badAddress || aliases) { fail(Status.Bounds.U) }
      .otherwise { state := readQ }
  }
  when(io.memory.fire) {
    state := MuxLookup(state, waitQ)(Seq(readK -> waitK, readV -> waitV, readG -> waitG,
      readState -> waitState, writeState -> waitStateWrite, writeOutput -> waitOutput))
  }
  when(io.response.fire) {
    val r = io.response.bits
    val words = r.data.asTypeOf(Vec(16, UInt(32.W)))
    val nonfinite = words.map(x => !TensorMath.finite(x)).reduce(_ || _)
    when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        when(state === waitQ || state === waitK || state === waitV) {
          for (i <- 0 until 16) {
            val index = Cat(vectorBeat, i.U(4.W))
            when(state === waitQ) { query(index(log2Ceil(keyDim)-1,0)) := words(i) }
              .elsewhen(state === waitK) { key(index(log2Ceil(keyDim)-1,0)) := words(i) }
              .otherwise { value(index(log2Ceil(valueDim)-1,0)) := words(i) }
          }
          when(nonfinite) { fail(Status.Numerical.U) }
            .elsewhen(vectorBeat === Mux(state === waitV, (valueDim / 16 - 1).U, (keyDim / 16 - 1).U)) {
              vectorBeat := 0.U
              state := MuxLookup(state, readG)(Seq(waitQ -> readK, waitK -> readV))
            }.otherwise {
              vectorBeat := vectorBeat + 1.U
              state := MuxLookup(state, readV)(Seq(waitQ -> readQ, waitK -> readK))
            }
        }
        when(state === waitG) {
          logDecay := words(0); beta := words(1)
          val badG = !TensorMath.finite(words(0)) || (!words(0)(31) && words(0)(30, 0).orR) || words(0)(30, 0) >= F32.lit(80)
          val badB = !TensorMath.finite(words(1)) || (words(1)(31) && words(1)(30, 0).orR) || words(1)(30, 0) > F32.lit(1)
          when(r.data(511, 64).orR) { fail(Status.Bounds.U) }
            .elsewhen(badG || badB) { fail(Status.Numerical.U) }
            .otherwise { operation := exp; state := scalarIssue }
        }
        when(state === waitState) {
          row := words; lane := 0.U; operation := decay; state := scalarIssue
          when(nonfinite) { fail(Status.Numerical.U) }
        }
        when(state === waitStateWrite) {
          bytes := bytes + 64.U
          when(rowIndex === (keyDim - 1).U) { state := writeOutput }
            .otherwise { rowIndex := rowIndex + 1.U; state := loadRow }
        }
        when(state === waitOutput) {
          bytes := bytes + 32.U
          when(column + 16.U === valueDim.U) {
            when(head + 1.U === job.heads) { state := finish }
              .otherwise { head := head + 1.U; vectorBeat := 0.U; column := 0.U; state := readQ }
          }.otherwise { column := column + 16.U; state := prepareTile }
        }
      }
  }
  when(state === prepareTile) {
    rowIndex := 0.U; lane := 0.U
    prediction := 0.U.asTypeOf(prediction); output := 0.U.asTypeOf(output)
    when(job.cold) { row := 0.U.asTypeOf(row); operation := decay; state := scalarIssue }
      .otherwise { state := readState }
  }
  when(state === saveRow) {
    tile.write(keyIndex, row.asUInt)
    lane := 0.U
    when(rowIndex === (keyDim - 1).U) { operation := subtract; state := scalarIssue }
      .otherwise {
        rowIndex := rowIndex + 1.U
        when(job.cold) { row := 0.U.asTypeOf(row); operation := decay; state := scalarIssue }
          .otherwise { state := readState }
      }
  }
  when(state === loadRow) { row := tile.read(keyIndex).asTypeOf(row); lane := 0.U; operation := rankMul; state := scalarIssue }
  when(io.scalar.request.fire) { state := scalarWait }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits
    when(io.scalar.error || !TensorMath.finite(r)) { fail(Status.Numerical.U) }
      .otherwise {
        state := scalarIssue
        switch(operation) {
          is(exp) { decayFactor := r; state := prepareTile }
          is(decay) { row(lane) := r; operation := predictMul }
          is(predictMul) { product := r; operation := predictAdd }
          is(predictAdd) {
            prediction(lane) := r
            when(lane === 15.U) { state := saveRow }
              .otherwise { lane := lane + 1.U; operation := decay }
          }
          is(subtract) { product := r; operation := betaMul }
          is(betaMul) {
            delta(lane) := r
            when(lane === 15.U) { rowIndex := 0.U; state := loadRow }
              .otherwise { lane := lane + 1.U; operation := subtract }
          }
          is(rankMul) { product := r; operation := update }
          is(update) { row(lane) := r; operation := outputMul }
          is(outputMul) { product := r; operation := outputAdd }
          is(outputAdd) {
            output(lane) := r
            when(rowIndex === (keyDim - 1).U && TensorMath.bf16Rne(r)(14, 7) === 255.U) { fail(Status.Numerical.U) }
              .elsewhen(lane === 15.U) { state := writeState }
              .otherwise { lane := lane + 1.U; operation := rankMul }
          }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}

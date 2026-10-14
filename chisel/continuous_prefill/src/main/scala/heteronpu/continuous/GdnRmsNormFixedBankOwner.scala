// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** H2048-only internal borrower controls. The inherited job is typed BF16;
  * admission must still enforce BF16 before constructing GdnRmsNormJob.
  *
  * abort cancels a job, including a held successful completion. clear during
  * a job also cancels; it does NOT erase an offered/accepted service request
  * or a held completion. Recovery samples clear only in idle/locked after
  * the failure completion has retired. At that point asserted clear attests that the
  * caller has recovered external memory/Scalar poison and excluded stale
  * responses. It does not override this owner's internal drain checks.
  * vectorUnavailable must be the actual original elementwise engine's
  * io.resetRequired (both DDR-origin and loan-origin poison), not constant
  * false or merely loan.resetRequired. It gates admission and recovery;
  * it does not prevent an already accepted failure from draining/retiring.
  *
  * drained means no owned offered/accepted transaction and no visible service
  * reply/busy. It does not mean the external fabric is globally recovered,
  * nor does it mean a held done has retired. locked includes recovery states.
  */
class GdnRmsNormFixedBankOwnerPort extends GdnRmsNormOwnerPort {
  val loan = Flipped(new ElementwiseLoanPort)
  val abort = Input(Bool())
  val clear = Input(Bool())
  val vectorUnavailable = Input(Bool())
  val drained = Output(Bool())
  val locked = Output(Bool())
}

object GdnRmsNormFixedBankOwner {
  val LogicalWidth = 2048
  val BankWidth = 1024
  val BankBytes = 2048
  val BankBeats = 32
  val ReadRequestsPerToken = 192
  val WriteAcksPerToken = 64
  val LoanRequestsPerToken = 128
  val ScalarRequestsPerToken = 4268
  val ScalarMulRequestsPerToken = 2049
  val ScalarAddRequestsPerToken = 2217
  // New same-bank H2048 ablation, not the historical H1024 owner baseline.
  val ScalarEpilogueRequestsPerToken = 3 * LogicalWidth
  val AllScalarRequestsPerToken = ScalarRequestsPerToken + ScalarEpilogueRequestsPerToken
}

/** Fixed-bank H2048 RMS borrower with an optional, default-off kernel binding.
  * QwenOwnerKernel.enableH2048RmsBorrower selects it statically; the legacy
  * GdnRmsNormOwner remains the default when that kernel option is disabled.
  *
  * Storage: exactly three 32 x 512-bit banks and four 32-bit scalar registers.
  * The first 128 bytes of output overlay 32 FP32 residue sums until inverse
  * is computed. No partial, gamma, normalized, or loan-result array exists.
  * Every output update changes one bank beat: a 32-bit partial, a 256-bit
  * vector BF16 half-beat, or one 16-bit Scalar BF16 lane. The whole chunk is
  * filled before its first DDR write.
  *
  * Arithmetic: external shared Scalar for the pinned two-chunk reduction;
  * external original ElementwiseRegisterLoan for the default 16-lane epilogue.
  * Compile-time useVectorEpilogue=false runs those three per-lane operations
  * on the same external Scalar with the same banks and two-pass DDR schedule.
  * No Module(new ...) arithmetic/service instances are created here.
  * The separate multiply/add nodes and explicit +0 additions are retained.
  *
  * At most one service transaction is offered/accepted at a time. Its state
  * and selectors retain its full payload through backpressure and cancel;
  * no 512-bit retained request/result register is needed. A cancelled loan
  * offer first handshakes, then receives exactly one abort pulse, then its
  * terminal is drained with abort low. Memory/Scalar cannot be cancelled and
  * must return. A wrong memory or loan tag does not discharge expected-tag
  * debt, even if the service drops busy after the malformed terminal.
  *
  * A successful done requires every output ACK and exact tokens * 4096 bytes.
  * The caller publishes only on done.fire && outputCommitted. A failure can
  * report acknowledged staging bytes without publishing output. All errors
  * lock admission after failure completion, until explicit drained clear.
  * Global module reset still requires coordinated external service drain.
  *
  * Source basis: bab427c37cfe4af4742d8c0733ff2bc1ea2354c0,
  * candidates/qwen35_35b_rms/owner.py SHA256
  * 14f8f9bb0ee5845dea3a2e3ff203128563e7b1fda11b64c354c26cfdc2cbedc1.
  * The preceding default-vector revision has local production-core-service
  * RTL replay evidence for frozen actual M1/M16/M128 inputs. That evidence is
  * source-pinned; this selectable Scalar-epilogue revision and its observation
  * changes require fresh frozen-source gates. No full-kernel simulation,
  * synthesis, physical timing, or PPA result is claimed here.
  */
class GdnRmsNormFixedBankOwner(maxTokens: Int = 128,
                               useVectorEpilogue: Boolean = true) extends Module {
  import GdnRmsNormFixedBankOwner._
  require(maxTokens >= 1 && maxTokens <= 128)
  val io = IO(new GdnRmsNormFixedBankOwnerPort)

  val idle :: readInput :: waitInput :: readWeight :: waitWeight :: scalarIssue :: scalarWait :: loanIssue :: loanWait :: loanAbort :: loanDrain :: writeOutput :: waitOutput :: finish :: locked :: recoverPulse :: recoverWait :: Nil = Enum(17)
  val state = RegInit(idle)
  val square :: sum :: residue :: foldResidue :: foldLane :: mean :: epsilon :: root :: inverse :: normalize :: onePlusWeight :: weighted :: Nil = Enum(12)
  val operation = RegInit(square)

  val job = Reg(new GdnRmsNormJob)
  val input = Reg(Vec(BankBeats, UInt(512.W)))
  val weights = Reg(Vec(BankBeats, UInt(512.W)))
  val output = Reg(Vec(BankBeats, UInt(512.W)))

  val token = RegInit(0.U(16.W))
  val beat = RegInit(0.U(5.W))
  // Reduction C: [9:7] lane8, [6:5] residue, [4] block, [3:0] term.
  // Fold: p=0..31. Epilogue: chunk-local column advances by 16 (loan) or 1 (Scalar).
  val lane = RegInit(0.U(10.W))
  val chunk = RegInit(false.B)
  val emitPass = RegInit(false.B)

  // These are the same four FP32 scalar storage roles as the original owner.
  val accumulator = RegInit(0.U(32.W))
  val value = Reg(UInt(32.W))
  val normalized = Reg(UInt(32.W)) // reduction sum, then one Scalar epilogue lane
  val invRms = Reg(UInt(32.W))

  // One common retirement sequence supplies memory low-tag and loan tag.
  // It is frozen from offer until response, including all cancel/drain cycles.
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))

  val memoryOffer = state === readInput || state === readWeight || state === writeOutput
  val memoryDebt = state === waitInput || state === waitWeight || state === waitOutput
  val scalarDebt = state === scalarIssue || state === scalarWait
  val loanDebt = state === loanIssue || state === loanWait ||
    state === loanAbort || state === loanDrain
  val outstanding = memoryOffer || memoryDebt || scalarDebt || loanDebt
  val servicesQuiet = !io.loan.busy && !io.loan.result.valid &&
    !io.response.valid && !io.scalar.result.valid
  val cancel = io.abort || io.clear
  val active = state =/= idle && state =/= locked &&
    state =/= recoverPulse && state =/= recoverWait
  val expectedBytes = (job.tokens.pad(64) << 12)(63, 0)

  io.drained := !outstanding && servicesQuiet
  io.locked := state === locked || state === recoverPulse || state === recoverWait
  io.job.ready := state === idle && !cancel && !io.loan.resetRequired &&
    !io.vectorUnavailable && servicesQuiet
  // Cancellation wins over retirement of a held successful completion.
  // Once converted to failure, the held failure can retire even if abort is held.
  io.done.valid := state === finish && io.drained &&
    !(cancel && status === Status.Ok.U)
  io.done.bits.tag := job.tag
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.outputCommitted := io.done.valid && status === Status.Ok.U &&
    bytes === expectedBytes && !cancel
  io.resetRequired := status =/= Status.Ok.U || io.loan.resetRequired || io.vectorUnavailable ||
    (active && cancel)

  val reduceIndex = Cat(lane(4), lane(3, 0), lane(6, 5), lane(9, 7))
  val inputIndex = Mux(emitPass, lane, reduceIndex)
  val inputWords = input(inputIndex(9, 5)).asTypeOf(Vec(32, UInt(16.W)))
  val partialIndex = Mux(operation === foldResidue, lane(4, 0), Cat(lane(9, 7), lane(6, 5)))
  val partialBeat = Cat(0.U(4.W), partialIndex(4))
  // Share the output-bank read mux between DDR, scalar scratch, and epilogue.
  val readPartial = (state === scalarIssue || state === scalarWait) &&
    (if (useVectorEpilogue) true.B else !emitPass)
  val outputReadIndex = Mux(memoryOffer || memoryDebt, beat,
    Mux(readPartial, partialBeat, lane(9, 5)))
  val currentOutputBeat = output(outputReadIndex)
  val partialWords = currentOutputBeat.asTypeOf(Vec(16, UInt(32.W)))
  val previousPartial = partialWords(partialIndex(3, 0))
  val previousResidue = Mux(!chunk && !lane(4), 0.U(32.W), previousPartial)
  val x = Cat(inputWords(reduceIndex(4, 0)), 0.U(16.W))

  val rowOffset = (token.pad(64) << 12)(63, 0)
  val chunkOffset = Mux(chunk, BankBytes.U(64.W), 0.U(64.W))
  val beatOffset = (beat.pad(64) << 6)(63, 0)
  io.memory.valid := memoryOffer
  io.memory.bits.write := state === writeOutput
  io.memory.bits.address := MuxLookup(state, job.input + rowOffset + chunkOffset + beatOffset)(Seq(
    readWeight -> (job.weight + chunkOffset + beatOffset),
    writeOutput -> (job.output + rowOffset + chunkOffset + beatOffset)))
  io.memory.bits.data := Mux(state === writeOutput, currentOutputBeat, 0.U)
  io.memory.bits.mask := Mux(state === writeOutput, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := memoryDebt

  io.scalar.request.valid := state === scalarIssue
  io.scalar.request.bits.op := MuxLookup(operation, ScalarOp.Add.U)(Seq(
    square -> ScalarOp.MulIeeeRne.U, mean -> ScalarOp.MulIeeeRne.U,
    root -> ScalarOp.Sqrt.U, inverse -> ScalarOp.Div.U))
  io.scalar.request.bits.a := MuxLookup(operation, value)(Seq(
    square -> x, sum -> accumulator, residue -> previousResidue,
    foldResidue -> accumulator, foldLane -> normalized,
    mean -> normalized, inverse -> F32.lit(1)))
  io.scalar.request.bits.b := MuxLookup(operation, value)(Seq(
    square -> x, residue -> accumulator, foldResidue -> previousPartial,
    foldLane -> accumulator, mean -> F32.lit(1.0 / LogicalWidth),
    epsilon -> F32.lit(1e-6), root -> 0.U))
  io.scalar.result.ready := state === scalarWait

  val weightWords = weights(lane(9, 5)).asTypeOf(Vec(32, UInt(16.W)))
  if (!useVectorEpilogue) {
    // Separate FP32 rounding boundaries, using the original external Scalar.
    // normalized holds x * inverse while value is overwritten by 1 + weight.
    when(operation === normalize) {
      io.scalar.request.bits.op := ScalarOp.MulIeeeRne.U
      io.scalar.request.bits.a := Cat(inputWords(lane(4, 0)), 0.U(16.W))
      io.scalar.request.bits.b := invRms
    }
    when(operation === onePlusWeight) {
      io.scalar.request.bits.op := ScalarOp.Add.U
      io.scalar.request.bits.a := F32.lit(1)
      io.scalar.request.bits.b := Cat(weightWords(lane(4, 0)), 0.U(16.W))
    }
    when(operation === weighted) {
      io.scalar.request.bits.op := ScalarOp.MulIeeeRne.U
      io.scalar.request.bits.a := normalized
      io.scalar.request.bits.b := value
    }
  }
  io.loan.request.valid := (if (useVectorEpilogue) state === loanIssue else false.B)
  io.loan.request.bits.tag := sequence
  io.loan.request.bits.op := ElementwiseLoanOp.RmsEpilogue.U
  io.loan.request.bits.a := VecInit((0 until 16).map { i =>
    Cat(inputWords(Cat(lane(4), i.U(4.W))), 0.U(16.W))
  }).asUInt
  io.loan.request.bits.b := VecInit((0 until 16).map { i =>
    Cat(weightWords(Cat(lane(4), i.U(4.W))), 0.U(16.W))
  }).asUInt
  io.loan.request.bits.inverse := invRms
  // Never pulse abort/reset while an unaccepted loan offer is being held:
  // the existing service gates request.ready with those inputs.
  io.loan.abort := state === loanAbort
  io.loan.resetLoan := state === recoverPulse
  io.loan.result.ready := (state === loanWait && !cancel) || state === loanDrain

  val loanFloats = io.loan.result.bits.value.asTypeOf(Vec(16, UInt(32.W)))
  val loanRounded = VecInit((0 until 16).map(i => TensorMath.bf16Rne(loanFloats(i))))
  val loanNonfinite = VecInit((0 until 16).map(i => !TensorMath.finite(loanFloats(i)))).asUInt.orR
  val bf16Overflow = VecInit((0 until 16).map(i => loanRounded(i)(14, 7) === 255.U)).asUInt.orR
  val scalarRounded = TensorMath.bf16Rne(io.scalar.result.bits)
  val scalarBf16Overflow = if (useVectorEpilogue) false.B else
    operation === weighted && scalarRounded(14, 7) === 255.U

  // A single logical output-bank write port serves the scratch and epilogue.
  // These are combinational patches, not retained arrays or result caches.
  val outputWrite = WireDefault(false.B)
  val outputWriteIndex = WireDefault(0.U(5.W))
  val outputWriteData = WireDefault(0.U(512.W))
  val updatedPartialWords = Wire(Vec(16, UInt(32.W)))
  updatedPartialWords := partialWords
  updatedPartialWords(partialIndex(3, 0)) := io.scalar.result.bits
  val roundedHalf = loanRounded.asUInt
  val updatedOutputBeat = Mux(lane(4),
    Cat(roundedHalf, currentOutputBeat(255, 0)),
    Cat(currentOutputBeat(511, 256), roundedHalf))

  def recordError(code: UInt): Unit = {
    when(status === Status.Ok.U) { status := code }
  }
  def fail(code: UInt): Unit = {
    recordError(code)
    state := finish
  }

  when(active && state =/= finish) { cycles := cycles + 1.U }
  // Record cancellation before response handlers so a simultaneously observed
  // actual response fault can take precedence; an older non-OK status is never
  // overwritten. No outstanding operation is removed by this assignment.
  when(active && cancel) { recordError(ElementwiseLoanOp.Aborted.U) }

  when(io.job.fire) {
    job := io.job.bits
    token := 0.U; beat := 0.U; lane := 0.U
    chunk := false.B; emitPass := false.B
    accumulator := 0.U; normalized := 0.U
    operation := square; sequence := 0.U
    status := Status.Ok.U; bytes := 0.U; cycles := 0.U
    val j = io.job.bits
    val vectorBytes = j.tokens.pad(66) << 12
    val weightBytes = (LogicalWidth * 2).U(66.W)
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || base.pad(66) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = badSpan(j.input, vectorBytes) || badSpan(j.weight, weightBytes) ||
      badSpan(j.output, vectorBytes)
    val anyOverlap = overlap(j.input, vectorBytes, j.weight, weightBytes) ||
      overlap(j.input, vectorBytes, j.output, vectorBytes) ||
      overlap(j.weight, weightBytes, j.output, vectorBytes)
    when(j.tokens === 0.U || j.tokens > maxTokens.U ||
      j.hiddenWidth =/= LogicalWidth.U || badAddress || anyOverlap) {
      fail(Status.Bounds.U)
    }.otherwise { state := readInput }
  }

  when(io.memory.fire) {
    // This fires even after cancellation of a previously offered request.
    state := MuxLookup(state, waitInput)(Seq(
      readWeight -> waitWeight, writeOutput -> waitOutput))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(job.tag, sequence)) {
      // Consume a stray packet, poison admission, retain the real obligation.
      // If its matching response never arrives, recovery is blocked rather
      // than falsely claiming drain or dropping the accepted request.
      recordError(Status.Protocol.U)
    }.otherwise {
      sequence := sequence + 1.U
      // Real successful write ACKs count even while cancellation drains.
      when(state === waitOutput && !r.error) { bytes := bytes + 64.U }
      when(r.error) { fail(Status.Memory.U) }
        .elsewhen(status =/= Status.Ok.U || cancel) { state := finish }
        .otherwise {
          when(state === waitInput || state === waitWeight) {
            val nonfinite = (0 until 32).map { i =>
              r.data(i * 16 + 14, i * 16 + 7) === 255.U
            }.reduce(_ || _)
            when(nonfinite) { fail(Status.Numerical.U) }
              .otherwise {
                when(state === waitWeight) { weights(beat) := r.data }
                  .otherwise { input(beat) := r.data }
                when(beat === (BankBeats - 1).U) {
                  beat := 0.U; lane := 0.U
                  when(state === waitWeight) {
                    if (useVectorEpilogue) { state := loanIssue }
                    else { operation := normalize; state := scalarIssue }
                  }
                    .elsewhen(emitPass) { state := readWeight }
                    .otherwise {
                      accumulator := 0.U; operation := square; state := scalarIssue
                    }
                }.otherwise {
                  beat := beat + 1.U
                  state := Mux(state === waitWeight, readWeight, readInput)
                }
              }
          }
          when(state === waitOutput) {
            when(beat === (BankBeats - 1).U) {
              beat := 0.U; lane := 0.U
              when(!chunk) { chunk := true.B; state := readInput }
                .elsewhen(token + 1.U === job.tokens) {
                  when(bytes + 64.U === expectedBytes) { state := finish }
                    .otherwise { fail(Status.Protocol.U) }
                }.otherwise {
                  token := token + 1.U; chunk := false.B; emitPass := false.B
                  accumulator := 0.U; normalized := 0.U
                  operation := square; state := readInput
                }
            }.otherwise { beat := beat + 1.U; state := writeOutput }
          }
        }
    }
  }

  when(io.scalar.request.fire) { state := scalarWait }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits
    when(io.scalar.error || !TensorMath.finite(r) || scalarBf16Overflow) { fail(Status.Numerical.U) }
      .elsewhen(status =/= Status.Ok.U || cancel) { state := finish }
      .otherwise {
        value := r
        state := scalarIssue
        switch(operation) {
          is(square) { operation := sum }
          is(sum) {
            accumulator := r
            when(lane(3, 0) === 15.U) { operation := residue }
              .otherwise { lane := lane + 1.U; operation := square }
          }
          is(residue) {
            outputWrite := true.B
            outputWriteIndex := partialBeat
            outputWriteData := updatedPartialWords.asUInt
            accumulator := 0.U
            when(lane === (BankWidth - 1).U) {
              lane := 0.U
              when(!chunk) {
                chunk := true.B; beat := 0.U
                operation := square; state := readInput
              }.otherwise {
                normalized := 0.U; operation := foldResidue
              }
            }.otherwise { lane := lane + 1.U; operation := square }
          }
          is(foldResidue) {
            accumulator := r
            when(lane(1, 0) === 3.U) { operation := foldLane }
              .otherwise { lane := lane + 1.U }
          }
          is(foldLane) {
            normalized := r; accumulator := 0.U
            when(lane === 31.U) { operation := mean }
              .otherwise { lane := lane + 1.U; operation := foldResidue }
          }
          is(mean) { operation := epsilon }
          is(epsilon) { operation := root }
          is(root) { operation := inverse }
          is(inverse) {
            invRms := r
            // All overlaid partials are dead before the first output update.
            emitPass := true.B; chunk := false.B; beat := 0.U; lane := 0.U
            state := readInput
          }
        }
        if (!useVectorEpilogue) {
          when(operation === normalize) { normalized := r; operation := onePlusWeight }
          when(operation === onePlusWeight) { operation := weighted }
          when(operation === weighted) {
            // Combinational one-lane patch of the SAME output bank write port.
            // No retained wide value, normalized vector, or second owner.
            val updatedScalarWords = Wire(Vec(32, UInt(16.W)))
            updatedScalarWords := currentOutputBeat.asTypeOf(Vec(32, UInt(16.W)))
            updatedScalarWords(lane(4, 0)) := scalarRounded
            outputWrite := true.B
            outputWriteIndex := lane(9, 5)
            outputWriteData := updatedScalarWords.asUInt
            when(lane === (BankWidth - 1).U) {
              beat := 0.U; state := writeOutput
            }.otherwise { lane := lane + 1.U; operation := normalize }
          }
        }
      }
  }

  when(io.loan.request.fire) {
    assert(io.loan.request.bits.tag === sequence, "loan request must carry the retained transaction tag")
    assert(io.loan.request.bits.op === ElementwiseLoanOp.RmsEpilogue.U,
      "the fixed-bank RMS owner borrows only the RMS epilogue")
    state := Mux(status =/= Status.Ok.U || cancel, loanAbort, loanWait)
  }
  when(state === loanWait && cancel) {
    // result.ready was suppressed above, including a held successful result.
    // Preserve an already-present bad terminal before the service's upcoming
    // abort pulse replaces that terminal's status with Aborted.
    when(io.loan.result.valid) {
      when(io.loan.result.bits.tag =/= sequence) { recordError(Status.Protocol.U) }
        .elsewhen(io.loan.result.bits.status =/= Status.Ok.U) {
          recordError(io.loan.result.bits.status)
        }.elsewhen(loanNonfinite || bf16Overflow) { recordError(Status.Numerical.U) }
    }
    state := loanAbort
  }
  when(state === loanAbort) { state := loanDrain }
  when(io.loan.result.fire) {
    val r = io.loan.result.bits
    when(r.tag =/= sequence) {
      // A malformed terminal cannot prove the expected loan was discharged.
      // Keep its tag/debt even if the service drops busy after this packet.
      recordError(Status.Protocol.U); state := loanDrain
    }
      .elsewhen(r.status =/= Status.Ok.U) { fail(r.status) }
      .elsewhen(state === loanDrain || status =/= Status.Ok.U || cancel) {
        // A buggy service returning Ok after abort still cannot commit output.
        recordError(ElementwiseLoanOp.Aborted.U); state := finish
      }.elsewhen(loanNonfinite || bf16Overflow) { fail(Status.Numerical.U) }
      .otherwise {
        sequence := sequence + 1.U
        outputWrite := true.B
        outputWriteIndex := lane(9, 5)
        outputWriteData := updatedOutputBeat
        when(lane === (BankWidth - 16).U) {
          beat := 0.U; state := writeOutput
        }.otherwise { lane := lane + 16.U; state := loanIssue }
      }
  }
  when(outputWrite) { output(outputWriteIndex) := outputWriteData }

  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
  // clear cannot erase a held terminal, an offered request, or accepted debt.
  // Clear is level-sensitive here, not queued. A one-cycle clear during work
  // cancels only; a level held into locked also attests recovery at that time.
  when((state === idle || state === locked) && io.clear && !io.abort && io.drained) {
    state := recoverPulse
  }
  // One pulse only. Do not feed sticky resetRequired back to loan.abort/reset.
  // The existing service will clear only loan-origin poison in its lLocked
  // state. DDR-origin poison cannot be cleared by this loan control.
  when(state === recoverPulse) { state := recoverWait }
  when(state === recoverWait && !io.abort && !io.loan.resetRequired &&
    !io.vectorUnavailable && servicesQuiet) {
    status := Status.Ok.U; state := idle
  }

  assert(PopCount(Seq(io.memory.valid, io.scalar.request.valid, io.loan.request.valid)) <= 1.U,
    "one borrowed service transaction at a time")
  if (!useVectorEpilogue) {
    assert(!io.loan.request.valid, "same-bank Scalar epilogue must issue zero loans")
  }
  when(io.loan.request.valid) {
    assert(emitPass && lane(3, 0) === 0.U, "loan must consume an aligned output half-beat")
    assert(!io.loan.abort && !io.loan.resetLoan, "held loan offers must remain acceptable")
  }
  when(outputWrite) {
    assert(status === Status.Ok.U && !cancel,
      "cancelled or failed arithmetic must never update the output bank")
  }
  when(io.done.valid) {
    assert(io.drained, "completion requires drained memory, Scalar, and loan")
    when(status === Status.Ok.U) {
      assert(bytes === expectedBytes, "success requires all 64-byte write ACKs")
    }
  }
  when(io.loan.resetLoan) {
    assert(!outstanding && !io.loan.busy, "loan recovery must follow terminal drain")
  }
}

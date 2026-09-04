package gemmini

import chisel3._
import chisel3.util._

/** Model-independent decomposition of every high-level operator required by
  * Qwen2-1.5B, Qwen3.5-35B-A3B and Qwen3.8-Flash-Next.  This is the mandatory
  * coverage boundary: an accepted operator always emits at least one concrete
  * primitive micro-op; unknown ids are rejected rather than falling back.
  *
  * Primitive variants identify transaction-local scratch operands and policy
  * choices. Tensor shapes, strides, scales and physical addresses remain in
  * descriptors referenced by src0/src1/dst.
  */
class HeteroModelOperatorSequencer extends Module {
  private val phaseBits = 6
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val command = Flipped(Decoupled(new HeteroOperatorCommand))
    val microOp = Decoupled(new HeteroPrimitiveMicroOp)
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidOperator = Output(Bool())
  })

  def countFor(id: UInt): UInt = {
    val count = WireDefault(0.U(phaseBits.W))
    switch(id) {
      is(HeteroModelOperatorId.TokenEmbedding) { count := 1.U }
      is(HeteroModelOperatorId.RmsNorm) { count := 1.U }
      is(HeteroModelOperatorId.DenseProjection) { count := 1.U }
      is(HeteroModelOperatorId.QkvBias) { count := 1.U }
      is(HeteroModelOperatorId.PartialRope) { count := 1.U }
      is(HeteroModelOperatorId.GqaBroadcast) { count := 1.U }
      is(HeteroModelOperatorId.DenseAttention) { count := 4.U }
      is(HeteroModelOperatorId.AttentionOutputGate) { count := 2.U }
      is(HeteroModelOperatorId.ResidualAdd) { count := 1.U }
      is(HeteroModelOperatorId.SiluTimesUp) { count := 2.U }
      is(HeteroModelOperatorId.KvAppend) { count := 1.U }
      is(HeteroModelOperatorId.KvGather) { count := 1.U }
      is(HeteroModelOperatorId.LmHead) { count := 1.U }
      is(HeteroModelOperatorId.MultimodalRope) { count := 2.U }
      is(HeteroModelOperatorId.LogitsTopK) { count := 1.U }
      is(HeteroModelOperatorId.PaddingMask) { count := 1.U }
      is(HeteroModelOperatorId.TensorView) { count := 1.U }

      is(HeteroModelOperatorId.GdnProjection) { count := 1.U }
      is(HeteroModelOperatorId.GdnCausalConv) { count := 4.U }
      is(HeteroModelOperatorId.GdnRecurrentUpdate) { count := 20.U }
      is(HeteroModelOperatorId.GdnGatedNormOutput) { count := 4.U }

      is(HeteroModelOperatorId.MoeRouterTopK) { count := 12.U }
      is(HeteroModelOperatorId.MoeDispatch) { count := 2.U }
      is(HeteroModelOperatorId.MoeRoutedExperts) { count := 5.U }
      is(HeteroModelOperatorId.MoeSharedExpert) { count := 7.U }
      is(HeteroModelOperatorId.MoeRouteReduce) { count := 2.U }
      is(HeteroModelOperatorId.MtpStateTransaction) { count := 4.U }

      is(HeteroModelOperatorId.GatedResidualRead) { count := 13.U }
      is(HeteroModelOperatorId.GatedResidualWrite) { count := 2.U }
      is(HeteroModelOperatorId.GroupRmsNorm) { count := 1.U }
      is(HeteroModelOperatorId.PleNgramHash) { count := 1.U }
      is(HeteroModelOperatorId.PleSparseRowFetch) { count := 1.U }
      is(HeteroModelOperatorId.PleProjectionDwConv) { count := 19.U }
      is(HeteroModelOperatorId.QsaIndexProjection) { count := 1.U }
      is(HeteroModelOperatorId.QsaBlockSummary) { count := 10.U }
      is(HeteroModelOperatorId.QsaStreamingTopK) { count := 2.U }
      is(HeteroModelOperatorId.QsaSparseKvGather) { count := 1.U }
      is(HeteroModelOperatorId.QsaSparseAttention) { count := 15.U }

      is(HeteroModelOperatorId.VisionPatchEmbed) { count := 3.U }
      is(HeteroModelOperatorId.VisionPosition) { count := 7.U }
      is(HeteroModelOperatorId.VisionLayerNorm) { count := 1.U }
      is(HeteroModelOperatorId.VisionAttention) { count := 10.U }
      is(HeteroModelOperatorId.VisionMlpGelu) { count := 5.U }
      is(HeteroModelOperatorId.VisionPatchMerge) { count := 7.U }
      is(HeteroModelOperatorId.VisionProject) { count := 2.U }
      is(HeteroModelOperatorId.VisionWindowLayout) { count := 1.U }
      is(HeteroModelOperatorId.VisionDeepstackInject) { count := 2.U }
      is(HeteroModelOperatorId.VisionTokenScatter) { count := 1.U }
    }
    count
  }

  val active = RegInit(false.B)
  val command = Reg(new HeteroOperatorCommand)
  val phase = RegInit(0.U(phaseBits.W))
  val phaseCount = RegInit(0.U(phaseBits.W))
  val requestedCount = countFor(io.command.bits.operatorId)

  io.command.ready := !active
  io.busy := active
  io.done := false.B
  io.invalidOperator := io.command.valid && io.command.ready && requestedCount === 0.U
  io.microOp.valid := active

  val op = Wire(new HeteroPrimitiveMicroOp)
  op.owner := HeteroPrimitiveOwner.Control
  op.opcode := HeteroPrimitiveOpcode.Barrier
  op.phase := phase
  op.variant := 0.U
  op.txnId := command.txnId
  op.src0 := command.src0
  op.src1 := command.src1
  op.dst := command.dst
  op.rows := command.rows
  op.columns := command.columns
  op.depth := command.depth
  op.aux := Cat(command.aux1, command.aux0)
  op.flags := command.flags
  op.stateful := false.B
  op.first := phase === 0.U
  op.last := phase + 1.U >= phaseCount

  def emit(owner: UInt, opcode: UInt, variant: Int = 0, stateful: Boolean = false): Unit = {
    op.owner := owner
    op.opcode := opcode
    op.variant := variant.U
    op.stateful := stateful.B
  }

  switch(command.operatorId) {
    is(HeteroModelOperatorId.TokenEmbedding) {
      emit(HeteroPrimitiveOwner.Dma, HeteroPrimitiveOpcode.DmaGather, 0)
    }
    is(HeteroModelOperatorId.RmsNorm) {
      emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRmsNorm, 0)
    }
    is(HeteroModelOperatorId.DenseProjection) {
      emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 0)
    }
    is(HeteroModelOperatorId.QkvBias) {
      emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 0)
    }
    is(HeteroModelOperatorId.PartialRope) {
      emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRope, 0)
    }
    is(HeteroModelOperatorId.GqaBroadcast) {
      emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuBroadcast, 0)
    }
    is(HeteroModelOperatorId.DenseAttention) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixQk, 0) }
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuCausalMask, 0) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuOnlineSoftmax, 0, stateful = true) }
        is(3.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixPv, 0) }
      }
    }
    is(HeteroModelOperatorId.AttentionOutputGate) {
      when(phase === 0.U) {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSigmoid, 0)
      }.otherwise {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 0)
      }
    }
    is(HeteroModelOperatorId.ResidualAdd) {
      emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 1)
    }
    is(HeteroModelOperatorId.SiluTimesUp) {
      when(phase === 0.U) {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSilu, 0)
      }.otherwise {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 1)
      }
    }
    is(HeteroModelOperatorId.KvAppend) {
      emit(HeteroPrimitiveOwner.KvMemory, HeteroPrimitiveOpcode.KvAppend, 0, stateful = true)
    }
    is(HeteroModelOperatorId.KvGather) {
      emit(HeteroPrimitiveOwner.KvMemory, HeteroPrimitiveOpcode.KvGather, 0, stateful = true)
    }
    is(HeteroModelOperatorId.LmHead) {
      emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemv, 0)
    }
    is(HeteroModelOperatorId.MultimodalRope) {
      when(phase === 0.U) {
        emit(HeteroPrimitiveOwner.Vision, HeteroPrimitiveOpcode.VisionMropeMap, 0)
      }.otherwise {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRope, 1)
      }
    }
    is(HeteroModelOperatorId.LogitsTopK) {
      emit(HeteroPrimitiveOwner.Selection, HeteroPrimitiveOpcode.SelectTopK, 0)
    }
    is(HeteroModelOperatorId.PaddingMask) {
      emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuGate, 1)
    }
    is(HeteroModelOperatorId.TensorView) {
      // Descriptor alias/view operation. It is explicit and cannot trigger CPU fallback.
      emit(HeteroPrimitiveOwner.Control, HeteroPrimitiveOpcode.Barrier, 1)
    }

    is(HeteroModelOperatorId.GdnProjection) {
      emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 2)
    }
    is(HeteroModelOperatorId.GdnCausalConv) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.State, HeteroPrimitiveOpcode.StateConvWindow, 0, stateful = true) }
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 2) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReduceSum, 0) }
        is(3.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSilu, 0) }
      }
    }
    is(HeteroModelOperatorId.GdnRecurrentUpdate) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 2) } // a + dt_bias
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSoftplus, 0) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuExp, 0) } // exp(A_log)
        is(3.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 3) } // -A * softplus
        is(4.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuExp, 1) } // state decay
        is(5.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSigmoid, 1) } // beta
        is(6.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuL2Norm, 0) } // Q
        is(7.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 0) } // 1/sqrt(K)
        is(8.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuL2Norm, 1) } // K
        is(9.U) { emit(HeteroPrimitiveOwner.State, HeteroPrimitiveOpcode.StateRead, 0, stateful = true) }
        is(10.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 4) } // M *= decay
        is(11.U) { emit(HeteroPrimitiveOwner.State, HeteroPrimitiveOpcode.StateWrite, 0, stateful = true) }
        is(12.U) { emit(HeteroPrimitiveOwner.State, HeteroPrimitiveOpcode.StateRead, 1, stateful = true) }
        is(13.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemv, 3) } // K^T M
        is(14.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSub, 0) } // V - memory
        is(15.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 5) } // beta * delta
        is(16.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixOuter, 0) } // K outer delta
        is(17.U) { emit(HeteroPrimitiveOwner.State, HeteroPrimitiveOpcode.StateWrite, 1, stateful = true) }
        is(18.U) { emit(HeteroPrimitiveOwner.State, HeteroPrimitiveOpcode.StateRead, 2, stateful = true) }
        is(19.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemv, 4) } // Q^T M
      }
    }
    is(HeteroModelOperatorId.GdnGatedNormOutput) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRmsNorm, 1) }
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSilu, 1) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 6) }
        is(3.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 3) }
      }
    }

    is(HeteroModelOperatorId.MoeRouterTopK) {
      // Full router softmax, stable top-k, and optional selected-probability renorm.
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemv, 5) }
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReduceMax, 0) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSub, 1) }
        is(3.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 1) }
        is(4.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuExp2, 0) }
        is(5.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReduceSum, 1) }
        is(6.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReciprocal, 0) }
        is(7.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 7) }
        is(8.U) { emit(HeteroPrimitiveOwner.Selection, HeteroPrimitiveOpcode.SelectTopK, 1) }
        is(9.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReduceSum, 2) }
        is(10.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReciprocal, 1) }
        is(11.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 8) }
      }
    }
    is(HeteroModelOperatorId.MoeDispatch) {
      when(phase === 0.U) {
        emit(HeteroPrimitiveOwner.Selection, HeteroPrimitiveOpcode.SelectRoute, 0, stateful = true)
      }.otherwise {
        emit(HeteroPrimitiveOwner.Dma, HeteroPrimitiveOpcode.DmaGather, 1, stateful = true)
      }
    }
    is(HeteroModelOperatorId.MoeRoutedExperts) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 4) } // packed gate/up
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSilu, 2) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 9) }
        is(3.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 5) } // down
        is(4.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 2) } // route weight
      }
    }
    is(HeteroModelOperatorId.MoeSharedExpert) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 6) }
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSilu, 3) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 10) }
        is(3.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 7) }
        is(4.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemv, 6) }
        is(5.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSigmoid, 2) }
        is(6.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 11) }
      }
    }
    is(HeteroModelOperatorId.MoeRouteReduce) {
      when(phase === 0.U) {
        emit(HeteroPrimitiveOwner.Selection, HeteroPrimitiveOpcode.SelectMerge, 0, stateful = true)
      }.otherwise {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 3)
      }
    }
    is(HeteroModelOperatorId.MtpStateTransaction) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.State, HeteroPrimitiveOpcode.StateBegin, 0, stateful = true) }
        is(1.U) { emit(HeteroPrimitiveOwner.Selection, HeteroPrimitiveOpcode.SelectMtpVerify, 0, stateful = true) }
        is(2.U) {
          op.owner := HeteroPrimitiveOwner.State
          op.opcode := Mux(command.flags(0), HeteroPrimitiveOpcode.StateRollback, HeteroPrimitiveOpcode.StateCommit)
          op.variant := 0.U
          op.stateful := true.B
        }
        is(3.U) { emit(HeteroPrimitiveOwner.Control, HeteroPrimitiveOpcode.Barrier, 2, stateful = true) }
      }
    }

    is(HeteroModelOperatorId.GatedResidualRead) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuGroupRmsNorm, 0) }
        is(1.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixLowRank, 0) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 3) }
        is(3.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSilu, 4) }
        is(4.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixLowRank, 1) }
        is(5.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSigmoid, 3) }
        is(6.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 12) }
        is(7.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReduceSum, 3) }
        is(8.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 4) }
        is(9.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemv, 7) }
        is(10.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 5) }
        is(11.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSigmoid, 4) }
        is(12.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 6) }
      }
    }
    is(HeteroModelOperatorId.GatedResidualWrite) {
      when(phase === 0.U) {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 13, stateful = true)
      }.otherwise {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 4, stateful = true)
      }
    }
    is(HeteroModelOperatorId.GroupRmsNorm) {
      emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuGroupRmsNorm, 1)
    }
    is(HeteroModelOperatorId.PleNgramHash) {
      emit(HeteroPrimitiveOwner.Vision, HeteroPrimitiveOpcode.PleHash, 0, stateful = true)
    }
    is(HeteroModelOperatorId.PleSparseRowFetch) {
      emit(HeteroPrimitiveOwner.Dma, HeteroPrimitiveOpcode.DmaGather, 2, stateful = true)
    }
    is(HeteroModelOperatorId.PleProjectionDwConv) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 8) } // key projection
        is(1.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 9) } // value projection
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuGroupRmsNorm, 2) }
        is(3.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuGroupRmsNorm, 3) }
        is(4.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixQk, 1) }
        is(5.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 7) }
        is(6.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAbs, 0) }
        is(7.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMax, 0) }
        is(8.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRsqrt, 0) }
        is(9.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 14) }
        is(10.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuCompareSelect, 0) }
        is(11.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSigmoid, 5) }
        is(12.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 15) }
        is(13.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuGroupRmsNorm, 4) }
        is(14.U) { emit(HeteroPrimitiveOwner.State, HeteroPrimitiveOpcode.StateConvWindow, 1, stateful = true) }
        is(15.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 16) }
        is(16.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReduceSum, 4) }
        is(17.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSilu, 5) }
        is(18.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 5) }
      }
    }
    is(HeteroModelOperatorId.QsaIndexProjection) {
      emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 10)
    }
    is(HeteroModelOperatorId.QsaBlockSummary) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuL2Norm, 2) }
        is(1.U) { emit(HeteroPrimitiveOwner.Selection, HeteroPrimitiveOpcode.SelectBlockPool, 0, stateful = true) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 8) }
        is(3.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuL2Norm, 3) }
        is(4.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRope, 2) }
        is(5.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRope, 3) }
        is(6.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixQk, 2) }
        is(7.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMax, 1) }
        is(8.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReduceSum, 5) }
        is(9.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 9) }
      }
    }
    is(HeteroModelOperatorId.QsaStreamingTopK) {
      when(phase === 0.U) {
        emit(HeteroPrimitiveOwner.Selection, HeteroPrimitiveOpcode.SelectTopK, 2, stateful = true)
      }.otherwise {
        emit(HeteroPrimitiveOwner.Selection, HeteroPrimitiveOpcode.SelectExpand, 0, stateful = true)
      }
    }
    is(HeteroModelOperatorId.QsaSparseKvGather) {
      emit(HeteroPrimitiveOwner.KvMemory, HeteroPrimitiveOpcode.KvGather, 1, stateful = true)
    }
    is(HeteroModelOperatorId.QsaSparseAttention) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 11) } // packed Q/gate
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRmsNorm, 2) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRope, 4) }
        is(3.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 12) } // K
        is(4.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRmsNorm, 3) }
        is(5.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRope, 5) }
        is(6.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 13) } // V
        is(7.U) { emit(HeteroPrimitiveOwner.KvMemory, HeteroPrimitiveOpcode.KvAppend, 1, stateful = true) }
        is(8.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixQk, 3) }
        is(9.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuCausalMask, 1) }
        is(10.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuOnlineSoftmax, 1, stateful = true) }
        is(11.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixPv, 1) }
        is(12.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuSigmoid, 6) }
        is(13.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 17) }
        is(14.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 14) }
      }
    }

    is(HeteroModelOperatorId.VisionPatchEmbed) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Vision, HeteroPrimitiveOpcode.VisionPatch3d, 0) }
        is(1.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixConv, 0) }
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 7) } // Conv3D bias
      }
    }
    is(HeteroModelOperatorId.VisionPosition) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Vision, HeteroPrimitiveOpcode.VisionPosInterp, 0) }
        is(1.U) { emit(HeteroPrimitiveOwner.Dma, HeteroPrimitiveOpcode.DmaGather, 3) }
        is(2.U) { emit(HeteroPrimitiveOwner.Dma, HeteroPrimitiveOpcode.DmaGather, 4) }
        is(3.U) { emit(HeteroPrimitiveOwner.Dma, HeteroPrimitiveOpcode.DmaGather, 5) }
        is(4.U) { emit(HeteroPrimitiveOwner.Dma, HeteroPrimitiveOpcode.DmaGather, 6) }
        is(5.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuMul, 18) }
        is(6.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuReduceSum, 6) }
      }
    }
    is(HeteroModelOperatorId.VisionLayerNorm) {
      emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuLayerNorm, 0)
    }
    is(HeteroModelOperatorId.VisionAttention) {
      // Qwen3.5/Qwen4-exp vision attention uses biased QKV and output
      // projections and scales QK before non-causal softmax.
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 15) }
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 8) } // QKV bias
        is(2.U) { emit(HeteroPrimitiveOwner.Vision, HeteroPrimitiveOpcode.VisionMropeMap, 1) }
        is(3.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuRope, 6) }
        is(4.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixQk, 4) }
        is(5.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuScale, 10) }
        is(6.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuOnlineSoftmax, 2, stateful = true) }
        is(7.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixPv, 2) }
        is(8.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 16) }
        is(9.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 9) } // projection bias
      }
    }
    is(HeteroModelOperatorId.VisionMlpGelu) {
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 17) }
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 10) } // fc1 bias
        is(2.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuGelu, 0) }
        is(3.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 18) }
        is(4.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 11) } // fc2 bias
      }
    }
    is(HeteroModelOperatorId.VisionPatchMerge) {
      // Spatial merge address remap followed by LayerNorm and the official
      // biased Linear-GELU-Linear merger projection.
      switch(phase) {
        is(0.U) { emit(HeteroPrimitiveOwner.Vision, HeteroPrimitiveOpcode.VisionPatchMerge, 0) }
        is(1.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuLayerNorm, 1) }
        is(2.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 19) }
        is(3.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 12) }
        is(4.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuGelu, 1) }
        is(5.U) { emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 20) }
        is(6.U) { emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 13) }
      }
    }
    is(HeteroModelOperatorId.VisionProject) {
      when(phase === 0.U) {
        emit(HeteroPrimitiveOwner.Matrix, HeteroPrimitiveOpcode.MatrixGemm, 21)
      }.otherwise {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 14)
      }
    }
    is(HeteroModelOperatorId.VisionWindowLayout) {
      emit(HeteroPrimitiveOwner.Vision, HeteroPrimitiveOpcode.VisionWindow, 0)
    }
    is(HeteroModelOperatorId.VisionDeepstackInject) {
      when(phase === 0.U) {
        emit(HeteroPrimitiveOwner.Dma, HeteroPrimitiveOpcode.DmaGather, 7)
      }.otherwise {
        emit(HeteroPrimitiveOwner.Sfu, HeteroPrimitiveOpcode.SfuAdd, 6)
      }
    }
    is(HeteroModelOperatorId.VisionTokenScatter) {
      emit(HeteroPrimitiveOwner.Dma, HeteroPrimitiveOpcode.DmaScatter, 0)
    }
  }

  io.microOp.bits := op

  when(io.clear) {
    active := false.B
    phase := 0.U
    phaseCount := 0.U
  }.otherwise {
    when(io.command.fire && requestedCount =/= 0.U) {
      command := io.command.bits
      phase := 0.U
      phaseCount := requestedCount
      active := true.B
    }
    when(io.microOp.fire) {
      when(op.last) {
        active := false.B
        phase := 0.U
        phaseCount := 0.U
        io.done := true.B
      }.otherwise {
        phase := phase + 1.U
      }
    }
  }

  when(active) {
    assert(phaseCount =/= 0.U)
    assert(op.opcode =/= HeteroPrimitiveOpcode.Nop)
    assert(HeteroPrimitiveCapability.source(op.owner, op.opcode))
    assert(phase < phaseCount)
  }
}

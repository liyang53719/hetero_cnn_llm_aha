package gemmini

import chisel3._
import chisel3.util._

/** Shared wrapper for a fixed tensor-level microprogram. */
abstract class HeteroCompositeOperatorPrimitive(
    val operatorProgram: Seq[HeteroMicroInstruction],
    val operatorName: String,
    val descriptorBits: Int = 24,
    val dimensionBits: Int = 16,
    val tagBits: Int = 16
) extends Module {
  override def desiredName: String = operatorName

  val io = IO(new Bundle {
    val launch = Flipped(Decoupled(new HeteroOperatorLaunch(
      descriptorBits = descriptorBits,
      dimensionBits = dimensionBits,
      tagBits = tagBits
    )))
    val microOp = Decoupled(new HeteroTensorMicroOp(
      descriptorBits = descriptorBits,
      dimensionBits = dimensionBits,
      tagBits = tagBits
    ))
    val completion = Flipped(Decoupled(new HeteroPrimitiveCompletion(tagBits)))
    val result = Decoupled(new HeteroOperatorResult(tagBits))
    val busy = Output(Bool())
    val protocolError = Output(Bool())
  })

  private val sequencer = Module(new HeteroMicroProgramSequencer(
    program = operatorProgram,
    descriptorBits = descriptorBits,
    dimensionBits = dimensionBits,
    tagBits = tagBits
  ))
  sequencer.io.launch <> io.launch
  io.microOp <> sequencer.io.microOp
  sequencer.io.completion <> io.completion
  io.result <> sequencer.io.result
  io.busy := sequencer.io.busy
  io.protocolError := sequencer.io.protocolError
}

object HeteroGdnProgram {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._

  /**
    * Descriptor slots:
    *   0 hidden/input, 1 qkv_weight, 2 z_weight, 3 a_weight,
    *   4 beta_weight, 5 conv_weight, 6 conv_state,
    *   7 recurrent_state, 8 a_log_dt_bias, 9 norm_weight,
    *   10 output_weight, 11 qkv_scratch, 12 parameter_scratch,
    *   13 vector_scratch, 14 output, 15 state_journal.
    * Dimension slots:
    *   0 tokens, 1 hidden, 2 qk_heads, 3 value_heads,
    *   4 key_dim, 5 value_dim, 6 conv_kernel, 7 chunk_size.
    */
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(MatrixGemm, 0x00, src0 = 0, src1 = 1, dst = 11, m = 0, n = 2, k = 1),
    HeteroMicroInstruction(MatrixGemm, 0x01, src0 = 0, src1 = 2, dst = 12, m = 0, n = 3, k = 1, index0 = 0),
    HeteroMicroInstruction(MatrixGemm, 0x02, src0 = 0, src1 = 3, dst = 12, m = 0, n = 3, k = 1, index0 = 1),
    HeteroMicroInstruction(MatrixGemm, 0x03, src0 = 0, src1 = 4, dst = 12, m = 0, n = 3, k = 1, index0 = 2),
    HeteroMicroInstruction(StateRead, 0x04, flag(HeteroPrimitiveFlags.Stateful), src0 = 6, dst = 13, m = 6),
    HeteroMicroInstruction(DepthwiseConv, 0x05,
      flag(HeteroPrimitiveFlags.Causal, HeteroPrimitiveFlags.ApplyActivation, HeteroPrimitiveFlags.Stateful),
      src0 = 11, src1 = 5, src2 = 13, dst = 11, m = 0, n = 2, k = 6),
    HeteroMicroInstruction(StateWrite, 0x06, flag(HeteroPrimitiveFlags.Stateful), src0 = 13, dst = 6, m = 6),
    HeteroMicroInstruction(L2Norm, 0x07, src0 = 11, dst = 13, m = 0, n = 2, k = 4, index0 = 0),
    HeteroMicroInstruction(L2Norm, 0x08, src0 = 11, dst = 13, m = 0, n = 2, k = 4, index0 = 1),
    HeteroMicroInstruction(Softplus, 0x09, src0 = 12, src1 = 8, dst = 12, m = 0, n = 3, index0 = 1),
    HeteroMicroInstruction(Exp2, 0x0a, src0 = 12, src1 = 8, dst = 12, m = 0, n = 3, index0 = 3),
    HeteroMicroInstruction(Sigmoid, 0x0b, src0 = 12, dst = 12, m = 0, n = 3, index0 = 2),
    HeteroMicroInstruction(StateRead, 0x0c, flag(HeteroPrimitiveFlags.Stateful), src0 = 7, dst = 13, m = 3, n = 4, k = 5),
    HeteroMicroInstruction(VectorMul, 0x0d, flag(HeteroPrimitiveFlags.Stateful), src0 = 13, src1 = 12, dst = 13, m = 3, n = 4, k = 5, index0 = 3),
    HeteroMicroInstruction(MatrixGemv, 0x0e, src0 = 13, src1 = 11, dst = 13, m = 3, n = 5, k = 4, index0 = 0),
    HeteroMicroInstruction(VectorSub, 0x0f, src0 = 11, src1 = 13, dst = 13, m = 0, n = 3, k = 5),
    HeteroMicroInstruction(VectorMul, 0x10, src0 = 13, src1 = 12, dst = 13, m = 0, n = 3, k = 5, index0 = 2),
    HeteroMicroInstruction(MatrixOuter, 0x11,
      flag(HeteroPrimitiveFlags.Stateful), src0 = 11, src1 = 13, src2 = 13, dst = 13,
      m = 3, n = 4, k = 5, index0 = 1),
    HeteroMicroInstruction(MatrixGemv, 0x12, src0 = 13, src1 = 13, dst = 13, m = 3, n = 5, k = 4, index0 = 1),
    HeteroMicroInstruction(RmsNorm, 0x13, src0 = 13, src1 = 9, dst = 13, m = 0, n = 3, k = 5),
    HeteroMicroInstruction(Silu, 0x14, src0 = 12, dst = 12, m = 0, n = 3, k = 5, index0 = 0),
    HeteroMicroInstruction(VectorMul, 0x15, src0 = 13, src1 = 12, dst = 13, m = 0, n = 3, k = 5),
    HeteroMicroInstruction(MatrixGemm, 0x16, src0 = 13, src1 = 10, dst = 14, m = 0, n = 1, k = 3),
    HeteroMicroInstruction(StateWrite, 0x17, flag(HeteroPrimitiveFlags.Stateful), src0 = 13, dst = 7, m = 3, n = 4, k = 5),
    HeteroMicroInstruction(StateCommit, 0x18,
      flag(HeteroPrimitiveFlags.Stateful, HeteroPrimitiveFlags.Commit, HeteroPrimitiveFlags.Last),
      src0 = 15, dst = 15)
  )
}

/** Full Gated-DeltaNet token-mixer primitive for prefill and recurrent decode. */
class HeteroGdnOperatorPrimitive(
    descriptorBits: Int = 24,
    dimensionBits: Int = 16,
    tagBits: Int = 16
) extends HeteroCompositeOperatorPrimitive(
  HeteroGdnProgram.program,
  "HeteroGdnOperatorPrimitive",
  descriptorBits,
  dimensionBits,
  tagBits
)

object HeteroMoeProgram {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._

  /**
    * Descriptor slots:
    *   0 hidden/input, 1 router_weight, 2 router_logits,
    *   3 ranked_routes, 4 dispatch_table, 5 expert_weight_store,
    *   6 expert_batch, 7 gate_up_scratch, 8 expert_output,
    *   9 routed_accumulator, 10 shared_weight, 11 shared_gate_weight,
    *   12 shared_scratch, 13 output, 14 weight_cache_metadata,
    *   15 route_journal.
    * Dimension slots:
    *   0 tokens, 1 hidden, 2 experts, 3 top_k,
    *   4 intermediate, 5 max_batch_tokens, 6 active_routes, 7 reserved.
    */
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(MatrixGemm, 0x00, src0 = 0, src1 = 1, dst = 2, m = 0, n = 2, k = 1),
    HeteroMicroInstruction(StableTopK, 0x01, src0 = 2, dst = 3, m = 0, n = 2, k = 3),
    HeteroMicroInstruction(VectorScatter, 0x02, src0 = 0, src1 = 3, dst = 4, m = 0, n = 3, k = 1),
    HeteroMicroInstruction(DmaRead, 0x03,
      flag(HeteroPrimitiveFlags.RoutedExpert), src0 = 5, src1 = 4, src2 = 14, dst = 6,
      m = 6, n = 4, k = 1),
    HeteroMicroInstruction(MatrixGemm, 0x04,
      flag(HeteroPrimitiveFlags.RoutedExpert, HeteroPrimitiveFlags.ApplyBias),
      src0 = 6, src1 = 5, dst = 7, m = 6, n = 4, k = 1, index0 = 0),
    HeteroMicroInstruction(MatrixGemm, 0x05,
      flag(HeteroPrimitiveFlags.RoutedExpert, HeteroPrimitiveFlags.ApplyBias),
      src0 = 6, src1 = 5, dst = 7, m = 6, n = 4, k = 1, index0 = 1),
    HeteroMicroInstruction(Silu, 0x06, flag(HeteroPrimitiveFlags.RoutedExpert), src0 = 7, dst = 7, m = 6, n = 4, index0 = 0),
    HeteroMicroInstruction(VectorMul, 0x07, flag(HeteroPrimitiveFlags.RoutedExpert), src0 = 7, src1 = 7, dst = 7, m = 6, n = 4),
    HeteroMicroInstruction(MatrixGemm, 0x08,
      flag(HeteroPrimitiveFlags.RoutedExpert), src0 = 7, src1 = 5, dst = 8,
      m = 6, n = 1, k = 4, index0 = 2),
    HeteroMicroInstruction(VectorFma, 0x09,
      flag(HeteroPrimitiveFlags.RoutedExpert), src0 = 8, src1 = 3, src2 = 9, dst = 9,
      m = 0, n = 1, k = 3),
    HeteroMicroInstruction(DmaRead, 0x0a,
      flag(HeteroPrimitiveFlags.SharedExpert), src0 = 10, src2 = 14, dst = 12,
      m = 0, n = 4, k = 1),
    HeteroMicroInstruction(MatrixGemm, 0x0b,
      flag(HeteroPrimitiveFlags.SharedExpert), src0 = 0, src1 = 10, dst = 12,
      m = 0, n = 4, k = 1, index0 = 0),
    HeteroMicroInstruction(MatrixGemm, 0x0c,
      flag(HeteroPrimitiveFlags.SharedExpert), src0 = 0, src1 = 10, dst = 12,
      m = 0, n = 4, k = 1, index0 = 1),
    HeteroMicroInstruction(Silu, 0x0d, flag(HeteroPrimitiveFlags.SharedExpert), src0 = 12, dst = 12, m = 0, n = 4),
    HeteroMicroInstruction(VectorMul, 0x0e, flag(HeteroPrimitiveFlags.SharedExpert), src0 = 12, src1 = 12, dst = 12, m = 0, n = 4),
    HeteroMicroInstruction(MatrixGemm, 0x0f,
      flag(HeteroPrimitiveFlags.SharedExpert), src0 = 12, src1 = 10, dst = 12,
      m = 0, n = 1, k = 4, index0 = 2),
    HeteroMicroInstruction(MatrixGemv, 0x10, flag(HeteroPrimitiveFlags.SharedExpert), src0 = 0, src1 = 11, dst = 8, m = 0, n = 1, k = 1),
    HeteroMicroInstruction(Sigmoid, 0x11, flag(HeteroPrimitiveFlags.SharedExpert), src0 = 8, dst = 8, m = 0),
    HeteroMicroInstruction(VectorMul, 0x12, flag(HeteroPrimitiveFlags.SharedExpert), src0 = 12, src1 = 8, dst = 12, m = 0, n = 1),
    HeteroMicroInstruction(VectorAdd, 0x13, flag(HeteroPrimitiveFlags.Last), src0 = 9, src1 = 12, dst = 13, m = 0, n = 1),
    HeteroMicroInstruction(StateCommit, 0x14,
      flag(HeteroPrimitiveFlags.Stateful, HeteroPrimitiveFlags.Commit, HeteroPrimitiveFlags.Last),
      src0 = 15, dst = 15)
  )
}

/** Routed-expert plus shared-expert MoE primitive, parameterized by descriptors. */
class HeteroMoeOperatorPrimitive(
    descriptorBits: Int = 24,
    dimensionBits: Int = 16,
    tagBits: Int = 16
) extends HeteroCompositeOperatorPrimitive(
  HeteroMoeProgram.program,
  "HeteroMoeOperatorPrimitive",
  descriptorBits,
  dimensionBits,
  tagBits
)

class HeteroMoeRouteItem(
    val tokenBits: Int = 16,
    val expertBits: Int = 9
) extends Bundle {
  val token = UInt(tokenBits.W)
  val expert = UInt(expertBits.W)
  val weight = UInt(32.W)
  val last = Bool()
  override def cloneType: this.type =
    new HeteroMoeRouteItem(tokenBits, expertBits).asInstanceOf[this.type]
}

class HeteroMoeDispatchEntry(
    val tokenBits: Int = 16,
    val expertBits: Int = 9,
    val routeBits: Int = 10
) extends Bundle {
  val token = UInt(tokenBits.W)
  val expert = UInt(expertBits.W)
  val weight = UInt(32.W)
  val routeOrdinal = UInt(routeBits.W)
  val firstForExpert = Bool()
  val lastForExpert = Bool()
  override def cloneType: this.type =
    new HeteroMoeDispatchEntry(tokenBits, expertBits, routeBits).asInstanceOf[this.type]
}

/**
  * Stable token-to-expert dispatch planner.
  *
  * Routes are collected in token/rank order, counted per expert, then emitted
  * in ascending expert id while preserving the original order inside each
  * expert. This is the deterministic batching contract used by Top-8 and
  * Top-10 MoE. The bounded implementation is intended for one compiler-chosen
  * token microbatch; larger batches are tiled by the descriptor scheduler.
  */
class HeteroMoeDispatchPlanner(
    val maxExperts: Int = 512,
    val maxRoutes: Int = 160,
    val tokenBits: Int = 16
) extends Module {
  require(maxExperts >= 1)
  require(maxRoutes >= 1)
  private val expertBits = math.max(1, log2Ceil(maxExperts))
  private val routeBits = math.max(1, log2Ceil(maxRoutes + 1))

  val io = IO(new Bundle {
    val start = Input(Bool())
    val in = Flipped(Decoupled(new HeteroMoeRouteItem(tokenBits, expertBits)))
    val out = Decoupled(new HeteroMoeDispatchEntry(tokenBits, expertBits, routeBits))
    val busy = Output(Bool())
    val done = Output(Bool())
    val overflow = Output(Bool())
    val routeCount = Output(UInt(routeBits.W))
  })

  val sIdle :: sCollect :: sFindExpert :: sScanRoutes :: sEmit :: Nil = Enum(5)
  val state = RegInit(sIdle)
  val tokens = Reg(Vec(maxRoutes, UInt(tokenBits.W)))
  val experts = Reg(Vec(maxRoutes, UInt(expertBits.W)))
  val weights = Reg(Vec(maxRoutes, UInt(32.W)))
  val expertCounts = Reg(Vec(maxExperts, UInt(routeBits.W)))
  val expertEmitted = Reg(Vec(maxExperts, UInt(routeBits.W)))
  val routeCount = RegInit(0.U(routeBits.W))
  val expertCursor = RegInit(0.U(expertBits.W))
  val routeCursor = RegInit(0.U(routeBits.W))
  val selectedRoute = RegInit(0.U(routeBits.W))
  val overflow = RegInit(false.B)
  val donePulse = RegInit(false.B)

  io.in.ready := state === sCollect && routeCount < maxRoutes.U
  io.out.valid := state === sEmit
  io.out.bits.token := tokens(selectedRoute)
  io.out.bits.expert := experts(selectedRoute)
  io.out.bits.weight := weights(selectedRoute)
  io.out.bits.routeOrdinal := selectedRoute
  io.out.bits.firstForExpert := expertEmitted(expertCursor) === 0.U
  io.out.bits.lastForExpert := expertEmitted(expertCursor) + 1.U >= expertCounts(expertCursor)
  io.busy := state =/= sIdle
  io.done := donePulse
  io.overflow := overflow
  io.routeCount := routeCount
  donePulse := false.B

  when(state === sIdle) {
    when(io.start) {
      routeCount := 0.U
      expertCursor := 0.U
      routeCursor := 0.U
      overflow := false.B
      for (expert <- 0 until maxExperts) {
        expertCounts(expert) := 0.U
        expertEmitted(expert) := 0.U
      }
      state := sCollect
    }
  }.elsewhen(state === sCollect) {
    when(io.in.fire) {
      tokens(routeCount) := io.in.bits.token
      experts(routeCount) := io.in.bits.expert
      weights(routeCount) := io.in.bits.weight
      expertCounts(io.in.bits.expert) := expertCounts(io.in.bits.expert) + 1.U
      routeCount := routeCount + 1.U
      when(io.in.bits.last) {
        expertCursor := 0.U
        routeCursor := 0.U
        state := sFindExpert
      }
    }.elsewhen(io.in.valid && routeCount >= maxRoutes.U) {
      overflow := true.B
    }
  }.elsewhen(state === sFindExpert) {
    when(routeCount === 0.U) {
      state := sIdle
      donePulse := true.B
    }.elsewhen(expertCounts(expertCursor) =/= 0.U) {
      routeCursor := 0.U
      state := sScanRoutes
    }.elsewhen(expertCursor + 1.U >= maxExperts.U) {
      state := sIdle
      donePulse := true.B
    }.otherwise {
      expertCursor := expertCursor + 1.U
    }
  }.elsewhen(state === sScanRoutes) {
    when(routeCursor >= routeCount) {
      when(expertCursor + 1.U >= maxExperts.U) {
        state := sIdle
        donePulse := true.B
      }.otherwise {
        expertCursor := expertCursor + 1.U
        state := sFindExpert
      }
    }.elsewhen(experts(routeCursor) === expertCursor) {
      selectedRoute := routeCursor
      state := sEmit
    }.otherwise {
      routeCursor := routeCursor + 1.U
    }
  }.elsewhen(state === sEmit) {
    when(io.out.fire) {
      expertEmitted(expertCursor) := expertEmitted(expertCursor) + 1.U
      routeCursor := routeCursor + 1.U
      state := sScanRoutes
    }
  }
}

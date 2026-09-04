package heteronpu.operator

import chisel3._
import chisel3.util._

/** Leaf operation codes shared by every model-level primitive.
  *
  * The codes identify existing Matrix/SFU/KV/DMA/state services or the small
  * irregular services that are generated next to this project.  They are not
  * model opcodes: a model operator is a finite, descriptor-driven sequence of
  * these leaf operations.
  */
object PrimitiveKind {
  val Width = 8

  val DmaRead            = 0x01
  val DmaWrite           = 0x02

  val MatrixGemm         = 0x10
  val MatrixGemv         = 0x11
  val MatrixOuter        = 0x12
  val MatrixConv         = 0x13
  val MatrixQk           = 0x14
  val MatrixPv           = 0x15

  val VectorAdd          = 0x20
  val VectorSub          = 0x21
  val VectorMul          = 0x22
  val VectorFma          = 0x23
  val VectorCompare      = 0x24
  val VectorSelect       = 0x25
  val VectorGather       = 0x26
  val VectorScatter      = 0x27
  val VectorBroadcast    = 0x28
  val LayoutTransform    = 0x29
  val ApplyMask          = 0x2a

  val ReduceSum          = 0x30
  val ReduceMax          = 0x31
  val StableTopK         = 0x32
  val StableSort         = 0x33
  val SparseGatherRun    = 0x34
  val Argmax             = 0x35

  val RmsNorm            = 0x40
  val GroupRmsNorm       = 0x41
  val LayerNorm          = 0x42
  val L2Norm             = 0x43

  val Rope               = 0x50
  val OnlineSoftmax      = 0x51
  val Exp2               = 0x52
  val Reciprocal         = 0x53
  val Rsqrt              = 0x54
  val Softplus           = 0x55
  val Sigmoid            = 0x56
  val Silu               = 0x57
  val Gelu               = 0x58
  val SignedSqrt         = 0x59
  val ConfiguredGateAct  = 0x5a

  val DepthwiseConv      = 0x60
  val EmbeddingLookup    = 0x61
  val NgramHash          = 0x62
  val BilinearPosition   = 0x63
  val SpatialMerge       = 0x64
  val MultimodalScatter  = 0x65

  val KvAppend           = 0x70
  val KvGather           = 0x71

  val StateRead          = 0x80
  val StateWrite         = 0x81
  val StateCommit        = 0x82
  val StateResolve       = 0x83
  val MtpCompare         = 0x84
}

object PrimitiveFlags {
  val Width = 16
  val Stateful          = 1 << 0
  val Causal            = 1 << 1
  val Sparse            = 1 << 2
  val ApplyBias         = 1 << 3
  val PartialRotary     = 1 << 4
  val MropeInterleaved  = 1 << 5
  val NonCausal         = 1 << 6
  val RoutedExpert      = 1 << 7
  val SharedExpert      = 1 << 8
  val Commit            = 1 << 9
  val Last              = 1 << 10
  val ApplyActivation   = 1 << 11
  val Gqa               = 1 << 12
  val Broadcast         = 1 << 13
  val Rollback          = 1 << 14
  val Configurable      = 1 << 15

  def of(values: Int*): Int = values.foldLeft(0)(_ | _)
}

/** Compile-time description of one model-operator phase.
  *
  * src/dst select one of the sixteen descriptor roots supplied at launch.
  * m/n/k select one of eight runtime dimensions.  index0/index1 are small
  * semantic literals (projection id, branch id, divisor selector, etc.).
  */
final case class MicroOpTemplate(
    kind: Int,
    flags: Int = 0,
    src0: Int = 15,
    src1: Int = 15,
    src2: Int = 15,
    dst: Int = 15,
    m: Int = 7,
    n: Int = 7,
    k: Int = 7,
    index0: Int = 0,
    index1: Int = 0
) {
  require(kind >= 0 && kind < (1 << PrimitiveKind.Width), s"kind overflow: $kind")
  require(flags >= 0 && flags < (1 << PrimitiveFlags.Width), s"flags overflow: $flags")
  require(Seq(src0, src1, src2, dst).forall(x => x >= 0 && x < 16), "descriptor slot overflow")
  require(Seq(m, n, k).forall(x => x >= 0 && x < 8), "dimension slot overflow")
  require(index0 >= 0 && index0 < 65536 && index1 >= 0 && index1 < 65536, "index overflow")
}

class OperatorLaunch(
    val descriptorBits: Int = 24,
    val dimensionBits: Int = 16,
    val tagBits: Int = 16
) extends Bundle {
  val descriptors = Vec(16, UInt(descriptorBits.W))
  val dimensions = Vec(8, UInt(dimensionBits.W))
  val tag = UInt(tagBits.W)

  /** Runtime semantic mode.  Current assignments:
    *   bit 0: configured output gate uses sigmoid; clear selects SiLU
    *   bit 1: vision merger uses post-shuffle normalization
    *   bit 2: decode/recurrent path; clear selects prefill/chunk path
    * Remaining bits are reserved and forwarded unchanged.
    */
  val mode = UInt(8.W)
}

class TensorMicroOp(
    val descriptorBits: Int = 24,
    val dimensionBits: Int = 16,
    val tagBits: Int = 16
) extends Bundle {
  val kind = UInt(PrimitiveKind.Width.W)
  val flags = UInt(PrimitiveFlags.Width.W)
  val phase = UInt(8.W)
  val tag = UInt(tagBits.W)
  val mode = UInt(8.W)
  val src0 = UInt(descriptorBits.W)
  val src1 = UInt(descriptorBits.W)
  val src2 = UInt(descriptorBits.W)
  val dst = UInt(descriptorBits.W)
  val m = UInt(dimensionBits.W)
  val n = UInt(dimensionBits.W)
  val k = UInt(dimensionBits.W)
  val index0 = UInt(16.W)
  val index1 = UInt(16.W)
}

class PrimitiveCompletion(val tagBits: Int = 16) extends Bundle {
  val tag = UInt(tagBits.W)
  val phase = UInt(8.W)
  val status = UInt(8.W)
}

class OperatorResult(val tagBits: Int = 16) extends Bundle {
  val tag = UInt(tagBits.W)
  val status = UInt(8.W)
  val completedPhases = UInt(8.W)
}

/** Synthesizable, one-transaction-at-a-time microprogram sequencer.
  *
  * A phase is issued exactly once and the next phase cannot issue until the
  * matching completion is consumed.  All output fields remain stable while
  * microOp.ready is low.  A tag/phase mismatch terminates the transaction with
  * a protocol error rather than silently advancing state.
  */
class ProgramPrimitive(
    val program: Seq[MicroOpTemplate],
    val moduleName: String,
    val descriptorBits: Int = 24,
    val dimensionBits: Int = 16,
    val tagBits: Int = 16
) extends Module {
  require(program.nonEmpty, s"$moduleName program must not be empty")
  require(program.length <= 255, s"$moduleName exceeds 8-bit phase count")
  require((program.last.flags & PrimitiveFlags.Last) != 0, s"$moduleName final phase must carry Last")
  require(program.dropRight(1).forall(x => (x.flags & PrimitiveFlags.Last) == 0),
    s"$moduleName has an early Last phase")
  override def desiredName: String = moduleName

  val io = IO(new Bundle {
    val launch = Flipped(Decoupled(new OperatorLaunch(descriptorBits, dimensionBits, tagBits)))
    val microOp = Decoupled(new TensorMicroOp(descriptorBits, dimensionBits, tagBits))
    val completion = Flipped(Decoupled(new PrimitiveCompletion(tagBits)))
    val result = Decoupled(new OperatorResult(tagBits))
    val busy = Output(Bool())
    val protocolError = Output(Bool())
  })

  private val sIdle :: sIssue :: sWait :: sReport :: Nil = Enum(4)
  private val state = RegInit(sIdle)
  private val pcWidth = log2Ceil(math.max(program.length, 2))
  private val pc = RegInit(0.U(pcWidth.W))
  private val launchReg = Reg(new OperatorLaunch(descriptorBits, dimensionBits, tagBits))
  private val resultStatus = RegInit(0.U(8.W))
  private val protocolErrorReg = RegInit(false.B)

  private def readRom(values: Seq[UInt]): UInt =
    if (values.length == 1) values.head else VecInit(values)(pc)

  private val kindValue = readRom(program.map(x => x.kind.U(PrimitiveKind.Width.W)))
  private val flagsValue = readRom(program.map(x => x.flags.U(PrimitiveFlags.Width.W)))
  private val src0Value = readRom(program.map(x => x.src0.U(4.W)))
  private val src1Value = readRom(program.map(x => x.src1.U(4.W)))
  private val src2Value = readRom(program.map(x => x.src2.U(4.W)))
  private val dstValue = readRom(program.map(x => x.dst.U(4.W)))
  private val mValue = readRom(program.map(x => x.m.U(3.W)))
  private val nValue = readRom(program.map(x => x.n.U(3.W)))
  private val kValue = readRom(program.map(x => x.k.U(3.W)))
  private val index0Value = readRom(program.map(x => x.index0.U(16.W)))
  private val index1Value = readRom(program.map(x => x.index1.U(16.W)))

  io.launch.ready := state === sIdle
  io.microOp.valid := state === sIssue
  io.completion.ready := state === sWait
  io.result.valid := state === sReport
  io.busy := state =/= sIdle
  io.protocolError := protocolErrorReg

  io.microOp.bits.kind := kindValue
  io.microOp.bits.flags := flagsValue
  io.microOp.bits.phase := pc
  io.microOp.bits.tag := launchReg.tag
  io.microOp.bits.mode := launchReg.mode
  io.microOp.bits.src0 := launchReg.descriptors(src0Value)
  io.microOp.bits.src1 := launchReg.descriptors(src1Value)
  io.microOp.bits.src2 := launchReg.descriptors(src2Value)
  io.microOp.bits.dst := launchReg.descriptors(dstValue)
  io.microOp.bits.m := launchReg.dimensions(mValue)
  io.microOp.bits.n := launchReg.dimensions(nValue)
  io.microOp.bits.k := launchReg.dimensions(kValue)
  io.microOp.bits.index0 := index0Value
  io.microOp.bits.index1 := index1Value

  io.result.bits.tag := launchReg.tag
  io.result.bits.status := resultStatus
  io.result.bits.completedPhases := Mux(resultStatus === 0.U, program.length.U, pc + 1.U)

  when(state === sIdle && io.launch.fire) {
    launchReg := io.launch.bits
    pc := 0.U
    resultStatus := 0.U
    protocolErrorReg := false.B
    state := sIssue
  }

  when(state === sIssue && io.microOp.fire) {
    state := sWait
  }

  when(state === sWait && io.completion.fire) {
    val tagMismatch = io.completion.bits.tag =/= launchReg.tag
    val phaseMismatch = io.completion.bits.phase =/= pc
    when(tagMismatch || phaseMismatch) {
      protocolErrorReg := true.B
      resultStatus := Mux(tagMismatch, "he1".U, "he2".U)
      state := sReport
    }.elsewhen(io.completion.bits.status =/= 0.U) {
      resultStatus := io.completion.bits.status
      state := sReport
    }.otherwise {
      when(pc === (program.length - 1).U) {
        resultStatus := 0.U
        state := sReport
      }.otherwise {
        pc := pc + 1.U
        state := sIssue
      }
    }
  }

  when(state === sReport && io.result.fire) {
    state := sIdle
  }
}

final case class LeafCapability(kind: Int, name: String, owner: String, stateful: Boolean = false)

/** Exhaustive execution-owner contract for every leaf kind used by V3. */
object LeafCapabilities {
  import PrimitiveKind._
  val all: Seq[LeafCapability] = Seq(
    LeafCapability(DmaRead, "dma_read", "dma"),
    LeafCapability(DmaWrite, "dma_write", "dma"),
    LeafCapability(MatrixGemm, "matrix_gemm", "matrix"),
    LeafCapability(MatrixGemv, "matrix_gemv", "matrix"),
    LeafCapability(MatrixOuter, "matrix_outer", "matrix_state", stateful = true),
    LeafCapability(MatrixConv, "matrix_conv", "matrix"),
    LeafCapability(MatrixQk, "matrix_qk", "matrix"),
    LeafCapability(MatrixPv, "matrix_pv", "matrix"),
    LeafCapability(VectorAdd, "vector_add", "sfu"),
    LeafCapability(VectorSub, "vector_sub", "sfu"),
    LeafCapability(VectorMul, "vector_mul", "sfu"),
    LeafCapability(VectorFma, "vector_fma", "sfu"),
    LeafCapability(VectorCompare, "vector_compare", "selection"),
    LeafCapability(VectorSelect, "vector_select", "selection"),
    LeafCapability(VectorGather, "vector_gather", "memory"),
    LeafCapability(VectorScatter, "vector_scatter", "memory"),
    LeafCapability(VectorBroadcast, "vector_broadcast", "sfu"),
    LeafCapability(LayoutTransform, "layout_transform", "sfu_cgra"),
    LeafCapability(ApplyMask, "apply_mask", "sfu"),
    LeafCapability(ReduceSum, "reduce_sum", "sfu"),
    LeafCapability(ReduceMax, "reduce_max", "sfu"),
    LeafCapability(StableTopK, "stable_topk", "selection"),
    LeafCapability(StableSort, "stable_sort", "selection"),
    LeafCapability(SparseGatherRun, "sparse_gather_run", "selection_memory"),
    LeafCapability(Argmax, "argmax", "selection"),
    LeafCapability(RmsNorm, "rmsnorm", "sfu"),
    LeafCapability(GroupRmsNorm, "group_rmsnorm", "sfu"),
    LeafCapability(LayerNorm, "layernorm", "sfu"),
    LeafCapability(L2Norm, "l2norm", "sfu"),
    LeafCapability(Rope, "rope", "sfu"),
    LeafCapability(OnlineSoftmax, "online_softmax", "attention_sfu"),
    LeafCapability(Exp2, "exp2", "sfu"),
    LeafCapability(Reciprocal, "reciprocal", "sfu"),
    LeafCapability(Rsqrt, "rsqrt", "sfu"),
    LeafCapability(Softplus, "softplus", "sfu"),
    LeafCapability(Sigmoid, "sigmoid", "sfu"),
    LeafCapability(Silu, "silu", "sfu"),
    LeafCapability(Gelu, "gelu", "sfu"),
    LeafCapability(SignedSqrt, "signed_sqrt", "sfu"),
    LeafCapability(ConfiguredGateAct, "configured_gate_activation", "sfu"),
    LeafCapability(DepthwiseConv, "depthwise_conv", "state_cgra", stateful = true),
    LeafCapability(EmbeddingLookup, "embedding_lookup", "memory"),
    LeafCapability(NgramHash, "ngram_hash", "control_memory"),
    LeafCapability(BilinearPosition, "bilinear_position", "control_sfu"),
    LeafCapability(SpatialMerge, "spatial_merge", "memory_sfu"),
    LeafCapability(MultimodalScatter, "multimodal_scatter", "memory"),
    LeafCapability(KvAppend, "kv_append", "kv", stateful = true),
    LeafCapability(KvGather, "kv_gather", "kv", stateful = true),
    LeafCapability(StateRead, "state_read", "state", stateful = true),
    LeafCapability(StateWrite, "state_write", "state", stateful = true),
    LeafCapability(StateCommit, "state_commit", "state", stateful = true),
    LeafCapability(StateResolve, "state_resolve", "state", stateful = true),
    LeafCapability(MtpCompare, "mtp_compare", "control_state", stateful = true)
  )
  require(all.map(_.kind).distinct.size == all.size, "duplicate leaf kind")
  val supportedKinds: Set[Int] = all.map(_.kind).toSet
}

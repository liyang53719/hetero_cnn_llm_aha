package gemmini

import chisel3._
import chisel3.util._

/** Owner-level split used by the model-independent operator primitive layer. */
object HeteroPrimitiveOwner {
  val width = 4
  val Control   = 0.U(width.W)
  val Dma       = 1.U(width.W)
  val Matrix    = 2.U(width.W)
  val Sfu       = 3.U(width.W)
  val KvMemory  = 4.U(width.W)
  val State     = 5.U(width.W)
  val Selection = 6.U(width.W)
  val Vision    = 7.U(width.W)
}

/** Primitive opcodes. Arithmetic opcodes bind to existing Matrix/SFU RTL;
  * state/selection/vision opcodes bind to Chisel controllers in this package.
  */
object HeteroPrimitiveOpcode {
  val width = 8
  val Nop = "h00".U(width.W); val Barrier = "h01".U(width.W)
  val DmaRead = "h10".U(width.W); val DmaWrite = "h11".U(width.W)
  val DmaGather = "h12".U(width.W); val DmaScatter = "h13".U(width.W)
  val MatrixGemm = "h20".U(width.W); val MatrixGemv = "h21".U(width.W)
  val MatrixQk = "h22".U(width.W); val MatrixPv = "h23".U(width.W)
  val MatrixOuter = "h24".U(width.W); val MatrixConv = "h25".U(width.W)
  val MatrixLowRank = "h26".U(width.W)
  val SfuAdd = "h30".U(width.W); val SfuSub = "h31".U(width.W)
  val SfuMul = "h32".U(width.W); val SfuScale = "h33".U(width.W)
  val SfuReduceSum = "h34".U(width.W); val SfuReduceMax = "h35".U(width.W)
  val SfuRsqrt = "h36".U(width.W); val SfuReciprocal = "h37".U(width.W)
  val SfuExp = "h38".U(width.W); val SfuSigmoid = "h39".U(width.W)
  val SfuSoftplus = "h3a".U(width.W); val SfuSilu = "h3b".U(width.W)
  val SfuGelu = "h3c".U(width.W); val SfuRmsNorm = "h3d".U(width.W)
  val SfuGroupRmsNorm = "h3e".U(width.W); val SfuRope = "h3f".U(width.W)
  val SfuOnlineSoftmax = "h40".U(width.W); val SfuGate = "h41".U(width.W)
  val SfuL2Norm = "h42".U(width.W); val SfuAbs = "h43".U(width.W)
  val SfuMax = "h44".U(width.W); val SfuCompareSelect = "h45".U(width.W)
  val SfuNegate = "h46".U(width.W); val SfuPwl = "h47".U(width.W)
  val SfuExp2 = "h48".U(width.W); val SfuBroadcast = "h49".U(width.W)
  val SfuCausalMask = "h4a".U(width.W); val SfuLayerNorm = "h4b".U(width.W)
  val KvAppend = "h50".U(width.W); val KvGather = "h51".U(width.W)
  val KvAlloc = "h52".U(width.W); val KvFree = "h53".U(width.W)
  val StateRead = "h60".U(width.W); val StateWrite = "h61".U(width.W)
  val StateDecay = "h62".U(width.W); val StateConvWindow = "h63".U(width.W)
  val StateBegin = "h64".U(width.W); val StateCommit = "h65".U(width.W)
  val StateRollback = "h66".U(width.W)
  val SelectTopK = "h70".U(width.W); val SelectExpand = "h71".U(width.W)
  val SelectRoute = "h72".U(width.W); val SelectMerge = "h73".U(width.W)
  val SelectBlockPool = "h74".U(width.W); val SelectMtpVerify = "h75".U(width.W)
  val VisionWindow = "h80".U(width.W); val VisionPatchMerge = "h81".U(width.W)
  val VisionPosInterp = "h82".U(width.W); val PleHash = "h83".U(width.W)
  val VisionPatch3d = "h84".U(width.W); val VisionMropeMap = "h85".U(width.W)
}

/** High-level model operators. Each id has a non-empty decomposition in
  * HeteroModelOperatorSequencer. Shape-only view operations remain explicit so
  * graph coverage never silently relies on CPU fallback.
  */
object HeteroModelOperatorId {
  val width = 8
  val TokenEmbedding = "h01".U(width.W); val RmsNorm = "h02".U(width.W)
  val DenseProjection = "h03".U(width.W); val QkvBias = "h04".U(width.W)
  val PartialRope = "h05".U(width.W); val GqaBroadcast = "h06".U(width.W)
  val DenseAttention = "h07".U(width.W); val AttentionOutputGate = "h08".U(width.W)
  val ResidualAdd = "h09".U(width.W); val SiluTimesUp = "h0a".U(width.W)
  val KvAppend = "h0b".U(width.W); val KvGather = "h0c".U(width.W)
  val LmHead = "h0d".U(width.W); val MultimodalRope = "h0e".U(width.W)
  val LogitsTopK = "h0f".U(width.W); val PaddingMask = "h10".U(width.W)
  val TensorView = "h11".U(width.W)
  val GdnProjection = "h20".U(width.W); val GdnCausalConv = "h21".U(width.W)
  val GdnRecurrentUpdate = "h22".U(width.W); val GdnGatedNormOutput = "h23".U(width.W)
  val MoeRouterTopK = "h30".U(width.W); val MoeDispatch = "h31".U(width.W)
  val MoeRoutedExperts = "h32".U(width.W); val MoeSharedExpert = "h33".U(width.W)
  val MoeRouteReduce = "h34".U(width.W); val MtpStateTransaction = "h35".U(width.W)
  val GatedResidualRead = "h40".U(width.W); val GatedResidualWrite = "h41".U(width.W)
  val GroupRmsNorm = "h42".U(width.W); val PleNgramHash = "h43".U(width.W)
  val PleSparseRowFetch = "h44".U(width.W); val PleProjectionDwConv = "h45".U(width.W)
  val QsaIndexProjection = "h46".U(width.W); val QsaBlockSummary = "h47".U(width.W)
  val QsaStreamingTopK = "h48".U(width.W); val QsaSparseKvGather = "h49".U(width.W)
  val QsaSparseAttention = "h4a".U(width.W)
  val VisionPatchEmbed = "h60".U(width.W); val VisionPosition = "h61".U(width.W)
  val VisionLayerNorm = "h62".U(width.W); val VisionAttention = "h63".U(width.W)
  val VisionMlpGelu = "h64".U(width.W); val VisionPatchMerge = "h65".U(width.W)
  val VisionProject = "h66".U(width.W); val VisionWindowLayout = "h67".U(width.W)
  val VisionDeepstackInject = "h68".U(width.W); val VisionTokenScatter = "h69".U(width.W)
}

class HeteroOperatorCommand extends Bundle {
  val operatorId = UInt(HeteroModelOperatorId.width.W)
  val txnId = UInt(16.W)
  val src0 = UInt(24.W); val src1 = UInt(24.W); val dst = UInt(24.W)
  val rows = UInt(16.W); val columns = UInt(16.W); val depth = UInt(16.W)
  val aux0 = UInt(16.W); val aux1 = UInt(16.W); val flags = UInt(16.W)
}

class HeteroPrimitiveMicroOp extends Bundle {
  val owner = UInt(HeteroPrimitiveOwner.width.W)
  val opcode = UInt(HeteroPrimitiveOpcode.width.W)
  val phase = UInt(8.W); val variant = UInt(8.W); val txnId = UInt(16.W)
  val src0 = UInt(24.W); val src1 = UInt(24.W); val dst = UInt(24.W)
  val rows = UInt(16.W); val columns = UInt(16.W); val depth = UInt(16.W)
  val aux = UInt(32.W); val flags = UInt(16.W)
  val stateful = Bool(); val first = Bool(); val last = Bool()
}

class HeteroScoreIndex(val scoreBits: Int = 32, val indexBits: Int = 32) extends Bundle {
  val score = UInt(scoreBits.W); val index = UInt(indexBits.W)
}
class HeteroRankedScore(val scoreBits: Int = 32, val indexBits: Int = 32, val rankBits: Int = 10) extends Bundle {
  val score = UInt(scoreBits.W); val index = UInt(indexBits.W); val rank = UInt(rankBits.W); val last = Bool()
}

object HeteroFp32Order {
  def key(bits: UInt): UInt = {
    require(bits.getWidth == 32)
    // IEEE-754 compares +0.0 and -0.0 equal. Canonicalize both so the stable
    // tie-break is the ascending item index rather than the sign bit.
    val canonical = Mux(bits(30, 0) === 0.U, 0.U(32.W), bits)
    Mux(canonical(31), ~canonical, canonical ^ "h80000000".U)
  }
  def isNaN(bits: UInt): Bool = { require(bits.getWidth == 32); bits(30,23).andR && bits(22,0).orR }
  /** Descending numeric value, ascending index; NaNs always sort last. */
  def better(as: UInt, ai: UInt, bs: UInt, bi: UInt): Bool = {
    val an = isNaN(as); val bn = isNaN(bs); val ak = key(as); val bk = key(bs)
    (!an && bn) || ((!an && !bn) && ((ak > bk) || ((ak === bk) && ai < bi))) || (an && bn && ai < bi)
  }
}

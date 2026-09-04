package gemmini

import chisel3._
import chisel3.util._

/**
  * Canonical tensor-level operator primitives for Qwen2-1.5B,
  * Qwen3.5-35B-A3B and Qwen3.8-Flash-Next.
  *
  * These modules are synthesizable microprogram sequencers.  Arithmetic leaf
  * operations are dispatched through HeteroTensorMicroOp to the existing
  * Matrix, fixed-SFU, KV/state and DMA engines.  Tensor shapes, addresses,
  * scales and constants remain descriptor-owned; no model dimension is baked
  * into the instruction stream.
  */
abstract class HeteroCompositeOperatorPrimitiveV2(
    val operatorProgramV2: Seq[HeteroMicroInstruction],
    val operatorNameV2: String,
    val descriptorBits: Int = 24,
    val dimensionBits: Int = 16,
    val tagBits: Int = 16
) extends Module {
  require(operatorProgramV2.nonEmpty)
  override def desiredName: String = operatorNameV2

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
    program = operatorProgramV2,
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
/** Distinct leaf names avoid parameter-collision when all emitted RTL is linked. */
class HeteroMoeStableTopKV2 extends HeteroStableTopK(maxK = 16, indexBits = 9) {
  override def desiredName: String = "HeteroMoeStableTopKV2"
}
class HeteroQsaStableTopKV2 extends HeteroStableTopK(maxK = 512, indexBits = 20) {
  override def desiredName: String = "HeteroQsaStableTopKV2"
}
class HeteroQsaStableIndexSorterV2 extends HeteroStableIndexSorter(maxItems = 512, indexBits = 20) {
  override def desiredName: String = "HeteroQsaStableIndexSorterV2"
}
class HeteroLanguageArgmaxV2 extends HeteroStableArgmax(indexBits = 20) {
  override def desiredName: String = "HeteroLanguageArgmaxV2"
}

object HeteroQwen2DecoderBlockProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._

  // Dims: token, hidden, q-heads, kv-heads, head-dim, intermediate, context, reserved.
  // Descriptor 14 carries masks/scales/constants; descriptor 15 is the state journal.
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(RmsNorm,      0x00, src0=0,  src1=1,  dst=8,  m=0, n=1),
    HeteroMicroInstruction(MatrixGemm,   0x01, src0=8,  src1=2,  dst=6,  m=0, n=2, k=1, index0=0),
    HeteroMicroInstruction(VectorAdd,    0x02, flag(HeteroPrimitiveFlags.ApplyBias), src0=6, src1=3, dst=6, m=0, n=2, index0=0),
    HeteroMicroInstruction(Rope,         0x03, src0=6,  src1=4,  dst=6,  m=0, n=2, k=4, index0=0),
    HeteroMicroInstruction(MatrixGemm,   0x04, src0=8,  src1=2,  dst=6,  m=0, n=3, k=1, index0=1),
    HeteroMicroInstruction(VectorAdd,    0x05, flag(HeteroPrimitiveFlags.ApplyBias), src0=6, src1=3, dst=6, m=0, n=3, index0=1),
    HeteroMicroInstruction(Rope,         0x06, src0=6,  src1=4,  dst=6,  m=0, n=3, k=4, index0=1),
    HeteroMicroInstruction(MatrixGemm,   0x07, src0=8,  src1=2,  dst=6,  m=0, n=3, k=1, index0=2),
    HeteroMicroInstruction(VectorAdd,    0x08, flag(HeteroPrimitiveFlags.ApplyBias), src0=6, src1=3, dst=6, m=0, n=3, index0=2),
    HeteroMicroInstruction(KvAppend,     0x09, flag(HeteroPrimitiveFlags.Stateful), src0=6, dst=5, m=0, n=3, k=4),
    HeteroMicroInstruction(MatrixQk,     0x0a, flag(HeteroPrimitiveFlags.Causal), src0=6, src1=5, dst=6, m=2, n=6, k=4),
    HeteroMicroInstruction(VectorMul,    0x0b, src0=6,  src1=14, dst=6,  m=2, n=6, index0=0),
    HeteroMicroInstruction(OnlineSoftmax,0x0c, flag(HeteroPrimitiveFlags.Causal), src0=6, src1=14, dst=6, m=2, n=6),
    HeteroMicroInstruction(MatrixPv,     0x0d, src0=6,  src1=5,  dst=6,  m=2, n=4, k=6),
    HeteroMicroInstruction(MatrixGemm,   0x0e, src0=6,  src1=7,  dst=8,  m=0, n=1, k=1, index0=0),
    HeteroMicroInstruction(VectorAdd,    0x0f, src0=0,  src1=8,  dst=8,  m=0, n=1),
    HeteroMicroInstruction(RmsNorm,      0x10, src0=8,  src1=9,  dst=11, m=0, n=1),
    HeteroMicroInstruction(MatrixGemm,   0x11, src0=11, src1=10, dst=11, m=0, n=5, k=1, index0=0),
    HeteroMicroInstruction(MatrixGemm,   0x12, src0=11, src1=10, dst=6,  m=0, n=5, k=1, index0=1),
    HeteroMicroInstruction(Silu,         0x13, src0=11, dst=11, m=0, n=5),
    HeteroMicroInstruction(VectorMul,    0x14, src0=11, src1=6,  dst=11, m=0, n=5),
    HeteroMicroInstruction(MatrixGemm,   0x15, src0=11, src1=12, dst=11, m=0, n=1, k=5),
    HeteroMicroInstruction(VectorAdd,    0x16, flag(HeteroPrimitiveFlags.Last), src0=8, src1=11, dst=13, m=0, n=1),
    HeteroMicroInstruction(StateCommit,  0x17, flag(HeteroPrimitiveFlags.Stateful,HeteroPrimitiveFlags.Commit,HeteroPrimitiveFlags.Last), src0=15, dst=15)
  )
}
class HeteroQwen2DecoderBlockOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroQwen2DecoderBlockProgramV2.program,
  "HeteroQwen2DecoderBlockOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)

object HeteroQwen35DenseAttentionProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._

  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(MatrixGemm,   0x00, src0=0, src1=1, dst=6, m=0, n=2, k=1, index0=0),
    HeteroMicroInstruction(MatrixGemm,   0x01, src0=0, src1=1, dst=6, m=0, n=3, k=1, index0=1),
    HeteroMicroInstruction(MatrixGemm,   0x02, src0=0, src1=1, dst=6, m=0, n=3, k=1, index0=2),
    HeteroMicroInstruction(MatrixGemm,   0x03, src0=0, src1=2, dst=7, m=0, n=2, k=1),
    HeteroMicroInstruction(RmsNorm,      0x04, src0=6, src1=3, dst=6, m=0, n=2, k=4, index0=0),
    HeteroMicroInstruction(RmsNorm,      0x05, src0=6, src1=3, dst=6, m=0, n=3, k=4, index0=1),
    HeteroMicroInstruction(Rope,         0x06, flag(HeteroPrimitiveFlags.PartialRotary,HeteroPrimitiveFlags.MropeInterleaved), src0=6, src1=4, dst=6, m=0, n=2, k=4),
    HeteroMicroInstruction(KvAppend,     0x07, flag(HeteroPrimitiveFlags.Stateful), src0=6, dst=5, m=0, n=3, k=4),
    HeteroMicroInstruction(MatrixQk,     0x08, flag(HeteroPrimitiveFlags.Causal), src0=6, src1=5, dst=8, m=2, n=6, k=4),
    HeteroMicroInstruction(VectorMul,    0x09, src0=8, src1=14, dst=8, m=2, n=6, index0=0),
    HeteroMicroInstruction(OnlineSoftmax,0x0a, flag(HeteroPrimitiveFlags.Causal), src0=8, dst=8, m=2, n=6),
    HeteroMicroInstruction(MatrixPv,     0x0b, src0=8, src1=5, dst=8, m=2, n=4, k=6),
    HeteroMicroInstruction(Sigmoid,      0x0c, src0=7, dst=7, m=0, n=2, k=4),
    HeteroMicroInstruction(VectorMul,    0x0d, src0=8, src1=7, dst=8, m=0, n=2, k=4),
    HeteroMicroInstruction(MatrixGemm,   0x0e, flag(HeteroPrimitiveFlags.Last), src0=8, src1=9, dst=10, m=0, n=1, k=2)
  )
}
class HeteroQwen35DenseAttentionOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroQwen35DenseAttentionProgramV2.program,
  "HeteroQwen35DenseAttentionOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)

package gemmini

import chisel3._
import chisel3.util._

object HeteroVisionPatchProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(MatrixConv,       0x00, flag(HeteroPrimitiveFlags.ApplyBias), src0=0, src1=1, dst=2, m=0, n=1, k=2, index0=3),
    HeteroMicroInstruction(BilinearPosition, 0x01, src0=3, src1=4, dst=5, m=0, n=1),
    HeteroMicroInstruction(VectorAdd,        0x02, flag(HeteroPrimitiveFlags.Last), src0=2, src1=5, dst=6, m=0, n=1)
  )
}
class HeteroVisionPatchEmbedOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroVisionPatchProgramV2.program,
  "HeteroVisionPatchEmbedOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)

object HeteroVisionBlockProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(LayerNorm,      0x00, src0=0, src1=1, dst=2, m=0, n=1),
    HeteroMicroInstruction(MatrixGemm,     0x01, flag(HeteroPrimitiveFlags.ApplyBias), src0=2, src1=3, dst=4, m=0, n=2, k=1),
    HeteroMicroInstruction(Rope,           0x02, flag(HeteroPrimitiveFlags.NonCausal), src0=4, src1=5, dst=4, m=0, n=2, k=3),
    HeteroMicroInstruction(MatrixQk,       0x03, flag(HeteroPrimitiveFlags.NonCausal), src0=4, src1=4, dst=6, m=2, n=2, k=3),
    HeteroMicroInstruction(VectorMul,      0x04, src0=6, src1=14, dst=6, m=2, n=2, index0=0),
    HeteroMicroInstruction(OnlineSoftmax,  0x05, flag(HeteroPrimitiveFlags.NonCausal), src0=6, dst=6, m=2, n=2),
    HeteroMicroInstruction(MatrixPv,       0x06, flag(HeteroPrimitiveFlags.NonCausal), src0=6, src1=4, dst=7, m=2, n=1, k=2),
    HeteroMicroInstruction(MatrixGemm,     0x07, src0=7, src1=8, dst=7, m=0, n=1, k=1),
    HeteroMicroInstruction(VectorAdd,      0x08, src0=0, src1=7, dst=9, m=0, n=1),
    HeteroMicroInstruction(LayerNorm,      0x09, src0=9, src1=10, dst=2, m=0, n=1),
    HeteroMicroInstruction(MatrixGemm,     0x0a, flag(HeteroPrimitiveFlags.ApplyBias), src0=2, src1=11, dst=4, m=0, n=4, k=1),
    HeteroMicroInstruction(GeluTanh,       0x0b, src0=4, dst=4, m=0, n=4),
    HeteroMicroInstruction(MatrixGemm,     0x0c, flag(HeteroPrimitiveFlags.ApplyBias), src0=4, src1=12, dst=7, m=0, n=1, k=4),
    HeteroMicroInstruction(VectorAdd,      0x0d, flag(HeteroPrimitiveFlags.Last), src0=9, src1=7, dst=13, m=0, n=1)
  )
}
class HeteroVisionTransformerBlockOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroVisionBlockProgramV2.program,
  "HeteroVisionTransformerBlockOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)

object HeteroVisionMergeProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(LayerNorm,   0x00, src0=0, src1=1, dst=2, m=0, n=1),
    HeteroMicroInstruction(SpatialMerge,0x01, src0=2, dst=3, m=0, n=1, index0=2),
    HeteroMicroInstruction(MatrixGemm,  0x02, flag(HeteroPrimitiveFlags.ApplyBias), src0=3, src1=4, dst=5, m=0, n=2, k=1),
    HeteroMicroInstruction(GeluTanh,    0x03, src0=5, dst=5, m=0, n=2),
    HeteroMicroInstruction(MatrixGemm,  0x04, flag(HeteroPrimitiveFlags.ApplyBias,HeteroPrimitiveFlags.Last), src0=5, src1=6, dst=7, m=0, n=3, k=2)
  )
}
class HeteroVisionPatchMergeOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroVisionMergeProgramV2.program,
  "HeteroVisionPatchMergeOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)

object HeteroLanguageModelBoundaryProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(EmbeddingLookup,0x00, src0=0, src1=1, dst=2, m=0, n=1),
    HeteroMicroInstruction(RmsNorm,       0x01, src0=3, src1=4, dst=5, m=0, n=1),
    HeteroMicroInstruction(MatrixGemv,    0x02, src0=5, src1=6, dst=7, m=0, n=2, k=1),
    HeteroMicroInstruction(Argmax,        0x03, flag(HeteroPrimitiveFlags.Last), src0=7, dst=8, n=2)
  )
}
class HeteroLanguageModelBoundaryOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroLanguageModelBoundaryProgramV2.program,
  "HeteroLanguageModelBoundaryOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)

object HeteroMtpDraftTargetProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(StateRead,     0x00, flag(HeteroPrimitiveFlags.Stateful), src0=0, dst=1),
    HeteroMicroInstruction(SubgraphLaunch,0x01, flag(HeteroPrimitiveFlags.Stateful), src0=2, src1=1, dst=3, m=0),
    HeteroMicroInstruction(MatrixGemv,    0x02, src0=3, src1=4, dst=5, m=0, n=1, k=2),
    HeteroMicroInstruction(Argmax,        0x03, src0=5, dst=6, m=0, n=1),
    HeteroMicroInstruction(SubgraphLaunch,0x04, flag(HeteroPrimitiveFlags.Stateful), src0=7, src1=1, dst=8, m=0),
    HeteroMicroInstruction(MatrixGemv,    0x05, src0=8, src1=9, dst=10, m=0, n=1, k=2),
    HeteroMicroInstruction(Argmax,        0x06, flag(HeteroPrimitiveFlags.Last), src0=10, dst=11, m=0, n=1)
  )
}
class HeteroMtpDraftTargetOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroMtpDraftTargetProgramV2.program,
  "HeteroMtpDraftTargetOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)


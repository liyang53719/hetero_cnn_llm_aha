package gemmini

import chisel3._
import chisel3.util._

object HeteroMoeProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._

  /** Top-K is followed by selected-logit softmax before dispatch. */
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(MatrixGemm,    0x00, src0=0, src1=1, dst=2, m=0, n=2, k=1),
    HeteroMicroInstruction(StableTopK,    0x01, src0=2, dst=3, m=0, n=2, k=3),
    HeteroMicroInstruction(OnlineSoftmax, 0x02, src0=3, dst=3, m=0, n=3),
    HeteroMicroInstruction(VectorScatter, 0x03, src0=0, src1=3, dst=4, m=0, n=3, k=1),
    HeteroMicroInstruction(StateRead,     0x04, flag(HeteroPrimitiveFlags.Stateful), src0=14, dst=14, n=2),
    HeteroMicroInstruction(DmaRead,       0x05, flag(HeteroPrimitiveFlags.RoutedExpert), src0=5, src1=4, src2=14, dst=6, m=6, n=4, k=1),
    HeteroMicroInstruction(MatrixGemm,    0x06, flag(HeteroPrimitiveFlags.RoutedExpert), src0=6, src1=5, dst=7, m=6, n=4, k=1, index0=0),
    HeteroMicroInstruction(MatrixGemm,    0x07, flag(HeteroPrimitiveFlags.RoutedExpert), src0=6, src1=5, dst=7, m=6, n=4, k=1, index0=1),
    HeteroMicroInstruction(Silu,          0x08, flag(HeteroPrimitiveFlags.RoutedExpert), src0=7, dst=7, m=6, n=4, index0=0),
    HeteroMicroInstruction(VectorMul,     0x09, flag(HeteroPrimitiveFlags.RoutedExpert), src0=7, src1=7, dst=7, m=6, n=4),
    HeteroMicroInstruction(MatrixGemm,    0x0a, flag(HeteroPrimitiveFlags.RoutedExpert), src0=7, src1=5, dst=8, m=6, n=1, k=4, index0=2),
    HeteroMicroInstruction(VectorFma,     0x0b, flag(HeteroPrimitiveFlags.RoutedExpert), src0=8, src1=3, src2=9, dst=9, m=0, n=1, k=3),
    HeteroMicroInstruction(DmaRead,       0x0c, flag(HeteroPrimitiveFlags.SharedExpert), src0=10, src2=14, dst=12, m=0, n=4, k=1),
    HeteroMicroInstruction(MatrixGemm,    0x0d, flag(HeteroPrimitiveFlags.SharedExpert), src0=0, src1=10, dst=12, m=0, n=4, k=1, index0=0),
    HeteroMicroInstruction(MatrixGemm,    0x0e, flag(HeteroPrimitiveFlags.SharedExpert), src0=0, src1=10, dst=12, m=0, n=4, k=1, index0=1),
    HeteroMicroInstruction(Silu,          0x0f, flag(HeteroPrimitiveFlags.SharedExpert), src0=12, dst=12, m=0, n=4),
    HeteroMicroInstruction(VectorMul,     0x10, flag(HeteroPrimitiveFlags.SharedExpert), src0=12, src1=12, dst=12, m=0, n=4),
    HeteroMicroInstruction(MatrixGemm,    0x11, flag(HeteroPrimitiveFlags.SharedExpert), src0=12, src1=10, dst=12, m=0, n=1, k=4, index0=2),
    HeteroMicroInstruction(MatrixGemv,    0x12, flag(HeteroPrimitiveFlags.SharedExpert), src0=0, src1=11, dst=8, m=0, n=1, k=1),
    HeteroMicroInstruction(Sigmoid,       0x13, flag(HeteroPrimitiveFlags.SharedExpert), src0=8, dst=8, m=0),
    HeteroMicroInstruction(VectorMul,     0x14, flag(HeteroPrimitiveFlags.SharedExpert), src0=12, src1=8, dst=12, m=0, n=1),
    HeteroMicroInstruction(VectorAdd,     0x15, src0=9, src1=12, dst=13, m=0, n=1),
    HeteroMicroInstruction(StateWrite,    0x16, flag(HeteroPrimitiveFlags.Stateful), src0=14, dst=14, n=2),
    HeteroMicroInstruction(StateCommit,   0x17, flag(HeteroPrimitiveFlags.Stateful,HeteroPrimitiveFlags.Commit,HeteroPrimitiveFlags.Last), src0=15, dst=15)
  )
}
class HeteroMoeOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroMoeProgramV2.program,
  "HeteroMoeOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)

object HeteroGatedResidualProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._

  /**
    * read = mean_b(group_rmsnorm(x_b) * sigmoid(read_gate_b));
    * inject_b = x_b + block * (2 * sigmoid(inject_gate_b / branches)).
    */
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(GroupRmsNorm,0x00, src0=0, dst=4, m=0, n=1, k=2),
    HeteroMicroInstruction(MatrixGemm,  0x01, src0=4, src1=1, dst=5, m=0, n=3, k=4),
    HeteroMicroInstruction(Sigmoid,     0x02, src0=5, dst=5, m=0, n=3),
    HeteroMicroInstruction(VectorMul,   0x03, src0=4, src1=5, dst=7, m=0, n=1, k=2),
    HeteroMicroInstruction(ReduceSum,   0x04, src0=7, dst=7, m=0, n=1, k=2),
    HeteroMicroInstruction(Reciprocal,  0x05, src0=14, dst=11, k=2, index0=0),
    HeteroMicroInstruction(VectorMul,   0x06, src0=7, src1=11, dst=7, m=0, n=1),
    HeteroMicroInstruction(MatrixGemm,  0x07, src0=4, src1=3, dst=9, m=0, n=2, k=4),
    HeteroMicroInstruction(VectorMul,   0x08, src0=9, src1=11, dst=9, m=0, n=2),
    HeteroMicroInstruction(Sigmoid,     0x09, src0=9, dst=9, m=0, n=2),
    HeteroMicroInstruction(VectorMul,   0x0a, src0=9, src1=14, dst=9, m=0, n=2, index0=1),
    HeteroMicroInstruction(VectorMul,   0x0b, src0=8, src1=9, dst=10, m=0, n=1, k=2),
    HeteroMicroInstruction(VectorAdd,   0x0c, flag(HeteroPrimitiveFlags.Stateful), src0=0, src1=10, dst=10, m=0, n=1, k=2),
    HeteroMicroInstruction(StateWrite,  0x0d, flag(HeteroPrimitiveFlags.Stateful), src0=10, dst=6, m=0, n=1, k=2),
    HeteroMicroInstruction(StateCommit, 0x0e, flag(HeteroPrimitiveFlags.Stateful,HeteroPrimitiveFlags.Commit,HeteroPrimitiveFlags.Last), src0=15, dst=15)
  )
}
class HeteroGatedResidualOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroGatedResidualProgramV2.program,
  "HeteroGatedResidualOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)

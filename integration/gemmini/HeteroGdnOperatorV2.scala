package gemmini

import chisel3._
import chisel3.util._

object HeteroGdnProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._

  /**
    * Exact algebraic stages represented explicitly:
    * q/k L2 normalization; q/sqrt(d); beta=sigmoid(b);
    * decay=exp(-exp(a_log)*softplus(a+dt_bias));
    * S=decay*S; delta=beta*(v-S^T*k); S+=k*delta^T; y=S^T*q;
    * gated RMSNorm and output projection.
    * Constants in descriptor 8 include log2(e), -log2(e), 1/sqrt(d), epsilon.
    */
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(MatrixGemm, 0x00, src0=0, src1=1, dst=11, m=0, n=2, k=1),
    HeteroMicroInstruction(MatrixGemm, 0x01, src0=0, src1=2, dst=12, m=0, n=3, k=1, index0=0),
    HeteroMicroInstruction(MatrixGemm, 0x02, src0=0, src1=3, dst=12, m=0, n=3, k=1, index0=1),
    HeteroMicroInstruction(MatrixGemm, 0x03, src0=0, src1=4, dst=12, m=0, n=3, k=1, index0=2),
    HeteroMicroInstruction(StateRead,  0x04, flag(HeteroPrimitiveFlags.Stateful), src0=6, dst=13, m=6),
    HeteroMicroInstruction(DepthwiseConv,0x05, flag(HeteroPrimitiveFlags.Causal,HeteroPrimitiveFlags.ApplyActivation,HeteroPrimitiveFlags.Stateful), src0=11, src1=5, src2=13, dst=11, m=0, n=2, k=6),
    HeteroMicroInstruction(StateWrite, 0x06, flag(HeteroPrimitiveFlags.Stateful), src0=13, dst=6, m=6),
    HeteroMicroInstruction(L2Norm,     0x07, src0=11, dst=11, m=0, n=2, k=4, index0=0),
    HeteroMicroInstruction(L2Norm,     0x08, src0=11, dst=11, m=0, n=2, k=4, index0=1),
    HeteroMicroInstruction(Rsqrt,      0x09, src0=8,  dst=13, k=4, index0=0),
    HeteroMicroInstruction(VectorMul,  0x0a, src0=11, src1=13, dst=11, m=0, n=2, k=4, index0=0),
    HeteroMicroInstruction(VectorAdd,  0x0b, src0=12, src1=8, dst=12, m=0, n=3, index0=1),
    HeteroMicroInstruction(Softplus,   0x0c, src0=12, dst=12, m=0, n=3, index0=1),
    HeteroMicroInstruction(VectorMul,  0x0d, src0=8,  src1=8,  dst=13, n=3, index0=1),
    HeteroMicroInstruction(Exp2,       0x0e, src0=13, dst=13, n=3, index0=0),
    HeteroMicroInstruction(VectorMul,  0x0f, src0=13, src1=12, dst=13, n=3, index0=1),
    HeteroMicroInstruction(VectorMul,  0x10, src0=13, src1=8,  dst=13, n=3, index0=2),
    HeteroMicroInstruction(Exp2,       0x11, src0=13, dst=13, n=3, index0=1),
    HeteroMicroInstruction(Sigmoid,    0x12, src0=12, dst=12, m=0, n=3, index0=2),
    HeteroMicroInstruction(StateRead,  0x13, flag(HeteroPrimitiveFlags.Stateful), src0=7, dst=13, m=3, n=4, k=5),
    HeteroMicroInstruction(VectorMul,  0x14, flag(HeteroPrimitiveFlags.Stateful), src0=13, src1=13, dst=13, m=3, n=4, k=5, index0=3),
    HeteroMicroInstruction(MatrixGemv, 0x15, src0=13, src1=11, dst=11, m=3, n=5, k=4, index0=0),
    HeteroMicroInstruction(VectorSub,  0x16, src0=11, src1=11, dst=11, m=0, n=3, k=5, index0=2, index1=3),
    HeteroMicroInstruction(VectorMul,  0x17, src0=11, src1=12, dst=11, m=0, n=3, k=5, index0=2),
    HeteroMicroInstruction(MatrixOuter,0x18, flag(HeteroPrimitiveFlags.Stateful), src0=11, src1=11, src2=13, dst=13, m=3, n=4, k=5, index0=1, index1=2),
    HeteroMicroInstruction(MatrixGemv, 0x19, src0=13, src1=11, dst=11, m=3, n=5, k=4, index0=1),
    HeteroMicroInstruction(RmsNorm,    0x1a, src0=11, src1=9, dst=11, m=0, n=3, k=5),
    HeteroMicroInstruction(Silu,       0x1b, src0=12, dst=12, m=0, n=3, k=5, index0=0),
    HeteroMicroInstruction(VectorMul,  0x1c, src0=11, src1=12, dst=11, m=0, n=3, k=5),
    HeteroMicroInstruction(MatrixGemm, 0x1d, src0=11, src1=10, dst=14, m=0, n=1, k=3),
    HeteroMicroInstruction(StateWrite, 0x1e, flag(HeteroPrimitiveFlags.Stateful), src0=13, dst=7, m=3, n=4, k=5),
    HeteroMicroInstruction(StateCommit,0x1f, flag(HeteroPrimitiveFlags.Stateful,HeteroPrimitiveFlags.Commit,HeteroPrimitiveFlags.Last), src0=15, dst=15)
  )
}
class HeteroGdnOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroGdnProgramV2.program,
  "HeteroGdnOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)


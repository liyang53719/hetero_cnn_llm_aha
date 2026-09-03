package gemmini

import chisel3._
import chisel3.util._

object HeteroPleProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._

  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(StateRead,      0x00, flag(HeteroPrimitiveFlags.Stateful), src0=1, dst=13, m=3),
    HeteroMicroInstruction(NgramHash,      0x01, src0=13, src1=2, dst=3, m=0, n=3, k=4),
    HeteroMicroInstruction(DmaRead,        0x02, flag(HeteroPrimitiveFlags.Sparse), src0=4, src1=3, src2=14, dst=5, m=0, n=4, k=5),
    HeteroMicroInstruction(EmbeddingLookup,0x03,flag(HeteroPrimitiveFlags.Sparse), src0=5, src1=3, dst=5, m=0, n=4, k=5),
    HeteroMicroInstruction(MatrixGemm,     0x04, src0=5, src1=6, dst=8, m=0, n=1, k=5),
    HeteroMicroInstruction(MatrixGemm,     0x05, src0=5, src1=7, dst=9, m=0, n=2, k=5),
    HeteroMicroInstruction(GroupRmsNorm,   0x06, src0=8, dst=8, m=0, n=1, k=2),
    HeteroMicroInstruction(GroupRmsNorm,   0x07, src0=0, dst=13, m=0, n=1, k=2),
    HeteroMicroInstruction(MatrixQk,       0x08, src0=13, src1=8, dst=13, m=0, n=1, k=2),
    HeteroMicroInstruction(SignedSqrt,     0x09, src0=13, dst=13, m=0, n=1),
    HeteroMicroInstruction(Sigmoid,        0x0a, src0=13, dst=13, m=0, n=1),
    HeteroMicroInstruction(VectorMul,      0x0b, src0=9, src1=13, dst=9, m=0, n=1, k=2),
    HeteroMicroInstruction(GroupRmsNorm,   0x0c, src0=9, dst=13, m=0, n=1, k=2),
    HeteroMicroInstruction(StateRead,      0x0d, flag(HeteroPrimitiveFlags.Stateful), src0=11, dst=13, n=1, k=6),
    HeteroMicroInstruction(DepthwiseConv,  0x0e, flag(HeteroPrimitiveFlags.Stateful,HeteroPrimitiveFlags.ApplyActivation), src0=13, src1=10, src2=13, dst=13, m=0, n=1, k=6, index0=3),
    HeteroMicroInstruction(StateWrite,     0x0f, flag(HeteroPrimitiveFlags.Stateful), src0=13, dst=11, n=1, k=6),
    HeteroMicroInstruction(VectorAdd,      0x10, src0=9, src1=13, dst=12, m=0, n=1, k=2),
    HeteroMicroInstruction(StateWrite,     0x11, flag(HeteroPrimitiveFlags.Stateful), src0=13, dst=1, m=3),
    HeteroMicroInstruction(StateCommit,    0x12, flag(HeteroPrimitiveFlags.Stateful,HeteroPrimitiveFlags.Commit,HeteroPrimitiveFlags.Last), src0=15, dst=15)
  )
}
class HeteroPleOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroPleProgramV2.program,
  "HeteroPleOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)

object HeteroQsaProgramV2 {
  import HeteroMicroInstruction.flag
  import HeteroPrimitiveCode._

  /**
    * QSA selection is explicit: average compressed-key blocks, L2 normalize,
    * dot normalized index queries, clamp scores at zero, reduce index heads,
    * scale by 1/sqrt(index_dim), stable Top-512, sort/coalesce selected tokens,
    * gather sparse KV, then execute sparse QK/online-softmax/PV.
    */
  val program: Seq[HeteroMicroInstruction] = Seq(
    HeteroMicroInstruction(MatrixGemm,    0x00, src0=0, src1=1, dst=9, m=0, n=2, k=1),
    HeteroMicroInstruction(L2Norm,        0x01, src0=9, dst=9, m=0, n=2, k=3),
    HeteroMicroInstruction(Rope,          0x02, flag(HeteroPrimitiveFlags.PartialRotary,HeteroPrimitiveFlags.MropeInterleaved), src0=9, dst=9, m=0, n=2, k=3),
    HeteroMicroInstruction(StateWrite,    0x03, flag(HeteroPrimitiveFlags.Stateful), src0=9, dst=2, m=0, n=3),
    HeteroMicroInstruction(ReduceSum,     0x04, src0=2, dst=3, m=0, n=3, index0=4),
    HeteroMicroInstruction(Reciprocal,    0x05, src0=14, dst=9, index0=4),
    HeteroMicroInstruction(VectorMul,     0x06, src0=3, src1=9, dst=3, m=0, n=3, index1=7),
    HeteroMicroInstruction(L2Norm,        0x07, src0=3, dst=3, m=0, n=3),
    HeteroMicroInstruction(MatrixQk,      0x08, src0=9, src1=3, dst=3, m=2, n=0, k=3),
    HeteroMicroInstruction(VectorCompare, 0x09, src0=3, src1=14, dst=9, index0=5),
    HeteroMicroInstruction(VectorSelect,  0x0a, src0=9, src1=3, src2=14, dst=3, index0=5),
    HeteroMicroInstruction(ReduceSum,     0x0b, src0=3, dst=3, m=0, n=0, k=2),
    HeteroMicroInstruction(Rsqrt,         0x0c, src0=14, dst=9, k=3, index0=6),
    HeteroMicroInstruction(VectorMul,     0x0d, src0=3, src1=9, dst=3, n=0, index1=6),
    HeteroMicroInstruction(StableTopK,    0x0e, src0=3, dst=4, m=0, n=7, index0=5),
    HeteroMicroInstruction(VectorGather,  0x0f, flag(HeteroPrimitiveFlags.Sparse), src0=2, src1=4, dst=4, m=0, n=7, index0=4),
    HeteroMicroInstruction(StableSort,    0x10, src0=4, dst=4, m=0, n=7),
    HeteroMicroInstruction(SparseGatherRun,0x11,flag(HeteroPrimitiveFlags.Sparse), src0=4, dst=5, m=0, n=7, index0=4),
    HeteroMicroInstruction(KvGather,      0x12, flag(HeteroPrimitiveFlags.Sparse), src0=10, src1=5, dst=11, m=0, n=5, k=6),
    HeteroMicroInstruction(MatrixGemm,    0x13, src0=0, src1=6, dst=9, m=0, n=4, k=1, index0=0),
    HeteroMicroInstruction(MatrixGemm,    0x14, src0=0, src1=7, dst=9, m=0, n=5, k=1, index0=1),
    HeteroMicroInstruction(MatrixGemm,    0x15, src0=0, src1=8, dst=9, m=0, n=5, k=1, index0=2),
    HeteroMicroInstruction(RmsNorm,       0x16, src0=9, dst=9, m=0, n=4, k=6, index0=0),
    HeteroMicroInstruction(RmsNorm,       0x17, src0=9, dst=9, m=0, n=5, k=6, index0=1),
    HeteroMicroInstruction(Rope,          0x18, flag(HeteroPrimitiveFlags.PartialRotary,HeteroPrimitiveFlags.MropeInterleaved), src0=9, dst=9, m=0, n=4, k=6),
    HeteroMicroInstruction(KvAppend,      0x19, flag(HeteroPrimitiveFlags.Stateful), src0=9, dst=10, m=0, n=5, k=6),
    HeteroMicroInstruction(MatrixQk,      0x1a, flag(HeteroPrimitiveFlags.Sparse), src0=9, src1=11, dst=12, m=4, n=7, k=6),
    HeteroMicroInstruction(VectorMul,     0x1b, src0=12, src1=14, dst=12, m=4, n=7, index0=2),
    HeteroMicroInstruction(OnlineSoftmax, 0x1c, flag(HeteroPrimitiveFlags.Causal,HeteroPrimitiveFlags.Sparse), src0=12, src1=11, dst=12, m=4, n=7, k=6),
    HeteroMicroInstruction(MatrixPv,      0x1d, flag(HeteroPrimitiveFlags.Sparse), src0=12, src1=11, dst=12, m=4, n=6, k=7),
    HeteroMicroInstruction(MatrixGemm,    0x1e, src0=0, src1=13, dst=9, m=0, n=4, k=1, index0=3),
    HeteroMicroInstruction(Sigmoid,       0x1f, src0=9, dst=9, m=0, n=4, k=6),
    HeteroMicroInstruction(VectorMul,     0x20, src0=12, src1=9, dst=12, m=0, n=4, k=6),
    HeteroMicroInstruction(MatrixGemm,    0x21, src0=12, src1=13, dst=12, m=0, n=1, k=4, index0=4),
    HeteroMicroInstruction(StateCommit,   0x22, flag(HeteroPrimitiveFlags.Stateful,HeteroPrimitiveFlags.Commit,HeteroPrimitiveFlags.Last), src0=15, dst=15)
  )
}
class HeteroQsaOperatorPrimitiveV2(
    descriptorBits:Int=24, dimensionBits:Int=16, tagBits:Int=16
) extends HeteroCompositeOperatorPrimitiveV2(
  HeteroQsaProgramV2.program,
  "HeteroQsaOperatorPrimitiveV2",
  descriptorBits, dimensionBits, tagBits
)


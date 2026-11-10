// Exact original interface-class excerpt; no owner/arithmetic substitution.
package heteronpu.continuous
import chisel3._
class QwenOwnerJob extends Bundle {
  // Explicit internal ABI extension. Values 0..7 retain their old meanings;
  // GDN is never truncated or aliased to a legacy owner kind.
  val kind=UInt(4.W); val m=UInt(16.W); val n=UInt(16.W); val k=UInt(16.W)
  val a=UInt(64.W); val b=UInt(64.W); val c=UInt(64.W); val dst=UInt(64.W)
  val weightBf16=Bool() // Dense B storage, or explicit BF16 B in typed Attention jobs.
  val activationBf16=Bool() // Typed A storage; false preserves legacy Dense FP32 ingress.
  val materializeDenseOutput=Bool() // Numerical BF16 value in FP32 storage, bound by validated public role.
  val outputBf16=Bool() // Explicit terminal RNE BF16 D storage; false preserves FP32 stores.
  val writeBytes=UInt(64.W); val tag=UInt(32.W)
  val historyOut=UInt(64.W);val expectedGeneration=UInt(32.W);val currentGeneration=UInt(32.W);val cold=Bool()
  // Explicit BF16 Attention context extension; legacy jobs leave these zero.
  val cacheCapacity=UInt(32.W);val cacheLength=UInt(32.W)
  val expectedCacheLength=UInt(32.W);val queryStart=UInt(32.W)
  val qkNormPolicy=UInt(8.W) // per-kind explicit runtime C1/C2 QKNorm or B1 PartialRoPE; never a capability
  // Private semantic phase; zero preserves legacy behavior, not internal width.
  // These phase/selection fields widen the private job by4 bits; Host844 stays unchanged.
  // 1 gate,2 up,3 SiLU,4 down,5 Residual2: never a host capability.
  val runtimeFfnPhase=UInt(3.W)
  // Only original validated public21 Q/K/V commands set this semantic bit.
  // Persistent physical tags are transport identity, never command PCs.
  val public21Reduction=Bool()
  val qkRole=UInt(2.W);val qkPositionBase=UInt(32.W);val qkTrigTokens=UInt(32.W)
  val gdnALog=UInt(64.W);val gdnDtBias=UInt(64.W);val gdnStateOut=UInt(64.W);val gdnRecurrentMode=Bool();val gdnElementwiseOp=UInt(2.W)
}

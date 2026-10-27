// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Fixed common arena contract. No per-model hardware or memory allocation.
  * These are DDR byte offsets, NOT payload SRAM instances. This proposed72MiB layout is NOT an approved capacity change. It may
  * only be used inside a real accepted original Host region3 of sufficient
  * extent, after root accepts the common lifetime/allocation analysis.
  * Host backing-store capacity remains a transport allocation duty.
  * An actual scheduler must use these destinations for the preceding Dense,
  * norm and Conv jobs, not fabricate a receipt for data at these addresses.
  */
class UnifiedGdnScratchPlanV3 extends Bundle {
  val projection=UInt(64.W);val convolved=UInt(64.W);val ab=UInt(64.W)
  val prepared=UInt(64.W);val chunk=UInt(64.W);val core=UInt(64.W)
  val historyOut=UInt(64.W);val normalized=UInt(64.W);val end=UInt(64.W)
  val layout=new GdnRuntimeChunkLayout
  val numeric=new GdnRuntimeChunkNumericPolicy
  val prepReduction=UInt(2.W);val prepGate=UInt(2.W)
  val vectorContextPolicy=UInt(1.W)
  val boundsLegal=Bool();val implementedRecipe=Bool()
}
object UnifiedGdnScratchPlanV3 {
  val ArenaBytes=72L*1024*1024
  val offsets=Seq(0L,2L<<20,4L<<20,5L<<20,12L<<20,66L<<20,67L<<20,68L<<20)
  require(32L*(65536+2*806912)<=54L*1024*1024)
  require(128L*51200<=7L*1024*1024)
  def decode(c:UnifiedBlockDispatchV1):UnifiedGdnScratchPlanV3={
    val p=WireDefault(0.U.asTypeOf(new UnifiedGdnScratchPlanV3))
    val (shape,known)=UnifiedRuntimeProfile.decode(c.launch.profileId)
    val same=known && shape.asUInt===c.profile.asUInt
    val small=c.launch.profileId===UnifiedProfileId.Qwen35SmallGdn.U
    val moe=c.launch.profileId===UnifiedProfileId.Qwen35MoeGdn.U
    val base=c.launch.scratch
    val ends=base.pad(65)+ArenaBytes.U(65.W)
    val dest=Seq(p.projection,p.convolved,p.ab,p.prepared,p.chunk,p.core,p.historyOut,p.normalized)
    dest.zip(offsets).foreach{case(d,o)=>d:=(base.pad(65)+o.U)(63,0)}
    p.end:=ends(63,0)
    p.layout.keyHeads:=16.U;p.layout.valueHeads:=shape.gdnValueHeads
    p.layout.layoutId:=0.U;p.layout.layoutVersion:=1.U
    p.layout.rowBytes:=shape.gdnValueHeads*1600.U
    // Different namespaces: context1 maps to bank RawFp32FiniteGradual3 in
    // the leaf. It must NEVER be copied into bank policy1 (BF16 Mul).
    p.vectorContextPolicy:=1.U;p.numeric.decay:=1.U
    p.numeric.cumsum:=Mux(moe,1.U,0.U)
    p.prepReduction:=Mux(moe,1.U,0.U);p.prepGate:=Mux(moe,2.U,0.U)
    p.boundsLegal:=same && (small||moe) &&
      (c.launch.tokens===16.U || c.launch.tokens===128.U) && base(5,0)===0.U &&
      ends<=(BigInt(1)<<56).U(65.W)
    // This is an implementation-selection gate, NOT numerical acceptance.
    // RawPrep gate2/35B full recipe remains unqualified and unsupported on the
    // trusted path. No host policy override, and no changed ULP tolerance.
    p.implementedRecipe:=small
    p
  }
}

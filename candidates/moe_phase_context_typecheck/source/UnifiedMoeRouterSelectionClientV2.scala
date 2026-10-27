// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import gemmini.{HeteroScoreIndex,HeteroRankedScore}

/** Borrow the ONE shared HeteroStreamingTopK capacity512/index32/count20.
  * No primitive/SRAM is instantiated here; parent must bind an exclusive
  * resource lease and its original external512x65 table, or keep this owner
  * unavailable. Runtime k=8 does not shrink the physical selection hardware.
  * No clear is exported: resetting a busy selector is NOT a drain receipt. */
class UnifiedMoeRouterSelectionClientV2 extends Bundle {
  val start=Output(Bool());val startReady=Input(Bool())
  val itemCount=Output(UInt(20.W));val k=Output(UInt(10.W))
  val in=Decoupled(new HeteroScoreIndex(32,32))
  val out=Flipped(Decoupled(new HeteroRankedScore(32,32,10)))
  val busy=Input(Bool());val done=Input(Bool());val invalidConfig=Input(Bool())
}
/** Private future shared-format service. Finite FP32 in[0,1] -> BF16 RNE.
  * This port is intentionally NOT implemented by BF16Add policy2, whose input
  * contract is already BF16-expanded. Parent format-resource integration is
  * still required; no formatter/ALU is silently copied into this owner. */
class UnifiedMoeRouterFormatRequestV2 extends Bundle {val value=UInt(32.W)}
class UnifiedMoeRouterFormatResultV2 extends Bundle {val value=UInt(16.W);val error=Bool()}
class UnifiedMoeRouterFormatClientV2 extends Bundle {
  val request=Decoupled(new UnifiedMoeRouterFormatRequestV2)
  val result=Flipped(Decoupled(new UnifiedMoeRouterFormatResultV2))
}

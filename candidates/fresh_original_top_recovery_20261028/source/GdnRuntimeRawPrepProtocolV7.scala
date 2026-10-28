// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** TEMP rebuilt after local evidence loss. This is a NEW source identity.
  * Widths are explicit common physical capacities, not an old ABI equivalence
  * claim. Full rebuild, elaboration and five-profile numerical replay required.
  */
class GdnRuntimeRawPrepLayoutV7 extends Bundle {
  val keyHeads=UInt(6.W);val valueHeads=UInt(6.W)
  val layoutId=UInt(2.W);val layoutVersion=UInt(8.W);val rowBytes=UInt(32.W)
}
object GdnRuntimeRawPrepLayoutV7 {
  def admitted(p:GdnRuntimeRawPrepLayoutV7):Bool =
    p.keyHeads===16.U && (p.valueHeads===16.U || p.valueHeads===32.U) &&
      p.layoutId===0.U && p.layoutVersion===1.U && p.rowBytes===p.valueHeads*1600.U
}
object GdnRuntimeRawPrepPolicyV7 {
  val TorchCpuDefault128=1
  val LegacyOpen80=0;val DualInnerCandidate=2
}
class GdnRuntimeRawPrepJobV7 extends Bundle {
  val tokens=UInt(16.W)
  val conv=UInt(64.W);val ab=UInt(64.W);val aLog=UInt(64.W);val dtBias=UInt(64.W);val output=UInt(64.W)
  val tag=UInt(32.W);val layout=new GdnRuntimeRawPrepLayoutV7
  val reductionPolicy=UInt(2.W);val gatePolicy=UInt(2.W)
}
object GdnRuntimeRawPrepJobV7 {
  def fromOwner(j:QwenOwnerJob):GdnRuntimeRawPrepJobV7={
    val r=WireDefault(0.U.asTypeOf(new GdnRuntimeRawPrepJobV7))
    r.tokens:=j.m;r.conv:=j.a;r.ab:=j.b;r.aLog:=j.gdnALog;r.dtBias:=j.gdnDtBias;r.output:=j.dst;r.tag:=j.tag
    r.layout.keyHeads:=16.U;r.layout.valueHeads:=j.n;r.layout.layoutId:=0.U;r.layout.layoutVersion:=1.U;r.layout.rowBytes:=j.n*1600.U
    r.reductionPolicy:=Mux(j.n===32.U,1.U,0.U);r.gatePolicy:=Mux(j.n===32.U,2.U,0.U)
    r
  }
}
class GdnRuntimeRawPrepReadyV7 extends Bundle {
  val accepted=new GdnRuntimeRawPrepJobV7
  val scalarOperations=UInt(32.W);val formatOperations=UInt(32.W)
  val nonnegativeALog=UInt(6.W);val acknowledgedALogReads=UInt(2.W)
}
class GdnRuntimeRawPrepResultV7 extends Bundle {
  val accepted=new GdnRuntimeRawPrepJobV7
  val tag=UInt(32.W);val status=UInt(8.W);val writeBytes=UInt(64.W);val cycles=UInt(64.W);val outputCommitted=Bool()
}
class GdnRuntimeRawPrepPortV7 extends Bundle {
  val job=Flipped(Decoupled(new GdnRuntimeRawPrepJobV7))
  val prepare=Decoupled(new GdnRuntimeRawPrepReadyV7)
  val done=Decoupled(new GdnRuntimeRawPrepResultV7)
  val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
  val scalar=new UnifiedScalarClientV2
  val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
  val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
  val parentFault=Input(Bool());val resetRequired=Output(Bool());val resourcesDrained=Output(Bool())
}

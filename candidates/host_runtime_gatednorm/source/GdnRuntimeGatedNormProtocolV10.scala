// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private decoded ordinary job. Both runtime profiles use these same fixed
  * widths, the same 128-element buffers and the same shared service ports.
  * Core/gate/output are packed BF16 [M, heads, 128]; gamma is FP32 [128].
  * Parent provenance must come from actual Guard and successful Chunk events,
  * never a Host flag, an address match alone, or this geometry mapper. */
class GdnRuntimeGatedNormJobV10 extends Bundle {
  val tokens=UInt(16.W);val heads=UInt(6.W)
  val core=UInt(64.W);val gate=UInt(64.W);val weight=UInt(64.W);val output=UInt(64.W)
  val tag=UInt(32.W)
}
object GdnRuntimeGatedNormJobV10 {
  def fromOwner(j:QwenOwnerJob):GdnRuntimeGatedNormJobV10={
    val r=WireDefault(0.U.asTypeOf(new GdnRuntimeGatedNormJobV10))
    r.tokens:=j.m;r.heads:=j.n;r.core:=j.a;r.gate:=j.b;r.weight:=j.c;r.output:=j.dst;r.tag:=j.tag
    r
  }
}
class GdnRuntimeGatedNormResultV10 extends Bundle {
  val accepted=new GdnRuntimeGatedNormJobV10
  val tag=UInt(32.W);val status=UInt(8.W);val writeBytes=UInt(64.W);val cycles=UInt(64.W)
  val outputCommitted=Bool()
}
class GdnRuntimeGatedNormPortV10 extends Bundle {
  val job=Flipped(Decoupled(new GdnRuntimeGatedNormJobV10))
  val done=Decoupled(new GdnRuntimeGatedNormResultV10)
  val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
  val scalar=new UnifiedScalarClientV2
  val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
  val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
  val parentFault=Input(Bool());val resetRequired=Output(Bool());val resourcesDrained=Output(Bool())
}

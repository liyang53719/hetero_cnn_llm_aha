// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Internal owner protocol; NOT a replacement encoding for Command128. */
object ElemOp { val Copy=0; val Add=1; val Mul=2 }
object Status { val Ok=0; val Malformed=2; val Memory=3; val Unsupported=4; val Bounds=5; val Dependency=6; val Protocol=7; val Numerical=8; val Permission=9 }
case class ChainConfig(tileElements: Int=1024, tensorSlots: Int=32, programDepth: Int=64) {
  require(tileElements>=32 && isPow2(tileElements))
  require(tensorSlots>=4 && tensorSlots<=256 && isPow2(tensorSlots))
  require(programDepth>=4 && programDepth<=1024 && isPow2(programDepth))
  val tensorBits=log2Ceil(tensorSlots); val pcBits=log2Ceil(programDepth)
  val tileBeats=tileElements/16
  // Three canonical-FP32 buffers. Allocated out of the existing shared fabric.
  val aBeat=0; val bBeat=tileBeats; val cBeat=2*tileBeats
  val localBytes=3*tileElements*4
}
class Region extends Bundle {
  val base=UInt(64.W); val limit=UInt(64.W) // exclusive, not size
  val read=Bool(); val write=Bool()
}
class Tensor extends Bundle {
  val base=UInt(64.W); val elements=UInt(32.W)
  val bf16=Bool(); val region=UInt(2.W); val external=Bool()
}
class ProgramWord(c:ChainConfig) extends Bundle {
  val op=UInt(3.W); val a=UInt(c.tensorBits.W); val b=UInt(c.tensorBits.W); val dst=UInt(c.tensorBits.W)
  val aVersion=UInt(16.W); val bVersion=UInt(16.W); val dstVersion=UInt(16.W)
}
class RegionWrite extends Bundle {val index=UInt(2.W);val value=new Region}
class TensorWrite(c:ChainConfig) extends Bundle {val index=UInt(c.tensorBits.W);val value=new Tensor}
class ProgramWrite(c:ChainConfig) extends Bundle {val index=UInt(c.pcBits.W);val value=new ProgramWord(c)}
class BoundJob extends Bundle {
  val op=UInt(3.W); val a=UInt(64.W); val b=UInt(64.W); val dst=UInt(64.W); val elements=UInt(32.W)
  val aBf16=Bool(); val bBf16=Bool(); val dstBf16=Bool()
  val tag=UInt(32.W) // {request epoch16, program counter16}
}
class JobResult extends Bundle { val tag=UInt(32.W); val status=UInt(8.W); val elements=UInt(32.W); val writeBytes=UInt(64.W) }
class MemoryRequest extends Bundle {
  val write=Bool(); val address=UInt(64.W); val data=UInt(512.W); val mask=UInt(64.W); val tag=UInt(64.W)
}
class MemoryResponse extends Bundle { val data=UInt(512.W); val tag=UInt(64.W); val error=Bool() }
class Launch extends Bundle { val commands=UInt(16.W); val epoch=UInt(16.W) }
class ChainResult extends Bundle { val status=UInt(8.W); val epoch=UInt(16.W); val completed=UInt(16.W); val failedPc=UInt(16.W) }
object TensorMath {
  def payloadBytes(t:Tensor):UInt = t.elements.pad(66) << Mux(t.bf16,1.U,2.U)
  def span(t:Tensor):UInt = ((payloadBytes(t)+63.U)>>6)<<6
  def end(t:Tensor):UInt = t.base.pad(66)+span(t)
  def overlap(a:Tensor,b:Tensor):Bool = a.base.pad(66)<end(b) && b.base.pad(66)<end(a)
  def finite(x:UInt):Bool = x(30,23)=/=255.U
  def bf16Rne(x:UInt):UInt = {
    val rounded=(x +& "h7fff".U +& x(16))(31,16)
    Mux(x(30,23)===255.U, Cat(x(31),255.U(8.W),Mux(x(22,0).orR,64.U(7.W),0.U(7.W))), rounded)
  }
}

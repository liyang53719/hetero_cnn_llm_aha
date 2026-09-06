// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
class GemmShape extends Bundle {
  val a=UInt(64.W);val b=UInt(64.W);val dst=UInt(64.W)
  val m=UInt(32.W);val n=UInt(32.W);val k=UInt(32.W)
  val aStride=UInt(32.W);val bStride=UInt(32.W);val dstStride=UInt(32.W)
  val aLimit=UInt(64.W);val bLimit=UInt(64.W);val dstLimit=UInt(64.W)
}
class GemmTile extends Bundle {
  val a=UInt(64.W);val b=UInt(64.W);val dst=UInt(64.W)
  val mBase=UInt(32.W);val nBase=UInt(32.W);val kBase=UInt(32.W)
  val rows=UInt(5.W);val columns=UInt(6.W);val depth=UInt(16.W)
  val aStride=UInt(32.W);val bStride=UInt(32.W);val dstStride=UInt(32.W)
  val clear=Bool();val lastK=Bool();val lastTensor=Bool();val tag=UInt(64.W)
}
/** Runtime M/N/K cursor for retained 16x32 Matrix. K blocks do not change a
  * dot product's accumulation order. The consumer MUST retain FP32 accumulator
  * state across non-last K blocks; no intermediate BF16 store/reload is allowed.
  * This is a tested scheduling component, not an implemented GEMM endpoint.
  */
class DenseTileCursor(kBlock:Int=128) extends Module {
  require(kBlock>=32&&kBlock<=32768&&isPow2(kBlock))
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new GemmShape));val tile=Decoupled(new GemmTile)
    val ack=Flipped(Decoupled(new Bundle {val tag=UInt(64.W);val status=UInt(8.W);val writeCommitted=Bool()}))
    val done=Decoupled(UInt(8.W));val usefulMacs=Output(UInt(64.W));val tiles=Output(UInt(64.W));val resetRequired=Output(Bool())
  })
  val idle::issue::waitAck::finish::locked::Nil=Enum(5);val state=RegInit(idle);val d=Reg(new GemmShape)
  val mi=RegInit(0.U(32.W));val ni=RegInit(0.U(32.W));val ki=RegInit(0.U(32.W));val tag=RegInit(0.U(64.W))
  val status=RegInit(0.U(8.W));val poison=RegInit(false.B);val macs=RegInit(0.U(64.W))
  val rm=Mux(d.m-mi>16.U,16.U,d.m-mi);val rn=Mux(d.n-ni>32.U,32.U,d.n-ni);val rk=Mux(d.k-ki>kBlock.U,kBlock.U,d.k-ki)
  val lastK=ki+rk===d.k;val lastTensor=lastK&&ni+rn===d.n&&mi+rm===d.m
  io.request.ready:=state===idle;io.tile.valid:=state===issue;io.ack.ready:=state===waitAck
  io.done.valid:=state===finish;io.done.bits:=status;io.usefulMacs:=macs;io.tiles:=tag;io.resetRequired:=poison
  io.tile.bits.a:=d.a+mi.pad(64)*d.aStride+ki.pad(64)*2.U
  io.tile.bits.b:=d.b+ki.pad(64)*d.bStride+ni.pad(64)*2.U
  io.tile.bits.dst:=d.dst+mi.pad(64)*d.dstStride+ni.pad(64)*4.U
  io.tile.bits.mBase:=mi;io.tile.bits.nBase:=ni;io.tile.bits.kBase:=ki
  io.tile.bits.rows:=rm;io.tile.bits.columns:=rn;io.tile.bits.depth:=rk
  io.tile.bits.aStride:=d.aStride;io.tile.bits.bStride:=d.bStride;io.tile.bits.dstStride:=d.dstStride
  io.tile.bits.clear:=ki===0.U;io.tile.bits.lastK:=lastK;io.tile.bits.lastTensor:=lastTensor;io.tile.bits.tag:=tag
  def fail(s:UInt):Unit={status:=s;poison:=true.B;state:=finish}
  switch(state) {
    is(idle) {when(io.request.fire) {
      d:=io.request.bits;mi:=0.U;ni:=0.U;ki:=0.U;tag:=0.U;macs:=0.U;status:=0.U
      val x=io.request.bits
      val ae=x.a.pad(66)+(x.m.pad(66)-1.U)*x.aStride+x.k.pad(66)*2.U
      val be=x.b.pad(66)+(x.k.pad(66)-1.U)*x.bStride+x.n.pad(66)*2.U
      val ce=x.dst.pad(66)+(x.m.pad(66)-1.U)*x.dstStride+x.n.pad(66)*4.U
      val macCount=x.m*x.n*x.k
      val legal=x.m=/=0.U&&x.n=/=0.U&&x.k=/=0.U&&x.a(5,0)===0.U&&x.b(5,0)===0.U&&x.dst(5,0)===0.U&&
        x.aStride(5,0)===0.U&&x.bStride(5,0)===0.U&&x.dstStride(5,0)===0.U&&
        x.aStride.pad(66)>=x.k.pad(66)*2.U&&x.bStride.pad(66)>=x.n.pad(66)*2.U&&x.dstStride.pad(66)>=x.n.pad(66)*4.U&&
        ae<=x.aLimit&&be<=x.bLimit&&ce<=x.dstLimit&&
        x.aLimit<=(BigInt(1)<<56).U&&x.bLimit<=(BigInt(1)<<56).U&&x.dstLimit<=(BigInt(1)<<56).U&&
        (ce<=x.a.pad(66)||ae<=x.dst.pad(66))&&(ce<=x.b.pad(66)||be<=x.dst.pad(66))&&macCount(95,64)===0.U
      when(!legal){fail(Status.Bounds.U)}.otherwise{state:=issue}
    }}
    is(issue) {when(io.tile.fire){state:=waitAck}}
    is(waitAck) {when(io.ack.fire){
      when(io.ack.bits.tag=/=tag||io.ack.bits.writeCommitted=/=lastK){fail(Status.Protocol.U)}
      .elsewhen(io.ack.bits.status=/=0.U){fail(io.ack.bits.status)}.otherwise {
        tag:=tag+1.U;macs:=macs+rm*rn*rk
        when(lastTensor){state:=finish}.elsewhen(!lastK){ki:=ki+rk;state:=issue}
        .elsewhen(ni+rn<d.n){ki:=0.U;ni:=ni+rn;state:=issue}
        .otherwise{ki:=0.U;ni:=0.U;mi:=mi+rm;state:=issue}
      }
    }}
    is(finish){when(io.done.fire){state:=Mux(poison,locked,idle)}}
    is(locked){}
  }
}

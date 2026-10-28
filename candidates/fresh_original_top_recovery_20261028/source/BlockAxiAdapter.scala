// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
class BlockAxiAddress extends Bundle {val addr=UInt(64.W);val id=UInt(8.W);val len=UInt(8.W);val size=UInt(3.W);val burst=UInt(2.W)}
class BlockAxiWrite extends Bundle {val data=UInt(512.W);val strb=UInt(64.W);val last=Bool()}
class BlockAxiB extends Bundle {val id=UInt(8.W);val resp=UInt(2.W)}
class BlockAxiR extends Bundle {val id=UInt(8.W);val data=UInt(512.W);val resp=UInt(2.W);val last=Bool()}
class BlockAxiMaster extends Bundle {
  val aw=Decoupled(new BlockAxiAddress);val w=Decoupled(new BlockAxiWrite);val b=Flipped(Decoupled(new BlockAxiB))
  val ar=Decoupled(new BlockAxiAddress);val r=Flipped(Decoupled(new BlockAxiR))
}
/** Single-inflight, single-64B-beat AXI4 master. AW and W may stall independently.
  * A MemoryResponse for a write is produced ONLY after B, never after AW/W.
  * Protocol/SLVERR/DECERR faults return one failed response then quarantine the
  * adapter until reset. Memory visibility is a platform integration contract.
  */
class BlockAxiMemoryAdapter extends Module {
  val io=IO(new Bundle {val request=Flipped(Decoupled(new MemoryRequest));val response=Decoupled(new MemoryResponse);val axi=new BlockAxiMaster;val resetRequired=Output(Bool())})
  val idle::wr::br::rd::rr::reply::locked::Nil=Enum(7);val state=RegInit(idle)
  val req=Reg(new MemoryRequest);val rsp=Reg(new MemoryResponse);val poison=RegInit(false.B)
  val awSent=RegInit(false.B);val wSent=RegInit(false.B)
  io.request.ready:=state===idle && !poison;io.response.valid:=state===reply;io.response.bits:=rsp;io.resetRequired:=poison
  io.axi.aw.valid:=state===wr && !awSent;io.axi.w.valid:=state===wr && !wSent
  io.axi.ar.valid:=state===rd;io.axi.b.ready:=state===br||state===locked;io.axi.r.ready:=state===rr||state===locked
  for(a<-Seq(io.axi.aw.bits,io.axi.ar.bits)){a.addr:=req.address;a.id:=req.tag(7,0);a.len:=0.U;a.size:=6.U;a.burst:=1.U}
  io.axi.w.bits.data:=req.data;io.axi.w.bits.strb:=req.mask;io.axi.w.bits.last:=true.B
  when(io.request.fire){req:=io.request.bits;rsp.tag:=io.request.bits.tag;rsp.data:=0.U;rsp.error:=false.B;awSent:=false.B;wSent:=false.B
    when(io.request.bits.address(5,0)=/=0.U||io.request.bits.address(63,56).orR){rsp.error:=true.B;poison:=true.B;state:=reply}
    .otherwise{state:=Mux(io.request.bits.write,wr,rd)}}
  when(state===wr){when(io.axi.aw.fire){awSent:=true.B};when(io.axi.w.fire){wSent:=true.B}
    when((awSent||io.axi.aw.fire)&&(wSent||io.axi.w.fire)){state:=br}}
  when(state===br&&io.axi.b.fire){val bad=io.axi.b.bits.resp=/=0.U||io.axi.b.bits.id=/=req.tag(7,0);rsp.error:=bad;poison:=bad;state:=reply}
  when(state===rd&&io.axi.ar.fire){state:=rr}
  when(state===rr&&io.axi.r.fire){val bad=io.axi.r.bits.resp=/=0.U||io.axi.r.bits.id=/=req.tag(7,0)|| !io.axi.r.bits.last
    rsp.data:=io.axi.r.bits.data;rsp.error:=bad;poison:=bad;state:=reply}
  when(state===reply&&io.response.fire){state:=Mux(poison,locked,idle)}
}
class Qwen2AxiBlockTop(s:QwenBlockShape=QwenBlockShape()) extends Module {
  val block=Module(new Qwen2ContinuousBlock(s));val bridge=Module(new BlockAxiMemoryAdapter)
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new BlockLaunch));val result=Decoupled(new BlockResult);val axi=new BlockAxiMaster
    val phase=Output(UInt(5.W));val stageCommit=Output(Bool());val committedPhase=Output(UInt(5.W));val resetRequired=Output(Bool())
    val readBytes=Output(UInt(64.W));val writeBytes=Output(UInt(64.W))
  })
  dontTouch(io) // Preserve scalar AXI constants when this root is a child of the joint emitter.
  block.io.launch<>io.launch;io.result<>block.io.result
  bridge.io.request<>block.io.memory;block.io.response<>bridge.io.response;io.axi<>bridge.io.axi
  io.phase:=block.io.phase;io.stageCommit:=block.io.stageCommit;io.committedPhase:=block.io.committedPhase
  io.resetRequired:=block.io.resetRequired||bridge.io.resetRequired;io.readBytes:=block.io.readBytes;io.writeBytes:=block.io.writeBytes
}

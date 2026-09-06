// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class AxiAddress extends Bundle {val address=UInt(64.W);val id=UInt(4.W);val len=UInt(8.W);val size=UInt(3.W);val burst=UInt(2.W)}
class AxiWriteData extends Bundle {val data=UInt(512.W);val strobe=UInt(64.W);val last=Bool()}
class AxiReadData extends Bundle {val data=UInt(512.W);val id=UInt(4.W);val response=UInt(2.W);val last=Bool()}
class AxiWriteResponse extends Bundle {val id=UInt(4.W);val response=UInt(2.W)}
class Axi512 extends Bundle {
  val ar=Decoupled(new AxiAddress);val r=Flipped(Decoupled(new AxiReadData))
  val aw=Decoupled(new AxiAddress);val w=Decoupled(new AxiWriteData);val b=Flipped(Decoupled(new AxiWriteResponse))
}
/** One in-flight single-beat AXI4 transport. Writes are committed only after B.
  * Independent AW and W backpressure; full 64-bit address preserved. This is a
  * conservative compatibility transport, NOT an iDMA throughput replacement.
  */
class MemoryToAxi extends Module {
  val io=IO(new Bundle {val request=Flipped(Decoupled(new MemoryRequest));val response=Decoupled(new MemoryResponse);val axi=new Axi512})
  val idle::readAddr::readData::writeData::writeResponse::reply::Nil=Enum(6)
  val state=RegInit(idle);val req=Reg(new MemoryRequest);val data=Reg(UInt(512.W));val error=RegInit(false.B)
  val awSent=RegInit(false.B);val wSent=RegInit(false.B)
  io.request.ready:=state===idle
  io.response.valid:=state===reply;io.response.bits.tag:=req.tag;io.response.bits.data:=data;io.response.bits.error:=error
  for(a<-Seq(io.axi.ar,io.axi.aw)){a.bits.address:=req.address;a.bits.id:=0.U;a.bits.len:=0.U;a.bits.size:=6.U;a.bits.burst:=1.U}
  io.axi.ar.valid:=state===readAddr;io.axi.r.ready:=state===readData
  io.axi.aw.valid:=state===writeData && !awSent
  io.axi.w.valid:=state===writeData && !wSent;io.axi.w.bits.data:=req.data;io.axi.w.bits.strobe:=req.mask;io.axi.w.bits.last:=true.B
  io.axi.b.ready:=state===writeResponse
  switch(state){
    is(idle){when(io.request.fire){req:=io.request.bits;error:=false.B;data:=0.U;awSent:=false.B;wSent:=false.B
      when(io.request.bits.address(5,0)=/=0.U||io.request.bits.address.pad(66)+64.U>(BigInt(1)<<56).U){error:=true.B;state:=reply}
      .otherwise{state:=Mux(io.request.bits.write,writeData,readAddr)}
    }}
    is(readAddr){when(io.axi.ar.fire){state:=readData}}
    is(readData){when(io.axi.r.fire){data:=io.axi.r.bits.data
      error:=error||io.axi.r.bits.id=/=0.U||io.axi.r.bits.response=/=0.U|| !io.axi.r.bits.last
      // Drain malformed multi-beat replies before releasing the one transaction.
      when(io.axi.r.bits.last){state:=reply}
    }}
    is(writeData){when(io.axi.aw.fire){awSent:=true.B};when(io.axi.w.fire){wSent:=true.B}
      when((awSent||io.axi.aw.fire)&&(wSent||io.axi.w.fire)){state:=writeResponse}}
    is(writeResponse){when(io.axi.b.fire){error:=io.axi.b.bits.id=/=0.U||io.axi.b.bits.response=/=0.U;state:=reply}}
    is(reply){when(io.response.fire){state:=idle}}
  }
}
class Qwen2BlockAxiTop(s:QwenBlockShape=QwenBlockShape()) extends Module {
  val io=IO(new Bundle {val launch=Flipped(Decoupled(new BlockLaunch));val result=Decoupled(new BlockResult);val axi=new Axi512;val resetRequired=Output(Bool());val phase=Output(UInt(5.W));val stageCommit=Output(Bool());val committedPhase=Output(UInt(5.W))})
  val block=Module(new Qwen2ContinuousBlock(s));val transport=Module(new MemoryToAxi)
  block.io.launch<>io.launch;io.result<>block.io.result
  transport.io.request<>block.io.memory;block.io.response<>transport.io.response;io.axi<>transport.io.axi;io.resetRequired:=block.io.resetRequired
  io.phase:=block.io.phase;io.stageCommit:=block.io.stageCommit;io.committedPhase:=block.io.committedPhase
}

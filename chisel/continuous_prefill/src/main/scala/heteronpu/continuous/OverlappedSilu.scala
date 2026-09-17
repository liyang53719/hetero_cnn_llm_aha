// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class SiluOwnerPort extends Bundle {
  val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
  val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
  val resetRequired=Output(Bool())
}

/** Overlap the next operand pair and prior store with the existing bit-exact
  * 16-lane arithmetic. There is still exactly one external memory transaction
  * in flight. No early store ACK and no changed exp/div/rounding recipe.
  * All queues and the arithmetic unit drain after an error before completion.
  */
class OverlappedSiluOwner extends Module {
  val io=IO(new SiluOwnerPort)
  val idle::active::finish::locked::Nil=Enum(4)
  val state=RegInit(idle);val job=Reg(new QwenOwnerJob)
  val status=RegInit(0.U(8.W));val cycles=RegInit(0.U(64.W));val bytes=RegInit(0.U(64.W))
  val elements=Reg(UInt(32.W));val fetched=RegInit(0.U(32.W));val stored=RegInit(0.U(32.W))
  val sequence=RegInit(0.U(32.W));val gate=Reg(Vec(16,UInt(32.W)));val gateValid=RegInit(false.B)
  val input=Module(new Queue(new SiluVectorInput(16),2,pipe=false,flow=false))
  val output=Module(new Queue(UInt(512.W),2,pipe=false,flow=false))
  val vector=Module(new SiluVectorUnit(16));val computing=RegInit(false.B)
  val memIdle::offer::waitReply::Nil=Enum(3)
  val memoryState=RegInit(memIdle);val request=Reg(new MemoryRequest);val requestKind=Reg(UInt(2.W))
  def fail(code:UInt):Unit={when(status===0.U){status:=code}}
  val poisoned=status=/=0.U
  io.resetRequired:=poisoned
  io.job.ready:=state===idle
  io.done.valid:=state===finish
  io.done.bits.tag:=job.tag;io.done.bits.status:=status;io.done.bits.cycles:=cycles
  io.done.bits.writeBytes:=bytes;io.done.bits.usefulMacs:=0.U;io.done.bits.executedMacs:=0.U
  io.memory.valid:=state===active&&memoryState===offer
  io.memory.bits:=request
  io.response.ready:=state===active&&memoryState===waitReply
  vector.io.request.valid:=state===active && !poisoned && input.io.deq.valid
  vector.io.request.bits:=input.io.deq.bits
  input.io.deq.ready:=poisoned || (state===active&&vector.io.request.ready)
  vector.io.result.ready:=poisoned || output.io.enq.ready
  output.io.enq.valid:=state===active && !poisoned && vector.io.result.valid && !vector.io.result.bits.error
  output.io.enq.bits:=vector.io.result.bits.value.asUInt
  when(vector.io.request.fire){computing:=true.B}
  when(vector.io.result.fire){computing:=false.B;when(vector.io.result.bits.error){fail(Status.Numerical.U)}}
  input.io.enq.valid:=false.B
  input.io.enq.bits.gate:=gate
  input.io.enq.bits.up:=io.response.bits.data.asTypeOf(Vec(16,UInt(32.W)))
  output.io.deq.ready:=poisoned

  // Capture a complete offer before asserting valid. Error discovery cannot
  // withdraw an already stalled offer: it is accepted and drained instead.
  when(state===active && memoryState===memIdle && !poisoned){
    val store=output.io.deq.valid
    val load=fetched<elements && input.io.enq.ready
    when(store || load){
      request.write:=store
      request.address:=Mux(store,job.dst+(stored.pad(64)<<2),Mux(gateValid,job.b,job.a)+(fetched.pad(64)<<2))
      request.data:=Mux(store,output.io.deq.bits,0.U)
      request.mask:=Mux(store,Fill(64,1.U(1.W)),0.U)
      request.tag:=Cat(job.tag,sequence)
      requestKind:=Mux(store,2.U,Mux(gateValid,1.U,0.U))
      output.io.deq.ready:=store;memoryState:=offer
    }
  }
  when(io.memory.fire){memoryState:=waitReply}
  when(io.response.fire){
    memoryState:=memIdle;sequence:=sequence+1.U
    val r=io.response.bits
    when(r.error){fail(Status.Memory.U)}
      .elsewhen(r.tag=/=request.tag){fail(Status.Protocol.U)}
      .otherwise{
        // Successful stores are physical side effects, even if a concurrent
        // numerical error poisoned the owner while this request was in flight.
        // Account their ACKs without publishing a successful tensor/result.
        when(requestKind===2.U){bytes:=bytes+64.U;stored:=stored+16.U}
        when(!poisoned){
          when(requestKind===0.U){gate:=r.data.asTypeOf(gate);gateValid:=true.B}
          when(requestKind===1.U){
            assert(input.io.enq.ready,"reserved SiLU input queue entry lost")
            input.io.enq.valid:=true.B;fetched:=fetched+16.U;gateValid:=false.B
          }
        }
      }
  }
  when(state===active){
    cycles:=cycles+1.U
    val drained=memoryState===memIdle && !computing && !input.io.deq.valid && !output.io.deq.valid
    when(poisoned && drained){gateValid:=false.B;state:=finish}
    when(!poisoned && stored===elements && fetched===elements && !gateValid && drained){state:=finish}
  }
  when(io.job.fire){
    val j=io.job.bits;job:=j;status:=0.U;cycles:=0.U;bytes:=0.U
    fetched:=0.U;stored:=0.U;sequence:=0.U;gateValid:=false.B
    val count=j.m*j.n;elements:=count
    val size=count.pad(66)<<2
    val endA=j.a.pad(66)+size;val endB=j.b.pad(66)+size;val endC=j.dst.pad(66)+size
    val badAddress=Seq(j.a,j.b,j.dst).map(x=>x(5,0)=/=0.U || x.pad(66)+size>(BigInt(1)<<56).U).reduce(_||_)
    val alias=(j.a.pad(66)<endC&&j.dst.pad(66)<endA)||(j.b.pad(66)<endC&&j.dst.pad(66)<endB)
    when(j.kind=/=QwenOwnerKind.Activation.U || count===0.U || count(3,0)=/=0.U || j.writeBytes=/=size || badAddress || alias){
      status:=Status.Bounds.U;state:=finish
    }.otherwise{state:=active}
  }
  when(io.done.fire){state:=Mux(poisoned,locked,idle)}
}

/** Elaboration-time selection: exactly one arithmetic owner is instantiated. */
class ScheduledSiluOwner(overlap:Boolean=false) extends Module {
  val io=IO(new SiluOwnerPort)
  if(overlap){val dut=Module(new OverlappedSiluOwner);io<>dut.io}
  else{val dut=Module(new VectorSiluOwner);io<>dut.io}
}

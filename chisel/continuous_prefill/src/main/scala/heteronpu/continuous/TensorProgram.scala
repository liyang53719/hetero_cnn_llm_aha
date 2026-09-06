// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Sequential, versioned tensor program. Configuration is immutable while active.
  * Availability is committed ONLY on a matching successful writeback completion.
  * All non-external slots are invalidated at each new request epoch.
  */
class TensorProgram(c:ChainConfig=ChainConfig()) extends Module {
  val io=IO(new Bundle {
    val regionWrite=Flipped(Decoupled(new RegionWrite))
    val tensorWrite=Flipped(Decoupled(new TensorWrite(c)))
    val programWrite=Flipped(Decoupled(new ProgramWrite(c)))
    val launch=Flipped(Decoupled(new Launch)); val result=Decoupled(new ChainResult)
    val job=Decoupled(new BoundJob); val done=Flipped(Decoupled(new JobResult))
    val busy=Output(Bool()); val resetRequired=Output(Bool())
    val committed=Output(Bool()); val committedTensor=Output(UInt(c.tensorBits.W)); val committedVersion=Output(UInt(16.W))
  })
  val idle::fetch::check::issue::waitDone::finish::locked::Nil=Enum(7)
  val state=RegInit(idle); val regs=Reg(Vec(4,new Region)); val regionSet=RegInit(0.U(4.W))
  val tensors=Reg(Vec(c.tensorSlots,new Tensor)); val tensorSet=RegInit(VecInit(Seq.fill(c.tensorSlots)(false.B)))
  val available=RegInit(VecInit(Seq.fill(c.tensorSlots)(false.B)))
  val versions=RegInit(VecInit(Seq.fill(c.tensorSlots)(0.U(16.W))))
  val program=Mem(c.programDepth,new ProgramWord(c)); val programSet=RegInit(VecInit(Seq.fill(c.programDepth)(false.B)))
  val pc=RegInit(0.U(16.W)); val count=RegInit(0.U(16.W)); val epoch=RegInit(0.U(16.W)); val lastEpoch=RegInit(0.U(16.W))
  val status=RegInit(0.U(8.W)); val completed=RegInit(0.U(16.W)); val poison=RegInit(false.B)
  val inst=Reg(new ProgramWord(c)); val bound=Reg(new BoundJob)
  io.regionWrite.ready:=state===idle && !io.launch.valid
  io.tensorWrite.ready:=state===idle && !io.launch.valid
  io.programWrite.ready:=state===idle && !io.launch.valid
  when(io.regionWrite.fire) { regs(io.regionWrite.bits.index):=io.regionWrite.bits.value; regionSet:=regionSet | UIntToOH(io.regionWrite.bits.index,4) }
  when(io.tensorWrite.fire) {tensors(io.tensorWrite.bits.index):=io.tensorWrite.bits.value; tensorSet(io.tensorWrite.bits.index):=true.B}
  when(io.programWrite.fire) {program(io.programWrite.bits.index):=io.programWrite.bits.value; programSet(io.programWrite.bits.index):=true.B}
  io.launch.ready:=state===idle; io.busy:=state=/=idle; io.resetRequired:=poison
  io.result.valid:=state===finish; io.result.bits.status:=status; io.result.bits.epoch:=epoch
  io.result.bits.completed:=completed; io.result.bits.failedPc:=pc
  io.job.valid:=state===issue; io.job.bits:=bound; io.done.ready:=state===waitDone
  io.committed:=false.B; io.committedTensor:=inst.dst; io.committedVersion:=inst.dstVersion
  val ta=tensors(inst.a); val tb=tensors(inst.b); val td=tensors(inst.dst)
  def validView(t:Tensor,w:Boolean):Bool = {
    val r=regs(t.region)
    regionSet(t.region) && t.elementCount=/=0.U && t.base(5,0)===0.U &&
      r.base<r.limit && r.limit<=(BigInt(1)<<56).U && t.base>=r.base &&
      TensorMath.end(t)<=r.limit.pad(66) && (if(w)r.write else r.read)
  }
  val regionLegal=(0 until 4).map(i => !regionSet(i) || (regs(i).base<regs(i).limit && regs(i).limit<=(BigInt(1)<<56).U && regs(i).base(5,0)===0.U && regs(i).limit(5,0)===0.U)).reduce(_&&_)
  val noRegionAlias=(for(i<-0 until 4;j<-i+1 until 4)yield !regionSet(i)|| !regionSet(j)||regs(i).limit<=regs(j).base||regs(j).limit<=regs(i).base).reduce(_&&_)
  val binary=inst.op=/=ElemOp.Copy.U
  val deps=tensorSet(inst.a)&&tensorSet(inst.dst)&&available(inst.a)&&versions(inst.a)===inst.aVersion&&
    (!binary || (tensorSet(inst.b)&&available(inst.b)&&versions(inst.b)===inst.bVersion))&&
    !td.external && versions(inst.dst)=/=65535.U && inst.dstVersion===versions(inst.dst)+1.U
  val aliases=(0 until c.tensorSlots).map(i=>available(i)&&i.U=/=inst.dst&&TensorMath.overlap(td,tensors(i))).reduce(_||_)
  val views=validView(ta,false)&&validView(td,true)&&(!binary||validView(tb,false))&&ta.elementCount===td.elementCount&&(!binary||tb.elementCount===td.elementCount)
  def fail(s:UInt):Unit={status:=s; poison:=true.B; state:=finish}
  switch(state) {
    is(idle) {when(io.launch.fire) {
      pc:=0.U; count:=io.launch.bits.commands; epoch:=io.launch.bits.epoch; completed:=0.U; status:=0.U
      for(i<-0 until c.tensorSlots) {available(i):=tensorSet(i)&&tensors(i).external; versions(i):=0.U}
      when(io.launch.bits.commands===0.U||io.launch.bits.commands>c.programDepth.U||io.launch.bits.epoch<=lastEpoch|| !regionLegal|| !noRegionAlias) {fail(Status.Malformed.U)}
        .otherwise {lastEpoch:=io.launch.bits.epoch; state:=fetch}
    }}
    is(fetch) {when(!programSet(pc(c.pcBits-1,0))) {fail(Status.Malformed.U)}.otherwise {inst:=program(pc(c.pcBits-1,0));state:=check}}
    is(check) {
      when(inst.op>ElemOp.Mul.U) {fail(Status.Unsupported.U)}
      .elsewhen(!deps) {fail(Status.Dependency.U)}
      .elsewhen(!views||aliases||inst.a===inst.dst||(binary&&inst.b===inst.dst)) {fail(Status.Bounds.U)}
      .otherwise {
        bound.op:=inst.op;bound.a:=ta.base;bound.b:=tb.base;bound.dst:=td.base;bound.elementCount:=td.elementCount
        bound.aBf16:=ta.bf16;bound.bBf16:=tb.bf16;bound.dstBf16:=td.bf16;bound.tag:=Cat(epoch,pc)
        available(inst.dst):=false.B;state:=issue
      }
    }
    is(issue) {when(io.job.fire) {state:=waitDone}}
    is(waitDone) {when(io.done.fire) {
      when(io.done.bits.tag=/=bound.tag) {fail(Status.Protocol.U)}
      .elsewhen(io.done.bits.status=/=0.U) {fail(io.done.bits.status)}
      .elsewhen(io.done.bits.elementCount=/=bound.elementCount||io.done.bits.writeBytes=/=TensorMath.payloadBytes(td)) {fail(Status.Protocol.U)}
      .otherwise {
        available(inst.dst):=true.B;versions(inst.dst):=inst.dstVersion;io.committed:=true.B
        completed:=completed+1.U
        when(pc+1.U===count) {state:=finish}.otherwise {pc:=pc+1.U;state:=fetch}
      }
    }
    is(finish) {when(io.result.fire) {state:=Mux(poison,locked,idle)}}
    is(locked) {}
  }
}

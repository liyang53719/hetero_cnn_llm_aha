// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Bounded SRAM tile feeder for the original 4096-MAC arithmetic.
  * A is cached for at most 16 token rows. Two BF16 weight buffers hold 16 K
  * positions for five independent N tiles. The producer fills the alternate
  * buffer through validated real-iDMA bursts while the consumer issues the
  * current one. Each output context receives K=0,1,... without reassociation.
  * Host completion follows all final FP32 stores, never the last MAC issue.
  */
class StreamingDenseOwner(maxK:Int=8960) extends Module {
  require(maxK>0 && maxK%16==0)
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val burst=Decoupled(new BurstReadRequest);val burstResponse=Flipped(Decoupled(new BurstReadResponse))
    val matrix=new MatrixStreamPort;val physicalSteps=Input(UInt(64.W))
    val resetRequired=Output(Bool());val issueCycles=Output(UInt(64.W));val operandStalls=Output(UInt(64.W))
  })
  val idle::aReq::aWait::setup::execute::finish::locked::Nil=Enum(7)
  val state=RegInit(idle);val job=Reg(new QwenOwnerJob)
  val status=RegInit(0.U(8.W));val cycles=RegInit(0.U(64.W));val useful=RegInit(0.U(64.W));val bytes=RegInit(0.U(64.W))
  val physicalBase=RegInit(0.U(64.W));val issued=RegInit(0.U(64.W));val starved=RegInit(0.U(64.W))
  val rowBase=RegInit(0.U(16.W));val rows=Reg(UInt(5.W));val nBase=RegInit(0.U(16.W));val contexts=Reg(UInt(3.W))
  val aRow=RegInit(0.U(5.W));val aBeat=RegInit(0.U(16.W))
  val burstCount=Reg(UInt(5.W));val burstIndex=RegInit(0.U(5.W));val sequence=RegInit(0.U(32.W))
  val burstTag=Reg(UInt(64.W))
  val aBanks=Seq.fill(16)(SyncReadMem(maxK/16,UInt(256.W)))
  val wBanks=Seq.fill(16)(SyncReadMem(160,UInt(256.W))) // 2 x K16 x contexts5
  val ready=RegInit(VecInit(Seq.fill(2)(false.B)))
  val readyK=Reg(Vec(2,UInt(16.W)))
  val loadIdle::loadReq::loadWait::Nil=Enum(3)
  val loadState=RegInit(loadIdle);val loadSel=RegInit(false.B);val loadK=Reg(UInt(16.W));val loadDepth=RegInit(0.U(5.W))
  val loadContext=RegInit(0.U(3.W));val loadBeat=RegInit(0.U(5.W));val nextLoadK=RegInit(0.U(16.W))
  val issueSel=RegInit(false.B);val issueK=RegInit(0.U(16.W));val issueContext=RegInit(0.U(3.W));val allIssued=RegInit(false.B)
  val groupStarted=RegInit(false.B);val groupDone=RegInit(false.B)
  val writeIdle::writeReq::writeWait::Nil=Enum(3)
  val writeState=RegInit(writeIdle);val writeContext=Reg(UInt(3.W));val writeRow=RegInit(0.U(5.W));val writeBeat=RegInit(0.U(5.W))
  val written=RegInit(0.U(3.W));val finalValue=Reg(Vec(16,Vec(256,UInt(32.W))))
  val writeSequence=RegInit(0.U(32.W));val writeTag=Cat(job.tag,writeSequence)
  def fail(code:UInt):Unit={when(status===0.U){status:=code}}
  def columns(ctx:UInt):UInt={val remaining=job.n-(nBase+(ctx.pad(16)<<8));Mux(remaining>256.U,256.U,remaining)}
  def countAt(addr:UInt,remaining:UInt):UInt={val page=16.U(6.W)-addr(9,6);Mux(remaining<page,remaining,page)}
  val aAddress=job.a+(((rowBase.pad(64)+aRow)*job.k+(aBeat.pad(64)<<4))<<2)
  val wAddress=job.b+(((loadK.pad(64)+loadDepth)*job.n+nBase+(loadContext.pad(64)<<8)+(loadBeat.pad(64)<<4))<<2)
  val loadingA=state===aReq||state===aWait
  io.burst.valid:=status===0.U && (state===aReq || (state===execute&&loadState===loadReq))
  io.burst.bits.address:=Mux(loadingA,aAddress,wAddress)
  io.burst.bits.beats:=Mux(loadingA,countAt(aAddress,(job.k>>4)-aBeat),countAt(wAddress,(columns(loadContext)>>4)-loadBeat))
  io.burst.bits.tag:=Cat(job.tag,sequence)
  io.burstResponse.ready:=state===aWait || (state===execute&&loadState===loadWait)
  io.job.ready:=state===idle
  io.done.valid:=state===finish;io.done.bits.tag:=job.tag;io.done.bits.status:=status
  io.done.bits.cycles:=cycles;io.done.bits.writeBytes:=bytes;io.done.bits.usefulMacs:=useful
  io.done.bits.executedMacs:=(io.physicalSteps-physicalBase)*512.U
  io.resetRequired:=status=/=0.U;io.issueCycles:=issued;io.operandStalls:=starved
  io.matrix.group.valid:=state===execute && !groupStarted && status===0.U
  io.matrix.group.bits.opcode:=0x20.U;io.matrix.group.bits.tag:=job.tag
  io.matrix.group.bits.sliceMask:=VecInit((0 until 8).map(i=>(nBase+(i*32).U)<job.n)).asUInt
  io.matrix.done.ready:=state===execute&&groupStarted && !groupDone
  io.matrix.abort:=state===execute&&status=/=0.U&&groupStarted && !groupDone

  // A single-cycle SRAM read stage followed by an elastic operand FIFO.
  // Credit reservation includes the pending synchronous read, so stalls cannot
  // overwrite an operand which was already accepted by this feeder.
  class Operand extends Bundle {val step=new MatrixStreamStep}
  val operands=Module(new Queue(new Operand,4,pipe=true))
  val pending=RegInit(false.B);val pendingK=Reg(UInt(16.W));val pendingContext=Reg(UInt(3.W))
  val canRead=state===execute&&groupStarted && !groupDone && !allIssued&&status===0.U&&
    ready(issueSel)&&readyK(issueSel)===(issueK&"hfff0".U)&&operands.io.count+&pending.asUInt<4.U
  val readFire=canRead
  val aRead=aBanks.map(_.read(issueK>>4,readFire))
  // 80 + 15*5 + 4 = 159: an explicit eight-bit sum is required.
  // A seven-bit Mux(80,0) plus a four-bit K product would wrap at 128.
  val wAddr=Mux(issueSel,80.U(8.W),0.U(8.W))+(issueK(3,0).pad(8)*5.U)(7,0)+issueContext.pad(8)
  val wRead=wBanks.map(_.read(wAddr,readFire))
  pending:=readFire
  when(readFire){pendingK:=issueK;pendingContext:=issueContext}
  val p=operands.io.enq.bits.step
  operands.io.enq.valid:=pending&&status===0.U
  p.context:=pendingContext;p.clear:=pendingK===0.U;p.last:=pendingK+1.U===job.k
  p.finish:=p.last&&pendingContext+1.U===contexts;p.emit:=p.last
  for(r<-0 until 16){
    val lane=aRead(r).asTypeOf(Vec(16,UInt(16.W)))
    p.a(r):=Mux(r.U<rows,lane(pendingK(3,0)),0.U)
  }
  for(c<-0 until 256){p.b(c):=Mux(c.U<columns(pendingContext),wRead(c/16)(16*(c%16)+15,16*(c%16)),0.U)}
  when(pending&&status===0.U){assert(operands.io.enq.ready,"reserved operand credit lost")}
  io.matrix.step.valid:=state===execute&&operands.io.deq.valid&&status===0.U
  io.matrix.step.bits:=operands.io.deq.bits.step
  operands.io.deq.ready:=Mux(status=/=0.U,true.B,io.matrix.step.ready&&state===execute)
  when(state===execute&&groupStarted && !allIssued&& !canRead&&status===0.U){starved:=starved+1.U}
  when(readFire){
    when(issueContext+1.U===contexts){
      issueContext:=0.U;issueK:=issueK+1.U
      when(issueK(3,0)===15.U || issueK+1.U===job.k){ready(issueSel):=false.B;issueSel:= !issueSel}
      when(issueK+1.U===job.k){allIssued:=true.B}
    }.otherwise{issueContext:=issueContext+1.U}
  }
  when(io.matrix.step.fire){
    useful:=useful+rows*columns(io.matrix.step.bits.context);issued:=issued+1.U
  }

  io.matrix.result.ready:=state===execute&&(status=/=0.U || writeState===writeIdle)
  when(io.matrix.result.fire && status===0.U){
    val r=io.matrix.result.bits
    val finite=(0 until 16).flatMap(i=>(0 until 256).map(j=>i.U>=rows||j.U>=columns(r.context)||TensorMath.finite(r.value(i)(j)))).reduce(_&&_)
    when(r.error || !r.last || r.context>=contexts || r.context=/=written){fail(Status.Protocol.U)}
    .elsewhen(!finite){fail(Status.Numerical.U)}
    .otherwise{finalValue:=r.value;writeContext:=r.context;writeRow:=0.U;writeBeat:=0.U;writeState:=writeReq}
  }
  io.memory.valid:=state===execute&&writeState===writeReq&&status===0.U
  io.memory.bits.write:=true.B
  io.memory.bits.address:=job.dst+(((rowBase.pad(64)+writeRow)*job.n+nBase+(writeContext.pad(64)<<8)+(writeBeat.pad(64)<<4))<<2)
  io.memory.bits.data:=VecInit((0 until 16).map(i=>finalValue(writeRow)(Cat(writeBeat(3,0),i.U(4.W))))).asUInt
  io.memory.bits.mask:=Fill(64,1.U(1.W));io.memory.bits.tag:=writeTag
  io.response.ready:=state===execute&&writeState===writeWait
  when(io.memory.fire){writeState:=writeWait}
  when(io.response.fire){
    when(io.response.bits.error){fail(Status.Memory.U);writeState:=writeIdle}
    .elsewhen(io.response.bits.tag=/=writeTag){fail(Status.Protocol.U);writeState:=writeIdle}
    .otherwise{
      bytes:=bytes+64.U;writeSequence:=writeSequence+1.U
      when(writeBeat+1.U===(columns(writeContext)>>4)){
        writeBeat:=0.U
        when(writeRow+1.U===rows){written:=written+1.U;writeState:=writeIdle}
        .otherwise{writeRow:=writeRow+1.U;writeState:=writeReq}
      }.otherwise{writeBeat:=writeBeat+1.U;writeState:=writeReq}
    }
  }

  when(state=/=idle&&state=/=finish&&state=/=locked){cycles:=cycles+1.U}
  when(io.job.fire){
    val j=io.job.bits;job:=j;status:=0.U;cycles:=0.U;useful:=0.U;bytes:=0.U;physicalBase:=io.physicalSteps
    rowBase:=0.U;nBase:=0.U;aRow:=0.U;aBeat:=0.U;sequence:=0.U;writeSequence:=0.U;issued:=0.U;starved:=0.U
    rows:=Mux(j.m>16.U,16.U,j.m)
    val aEnd=j.a.pad(66)+((j.m.pad(66)*j.k)<<2);val bEnd=j.b.pad(66)+((j.k.pad(66)*j.n)<<2)
    val cEnd=j.dst.pad(66)+((j.m.pad(66)*j.n)<<2)
    val aligned=Seq(j.a,j.b,j.dst).map(_(5,0)===0.U).reduce(_&&_)
    val aliases=(j.a.pad(66)<cEnd && j.dst.pad(66)<aEnd)||(j.b.pad(66)<cEnd && j.dst.pad(66)<bEnd)
    when(j.kind=/=QwenOwnerKind.Dense.U||j.m===0.U||j.n===0.U||j.k===0.U||j.k>maxK.U||j.k(3,0)=/=0.U||j.n(3,0)=/=0.U||
      !aligned||aliases||Seq(aEnd,bEnd,cEnd).map(_>(BigInt(1)<<56).U).reduce(_||_)||j.writeBytes=/=((j.m.pad(64)*j.n)<<2)){
      status:=Status.Bounds.U;state:=finish
    }.otherwise{state:=aReq}
  }
  when(io.burst.fire){burstCount:=io.burst.bits.beats;burstIndex:=0.U;burstTag:=io.burst.bits.tag;sequence:=sequence+1.U
    when(loadingA){state:=aWait}.otherwise{loadState:=loadWait}
  }
  when(io.burstResponse.fire){
    val r=io.burstResponse.bits;val last=burstIndex+1.U===burstCount
    val words=r.data.asTypeOf(Vec(16,UInt(32.W)))
    val finite=words.map(TensorMath.finite).reduce(_&&_)
    val packed=VecInit(words.map(TensorMath.bf16Rne)).asUInt
    val bad=r.error||r.tag=/=burstTag||r.last=/=last|| !finite
    when(bad){fail(Mux(r.error,Status.Memory.U,Mux(!finite,Status.Numerical.U,Status.Protocol.U)))}
    when(status===0.U && !bad){
      when(state===aWait){for(i<-0 until 16){when(aRow===i.U){aBanks(i).write(aBeat+burstIndex,packed)}}}
      .otherwise{for(i<-0 until 16){when(loadBeat+burstIndex===i.U){wBanks(i).write(Mux(loadSel,80.U,0.U)+loadDepth*5.U+loadContext,packed)}}}
    }
    burstIndex:=burstIndex+1.U
    when(last){
      when(state===aWait){
        when(bad||status=/=0.U){state:=finish}
        .elsewhen(aBeat+burstCount===(job.k>>4)){
          aBeat:=0.U
          when(aRow+1.U===rows){state:=setup}.otherwise{aRow:=aRow+1.U;state:=aReq}
        }.otherwise{aBeat:=aBeat+burstCount;state:=aReq}
      }.otherwise{
        when(bad||status=/=0.U){loadState:=loadIdle}
        .elsewhen(loadBeat+burstCount===(columns(loadContext)>>4)){
          loadBeat:=0.U
          when(loadContext+1.U===contexts){
            loadContext:=0.U
            when(loadDepth===15.U || loadK+loadDepth+1.U===job.k){
              ready(loadSel):=true.B;readyK(loadSel):=loadK;nextLoadK:=loadK+16.U;loadSel:= !loadSel;loadState:=loadIdle
            }.otherwise{loadDepth:=loadDepth+1.U;loadState:=loadReq}
          }.otherwise{loadContext:=loadContext+1.U;loadState:=loadReq}
        }.otherwise{loadBeat:=loadBeat+burstCount;loadState:=loadReq}
      }
    }
  }
  when(state===setup){
    val fullTiles=(job.n-nBase)>>8
    // A partial-width last tile gets its own group and slice mask. Otherwise
    // masked columns would inflate executed-MAC accounting for earlier tiles.
    contexts:=Mux(fullTiles===0.U,1.U,Mux(fullTiles>5.U,5.U,fullTiles))
    ready:=VecInit(Seq.fill(2)(false.B));loadSel:=false.B;nextLoadK:=0.U;loadState:=loadIdle
    issueSel:=false.B;issueK:=0.U;issueContext:=0.U;allIssued:=false.B
    groupStarted:=false.B;groupDone:=false.B;written:=0.U;writeState:=writeIdle;state:=execute
  }
  when(io.matrix.group.fire){groupStarted:=true.B}
  when(io.matrix.done.fire){groupDone:=true.B;when(io.matrix.done.bits.error||io.matrix.done.bits.tag=/=job.tag){fail(Status.Protocol.U)}}
  when(state===execute&&status===0.U&&loadState===loadIdle&&nextLoadK<job.k && !ready(loadSel)){
    loadK:=nextLoadK;loadDepth:=0.U;loadContext:=0.U;loadBeat:=0.U;loadState:=loadReq
  }
  when(state===execute&&status===0.U&&groupDone&&written===contexts&&writeState===writeIdle){
    when(nBase+(contexts.pad(16)<<8)>=job.n){
      when(rowBase+rows>=job.m){state:=finish}
      .otherwise{rowBase:=rowBase+rows;rows:=Mux(job.m-rowBase-rows>16.U,16.U,job.m-rowBase-rows);nBase:=0.U;aRow:=0.U;aBeat:=0.U;state:=aReq}
    }.otherwise{nBase:=nBase+(contexts.pad(16)<<8);state:=setup}
  }
  when(state===execute&&status=/=0.U){
    when(writeState===writeReq){writeState:=writeIdle}
    when(loadState===loadReq){loadState:=loadIdle}
    when((!groupStarted||groupDone)&&loadState=/=loadWait&&writeState=/=writeWait && !pending && !operands.io.deq.valid){state:=finish}
  }
  when(io.done.fire){state:=Mux(status===0.U,idle,locked)}
}

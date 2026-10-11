// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Full-A, Dense-only alternative to StreamingDenseOwner. It owns the same
  * decoded job, real-iDMA read, destination-ACK and retained-Matrix interfaces.
  * M16/M128, K<=1536 and N32 tiles are deliberately the first admission gate.
  * The owner and DMA/Matrix must share a COORDINATED reset/quiescence domain.
  * Sequence counters are transaction IDs, never proof of freshness after an
  * independently reset owner. There is no runtime local-reset/retry interface.
  */
class TransposedDenseOwner(burstWrites:Boolean=false) extends Module {
  val io=IO(new DenseOwnerIO(burstWrites,transposed=true))
  val idle::clearA::aReq::aWait::aFence::setup::execute::drain::finish::locked::Nil=Enum(10)
  val state=RegInit(idle);val job=Reg(new QwenOwnerJob)
  val status=RegInit(0.U(8.W));val cycles=RegInit(0.U(64.W));val bytes=RegInit(0.U(64.W))
  val useful=RegInit(0.U(64.W));val physicalBase=RegInit(0.U(64.W))
  val issued=RegInit(0.U(64.W));val starved=RegInit(0.U(64.W))
  val aCommitted=RegInit(false.B);val aGeneration=RegInit(0.U(32.W))
  val zeroWord=RegInit(0.U(11.W));val aRow=RegInit(0.U(7.W));val aBeat=RegInit(0.U(7.W))
  // The lower 256 bits live in the banks' RMW stage. Only native BF16 needs
  // this additional upper 256-bit hold, and it uses the same physical ports.
  val aHighPending=RegInit(false.B);val aHigh=Reg(UInt(256.W))
  val aHighRow=Reg(UInt(7.W));val aHighKWord=Reg(UInt(7.W))
  val sequence=RegInit(0.U(32.W));val burstTag=Reg(UInt(64.W))
  val burstOutstanding=RegInit(false.B);val burstIsA=Reg(Bool());val received=RegInit(0.U(8.W))
  val nBase=RegInit(0.U(16.W));val contexts=Reg(UInt(3.W))
  val halfReady=RegInit(VecInit(Seq.fill(2)(false.B)))
  val halfK=Reg(Vec(2,UInt(11.W)));val halfN=Reg(Vec(2,UInt(16.W)))
  val loadIdle::loadReq::loadWait::Nil=Enum(3)
  val loadState=RegInit(loadIdle);val loadHalf=RegInit(false.B)
  val nextLoadK=RegInit(0.U(12.W));val loadK=Reg(UInt(11.W))
  val loadDepth=RegInit(0.U(7.W));val loadContext=RegInit(0.U(3.W));val loadBeat=RegInit(false.B)
  val issueHalf=RegInit(false.B);val readK=RegInit(0.U(11.W));val readContext=RegInit(0.U(3.W))
  val allRead=RegInit(false.B);val groupStarted=RegInit(false.B);val groupDone=RegInit(false.B)
  val groupIssueBase=RegInit(0.U(64.W));val terminalIssued=RegInit(0.U(5.W));val captured=RegInit(0.U(3.W))
  val writeIdle::writeReq::writeData::writeWait::Nil=Enum(4)
  val writeState=RegInit(writeIdle);val written=RegInit(0.U(3.W));val writeContext=Reg(UInt(3.W))
  val writeRow=RegInit(0.U(7.W));val writeBeat=RegInit(false.B)
  val writeCount=Reg(UInt(5.W));val writeIndex=RegInit(0.U(5.W))
  val writeSequence=RegInit(0.U(32.W));val writeTag=Reg(UInt(64.W))
  val finalValue=Reg(Vec(16,Vec(256,UInt(32.W))))
  def fail(code:UInt):Unit={when(status===0.U){status:=code}}
  val banks=Module(new TransposedDenseBanks)
  banks.io.zero.valid:=state===clearA; banks.io.zero.bits:=zeroWord
  banks.io.weight.valid:=false.B; banks.io.weight.bits:=0.U.asTypeOf(new TransposedWeightLoad)
  banks.io.activation.valid:=false.B; banks.io.activation.bits:=0.U.asTypeOf(new TransposedActivationLoad)

  val activationBytes=Mux(job.activationBf16,2.U(3.W),4.U(3.W))
  val activationBeats=Mux(job.activationBf16,job.k>>5,job.k>>4)
  val weightBytes=Mux(job.weightBf16,2.U(3.W),4.U(3.W))
  val outputBytes=Mux(job.outputBf16,2.U(3.W),4.U(3.W))
  val outputBeats=Mux(job.outputBf16,1.U(2.W),2.U(2.W))
  val aAddress=job.a+aRow.pad(64)*job.k*activationBytes+(aBeat.pad(64)<<6)
  val wAddress=job.b+((loadK.pad(64)+loadDepth)*job.n+nBase+(loadContext.pad(64)<<5)+
    Mux(loadBeat,16.U(64.W),0.U(64.W)))*weightBytes
  // One-beat descriptors are intentionally conservative. The ABI still uses
  // the real burst bridge and its validated LAST fence, with no simulated DMA.
  io.burst.valid:=status===0.U && !burstOutstanding &&
    ((state===aReq && !aHighPending && !banks.io.activationBusy) || (state===execute && loadState===loadReq))
  io.burst.bits.address:=Mux(state===aReq,aAddress,wAddress)
  io.burst.bits.beats:=1.U;io.burst.bits.tag:=Cat(job.tag,sequence)
  io.burstResponse.ready:=burstOutstanding &&
    (status=/=0.U || !burstIsA || (!aHighPending && banks.io.activation.ready))
  val response=io.burstResponse.bits
  val sourceNative=Mux(burstIsA,job.activationBf16,job.weightBf16)
  val sourceWords=response.data.asTypeOf(Vec(16,UInt(32.W)))
  val sourceHalves=response.data.asTypeOf(Vec(32,UInt(16.W)))
  val converted=VecInit(sourceWords.map(TensorMath.bf16Rne))
  // Explicitly reject finite FP32 values whose unchanged RNE conversion
  // overflows to BF16 infinity (including +/-0x7f7f8000 ties). No valid finite
  // product or successful-output bit pattern changes; failure occurs earlier.
  val sourceFinite=Mux(sourceNative,sourceHalves.map(_(14,7)=/=255.U).reduce(_&&_),
    sourceWords.map(TensorMath.finite).reduce(_&&_) && converted.map(_(14,7)=/=255.U).reduce(_&&_))
  val packed=converted.asUInt
  val responseBad=response.error || response.tag=/=burstTag || !response.last || received=/=0.U || !sourceFinite
  val responseGood=io.burstResponse.valid && burstOutstanding && status===0.U && !responseBad
  when(aHighPending && status===0.U){
    banks.io.activation.valid:=true.B
    banks.io.activation.bits.m:=aHighRow;banks.io.activation.bits.kWord:=aHighKWord
    banks.io.activation.bits.value:=aHigh
    when(banks.io.activation.fire){aHighPending:=false.B}
  }.elsewhen(responseGood && burstIsA){
    banks.io.activation.valid:=true.B
    banks.io.activation.bits.m:=aRow
    banks.io.activation.bits.kWord:=Mux(job.activationBf16,aBeat<<1,aBeat)
    banks.io.activation.bits.value:=Mux(job.activationBf16,response.data(255,0),packed)
  }

  io.job.ready:=state===idle
  io.done.valid:=state===finish;io.done.bits.tag:=job.tag;io.done.bits.status:=status
  io.done.bits.writeBytes:=bytes;io.done.bits.cycles:=cycles;io.done.bits.usefulMacs:=useful
  io.done.bits.executedMacs:=(io.physicalSteps-physicalBase)*512.U
  io.resetRequired:=status=/=0.U;io.issueCycles:=issued;io.operandStalls:=starved
  io.matrix.group.valid:=state===execute && aCommitted && !groupStarted && status===0.U
  io.matrix.group.bits.opcode:=0x20.U;io.matrix.group.bits.sliceMask:=255.U
  io.matrix.group.bits.tag:=job.tag;io.matrix.group.bits.transposedDense.get:=true.B
  io.matrix.done.ready:=(state===execute || state===drain) && groupStarted && !groupDone
  io.matrix.abort:=(state===drain || status=/=0.U) && groupStarted && !groupDone

  val operands=Module(new Queue(new MatrixStreamStep,4,pipe=true))
  val pendingK=Reg(UInt(11.W));val pendingContext=Reg(UInt(3.W))
  val eligibleHalf=halfReady(issueHalf) && halfK(issueHalf)===(readK & "h780".U) && halfN(issueHalf)===nBase
  banks.io.read.valid:=state===execute && aCommitted && groupStarted && !groupDone && !allRead && status===0.U &&
    eligibleHalf && operands.io.count+&banks.io.response.valid.asUInt<4.U
  banks.io.read.bits.k:=readK;banks.io.read.bits.context:=readContext;banks.io.read.bits.half:=issueHalf
  when(banks.io.read.fire){pendingK:=readK;pendingContext:=readContext}
  operands.io.enq.valid:=banks.io.response.valid && status===0.U
  val step=operands.io.enq.bits
  step.context:=pendingContext;step.clear:=pendingK===0.U;step.last:=pendingK+1.U===job.k
  step.finish:=step.last && pendingContext+1.U===contexts;step.emit:=step.last
  for(n<-0 until 16){step.a(n):=banks.io.response.bits.weight(n)}
  for(m<-0 until 256){
    if(m<128){step.b(m):=Mux(m.U<job.m,banks.io.response.bits.activation(m),0.U)}
    else if(m<144){step.b(m):=banks.io.response.bits.weight(m-112)}
    else{step.b(m):=0.U}
  }
  when(banks.io.response.valid && status===0.U){assert(operands.io.enq.ready,"reserved synchronous-read credit lost")}
  io.matrix.step.valid:=state===execute && operands.io.deq.valid && status===0.U
  io.matrix.step.bits:=operands.io.deq.bits
  operands.io.deq.ready:=Mux(status=/=0.U,true.B,state===execute && io.matrix.step.ready)
  when(banks.io.read.fire){
    when(readContext+1.U===contexts){
      readContext:=0.U;readK:=readK+1.U
      when(readK(6,0)===127.U || readK+1.U===job.k){halfReady(issueHalf):=false.B;issueHalf:= !issueHalf}
      when(readK+1.U===job.k){allRead:=true.B}
    }.otherwise{readContext:=readContext+1.U}
  }
  when(io.matrix.step.fire){
    issued:=issued+1.U;useful:=useful+job.m.pad(64)*32.U
    when(io.matrix.step.bits.last){terminalIssued:=terminalIssued|UIntToOH(io.matrix.step.bits.context,5)}
  }
  when(state===execute && groupStarted && !allRead && !banks.io.read.fire && status===0.U){starved:=starved+1.U}

  // Drain each terminal context while the service is still running. Waiting
  // for done before reading results deadlocks five contexts against 2+1 slots.
  io.matrix.result.ready:=(state===execute || state===drain) && (status=/=0.U || writeState===writeIdle)
  when(io.matrix.result.fire && status===0.U){
    val r=io.matrix.result.bits
    val finite=(0 until 16).flatMap(n=>(0 until 256).map(col=>
      (col%128).U>=job.m || (TensorMath.finite(r.value(n)(col)) &&
        (!job.outputBf16 || r.value(n)(col)(30,0)<"h7f7f8000".U(31.W))))).reduce(_&&_)
    when(r.error || !r.last || r.context>=contexts || r.context=/=written || !terminalIssued(r.context)){fail(Status.Protocol.U)}
    .elsewhen(!finite){fail(Status.Numerical.U)}
    .otherwise{finalValue:=r.value;captured:=captured+1.U;writeContext:=r.context;writeRow:=0.U;writeBeat:=false.B;writeState:=writeReq}
  }
  val outputAddress=job.dst+(writeRow.pad(64)*job.n+nBase+(writeContext.pad(64)<<5)+
    Mux(writeBeat,16.U(64.W),0.U(64.W)))*outputBytes
  def outputPacket(beat:UInt):UInt={
    // Y[m,n] = physical[n%16][32*(4*(n/16)+m/32)+m%32].
    val fp32=VecInit((0 until 16).map(n=>finalValue(n)(Cat(beat(0),writeRow)))).asUInt
    val bf16=VecInit((0 until 32).map(n=>TensorMath.bf16Rne(finalValue(n%16)(Cat((n/16).U(1.W),writeRow))))).asUInt
    Mux(job.outputBf16,bf16,fp32)
  }
  val writeActive=state===execute || state===drain
  val ackFire=WireDefault(false.B);val ackBits=WireDefault(0.U.asTypeOf(new MemoryResponse))
  val ackBeats=WireDefault(1.U(5.W))
  io.memory.valid:=false.B;io.memory.bits:=0.U.asTypeOf(new MemoryRequest);io.response.ready:=false.B
  if(burstWrites){
    val port=io.writeRequest.get
    val remaining=outputBeats-writeBeat.asUInt
    val page=16.U(5.W)-outputAddress(9,6)
    port.valid:=state===execute && writeState===writeReq && status===0.U
    port.bits.address:=outputAddress;port.bits.beats:=Mux(remaining<page,remaining,page)
    port.bits.tag:=Cat(job.tag,writeSequence)
    io.writeData.get.valid:=writeActive && writeState===writeData
    io.writeData.get.bits.data:=outputPacket(writeBeat.asUInt+writeIndex)
    io.writeData.get.bits.last:=writeIndex+1.U===writeCount
    io.writeResponse.get.ready:=writeActive && writeState===writeWait
    when(port.fire){writeTag:=port.bits.tag;writeCount:=port.bits.beats;writeIndex:=0.U;writeState:=writeData}
    when(io.writeData.get.fire){writeIndex:=writeIndex+1.U;when(writeIndex+1.U===writeCount){writeState:=writeWait}}
    ackFire:=io.writeResponse.get.fire;ackBits:=io.writeResponse.get.bits;ackBeats:=writeCount
  }else{
    io.memory.valid:=state===execute && writeState===writeReq && status===0.U
    io.memory.bits.write:=true.B;io.memory.bits.address:=outputAddress
    io.memory.bits.data:=outputPacket(writeBeat.asUInt);io.memory.bits.mask:=Fill(64,1.U(1.W))
    io.memory.bits.tag:=Cat(job.tag,writeSequence)
    io.response.ready:=writeActive && writeState===writeWait
    when(io.memory.fire){writeTag:=io.memory.bits.tag;writeState:=writeWait}
    ackFire:=io.response.fire;ackBits:=io.response.bits
  }
  when(ackFire){
    when(ackBits.error || ackBits.tag=/=writeTag){
      fail(Mux(ackBits.error,Status.Memory.U,Status.Protocol.U));writeState:=writeIdle
    }.otherwise{
      bytes:=bytes+(ackBeats.pad(64)<<6);writeSequence:=writeSequence+1.U
      when(status=/=0.U){writeState:=writeIdle}
      .elsewhen(writeBeat.asUInt+&ackBeats===outputBeats){
        writeBeat:=false.B
        when(writeRow+&1.U===job.m){written:=written+1.U;writeState:=writeIdle}
        .otherwise{writeRow:=writeRow+1.U;writeState:=writeReq}
      }.otherwise{writeBeat:=true.B;writeState:=writeReq}
    }
  }

  val cycleBuckets=RegInit(VecInit(Seq.fill(7)(0.U(64.W))))
  val cycleClass=WireDefault(0.U(3.W))
  when(state===clearA || state===aReq || state===aWait || state===aFence){cycleClass:=1.U}
  .elsewhen(state===setup){cycleClass:=2.U}
  .elsewhen(state===execute){
    when(io.matrix.step.fire){cycleClass:=3.U}
    .elsewhen(writeState=/=writeIdle){cycleClass:=4.U}
    .elsewhen(!allRead && !eligibleHalf){cycleClass:=5.U}
    .elsewhen(operands.io.deq.valid && !io.matrix.step.ready){cycleClass:=6.U}
  }
  when(state=/=idle && state=/=finish && state=/=locked){cycles:=cycles+1.U;cycleBuckets(cycleClass):=cycleBuckets(cycleClass)+1.U}
  io.profile.other:=cycleBuckets(0);io.profile.activationFetch:=cycleBuckets(1);io.profile.setup:=cycleBuckets(2)
  io.profile.issue:=cycleBuckets(3);io.profile.writeback:=cycleBuckets(4);io.profile.weightWait:=cycleBuckets(5)
  io.profile.matrixBackpressure:=cycleBuckets(6)
  when(io.done.valid){assert(cycleBuckets.reduce(_+&_)===cycles)}

  when(io.job.fire){
    val j=io.job.bits;job:=j;status:=0.U;cycles:=0.U;bytes:=0.U;useful:=0.U;issued:=0.U;starved:=0.U
    cycleBuckets:=VecInit(Seq.fill(7)(0.U(64.W)));physicalBase:=io.physicalSteps
    aCommitted:=false.B;zeroWord:=0.U;aRow:=0.U;aBeat:=0.U;aHighPending:=false.B;nBase:=0.U
    val aEnd=j.a.pad(66)+j.m.pad(66)*j.k*Mux(j.activationBf16,2.U(3.W),4.U(3.W))
    val bEnd=j.b.pad(66)+j.k.pad(66)*j.n*Mux(j.weightBf16,2.U(3.W),4.U(3.W))
    val dEnd=j.dst.pad(66)+j.m.pad(66)*j.n*Mux(j.outputBf16,2.U(3.W),4.U(3.W))
    val aliases=(j.a.pad(66)<dEnd && j.dst.pad(66)<aEnd)||(j.b.pad(66)<dEnd && j.dst.pad(66)<bEnd)
    val aligned=Seq(j.a,j.b,j.dst).map(_(5,0)===0.U).reduce(_&&_)
    when(j.kind=/=QwenOwnerKind.Dense.U || !(j.m===16.U || j.m===128.U) || j.k===0.U || j.k>1536.U ||
      j.k(3,0)=/=0.U || (j.activationBf16 && j.k(4,0)=/=0.U) || j.n===0.U || j.n(4,0)=/=0.U ||
      !aligned || aliases || Seq(aEnd,bEnd,dEnd).map(_>(BigInt(1)<<56).U).reduce(_||_) ||
      j.writeBytes=/=j.m.pad(64)*j.n*Mux(j.outputBf16,2.U(3.W),4.U(3.W))){
      status:=Status.Bounds.U;state:=finish
    }.otherwise{state:=clearA}
  }
  when(state===clearA){
    when(zeroWord+1.U===(job.k>>4)*8.U){state:=aReq}.otherwise{zeroWord:=zeroWord+1.U}
  }
  when(io.burst.fire){
    assert(io.burst.bits.address(5,0)===0.U && io.burst.bits.beats===1.U)
    burstOutstanding:=true.B;burstTag:=io.burst.bits.tag;sequence:=sequence+1.U;received:=0.U
    burstIsA:=state===aReq
    when(state===aReq){state:=aWait}.otherwise{loadState:=loadWait}
  }
  when(io.burstResponse.fire){
    received:=received+1.U
    when(responseBad){fail(Mux(response.error,Status.Memory.U,Mux(!sourceFinite,Status.Numerical.U,Status.Protocol.U)))}
    when(!responseBad && status===0.U){
      when(burstIsA){
        assert(banks.io.activation.fire)
        when(job.activationBf16){
          aHighPending:=true.B;aHigh:=response.data(511,256);aHighRow:=aRow;aHighKWord:=(aBeat<<1)+1.U
        }
      }.otherwise{
        banks.io.weight.valid:=true.B;banks.io.weight.bits.half:=loadHalf
        banks.io.weight.bits.depth:=loadDepth;banks.io.weight.bits.group16:=(loadContext<<1)+loadBeat.asUInt
        banks.io.weight.bits.pair:=job.weightBf16
        banks.io.weight.bits.value:=Mux(job.weightBf16,response.data,Cat(0.U(256.W),packed))
      }
    }
    // Preserve the original adapter's sole-outstanding physical-port contract:
    // drain the descriptor's EXPECTED beat count even when LAST/tag is bad.
    // This descriptor has exactly one beat. A malformed terminal poisons and
    // locks the owner; it never publishes data or waits for a second terminal
    // the controlled backend will not send. Cross-job stale returns must be
    // prevented by the coordinated adapter/reset domain, not local counters.
    when(received===0.U){
      burstOutstanding:=false.B
      when(burstIsA){
        when(!responseBad && status===0.U){
          when(aBeat+1.U===activationBeats){
            aBeat:=0.U
            when(aRow+&1.U===job.m){state:=aFence}.otherwise{aRow:=aRow+1.U;state:=aReq}
          }.otherwise{aBeat:=aBeat+1.U;state:=aReq}
        }
      }.otherwise{
        loadState:=loadIdle
        when(!responseBad && status===0.U){
          when(job.weightBf16 || loadBeat){
            loadBeat:=false.B
            when(loadContext+1.U===contexts){
              loadContext:=0.U
              when(loadDepth===127.U || loadK+&loadDepth+1.U===job.k){
                halfReady(loadHalf):=true.B;halfK(loadHalf):=loadK;halfN(loadHalf):=nBase
                nextLoadK:=loadK+&128.U;loadHalf:= !loadHalf
              }.otherwise{loadDepth:=loadDepth+1.U;loadState:=loadReq}
            }.otherwise{loadContext:=loadContext+1.U;loadState:=loadReq}
          }.otherwise{loadBeat:=true.B;loadState:=loadReq}
        }
      }
    }
  }
  when(state===aFence && !aHighPending && !banks.io.activationBusy && status===0.U){
    aCommitted:=true.B;aGeneration:=aGeneration+1.U;state:=setup
  }
  when(state===setup && status===0.U){
    contexts:=Mux((job.n-nBase)>>5>5.U,5.U,((job.n-nBase)>>5)(2,0))
    halfReady:=VecInit(Seq.fill(2)(false.B));loadHalf:=false.B;nextLoadK:=0.U;loadState:=loadIdle
    issueHalf:=false.B;readK:=0.U;readContext:=0.U;allRead:=false.B
    groupStarted:=false.B;groupDone:=false.B;written:=0.U;writeState:=writeIdle;state:=execute
    groupIssueBase:=issued;terminalIssued:=0.U;captured:=0.U
  }
  when(state===execute && status===0.U && loadState===loadIdle && nextLoadK<job.k && !halfReady(loadHalf)){
    loadK:=nextLoadK;loadDepth:=0.U;loadContext:=0.U;loadBeat:=false.B;loadState:=loadReq
  }
  when(io.matrix.group.fire){groupStarted:=true.B}
  when(io.matrix.done.fire){
    groupDone:=true.B
    when(io.matrix.done.bits.error || io.matrix.done.bits.tag=/=job.tag || !allRead || banks.io.response.valid ||
      operands.io.deq.valid || captured=/=contexts || issued-groupIssueBase=/=job.k.pad(64)*contexts){fail(Status.Protocol.U)}
  }
  val operandsEmpty= !banks.io.response.valid && !operands.io.deq.valid
  when(state===execute && status===0.U && groupDone && written===contexts && writeState===writeIdle &&
    allRead && operandsEmpty && !burstOutstanding && loadState===loadIdle){
    when(nBase+(contexts.pad(17)<<5)>=job.n){
      when(bytes=/=job.writeBytes){fail(Status.Protocol.U)}.otherwise{state:=finish}
    }.otherwise{nBase:=nBase+(contexts.pad(16)<<5);state:=setup}
  }
  when(status=/=0.U && state=/=idle && state=/=finish && state=/=locked){
    state:=drain;aCommitted:=false.B;halfReady:=VecInit(Seq.fill(2)(false.B));aHighPending:=false.B
    when(loadState===loadReq){loadState:=loadIdle}
    when(writeState===writeReq){writeState:=writeIdle}
    when(!burstOutstanding && (!groupStarted || groupDone) && writeState=/=writeWait && writeState=/=writeData &&
      !banks.io.activationBusy && operandsEmpty){state:=finish}
  }
  when(io.done.fire){state:=Mux(status===0.U,idle,locked)}
}

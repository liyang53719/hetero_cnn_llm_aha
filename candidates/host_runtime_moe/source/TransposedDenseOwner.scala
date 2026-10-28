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

/** Candidate-only internal reservation. It is deliberately not inferred from
  * job.c or a fixed DDR address. Production Host allocation/binding stays open.
  * Admission snapshots this lease; generations do not prove reset freshness.
  */
class TransposedPrefixWorkspace(maxLocalK:Int=1536) extends Bundle {
  val valid=Bool();val base=UInt(64.W);val extent=UInt(64.W)
  val generation=UInt(32.W);val splitK=UInt((if(maxLocalK>1536)12 else 11).W)
}

/** Default-off selected extension of the actual transposed owner. Exactly one
  * owner is instantiated. Prefix save uses its existing finalValue storage;
  * restore streams one raw FP32 DDR beat to the same retained five banks.
  */
class TransposedDenseSeedOwner(burstWrites:Boolean=false) extends Module {
  val io=IO(new DenseOwnerIO(burstWrites,transposed=true,enableAccumulatorSeed=true))
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
  val workspace=Reg(new TransposedPrefixWorkspace)
  val restoring=RegInit(false.B);val prefixValid=RegInit(false.B)
  val prefixAckBytes=RegInit(0.U(64.W));val prefixWriteIndex=RegInit(0.U(8.W))
  val groupSequence=RegInit(0.U(32.W))
  val seedIdle::seedBegin::seedRead::seedWait::seedSend::seedAck::Nil=Enum(6)
  val seedState=RegInit(seedIdle);val seedContext=RegInit(0.U(3.W));val seedIndex=RegInit(0.U(8.W))
  val seedHold=Reg(UInt(512.W));val burstIsPrefix=RegInit(false.B)
  val chunkStart=Mux(restoring,workspace.splitK,0.U(11.W))
  val chunkEnd=Mux(restoring,job.k,workspace.splitK)
  val seedFinished=seedState===seedIdle
  val seed=io.matrix.seed.get
  seed.begin.valid:=state===execute && groupStarted && restoring && prefixValid && seedState===seedBegin && status===0.U
  seed.begin.bits.groupTag:=job.tag;seed.begin.bits.groupSequence:=groupSequence
  seed.begin.bits.sourceGeneration:=workspace.generation;seed.begin.bits.context:=seedContext;seed.begin.bits.sliceMask:=255.U
  seed.beat.valid:=state===execute && seedState===seedSend && status===0.U
  seed.beat.bits.groupTag:=job.tag;seed.beat.bits.groupSequence:=groupSequence
  seed.beat.bits.sourceGeneration:=workspace.generation;seed.beat.bits.context:=seedContext
  seed.beat.bits.index:=seedIndex;seed.beat.bits.data:=seedHold;seed.beat.bits.last:=seedIndex===255.U;seed.beat.bits.error:=false.B
  seed.ack.ready:=state===drain || (state===execute && seedState===seedAck)
  when(seed.begin.fire){seedState:=seedRead}
  when(seed.beat.fire){
    when(seedIndex===255.U){seedState:=seedAck}.otherwise{seedIndex:=seedIndex+1.U;seedState:=seedRead}
  }
  when(seed.ack.fire){
    val a=seed.ack.bits
    when(a.error || a.groupTag=/=job.tag || a.groupSequence=/=groupSequence ||
      a.sourceGeneration=/=workspace.generation || a.context=/=seedContext){fail(Status.Protocol.U)}
    .elsewhen(status===0.U && state===execute){
      seedIndex:=0.U;seedContext:=seedContext+1.U
      seedState:=Mux(seedContext+1.U===contexts,seedIdle,seedBegin)
    }
  }
  when(seed.ack.valid && !seed.ack.ready && seedState=/=seedAck){fail(Status.Protocol.U)}
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
  val prefixReadAddress=workspace.base+((nBase.pad(64)>>5)+seedContext)*16384.U+
    (((seedIndex(4,1).pad(64)<<4)+(seedIndex(7,5).pad(64)<<1)+seedIndex(0).asUInt)<<6)
  val readingPrefix=state===execute && restoring && prefixValid && groupStarted && seedState===seedRead
  io.burst.valid:=status===0.U && !burstOutstanding &&
    ((state===aReq && !aHighPending && !banks.io.activationBusy) || (state===execute && seedFinished && loadState===loadReq) || readingPrefix)
  io.burst.bits.address:=Mux(state===aReq,aAddress,Mux(readingPrefix,prefixReadAddress,wAddress))
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
  val sourceFinite=Mux(burstIsPrefix,sourceWords.map(TensorMath.finite).reduce(_&&_),Mux(sourceNative,sourceHalves.map(_(14,7)=/=255.U).reduce(_&&_),
    sourceWords.map(TensorMath.finite).reduce(_&&_) && converted.map(_(14,7)=/=255.U).reduce(_&&_)))
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
  io.matrix.group.bits.groupSequence.get:=groupSequence
  io.matrix.group.bits.tag:=job.tag;io.matrix.group.bits.transposedDense.get:=true.B
  io.matrix.done.ready:=(state===execute || state===drain) && groupStarted && !groupDone
  io.matrix.abort:=(state===drain || status=/=0.U) && groupStarted && !groupDone

  val operands=Module(new Queue(new MatrixStreamStep,4,pipe=true))
  val pendingK=Reg(UInt(11.W));val pendingContext=Reg(UInt(3.W))
  val eligibleHalf=halfReady(issueHalf) && halfK(issueHalf)===(readK & "h780".U) && halfN(issueHalf)===nBase
  banks.io.read.valid:=state===execute && aCommitted && groupStarted && !groupDone && !allRead && seedFinished && status===0.U &&
    eligibleHalf && operands.io.count+&banks.io.response.valid.asUInt<4.U
  banks.io.read.bits.k:=readK;banks.io.read.bits.context:=readContext;banks.io.read.bits.half:=issueHalf
  when(banks.io.read.fire){pendingK:=readK;pendingContext:=readContext}
  operands.io.enq.valid:=banks.io.response.valid && status===0.U
  val step=operands.io.enq.bits
  step.context:=pendingContext;step.clear:=pendingK===0.U;step.last:=pendingK+1.U===chunkEnd
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
      when(readK(6,0)===127.U || readK+1.U===chunkEnd){halfReady(issueHalf):=false.B;issueHalf:= !issueHalf}
      when(readK+1.U===chunkEnd){allRead:=true.B}
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
      (restoring && (col%128).U>=job.m) || (TensorMath.finite(r.value(n)(col)) &&
        (!restoring || !job.outputBf16 || r.value(n)(col)(30,0)<"h7f7f8000".U(31.W))))).reduce(_&&_)
    when(r.error || !r.last || r.context>=contexts || r.context=/=written || !terminalIssued(r.context)){fail(Status.Protocol.U)}
    .elsewhen(!finite){fail(Status.Numerical.U)}
    .otherwise{finalValue:=r.value;captured:=captured+1.U;writeContext:=r.context;prefixWriteIndex:=0.U;writeRow:=0.U;writeBeat:=false.B;writeState:=writeReq}
  }
  val finalOutputAddress=job.dst+(writeRow.pad(64)*job.n+nBase+(writeContext.pad(64)<<5)+
    Mux(writeBeat,16.U(64.W),0.U(64.W)))*outputBytes
  val prefixOutputAddress=workspace.base+((nBase.pad(64)>>5)+writeContext)*16384.U+(prefixWriteIndex.pad(64)<<6)
  val outputAddress=Mux(restoring,finalOutputAddress,prefixOutputAddress)
  def outputPacket(beat:UInt):UInt={
    // Y[m,n] = physical[n%16][32*(4*(n/16)+m/32)+m%32].
    val fp32=VecInit((0 until 16).map(n=>finalValue(n)(Cat(beat(0),writeRow)))).asUInt
    val bf16=VecInit((0 until 32).map(n=>TensorMath.bf16Rne(finalValue(n%16)(Cat((n/16).U(1.W),writeRow))))).asUInt
    val prefix=VecInit((0 until 16).map(i=>finalValue(prefixWriteIndex(7,4))(Cat(prefixWriteIndex(3,0),i.U(4.W))))).asUInt
    Mux(restoring,Mux(job.outputBf16,bf16,fp32),prefix)
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
    port.bits.address:=outputAddress;port.bits.beats:=Mux(restoring,Mux(remaining<page,remaining,page),1.U)
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
      when(restoring){bytes:=bytes+(ackBeats.pad(64)<<6)}.otherwise{prefixAckBytes:=prefixAckBytes+64.U}
      writeSequence:=writeSequence+1.U
      when(status=/=0.U){writeState:=writeIdle}
      .elsewhen(!restoring){
        when(prefixWriteIndex===255.U){written:=written+1.U;writeState:=writeIdle}
        .otherwise{prefixWriteIndex:=prefixWriteIndex+1.U;writeState:=writeReq}
      }
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
    val j=io.job.bits;val w=io.prefixWorkspace.get;workspace:=w
    restoring:=false.B;prefixValid:=false.B;prefixAckBytes:=0.U;seedState:=seedIdle
    job:=j;status:=0.U;cycles:=0.U;bytes:=0.U;useful:=0.U;issued:=0.U;starved:=0.U
    cycleBuckets:=VecInit(Seq.fill(7)(0.U(64.W)));physicalBase:=io.physicalSteps
    aCommitted:=false.B;zeroWord:=0.U;aRow:=0.U;aBeat:=0.U;aHighPending:=false.B;nBase:=0.U
    val aEnd=j.a.pad(66)+j.m.pad(66)*j.k*Mux(j.activationBf16,2.U(3.W),4.U(3.W))
    val bEnd=j.b.pad(66)+j.k.pad(66)*j.n*Mux(j.weightBf16,2.U(3.W),4.U(3.W))
    val dEnd=j.dst.pad(66)+j.m.pad(66)*j.n*Mux(j.outputBf16,2.U(3.W),4.U(3.W))
    val aliases=(j.a.pad(66)<dEnd && j.dst.pad(66)<aEnd)||(j.b.pad(66)<dEnd && j.dst.pad(66)<bEnd)
    val aligned=Seq(j.a,j.b,j.dst).map(_(5,0)===0.U).reduce(_&&_)
    val pEnd=w.base.pad(66)+w.extent.pad(66)
    val prefixAliases=Seq((j.a,aEnd),(j.b,bEnd),(j.dst,dEnd)).map{case(base,end)=>
      w.base.pad(66)<end && base.pad(66)<pEnd}.reduce(_||_)
    when(!w.valid || w.base(5,0)=/=0.U || w.extent<(j.n.pad(64)>>5)*16384.U ||
      pEnd>(BigInt(1)<<56).U || prefixAliases || w.generation===0.U || w.splitK===0.U ||
      w.splitK>=j.k || w.splitK(6,0)=/=0.U || groupSequence==="hffffffff".U ||
      j.kind=/=QwenOwnerKind.Dense.U || !(j.m===16.U || j.m===128.U) || j.k===0.U || j.k>1536.U ||
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
    burstIsA:=state===aReq;burstIsPrefix:=readingPrefix
    when(state===aReq){state:=aWait}.elsewhen(readingPrefix){seedState:=seedWait}.otherwise{loadState:=loadWait}
  }
  when(io.burstResponse.fire){
    received:=received+1.U
    when(responseBad){fail(Mux(response.error,Status.Memory.U,Mux(!sourceFinite,Status.Numerical.U,Status.Protocol.U)))}
    when(!responseBad && status===0.U){
      when(burstIsPrefix){seedHold:=response.data;seedState:=seedSend}
      .elsewhen(burstIsA){
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
      when(burstIsPrefix){}
      .elsewhen(burstIsA){
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
              when(loadDepth===127.U || loadK+&loadDepth+1.U===chunkEnd){
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
    halfReady:=VecInit(Seq.fill(2)(false.B));loadHalf:=chunkStart(7);nextLoadK:=chunkStart;loadState:=loadIdle
    issueHalf:=chunkStart(7);readK:=chunkStart;readContext:=0.U;allRead:=false.B
    groupStarted:=false.B;groupDone:=false.B;written:=0.U;writeState:=writeIdle;state:=execute
    groupIssueBase:=issued;terminalIssued:=0.U;captured:=0.U
    seedState:=Mux(restoring,seedBegin,seedIdle);seedContext:=0.U;seedIndex:=0.U
    when(groupSequence==="hffffffff".U){fail(Status.Protocol.U)}.otherwise{groupSequence:=groupSequence+1.U}
  }
  when(state===execute && status===0.U && seedFinished && loadState===loadIdle && nextLoadK<chunkEnd && !halfReady(loadHalf)){
    loadK:=nextLoadK;loadDepth:=0.U;loadContext:=0.U;loadBeat:=false.B;loadState:=loadReq
  }
  when(io.matrix.group.fire){groupStarted:=true.B}
  when(io.matrix.done.fire){
    groupDone:=true.B
    when(io.matrix.done.bits.error || io.matrix.done.bits.tag=/=job.tag || !allRead || banks.io.response.valid ||
      operands.io.deq.valid || captured=/=contexts || issued-groupIssueBase=/=(chunkEnd-chunkStart).pad(64)*contexts){fail(Status.Protocol.U)}
  }
  val operandsEmpty= !banks.io.response.valid && !operands.io.deq.valid
  when(state===execute && status===0.U && groupDone && written===contexts && writeState===writeIdle &&
    allRead && operandsEmpty && !burstOutstanding && loadState===loadIdle){
    when(!restoring){
      when(prefixAckBytes=/=((nBase.pad(64)>>5)+contexts)*16384.U){fail(Status.Protocol.U)}
      .otherwise{prefixValid:=true.B;restoring:=true.B;state:=setup}
    }.elsewhen(nBase+(contexts.pad(17)<<5)>=job.n){
      when(bytes=/=job.writeBytes){fail(Status.Protocol.U)}.otherwise{state:=finish}
    }.otherwise{nBase:=nBase+(contexts.pad(16)<<5);restoring:=false.B;prefixValid:=false.B;state:=setup}
  }
  when(status=/=0.U && state=/=idle && state=/=finish && state=/=locked){
    state:=drain;aCommitted:=false.B;prefixValid:=false.B;halfReady:=VecInit(Seq.fill(2)(false.B));aHighPending:=false.B
    when(loadState===loadReq){loadState:=loadIdle}
    when(writeState===writeReq){writeState:=writeIdle}
    when(!burstOutstanding && (!groupStarted || groupDone) && writeState=/=writeWait && writeState=/=writeData &&
      !banks.io.activationBusy && operandsEmpty){state:=finish}
  }
  when(io.done.fire){state:=Mux(status===0.U,idle,locked)}
}

/** Selected chunk-major extension; same physical banks, service, and seed leaf. */
class TransposedDenseDownOwner(burstWrites:Boolean=false,enableFfnTiles:Boolean=false,enableFfnWindow:Boolean=false,enableFfnDrain:Boolean=false,numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0,enableKWindow:Boolean=false,enableDenseDrain:Boolean=false) extends Module {
  require(!enableDenseDrain || enableFfnDrain,"Dense tile drain requires the existing drain port")
  require(!enableKWindow || enableFfnWindow,"K windows require the actual FFN window owner")
  private val officialBf16=Qwen2NumericPolicy.official(numericPolicy)
  require(!enableFfnDrain || enableFfnTiles,"act drain requires the shared tile banks")
  require(!enableFfnWindow || enableFfnTiles,"internal window requires the shared tile banks")
  val io=IO(new DenseOwnerIO(burstWrites,transposed=true,enableAccumulatorSeed=true,downChunks=true,enableFfnTiles=enableFfnTiles,enableFfnWindow=enableFfnWindow,enableFfnDrain=enableFfnDrain,enableKWindow=enableKWindow))
  val idle::clearA::aReq::aWait::aFence::setup::execute::drain::finish::locked::Nil=Enum(10)
  val state=RegInit(idle);val job=Reg(new QwenOwnerJob)
  val status=RegInit(0.U(8.W));val cycles=RegInit(0.U(64.W));val bytes=RegInit(0.U(64.W))
  val useful=RegInit(0.U(64.W));val physicalBase=RegInit(0.U(64.W))
  val issued=RegInit(0.U(64.W));val starved=RegInit(0.U(64.W))
  val aCommitted=RegInit(false.B);val aGeneration=RegInit(0.U(32.W))
  val zeroWord=RegInit(0.U(11.W));val aRow=RegInit(0.U(7.W));val aBeat=RegInit(0.U(8.W))
  // The lower 256 bits live in the banks' RMW stage. Only native BF16 needs
  // this additional upper 256-bit hold, and it uses the same physical ports.
  val aHighPending=RegInit(false.B);val aHigh=Reg(UInt(256.W))
  val aHighRow=Reg(UInt(7.W));val aHighKWord=Reg(UInt(8.W))
  val sequence=RegInit(0.U(32.W));val burstTag=Reg(UInt(64.W))
  val burstOutstanding=RegInit(false.B);val burstIsA=Reg(Bool());val received=RegInit(0.U(8.W))
  val nBase=RegInit(0.U(16.W));val contexts=Reg(UInt(3.W))
  val halfReady=RegInit(VecInit(Seq.fill(2)(false.B)))
  val halfK=Reg(Vec(2,UInt(12.W)));val halfN=Reg(Vec(2,UInt(16.W)))
  val loadIdle::loadReq::loadWait::Nil=Enum(3)
  val loadState=RegInit(loadIdle);val loadHalf=RegInit(false.B)
  val nextLoadK=RegInit(0.U(12.W));val loadK=Reg(UInt(12.W))
  val loadDepth=RegInit(0.U(7.W));val loadContext=RegInit(0.U(3.W));val loadBeat=RegInit(false.B)
  val issueHalf=RegInit(false.B);val readK=RegInit(0.U(12.W));val readContext=RegInit(0.U(3.W))
  val allRead=RegInit(false.B);val groupStarted=RegInit(false.B);val groupDone=RegInit(false.B)
  val groupIssueBase=RegInit(0.U(64.W));val terminalIssued=RegInit(0.U(5.W));val captured=RegInit(0.U(3.W))
  val writeIdle::writeReq::writeData::writeWait::Nil=Enum(4)
  val writeState=RegInit(writeIdle);val written=RegInit(0.U(3.W));val writeContext=Reg(UInt(3.W))
  val writeRow=RegInit(0.U(7.W));val writeBeat=RegInit(false.B)
  val writeCount=Reg(UInt(5.W));val writeIndex=RegInit(0.U(5.W))
  val writeSequence=RegInit(0.U(32.W));val writeTag=Reg(UInt(64.W))
  val finalValue=Reg(Vec(16,Vec(256,UInt(32.W))))
  def fail(code:UInt):Unit={when(status===0.U){status:=code}}
  // Optional control/identity only. Payload storage remains the existing finalValue.
  val windowActive=if(enableFfnWindow)Some(RegInit(false.B))else None
  val windowIdentity=if(enableFfnWindow)Some(Reg(UInt(32.W)))else None
  val windowNg=if(enableFfnWindow)Some(Reg(UInt(16.W)))else None
  val windowCols=if(enableFfnWindow)Some(Reg(UInt(8.W)))else None
  val windowSlot=if(enableFfnWindow)Some(Reg(UInt(2.W)))else None
  val windowReuse=if(enableFfnWindow)Some(Reg(Bool()))else None
  val windowBegun=if(enableFfnWindow)Some(RegInit(false.B))else None
  val windowCommitted=if(enableFfnWindow)Some(RegInit(false.B))else None
  val windowPhase=if(enableFfnWindow)Some(RegInit(0.U(3.W)))else None // 1 begin,2 verify,3 run,4 seal,5 retire
  val aLease=if(enableFfnWindow)Some(Reg(new FfnALease))else None
  val aLeaseValid=if(enableFfnWindow)Some(RegInit(false.B))else None
  // Control metadata only. The existing finalValue and A/B banks are shared.
  val kPolicy=if(enableKWindow)Some(RegInit(0.U.asTypeOf(new DenseKWindowPolicy)))else None
  val drainActive=if(enableFfnDrain)Some(RegInit(false.B))else None
  val drainIdentity=if(enableFfnDrain)Some(Reg(UInt(32.W)))else None
  val drainNg=if(enableFfnDrain)Some(Reg(UInt(16.W)))else None
  val drainCols=if(enableFfnDrain)Some(Reg(UInt(8.W)))else None
  val drainPhase=if(enableFfnDrain)Some(RegInit(0.U(3.W)))else None
  val drainReadPending=if(enableFfnDrain)Some(RegInit(false.B))else None
  val drainConsumed=if(enableFfnDrain)Some(RegInit(0.U(11.W)))else None
  val drainCommitted=if(enableFfnDrain)Some(RegInit(false.B))else None
  val drainPoison=if(enableFfnDrain)Some(RegInit(false.B))else None
  val workspace=Reg(new TransposedPrefixWorkspace(2560))
  val chunkBase=RegInit(0.U(16.W))
  val committedPrefixEnd=RegInit(0.U(16.W))
  val restoredContexts=RegInit(0.U(12.W));val savedContexts=RegInit(0.U(12.W))
  val sweepAckBytes=RegInit(0.U(64.W))
  val restoring=RegInit(false.B);val prefixValid=RegInit(false.B)
  val prefixAckBytes=RegInit(0.U(64.W));val prefixWriteIndex=RegInit(0.U(8.W))
  val groupSequence=RegInit(0.U(32.W))
  val seedIdle::seedBegin::seedRead::seedWait::seedSend::seedAck::Nil=Enum(6)
  val seedState=RegInit(seedIdle);val seedContext=RegInit(0.U(3.W));val seedIndex=RegInit(0.U(8.W))
  val seedHold=Reg(UInt(512.W));val burstIsPrefix=RegInit(false.B)
  val seedOutstanding=RegInit(false.B)
  // Global DDR stride remains job.k; SRAM coordinates are always local.
  val chunkDepth=if(enableFfnWindow)Mux(windowActive.get,job.k,Mux(job.k-chunkBase>workspace.splitK,workspace.splitK,job.k-chunkBase))else Mux(job.k-chunkBase>workspace.splitK,workspace.splitK,job.k-chunkBase)
  val chunkEnd=chunkBase+chunkDepth
  // Keep chunkDepth as the COMPLETE A load extent. K execution has its own
  // bounds; otherwise A row stride/clear/RMW/lease would silently be shortened.
  val kActive=if(enableKWindow)windowActive.get && kPolicy.get.enabled else false.B
  val executionBegin=if(enableKWindow)Mux(kActive,kPolicy.get.begin,0.U)else 0.U
  val executionEnd=if(enableKWindow)Mux(kActive,kPolicy.get.end,chunkDepth)else chunkDepth
  val executionLength=if(enableKWindow)executionEnd-executionBegin else chunkDepth
  val savingPrefix=chunkEnd<job.k
  val restoreLegal=prefixValid && committedPrefixEnd===chunkBase &&
    (nBase.pad(17)>>5)+seedContext===restoredContexts &&
    (nBase.pad(17)>>5)+seedContext>=savedContexts
  val seedFinished=seedState===seedIdle
  val seed=io.matrix.seed.get
  seed.begin.valid:=state===execute && groupStarted && restoring && restoreLegal && seedState===seedBegin && status===0.U
  seed.begin.bits.groupTag:=job.tag;seed.begin.bits.groupSequence:=groupSequence
  seed.begin.bits.sourceGeneration:=workspace.generation;seed.begin.bits.context:=seedContext;seed.begin.bits.sliceMask:=255.U
  seed.beat.valid:=state===execute && seedState===seedSend && status===0.U
  seed.beat.bits.groupTag:=job.tag;seed.beat.bits.groupSequence:=groupSequence
  seed.beat.bits.sourceGeneration:=workspace.generation;seed.beat.bits.context:=seedContext
  seed.beat.bits.index:=seedIndex;seed.beat.bits.data:=seedHold;seed.beat.bits.last:=seedIndex===255.U;seed.beat.bits.error:=false.B
  seed.ack.ready:=seedOutstanding && (state===drain || (state===execute && seedState===seedAck))
  when(state===execute && groupStarted && restoring && seedState===seedBegin && !restoreLegal){fail(Status.Protocol.U)}
  when(seed.begin.fire){seedOutstanding:=true.B;seedState:=seedRead}
  when(seed.beat.fire){
    when(seedIndex===255.U){seedState:=seedAck}.otherwise{seedIndex:=seedIndex+1.U;seedState:=seedRead}
  }
  when(seed.ack.fire){
    seedOutstanding:=false.B
    val a=seed.ack.bits
    when(a.error || a.groupTag=/=job.tag || a.groupSequence=/=groupSequence ||
      a.sourceGeneration=/=workspace.generation || a.context=/=seedContext){fail(Status.Protocol.U)}
    .elsewhen(status===0.U && state===execute){
      when(!restoreLegal){fail(Status.Protocol.U)}
      restoredContexts:=restoredContexts+1.U
      seedIndex:=0.U;seedContext:=seedContext+1.U
      seedState:=Mux(seedContext+1.U===contexts,seedIdle,seedBegin)
    }
  }
  when(seed.ack.valid && !seed.ack.ready && seedState=/=seedAck){fail(Status.Protocol.U)}
  val banks=Module(new TransposedDownDenseBanks(enableFfnTiles,enableMatrixProducerOrder=enableFfnWindow))
  if(enableFfnTiles){banks.io.tiles.get<>io.tiles.get;banks.io.tileEnable.get:=state===idle}
  if(enableFfnWindow || enableFfnDrain){
    val p=banks.io.tiles.get;val external=io.tiles.get
    val active=if(enableFfnDrain)drainActive.get || windowActive.getOrElse(false.B)else windowActive.get
    // Exclusive ownership also covers begin, seal, drain and a stalled result.
    external.control.ready:= !active && p.control.ready
    external.write.ready:= !active && p.write.ready
    external.read.ready:= !active && p.read.ready
    p.control.valid:= !active && external.control.valid
    p.write.valid:= !active && external.write.valid
    p.read.valid:= !active && external.read.valid
    p.response.ready:= !active && external.response.ready
    external.response.valid:= !active && p.response.valid
    p.abort:=external.abort || (active && status=/=0.U)
    if(enableFfnDrain){p.abort:=external.abort || io.drain.get.abort || drainPoison.get || (active && status=/=0.U)}
    banks.io.tileEnable.get:=state===idle || active
  }
  banks.io.zero.valid:=state===clearA; banks.io.zero.bits:=zeroWord
  banks.io.weight.valid:=false.B; banks.io.weight.bits:=0.U.asTypeOf(new TransposedDownWeightLoad)
  banks.io.activation.valid:=false.B; banks.io.activation.bits:=0.U.asTypeOf(new TransposedDownActivationLoad)

  val activationBytes=Mux(job.activationBf16,2.U(3.W),4.U(3.W))
  val activationBeats=Mux(job.activationBf16,chunkDepth>>5,chunkDepth>>4)
  val weightBytes=Mux(job.weightBf16,2.U(3.W),4.U(3.W))
  val outputBytes=Mux(job.outputBf16,2.U(3.W),4.U(3.W))
  val outputBeats=Mux(job.outputBf16,1.U(2.W),2.U(2.W))
  val aAddress=job.a+(aRow.pad(64)*job.k+chunkBase)*activationBytes+(aBeat.pad(64)<<6)
  val wAddress=job.b+((chunkBase.pad(64)+loadK+loadDepth)*job.n+nBase+(loadContext.pad(64)<<5)+
    Mux(loadBeat,16.U(64.W),0.U(64.W)))*weightBytes
  // One-beat descriptors are intentionally conservative. The ABI still uses
  // the real burst bridge and its validated LAST fence, with no simulated DMA.
  val prefixReadAddress=workspace.base+((nBase.pad(64)>>5)+seedContext)*16384.U+
    (((seedIndex(4,1).pad(64)<<4)+(seedIndex(7,5).pad(64)<<1)+seedIndex(0).asUInt)<<6)
  val readingPrefix=state===execute && restoring && restoreLegal && groupStarted && seedState===seedRead
  io.burst.valid:=status===0.U && !burstOutstanding &&
    ((state===aReq && !aHighPending && !banks.io.activationBusy) || (state===execute && seedFinished && loadState===loadReq) || readingPrefix)
  io.burst.bits.address:=Mux(state===aReq,aAddress,Mux(readingPrefix,prefixReadAddress,wAddress))
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
  val sourceFinite=Mux(burstIsPrefix,sourceWords.map(TensorMath.finite).reduce(_&&_),Mux(sourceNative,sourceHalves.map(_(14,7)=/=255.U).reduce(_&&_),
    sourceWords.map(TensorMath.finite).reduce(_&&_) && converted.map(_(14,7)=/=255.U).reduce(_&&_)))
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
  if(enableFfnTiles){io.job.ready:=state===idle && !banks.io.tiles.get.busy && !io.tiles.get.control.valid && !io.tiles.get.write.valid && !io.tiles.get.read.valid && !io.tiles.get.abort}
  io.done.valid:=(if(enableFfnDrain)state===finish && !drainActive.get && !windowActive.getOrElse(false.B)else if(enableFfnWindow)state===finish && !windowActive.get else state===finish);io.done.bits.tag:=job.tag;io.done.bits.status:=status
  io.done.bits.writeBytes:=bytes;io.done.bits.cycles:=cycles;io.done.bits.usefulMacs:=useful
  io.done.bits.executedMacs:=(io.physicalSteps-physicalBase)*512.U
  io.resetRequired:=(if(enableFfnTiles)(status=/=0.U) || banks.io.tiles.get.resetRequired || io.tiles.get.abort else status=/=0.U);io.issueCycles:=issued;io.operandStalls:=starved
  io.matrix.group.valid:=state===execute && aCommitted && !groupStarted && status===0.U
  io.matrix.group.bits.opcode:=0x20.U;io.matrix.group.bits.sliceMask:=255.U
  io.matrix.group.bits.groupSequence.get:=groupSequence
  io.matrix.group.bits.tag:=job.tag;io.matrix.group.bits.transposedDense.get:=true.B
  io.matrix.done.ready:=(state===execute || state===drain) && groupStarted && !groupDone
  io.matrix.abort:=(state===drain || status=/=0.U) && groupStarted && !groupDone

  val operands=Module(new Queue(new MatrixStreamStep,4,pipe=true))
  val pendingK=Reg(UInt(12.W));val pendingContext=Reg(UInt(3.W))
  val eligibleHalf=halfReady(issueHalf) && halfK(issueHalf)===Cat(readK(11,7),0.U(7.W)) && halfN(issueHalf)===nBase
  banks.io.read.valid:=state===execute && aCommitted && groupStarted && !groupDone && !allRead && seedFinished && status===0.U &&
    eligibleHalf && operands.io.count+&banks.io.response.valid.asUInt<4.U
  if(enableFfnWindow){when(windowActive.get && writeState=/=writeIdle){banks.io.read.valid:=false.B}}
  banks.io.read.bits.k:=readK;banks.io.read.bits.context:=readContext;banks.io.read.bits.half:=issueHalf
  if(enableKWindow){
    // readK remains monotonic progress. Pair permutation is only an SRAM address.
    when(kActive){banks.io.read.bits.k:=executionBegin+((readK-executionBegin)^kPolicy.get.pairReverse.asUInt)}
  }
  when(banks.io.read.fire){pendingK:=readK;pendingContext:=readContext}
  operands.io.enq.valid:=banks.io.response.valid && status===0.U
  val step=operands.io.enq.bits
  step.context:=pendingContext;step.clear:=chunkBase===0.U && pendingK===0.U;step.last:=pendingK+1.U===chunkDepth
  if(enableKWindow){when(kActive){step.clear:=pendingK===executionBegin;step.last:=pendingK+1.U===executionEnd}}
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
      // Release after the final ordinal in the half, including 127 then 126.
      when(readK(6,0)===127.U || readK+1.U===executionEnd){halfReady(issueHalf):=false.B;issueHalf:= !issueHalf}
      when(readK+1.U===executionEnd){allRead:=true.B}
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
      (!savingPrefix && (col%128).U>=job.m) || (TensorMath.finite(r.value(n)(col)) &&
        (savingPrefix || !(job.outputBf16 || (officialBf16.B && job.materializeDenseOutput)) || r.value(n)(col)(30,0)<"h7f7f8000".U(31.W))))).reduce(_&&_)
    when(r.error || !r.last || r.context>=contexts || r.context=/=written || !terminalIssued(r.context)){fail(Status.Protocol.U)}
    .elsewhen(!finite){fail(Status.Numerical.U)}
    .otherwise{finalValue:=r.value;captured:=captured+1.U;writeContext:=r.context;prefixWriteIndex:=0.U;writeRow:=0.U;writeBeat:=false.B;writeState:=writeReq}
  }
  val finalOutputAddress=job.dst+(writeRow.pad(64)*job.n+nBase+(writeContext.pad(64)<<5)+
    Mux(writeBeat,16.U(64.W),0.U(64.W)))*outputBytes
  val prefixOutputAddress=workspace.base+((nBase.pad(64)>>5)+writeContext)*16384.U+(prefixWriteIndex.pad(64)<<6)
  val drainRowBeat=if(enableFfnDrain)Some(Cat(writeContext,writeBeat))else None
  val drainOutputAddress=if(enableFfnDrain)Some(job.dst+(writeRow.pad(64)*job.n+drainNg.get+(drainRowBeat.get.pad(64)<<4))*4.U)else None
  val outputAddress=if(enableFfnDrain)Mux(drainActive.get,drainOutputAddress.get,Mux(savingPrefix,prefixOutputAddress,finalOutputAddress))else Mux(savingPrefix,prefixOutputAddress,finalOutputAddress)
  def outputPacket(beat:UInt):UInt={
    // Y[m,n] = physical[n%16][32*(4*(n/16)+m/32)+m%32].
    val fp32=VecInit((0 until 16).map{n=>
      val raw=finalValue(n)(Cat(beat(0),writeRow))
      if(officialBf16)Mux(job.materializeDenseOutput,F32.bf(raw),raw)else raw
    }).asUInt
    val bf16=VecInit((0 until 32).map(n=>TensorMath.bf16Rne(finalValue(n%16)(Cat((n/16).U(1.W),writeRow))))).asUInt
    val prefix=VecInit((0 until 16).map(i=>finalValue(prefixWriteIndex(7,4))(Cat(prefixWriteIndex(3,0),i.U(4.W))))).asUInt
    if(enableFfnDrain){
      val act=VecInit((0 until 16).map(i=>finalValue(writeRow(3,0))((beat.pad(8)<<4)+i.U))).asUInt
      Mux(drainActive.get,act,Mux(savingPrefix,prefix,Mux(job.outputBf16,bf16,fp32)))
    }else Mux(savingPrefix,prefix,Mux(job.outputBf16,bf16,fp32))
  }
  val prefixStoreLegal=(nBase.pad(17)>>5)+writeContext===savedContexts &&
    (!restoring || (nBase.pad(17)>>5)+writeContext<restoredContexts)
  when(state===execute && writeState===writeReq && savingPrefix && !prefixStoreLegal){fail(Status.Protocol.U)}
  val writeActive=state===execute || state===drain
  val ackFire=WireDefault(false.B);val ackBits=WireDefault(0.U.asTypeOf(new MemoryResponse))
  val ackBeats=WireDefault(1.U(5.W))
  io.memory.valid:=false.B;io.memory.bits:=0.U.asTypeOf(new MemoryRequest);io.response.ready:=false.B
  if(burstWrites){
    val port=io.writeRequest.get
    val remaining=if(enableFfnDrain)Mux(drainActive.get,(drainCols.get>>4)-drainRowBeat.get,outputBeats-writeBeat.asUInt)else outputBeats-writeBeat.asUInt
    val page=16.U(5.W)-outputAddress(9,6)
    port.valid:=state===execute && writeState===writeReq && status===0.U && (!savingPrefix || prefixStoreLegal)
    if(enableFfnWindow){when(windowActive.get){port.valid:=false.B}}
    port.bits.address:=outputAddress;port.bits.beats:=(if(enableFfnDrain)Mux(drainActive.get,Mux(remaining<page,remaining,page),Mux(savingPrefix,1.U,Mux(remaining<page,remaining,page)))else Mux(savingPrefix,1.U,Mux(remaining<page,remaining,page)))
    port.bits.tag:=Cat(job.tag,writeSequence)
    io.writeData.get.valid:=writeActive && writeState===writeData
    io.writeData.get.bits.data:=outputPacket(if(enableFfnDrain)Mux(drainActive.get,drainRowBeat.get+writeIndex,writeBeat.asUInt+writeIndex)else writeBeat.asUInt+writeIndex)
    io.writeData.get.bits.last:=writeIndex+1.U===writeCount
    io.writeResponse.get.ready:=writeActive && writeState===writeWait
    when(port.fire){writeTag:=port.bits.tag;writeCount:=port.bits.beats;writeIndex:=0.U;writeState:=writeData}
    when(io.writeData.get.fire){writeIndex:=writeIndex+1.U;when(writeIndex+1.U===writeCount){writeState:=writeWait}}
    ackFire:=io.writeResponse.get.fire;ackBits:=io.writeResponse.get.bits;ackBeats:=writeCount
  }else{
    io.memory.valid:=state===execute && writeState===writeReq && status===0.U && (!savingPrefix || prefixStoreLegal)
    if(enableFfnWindow){when(windowActive.get){io.memory.valid:=false.B}}
    io.memory.bits.write:=true.B;io.memory.bits.address:=outputAddress
    io.memory.bits.data:=outputPacket(if(enableFfnDrain)Mux(drainActive.get,drainRowBeat.get,writeBeat.asUInt)else writeBeat.asUInt);io.memory.bits.mask:=Fill(64,1.U(1.W))
    io.memory.bits.tag:=Cat(job.tag,writeSequence)
    io.response.ready:=writeActive && writeState===writeWait
    when(io.memory.fire){writeTag:=io.memory.bits.tag;writeState:=writeWait}
    ackFire:=io.response.fire;ackBits:=io.response.bits
  }
  when(if(enableFfnDrain)ackFire && !drainActive.get else ackFire){
    when(ackBits.error || ackBits.tag=/=writeTag){
      fail(Mux(ackBits.error,Status.Memory.U,Status.Protocol.U));writeState:=writeIdle
    }.otherwise{
      when(savingPrefix){prefixAckBytes:=prefixAckBytes+64.U;sweepAckBytes:=sweepAckBytes+64.U}.otherwise{bytes:=bytes+(ackBeats.pad(64)<<6)}
      writeSequence:=writeSequence+1.U
      when(status=/=0.U){writeState:=writeIdle}
      .elsewhen(savingPrefix){
        when(prefixWriteIndex===255.U){written:=written+1.U;savedContexts:=savedContexts+1.U;writeState:=writeIdle}
        .otherwise{prefixWriteIndex:=prefixWriteIndex+1.U;writeState:=writeReq}
      }
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
    val j=io.job.bits;val w=io.prefixWorkspace.get;workspace:=w
    restoring:=false.B;prefixValid:=false.B;prefixAckBytes:=0.U;seedState:=seedIdle
    chunkBase:=0.U;committedPrefixEnd:=0.U;restoredContexts:=0.U;savedContexts:=0.U;sweepAckBytes:=0.U
    job:=j;status:=0.U;cycles:=0.U;bytes:=0.U;useful:=0.U;issued:=0.U;starved:=0.U
    cycleBuckets:=VecInit(Seq.fill(7)(0.U(64.W)));physicalBase:=io.physicalSteps
    aCommitted:=false.B;zeroWord:=0.U;aRow:=0.U;aBeat:=0.U;aHighPending:=false.B;nBase:=0.U
    val aEnd=j.a.pad(66)+j.m.pad(66)*j.k*Mux(j.activationBf16,2.U(3.W),4.U(3.W))
    val bEnd=j.b.pad(66)+j.k.pad(66)*j.n*Mux(j.weightBf16,2.U(3.W),4.U(3.W))
    val dEnd=j.dst.pad(66)+j.m.pad(66)*j.n*Mux(j.outputBf16,2.U(3.W),4.U(3.W))
    val aliases=(j.a.pad(66)<dEnd && j.dst.pad(66)<aEnd)||(j.b.pad(66)<dEnd && j.dst.pad(66)<bEnd)
    val aligned=Seq(j.a,j.b,j.dst).map(_(5,0)===0.U).reduce(_&&_)
    val pEnd=w.base.pad(66)+w.extent.pad(66)
    val prefixAliases=Seq((j.a,aEnd),(j.b,bEnd),(j.dst,dEnd)).map{case(base,end)=>
      w.base.pad(66)<end && base.pad(66)<pEnd}.reduce(_||_)
    val tileConflict=if(enableFfnTiles)banks.io.tiles.get.leased && j.k>1536.U else false.B
    when(if(enableFfnTiles)tileConflict || !w.valid || w.base(5,0)=/=0.U || w.extent===0.U || (j.k>w.splitK && w.extent<(j.n.pad(64)>>5)*16384.U) ||
      pEnd>(BigInt(1)<<56).U || prefixAliases || w.generation===0.U || w.splitK===0.U ||
      w.splitK>2560.U || w.splitK(6,0)=/=0.U || groupSequence==="hffffffff".U ||
      j.kind=/=QwenOwnerKind.Dense.U || (j.m===0.U || j.m>128.U) || j.k===0.U || j.k>8960.U ||
      j.k(3,0)=/=0.U || (j.activationBf16 && j.k(4,0)=/=0.U) || j.n===0.U || j.n(4,0)=/=0.U ||
      !aligned || aliases || Seq(aEnd,bEnd,dEnd).map(_>(BigInt(1)<<56).U).reduce(_||_) ||
      j.writeBytes=/=j.m.pad(64)*j.n*Mux(j.outputBf16,2.U(3.W),4.U(3.W)) else !w.valid || w.base(5,0)=/=0.U || w.extent===0.U || (j.k>w.splitK && w.extent<(j.n.pad(64)>>5)*16384.U) ||
      pEnd>(BigInt(1)<<56).U || prefixAliases || w.generation===0.U || w.splitK===0.U ||
      w.splitK>2560.U || w.splitK(6,0)=/=0.U || groupSequence==="hffffffff".U ||
      j.kind=/=QwenOwnerKind.Dense.U || (j.m===0.U || j.m>128.U) || j.k===0.U || j.k>8960.U ||
      j.k(3,0)=/=0.U || (j.activationBf16 && j.k(4,0)=/=0.U) || j.n===0.U || j.n(4,0)=/=0.U ||
      !aligned || aliases || Seq(aEnd,bEnd,dEnd).map(_>(BigInt(1)<<56).U).reduce(_||_) ||
      j.writeBytes=/=j.m.pad(64)*j.n*Mux(j.outputBf16,2.U(3.W),4.U(3.W))) {
      status:=Status.Bounds.U;state:=finish
    }.otherwise{state:=clearA}
  }
  when(state===clearA){
    when(zeroWord+1.U===(chunkDepth>>4)*8.U){state:=aReq}.otherwise{zeroWord:=zeroWord+1.U}
  }
  when(io.burst.fire){
    assert(io.burst.bits.address(5,0)===0.U && io.burst.bits.beats===1.U)
    burstOutstanding:=true.B;burstTag:=io.burst.bits.tag;sequence:=sequence+1.U;received:=0.U
    burstIsA:=state===aReq;burstIsPrefix:=readingPrefix
    when(state===aReq){state:=aWait}.elsewhen(readingPrefix){seedState:=seedWait}.otherwise{loadState:=loadWait}
  }
  when(io.burstResponse.fire){
    received:=received+1.U
    when(responseBad){fail(Mux(response.error,Status.Memory.U,Mux(!sourceFinite,Status.Numerical.U,Status.Protocol.U)))}
    when(!responseBad && status===0.U){
      when(burstIsPrefix){seedHold:=response.data;seedState:=seedSend}
      .elsewhen(burstIsA){
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
      when(burstIsPrefix){}
      .elsewhen(burstIsA){
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
              when(loadDepth===127.U || loadK+&loadDepth+1.U===executionEnd){
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
    contexts:=(if(enableFfnWindow)Mux(windowActive.get,(windowCols.get>>5)(2,0),Mux((job.n-nBase)>>5>5.U,5.U,((job.n-nBase)>>5)(2,0)))else Mux((job.n-nBase)>>5>5.U,5.U,((job.n-nBase)>>5)(2,0)))
    halfReady:=VecInit(Seq.fill(2)(false.B));loadHalf:=false.B;nextLoadK:=0.U;loadState:=loadIdle
    issueHalf:=false.B;readK:=0.U;readContext:=0.U;allRead:=false.B
    if(enableKWindow){when(kActive){
      nextLoadK:=executionBegin;loadHalf:=executionBegin(7)
      readK:=executionBegin;issueHalf:=executionBegin(7)
    }}
    groupStarted:=false.B;groupDone:=false.B;written:=0.U;writeState:=writeIdle;state:=execute
    groupIssueBase:=issued;terminalIssued:=0.U;captured:=0.U
    seedState:=Mux(restoring,seedBegin,seedIdle);seedContext:=0.U;seedIndex:=0.U
    when(groupSequence==="hffffffff".U){fail(Status.Protocol.U)}.otherwise{groupSequence:=groupSequence+1.U}
  }
  when(state===execute && status===0.U && seedFinished && loadState===loadIdle && nextLoadK<executionEnd && !halfReady(loadHalf)){
    loadK:=nextLoadK;loadDepth:=0.U;loadContext:=0.U;loadBeat:=false.B;loadState:=loadReq
    if(enableKWindow){when(kActive){
      // Interior even boundaries load only selected rows into their unchanged
      // physical depth in the 128-K B half. No scratch or address translation.
      loadK:=Cat(nextLoadK(11,7),0.U(7.W));loadDepth:=nextLoadK(6,0)
    }}
  }
  when(io.matrix.group.fire){groupStarted:=true.B}
  when(io.matrix.done.fire){
    groupDone:=true.B
    when(io.matrix.done.bits.error || io.matrix.done.bits.tag=/=job.tag || !allRead || banks.io.response.valid ||
      operands.io.deq.valid || captured=/=contexts || issued-groupIssueBase=/=executionLength.pad(64)*contexts){fail(Status.Protocol.U)}
  }
  val operandsEmpty= !banks.io.response.valid && !operands.io.deq.valid
  if(enableFfnWindow){
  when(state===execute && status===0.U && groupDone && written===contexts && writeState===writeIdle &&
    allRead && operandsEmpty && !burstOutstanding && !seedOutstanding && loadState===loadIdle){
    when(windowActive.get){windowPhase.get:=4.U}.otherwise{
    val nextContext=(nBase.pad(17)>>5)+contexts
    val sweepComplete=nextContext===(job.n.pad(17)>>5)
    when(savingPrefix && (savedContexts=/=nextContext || sweepAckBytes=/=nextContext*16384.U)){
      fail(Status.Protocol.U)
    }.elsewhen(restoring && (restoredContexts=/=nextContext || committedPrefixEnd=/=chunkBase)){
      fail(Status.Protocol.U)
    }.elsewhen(!savingPrefix && bytes=/=job.m.pad(64)*(nextContext<<5)*outputBytes){
      fail(Status.Protocol.U)
    }.elsewhen(!sweepComplete){
      nBase:=nBase+(contexts.pad(16)<<5);state:=setup
    }.elsewhen(savingPrefix){
      // All old contexts were consumed in order before their in-place writes.
      // Commit only after every group's done and every prefix write ACK.
      committedPrefixEnd:=chunkEnd;chunkBase:=chunkEnd
      prefixValid:=true.B;restoring:=true.B
      restoredContexts:=0.U;savedContexts:=0.U;sweepAckBytes:=0.U
      nBase:=0.U;zeroWord:=0.U;aRow:=0.U;aBeat:=0.U;aCommitted:=false.B
      groupStarted:=false.B;groupDone:=false.B;seedState:=seedIdle
      halfReady:=VecInit(Seq.fill(2)(false.B));state:=clearA
    }.otherwise{
      when(bytes=/=job.writeBytes){fail(Status.Protocol.U)}.otherwise{state:=finish}
    }
    }
  }
  }else{
  when(state===execute && status===0.U && groupDone && written===contexts && writeState===writeIdle &&
    allRead && operandsEmpty && !burstOutstanding && !seedOutstanding && loadState===loadIdle){
    val nextContext=(nBase.pad(17)>>5)+contexts
    val sweepComplete=nextContext===(job.n.pad(17)>>5)
    when(savingPrefix && (savedContexts=/=nextContext || sweepAckBytes=/=nextContext*16384.U)){
      fail(Status.Protocol.U)
    }.elsewhen(restoring && (restoredContexts=/=nextContext || committedPrefixEnd=/=chunkBase)){
      fail(Status.Protocol.U)
    }.elsewhen(!savingPrefix && bytes=/=job.m.pad(64)*(nextContext<<5)*outputBytes){
      fail(Status.Protocol.U)
    }.elsewhen(!sweepComplete){
      nBase:=nBase+(contexts.pad(16)<<5);state:=setup
    }.elsewhen(savingPrefix){
      // All old contexts were consumed in order before their in-place writes.
      // Commit only after every group's done and every prefix write ACK.
      committedPrefixEnd:=chunkEnd;chunkBase:=chunkEnd
      prefixValid:=true.B;restoring:=true.B
      restoredContexts:=0.U;savedContexts:=0.U;sweepAckBytes:=0.U
      nBase:=0.U;zeroWord:=0.U;aRow:=0.U;aBeat:=0.U;aCommitted:=false.B
      groupStarted:=false.B;groupDone:=false.B;seedState:=seedIdle
      halfReady:=VecInit(Seq.fill(2)(false.B));state:=clearA
    }.otherwise{
      when(bytes=/=job.writeBytes){fail(Status.Protocol.U)}.otherwise{state:=finish}
    }
  }
  }
  when(if(enableFfnDrain)status=/=0.U && state=/=idle && state=/=finish && state=/=locked && !drainActive.get else status=/=0.U && state=/=idle && state=/=finish && state=/=locked){
    state:=drain;aCommitted:=false.B;prefixValid:=false.B;halfReady:=VecInit(Seq.fill(2)(false.B));aHighPending:=false.B
    when(loadState===loadReq){loadState:=loadIdle}
    when(writeState===writeReq){writeState:=writeIdle}
    when(!burstOutstanding && !seedOutstanding && (!groupStarted || groupDone) && writeState=/=writeWait && writeState=/=writeData &&
      !banks.io.activationBusy && operandsEmpty){
      if(enableFfnWindow){when(!windowActive.get || banks.io.tiles.get.drained){state:=finish}}else{state:=finish}
    }
  }
  if(enableFfnTiles){when((banks.io.tiles.get.resetRequired || io.tiles.get.abort) && state=/=idle && state=/=finish && state=/=locked){fail(Status.Protocol.U)}}

  if(enableFfnWindow){
    val w=io.window.get;val p=banks.io.tiles.get;val active=windowActive.get
    val phase=windowPhase.get;val t=p.state(windowSlot.get)
    val expected=(job.m>>4)*windowCols.get
    val exact=t.live && t.identity===windowIdentity.get && t.ng===windowNg.get &&
      t.rows===job.m && t.cols===windowCols.get && t.expected===expected && t.matrixProducerOrder.get
    w.busy:=active;w.leaseValid:=aLeaseValid.get;w.resetRequired:=io.resetRequired
    w.request.ready:=state===idle && !active && !p.busy && p.drained && !p.resetRequired &&
      !io.tiles.get.control.valid && !io.tiles.get.write.valid && !io.tiles.get.read.valid && !io.tiles.get.abort
    io.job.ready:=state===idle && !active && !w.request.valid && !p.busy &&
      !io.tiles.get.control.valid && !io.tiles.get.write.valid && !io.tiles.get.read.valid && !io.tiles.get.abort
    w.result.valid:=active && state===finish
    if(enableKWindow){w.result.bits.kWindow.get:=kPolicy.get}
    w.result.bits.tag:=job.tag;w.result.bits.identity:=windowIdentity.get;w.result.bits.ng:=windowNg.get
    w.result.bits.cols:=windowCols.get;w.result.bits.slot:=windowSlot.get;w.result.bits.rows:=job.m
    w.result.bits.status:=status;w.result.bits.committed:=windowCommitted.get
    // A tag is not necessarily live after admission rejection. Never report another slot's work.
    w.result.bits.producedBeats:=Mux(windowBegun.get && exact,t.produced,0.U);w.result.bits.ddrWriteBytes:=0.U
    if(enableFfnDrain){
      w.result.bits.cycles.get:=cycles;w.result.bits.usefulMacs.get:=useful
      w.result.bits.executedMacs.get:=(io.physicalSteps-physicalBase)*512.U
    }
    when(w.request.fire){
      val r=w.request.bits;val j=r.job;val lease=aLease.get;val ws=io.prefixWorkspace.get
      workspace:=ws
      val rowStride=j.k.pad(64)*Mux(j.activationBf16,2.U(3.W),4.U(3.W))
      val reuseOK=aLeaseValid.get && !w.invalidateLease && lease.base===j.a && lease.activationBf16===j.activationBf16 &&
        lease.rows===j.m && lease.k===j.k && lease.rowStride===rowStride && lease.identity===r.identity
      val aEnd=j.a.pad(66)+j.m.pad(66)*rowStride
      val bEnd=j.b.pad(66)+j.k.pad(66)*j.n*Mux(j.weightBf16,2.U(3.W),4.U(3.W))
      val dEnd=j.dst.pad(66)+j.m.pad(66)*j.n*4.U
      val aliases=(j.a.pad(66)<dEnd && j.dst.pad(66)<aEnd)||(j.b.pad(66)<dEnd && j.dst.pad(66)<bEnd)
      val pEnd=ws.base.pad(66)+ws.extent.pad(66)
      val prefixAliases=Seq((j.a,aEnd),(j.b,bEnd),(j.dst,dEnd)).map{case(base,end)=>
        ws.base.pad(66)<end && base.pad(66)<pEnd}.reduce(_||_)
      val workspaceOK=ws.valid && ws.base(5,0)===0.U && ws.extent=/=0.U &&
        (!(j.k>ws.splitK) || ws.extent>=(j.n.pad(64)>>5)*16384.U) &&
        pEnd<=(BigInt(1)<<56).U && !prefixAliases && ws.generation=/=0.U &&
        ws.splitK=/=0.U && ws.splitK<=2560.U && ws.splitK(6,0)===0.U
      val shape=if(enableKWindow){
      val kShape={
        val k=r.kWindow.get
        !k.enabled || (k.begin<k.end && k.end<=j.k && !k.begin(0) && !k.end(0) &&
          k.blockId=/=0.U && !j.materializeDenseOutput)
      }
      val materializeShape= !officialBf16.B || r.kWindow.get.enabled || j.materializeDenseOutput
      kShape && materializeShape && workspaceOK && j.kind===QwenOwnerKind.Dense.U && (j.m===16.U || j.m===128.U) && j.k>0.U && j.k<=1536.U &&
        j.k(3,0)===0.U && (!j.activationBf16 || j.k(4,0)===0.U) && !j.outputBf16 &&
        j.n>0.U && j.n(4,0)===0.U && r.identity=/=0.U && r.ng(4,0)===0.U &&
        r.cols>0.U && r.cols<=160.U && r.cols(4,0)===0.U && r.slot<2.U &&
        r.ng.pad(17)+&r.cols.pad(17)<=j.n.pad(18) && j.a(5,0)===0.U && j.b(5,0)===0.U &&
        j.dst(5,0)===0.U && !aliases && dEnd<=(BigInt(1)<<56).U &&
        j.writeBytes===j.m.pad(64)*j.n*4.U &&
        aEnd<=(BigInt(1)<<56).U && bEnd<=(BigInt(1)<<56).U && groupSequence=/="hffffffff".U
      }else{
      (!officialBf16.B || j.materializeDenseOutput) && workspaceOK && j.kind===QwenOwnerKind.Dense.U && (j.m===16.U || j.m===128.U) && j.k>0.U && j.k<=1536.U &&
        j.k(3,0)===0.U && (!j.activationBf16 || j.k(4,0)===0.U) && !j.outputBf16 &&
        j.n>0.U && j.n(4,0)===0.U && r.identity=/=0.U && r.ng(4,0)===0.U &&
        r.cols>0.U && r.cols<=160.U && r.cols(4,0)===0.U && r.slot<2.U &&
        r.ng.pad(17)+&r.cols.pad(17)<=j.n.pad(18) && j.a(5,0)===0.U && j.b(5,0)===0.U &&
        j.dst(5,0)===0.U && !aliases && dEnd<=(BigInt(1)<<56).U &&
        j.writeBytes===j.m.pad(64)*j.n*4.U &&
        aEnd<=(BigInt(1)<<56).U && bEnd<=(BigInt(1)<<56).U && groupSequence=/="hffffffff".U
      }
      if(enableKWindow){kPolicy.get:=r.kWindow.get}
      windowActive.get:=true.B;windowIdentity.get:=r.identity;windowNg.get:=r.ng
      windowCols.get:=r.cols;windowSlot.get:=r.slot;windowReuse.get:=r.reuseA
      windowBegun.get:=false.B;windowCommitted.get:=false.B;windowPhase.get:=1.U
      job:=j;status:=0.U;cycles:=0.U;bytes:=0.U;useful:=0.U;issued:=0.U;starved:=0.U
      cycleBuckets:=VecInit(Seq.fill(7)(0.U(64.W)));physicalBase:=io.physicalSteps
      restoring:=false.B;prefixValid:=false.B;prefixAckBytes:=0.U;seedState:=seedIdle
      chunkBase:=0.U;committedPrefixEnd:=0.U;restoredContexts:=0.U;savedContexts:=0.U;sweepAckBytes:=0.U
      zeroWord:=0.U;aRow:=0.U;aBeat:=0.U;aHighPending:=false.B;nBase:=r.ng
      aCommitted:=r.reuseA && reuseOK
      groupStarted:=false.B;groupDone:=false.B;written:=0.U;captured:=0.U;writeState:=writeIdle
      loadState:=loadIdle;halfReady:=VecInit(Seq.fill(2)(false.B));allRead:=false.B
      when(!r.reuseA){aLeaseValid.get:=false.B}
      when(!shape || p.state(r.slot).live){status:=Status.Bounds.U;state:=finish;aLeaseValid.get:=false.B}
      .elsewhen(r.reuseA && !reuseOK){status:=Status.Protocol.U;state:=finish;aLeaseValid.get:=false.B}
    }
    when(active && status===0.U && state=/=finish && !p.resetRequired && !io.tiles.get.abort){
      when(phase===1.U || phase===4.U){
        p.control.valid:=true.B;p.control.bits.op:=Mux(phase===1.U,0.U,1.U)
        p.control.bits.slot:=windowSlot.get;p.control.bits.identity:=windowIdentity.get;p.control.bits.ng:=windowNg.get
        p.control.bits.rows:=job.m;p.control.bits.cols:=windowCols.get;p.control.bits.matrixProducerOrder.get:=true.B
        when(p.control.fire){phase:=Mux(phase===1.U,2.U,5.U)}
      }
      when(phase===2.U){
        when(exact && !t.sealedTile && t.produced===0.U && t.consumed===0.U && p.drained){
          windowBegun.get:=true.B;phase:=3.U;state:=Mux(windowReuse.get,setup,clearA)
        }.otherwise{fail(Status.Protocol.U);state:=drain}
      }
      // finalValue is the sole existing 16 KiB result hold. The existing
      // eight-bit prefix cursor walks g:j; no second tensor is allocated.
      // Wait only for the synchronous bank response, not the operand FIFO:
      // waiting for FIFO-empty can deadlock the bounded Matrix result queue.
      when(phase===3.U && state===execute && writeState===writeReq && !banks.io.response.valid){
        p.write.valid:=true.B;p.write.bits.key.slot:=windowSlot.get
        p.write.bits.key.identity:=windowIdentity.get;p.write.bits.key.ng:=windowNg.get
        p.write.bits.key.index:=prefixWriteIndex(7,5)*windowCols.get+(writeContext.pad(11)<<5)+prefixWriteIndex(4,0)
        for(l<-0 until 16){
          val raw=finalValue(prefixWriteIndex(3,0))(Cat(prefixWriteIndex(4),prefixWriteIndex(7,5),l.U(4.W)))
          p.write.bits.value(l):=(if(officialBf16)Mux(job.materializeDenseOutput,F32.bf(raw),raw)else raw)
        }
        when(p.write.fire){writeState:=writeWait}
      }
      // write.fire only accepted a RMW read; observe the bank's next-cycle
      // committed count and drained fence before advancing the shared cursor.
      when(phase===3.U && state===execute && writeState===writeWait && p.drained){
        val committedBefore=Mux(job.m===16.U,writeContext.pad(11)<<5,writeContext.pad(11)<<8)+prefixWriteIndex
        when(!exact || t.sealedTile || t.produced=/=committedBefore+1.U){fail(Status.Protocol.U)}
        .otherwise{
          when(prefixWriteIndex===Mux(job.m===16.U,31.U,255.U)){written:=written+1.U;writeState:=writeIdle}
          .otherwise{prefixWriteIndex:=prefixWriteIndex+1.U;writeState:=writeReq}
        }
      }
      when(phase===5.U){
        when(exact && t.sealedTile && t.produced===expected && t.consumed===0.U &&
          groupDone && captured===contexts && written===contexts && p.drained && operandsEmpty &&
          !burstOutstanding && !seedOutstanding && writeState===writeIdle){
          windowCommitted.get:=true.B;state:=finish
        }.otherwise{fail(Status.Protocol.U);state:=drain}
      }
    }
    when(active){
      // writeWait belongs to the tile RMW path, never a DDR acknowledgement.
      ackFire:=false.B;io.response.ready:=false.B
      if(burstWrites){io.writeResponse.get.ready:=false.B}
    }
    // Only real low-A mutations invalidate the retained activation lease.
    // aFence follows the final DMA return, BF16 upper-half write and RMW commit.
    when(w.invalidateLease || io.job.fire || banks.io.zero.valid || banks.io.activation.fire || status=/=0.U || p.resetRequired || io.tiles.get.abort){aLeaseValid.get:=false.B}
    when(active && state===aFence && !aHighPending && !banks.io.activationBusy && status===0.U && !p.resetRequired && !io.tiles.get.abort && !w.invalidateLease){
      aLease.get.base:=job.a;aLease.get.activationBf16:=job.activationBf16
      aLease.get.rows:=job.m;aLease.get.k:=job.k
      aLease.get.rowStride:=job.k.pad(64)*Mux(job.activationBf16,2.U(3.W),4.U(3.W))
      aLease.get.identity:=windowIdentity.get;aLeaseValid.get:=true.B
    }
    // An abort before the existing FSM leaves idle must still enter drain.
    when(active && state===idle && (status=/=0.U || p.resetRequired || io.tiles.get.abort)){
      fail(Status.Protocol.U);state:=drain
    }
    // Internal RMW writeWait is not an outstanding DDR ACK. Its physical edge
    // retires even on poison; preserve it until the bank reports drained.
    when(active && status=/=0.U && writeState===writeWait && p.drained){writeState:=writeIdle}
    when(w.result.fire){windowActive.get:=false.B;phase:=0.U;state:=Mux(status===0.U && !io.resetRequired,idle,locked)}
    when(w.result.valid){assert(!io.done.valid && bytes===0.U,"internal window cannot masquerade as DDR completion")}
  }
  if(enableFfnDrain){
    val d=io.drain.get;val p=banks.io.tiles.get;val active=drainActive.get
    val phase=drainPhase.get;val pending=drainReadPending.get;val t=p.state(2)
    val expected=(job.m>>4)*drainCols.get
    val index=(writeRow.pad(11)>>4)*drainCols.get+prefixWriteIndex
    val exact=t.live && t.sealedTile && t.identity===drainIdentity.get && t.ng===drainNg.get &&
      t.rows===job.m && t.cols===drainCols.get && t.expected===expected && t.produced===expected &&
      !t.matrixProducerOrder.getOrElse(false.B)
    val rawAck=if(burstWrites)io.writeResponse.get.valid else io.response.valid
    val unexpectedAck=if(burstWrites)rawAck && writeState=/=writeWait && writeState=/=writeData else rawAck && writeState=/=writeWait
    val activeUnexpected=p.response.valid && !pending || unexpectedAck || io.matrix.result.valid || io.burstResponse.valid
    val bad=io.tiles.get.abort || d.abort || p.resetRequired || drainPoison.get || status=/=0.U || (active && activeUnexpected)
    val ackGood=ackFire && !ackBits.error && ackBits.tag===writeTag
    val matching=p.response.bits.key.slot===2.U && p.response.bits.key.identity===drainIdentity.get &&
      p.response.bits.key.ng===drainNg.get && p.response.bits.key.index===index
    val noExternal= !io.tiles.get.control.valid && !io.tiles.get.write.valid && !io.tiles.get.read.valid
    val windowIdle= !windowActive.getOrElse(false.B)
    val idleUnexpected=state===idle && (rawAck || io.burstResponse.valid || io.matrix.result.valid)
    d.request.ready:=state===idle && !active && windowIdle &&
      !io.window.map(_.request.valid).getOrElse(false.B) && !p.busy && p.drained && noExternal && !bad && !idleUnexpected
    // Window has priority over drain, drain has priority over the normal job.
    io.job.ready:=state===idle && windowIdle && !active && !d.request.valid && !io.window.map(_.request.valid).getOrElse(false.B) && !p.busy && noExternal && !bad && !idleUnexpected
    if(enableFfnWindow){io.window.get.request.ready:=state===idle && windowIdle && !active && !p.busy && p.drained && noExternal && !bad && !idleUnexpected}
    d.busy:=active;d.resetRequired:=io.resetRequired
    io.resetRequired:=(status=/=0.U) || p.resetRequired || io.tiles.get.abort || drainPoison.get || d.abort || idleUnexpected || (active && activeUnexpected)
    d.result.valid:=active && state===finish
    d.result.bits.tag:=job.tag;d.result.bits.identity:=drainIdentity.get;d.result.bits.ng:=drainNg.get
    d.result.bits.rows:=job.m;d.result.bits.cols:=drainCols.get;d.result.bits.status:=status
    d.result.bits.committed:=drainCommitted.get;d.result.bits.consumedBeats:=drainConsumed.get
    d.result.bits.ddrWriteBytes:=bytes;d.result.bits.cycles:=cycles;d.result.bits.usefulMacs:=useful
    d.result.bits.executedMacs:=(io.physicalSteps-physicalBase)*512.U
    when(d.request.fire){
      val r=d.request.bits;val j=r.job;val ws=io.prefixWorkspace.get
      // The output is FP32 for both modes. Dense carries its ORIGINAL Job:
      // full A and B spans retain K and their source dtype, even for a narrow ng.
      val size=j.m.pad(66)*j.n*4.U
      val aEnd=if(enableDenseDrain){
        j.a.pad(66)+Mux(j.kind===QwenOwnerKind.Dense.U,
          j.m.pad(66)*j.k*Mux(j.activationBf16,2.U(3.W),4.U(3.W)),size)
      }else j.a.pad(66)+size
      val bEnd=if(enableDenseDrain){
        j.b.pad(66)+Mux(j.kind===QwenOwnerKind.Dense.U,
          j.k.pad(66)*j.n*Mux(j.weightBf16,2.U(3.W),4.U(3.W)),size)
      }else j.b.pad(66)+size
      val dEnd=j.dst.pad(66)+size
      val pEnd=ws.base.pad(66)+ws.extent.pad(66)
      val spans=Seq((j.a,aEnd),(j.b,bEnd),(j.dst,dEnd))
      val disjoint=(for(i<-spans.indices;k<-i+1 until spans.size)yield
        !(spans(i)._1.pad(66)<spans(k)._2 && spans(k)._1.pad(66)<spans(i)._2)).reduce(_&&_)
      val workspaceOK=ws.valid && ws.base(5,0)===0.U && ws.extent=/=0.U && pEnd<=(BigInt(1)<<56).U &&
        ws.generation=/=0.U && ws.splitK=/=0.U && ws.splitK<=2560.U && ws.splitK(6,0)===0.U &&
        spans.map{case(base,end)=> !(ws.base.pad(66)<end && base.pad(66)<pEnd)}.reduce(_&&_)
      val shape=if(enableDenseDrain){
        val activationShape=j.kind===QwenOwnerKind.Activation.U && (j.m===16.U || j.m===128.U) &&
          j.n===8960.U && j.k===8960.U && !j.activationBf16 && !j.weightBf16 && !j.outputBf16
        val denseShape=j.kind===QwenOwnerKind.Dense.U && (j.m===16.U || j.m===128.U) &&
          j.m<=j.k && j.k<=1536.U && j.n>0.U && j.n<=j.k && j.n(4,0)===0.U &&
          j.k(3,0)===0.U && (!j.activationBf16 || j.k(4,0)===0.U) &&
          !j.outputBf16 && !j.materializeDenseOutput
        (activationShape || denseShape) &&
        j.writeBytes===size && disjoint && workspaceOK &&
        spans.map{case(base,end)=>base(5,0)===0.U && end<=(BigInt(1)<<56).U}.reduce(_&&_) &&
        r.identity=/=0.U && r.ng(4,0)===0.U && r.cols>0.U && r.cols<=160.U && r.cols(4,0)===0.U &&
        r.ng.pad(17)+&r.cols.pad(17)<=j.n.pad(18)
      }else{
        j.kind===QwenOwnerKind.Activation.U && (j.m===16.U || j.m===128.U) &&
        j.n===8960.U && j.k===8960.U && !j.activationBf16 && !j.weightBf16 && !j.outputBf16 &&
        j.writeBytes===size && disjoint && workspaceOK &&
        spans.map{case(base,end)=>base(5,0)===0.U && end<=(BigInt(1)<<56).U}.reduce(_&&_) &&
        r.identity=/=0.U && r.ng(4,0)===0.U && r.cols>0.U && r.cols<=160.U && r.cols(4,0)===0.U &&
        r.ng.pad(17)+&r.cols.pad(17)<=j.n.pad(18)
      }
      val slotOK=t.live && t.sealedTile && t.identity===r.identity && t.ng===r.ng && t.rows===j.m &&
        t.cols===r.cols && t.expected===(j.m>>4)*r.cols && t.produced===t.expected && t.consumed===0.U &&
        !t.matrixProducerOrder.getOrElse(false.B)
      active:=true.B;drainIdentity.get:=r.identity;drainNg.get:=r.ng;drainCols.get:=r.cols
      drainConsumed.get:=0.U;drainCommitted.get:=false.B;pending:=false.B;phase:=1.U
      job:=j;workspace:=ws;status:=0.U;cycles:=0.U;bytes:=0.U;useful:=0.U;issued:=0.U;starved:=0.U
      cycleBuckets:=VecInit(Seq.fill(7)(0.U(64.W)));physicalBase:=io.physicalSteps
      writeState:=writeIdle;writeRow:=0.U;prefixWriteIndex:=0.U;writeContext:=0.U;writeBeat:=false.B
      groupStarted:=false.B;groupDone:=false.B;loadState:=loadIdle;seedState:=seedIdle
      aHighPending:=false.B;allRead:=true.B;halfReady:=VecInit(Seq.fill(2)(false.B));state:=drain
      when(!shape || !slotOK){status:=Status.Bounds.U;state:=finish;phase:=0.U}
    }
    when(active){
      // This mode issues no Matrix, A load, prefix restore or tile write.
      io.matrix.group.valid:=false.B;io.matrix.step.valid:=false.B;io.matrix.result.ready:=false.B
      banks.io.read.valid:=false.B;p.write.valid:=false.B;p.control.valid:=false.B;p.read.valid:=false.B
      p.response.ready:=pending
      if(burstWrites){
        io.writeRequest.get.valid:=phase===3.U && writeState===writeReq && !bad
        // Accepted bursts must send every beat even after poison.
        io.writeData.get.valid:=writeState===writeData
        io.writeResponse.get.ready:=writeState===writeWait
      }else{
        io.memory.valid:=phase===3.U && writeState===writeReq && !bad
        io.response.ready:=writeState===writeWait
      }
      when(state=/=finish){cycleClass:=Mux(phase===3.U,4.U,0.U)}
      when(!bad && state=/=finish){
        when(phase===1.U){
          when(!exact || t.consumed=/=drainConsumed.get){fail(Status.Protocol.U)}
          .otherwise{
            p.read.valid:=true.B;p.read.bits.slot:=2.U;p.read.bits.identity:=drainIdentity.get
            p.read.bits.ng:=drainNg.get;p.read.bits.index:=index
            when(p.read.fire){pending:=true.B;phase:=2.U}
          }
        }
        when(phase===4.U){
          when(!exact || t.consumed=/=expected || drainConsumed.get=/=expected || bytes=/=job.m.pad(64)*drainCols.get*4.U){fail(Status.Protocol.U)}
          .elsewhen(p.drained && !pending && writeState===writeIdle){
            p.control.valid:=true.B;p.control.bits.op:=2.U;p.control.bits.slot:=2.U
            p.control.bits.identity:=drainIdentity.get;p.control.bits.ng:=drainNg.get
            p.control.bits.rows:=job.m;p.control.bits.cols:=drainCols.get
            p.control.bits.matrixProducerOrder.foreach(_:=false.B)
            when(p.control.fire){phase:=5.U}
          }
        }
        // Release acceptance is not completion. Check the next-cycle state.
        when(phase===5.U){
          when(!t.live && !t.sealedTile && p.drained && !pending && writeState===writeIdle &&
            t.identity===drainIdentity.get && t.ng===drainNg.get && t.rows===job.m && t.cols===drainCols.get &&
            t.consumed===expected && drainConsumed.get===expected && bytes===job.m.pad(64)*drainCols.get*4.U){
            drainCommitted.get:=true.B;state:=finish
          }.otherwise{fail(Status.Protocol.U)}
        }
      }
      when(p.response.fire){
        pending:=false.B
        when(matching){drainConsumed.get:=drainConsumed.get+1.U}
        when(!matching || p.response.bits.error){fail(Mux(p.response.bits.error,Status.Numerical.U,Status.Protocol.U))}
        .elsewhen(!bad){
          for(l<-0 until 16){finalValue(l)(prefixWriteIndex):=p.response.bits.value(l)}
          when(prefixWriteIndex+1.U===drainCols.get){
            prefixWriteIndex:=0.U;writeContext:=0.U;writeBeat:=false.B;writeState:=writeReq;phase:=3.U
          }.otherwise{prefixWriteIndex:=prefixWriteIndex+1.U;phase:=1.U}
        }
      }
      when(ackFire){
        when(!ackGood){fail(Mux(ackBits.error,Status.Memory.U,Status.Protocol.U));writeState:=writeIdle}
        .otherwise{
          // Actual physical ACK bytes remain reportable even on an abort edge.
          bytes:=bytes+(ackBeats.pad(64)<<6);writeSequence:=writeSequence+1.U
          when(bad){writeState:=writeIdle}
          .elsewhen(drainRowBeat.get+&ackBeats===(drainCols.get>>4)){
            writeContext:=0.U;writeBeat:=false.B
            when(writeRow+&1.U===job.m){writeState:=writeIdle;phase:=4.U}
            .otherwise{
              writeRow:=writeRow+1.U
              when(writeRow(3,0)===15.U){writeState:=writeIdle;prefixWriteIndex:=0.U;phase:=1.U}
              .otherwise{writeState:=writeReq}
            }
          }.otherwise{
            val next=drainRowBeat.get+ackBeats;writeContext:=next(3,1);writeBeat:=next(0);writeState:=writeReq
          }
        }
      }
      when(activeUnexpected){drainPoison.get:=true.B;when(state=/=finish){fail(Status.Protocol.U)}}
      when(bad && state=/=finish){
        fail(Status.Protocol.U);phase:=6.U;drainCommitted.get:=false.B
        when(writeState===writeReq){writeState:=writeIdle}
        when(!pending && p.drained && writeState=/=writeData && writeState=/=writeWait){state:=finish}
      }
    }
    val idleAck=if(burstWrites)io.writeResponse.get.valid else io.response.valid
    when(idleUnexpected || ((state===locked || state===finish) && !active && !windowActive.getOrElse(false.B) && idleAck)){drainPoison.get:=true.B}
    when(d.abort){drainPoison.get:=true.B}
    if(enableFfnWindow){when(d.abort || drainPoison.get){aLeaseValid.get:=false.B}}
    when(d.result.fire){active:=false.B;phase:=0.U;state:=Mux(status===0.U && !io.resetRequired,idle,locked)}
    when(d.result.valid){assert(!io.done.valid && !windowActive.getOrElse(false.B));assert(cycleBuckets.reduce(_+&_)===cycles)}
  }
  when(io.done.fire){state:=Mux(status===0.U,idle,locked)}
}

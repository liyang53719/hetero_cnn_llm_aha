// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** One fixed32 V4 bank shared by three raw scalar-format and two raw16 vector
  * clients. Three raw Scalar clients borrow the EXISTING Core V3 endpoint;
  * ZERO Scalar/ALU/formatter primitives are added outside this one V4 bank.
  *
  * Whole-group scope: token/tile/phase/head/chunk are explicitly zero. Full
  * txn64/owner32/stage/serial32 come only from accepted lease snapshots. The
  * original children retain their real token/tile progress; no tile authority
  * is inferred from an untagged raw arithmetic request.
  *
  * V4 has no lane mask: raw16 uses low16 plus sixteen actual +0 lanes; format
  * uses lane0 plus31 +0 lanes. These lanes still physically compute. Neither
  * this compatibility path nor its clients claim32 useful results/cycle.
  * Bank ingress1+bank held result1 are two fixed credits. Scalar is deliberately
  * one accepted operation at a time, and physical issued is observed from the
  * real Core cumulative primitive counter, NOT from its frontend request.fire.
  */
class UnifiedMoeSharedArithmeticAdapterV5 extends Module {
  private val N=UnifiedMoeArithmeticClientV5.Count
  val io=IO(new Bundle {
    val acquire=Input(Vec(N,Valid(new UnifiedMoeArithmeticLeaseV5)))
    val retire=Input(Vec(N,Valid(new UnifiedMoeArithmeticRetireV5)))
    val scalar=Flipped(Vec(3,new UnifiedScalarClientV2))
    val formatRequest=Flipped(Vec(3,Decoupled(new UnifiedRawFp32FormatRequestV3)))
    val formatResult=Vec(3,Decoupled(new UnifiedRawFp32FormatResultV3))
    val vectorRequest=Flipped(Vec(2,Decoupled(new UnifiedVectorRequestV2)))
    val vectorResult=Vec(2,Decoupled(new UnifiedVectorResultV2))
    val coreScalar=Flipped(new QwenSharedScalarServiceV3)
    val externalPoison=Input(Bool()) // error-only; never authorization or drain
    val status=Output(Vec(N,new UnifiedMoeArithmeticClientStatusV5))
    val resourcesDrained=Output(Bool());val resetRequired=Output(Bool())
  })
  val bank=Module(new UnifiedVectorElement32BankV4) // exactly ONE physical bank
  val leases=Reg(Vec(N,new UnifiedMoeArithmeticLeaseV5))
  val active=RegInit(VecInit(Seq.fill(N)(false.B)))
  val retiring=RegInit(VecInit(Seq.fill(N)(false.B)))
  val havePrevious=RegInit(VecInit(Seq.fill(N)(false.B)))
  val terminalStatus=Reg(Vec(N,UInt(8.W)))
  val accepted=RegInit(VecInit(Seq.fill(N)(0.U(33.W))))
  val issued=RegInit(VecInit(Seq.fill(N)(0.U(33.W))))
  val returned=RegInit(VecInit(Seq.fill(N)(0.U(33.W))))
  val poison=RegInit(false.B)
  val scalarQuarantine=RegInit(false.B);val vectorQuarantine=RegInit(false.B)
  val eventFault=WireDefault(false.B)
  val rawValid=Wire(Vec(N,Bool()))
  for(i<-0 until 3){rawValid(i):=io.scalar(i).request.valid;rawValid(i+3):=io.formatRequest(i).valid}
  for(i<-0 until 2)rawValid(i+6):=io.vectorRequest(i).valid
  val countBad=VecInit((0 until N).map(i=>returned(i)>issued(i) || issued(i)>accepted(i) ||
    accepted(i)(32) || issued(i)(32) || returned(i)(32)))
  val overrun=VecInit((0 until N).map(i=>active(i) && !retiring(i) && rawValid(i) &&
    (accepted(i)>=leases(i).lease.expectedOperations.pad(33) || accepted(i)==="hffffffff".U)))

  // The immutable packet doubles as retained response identity; no copied
  // numerical result. Core's own held output is the only Scalar result buffer.
  val sOffer=RegInit(false.B);val sSubmitted=RegInit(false.B);val sIssuedSeen=RegInit(false.B)
  val sPacket=Reg(new QwenSharedScalarRequestV3);val sClient=Reg(UInt(3.W))
  val coreIssuedLast=RegInit(0.U(33.W))
  val coreIssued=io.coreScalar.status.counts.issued
  val coreIssueDelta=coreIssued-coreIssuedLast
  val coreIssueChanged=coreIssued=/=coreIssuedLast
  val coreIssueMalformed=coreIssued<coreIssuedLast || coreIssueDelta>1.U ||
    (coreIssueChanged && (!sSubmitted || sIssuedSeen))
  coreIssuedLast:=coreIssued
  val scalarIssue=coreIssueChanged && !coreIssueMalformed && sSubmitted && !sIssuedSeen
  val scalarIssuedNow=sIssuedSeen || scalarIssue
  val scalarIdentity=io.coreScalar.result.bits.identity.asUInt===sPacket.identity.asUInt &&
    io.coreScalar.result.bits.payload.policy===sPacket.payload.policy
  val unknownScalar=io.coreScalar.result.valid && (!sSubmitted || !scalarIssuedNow || !scalarIdentity)
  when(unknownScalar || coreIssueMalformed){scalarQuarantine:=true.B}
  val scalarResponseOwned=sSubmitted && scalarIssuedNow && scalarIdentity &&
    !scalarQuarantine && !unknownScalar && !coreIssueMalformed
  io.coreScalar.request.valid:=sOffer;io.coreScalar.request.bits:=sPacket
  io.coreScalar.result.ready:=scalarResponseOwned &&
    MuxLookup(sClient,false.B)((0 until 3).map(i=>i.U->io.scalar(i).result.ready))
  for(i<-0 until 3){
    io.scalar(i).result.valid:=io.coreScalar.result.valid && scalarResponseOwned && sClient===i.U
    io.scalar(i).result.bits:=io.coreScalar.result.bits.payload
  }
  when(io.coreScalar.request.fire){sOffer:=false.B;sSubmitted:=true.B;sIssuedSeen:=false.B}
  when(scalarIssue){sIssuedSeen:=true.B}
  val scalarReturn=io.coreScalar.result.fire
  when(scalarReturn){sSubmitted:=false.B}

  // Exactly one accepted ingress and one bank-held result. Push wins pop in
  // both slots, so physical bank refill and ingress refill can occur together.
  val vOffer=RegInit(false.B);val vPacket=Reg(new UnifiedVectorElement32RequestV4)
  val vOfferClient=Reg(UInt(3.W));val vOfferRawPolicy=Reg(UInt(2.W))
  val vPending=RegInit(false.B);val vTag=Reg(new UnifiedSharedOperationTagV3)
  val vClient=Reg(UInt(3.W));val vPolicy=Reg(UInt(3.W));val vRawPolicy=Reg(UInt(2.W))
  bank.io.request.valid:=vOffer;bank.io.request.bits:=vPacket
  val vectorIdentity=bank.io.result.bits.identity.asUInt===vTag.asUInt &&
    bank.io.result.bits.payload.policy===vPolicy &&
    bank.io.result.bits.payload.arithFlagsValid===(vClient>=6.U) &&
    !bank.io.result.bits.payload.formatFlagsValid
  val unknownVector=bank.io.result.valid && (!vPending || !vectorIdentity)
  when(unknownVector){vectorQuarantine:=true.B}
  val vectorResponseOwned=vPending && vectorIdentity && !vectorQuarantine && !unknownVector
  val vectorConsumerReady=MuxLookup(vClient,false.B)(
    (0 until 3).map(i=>(i+3).U->io.formatResult(i).ready)++
    (0 until 2).map(i=>(i+6).U->io.vectorResult(i).ready))
  bank.io.result.ready:=vectorResponseOwned && vectorConsumerReady
  for(i<-0 until 3){
    io.formatResult(i).valid:=bank.io.result.valid && vectorResponseOwned && vClient===(i+3).U
    io.formatResult(i).bits.value:=bank.io.result.bits.payload.value(0)(31,16)
    io.formatResult(i).bits.error:=bank.io.result.bits.payload.error
  }
  for(i<-0 until 2){
    io.vectorResult(i).valid:=bank.io.result.valid && vectorResponseOwned && vClient===(i+6).U
    io.vectorResult(i).bits.policy:=vRawPolicy
    for(j<-0 until 16){
      io.vectorResult(i).bits.value(j):=bank.io.result.bits.payload.value(j)
      io.vectorResult(i).bits.flags(j):=bank.io.result.bits.payload.arithFlags(j)
    }
    // Old raw policy3 is unsupported. Route it through real BF16 policy2
    // arithmetic to preserve its diagnostic values/flags, but retain the old
    // unconditional error. Never reinterpret it as V4's valid gradual policy3.
    io.vectorResult(i).bits.error:=bank.io.result.bits.payload.error || vRawPolicy===3.U
  }
  val vectorIssue=bank.io.request.fire;val vectorReturn=bank.io.result.fire
  when(vectorIssue){
    vTag:=vPacket.identity;vClient:=vOfferClient;vPolicy:=vPacket.payload.policy
    vRawPolicy:=vOfferRawPolicy;vPending:=true.B
  }.elsewhen(vectorReturn){vPending:=false.B}

  val numericalFault=(io.coreScalar.result.valid && scalarResponseOwned && io.coreScalar.result.bits.payload.error) ||
    (bank.io.result.valid && vectorResponseOwned &&
      (bank.io.result.bits.payload.error || (vClient>=6.U && vRawPolicy===3.U)))
  val terminalError=io.retire.map(r=>r.valid && r.bits.status=/=Status.Ok.U).reduce(_||_)
  val serviceFault=countBad.asUInt.orR || overrun.asUInt.orR || unknownScalar ||
    unknownVector || coreIssueMalformed || io.coreScalar.status.resetRequired || numericalFault ||
    terminalError || io.externalPoison
  val currentFault=eventFault || serviceFault
  when(currentFault){poison:=true.B}
  io.resetRequired:=poison || scalarQuarantine || vectorQuarantine || currentFault
  // Only fresh acceptance is stopped. Captured physical offers and matched
  // results above are NEVER gated by ordinary poison or terminal intent.
  val admit= !poison && !currentFault && !scalarQuarantine && !vectorQuarantine
  def clientMayAccept(i:Int):Bool=active(i) && !retiring(i) && !io.retire(i).valid &&
    !io.acquire(i).valid && !countBad(i) && accepted(i)<leases(i).lease.expectedOperations.pad(33) &&
    accepted(i)<"hffffffff".U

  val sarb=Module(new RRArbiter(new QwenSharedScalarRequestV3,3))
  for(i<-0 until 3){
    sarb.io.in(i).valid:=io.scalar(i).request.valid && clientMayAccept(i)
    sarb.io.in(i).bits.identity.owner:=leases(i).lease.identity
    sarb.io.in(i).bits.identity.resource:=2.U;sarb.io.in(i).bits.identity.serial:=accepted(i)(31,0)
    sarb.io.in(i).bits.payload:=io.scalar(i).request.bits
    io.scalar(i).request.ready:=sarb.io.in(i).ready && clientMayAccept(i)
  }
  sarb.io.out.ready:= !sOffer && !sSubmitted && !io.coreScalar.result.valid && admit
  val scalarAccept=sarb.io.out.fire;val scalarAcceptClient=sarb.io.chosen.pad(3)
  when(scalarAccept){sPacket:=sarb.io.out.bits;sClient:=scalarAcceptClient;sOffer:=true.B}

  val varb=Module(new RRArbiter(new UnifiedVectorElement32RequestV4,5))
  for(i<-0 until 5){
    val client=i+3
    varb.io.in(i).valid:=rawValid(client) && clientMayAccept(client)
    varb.io.in(i).bits:=0.U.asTypeOf(new UnifiedVectorElement32RequestV4)
    varb.io.in(i).bits.identity.owner:=leases(client).lease.identity
    varb.io.in(i).bits.identity.resource:=1.U
    varb.io.in(i).bits.identity.serial:=accepted(client)(31,0)
    if(i<3){
      varb.io.in(i).bits.payload.policy:=UnifiedVectorElement32PolicyV4.RawFp32ToBf16Rne.U
      varb.io.in(i).bits.payload.a(0):=io.formatRequest(i).bits.value
      io.formatRequest(i).ready:=varb.io.in(i).ready && clientMayAccept(client)
    }else{
      val raw=io.vectorRequest(i-3).bits
      varb.io.in(i).bits.payload.policy:=Mux(raw.policy===3.U,
        UnifiedVectorElement32PolicyV4.Bf16AddRne.U,raw.policy.pad(3))
      varb.io.in(i).bits.payload.multiply:=raw.multiply
      for(j<-0 until 16){varb.io.in(i).bits.payload.a(j):=raw.a(j);varb.io.in(i).bits.payload.b(j):=raw.b(j)}
      io.vectorRequest(i-3).ready:=varb.io.in(i).ready && clientMayAccept(client)
    }
  }
  varb.io.out.ready:=(!vOffer || bank.io.request.ready) && admit
  val vectorAccept=varb.io.out.fire;val vectorAcceptClient=varb.io.chosen.pad(3)+3.U
  val selectedRawPolicy=MuxLookup(varb.io.chosen,0.U(2.W))(
    Seq(3.U->io.vectorRequest(0).bits.policy,4.U->io.vectorRequest(1).bits.policy))
  when(vectorAccept){
    vPacket:=varb.io.out.bits;vOfferClient:=vectorAcceptClient;vOfferRawPolicy:=selectedRawPolicy;vOffer:=true.B
  }.elsewhen(vectorIssue){vOffer:=false.B}

  // Authoritative acquisition is an external actual-event input, not a
  // manufactured grant. Raw valid before a lease merely receives backpressure.
  for(i<-0 until N){
    val a=io.acquire(i).bits;val id=a.lease.identity;val previous=leases(i)
    val fresh= !havePrevious(i) || id.transactionId>previous.lease.identity.transactionId ||
      (id.transactionId===previous.lease.identity.transactionId &&
        id.ownerSequence>previous.lease.identity.ownerSequence &&
        a.allocationSequence===previous.allocationSequence && a.hostEpoch===previous.hostEpoch)
    val groupScope=id.phase===0.U && id.head===0.U && id.chunk===0.U && id.token===0.U && id.tileOrdinal===0.U
    val legal=groupScope && id.stage===UnifiedMoeArithmeticClientV5.Stages(i).U &&
      a.lease.resource===UnifiedMoeArithmeticClientV5.Resources(i).U && id.ownerSequence=/="hffffffff".U &&
      a.lease.expectedOperations>0.U && a.lease.expectedOperations<=UnifiedMoeArithmeticClientV5.MaximumOperations(i).U &&
      a.allocationSequence=/=0.U && fresh
    when(io.acquire(i).valid){
      when(!active(i) && !retiring(i) && !io.retire(i).valid && legal && !poison &&
        !scalarQuarantine && !vectorQuarantine && !serviceFault){
        leases(i):=a;active(i):=true.B;havePrevious(i):=true.B
        accepted(i):=0.U;issued(i):=0.U;returned(i):=0.U
      }.otherwise{eventFault:=true.B}
    }
    val knownStatus=io.retire(i).bits.status===Status.Ok.U ||
      (io.retire(i).bits.status>=Status.Malformed.U && io.retire(i).bits.status<=Status.Permission.U)
    when(io.retire(i).valid){
      when(active(i) && !retiring(i) && !io.acquire(i).valid && knownStatus &&
        io.retire(i).bits.lease.asUInt===leases(i).asUInt){
        retiring(i):=true.B;terminalStatus(i):=io.retire(i).bits.status
        when(io.retire(i).bits.status=/=Status.Ok.U){poison:=true.B}
      }.otherwise{eventFault:=true.B}
    }
    when((scalarAccept && scalarAcceptClient===i.U) || (vectorAccept && vectorAcceptClient===i.U)){
      accepted(i):=accepted(i)+1.U
    }
    when((scalarIssue && sClient===i.U) || (vectorIssue && vOfferClient===i.U)){
      issued(i):=issued(i)+1.U
    }
    when((scalarReturn && sClient===i.U) || (vectorReturn && vClient===i.U)){
      returned(i):=returned(i)+1.U
    }
    val held=(sOffer && sClient===i.U) || (sSubmitted && sClient===i.U) ||
      (vOffer && vOfferClient===i.U) || (vPending && vClient===i.U)
    val domainQuarantine=if(i<3)scalarQuarantine || unknownScalar || coreIssueMalformed
      else vectorQuarantine || unknownVector
    val drained= !held && !rawValid(i) && !countBad(i) && !domainQuarantine &&
      accepted(i)===issued(i) && issued(i)===returned(i)
    when(retiring(i) && rawValid(i)){eventFault:=true.B}
    when(retiring(i) && drained && terminalStatus(i)===Status.Ok.U &&
      returned(i)=/=leases(i).lease.expectedOperations.pad(33)){eventFault:=true.B}
    when(retiring(i) && drained){
      when(terminalStatus(i)=/=Status.Ok.U){active(i):=false.B;retiring(i):=false.B}
      .elsewhen(returned(i)===leases(i).lease.expectedOperations.pad(33) && !poison && !currentFault){
        active(i):=false.B;retiring(i):=false.B
      }.otherwise{poison:=true.B}
    }
    io.status(i).lease:=leases(i);io.status(i).active:=active(i);io.status(i).retiring:=retiring(i)
    io.status(i).counts.accepted:=accepted(i);io.status(i).counts.issued:=issued(i);io.status(i).counts.returned:=returned(i)
    io.status(i).resourcesDrained:=drained
  }
  // Mere active reservation is excluded, but actual offer/pending/held/raw
  // responses and the underlying Core's physical state are never excluded.
  io.resourcesDrained:= !sOffer && !sSubmitted && !vOffer && !vPending &&
    !io.coreScalar.result.valid && !bank.io.result.valid && io.coreScalar.status.resourcesDrained &&
    !rawValid.asUInt.orR && !scalarQuarantine && !vectorQuarantine && !unknownScalar && !unknownVector &&
    !coreIssueMalformed && !countBad.asUInt.orR &&
    (0 until N).map(i=>accepted(i)===issued(i) && issued(i)===returned(i)).reduce(_&&_)
}

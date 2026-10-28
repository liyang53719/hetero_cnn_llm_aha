// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** One fixed32 V4 bank shared by four raw scalar-format, two legacy raw16
  * vector clients and one private ordinary raw16/format16 client. Four raw
  * Scalar clients borrow the EXISTING Core V3 endpoint;
  * ZERO Scalar/ALU/formatter primitives are added outside this one V4 bank.
  *
  * Whole-group scope: token/tile/phase/head/chunk are explicitly zero. Full
  * txn64/owner32/stage/serial32 come only from accepted lease snapshots. The
  * original children retain their real token/tile progress; no tile authority
  * is inferred from an untagged raw arithmetic request.
  *
  * V4 has no lane mask: raw16 uses low16 plus sixteen actual +0 lanes; format
  * uses lane0 plus31 +0 lanes; private format16 uses low16 plus16 +0. These
  * lanes still physically compute. Neither
  * this compatibility path nor its clients claim32 useful results/cycle.
  * Bank ingress1+bank held result1 are two fixed credits. Scalar is deliberately
  * one accepted operation at a time, and physical issued is observed from the
  * real Core cumulative primitive counter, NOT from its frontend request.fire.
  */
class UnifiedMoeSharedArithmeticAdapterV5 extends Module {
  private val N=UnifiedMoeArithmeticClientV5.Count
  private val scalarClients=UnifiedMoeArithmeticClientV5.ScalarClients
  private val formatClients=UnifiedMoeArithmeticClientV5.FormatClients
  private val vectorClients=UnifiedMoeArithmeticClientV5.VectorClients
  private val bankClients=UnifiedMoeArithmeticClientV5.BankClients
  val io=IO(new Bundle {
    val acquire=Input(Vec(N,Valid(new UnifiedMoeArithmeticLeaseV5)))
    val retire=Input(Vec(N,Valid(new UnifiedMoeArithmeticRetireV5)))
    val scalar=Flipped(Vec(4,new UnifiedScalarClientV2))
    val formatRequest=Flipped(Vec(4,Decoupled(new UnifiedRawFp32FormatRequestV3)))
    val formatResult=Vec(4,Decoupled(new UnifiedRawFp32FormatResultV3))
    val vectorRequest=Flipped(Vec(2,Decoupled(new UnifiedVectorRequestV2)))
    val vectorResult=Vec(2,Decoupled(new UnifiedVectorResultV2))
    val ordinaryVectorRequest=Flipped(Decoupled(new UnifiedOrdinaryVectorRequestV5))
    val ordinaryVectorResult=Decoupled(new UnifiedOrdinaryVectorResultV5)
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
  for(i<-0 until 4){rawValid(scalarClients(i)):=io.scalar(i).request.valid;rawValid(formatClients(i)):=io.formatRequest(i).valid}
  for(i<-0 until 2)rawValid(vectorClients(i)):=io.vectorRequest(i).valid
  rawValid(UnifiedMoeArithmeticClientV5.OrdinaryChunkVector):=io.ordinaryVectorRequest.valid
  val ordinaryRaw=io.ordinaryVectorRequest.bits.payload
  val ordinaryFormatCanonical=ordinaryRaw.policy===0.U && !ordinaryRaw.multiply &&
    ordinaryRaw.b.map(x=>x===0.U).reduce(_&&_)
  val ordinaryGradualCanonical=ordinaryRaw.policy===UnifiedVectorPolicyV2.LegacyRaw.U
  val ordinaryFormatRequested=io.ordinaryVectorRequest.bits.formatOnly
  val ordinaryGradualRequested=io.ordinaryVectorRequest.bits.gradual
  // Reject malformed NEW mode offers without fake replies or withdrawing
  // any captured physical request/result. Shape fault is independent of ready.
  // Neither raw policy3 nor simultaneous format+gradual is an implicit mode.
  val ordinaryShapeBad=io.ordinaryVectorRequest.valid &&
    ((ordinaryFormatRequested && ordinaryGradualRequested) ||
      (ordinaryFormatRequested && !ordinaryFormatCanonical) ||
      (ordinaryGradualRequested && !ordinaryGradualCanonical))
  val countBad=VecInit((0 until N).map(i=>returned(i)>issued(i) || issued(i)>accepted(i) ||
    accepted(i)(32) || issued(i)(32) || returned(i)(32)))
  val overrun=VecInit((0 until N).map(i=>active(i) && !retiring(i) && rawValid(i) &&
    (accepted(i)>=leases(i).lease.expectedOperations.pad(33) || accepted(i)==="hffffffff".U)))

  // The immutable packet doubles as retained response identity; no copied
  // numerical result. Core's own held output is the only Scalar result buffer.
  val sOffer=RegInit(false.B);val sSubmitted=RegInit(false.B);val sIssuedSeen=RegInit(false.B)
  val sPacket=Reg(new QwenSharedScalarRequestV3);val sClient=Reg(UInt(4.W))
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
    MuxLookup(sClient,false.B)((0 until 4).map(i=>scalarClients(i).U->io.scalar(i).result.ready))
  for(i<-0 until 4){
    io.scalar(i).result.valid:=io.coreScalar.result.valid && scalarResponseOwned && sClient===scalarClients(i).U
    io.scalar(i).result.bits:=io.coreScalar.result.bits.payload
  }
  when(io.coreScalar.request.fire){sOffer:=false.B;sSubmitted:=true.B;sIssuedSeen:=false.B}
  when(scalarIssue){sIssuedSeen:=true.B}
  val scalarReturn=io.coreScalar.result.fire
  when(scalarReturn){sSubmitted:=false.B}

  // Exactly one accepted ingress and one bank-held result. Push wins pop in
  // both slots, so physical bank refill and ingress refill can occur together.
  val vOffer=RegInit(false.B);val vPacket=Reg(new UnifiedVectorElement32RequestV4)
  val vOfferClient=Reg(UInt(4.W));val vOfferRawPolicy=Reg(UInt(2.W))
  val vPending=RegInit(false.B);val vTag=Reg(new UnifiedSharedOperationTagV3)
  val vClient=Reg(UInt(4.W));val vPolicy=Reg(UInt(3.W));val vRawPolicy=Reg(UInt(2.W))
  bank.io.request.valid:=vOffer;bank.io.request.bits:=vPacket
  // Modes are retained without another buffer: canonical formatOnly maps to
  // policy4, canonical gradual maps to policy3. Both travel in vPacket/vPolicy
  // with the tag; response mode must NEVER be decoded from the live request.
  val ordinaryVectorClient=vClient===UnifiedMoeArithmeticClientV5.OrdinaryChunkVector.U
  val ordinaryVectorFormat=ordinaryVectorClient && vPolicy===UnifiedVectorElement32PolicyV4.RawFp32ToBf16Rne.U
  val ordinaryVectorGradual=ordinaryVectorClient && vPolicy===UnifiedVectorElement32PolicyV4.RawFp32FiniteGradual.U
  // Format9 and ordinary format16 are NOT arithmetic. Never classify by >=6.
  val vectorClientIsRaw=vectorClients.map(i=>vClient===i.U).reduce(_||_) ||
    (ordinaryVectorClient && !ordinaryVectorFormat)
  val vectorIdentity=bank.io.result.bits.identity.asUInt===vTag.asUInt &&
    bank.io.result.bits.payload.policy===vPolicy &&
    bank.io.result.bits.payload.arithFlagsValid===vectorClientIsRaw &&
    !bank.io.result.bits.payload.formatFlagsValid
  val unknownVector=bank.io.result.valid && (!vPending || !vectorIdentity)
  when(unknownVector){vectorQuarantine:=true.B}
  val vectorResponseOwned=vPending && vectorIdentity && !vectorQuarantine && !unknownVector
  val vectorConsumerReady=MuxLookup(vClient,false.B)(
    (0 until 4).map(i=>formatClients(i).U->io.formatResult(i).ready)++
    (0 until 2).map(i=>vectorClients(i).U->io.vectorResult(i).ready)++
    Seq(UnifiedMoeArithmeticClientV5.OrdinaryChunkVector.U->io.ordinaryVectorResult.ready))
  bank.io.result.ready:=vectorResponseOwned && vectorConsumerReady
  for(i<-0 until 4){
    io.formatResult(i).valid:=bank.io.result.valid && vectorResponseOwned && vClient===formatClients(i).U
    io.formatResult(i).bits.value:=bank.io.result.bits.payload.value(0)(31,16)
    io.formatResult(i).bits.error:=bank.io.result.bits.payload.error
  }
  for(i<-0 until 2){
    io.vectorResult(i).valid:=bank.io.result.valid && vectorResponseOwned && vClient===vectorClients(i).U
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
  io.ordinaryVectorResult.valid:=bank.io.result.valid && vectorResponseOwned && ordinaryVectorClient
  io.ordinaryVectorResult.bits.formatOnly:=ordinaryVectorFormat
  io.ordinaryVectorResult.bits.gradual:=ordinaryVectorGradual
  io.ordinaryVectorResult.bits.arithFlagsValid:=bank.io.result.bits.payload.arithFlagsValid
  io.ordinaryVectorResult.bits.payload.policy:=vRawPolicy
  for(j<-0 until 16){
    io.ordinaryVectorResult.bits.payload.value(j):=bank.io.result.bits.payload.value(j)
    io.ordinaryVectorResult.bits.payload.flags(j):=bank.io.result.bits.payload.arithFlags(j)
  }
  io.ordinaryVectorResult.bits.payload.error:=bank.io.result.bits.payload.error ||
    (!ordinaryVectorFormat && vRawPolicy===3.U)
  val vectorIssue=bank.io.request.fire;val vectorReturn=bank.io.result.fire
  when(vectorIssue){
    vTag:=vPacket.identity;vClient:=vOfferClient;vPolicy:=vPacket.payload.policy
    vRawPolicy:=vOfferRawPolicy;vPending:=true.B
  }.elsewhen(vectorReturn){vPending:=false.B}

  val numericalFault=(io.coreScalar.result.valid && scalarResponseOwned && io.coreScalar.result.bits.payload.error) ||
    (bank.io.result.valid && vectorResponseOwned &&
      (bank.io.result.bits.payload.error || (vectorClientIsRaw && vRawPolicy===3.U)))
  val terminalError=io.retire.map(r=>r.valid && r.bits.status=/=Status.Ok.U).reduce(_||_)
  val serviceFault=countBad.asUInt.orR || overrun.asUInt.orR || unknownScalar ||
    unknownVector || coreIssueMalformed || io.coreScalar.status.resetRequired || numericalFault ||
    terminalError || ordinaryShapeBad || io.externalPoison
  val currentFault=eventFault || serviceFault
  when(currentFault){poison:=true.B}
  io.resetRequired:=poison || scalarQuarantine || vectorQuarantine || currentFault
  // Only fresh acceptance is stopped. Captured physical offers and matched
  // results above are NEVER gated by ordinary poison or terminal intent.
  val admit= !poison && !currentFault && !scalarQuarantine && !vectorQuarantine
  def clientMayAccept(i:Int):Bool=active(i) && !retiring(i) && !io.retire(i).valid &&
    !io.acquire(i).valid && !countBad(i) && accepted(i)<leases(i).lease.expectedOperations.pad(33) &&
    accepted(i)<"hffffffff".U

  val sarb=Module(new RRArbiter(new QwenSharedScalarRequestV3,4))
  for(i<-0 until 4){
    val client=scalarClients(i)
    sarb.io.in(i).valid:=io.scalar(i).request.valid && clientMayAccept(client)
    sarb.io.in(i).bits.identity.owner:=leases(client).lease.identity
    sarb.io.in(i).bits.identity.resource:=2.U;sarb.io.in(i).bits.identity.serial:=accepted(client)(31,0)
    sarb.io.in(i).bits.payload:=io.scalar(i).request.bits
    io.scalar(i).request.ready:=sarb.io.in(i).ready && clientMayAccept(client)
  }
  sarb.io.out.ready:= !sOffer && !sSubmitted && !io.coreScalar.result.valid && admit
  val scalarAccept=sarb.io.out.fire;val scalarAcceptClient=VecInit(scalarClients.map(_.U(4.W)))(sarb.io.chosen)
  when(scalarAccept){sPacket:=sarb.io.out.bits;sClient:=scalarAcceptClient;sOffer:=true.B}

  val varb=Module(new RRArbiter(new UnifiedVectorElement32RequestV4,7))
  for(i<-0 until 7){
    val client=bankClients(i)
    varb.io.in(i).valid:=rawValid(client) && clientMayAccept(client)
    varb.io.in(i).bits:=0.U.asTypeOf(new UnifiedVectorElement32RequestV4)
    varb.io.in(i).bits.identity.owner:=leases(client).lease.identity
    varb.io.in(i).bits.identity.resource:=1.U
    varb.io.in(i).bits.identity.serial:=accepted(client)(31,0)
    if(i<4){
      varb.io.in(i).bits.payload.policy:=UnifiedVectorElement32PolicyV4.RawFp32ToBf16Rne.U
      varb.io.in(i).bits.payload.a(0):=io.formatRequest(i).bits.value
      io.formatRequest(i).ready:=varb.io.in(i).ready && clientMayAccept(client)
    }else if(i<6){
      val raw=io.vectorRequest(i-4).bits
      varb.io.in(i).bits.payload.policy:=Mux(raw.policy===3.U,
        UnifiedVectorElement32PolicyV4.Bf16AddRne.U,raw.policy.pad(3))
      varb.io.in(i).bits.payload.multiply:=raw.multiply
      for(j<-0 until 16){varb.io.in(i).bits.payload.a(j):=raw.a(j);varb.io.in(i).bits.payload.b(j):=raw.b(j)}
      io.vectorRequest(i-4).ready:=varb.io.in(i).ready && clientMayAccept(client)
    }else{
      val raw=io.ordinaryVectorRequest.bits.payload
      val format=io.ordinaryVectorRequest.bits.formatOnly
      val gradual=io.ordinaryVectorRequest.bits.gradual
      varb.io.in(i).bits.payload.policy:=Mux(format,UnifiedVectorElement32PolicyV4.RawFp32ToBf16Rne.U,
        Mux(gradual,UnifiedVectorElement32PolicyV4.RawFp32FiniteGradual.U,
          Mux(raw.policy===3.U,UnifiedVectorElement32PolicyV4.Bf16AddRne.U,raw.policy.pad(3))))
      varb.io.in(i).bits.payload.multiply:=Mux(format,false.B,raw.multiply)
      for(j<-0 until 16){
        varb.io.in(i).bits.payload.a(j):=raw.a(j)
        varb.io.in(i).bits.payload.b(j):=Mux(format,0.U,raw.b(j))
      }
      io.ordinaryVectorRequest.ready:=varb.io.in(i).ready && clientMayAccept(client) && !ordinaryShapeBad
    }
  }
  varb.io.out.ready:=(!vOffer || bank.io.request.ready) && admit
  val vectorAccept=varb.io.out.fire;val vectorAcceptClient=VecInit(bankClients.map(_.U(4.W)))(varb.io.chosen)
  val selectedRawPolicy=MuxLookup(varb.io.chosen,0.U(2.W))(
    Seq(4.U->io.vectorRequest(0).bits.policy,5.U->io.vectorRequest(1).bits.policy,
      6.U->io.ordinaryVectorRequest.bits.payload.policy))
  when(vectorAccept){
    vPacket:=varb.io.out.bits;vOfferClient:=vectorAcceptClient;vOfferRawPolicy:=selectedRawPolicy;vOffer:=true.B
  }.elsewhen(vectorIssue){vOffer:=false.B}

  // Authoritative acquisition is an external actual-event input, not a
  // manufactured grant. Raw valid before a lease merely receives backpressure.
  for(i<-0 until N){
    val a=io.acquire(i).bits;val id=a.lease.identity;val previous=leases(i)
    def ordinaryKind(k:UInt):Bool=k===UnifiedArithmeticAuthorityKindV5.OrdinaryNorm.U ||
      k===UnifiedArithmeticAuthorityKindV5.OrdinaryConv.U ||
      k===UnifiedArithmeticAuthorityKindV5.OrdinaryRawPrep.U ||
      k===UnifiedArithmeticAuthorityKindV5.OrdinaryChunk.U ||
      k===UnifiedArithmeticAuthorityKindV5.OrdinaryGatedNorm.U ||
      k===UnifiedArithmeticAuthorityKindV5.OrdinaryQkNorm.U ||
      k===UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U ||
      k===UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U
    // Ordinary operations reuse their fixed slots within one transaction,
    // but only a STRICTLY later actual physical owner with the same epoch.
    val authorityContinuity=if(i<8) a.authorityKind===previous.authorityKind
      else ordinaryKind(a.authorityKind) && ordinaryKind(previous.authorityKind)
    val fresh= !havePrevious(i) || id.transactionId>previous.lease.identity.transactionId ||
      (id.transactionId===previous.lease.identity.transactionId &&
        id.ownerSequence>previous.lease.identity.ownerSequence &&
        authorityContinuity && a.allocationValid===previous.allocationValid &&
        a.allocationSequence===previous.allocationSequence && a.hostEpoch===previous.hostEpoch)
    val groupScope=id.phase===0.U && id.head===0.U && id.chunk===0.U && id.token===0.U && id.tileOrdinal===0.U
    // A missing MoE allocation is NEVER converted to ordinary authority.
    // The fixed client slot and explicit kind must BOTH select the domain.
    val ordinaryChunk=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryChunk.U
    val ordinaryQkNorm=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryQkNorm.U
    val ordinaryRope=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U
    val ordinaryGqa=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U
    val slotKindLegal=if(i==8) ordinaryKind(a.authorityKind)
      else if(i==9) ordinaryKind(a.authorityKind) && !ordinaryChunk && !ordinaryQkNorm && !ordinaryRope && !ordinaryGqa
      else if(i==10) ordinaryChunk
      else false.B
    val domainLegal=if(i<8) a.authorityKind===UnifiedArithmeticAuthorityKindV5.MoEAllocation.U &&
      a.allocationValid && a.allocationSequence=/=0.U
      else slotKindLegal && !a.allocationValid && a.allocationSequence===0.U
    val ordinaryConv=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryConv.U
    val ordinaryRawPrep=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryRawPrep.U
    val ordinaryGatedNorm=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryGatedNorm.U
    val expectedStage=if(i<8) UnifiedMoeArithmeticClientV5.Stages(i).U
      else Mux(ordinaryGqa,UnifiedMoeArithmeticClientV5.OrdinaryGqaStage.U,
        Mux(ordinaryRope,UnifiedMoeArithmeticClientV5.OrdinaryRopeStage.U,
        Mux(ordinaryQkNorm,UnifiedMoeArithmeticClientV5.OrdinaryQkNormStage.U,
        Mux(ordinaryGatedNorm,UnifiedMoeArithmeticClientV5.OrdinaryGatedNormStage.U,
        Mux(ordinaryChunk,UnifiedMoeArithmeticClientV5.OrdinaryChunkStage.U,
        Mux(ordinaryRawPrep,UnifiedMoeArithmeticClientV5.OrdinaryRawPrepStage.U,
          Mux(ordinaryConv,UnifiedMoeArithmeticClientV5.OrdinaryConvStage.U,
            UnifiedMoeArithmeticClientV5.Stages(i).U)))))))
    // Do not enlarge Norm, Conv, RawPrep, QKNorm, RoPE or any other count domain.
    // RawPrep's precise expected count is the parent's authenticated prepare
    // receipt after actual A_log DDR reads, NEVER the maximum below.
    val maximumOperations=if(i<8) UnifiedMoeArithmeticClientV5.MaximumOperations(i).U
      else if(i==10) UnifiedMoeArithmeticClientV5.OrdinaryChunkMaximumOperations(1).U
      else Mux(ordinaryGqa,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryGqaMaximumOperations.U else 0.U),
        Mux(ordinaryRope,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryRopeMaximumOperations.U else 0.U),
        Mux(ordinaryQkNorm,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryQkNormMaximumOperations.U else 0.U),
        Mux(ordinaryGatedNorm,UnifiedMoeArithmeticClientV5.OrdinaryGatedNormMaximumOperations(i-8).U,
        Mux(ordinaryChunk,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryChunkMaximumOperations(0).U else 0.U),
        Mux(ordinaryRawPrep,UnifiedMoeArithmeticClientV5.OrdinaryRawPrepMaximumOperations(i-8).U,
          Mux(ordinaryConv,UnifiedMoeArithmeticClientV5.OrdinaryConvMaximumOperations(i-8).U,
            UnifiedMoeArithmeticClientV5.MaximumOperations(i).U)))))))
    val legal=domainLegal && groupScope && id.stage===expectedStage &&
      a.lease.resource===UnifiedMoeArithmeticClientV5.Resources(i).U && id.ownerSequence=/="hffffffff".U &&
      a.lease.expectedOperations>0.U && a.lease.expectedOperations<=maximumOperations &&
      fresh
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
    val domainQuarantine=if(scalarClients.contains(i))scalarQuarantine || unknownScalar || coreIssueMalformed
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

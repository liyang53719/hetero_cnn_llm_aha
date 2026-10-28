// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Ordinary runtime RMS/Conv/RawPrep authority, never a MoE allocation or Host grant.
  * Real Guard logical acceptance captures provenance. Only the corresponding
  * physicalJob.fire acquires RMS/Conv leases; RawPrep defers until its real prepared DDR event; only its matching
  * physicalDone.fire retires them. Scope stage69/70/71 covers the WHOLE ordinary job.
  * Registers below are metadata, not a second dispatcher or numerical bank.
  */
/** Private actual staging receipt only. It cannot publish cache/state roots;
  * the whole-block final ACK/dual-root fence remains the publication owner. */
class HostRuntimeKvStagedReceiptV13 extends Bundle {
  val host=new HostCommandLaunchV4
  val transactionId=UInt(64.W)
  val job=new QwenOwnerJob
  val result=new Bf16KvAppendRuntimeResultV13
}
/** Actual physical terminal snapshot. It never authorizes a final root commit.
  * Accepted is copied from Guard's physical job, result from physicalDone.fire;
  * specialized accepted/ACK/count evidence is checked before capture. */
class HostRuntimeOutputStagedReceiptV15 extends Bundle {
  val host=new HostCommandLaunchV4
  val transactionId=UInt(64.W)
  val job=new QwenOwnerJob
  val result=new QwenOwnerResult
}
/** Private FFN-input evidence from the SAME physical RMS child. InputNorm's
  * stage69/authority-kind1 is reused, but phase3 and its retained Residual1
  * producer distinguish this postNorm receipt from phase0 success. No new
  * tensor cache, arithmetic engine or Host-supplied capability is introduced. */
class HostRuntimePostnormStagedReceiptV16 extends Bundle {
  val host=new HostCommandLaunchV4
  val transactionId=UInt(64.W)
  val job=new QwenOwnerJob
  val logicalJob=new QwenOwnerJob
  val result=new GdnRuntimeRmsNormResultV16
  val residual=new HostRuntimeOutputStagedReceiptV15
}
/** Actual FFN physical ACK. No new grant port or final root publication. */
class HostRuntimeFfnStagedReceiptV17 extends Bundle {
  val host=new HostCommandLaunchV4;val transactionId=UInt(64.W)
  val job=new QwenOwnerJob;val logicalJob=new QwenOwnerJob
  val result=new QwenOwnerResult
}
object HostRuntimePrefixLeaseWiringV8 {
  class View extends Bundle {
    val owned=Bool();val localFault=Bool();val eventsPending=Bool();val resourcesDrained=Bool()
    val host=new HostCommandLaunchV4
    val transactionId=UInt(64.W);val job=new QwenOwnerJob
    // Read-only snapshot, NOT Decoupled: eligibility may be revoked on fault
    // or context change. No external/fabricated consume input exists.
    val prepReceipt=Valid(new GdnRuntimeRawPrepReceiptV8)
    val kvReceipt=Valid(new HostRuntimeKvStagedReceiptV13)
    val postnormReceipt=Valid(new HostRuntimePostnormStagedReceiptV16)
    val ffnReceipt=Valid(new HostRuntimeFfnStagedReceiptV17)
    val scalarAcquire=Valid(new UnifiedMoeArithmeticLeaseV5)
    val scalarRetire=Valid(new UnifiedMoeArithmeticRetireV5)
  }
  def connect(a:UnifiedMoeSharedArithmeticAdapterV5,g:HostRuntimeOwnerGuardV5,
      authority:HostRuntimeAuthoritySnapshotV4,k:QwenOwnerKernel,currentIndependentFault:Bool,scalarPort:UnifiedScalarClientV2,chunkReceipt:ValidIO[GdnRuntimeChunkStagedReceiptV10]):View={
    val out=Wire(new View)
    val logical=Reg(new QwenOwnerJob);val host=Reg(new HostCommandLaunchV4)
    val transaction=Reg(UInt(64.W));val physical=Reg(UInt(32.W))
    val waiting=RegInit(false.B);val owned=RegInit(false.B);val poison=RegInit(false.B)
    val acquirePending=RegInit(false.B);val retirePending=RegInit(false.B)
    val leaseEventSubmitted=RegInit(false.B);val awaitPrepare=RegInit(false.B)
    val retireStatus=Reg(UInt(8.W));val leases=Reg(Vec(2,new UnifiedMoeArithmeticLeaseV5))
    val gatedProducer=Reg(UInt(32.W));val gatedSource=Reg(new GdnRuntimeChunkStagedReceiptV10)
    val gatedConsumed=RegInit(false.B);val lastGatedProducer=Reg(UInt(32.W));val lastGatedTransaction=Reg(UInt(64.W))
    // Actual Dense physical acceptance/terminal snapshots, not Host receipts.
    // Three typed Q/K/V producers are retained under ONE full Host lifetime.
    val projectionValid=RegInit(VecInit(Seq.fill(3)(false.B)))
    val projectionJobs=Reg(Vec(3,new QwenOwnerJob));val projectionResults=Reg(Vec(3,new QwenOwnerResult))
    val projectionHost=Reg(new HostCommandLaunchV4);val projectionTransaction=Reg(UInt(64.W))
    val projectionPending=Reg(new QwenOwnerJob);val projectionBusy=RegInit(false.B)
    val qkProducer=Reg(new QwenOwnerJob);val qkProducerResult=Reg(new QwenOwnerResult)
    val qkConsumed=RegInit(VecInit(Seq.fill(2)(false.B)))
    val qkLastProducer=Reg(Vec(2,UInt(32.W)));val qkLastTransaction=Reg(Vec(2,UInt(64.W)))
    // Real QKNorm terminal/ACK snapshots retained under the same full Host.
    // They are prerequisites, not leases fabricated from matching addresses.
    val normalizedValid=RegInit(VecInit(Seq.fill(2)(false.B)))
    val normalizedJobs=Reg(Vec(2,new QwenOwnerJob))
    val normalizedResults=Reg(Vec(2,new QkNormRuntimeResultV11))
    val normalizedHost=Reg(new HostCommandLaunchV4);val normalizedTransaction=Reg(UInt(64.W))
    val normalizedCurrent=authority.accepted && authority.transaction===normalizedTransaction &&
      authority.launch.asUInt===normalizedHost.asUInt
    val ropeProducer=Reg(new QwenOwnerJob);val ropeProducerResult=Reg(new QkNormRuntimeResultV11)
    val ropeConsumed=RegInit(VecInit(Seq.fill(2)(false.B)))
    val ropeLastProducer=Reg(Vec(2,UInt(32.W)));val ropeLastTransaction=Reg(Vec(2,UInt(64.W)))
    val ropeQCommitted=RegInit(false.B)
    // Full Q rotary provenance is retained from its actual terminal/ACK fire.
    // A Boolean "Q completed" is insufficient to authorize later GQA reads.
    val rotatedQValid=RegInit(false.B)
    val rotatedQJob=Reg(new QwenOwnerJob);val rotatedQResult=Reg(new PartialRopeRuntimeResultV12)
    val rotatedQHost=Reg(new HostCommandLaunchV4);val rotatedQTransaction=Reg(UInt(64.W))
    val rotatedQCurrent=authority.accepted && authority.transaction===rotatedQTransaction &&
      authority.launch.asUInt===rotatedQHost.asUInt
    // K rotary and V Dense provenance come only from real Guard/child fires.
    val rotatedKValid=RegInit(false.B)
    val rotatedKJob=Reg(new QwenOwnerJob);val rotatedKResult=Reg(new PartialRopeRuntimeResultV12)
    val rotatedKHost=Reg(new HostCommandLaunchV4);val rotatedKTransaction=Reg(UInt(64.W))
    val rotatedKCurrent=authority.accepted && authority.transaction===rotatedKTransaction &&
      authority.launch.asUInt===rotatedKHost.asUInt
    val kvKeyProducer=Reg(new QwenOwnerJob);val kvKeyResult=Reg(new PartialRopeRuntimeResultV12)
    val kvValueProducer=Reg(new QwenOwnerJob);val kvValueResult=Reg(new QwenOwnerResult)
    val kvConsumed=RegInit(false.B);val kvLastTransaction=Reg(UInt(64.W))
    val kvLastKey=Reg(UInt(32.W));val kvLastValue=Reg(UInt(32.W))
    val kvReceiptValid=RegInit(false.B);val kvReceipt=Reg(new HostRuntimeKvStagedReceiptV13)
    val kvReceiptCurrent=authority.accepted && authority.transaction===kvReceipt.transactionId &&
      authority.launch.asUInt===kvReceipt.host.asUInt
    // Two independent physical producers feed one guarded GQA consumer. These
    // retained snapshots are private staging provenance, never published roots.
    val gqaQueryProducer=Reg(new QwenOwnerJob);val gqaQueryResult=Reg(new PartialRopeRuntimeResultV12)
    val gqaCacheProducer=Reg(new HostRuntimeKvStagedReceiptV13)
    val gqaConsumed=RegInit(false.B);val gqaLastTransaction=Reg(UInt(64.W))
    val gqaLastQuery=Reg(UInt(32.W));val gqaLastCache=Reg(UInt(32.W))
    // Fixed metadata ledgers for real output-tail producers. No tensor cache,
    // no second owner dispatcher, and no Host writable receipt/grant input.
    val hiddenValid=RegInit(false.B);val hiddenReceipt=Reg(new HostRuntimeOutputStagedReceiptV15)
    val gqaOutputValid=RegInit(false.B);val gqaOutputReceipt=Reg(new HostRuntimeOutputStagedReceiptV15)
    val gqaGateJob=Reg(new QwenOwnerJob);val gqaGateResult=Reg(new QkNormRuntimeResultV11)
    val mixedValid=RegInit(false.B);val mixedReceipt=Reg(new HostRuntimeOutputStagedReceiptV15)
    val denseOValid=RegInit(false.B);val denseOReceipt=Reg(new HostRuntimeOutputStagedReceiptV15)
    val residualValid=RegInit(false.B);val residualReceipt=Reg(new HostRuntimeOutputStagedReceiptV15)
    val normPostPhase=RegInit(false.B)
    val postnormInput=Reg(new HostRuntimeOutputStagedReceiptV15)
    val postnormConsumed=RegInit(false.B);val postnormLastTransaction=Reg(UInt(64.W))
    val postnormLastProducer=Reg(UInt(32.W))
    val postnormValid=RegInit(false.B);val postnormReceipt=Reg(new HostRuntimePostnormStagedReceiptV16)
    val postnormCurrent=authority.accepted && authority.transaction===postnormReceipt.transactionId &&
      authority.launch.asUInt===postnormReceipt.host.asUInt
    // Fixed five-stage metadata ledger; payload lives in original DDR and
    // shared Dense/Matrix/Elementwise banks. Stage0 is never an FFN producer.
    val ffnValid=RegInit(VecInit(Seq.fill(5)(false.B)))
    val ffnIssued=RegInit(VecInit(Seq.fill(5)(false.B)))
    val ffnStages=Reg(Vec(5,new HostRuntimeFfnStagedReceiptV17))
    val ffnReceipt=Reg(new HostRuntimeFfnStagedReceiptV17);val ffnReceiptValid=RegInit(false.B)
    val ffnSourceA=Reg(new HostRuntimeFfnStagedReceiptV17)
    val ffnSourceB=Reg(new HostRuntimeFfnStagedReceiptV17)
    val ffnNormSource=Reg(new HostRuntimePostnormStagedReceiptV16)
    val ffnDenseWaiting=RegInit(false.B);val ffnDenseBusy=RegInit(false.B)
    val ffnDenseLogical=Reg(new QwenOwnerJob);val ffnDensePending=Reg(new QwenOwnerJob)
    val ffnDenseHost=Reg(new HostCommandLaunchV4);val ffnDenseTransaction=Reg(UInt(64.W))
    val elementInputA=Reg(new HostRuntimeOutputStagedReceiptV15)
    val elementInputB=Reg(new HostRuntimeOutputStagedReceiptV15)
    val elementGateJob=Reg(new QwenOwnerJob);val elementGateResult=Reg(new QkNormRuntimeResultV11)
    val elementConsumed=RegInit(VecInit(Seq.fill(2)(false.B)))
    val elementLastTransaction=Reg(Vec(2,UInt(64.W)))
    val elementLastA=Reg(Vec(2,UInt(32.W)));val elementLastB=Reg(Vec(2,UInt(32.W)))
    val denseOWaiting=RegInit(false.B);val denseOBusy=RegInit(false.B)
    val denseOLogical=Reg(new QwenOwnerJob);val denseOPending=Reg(new QwenOwnerJob)
    val denseOSource=Reg(new HostRuntimeOutputStagedReceiptV15)
    val denseOHost=Reg(new HostCommandLaunchV4);val denseOTransaction=Reg(UInt(64.W))
    val denseOConsumed=RegInit(false.B);val denseOLastTransaction=Reg(UInt(64.W));val denseOLastProducer=Reg(UInt(32.W))
    def tailCurrent(r:HostRuntimeOutputStagedReceiptV15):Bool=authority.accepted &&
      authority.transaction===r.transactionId && authority.launch.asUInt===r.host.asUInt
    def tailSuccess(r:HostRuntimeOutputStagedReceiptV15):Bool=r.result.tag===r.job.tag &&
      r.result.status===Status.Ok.U && r.result.writeBytes===r.job.writeBytes && r.job.tag=/="hffffffff".U
    def isOutputDense(j:QwenOwnerJob):Bool=j.kind===QwenOwnerKind.Dense.U && j.qkRole===3.U && j.runtimeFfnPhase===0.U &&
      j.activationBf16 && j.weightBf16 && j.outputBf16
    def isElementwise(j:QwenOwnerJob):Bool=j.kind===QwenOwnerKind.GdnElementwise.U &&
      j.activationBf16 && j.weightBf16 && j.outputBf16
    def outputRows(j:QwenOwnerJob):Bool=Mux(authority.launch.profileId===1.U || authority.launch.profileId===3.U,
      j.m===16.U || j.m===128.U,j.m===128.U)
    val outputHetero=authority.launch.profileId>=1.U && authority.launch.profileId<=4.U
    val outputAttention=authority.launch.profileId===2.U || authority.launch.profileId===4.U
    val outputHiddenWidth=Mux(authority.launch.profileId<=2.U,1024.U,2048.U)
    val outputContextWidth=Mux(authority.launch.profileId<=2.U,2048.U,4096.U)
    def outputCommon(j:QwenOwnerJob):Bool=outputHetero && outputRows(j) && j.cold &&
      j.expectedGeneration===0.U && j.currentGeneration===0.U &&
      j.writeBytes===(j.m.pad(64)*j.n.pad(64)<<1)(63,0)
    def isFfn(j:QwenOwnerJob):Bool=j.runtimeFfnPhase=/=0.U
    def isFfnDense(j:QwenOwnerJob):Bool=j.kind===QwenOwnerKind.Dense.U && isFfn(j)
    def ffnCommon(j:QwenOwnerJob):Bool=(authority.launch.profileId===1.U || authority.launch.profileId===2.U) &&
      outputCommon(j) && j.activationBf16 && j.weightBf16 && j.outputBf16 && !j.materializeDenseOutput && !j.public21Reduction
    def ffnDenseShape(j:QwenOwnerJob):Bool=isFfnDense(j) && ffnCommon(j) && j.qkRole===3.U &&
      (((j.runtimeFfnPhase===1.U || j.runtimeFfnPhase===2.U) && j.n===3584.U && j.k===1024.U) ||
       (j.runtimeFfnPhase===4.U && j.n===1024.U && j.k===3584.U))
    def ffnElementShape(j:QwenOwnerJob):Bool=isElementwise(j) && ffnCommon(j) && j.k===j.n &&
      ((j.runtimeFfnPhase===3.U && j.gdnElementwiseOp===GdnElementwiseOp.SiluMul.U && j.n===3584.U) ||
       (j.runtimeFfnPhase===5.U && j.gdnElementwiseOp===GdnElementwiseOp.Add.U && j.n===1024.U))
    def elementShape(j:QwenOwnerJob):Bool=ffnElementShape(j) || (isElementwise(j) && j.runtimeFfnPhase===0.U && outputCommon(j) && j.k===j.n &&
      ((j.gdnElementwiseOp===GdnElementwiseOp.SigmoidMul.U && outputAttention && j.n===outputContextWidth) ||
       (j.gdnElementwiseOp===GdnElementwiseOp.Add.U && j.n===outputHiddenWidth)))
    def ffnCurrent(r:HostRuntimeFfnStagedReceiptV17):Bool=authority.accepted &&
      authority.transaction===r.transactionId && authority.launch.asUInt===r.host.asUInt
    def ffnSuccess(i:Int):Bool={
      val r=ffnStages(i)
      ffnValid(i) && ffnCurrent(r) && r.job.runtimeFfnPhase===(i+1).U &&
        r.result.tag===r.job.tag && r.result.status===Status.Ok.U && r.result.writeBytes===r.job.writeBytes &&
        r.job.tag=/="hffffffff".U
    }
    def ffnNormInputs(q:QwenOwnerJob):Bool={
      val r=postnormReceipt
      postnormValid && postnormCurrent && r.job.qkRole===3.U &&
        r.job.runtimeFfnPhase===0.U && r.job.kind===QwenOwnerKind.GdnRmsNorm.U &&
        r.logicalJob.asUInt===authority.postnormJob.asUInt && r.result.tag===r.job.tag &&
        r.result.status===Status.Ok.U && r.result.outputCommitted && r.result.resourcesDrained &&
        r.result.outputAckBytes===r.job.writeBytes && r.result.writeBytes===r.job.writeBytes &&
        r.job.tag=/="hffffffff".U && r.job.dst===q.a && r.job.m===q.m && r.job.n===1024.U &&
        r.job.writeBytes===(q.m.pad(64)<<11)
    }
    def ffnInputs(q:QwenOwnerJob):Bool={
      val gate=ffnStages(0).job;val up=ffnStages(1).job;val act=ffnStages(2).job;val down=ffnStages(3).job
      q.runtimeFfnPhase>=1.U && q.runtimeFfnPhase<=5.U && !ffnIssued(q.runtimeFfnPhase-1.U) &&
      MuxLookup(q.runtimeFfnPhase,false.B)(Seq(
        1.U->ffnNormInputs(q),
        2.U->(ffnNormInputs(q) && ffnSuccess(0) && gate.a===q.a && gate.m===q.m),
        3.U->(ffnSuccess(0) && ffnSuccess(1) && gate.dst===q.a && up.dst===q.b &&
          gate.m===q.m && up.m===q.m && gate.n===q.n && up.n===q.n && gate.a===up.a),
        4.U->(ffnSuccess(2) && act.dst===q.a && act.m===q.m && act.n===q.k),
        5.U->(ffnSuccess(3) && residualValid && tailCurrent(residualReceipt) && tailSuccess(residualReceipt) &&
          residualReceipt.job.runtimeFfnPhase===0.U && residualReceipt.job.dst===q.a &&
          residualReceipt.job.m===q.m && residualReceipt.job.n===q.n &&
          down.dst===q.b && down.m===q.m && down.n===q.n)))
    }
    def denseOShape(j:QwenOwnerJob):Bool=isOutputDense(j) && !j.materializeDenseOutput && outputCommon(j) &&
      j.n===outputHiddenWidth && j.k===outputContextWidth
    def isRuntimeNorm(j:QwenOwnerJob):Bool=j.kind===QwenOwnerKind.GdnRmsNorm.U
    def normCommon(j:QwenOwnerJob):Bool=isRuntimeNorm(j) && outputHetero &&
      j.activationBf16 && j.weightBf16 && j.outputBf16 && j.m>=1.U && j.m<=128.U &&
      j.n===outputHiddenWidth && j.k===j.n && (j.qkRole===0.U || j.qkRole===3.U) &&
      j.cold && j.expectedGeneration===0.U && j.currentGeneration===0.U &&
      j.writeBytes===(j.m.pad(64)*j.n.pad(64)<<1)(63,0)
    def postnormInputs(q:QwenOwnerJob):Bool={
      val r=residualReceipt
      residualValid && tailCurrent(r) && tailSuccess(r) &&
        isElementwise(r.job) && r.job.gdnElementwiseOp===GdnElementwiseOp.Add.U &&
        r.job.cold && r.job.expectedGeneration===0.U && r.job.currentGeneration===0.U &&
        r.job.dst===q.a && r.job.m===q.m && r.job.n===q.n && r.job.k===q.k &&
        r.job.writeBytes===q.writeBytes && outputRows(q) &&
        (!postnormConsumed || r.transactionId>postnormLastTransaction ||
          (r.transactionId===postnormLastTransaction && r.job.tag>postnormLastProducer))
    }
    def gateInputs(q:QwenOwnerJob):Bool={
      val p=normalizedJobs(0);val r=normalizedResults(0);val c=gqaOutputReceipt
      normalizedValid(0) && normalizedCurrent && gqaOutputValid && tailCurrent(c) && tailSuccess(c) &&
        normalizedTransaction===c.transactionId && normalizedHost.asUInt===c.host.asUInt &&
        p.asUInt===gqaGateJob.asUInt && r.asUInt===gqaGateResult.asUInt &&
        p.qkRole===0.U && p.c===q.a && p.m===q.m && (p.n.pad(32)<<8)===q.n && p.k===256.U &&
        r.accepted.asUInt===QkNormRuntimeJobV11.fromOwner(p).asUInt && r.tag===p.tag &&
        r.status===Status.Ok.U && r.outputCommitted && r.outputAckBytes===p.writeBytes &&
        p.writeBytes===(q.writeBytes<<1) && c.job.kind===QwenOwnerKind.Attention.U &&
        c.job.dst===q.b && c.job.m===q.m && c.job.n===q.n && c.job.writeBytes===q.writeBytes &&
        (!elementConsumed(1) || c.transactionId>elementLastTransaction(1) ||
          (c.transactionId===elementLastTransaction(1) && p.tag>elementLastA(1) && c.job.tag>elementLastB(1)))
    }
    def residualInputs(q:QwenOwnerJob):Bool={
      val x=hiddenReceipt;val o=denseOReceipt
      hiddenValid && denseOValid && tailCurrent(x) && tailCurrent(o) && tailSuccess(x) && tailSuccess(o) &&
        x.transactionId===o.transactionId && x.host.asUInt===o.host.asUInt &&
        x.job.kind===QwenOwnerKind.GdnRmsNorm.U && x.job.qkRole===0.U &&
        x.job.a===q.a && x.job.m===q.m && x.job.n===q.n && x.job.writeBytes===q.writeBytes &&
        isOutputDense(o.job) && o.job.dst===q.b && o.job.m===q.m && o.job.n===q.n && o.job.writeBytes===q.writeBytes &&
        (!elementConsumed(0) || o.transactionId>elementLastTransaction(0) ||
          (o.transactionId===elementLastTransaction(0) && x.job.tag>elementLastA(0) && o.job.tag>elementLastB(0)))
    }
    def denseOInputs(q:QwenOwnerJob):Bool={
      val r=mixedReceipt
      mixedValid && tailCurrent(r) && tailSuccess(r) && r.job.dst===q.a && r.job.m===q.m &&
        r.job.writeBytes===(q.m.pad(64)*q.k.pad(64)<<1)(63,0) &&
        Mux(outputAttention,r.job.kind===QwenOwnerKind.GdnElementwise.U &&
          r.job.gdnElementwiseOp===GdnElementwiseOp.SigmoidMul.U && r.job.n===q.k,
          r.job.kind===QwenOwnerKind.GdnGatedNorm.U && (r.job.n.pad(32)<<7)===q.k) &&
        (!denseOConsumed || r.transactionId>denseOLastTransaction ||
          (r.transactionId===denseOLastTransaction && r.job.tag>denseOLastProducer))
    }
    val offeredOutput=g.io.job.bits
    // Raw valid is state-only in Commands. This pre-admission predicate uses
    // only registered actual producer evidence, never job.fire/currentFault;
    // an invalid Dense source cannot enter the original Guard/Matrix path.
    val outputLogicalOfferBad=g.io.job.valid &&
      ((isFfn(offeredOutput) && !((ffnDenseShape(offeredOutput) || ffnElementShape(offeredOutput)) && ffnInputs(offeredOutput))) ||
       (isOutputDense(offeredOutput) && !(denseOShape(offeredOutput) && denseOInputs(offeredOutput))) ||
       (isElementwise(offeredOutput) && !isFfn(offeredOutput) && !(elementShape(offeredOutput) &&
         Mux(offeredOutput.gdnElementwiseOp===GdnElementwiseOp.SigmoidMul.U,gateInputs(offeredOutput),residualInputs(offeredOutput)))) ||
       (isRuntimeNorm(offeredOutput) && (!normCommon(offeredOutput) ||
         (offeredOutput.qkRole===3.U && !postnormInputs(offeredOutput)))))
    when(outputLogicalOfferBad){poison:=true.B}
    val projectionProfile=authority.launch.profileId===2.U || authority.launch.profileId===4.U
    val projectionCurrent=authority.accepted && authority.transaction===projectionTransaction &&
      authority.launch.asUInt===projectionHost.asUInt
    val projectionStart=g.io.physicalJob.fire && g.io.physicalJob.bits.kind===QwenOwnerKind.Dense.U &&
      g.io.physicalJob.bits.qkRole=/=3.U && projectionProfile
    val pj=g.io.physicalJob.bits
    val projectionShape=pj.activationBf16 && pj.weightBf16 && pj.outputBf16 &&
      (pj.m>=1.U && pj.m<=128.U) && pj.qkRole<=2.U &&
      pj.k===Mux(authority.launch.profileId===2.U,1024.U,2048.U) &&
      pj.n===Mux(pj.qkRole===0.U,Mux(authority.launch.profileId===2.U,4096.U,8192.U),512.U) &&
      pj.writeBytes===(pj.m.pad(64)*pj.n.pad(64)<<1)(63,0)
    when(projectionStart){
      when(projectionBusy || g.io.phaseReserved || !authority.accepted || !authority.ownerValidated ||
        g.io.acceptedTransaction=/=authority.transaction || !projectionShape || pj.tag==="hffffffff".U){poison:=true.B}
      projectionPending:=pj;projectionBusy:=true.B
      when(!projectionCurrent || pj.qkRole===0.U){projectionValid:=VecInit(Seq.fill(3)(false.B))}
      projectionHost:=authority.launch;projectionTransaction:=authority.transaction
      when(pj.qkRole<=2.U){projectionValid(pj.qkRole):=false.B}
    }
    when(projectionBusy && g.io.physicalDone.valid && g.io.physicalDone.bits.tag=/=projectionPending.tag){poison:=true.B}
    when(projectionBusy && g.io.physicalDone.fire){
      val d=g.io.physicalDone.bits
      val exact=projectionCurrent && d.tag===projectionPending.tag && projectionPending.qkRole<=2.U &&
        d.status===Status.Ok.U && d.writeBytes===projectionPending.writeBytes &&
        d.usefulMacs===(projectionPending.m.pad(64)*projectionPending.n.pad(64)*projectionPending.k.pad(64))(63,0)
      when(exact && !poison && !currentIndependentFault && !authority.currentFault && !g.io.localFault){
        projectionJobs(projectionPending.qkRole):=projectionPending
        projectionResults(projectionPending.qkRole):=d;projectionValid(projectionPending.qkRole):=true.B
      }.otherwise{projectionValid:=VecInit(Seq.fill(3)(false.B));poison:=true.B}
      when(d.tag===projectionPending.tag){projectionBusy:=false.B}
    }
    when(poison || currentIndependentFault || authority.currentFault || g.io.localFault ||
      (projectionValid.asUInt.orR && !projectionCurrent)){projectionValid:=VecInit(Seq.fill(3)(false.B))}
    val prepReceiptValid=RegInit(false.B)
    val prepReceipt=Reg(new GdnRuntimeRawPrepReceiptV8)
    val slots=Seq(8,9)
    val busy=waiting || owned || awaitPrepare || acquirePending || retirePending || k.io.runtimePrepPrepare.get.valid ||
      slots.map(i=>a.io.status(i).active || a.io.status(i).retiring).reduce(_||_)
    val contextChanged=(waiting || owned) && (!authority.accepted ||
      authority.transaction=/=transaction || authority.launch.asUInt=/=host.asUInt)
    when(contextChanged || ((waiting || owned) &&
      (currentIndependentFault || authority.currentFault || g.io.localFault))){poison:=true.B}
    def isPrefix(j:QwenOwnerJob):Bool=isElementwise(j) || j.kind===QwenOwnerKind.GdnRmsNorm.U || j.kind===QwenOwnerKind.GdnConv.U || j.kind===QwenOwnerKind.GdnInputPrep.U || j.kind===QwenOwnerKind.GdnGatedNorm.U || j.kind===QwenOwnerKind.QkNorm256.U || j.kind===QwenOwnerKind.PartialRope64.U ||
      ((j.kind===QwenOwnerKind.KvAppend.U || j.kind===QwenOwnerKind.Attention.U) &&
        j.activationBf16 && j.weightBf16 && j.outputBf16)
    val logicalStart=g.io.job.fire && isPrefix(g.io.job.bits)
    // Acceptance authority is the original Guard handshake, not equality of
    // a raw job to a Host-provided packet. Its full snapshot is retained here.
    when(logicalStart){
      when(busy || g.io.phaseReserved || !authority.accepted || !authority.ownerValidated ||
        authority.currentFault || authority.ownerJob.asUInt=/=g.io.job.bits.asUInt){poison:=true.B}
      .otherwise{logical:=g.io.job.bits;host:=authority.launch;transaction:=authority.transaction;waiting:=true.B}
    }
    val normLogical=logicalStart && isRuntimeNorm(g.io.job.bits)
    when(normLogical){
      val q=g.io.job.bits
      normPostPhase:=authority.ownerPostnormValidated
      when(!normCommon(q) || authority.ownerPostnormValidated=/=(q.qkRole===3.U)){poison:=true.B}
      when(q.qkRole===3.U){
        postnormInput:=residualReceipt;postnormValid:=false.B
        when(!postnormInputs(q)){poison:=true.B}
      }
    }
    val elementLogical=logicalStart && isElementwise(g.io.job.bits)
    when(elementLogical){
      val q=g.io.job.bits
      when(isFfn(q)){
        ffnSourceA:=Mux(q.runtimeFfnPhase===3.U,ffnStages(0),ffnStages(3))
        ffnSourceB:=ffnStages(1)
        when(q.runtimeFfnPhase===5.U){elementInputA:=residualReceipt}
        when(!ffnElementShape(q) || !ffnInputs(q)){poison:=true.B}
      }.elsewhen(q.gdnElementwiseOp===GdnElementwiseOp.SigmoidMul.U){
        elementGateJob:=normalizedJobs(0);elementGateResult:=normalizedResults(0)
        elementInputB:=gqaOutputReceipt
        when(!elementShape(q) || !gateInputs(q)){poison:=true.B}
      }.otherwise{
        elementInputA:=hiddenReceipt;elementInputB:=denseOReceipt
        when(!elementShape(q) || !residualInputs(q)){poison:=true.B}
      }
    }
    val denseOLogicalStart=g.io.job.fire && isOutputDense(g.io.job.bits)
    when(denseOLogicalStart){
      when(denseOWaiting || denseOBusy || g.io.phaseReserved || !authority.accepted || !authority.ownerValidated ||
        !denseOShape(g.io.job.bits) || !denseOInputs(g.io.job.bits) ||
        authority.ownerJob.asUInt=/=g.io.job.bits.asUInt){poison:=true.B}
      denseOLogical:=g.io.job.bits;denseOSource:=mixedReceipt;denseOHost:=authority.launch
      denseOTransaction:=authority.transaction;denseOWaiting:=true.B;denseOValid:=false.B
    }
    val denseOContext=authority.accepted && authority.transaction===denseOTransaction &&
      authority.launch.asUInt===denseOHost.asUInt
    val denseOExpected=WireDefault(denseOLogical);denseOExpected.tag:=g.io.physicalJob.bits.tag
    val denseOPhysicalExact=denseOWaiting && !denseOBusy && denseOContext && !g.io.phaseReserved &&
      g.io.acceptedTransaction===denseOTransaction && g.io.physicalJob.bits.asUInt===denseOExpected.asUInt &&
      denseOShape(denseOLogical) && mixedValid && tailCurrent(mixedReceipt) &&
      denseOSource.asUInt===mixedReceipt.asUInt && tailSuccess(denseOSource) &&
      denseOSource.job.tag<g.io.physicalJob.bits.tag && g.io.physicalJob.bits.tag=/="hffffffff".U
    val denseOPhysicalBad=g.io.physicalJob.valid && isOutputDense(g.io.physicalJob.bits) && !denseOPhysicalExact
    when(denseOPhysicalBad || ((denseOWaiting || denseOBusy) && !denseOContext)){poison:=true.B}
    when(g.io.physicalJob.fire && isOutputDense(g.io.physicalJob.bits)){
      denseOPending:=g.io.physicalJob.bits;denseOWaiting:=false.B;denseOBusy:=true.B
      when(!denseOPhysicalExact){poison:=true.B}
      .otherwise{denseOConsumed:=true.B;denseOLastTransaction:=denseOTransaction;denseOLastProducer:=denseOSource.job.tag}
    }
    val denseOTerminalExact=denseOContext && g.io.physicalDone.bits.tag===denseOPending.tag &&
      (g.io.physicalDone.bits.status=/=Status.Ok.U ||
        (g.io.physicalDone.bits.writeBytes===denseOPending.writeBytes &&
         g.io.physicalDone.bits.usefulMacs===(denseOPending.m.pad(64)*denseOPending.n.pad(64)*denseOPending.k.pad(64))(63,0)))
    when(denseOBusy && g.io.physicalDone.valid && !denseOTerminalExact){poison:=true.B}
    when(denseOBusy && g.io.physicalDone.fire){
      when(!denseOTerminalExact){poison:=true.B}
      .otherwise{
        denseOBusy:=false.B
        when(g.io.physicalDone.bits.status===Status.Ok.U && !poison && !currentIndependentFault &&
          !authority.currentFault && !g.io.localFault){
          denseOReceipt.host:=denseOHost;denseOReceipt.transactionId:=denseOTransaction
          denseOReceipt.job:=denseOPending;denseOReceipt.result:=g.io.physicalDone.bits;denseOValid:=true.B
        }
      }
    }
    val ffnDenseStart=g.io.job.fire && isFfnDense(g.io.job.bits)
    val ffnLogicalStart=ffnDenseStart || (elementLogical && isFfn(g.io.job.bits))
    when(ffnLogicalStart){ffnReceiptValid:=false.B}
    when(ffnDenseStart){
      val q=g.io.job.bits
      when(ffnDenseWaiting || ffnDenseBusy || g.io.phaseReserved || !authority.accepted || !authority.ownerValidated ||
        !ffnDenseShape(q) || !ffnInputs(q) || authority.ownerJob.asUInt=/=q.asUInt){poison:=true.B}
      ffnDenseLogical:=q;ffnDenseHost:=authority.launch;ffnDenseTransaction:=authority.transaction
      ffnNormSource:=postnormReceipt;ffnSourceA:=Mux(q.runtimeFfnPhase===4.U,ffnStages(2),ffnStages(0))
      ffnDenseWaiting:=true.B
    }
    val ffnDenseContext=authority.accepted && authority.transaction===ffnDenseTransaction &&
      authority.launch.asUInt===ffnDenseHost.asUInt
    val ffnDenseExpected=WireDefault(ffnDenseLogical);ffnDenseExpected.tag:=g.io.physicalJob.bits.tag
    val ffnDensePrior=Mux(ffnDenseLogical.runtimeFfnPhase===4.U,
      ffnSourceA.asUInt===ffnStages(2).asUInt && ffnSourceA.job.tag<g.io.physicalJob.bits.tag,
      ffnNormSource.asUInt===postnormReceipt.asUInt && ffnNormSource.job.tag<g.io.physicalJob.bits.tag &&
        (ffnDenseLogical.runtimeFfnPhase=/=2.U || (ffnSourceA.asUInt===ffnStages(0).asUInt &&
          ffnSourceA.job.tag<g.io.physicalJob.bits.tag)))
    val ffnDensePhysicalExact=ffnDenseWaiting && !ffnDenseBusy && ffnDenseContext && !g.io.phaseReserved &&
      g.io.acceptedTransaction===ffnDenseTransaction && g.io.physicalJob.bits.asUInt===ffnDenseExpected.asUInt &&
      g.io.physicalJob.bits.tag=/="hffffffff".U && ffnDenseShape(ffnDenseLogical) &&
      ffnInputs(ffnDenseLogical) && ffnDensePrior
    val ffnDensePhysicalBad=g.io.physicalJob.valid && isFfnDense(g.io.physicalJob.bits) && !ffnDensePhysicalExact
    when(ffnDensePhysicalBad || ((ffnDenseWaiting || ffnDenseBusy) && !ffnDenseContext)){poison:=true.B}
    when(g.io.physicalJob.fire && isFfnDense(g.io.physicalJob.bits)){
      ffnDensePending:=g.io.physicalJob.bits;ffnDenseWaiting:=false.B;ffnDenseBusy:=true.B
      when(!ffnDensePhysicalExact){poison:=true.B}
        .otherwise{ffnIssued(ffnDenseLogical.runtimeFfnPhase-1.U):=true.B}
    }
    val ffnDenseTerminalExact=ffnDenseContext && g.io.physicalDone.bits.tag===ffnDensePending.tag &&
      (g.io.physicalDone.bits.status=/=Status.Ok.U ||
        (g.io.physicalDone.bits.writeBytes===ffnDensePending.writeBytes &&
         g.io.physicalDone.bits.usefulMacs===(ffnDensePending.m.pad(64)*ffnDensePending.n.pad(64)*ffnDensePending.k.pad(64))(63,0)))
    when(ffnDenseBusy && g.io.physicalDone.valid && !ffnDenseTerminalExact){poison:=true.B}
    when(ffnDenseBusy && g.io.physicalDone.fire){
      when(!ffnDenseTerminalExact){poison:=true.B}
      .otherwise{
        ffnDenseBusy:=false.B
        when(g.io.physicalDone.bits.status===Status.Ok.U && !poison && !currentIndependentFault &&
          !authority.currentFault && !g.io.localFault){
          val r=Wire(new HostRuntimeFfnStagedReceiptV17)
          r.host:=ffnDenseHost;r.transactionId:=ffnDenseTransaction;r.job:=ffnDensePending
          r.logicalJob:=ffnDenseLogical;r.result:=g.io.physicalDone.bits
          ffnReceipt:=r;ffnReceiptValid:=true.B
          ffnStages(ffnDensePending.runtimeFfnPhase-1.U):=r;ffnValid(ffnDensePending.runtimeFfnPhase-1.U):=true.B
        }
      }
    }
    val gatedLogical=logicalStart && g.io.job.bits.kind===QwenOwnerKind.GdnGatedNorm.U
    when(gatedLogical){
      val r=chunkReceipt.bits;val c=r.result.accepted
      gatedProducer:=r.producer.ownerSequence;gatedSource:=r
      when(!chunkReceipt.valid || r.producer.transactionId=/=authority.transaction ||
        r.producer.hostEpoch=/=authority.launch.epoch || r.result.status=/=Status.Ok.U ||
        !r.result.stagedComplete || !r.result.drained || c.context.tag=/=r.producer.ownerSequence ||
        c.context.output=/=g.io.job.bits.a || c.context.tokens=/=g.io.job.bits.m ||
        c.layout.valueHeads=/=g.io.job.bits.n ||
        r.result.outputAckBytes=/=(g.io.job.bits.m.pad(64)*g.io.job.bits.n.pad(64)*256.U)(63,0) ||
        (gatedConsumed && (r.producer.transactionId<lastGatedTransaction ||
          (r.producer.transactionId===lastGatedTransaction && r.producer.ownerSequence<=lastGatedProducer)))){poison:=true.B}
    }
    val qkLogical=logicalStart && g.io.job.bits.kind===QwenOwnerKind.QkNorm256.U
    when(qkLogical){
      val q=g.io.job.bits;val role=q.qkRole(0);val p=projectionJobs(role);val d=projectionResults(role)
      qkProducer:=p;qkProducerResult:=d
      when(q.qkRole>1.U || !projectionValid.asUInt.andR || !projectionCurrent || projectionBusy ||
        p.dst=/=q.a || p.m=/=q.m || p.qkRole=/=q.qkRole || p.tag=/=d.tag ||
        p.n=/=(q.n*Mux(q.qkRole===0.U,512.U,256.U)) ||
        d.status=/=Status.Ok.U || d.writeBytes=/=p.writeBytes ||
        (qkConsumed(role) && (projectionTransaction<qkLastTransaction(role) ||
          (projectionTransaction===qkLastTransaction(role) && p.tag<=qkLastProducer(role))))){poison:=true.B}
    }
    val ropeLogical=logicalStart && g.io.job.bits.kind===QwenOwnerKind.PartialRope64.U
    when(ropeLogical){
      val q=g.io.job.bits;val role=q.qkRole(0);val p=normalizedJobs(role);val d=normalizedResults(role)
      ropeProducer:=p;ropeProducerResult:=d
      when(q.qkRole>1.U || !normalizedValid.asUInt.andR || !normalizedCurrent ||
        p.dst=/=q.a || p.m=/=q.m || p.n=/=q.n || p.k=/=q.k || p.qkRole=/=q.qkRole ||
        p.tag=/=d.tag || d.accepted.tag=/=p.tag || d.accepted.output=/=q.a ||
        d.status=/=Status.Ok.U || !d.outputCommitted || d.outputAckBytes=/=p.writeBytes ||
        d.writeBytes=/=p.writeBytes || (q.qkRole===1.U && !ropeQCommitted) ||
        (ropeConsumed(role) && (normalizedTransaction<ropeLastTransaction(role) ||
          (normalizedTransaction===ropeLastTransaction(role) && p.tag<=ropeLastProducer(role))))){poison:=true.B}
    }
    val kvLogical=logicalStart && g.io.job.bits.kind===QwenOwnerKind.KvAppend.U
    when(kvLogical){
      val q=g.io.job.bits;val v=projectionJobs(2);val vd=projectionResults(2)
      kvKeyProducer:=rotatedKJob;kvKeyResult:=rotatedKResult
      kvValueProducer:=v;kvValueResult:=vd;kvReceiptValid:=false.B
      when(!rotatedKValid || !rotatedKCurrent || !ropeQCommitted || !projectionCurrent ||
        !projectionValid.asUInt.andR || projectionBusy ||
        rotatedKTransaction=/=projectionTransaction || rotatedKHost.asUInt=/=projectionHost.asUInt ||
        rotatedKJob.qkRole=/=1.U || rotatedKJob.n=/=2.U || rotatedKJob.k=/=256.U ||
        rotatedKJob.dst=/=q.a || rotatedKJob.m=/=q.m || rotatedKJob.tag=/=rotatedKResult.tag ||
        rotatedKResult.accepted.output=/=q.a || rotatedKResult.accepted.positionBase=/=q.queryStart ||
        rotatedKResult.status=/=Status.Ok.U || !rotatedKResult.outputCommitted ||
        rotatedKResult.outputAckBytes=/=(q.m.pad(64)<<10) ||
        v.qkRole=/=2.U || v.n=/=512.U || v.m=/=q.m || v.dst=/=q.b ||
        v.tag=/=vd.tag || vd.status=/=Status.Ok.U || vd.writeBytes=/=(q.m.pad(64)<<10) ||
        (kvConsumed && (projectionTransaction<kvLastTransaction ||
          (projectionTransaction===kvLastTransaction &&
            (rotatedKJob.tag<=kvLastKey || v.tag<=kvLastValue))))){poison:=true.B}
    }
    val gqaLogical=logicalStart && g.io.job.bits.kind===QwenOwnerKind.Attention.U
    when(gqaLogical){
      val q=g.io.job.bits;val p=rotatedQJob;val d=rotatedQResult
      val c=kvReceipt.job;val r=kvReceipt.result
      gqaQueryProducer:=p;gqaQueryResult:=d;gqaCacheProducer:=kvReceipt
      when(!rotatedQValid || !rotatedQCurrent || !ropeQCommitted || !kvReceiptValid || !kvReceiptCurrent ||
        rotatedQTransaction=/=kvReceipt.transactionId || rotatedQHost.asUInt=/=kvReceipt.host.asUInt ||
        p.qkRole=/=0.U || p.m=/=q.m || p.n=/=(q.n>>8) || p.k=/=q.k || p.dst=/=q.a ||
        p.qkPositionBase=/=q.queryStart || p.tag=/=d.tag || d.accepted.tag=/=p.tag ||
        d.accepted.asUInt=/=PartialRopeRuntimeJobV12.fromOwner(p).asUInt ||
        d.accepted.output=/=q.a || d.accepted.positionBase=/=q.queryStart ||
        d.status=/=Status.Ok.U || !d.outputCommitted || d.outputAckBytes=/=q.writeBytes || d.writeBytes=/=q.writeBytes ||
        c.kind=/=QwenOwnerKind.KvAppend.U || c.tag=/=r.tag || c.m=/=q.m || c.dst=/=q.b ||
        c.cacheCapacity=/=q.cacheCapacity || c.queryStart=/=q.queryStart ||
        c.cacheLength=/=q.expectedCacheLength || c.expectedCacheLength=/=q.expectedCacheLength ||
        c.currentGeneration=/=q.currentGeneration || c.expectedGeneration=/=q.expectedGeneration || c.cold=/=q.cold ||
        r.accepted.asUInt=/=Bf16KvAppendRuntimeJobV13.fromOwner(c).asUInt ||
        r.status=/=Status.Ok.U || !r.proposalValid || !r.drained || r.cacheBase=/=q.b ||
        r.capacityTokens=/=q.cacheCapacity || r.proposedLength=/=q.cacheLength ||
        r.proposedGeneration=/=q.expectedGeneration+&1.U ||
        r.keyAckBytes=/=(q.m.pad(64)<<10) || r.valueAckBytes=/=(q.m.pad(64)<<10) ||
        r.writeBytes=/=(q.m.pad(64)<<11) || r.memoryAccepted=/=(q.m.pad(32)<<6) ||
        r.memoryReturned=/=r.memoryAccepted ||
        (gqaConsumed && (kvReceipt.transactionId<gqaLastTransaction ||
          (kvReceipt.transactionId===gqaLastTransaction && (p.tag<=gqaLastQuery || c.tag<=gqaLastCache))))){poison:=true.B}
    }
    // Replacing either producer invalidates eligibility, never transport debt.
    when(projectionStart || (qkLogical && g.io.job.bits.qkRole===0.U) ||
      (ropeLogical && g.io.job.bits.qkRole===0.U)){rotatedQValid:=false.B}
    when(poison || currentIndependentFault || authority.currentFault || g.io.localFault ||
      (rotatedQValid && !rotatedQCurrent)){rotatedQValid:=false.B}
    when(projectionStart || qkLogical || ropeLogical){rotatedKValid:=false.B;kvReceiptValid:=false.B}
    when(poison || currentIndependentFault || authority.currentFault || g.io.localFault ||
      (rotatedKValid && !rotatedKCurrent)) {rotatedKValid:=false.B;kvReceiptValid:=false.B}
    // Replacement invalidation is not debt cancellation. Both Q and K must
    // be newly acknowledged before a new pair can feed the rotary owner.
    when((projectionStart && pj.qkRole===0.U) || (qkLogical && g.io.job.bits.qkRole===0.U)){
      normalizedValid:=VecInit(Seq.fill(2)(false.B));ropeQCommitted:=false.B
    }
    when(qkLogical && g.io.job.bits.qkRole===1.U){normalizedValid(1):=false.B}
    when(poison || currentIndependentFault || authority.currentFault || g.io.localFault ||
      (normalizedValid.asUInt.orR && !normalizedCurrent)){
      normalizedValid:=VecInit(Seq.fill(2)(false.B));ropeQCommitted:=false.B
    }
    // A replacement producer invalidates the old private snapshot at the
    // real Guard logical acceptance, even if that replacement later fails.
    val prepReplacement=logicalStart && g.io.job.bits.kind===QwenOwnerKind.GdnInputPrep.U
    when(prepReplacement){prepReceiptValid:=false.B}
    val expected=WireDefault(logical);expected.tag:=g.io.physicalJob.bits.tag
    val normShape=normCommon(logical) && normPostPhase===(logical.qkRole===3.U)
    val postnormShape=normShape && normPostPhase
    val normScalarOperations=logical.m.pad(64)*Mux(logical.n===1024.U,5228.U,10412.U)
    val normFormatOperations=logical.m.pad(64)*logical.n.pad(64)
    val normMemoryOperations=normFormatOperations>>3
    val convShape=logical.kind===QwenOwnerKind.GdnConv.U &&
      logical.activationBf16 && logical.weightBf16 && logical.outputBf16 &&
      logical.m>=1.U && logical.m<=128.U && logical.k===4.U &&
      Mux(host.profileId===1.U,logical.n===6144.U,host.profileId===3.U && logical.n===8192.U) &&
      logical.cold && logical.expectedGeneration===0.U && logical.currentGeneration===0.U &&
      logical.writeBytes===(((logical.m.pad(80)*logical.n.pad(80))<<1)+(logical.n.pad(80)<<3))(63,0)
    val prepShape=logical.kind===QwenOwnerKind.GdnInputPrep.U &&
      logical.activationBf16 && !logical.weightBf16 && !logical.outputBf16 &&
      logical.m>=1.U && logical.m<=128.U && logical.k===128.U &&
      Mux(host.profileId===1.U,logical.n===16.U,host.profileId===3.U && logical.n===32.U) &&
      logical.cold && logical.expectedGeneration===0.U && logical.currentGeneration===0.U && !logical.gdnRecurrentMode &&
      logical.writeBytes===(logical.m.pad(80)*logical.n.pad(80)*1600.U)(63,0)
    val gatedShape=logical.kind===QwenOwnerKind.GdnGatedNorm.U &&
      logical.activationBf16 && !logical.weightBf16 && logical.outputBf16 &&
      (logical.m===16.U || logical.m===128.U) && logical.k===128.U &&
      Mux(host.profileId===1.U,logical.n===16.U,host.profileId===3.U && logical.n===32.U) &&
      logical.cold && logical.expectedGeneration===0.U && logical.currentGeneration===0.U &&
      logical.writeBytes===(logical.m.pad(64)*logical.n.pad(64)*256.U)(63,0)
    val qkShape=logical.kind===QwenOwnerKind.QkNorm256.U &&
      logical.activationBf16 && logical.weightBf16 && logical.outputBf16 &&
      (logical.m>=1.U && logical.m<=128.U) && logical.k===256.U && logical.qkRole<=1.U &&
      (host.profileId===2.U || host.profileId===4.U) &&
      logical.n===Mux(logical.qkRole===0.U,Mux(host.profileId===2.U,8.U,16.U),2.U) &&
      (logical.qkNormPolicy==="hc1".U || logical.qkNormPolicy==="hc2".U) &&
      logical.cold && logical.expectedGeneration===0.U && logical.currentGeneration===0.U &&
      logical.writeBytes===(logical.m.pad(64)*logical.n.pad(64)*Mux(logical.qkRole===0.U,1024.U,512.U))(63,0)
    val ropeShape=logical.kind===QwenOwnerKind.PartialRope64.U &&
      logical.activationBf16 && logical.weightBf16 && logical.outputBf16 &&
      logical.m>=1.U && logical.m<=128.U && logical.k===256.U && logical.qkRole<=1.U &&
      (host.profileId===2.U || host.profileId===4.U) &&
      logical.n===Mux(logical.qkRole===0.U,Mux(host.profileId===2.U,8.U,16.U),2.U) &&
      logical.qkNormPolicy==="hb1".U && logical.qkTrigTokens>0.U &&
      logical.qkPositionBase.pad(65)+logical.m.pad(65)<=logical.qkTrigTokens.pad(65) &&
      logical.cold && logical.expectedGeneration===0.U && logical.currentGeneration===0.U &&
      logical.writeBytes===(logical.m.pad(64)*logical.n.pad(64)*512.U)(63,0)
    val kvShape=logical.kind===QwenOwnerKind.KvAppend.U &&
      logical.activationBf16 && logical.weightBf16 && logical.outputBf16 &&
      (host.profileId===2.U || host.profileId===4.U) && logical.m>=1.U && logical.m<=128.U &&
      logical.n===512.U && logical.k===256.U && logical.cacheCapacity===128.U &&
      logical.cold && logical.queryStart===0.U && logical.cacheLength===0.U && logical.expectedCacheLength===0.U &&
      logical.expectedGeneration===0.U && logical.currentGeneration===0.U &&
      logical.writeBytes===(logical.m.pad(64)<<11)
    // First installed chain is cold whole-window M128/C128. Runtime Q8/Q16
    // select the SAME fixed leaf/service. Pair-high-first order is bound by
    // Commands' accepted common A1 policy, never by a raw leaf preference.
    val gqaShape=logical.kind===QwenOwnerKind.Attention.U &&
      logical.activationBf16 && logical.weightBf16 && logical.outputBf16 &&
      (host.profileId===2.U || host.profileId===4.U) && logical.m===128.U &&
      logical.n===Mux(host.profileId===2.U,2048.U,4096.U) && logical.k===256.U &&
      logical.qkRole===0.U && logical.qkNormPolicy===1.U &&
      logical.cacheCapacity===128.U && logical.cacheLength===128.U &&
      logical.cold && logical.queryStart===0.U && logical.expectedCacheLength===0.U &&
      logical.expectedGeneration===0.U && logical.currentGeneration===0.U &&
      logical.writeBytes===(logical.m.pad(64)*logical.n.pad(64)<<1)(63,0)
    // Full input widths are multiplied before any narrowing; the domain has
    // at most 59 significant bits. Only validated bounded jobs become leases.
    val gqaScalarOperations=(logical.m*logical.cacheLength*(logical.n>>8)*6.U).pad(64)
    val gqaQueryTiles=(logical.m.pad(17)+15.U)>>4
    val gqaKeyTiles=(logical.cacheLength.pad(33)+31.U)>>5
    val gqaMatrixGroups=(gqaQueryTiles*(logical.n>>8)*(gqaKeyTiles+1.U)).pad(64)
    val gqaMemoryOperations=(((logical.m.pad(64)+(gqaQueryTiles*logical.cacheLength).pad(64))*(logical.n>>8))<<4)
    val elementwiseShape=elementShape(logical)
    val elementwiseSigmoid=elementwiseShape && logical.gdnElementwiseOp===GdnElementwiseOp.SigmoidMul.U
    val elementwiseLanes=logical.m.pad(64)*logical.n.pad(64)
    val elementwiseSilu=elementwiseShape && logical.gdnElementwiseOp===GdnElementwiseOp.SiluMul.U
    val elementwiseScalarOperations=elementwiseLanes*Mux(elementwiseSilu,6.U,Mux(elementwiseSigmoid,5.U,1.U))
    val elementwiseFormatOperations=elementwiseLanes*Mux(elementwiseSigmoid || elementwiseSilu,2.U,1.U)
    val elementwiseMemoryOperations=(elementwiseLanes>>5)*3.U
    val logicalShape=normShape || convShape || prepShape || gatedShape || qkShape || ropeShape || kvShape || elementwiseShape ||
      (gqaShape && gqaScalarOperations>0.U && gqaScalarOperations<=UnifiedMoeArithmeticClientV5.OrdinaryGqaMaximumOperations.U)
    val physicalExact=waiting && !owned && !g.io.phaseReserved && !contextChanged &&
      g.io.acceptedTransaction===transaction && g.io.physicalJob.bits.asUInt===expected.asUInt &&
      g.io.physicalJob.bits.tag=/="hffffffff".U && logicalShape &&
      (!postnormShape || (postnormInputs(logical) &&
        postnormInput.asUInt===residualReceipt.asUInt && postnormInput.transactionId===transaction &&
        postnormInput.host.asUInt===host.asUInt && postnormInput.job.tag<g.io.physicalJob.bits.tag &&
        postnormInput.job.tag=/="hffffffff".U)) &&
      (!qkShape || (projectionCurrent && projectionValid.asUInt.andR && !projectionBusy &&
        qkProducer.tag<g.io.physicalJob.bits.tag && qkProducer.tag=/="hffffffff".U &&
        qkProducer.dst===logical.a && qkProducer.m===logical.m && qkProducer.qkRole===logical.qkRole &&
        qkProducerResult.tag===qkProducer.tag && qkProducerResult.status===Status.Ok.U &&
        qkProducerResult.writeBytes===qkProducer.writeBytes)) &&
      (!ropeShape || (normalizedCurrent && normalizedValid.asUInt.andR &&
        ropeProducer.tag<g.io.physicalJob.bits.tag && ropeProducer.tag=/="hffffffff".U &&
        ropeProducer.dst===logical.a && ropeProducer.m===logical.m && ropeProducer.n===logical.n &&
        ropeProducer.qkRole===logical.qkRole && ropeProducerResult.tag===ropeProducer.tag &&
        ropeProducerResult.status===Status.Ok.U && ropeProducerResult.outputCommitted &&
        ropeProducerResult.outputAckBytes===ropeProducer.writeBytes &&
        (logical.qkRole===0.U || ropeQCommitted))) &&
      (!kvShape || (rotatedKValid && rotatedKCurrent && projectionCurrent && projectionValid.asUInt.andR &&
        !projectionBusy && ropeQCommitted &&
        kvKeyProducer.tag<g.io.physicalJob.bits.tag && kvValueProducer.tag<g.io.physicalJob.bits.tag &&
        kvKeyProducer.tag=/="hffffffff".U && kvValueProducer.tag=/="hffffffff".U &&
        kvKeyProducer.asUInt===rotatedKJob.asUInt && kvKeyResult.asUInt===rotatedKResult.asUInt &&
        kvValueProducer.asUInt===projectionJobs(2).asUInt && kvValueResult.asUInt===projectionResults(2).asUInt)) &&
      (!gqaShape || (rotatedQValid && rotatedQCurrent && ropeQCommitted && kvReceiptValid && kvReceiptCurrent &&
        rotatedQTransaction===transaction && rotatedQHost.asUInt===host.asUInt &&
        gqaCacheProducer.transactionId===transaction && gqaCacheProducer.host.asUInt===host.asUInt &&
        gqaQueryProducer.tag<g.io.physicalJob.bits.tag && gqaCacheProducer.job.tag<g.io.physicalJob.bits.tag &&
        gqaQueryProducer.tag=/="hffffffff".U && gqaCacheProducer.job.tag=/="hffffffff".U &&
        gqaQueryProducer.asUInt===rotatedQJob.asUInt && gqaQueryResult.asUInt===rotatedQResult.asUInt &&
        gqaCacheProducer.asUInt===kvReceipt.asUInt)) &&
      (!elementwiseShape || Mux(isFfn(logical),
        ffnInputs(logical) && ffnSourceA.job.tag<g.io.physicalJob.bits.tag &&
        Mux(logical.runtimeFfnPhase===3.U,
          ffnSourceA.asUInt===ffnStages(0).asUInt && ffnSourceB.asUInt===ffnStages(1).asUInt &&
            ffnSourceB.job.tag<g.io.physicalJob.bits.tag,
          ffnSourceA.asUInt===ffnStages(3).asUInt && elementInputA.asUInt===residualReceipt.asUInt &&
            elementInputA.job.tag<g.io.physicalJob.bits.tag),
        (elementInputB.job.tag<g.io.physicalJob.bits.tag &&
        elementInputB.job.tag=/="hffffffff".U && elementInputB.transactionId===transaction &&
        elementInputB.host.asUInt===host.asUInt &&
        Mux(elementwiseSigmoid,
          gateInputs(logical) && elementGateJob.tag<g.io.physicalJob.bits.tag && elementGateJob.tag=/="hffffffff".U &&
          elementGateJob.asUInt===gqaGateJob.asUInt && elementGateResult.asUInt===gqaGateResult.asUInt &&
          elementInputB.asUInt===gqaOutputReceipt.asUInt,
          residualInputs(logical) && elementInputA.job.tag<g.io.physicalJob.bits.tag &&
          elementInputA.job.tag=/="hffffffff".U && elementInputA.transactionId===transaction &&
          elementInputA.host.asUInt===host.asUInt && elementInputA.asUInt===hiddenReceipt.asUInt &&
          elementInputB.asUInt===denseOReceipt.asUInt)))) &&
      (!gatedShape || (g.io.physicalJob.bits.tag>gatedProducer && gatedProducer=/="hffffffff".U &&
        gatedSource.producer.transactionId===transaction && gatedSource.producer.hostEpoch===host.epoch &&
        gatedSource.producer.ownerSequence===gatedProducer && gatedSource.result.accepted.context.output===logical.a &&
        gatedSource.result.accepted.context.tokens===logical.m && gatedSource.result.accepted.layout.valueHeads===logical.n))
    val physicalOfferBad=g.io.physicalJob.valid && isPrefix(g.io.physicalJob.bits) && !physicalExact
    when(physicalOfferBad){poison:=true.B}
    val packets=(0 until 2).map{i=>
      val p=WireDefault(0.U.asTypeOf(new UnifiedMoeArithmeticLeaseV5))
      p.authorityKind:=Mux(elementwiseShape,UnifiedArithmeticAuthorityKindV5.OrdinaryElementwise.U,Mux(gqaShape,UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U,Mux(ropeShape,UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U,Mux(qkShape,UnifiedArithmeticAuthorityKindV5.OrdinaryQkNorm.U,Mux(gatedShape,UnifiedArithmeticAuthorityKindV5.OrdinaryGatedNorm.U,
        Mux(convShape,UnifiedArithmeticAuthorityKindV5.OrdinaryConv.U,UnifiedArithmeticAuthorityKindV5.OrdinaryNorm.U))))))
      p.allocationValid:=false.B;p.allocationSequence:=0.U // deliberately NOT a MoE allocation
      p.hostEpoch:=host.epoch;p.lease.identity.transactionId:=transaction
      p.lease.identity.ownerSequence:=g.io.physicalJob.bits.tag;p.lease.identity.stage:=Mux(elementwiseShape,77.U,Mux(gqaShape,76.U,Mux(ropeShape,75.U,Mux(qkShape,74.U,Mux(gatedShape,73.U,Mux(convShape,70.U,69.U))))))
      p.lease.resource:=(if(i==0)2 else 1).U
      p.lease.expectedOperations:=Mux(elementwiseShape,(if(i==0)elementwiseScalarOperations(31,0) else elementwiseFormatOperations(31,0)),Mux(gqaShape,(if(i==0)gqaScalarOperations(31,0) else 0.U),logical.m.pad(32)*
        (if(i==0)Mux(ropeShape,logical.n.pad(32)*192.U,Mux(qkShape,logical.n.pad(32)*Mux(logical.qkNormPolicy==="hc2".U,1316.U,1290.U),Mux(gatedShape,logical.n.pad(32)*1284.U,Mux(convShape,logical.n.pad(32)*13.U,Mux(logical.n===1024.U,5228.U(32.W),10412.U(32.W))))))
         else Mux(qkShape || ropeShape,0.U,Mux(gatedShape,logical.n.pad(32)*256.U,Mux(convShape,logical.n.pad(32)<<1,logical.n.pad(32)))))))
      p
    }
    // This is distinct from provenance/identity: a held Guard job is still
    // accepted under late fault, but may NOT acquire a fresh arithmetic lease.
    val acquireClean= !currentIndependentFault && !authority.currentFault && !g.io.localFault
    val start=g.io.physicalJob.fire && isPrefix(g.io.physicalJob.bits)
    acquirePending:=false.B;retirePending:=false.B
    when(start){
      // Even rejected provenance cannot erase an ACTUALLY accepted Kernel job.
      // Retain its physical ownership and poison: no new memory effect or
      // arithmetic lease is allowed, and recovery may require joint reset.
      physical:=g.io.physicalJob.bits.tag;waiting:=false.B;owned:=true.B;awaitPrepare:=false.B;leaseEventSubmitted:=false.B
      when(!physicalExact || poison || !acquireClean){poison:=true.B}
      .elsewhen(kvShape){
        // Memory-only mode12: do not mint kind8, a Scalar lease, or arithmetic operations.
        kvConsumed:=true.B;kvLastTransaction:=transaction
        kvLastKey:=kvKeyProducer.tag;kvLastValue:=kvValueProducer.tag
      }
      .elsewhen(prepShape){awaitPrepare:=true.B}
      .otherwise{
        acquirePending:=true.B;leaseEventSubmitted:=true.B;for(i<-0 until 2){leases(i):=packets(i)}
        when(postnormShape){
          postnormConsumed:=true.B;postnormLastTransaction:=transaction;postnormLastProducer:=postnormInput.job.tag
        }
        when(qkShape){
          normalizedHost:=host;normalizedTransaction:=transaction
          val role=logical.qkRole(0);qkConsumed(role):=true.B
          qkLastProducer(role):=qkProducer.tag;qkLastTransaction(role):=transaction
        }
        when(ropeShape){
          val role=logical.qkRole(0);ropeConsumed(role):=true.B
          ropeLastProducer(role):=ropeProducer.tag;ropeLastTransaction(role):=transaction
        }
        when(gqaShape){
          gqaConsumed:=true.B;gqaLastTransaction:=transaction
          gqaLastQuery:=gqaQueryProducer.tag;gqaLastCache:=gqaCacheProducer.job.tag
        }
        when(elementwiseShape && isFfn(logical)){ffnIssued(logical.runtimeFfnPhase-1.U):=true.B}
        when(elementwiseShape && !isFfn(logical)){
          val role=elementwiseSigmoid.asUInt;elementConsumed(role):=true.B;elementLastTransaction(role):=transaction
          elementLastA(role):=Mux(elementwiseSigmoid,elementGateJob.tag,elementInputA.job.tag)
          elementLastB(role):=elementInputB.job.tag
        }
        when(gatedShape){gatedConsumed:=true.B;lastGatedProducer:=gatedProducer;lastGatedTransaction:=transaction}
      }
    }
    // RawPrep must first obtain true Guard-owned DDR responses. Its prepare
    // event is the child retained job plus counts derived from cached A_log;
    // no Host expected-count hint or manufactured allocation is accepted.
    val prep=k.io.runtimePrepPrepare.get
    val retainedPhysical=WireDefault(logical);retainedPhysical.tag:=physical
    val expectedPrep=GdnRuntimeRawPrepJobV7.fromOwner(retainedPhysical)
    val prepBase=Mux(expectedPrep.reductionPolicy===1.U,908.U(32.W),910.U(32.W))
    val exactScalar=(logical.m.pad(64)*(logical.n.pad(64)*prepBase+prep.bits.nonnegativeALog.pad(64)))(31,0)
    val exactFormat=(logical.m.pad(32)*logical.n.pad(32))(31,0)
    val prepareExact=owned && awaitPrepare && prepShape && !contextChanged && !leaseEventSubmitted &&
      prep.bits.accepted.asUInt===expectedPrep.asUInt && prep.bits.nonnegativeALog<=logical.n &&
      prep.bits.acknowledgedALogReads===(logical.n>>4) &&
      prep.bits.scalarOperations===exactScalar && prep.bits.formatOperations===exactFormat &&
      exactScalar>0.U && exactScalar<=3731456.U && exactFormat>0.U && exactFormat<=4096.U
    val prepareBad=prep.valid && !prepareExact
    when(prepareBad){poison:=true.B}
    // Identity-valid held events may finish transport under a late independent
    // fault, but they do NOT receive new arithmetic authority in that case.
    prep.ready:=prepareExact && !acquirePending && !retirePending &&
      slots.map(i=> !a.io.status(i).active && !a.io.status(i).retiring).reduce(_&&_)
    val prepPackets=(0 until 2).map{i=>
      val p=WireDefault(0.U.asTypeOf(new UnifiedMoeArithmeticLeaseV5))
      p.authorityKind:=UnifiedArithmeticAuthorityKindV5.OrdinaryRawPrep.U
      p.allocationValid:=false.B;p.allocationSequence:=0.U;p.hostEpoch:=host.epoch
      p.lease.identity.transactionId:=transaction;p.lease.identity.ownerSequence:=physical
      p.lease.identity.stage:=71.U;p.lease.resource:=(if(i==0)2 else 1).U
      p.lease.expectedOperations:=(if(i==0)prep.bits.scalarOperations else prep.bits.formatOperations)
      p
    }
    when(prep.fire){
      awaitPrepare:=false.B
      when(poison || !acquireClean){poison:=true.B}
        .otherwise{acquirePending:=true.B;leaseEventSubmitted:=true.B;for(i<-0 until 2){leases(i):=prepPackets(i)}}
    }
    val gatedEvent=k.io.runtimeGatedDoneFire.get
    val gatedExpected=GdnRuntimeGatedNormJobV10.fromOwner(retainedPhysical)
    val gatedCountsExact=slots.indices.map(i=>a.io.status(slots(i)).lease.asUInt===leases(i).asUInt &&
      a.io.status(slots(i)).counts.returned===leases(i).lease.expectedOperations.pad(33) &&
      a.io.status(slots(i)).resourcesDrained).reduce(_&&_)
    val gatedTerminalExact=gatedEvent.bits.tag===physical &&
      gatedEvent.bits.accepted.asUInt===gatedExpected.asUInt &&
      gatedEvent.bits.status===g.io.physicalDone.bits.status &&
      gatedEvent.bits.writeBytes===g.io.physicalDone.bits.writeBytes &&
      gatedEvent.bits.cycles===g.io.physicalDone.bits.cycles &&
      (gatedEvent.bits.status=/=Status.Ok.U || (leaseEventSubmitted && gatedEvent.bits.outputCommitted &&
        gatedEvent.bits.writeBytes===logical.writeBytes && gatedCountsExact))
    val qkEvent=k.io.runtimeQkNormDoneFire.get
    val qkExpected=QkNormRuntimeJobV11.fromOwner(retainedPhysical)
    val qkScalarExact=a.io.status(8).lease.asUInt===leases(0).asUInt &&
      a.io.status(8).counts.returned===leases(0).lease.expectedOperations.pad(33) && a.io.status(8).resourcesDrained
    val qkTerminalExact=qkEvent.bits.tag===physical && qkEvent.bits.accepted.asUInt===qkExpected.asUInt &&
      qkEvent.bits.status===g.io.physicalDone.bits.status && qkEvent.bits.writeBytes===g.io.physicalDone.bits.writeBytes &&
      qkEvent.bits.cycles===g.io.physicalDone.bits.cycles &&
      (qkEvent.bits.status=/=Status.Ok.U || (leaseEventSubmitted && qkEvent.bits.outputCommitted &&
        qkEvent.bits.writeBytes===logical.writeBytes && qkScalarExact &&
        qkEvent.bits.scalarAccepted===leases(0).lease.expectedOperations &&
        qkEvent.bits.scalarReturned===leases(0).lease.expectedOperations &&
        qkEvent.bits.memoryAccepted===(8.U+logical.m.pad(32)*logical.n.pad(32)*Mux(logical.qkRole===0.U,32.U,16.U))(31,0) &&
        qkEvent.bits.memoryReturned===qkEvent.bits.memoryAccepted && qkEvent.bits.outputAckBytes===logical.writeBytes))
    val ropeEvent=k.io.runtimeRopeDoneFire.get
    val ropeExpected=PartialRopeRuntimeJobV12.fromOwner(retainedPhysical)
    val ropeScalarExact=a.io.status(8).lease.asUInt===leases(0).asUInt &&
      a.io.status(8).counts.returned===leases(0).lease.expectedOperations.pad(33) && a.io.status(8).resourcesDrained
    val ropeTerminalExact=ropeEvent.bits.tag===physical && ropeEvent.bits.accepted.asUInt===ropeExpected.asUInt &&
      ropeEvent.bits.status===g.io.physicalDone.bits.status && ropeEvent.bits.writeBytes===g.io.physicalDone.bits.writeBytes &&
      ropeEvent.bits.cycles===g.io.physicalDone.bits.cycles &&
      (ropeEvent.bits.status=/=Status.Ok.U || (leaseEventSubmitted && ropeEvent.bits.outputCommitted &&
        ropeEvent.bits.writeBytes===logical.writeBytes && ropeScalarExact &&
        ropeEvent.bits.scalarAccepted===leases(0).lease.expectedOperations &&
        ropeEvent.bits.scalarReturned===leases(0).lease.expectedOperations &&
        ropeEvent.bits.memoryAccepted===(logical.m.pad(32)*(2.U+logical.n.pad(32)*16.U))(31,0) &&
        ropeEvent.bits.memoryReturned===ropeEvent.bits.memoryAccepted && ropeEvent.bits.outputAckBytes===logical.writeBytes))
    val kvEvent=k.io.runtimeKvAppendDoneFire.get
    val kvExpected=Bf16KvAppendRuntimeJobV13.fromOwner(retainedPhysical)
    val kvPlaneBytes=logical.m.pad(64)<<10
    val kvTerminalExact=kvEvent.bits.tag===physical && kvEvent.bits.accepted.asUInt===kvExpected.asUInt &&
      kvEvent.bits.status===g.io.physicalDone.bits.status && kvEvent.bits.writeBytes===g.io.physicalDone.bits.writeBytes &&
      kvEvent.bits.cycles===g.io.physicalDone.bits.cycles &&
      (kvEvent.bits.status=/=Status.Ok.U || (kvEvent.bits.proposalValid && kvEvent.bits.drained &&
        !leaseEventSubmitted && kvEvent.bits.cacheBase===logical.dst && kvEvent.bits.capacityTokens===128.U &&
        kvEvent.bits.proposedLength===logical.m && kvEvent.bits.proposedGeneration===1.U &&
        kvEvent.bits.keyAckBytes===kvPlaneBytes && kvEvent.bits.valueAckBytes===kvPlaneBytes &&
        kvEvent.bits.writeBytes===logical.writeBytes &&
        kvEvent.bits.memoryAccepted===(logical.m.pad(32)<<6) &&
        kvEvent.bits.memoryReturned===kvEvent.bits.memoryAccepted))
    val gqaEvent=k.io.runtimeGqaDoneFire.get
    val gqaExpected=Bf16CausalGqaRuntimeJobV14.fromOwner(retainedPhysical)
    val gqaScalarExact=a.io.status(8).lease.asUInt===leases(0).asUInt &&
      a.io.status(8).counts.accepted===leases(0).lease.expectedOperations.pad(33) &&
      a.io.status(8).counts.issued===leases(0).lease.expectedOperations.pad(33) &&
      a.io.status(8).counts.returned===leases(0).lease.expectedOperations.pad(33) && a.io.status(8).resourcesDrained
    val gqaTerminalExact=gqaEvent.bits.tag===physical && gqaEvent.bits.accepted.asUInt===gqaExpected.asUInt &&
      gqaEvent.bits.status===g.io.physicalDone.bits.status && gqaEvent.bits.writeBytes===g.io.physicalDone.bits.writeBytes &&
      gqaEvent.bits.cycles===g.io.physicalDone.bits.cycles &&
      (gqaEvent.bits.status=/=Status.Ok.U || (leaseEventSubmitted && gqaScalarExact &&
        gqaEvent.bits.outputCommitted && gqaEvent.bits.drained && gqaEvent.bits.attentionStatus===0.U &&
        gqaEvent.bits.writeBytes===logical.writeBytes && gqaEvent.bits.outputAckBytes===logical.writeBytes &&
        gqaEvent.bits.scalarAccepted.pad(64)===gqaScalarOperations &&
        gqaEvent.bits.scalarReturned.pad(64)===gqaScalarOperations &&
        gqaEvent.bits.memoryAccepted.pad(64)===gqaMemoryOperations &&
        gqaEvent.bits.memoryReturned===gqaEvent.bits.memoryAccepted &&
        gqaEvent.bits.matrixGroupsAccepted.pad(64)===gqaMatrixGroups &&
        gqaEvent.bits.matrixGroupsReturned===gqaEvent.bits.matrixGroupsAccepted))
    val elementwiseEvent=k.io.runtimeElementwiseDoneFire.get
    val elementwiseExpected=GdnRuntimeElementwiseJobV15.fromOwner(retainedPhysical)
    val outputCountsExact=slots.indices.map{i=>
      val r=a.io.status(slots(i))
      r.lease.asUInt===leases(i).asUInt && r.resourcesDrained &&
        r.counts.accepted===leases(i).lease.expectedOperations.pad(33) &&
        r.counts.issued===leases(i).lease.expectedOperations.pad(33) &&
        r.counts.returned===leases(i).lease.expectedOperations.pad(33)
    }.reduce(_&&_)
    val elementwiseTerminalExact=elementwiseEvent.bits.tag===physical &&
      elementwiseEvent.bits.accepted.asUInt===elementwiseExpected.asUInt &&
      elementwiseEvent.bits.status===g.io.physicalDone.bits.status &&
      elementwiseEvent.bits.writeBytes===g.io.physicalDone.bits.writeBytes &&
      elementwiseEvent.bits.cycles===g.io.physicalDone.bits.cycles &&
      (elementwiseEvent.bits.status=/=Status.Ok.U || (leaseEventSubmitted && outputCountsExact &&
        elementwiseEvent.bits.outputCommitted && elementwiseEvent.bits.resourcesDrained &&
        elementwiseEvent.bits.writeBytes===logical.writeBytes && elementwiseEvent.bits.outputAckBytes===logical.writeBytes &&
        elementwiseEvent.bits.scalarAccepted.pad(64)===elementwiseScalarOperations &&
        elementwiseEvent.bits.scalarReturned===elementwiseEvent.bits.scalarAccepted &&
        elementwiseEvent.bits.formatAccepted.pad(64)===elementwiseFormatOperations &&
        elementwiseEvent.bits.formatReturned===elementwiseEvent.bits.formatAccepted &&
        elementwiseEvent.bits.memoryAccepted.pad(64)===elementwiseMemoryOperations &&
        elementwiseEvent.bits.memoryReturned===elementwiseEvent.bits.memoryAccepted))
    val normEvent=k.io.runtimeRmsDoneFire.get
    val normExpected=GdnRuntimeRmsNormJobV3.fromOwner(retainedPhysical)
    val normTerminalExact=normEvent.bits.tag===physical && normEvent.bits.accepted.asUInt===normExpected.asUInt &&
      normEvent.bits.status===g.io.physicalDone.bits.status && normEvent.bits.writeBytes===g.io.physicalDone.bits.writeBytes &&
      normEvent.bits.cycles===g.io.physicalDone.bits.cycles &&
      (normEvent.bits.status=/=Status.Ok.U || (leaseEventSubmitted && outputCountsExact &&
        normEvent.bits.outputCommitted && normEvent.bits.resourcesDrained &&
        normEvent.bits.outputAckBytes===logical.writeBytes && normEvent.bits.writeBytes===logical.writeBytes &&
        normEvent.bits.scalarAccepted.pad(64)===normScalarOperations &&
        normEvent.bits.scalarReturned===normEvent.bits.scalarAccepted &&
        normEvent.bits.formatAccepted.pad(64)===normFormatOperations &&
        normEvent.bits.formatReturned===normEvent.bits.formatAccepted &&
        normEvent.bits.memoryAccepted.pad(64)===normMemoryOperations &&
        normEvent.bits.memoryReturned===normEvent.bits.memoryAccepted))
    val terminalExact=g.io.physicalDone.bits.tag===physical && !contextChanged &&
      (!normShape || normTerminalExact) && (!gatedShape || gatedTerminalExact) && (!qkShape || qkTerminalExact) && (!ropeShape || ropeTerminalExact) && (!kvShape || kvTerminalExact) && (!gqaShape || gqaTerminalExact) && (!elementwiseShape || elementwiseTerminalExact)
    when(normEvent.valid && (!owned || !normShape || !g.io.physicalDone.fire || !normTerminalExact)){poison:=true.B}
    when(elementwiseEvent.valid && (!owned || !elementwiseShape || !g.io.physicalDone.fire || !elementwiseTerminalExact)){poison:=true.B}
    when(gqaEvent.valid && (!owned || !gqaShape || !g.io.physicalDone.fire || !gqaTerminalExact)){poison:=true.B}
    when(kvEvent.valid && (!owned || !kvShape || !g.io.physicalDone.fire || !kvTerminalExact)){poison:=true.B}
    when(ropeEvent.valid && (!owned || !ropeShape || !g.io.physicalDone.fire || !ropeTerminalExact)){poison:=true.B}
    when(qkEvent.valid && (!owned || !qkShape || !g.io.physicalDone.fire || !qkTerminalExact)){poison:=true.B}
    when(gatedEvent.valid && (!owned || !gatedShape || !g.io.physicalDone.fire || !gatedTerminalExact)){poison:=true.B}
    when(owned && g.io.physicalDone.valid && !terminalExact){poison:=true.B}
    when(owned && g.io.physicalDone.fire){
      when(!terminalExact || (normShape && !normEvent.valid) || (gatedShape && !gatedEvent.valid) || (qkShape && !qkEvent.valid) || (ropeShape && !ropeEvent.valid) || (kvShape && !kvEvent.valid) || (gqaShape && !gqaEvent.valid) || (elementwiseShape && !elementwiseEvent.valid)){poison:=true.B}
      .otherwise{
        when(prepShape && g.io.physicalDone.bits.status===Status.Ok.U && !leaseEventSubmitted){poison:=true.B}
        owned:=false.B;awaitPrepare:=false.B;retirePending:=leaseEventSubmitted;leaseEventSubmitted:=false.B
        retireStatus:=g.io.physicalDone.bits.status
      }
    }
    // Exact actual terminal + full matching specialized accepted payload and
    // real shared-service counters fence each next stage. These are private
    // staging receipts only; final residual/FFN/dual-root fence stays sealed.
    val tailCaptureClean= !poison && !currentIndependentFault && !authority.currentFault && !g.io.localFault
    def captureTail(r:HostRuntimeOutputStagedReceiptV15):Unit={
      r.host:=host;r.transactionId:=transaction;r.job:=retainedPhysical;r.result:=g.io.physicalDone.bits
    }
    val tailPhysicalSuccess=owned && terminalExact && g.io.physicalDone.fire &&
      g.io.physicalDone.bits.status===Status.Ok.U && g.io.physicalDone.bits.writeBytes===logical.writeBytes && tailCaptureClean
    when(tailPhysicalSuccess && normShape && !normPostPhase && logical.qkRole===0.U &&
      normEvent.valid && normTerminalExact){
      captureTail(hiddenReceipt);hiddenValid:=true.B
    }
    when(tailPhysicalSuccess && gatedShape && gatedEvent.valid && gatedTerminalExact && outputCountsExact){
      captureTail(mixedReceipt);mixedValid:=true.B
    }
    when(tailPhysicalSuccess && gqaShape && gqaEvent.valid && gqaTerminalExact){
      captureTail(gqaOutputReceipt);gqaOutputValid:=true.B
      gqaGateJob:=normalizedJobs(0);gqaGateResult:=normalizedResults(0)
    }
    when(tailPhysicalSuccess && elementwiseSigmoid && elementwiseEvent.valid && elementwiseTerminalExact){
      captureTail(mixedReceipt);mixedValid:=true.B
    }
    when(tailPhysicalSuccess && elementwiseShape && !elementwiseSigmoid && !isFfn(logical) &&
      elementwiseEvent.valid && elementwiseTerminalExact){
      captureTail(residualReceipt);residualValid:=true.B
    }
    when(tailPhysicalSuccess && elementwiseShape && isFfn(logical) && elementwiseEvent.valid && elementwiseTerminalExact){
      val r=Wire(new HostRuntimeFfnStagedReceiptV17)
      r.host:=host;r.transactionId:=transaction;r.job:=retainedPhysical;r.logicalJob:=logical;r.result:=g.io.physicalDone.bits
      ffnReceipt:=r;ffnReceiptValid:=true.B;ffnStages(logical.runtimeFfnPhase-1.U):=r;ffnValid(logical.runtimeFfnPhase-1.U):=true.B
    }
    when(tailPhysicalSuccess && postnormShape && normEvent.valid && normTerminalExact){
      postnormReceipt.host:=host;postnormReceipt.transactionId:=transaction
      postnormReceipt.job:=retainedPhysical;postnormReceipt.logicalJob:=logical
      postnormReceipt.result:=normEvent.bits;postnormReceipt.residual:=postnormInput;postnormValid:=true.B
    }
    // Replacement/fault revokes only eligibility. Existing held physical
    // offers and returned debt are retained by their original owners.
    when(logicalStart && g.io.job.bits.kind===QwenOwnerKind.GdnRmsNorm.U && g.io.job.bits.qkRole===0.U){
      hiddenValid:=false.B;mixedValid:=false.B;denseOValid:=false.B;gqaOutputValid:=false.B
      residualValid:=false.B;postnormValid:=false.B
      ffnValid:=VecInit(Seq.fill(5)(false.B));ffnIssued:=VecInit(Seq.fill(5)(false.B));ffnReceiptValid:=false.B
    }
    when((elementLogical && !isFfn(g.io.job.bits)) || denseOLogicalStart || gatedLogical || gqaLogical || projectionStart || qkLogical || ropeLogical || kvLogical){
      residualValid:=false.B;postnormValid:=false.B
    }
    when(!tailCaptureClean || (residualValid && !tailCurrent(residualReceipt))){residualValid:=false.B}
    when(!tailCaptureClean || (postnormValid && !postnormCurrent)){postnormValid:=false.B}
    when(!tailCaptureClean || (ffnReceiptValid && !ffnCurrent(ffnReceipt))){ffnReceiptValid:=false.B}
    for(i<-0 until 5){when(!tailCaptureClean || (ffnValid(i) && !ffnCurrent(ffnStages(i)))){ffnValid(i):=false.B}}
    when(gatedLogical || (elementLogical && g.io.job.bits.gdnElementwiseOp===GdnElementwiseOp.SigmoidMul.U)){mixedValid:=false.B;denseOValid:=false.B}
    when(gqaLogical || projectionStart || qkLogical || ropeLogical || kvLogical){
      gqaOutputValid:=false.B;mixedValid:=false.B;denseOValid:=false.B
    }
    when(!tailCaptureClean || (hiddenValid && !tailCurrent(hiddenReceipt))){hiddenValid:=false.B}
    when(!tailCaptureClean || (mixedValid && !tailCurrent(mixedReceipt))){mixedValid:=false.B}
    when(!tailCaptureClean || (denseOValid && !tailCurrent(denseOReceipt))){denseOValid:=false.B}
    when(!tailCaptureClean || (gqaOutputValid && !tailCurrent(gqaOutputReceipt))){gqaOutputValid:=false.B}
    // Capture only the exact actual QKNorm fire, with genuine scalar returns
    // and norm+gate memory ACKs already checked above. Never Host success.
    val normalizedEventSuccess=qkEvent.valid && owned && qkShape && terminalExact &&
      g.io.physicalDone.fire && qkTerminalExact && qkEvent.bits.status===Status.Ok.U
    when(normalizedEventSuccess && !poison && !currentIndependentFault && !authority.currentFault && !g.io.localFault){
      val role=logical.qkRole(0)
      normalizedJobs(role):=retainedPhysical;normalizedResults(role):=qkEvent.bits;normalizedValid(role):=true.B
    }
    when(ropeEvent.valid && owned && ropeShape && terminalExact && g.io.physicalDone.fire &&
      ropeTerminalExact && ropeEvent.bits.status===Status.Ok.U && logical.qkRole===0.U &&
      !poison && !currentIndependentFault && !authority.currentFault && !g.io.localFault){
      ropeQCommitted:=true.B;rotatedQValid:=true.B;rotatedQJob:=retainedPhysical;rotatedQResult:=ropeEvent.bits
      rotatedQHost:=host;rotatedQTransaction:=transaction
    }
    when(ropeEvent.valid && owned && ropeShape && terminalExact && g.io.physicalDone.fire &&
      ropeTerminalExact && ropeEvent.bits.status===Status.Ok.U && logical.qkRole===1.U &&
      !poison && !currentIndependentFault && !authority.currentFault && !g.io.localFault){
      rotatedKValid:=true.B;rotatedKJob:=retainedPhysical;rotatedKResult:=ropeEvent.bits
      rotatedKHost:=host;rotatedKTransaction:=transaction
    }
    when(kvEvent.valid && owned && kvShape && terminalExact && g.io.physicalDone.fire &&
      kvTerminalExact && kvEvent.bits.status===Status.Ok.U &&
      !poison && !currentIndependentFault && !authority.currentFault && !g.io.localFault){
      kvReceipt.host:=host;kvReceipt.transactionId:=transaction
      kvReceipt.job:=retainedPhysical;kvReceipt.result:=kvEvent.bits;kvReceiptValid:=true.B
    }
    when(kvReceiptValid && !kvReceiptCurrent){kvReceiptValid:=false.B}
    // Observe the actual RawPrep child terminal, not the generic owner result
    // with its accepted payload discarded. Same-cycle physicalDone.fire binds
    // it to the retained real Guard owner P and accepted host transaction.
    // Fault capture is registered ONLY: no event -> localFault -> ready loop.
    val prepEvent=k.io.runtimePrepDoneFire.get
    val prepEventExact=owned && prepShape && !contextChanged &&
      g.io.physicalDone.fire && terminalExact &&
      prepEvent.bits.tag===physical && prepEvent.bits.accepted.asUInt===expectedPrep.asUInt &&
      g.io.physicalDone.bits.tag===prepEvent.bits.tag &&
      g.io.physicalDone.bits.status===prepEvent.bits.status &&
      g.io.physicalDone.bits.writeBytes===prepEvent.bits.writeBytes &&
      g.io.physicalDone.bits.cycles===prepEvent.bits.cycles
    val prepEventSuccess=prepEventExact && leaseEventSubmitted && !awaitPrepare &&
      prepEvent.bits.status===Status.Ok.U && prepEvent.bits.outputCommitted &&
      prepEvent.bits.writeBytes===logical.writeBytes &&
      prepEvent.bits.writeBytes===(expectedPrep.tokens.pad(64)*expectedPrep.layout.rowBytes.pad(64))(63,0)
    val receiptCurrent=authority.accepted && authority.transaction===prepReceipt.producer.transactionId &&
      authority.launch.epoch===prepReceipt.producer.hostEpoch && authority.launch.asUInt===host.asUInt
    val receiptFault=poison || currentIndependentFault || authority.currentFault || g.io.localFault || a.io.resetRequired
    when(prepEvent.valid){
      when(!prepEventExact || (prepEvent.bits.status===Status.Ok.U && !prepEventSuccess) || prepReceiptValid){
        poison:=true.B;prepReceiptValid:=false.B
      }.elsewhen(prepEventSuccess && !receiptFault){
        prepReceipt.producer.transactionId:=transaction
        prepReceipt.producer.hostEpoch:=host.epoch
        prepReceipt.producer.ownerSequence:=physical
        prepReceipt.result:=prepEvent.bits
        prepReceiptValid:=true.B
      }
    }
    // A fault or changed lifetime can never leave a stale eligible snapshot.
    // This is metadata invalidation, not cancellation of a held service offer.
    when(receiptFault || (prepReceiptValid && !receiptCurrent)){prepReceiptValid:=false.B}
    // One registered stage prevents actual-fire rejection feedback cycles.
    // Both events preserve their original order; status is from its real fire.
    for(i<-0 until 2){
      if(i==0){
        out.scalarAcquire.valid:=acquirePending;out.scalarAcquire.bits:=leases(i)
        out.scalarRetire.valid:=retirePending;out.scalarRetire.bits.lease:=leases(i);out.scalarRetire.bits.status:=retireStatus
      }else{
        a.io.acquire(slots(i)).valid:=acquirePending && !qkShape && !ropeShape && !gqaShape;a.io.acquire(slots(i)).bits:=leases(i)
        a.io.retire(slots(i)).valid:=retirePending && !qkShape && !ropeShape && !gqaShape;a.io.retire(slots(i)).bits.lease:=leases(i)
        a.io.retire(slots(i)).bits.status:=retireStatus
      }
    }
    // A leaf-local offer is not yet an exposed shared-service obligation.
    // Two bits preserve only previously published requests through late fault;
    // CURRENT independent fault blocks first publication without cancelling
    // a held request. Adapter's own current fault still blocks fresh captures
    // internally; feeding it back into these valid gates would form a cycle.
    val firstFault=currentIndependentFault || poison || contextChanged || physicalOfferBad || prepareBad || g.io.localFault
    val scalar=k.io.runtimeRms.get.scalar
    val scalarPublish=HeldDecoupledOffer(scalar.request.valid,scalarPort.request.ready,firstFault)
    scalarPort.request.valid:=scalarPublish.valid;scalarPort.request.bits:=scalar.request.bits
    scalar.request.ready:=scalarPort.request.ready && scalarPublish.valid
    scalar.result<>scalarPort.result
    val format=k.io.runtimeRms.get.formatRequest
    val formatPublish=HeldDecoupledOffer(format.valid,a.io.formatRequest(3).ready,firstFault)
    a.io.formatRequest(3).valid:=formatPublish.valid;a.io.formatRequest(3).bits:=format.bits
    format.ready:=a.io.formatRequest(3).ready && formatPublish.valid
    k.io.runtimeRms.get.formatResult<>a.io.formatResult(3)
    out.owned:=owned;out.host:=host;out.transactionId:=transaction
    out.job:=logical;out.job.tag:=physical
    // This receipt proves staged numerical ACK, not a resource grant. Commands
    // additionally require their true completion.fire before FFN-input publish;
    // the existing allocator still waits for real slot8/9 retirement/drain.
    out.ffnReceipt.bits:=ffnReceipt
    out.ffnReceipt.valid:=ffnReceiptValid && ffnCurrent(ffnReceipt) && !receiptFault
    out.postnormReceipt.bits:=postnormReceipt
    out.postnormReceipt.valid:=postnormValid && postnormCurrent && !receiptFault
    out.kvReceipt.bits:=kvReceipt
    out.kvReceipt.valid:=kvReceiptValid && kvReceiptCurrent && !receiptFault && !kvLogical && !busy &&
      k.io.runtimeRms.get.resourcesDrained
    out.prepReceipt.bits:=prepReceipt
    // Producer success does not retire slot8/9 leases. Wait for their ACTUAL
    // existing retirement/drain before a later owner may borrow the resources.
    out.prepReceipt.valid:=prepReceiptValid && receiptCurrent && !receiptFault && !prepReplacement && !busy &&
      slots.map(i=>a.io.status(i).resourcesDrained).reduce(_&&_) && k.io.runtimeRms.get.resourcesDrained
    out.localFault:=poison || contextChanged || physicalOfferBad || prepareBad || outputLogicalOfferBad || denseOPhysicalBad || ffnDensePhysicalBad
    out.eventsPending:=acquirePending || retirePending || awaitPrepare || prep.valid || scalarPublish.held || formatPublish.held || denseOWaiting || denseOBusy || ffnDenseWaiting || ffnDenseBusy
    out.resourcesDrained:= !busy && !denseOWaiting && !denseOBusy && !ffnDenseWaiting && !ffnDenseBusy && !scalarPublish.held && !formatPublish.held && slots.map(i=>a.io.status(i).resourcesDrained).reduce(_&&_) &&
      k.io.runtimeRms.get.resourcesDrained
    out
  }
}

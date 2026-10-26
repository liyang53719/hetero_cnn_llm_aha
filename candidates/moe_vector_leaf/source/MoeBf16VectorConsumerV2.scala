// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Complete nine-contribution MoE final-hidden32 tile, one shared16-lane bank.
  * This ownerless consumer creates no ALU, Scalar, Matrix or BF16 rounder.
  * The single common V2 bank materializes BF16 after EACH Mul and EACH Add,
  * returning each materialized value expanded in bits31:16 with low16 zero.
  * Runtime profiles use the same graph. Contribution order is expert-ID
  * ascending with exactly one shared contribution last, proven by the actual
  * producer/owner wrapper (not by a host-supplied drained Boolean).
  *
  * External owner/arbiter must bind a lease and every operation to the full
  * V2 txn/resource/ownerSequence/stage/token/tile/serial tag. This raw local
  * port has one pending operation and is NOT that complete shared-fabric
  * integration. It never cancels an offered request or an accepted operation.
  * Missing responses/contributions require parent watchdog plus isolation;
  * no bare error fabricates drain or releases another owner's credit.
  */
class MoeBf16VectorConsumerV2 extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new MoeBf16TileJob))
    val contribution=Flipped(Decoupled(new MoeBf16TileContribution))
    val result=Decoupled(new MoeBf16TileResult)
    val sourceFailure=Flipped(Decoupled(new MoeBf16SourceFailure))
    val rejectedFailure=Output(Bool())
    val vectorRequest=Decoupled(new UnifiedVectorRequestV2)
    val vectorResult=Flipped(Decoupled(new UnifiedVectorResultV2))
    val busy=Output(Bool());val staleContributionRejected=Output(Bool())
  })
  val sIdle::sLoad::sMulIssue::sMulWait::sAddIssue::sAddWait::sDrain::sDone::Nil=Enum(8)
  val state=RegInit(sIdle);val identity=Reg(new MoeBf16TileIdentity)
  val received=RegInit(0.U(4.W));val seen=RegInit(0.U(9.W))
  val half=RegInit(false.B);val data=Reg(UInt(512.W));val weight=Reg(UInt(16.W))
  val product=Reg(Vec(16,UInt(16.W)));val accum=Reg(Vec(32,UInt(16.W)))
  val status=RegInit(Status.Ok.U(8.W))
  val words=data.asTypeOf(Vec(32,UInt(16.W)))
  io.job.ready:=state===sIdle;io.busy:=state=/=sIdle
  io.contribution.ready:=state===sLoad || state===sDrain
  val sameIdentity=io.contribution.bits.identity.asUInt===identity.asUInt
  val validUniqueTag=io.contribution.bits.routeTag<9.U && !seen(io.contribution.bits.routeTag)
  val accepted=io.contribution.fire && sameIdentity && validUniqueTag
  io.staleContributionRejected:=io.contribution.fire && !sameIdentity
  val validFailure=io.sourceFailure.bits.identity.asUInt===identity.asUInt &&
    io.sourceFailure.bits.drained && io.sourceFailure.bits.status>=Status.Malformed.U &&
    io.sourceFailure.bits.status<=Status.Permission.U
  val safeFailure=state===sLoad || state===sDrain
  io.sourceFailure.ready:=safeFailure && (!validFailure || !io.contribution.valid)
  io.rejectedFailure:=io.sourceFailure.fire && !validFailure
  io.result.valid:=state===sDone;io.result.bits.identity:=identity
  io.result.bits.data:=Mux(status===Status.Ok.U,accum.asUInt,0.U);io.result.bits.status:=status

  val multiplying=state===sMulIssue
  io.vectorRequest.valid:=state===sMulIssue || state===sAddIssue
  io.vectorRequest.bits.policy:=Mux(multiplying,1.U,2.U) // CommonV2 BF16 MulRNE / AddRNE, never legacy0.
  io.vectorRequest.bits.multiply:=multiplying
  for(i<-0 until 16){
    val lane=Cat(half,i.U(4.W))
    io.vectorRequest.bits.a(i):=Cat(Mux(multiplying,words(lane),accum(lane)),0.U(16.W))
    io.vectorRequest.bits.b(i):=Cat(Mux(multiplying,weight,product(i)),0.U(16.W))
  }
  io.vectorResult.ready:=state===sMulWait || state===sAddWait
  // No second RNE conversion, no hidden FP32 accumulator, no error masking.
  // Bank policy independently retains raw flags and validates its numeric domain.
  val canonicalResult=io.vectorResult.bits.value.map(x=>TensorMath.finite(x) && x(15,0)===0.U).reduce(_&&_)
  val policyMatches=io.vectorResult.bits.policy===Mux(state===sMulWait,1.U,2.U)
  val flagsBad=io.vectorResult.bits.flags.map(f=>Mux(state===sMulWait,f(4,2).orR,f(4,1).orR)).reduce(_||_)
  val badResult=io.vectorResult.bits.error || !canonicalResult || flagsBad || !policyMatches
  def failAfterResponse():Unit={
    status:=Mux(!policyMatches,Status.Protocol.U,Status.Numerical.U)
    state:=Mux(received===9.U,sDone,sDrain)
  }
  when(io.contribution.fire && sameIdentity && !validUniqueTag){
    when(status===Status.Ok.U){status:=Status.Protocol.U};state:=sDrain
  }
  switch(state){
    is(sIdle){when(io.job.fire){
      identity:=io.job.bits.identity;received:=0.U;seen:=0.U;half:=false.B;status:=Status.Ok.U
      for(i<-0 until 32){accum(i):=0.U}
      // Complete MoE is always8 routed+1shared; no arbitrary count/host shortcut.
      when(io.job.bits.contributionCount=/=9.U){status:=Status.Malformed.U;state:=sDone}.otherwise{state:=sLoad}
    }}
    is(sLoad){when(accepted){
      val c=io.contribution.bits
      val markersOk=c.first===(received===0.U) && c.last===(received===8.U)
      val finiteData=(0 until 32).map(i=>c.data(16*i+14,16*i+7)=/=255.U).reduce(_&&_)
      val canonical=c.weight(31,16)===0.U && c.weight(14,7)=/=255.U && finiteData
      received:=received+1.U;seen:=seen | (1.U(9.W)<<c.routeTag)
      when(!markersOk || !canonical){
        status:=Mux(!canonical,Status.Numerical.U,Status.Protocol.U)
        state:=Mux(received===8.U,sDone,sDrain)
      }.otherwise{data:=c.data;weight:=c.weight(15,0);half:=false.B;state:=sMulIssue}
    }}
    is(sMulIssue){when(io.vectorRequest.fire){state:=sMulWait}}
    is(sMulWait){when(io.vectorResult.fire){
      when(badResult){failAfterResponse()}.otherwise{
        for(i<-0 until 16){product(i):=io.vectorResult.bits.value(i)(31,16)}
        state:=sAddIssue
      }
    }}
    is(sAddIssue){when(io.vectorRequest.fire){state:=sAddWait}}
    is(sAddWait){when(io.vectorResult.fire){
      when(badResult){failAfterResponse()}.otherwise{
        for(i<-0 until 16){accum(Cat(half,i.U(4.W))):=io.vectorResult.bits.value(i)(31,16)}
        when(!half){half:=true.B;state:=sMulIssue}.otherwise{state:=Mux(received===9.U,sDone,sLoad)}
      }
    }}
    is(sDrain){when(accepted){
      received:=received+1.U;seen:=seen | (1.U(9.W)<<io.contribution.bits.routeTag)
      when(received===8.U){state:=sDone}
    }}
    is(sDone){when(io.result.fire){state:=sIdle}}
  }
  when(io.sourceFailure.fire && validFailure){
    when(status===Status.Ok.U){status:=io.sourceFailure.bits.status};state:=sDone
  }
}

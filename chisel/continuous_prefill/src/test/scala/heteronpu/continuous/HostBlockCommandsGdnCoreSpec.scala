// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** CONTROL_ONLY. Stand-in owner completions verify public-command admission,
  * producer provenance and atomic state publication, not numerical arithmetic,
  * payload DMA or physical-resource correctness. Those require the real kernel.
  */
class GdnCoreFrontendControlHarness(enabled:Boolean=true) extends HostBlockCommands(
  QwenBlockShape.qwen35Gdn(),eventSlots=32,maxCommands=21,bf16Gdn=true,bf16GdnCore=enabled) {
  val committedValid=IO(Output(Bool()));committedValid:=stateValid
  val committedGeneration=IO(Output(UInt(32.W)));committedGeneration:=currentGeneration
  val committedHistory=IO(Output(UInt(64.W)));committedHistory:=currentHistoryAddress
  val committedState=IO(Output(UInt(64.W)));committedState:=currentStateAddress
}
class HostBlockCommandsGdnCoreSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val nil=BigInt(0xffffff);val cb=BigInt(0x1000);val db=BigInt(0x2000)
  val hidden=BigInt(0x10000);val convW=BigInt(0x20000);val initialHistory=BigInt(0x40000)
  val aLog=BigInt(0x50000);val dtBias=BigInt(0x50040);val gamma=BigInt(0x50100);val initialState=BigInt(0x80000)
  val qkvW=BigInt(0x300000);val zW=BigInt(0x1000000);val abW=BigInt(0x1500000)
  val rw=BigInt(0x4000000);val rwEnd=BigInt(0x8000000)
  val qkv=rw;val z=rw+0x4000;val ab=rw+0x5000;val conv=rw+0x8000;val prep=rw+0x10000
  val core=rw+0x18000;val finalD=rw+0x1a000
  val h0=rw+0x100000;val h1=rw+0x110000;val s0=rw+0x200000;val s1=rw+0x400000
  case class T(address:BigInt,m:Int,n:Int,dtype:Int=5)
  case class E(kind:Int,a:BigInt,b:BigInt,dst:BigInt,n:Int,k:Int,bytes:BigInt,c:BigInt=0,hout:BigInt=0,
               sout:BigInt=0,alog:BigInt=0,dt:BigInt=0,cold:Boolean=false,generation:BigInt=0,mode:Boolean=false)
  case class P(commands:Vector[BigInt],records:Vector[BigInt],expected:Vector[E],generation:BigInt,hout:BigInt,sout:BigInt)
  def rec(kind:Int,next:BigInt,payload:BigInt):BigInt=BigInt(kind)|(next<<32)|(payload<<56)
  def field(word:BigInt,lo:Int,width:Int,value:BigInt):BigInt=(word&~(((BigInt(1)<<width)-1)<<lo))|(value<<lo)
  def prefix(t:T,start:Int,tail:BigInt):Vector[BigInt]={
    val base=(t.address&((BigInt(1)<<48)-1))|(BigInt(t.dtype)<<52)|(BigInt(2)<<60)|((t.address>>48)<<64)
    val shape=BigInt(t.m)|(BigInt(t.n)<<18)|(BigInt(1)<<36)|(BigInt(1)<<54)
    Vector(rec(1,start+1,base),rec(2,start+2,shape),rec(3,tail,BigInt(t.n)|(BigInt(1)<<24)|(BigInt(1)<<48)))
  }
  def program(generation:BigInt=0,cold:Boolean=true,hin:BigInt=initialHistory,hout:BigInt=h0,
              sin:BigInt=initialState,sout:BigInt=s0):P={
    var records=Vector.empty[BigInt];var commands=Vector.empty[BigInt];var expected=Vector.empty[E]
    def gp(op:Int):BigInt=BigInt(2)|(BigInt(op)<<8)|(BigInt(if(cold)1 else 0)<<24)|
      (BigInt(if(cold)0 else 1)<<25)|(generation<<32)
    def add(op:Int,a:T,b:T,d:T,extras:Vector[T]=Vector.empty,e:Option[E]=None):Unit={
      val start=records.size;val pc=commands.size
      val matrix=op==2;val tail:BigInt=if(matrix || extras.nonEmpty)BigInt(start+11) else nil
      val policies=if(matrix)Vector(rec(0x10,start+10,BigInt(1)|(BigInt(d.n)<<16)|(BigInt(1024)<<32)),
        rec(0x12,start+11,BigInt("004000040020ffffff",16)),rec(0x21,nil,gp(op)))
      else {
        val inType=if(op==4)7 else 5;val outType=if(op==3)7 else 5
        val sfu=BigInt(0x30)|(BigInt(2)<<16)|(BigInt(1)<<24)|(BigInt(inType)<<32)|
          (BigInt(outType)<<36)|(BigInt(16)<<40)|(BigInt(1)<<48)
        Vector(rec(0x20,start+10,sfu),rec(0x21,tail,gp(op)))++
          (if(extras.nonEmpty)Vector(rec(if(op==1)0x22 else 0x23,nil,BigInt(start+12)|((if(extras.size==2)BigInt(start+15) else nil)<<24))) else Vector.empty)
      }
      records=records++prefix(a,start,start+9)++prefix(b,start+3,nil)++prefix(d,start+6,nil)++policies++
        extras.zipWithIndex.flatMap{case(t,i)=>prefix(t,start+12+3*i,nil)}
      commands=commands:+(BigInt(if(matrix)0x220 else 0x330)|(BigInt(pc)<<24)|(BigInt(pc+1)<<40)|
        (BigInt(start)<<56)|(BigInt(start+3)<<80)|(BigInt(start+6)<<104))
      e.foreach(x=>expected=expected:+x)
    }
    for((n,w,d)<-Seq((6144,qkvW,qkv),(2048,zW,z),(32,abW,ab)))
      add(2,T(hidden,1,1024),T(w,1024,n),T(d,1,n),e=Some(E(QwenOwnerKind.Dense,hidden,w,d,n,1024,n*2)))
    add(1,T(qkv,1,6144),T(convW,6144,4),T(conv,1,6144),Vector(T(hin,6144,4),T(hout,6144,4)),
      Some(E(QwenOwnerKind.GdnConv,qkv,convW,conv,6144,4,6144*2+6144*4*2,c=hin,hout=hout,cold=cold,generation=generation)))
    add(3,T(conv,1,6144),T(ab,1,32),T(prep,1,6400,7),Vector(T(aLog,1,16,7),T(dtBias,1,16)),
      Some(E(QwenOwnerKind.GdnInputPrep,conv,ab,prep,16,128,6400*4,alog=aLog,dt=dtBias,mode= !cold)))
    add(4,T(prep,1,6400,7),T(sin,2048,128,7),T(core,1,2048),Vector(T(sout,2048,128,7)),
      Some(E(QwenOwnerKind.GdnRecurrent,prep,sin,core,16,128,2048*2+2048*128*4,sout=sout,cold=cold,generation=generation)))
    add(5,T(core,1,2048),T(z,1,2048),T(finalD,1,2048),Vector(T(gamma,1,128,7)),
      Some(E(QwenOwnerKind.GdnGatedNorm,core,z,finalD,16,128,2048*2,c=gamma)))
    add(6,T(hout,6144,4),T(sout,2048,128,7),T(finalD,1,2048))
    P(commands,records,expected,generation,hout,sout)
  }
  def edit(p:P,i:Int,lo:Int,width:Int,v:BigInt):P=p.copy(records=p.records.updated(i,field(p.records(i),lo,width,v)))
  def setup(d:GdnCoreFrontendControlHarness,p:P,reset:Boolean):Unit={
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.completion.ready.poke(false.B)
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B);d.io.job.ready.poke(false.B);d.io.done.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
    d.io.done.bits.tag.poke(0.U);d.io.done.bits.status.poke(0.U);d.io.done.bits.writeBytes.poke(0.U)
    d.io.done.bits.cycles.poke(0.U);d.io.done.bits.usefulMacs.poke(0.U);d.io.done.bits.executedMacs.poke(0.U)
    if(reset){d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B)}
    val l=d.io.launch.bits;l.commandBase.poke(cb.U);l.commandLimit.poke((cb+0x1000).U);l.commands.poke(p.commands.size.U)
    l.descriptorBase.poke(db.U);l.descriptorLimit.poke(0x10000.U);l.descriptors.poke(p.records.size.U);l.epoch.poke(9.U)
    for((r,i)<-Seq((cb,BigInt(0x10000),true,false),(hidden,BigInt(0x3000000),true,false),
      (rw,rwEnd,true,true),(BigInt(0),BigInt(0),false,false)).zipWithIndex){
      l.regions(i).base.poke(r._1.U);l.regions(i).limit.poke(r._2.U);l.regions(i).read.poke(r._3.B);l.regions(i).write.poke(r._4.B)
    }
  }
  def run(d:GdnCoreFrontendControlHarness,p:P,reset:Boolean=true,faultJob:Int= -1,fault:Int=0,
          badMemoryTag:Boolean=false,writeOnly:Boolean=false,readonlyLimit:BigInt=BigInt(0x3000000),writableBase:BigInt=rw):(Int,Int,Int)={
    setup(d,p,reset)
    var generation=d.committedGeneration.peek().litValue;var history=d.committedHistory.peek().litValue
    var state=d.committedState.peek().litValue;var valid=d.committedValid.peek().litToBoolean
    d.io.launch.bits.regions(1).limit.poke(readonlyLimit.U)
    d.io.launch.bits.regions(2).base.poke(writableBase.U)
    if(writeOnly)d.io.launch.bits.regions(2).read.poke(false.B)
    def unchanged():Unit={d.committedGeneration.expect(generation.U);d.committedHistory.expect(history.U)
      d.committedState.expect(state.U);d.committedValid.expect(valid.B)}
    d.io.launch.ready.expect(true.B);d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
    d.io.launch.bits.epoch.poke(99.U);d.io.launch.bits.regions(2).write.poke(false.B)
    var jobs=0;var completed=0;var ticks=0;var written=BigInt(0)
    while(!d.io.result.valid.peek().litToBoolean && ticks<15000){
      unchanged()
      if(d.io.memory.valid.peek().litToBoolean){
        val addr=d.io.memory.bits.address.peek().litValue;val tag=d.io.memory.bits.tag.peek().litValue
        d.io.memory.bits.write.expect(false.B);d.clock.step(2);d.io.memory.bits.address.expect(addr.U);d.io.memory.bits.tag.expect(tag.U)
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        val table=if(addr<db)p.commands else p.records;val offset=((addr-(if(addr<db)cb else db))/16).toInt
        val data=(0 until 4).map(i=>table.lift(offset+i).getOrElse(BigInt(0))<<(128*i)).reduce(_|_)
        d.io.response.bits.data.poke(data.U);d.io.response.bits.tag.poke((if(badMemoryTag)tag^1 else tag).U)
        d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B);d.clock.step();d.io.response.valid.poke(false.B)
      }else if(d.io.job.valid.peek().litToBoolean){
        assert(jobs<p.expected.size,"Fence must never issue an owner job")
        val e=p.expected(jobs);val tag=(BigInt(9)<<16)|d.io.pc.peek().litValue
        d.io.job.bits.kind.expect(e.kind.U);d.io.job.bits.a.expect(e.a.U);d.io.job.bits.b.expect(e.b.U);d.io.job.bits.dst.expect(e.dst.U)
        d.io.job.bits.m.expect(1.U);d.io.job.bits.n.expect(e.n.U);d.io.job.bits.k.expect(e.k.U);d.io.job.bits.c.expect(e.c.U)
        d.io.job.bits.historyOut.expect(e.hout.U);d.io.job.bits.gdnStateOut.expect(e.sout.U)
        d.io.job.bits.gdnALog.expect(e.alog.U);d.io.job.bits.gdnDtBias.expect(e.dt.U);d.io.job.bits.gdnRecurrentMode.expect(e.mode.B)
        d.io.job.bits.expectedGeneration.expect(e.generation.U)
        d.io.job.bits.currentGeneration.expect((if(e.kind==QwenOwnerKind.GdnConv||e.kind==QwenOwnerKind.GdnRecurrent)generation else BigInt(0)).U)
        d.io.job.bits.cold.expect(e.cold.B);d.io.job.bits.tag.expect(tag.U);d.io.job.bits.writeBytes.expect(e.bytes.U)
        d.io.job.bits.weightBf16.expect((e.kind==QwenOwnerKind.Dense || e.kind==QwenOwnerKind.GdnConv).B)
        d.io.job.bits.activationBf16.expect((e.kind!=QwenOwnerKind.GdnRecurrent).B)
        d.io.job.bits.outputBf16.expect((e.kind!=QwenOwnerKind.GdnInputPrep).B)
        val saved=d.io.job.bits.peek()
        for(_<-0 until 3){unchanged();d.io.job.bits.expect(saved);d.io.completion.valid.expect(false.B);d.clock.step()}
        d.io.job.ready.poke(true.B);d.clock.step();d.io.job.ready.poke(false.B)
        for(_<-0 until 3){unchanged();d.io.completion.valid.expect(false.B);d.io.memory.valid.expect(false.B);d.clock.step()}
        val f=if(jobs==faultJob)fault else 0
        d.io.done.bits.tag.poke((if(f==2)tag^1 else tag).U);d.io.done.bits.status.poke((if(f==1)Status.Memory else 0).U)
        d.io.done.bits.writeBytes.poke((e.bytes+(if(f==3)-64 else if(f==4)64 else 0)).U)
        d.io.done.valid.poke(true.B);d.io.done.ready.expect(true.B);d.clock.step();d.io.done.valid.poke(false.B)
        if(f==0)written+=e.bytes
        jobs+=1
      }else if(d.io.completion.valid.peek().litToBoolean){
        val word=d.io.completion.bits.peek().litValue;val ok=((word>>32)&255)==0;val pc=d.io.pc.peek().litValue.toInt
        for(_<-0 until 4){unchanged();d.io.completion.bits.expect(word.U);d.io.job.valid.expect(false.B);d.io.memory.valid.expect(false.B);d.clock.step()}
        d.io.completion.ready.poke(true.B);d.clock.step();d.io.completion.ready.poke(false.B)
        if(ok){completed+=1;if(pc==7){generation=p.generation+1;history=p.hout;state=p.sout;valid=true}}
        unchanged()
      }else d.clock.step()
      ticks+=1
    }
    d.io.result.valid.expect(true.B);d.io.result.bits.completed.expect(completed.U);d.io.result.bits.epoch.expect(9.U)
    val status=d.io.result.bits.status.peek().litValue.toInt
    d.io.issuedJobs.expect(jobs.U);d.io.writeBytes.expect(written.U);d.io.resetRequired.expect((status!=0).B);unchanged()
    d.clock.step(2);d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
    d.io.launch.ready.expect((status==0).B)
    (status,jobs,completed)
  }
  "Host GDN core CONTROL_ONLY" should "publish both persistent states only at the accepted terminal fence" in {
    test(new GdnCoreFrontendControlHarness).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val p=program();p.records.size shouldBe 113
      run(d,p) shouldBe (0,7,8)
      run(d,program(1,false,h0,h1,s0,s1),reset=false) shouldBe (0,7,8)
      run(d,program(2,false,h1,h0,s1,s0),reset=false) shouldBe (0,7,8)
      // Only the committed checkpoint parameters persist across tokens;
      // all three projections may consume the next hidden token allocation.
      var nextHidden=program(3,false,h0,h1,s0,s1)
      for(root<-Seq(0,12,24))nextHidden=edit(nextHidden,root,56,48,hidden+64)
      nextHidden=nextHidden.copy(expected=nextHidden.expected.zipWithIndex.map{case(e,i)=>if(i<3)e.copy(a=hidden+64) else e})
      run(d,nextHidden,reset=false) shouldBe (0,7,8)
      // Hidden cannot masquerade as a not-yet-visited checkpoint parameter;
      // reject before the first Dense, not when gamma is eventually read.
      run(d,p) shouldBe (0,7,8)
      var parameterAsHidden=program(1,false,h0,h1,s0,s1)
      for(root<-Seq(0,12,24))parameterAsHidden=edit(parameterAsHidden,root,56,48,gamma)
      parameterAsHidden=parameterAsHidden.copy(expected=parameterAsHidden.expected.zipWithIndex.map{
        case(e,i)=>if(i<3)e.copy(a=gamma) else e})
      run(d,parameterAsHidden,reset=false) shouldBe (Status.Permission,0,0)
      // A new parameter allocation cannot be combined with the old state.
      for(root<-Seq(3,15,27,39,66,69,99)){
        run(d,p) shouldBe (0,7,8)
        val carry=program(1,false,h0,h1,s0,s1)
        val address=((carry.records(root)>>56)&((BigInt(1)<<48)-1))+(if(root==66)128 else 64)
        run(d,edit(carry,root,56,48,address),reset=false)._1 shouldBe Status.Permission
      }
      // Reclassifying an unvisited checkpoint parameter as writable must not
      // let an earlier producer corrupt it before its own source validation.
      val highGamma=rw-0x10000
      var high=edit(p,99,56,48,highGamma)
      high=high.copy(expected=high.expected.updated(6,high.expected(6).copy(c=highGamma)))
      run(d,high,readonlyLimit=rw) shouldBe (0,7,8)
      var destructive=edit(program(1,false,h0,h1,s0,s1),99,56,48,highGamma)
      destructive=edit(destructive,6,56,48,highGamma)
      run(d,destructive,reset=false,readonlyLimit=highGamma,writableBase=highGamma) shouldBe (Status.Permission,0,0)
      // An already-signaled event is insufficient: v2 requires the immediately
      // preceding command's signal. Legacy event admission is unchanged.
      val skippedWait=p.copy(commands=p.commands.updated(1,field(p.commands(1),24,16,BigInt(0))))
      run(d,skippedWait) shouldBe (Status.Dependency,1,1)
      // Warm state requires an existing committed context. Recovery cannot
      // silently import a reference state through ordinary readonly tensors.
      run(d,program(cold=false)) shouldBe (Status.Dependency,0,0)
      for(job<-0 until 7;fault<-1 to 4){
        run(d,p) shouldBe (0,7,8)
        run(d,program(1,false,h0,h1,s0,s1),reset=false,faultJob=job,fault=fault) shouldBe
          (if(fault==1)Status.Memory else Status.Protocol,job+1,job)
      }
      // Invalid terminal publication never advances either persistent root.
      for((i,v)<-Seq((102,h1),(105,s1),(108,finalD+64))){
        run(d,edit(p,i,56,48,v))._1 should not be 0
      }
      // Omitting the fence fails before issuing the last arithmetic command.
      run(d,p.copy(commands=p.commands.dropRight(1))) shouldBe (Status.Malformed,6,6)
      // Gen/cold/path are uniform across all public commands; bad early context
      // fails before any Dense write, while a bad late one cannot commit Conv.
      run(d,program(generation=1)) shouldBe (Status.Dependency,0,0)
      for(i<-Seq(11,23,35,46,64,82,97,112)){
        run(d,edit(p,i,81,1,BigInt(1)))._1 should not be 0
        run(d,edit(p,i,88,32,BigInt(1)))._1 should not be 0
      }
      // Different hidden input, external stand-ins and unpublished gaps cannot
      // replace any real producer in the transaction.
      for((i,v)<-Seq((12,hidden+64),(36,hidden),(54,hidden),(57,hidden),(72,hidden),(87,hidden),(90,hidden))){
        run(d,edit(p,i,56,48,v))._1 should not be 0
      }
      // Every extra root has the same dtype/stride/tail/bounds enforcement as
      // primary operands. Recurrent state must remain FP32, including stateOut.
      for(root<-Seq(48,51,66,69,75,84,99)){
        run(d,edit(p,root,108,4,BigInt(4)))._1 should not be 0
        run(d,edit(p,root+2,56,24,BigInt(2)))._1 should not be 0
      }
      for((i,lo,width,v)<-Seq((65,80,24,BigInt(66)),(83,80,24,BigInt(84)),(98,80,24,BigInt(99)),
        (65,104,24,BigInt(1)),(83,104,24,BigInt(1)),(98,104,24,BigInt(1)),(112,32,24,BigInt(111)))){
        run(d,edit(p,i,lo,width,v))._1 should not be 0
      }
      // Distinct semantic sources stay disjoint across separate commands,
      // including cold history/state whose payloads will not be consumed.
      for((root,address)<-Seq((15,qkvW),(27,zW),(39,hidden),(48,hidden),(66,qkvW),(69,convW),(75,qkvW),(99,aLog))){
        run(d,edit(p,root,56,48,address))._1 shouldBe Status.Permission
      }
      run(d,p,badMemoryTag=true)._1 should not be 0
      run(d,p,writeOnly=true)._1 should not be 0
      // Previous durable roots cannot be overwritten by even the first Dense.
      for(target<-Seq(h0,s0)){
        run(d,p) shouldBe (0,7,8)
        run(d,edit(program(1,false,h0,h1,s0,s1),6,56,48,target),reset=false) shouldBe (Status.Permission,0,0)
      }
      // Unsupported M128 is never silently claimed by the M1 core profile.
      run(d,edit(p,1,56,18,BigInt(128))) shouldBe (Status.Unsupported,0,0)
      // Faults lock; reset explicitly clears context. Checkpoint restoration is
      // a separate protocol and is not implied by this cold-reset test.
      run(d,p) shouldBe (0,7,8)
    }
  }
  it should "remain disabled without the explicit core flag" in {
    test(new GdnCoreFrontendControlHarness(false)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      run(d,program()) shouldBe (Status.Unsupported,0,0)
    }
  }
}

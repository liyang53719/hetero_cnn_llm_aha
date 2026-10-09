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
class GdnBlockFrontendControlHarness(enabled:Boolean=true) extends HostBlockCommands(
  QwenBlockShape.qwen35Gdn(),eventSlots=32,maxCommands=21,bf16Gdn=true,bf16GdnCore=true,bf16GdnBlock=enabled) {
  val committedValid=IO(Output(Bool()));committedValid:=stateValid
  val committedGeneration=IO(Output(UInt(32.W)));committedGeneration:=currentGeneration
  val committedHistory=IO(Output(UInt(64.W)));committedHistory:=currentHistoryAddress
  val committedState=IO(Output(UInt(64.W)));committedState:=currentStateAddress
}
class HostBlockCommandsGdnBlockSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val nil=BigInt(0xffffff);val cb=BigInt(0x1000);val db=BigInt(0x2000)
  val hidden=BigInt(0x10000);val convW=BigInt(0x20000);val initialHistory=BigInt(0x40000)
  val aLog=BigInt(0x50000);val dtBias=BigInt(0x50040);val gamma=BigInt(0x50100);val initialState=BigInt(0x80000)
  val qkvW=BigInt(0x300000);val zW=BigInt(0x1000000);val abW=BigInt(0x1500000)
  val rw=BigInt(0x4000000);val rwEnd=BigInt(0x8000000)
  val qkv=rw;val z=rw+0x4000;val ab=rw+0x5000;val conv=rw+0x8000;val prep=rw+0x10000
  val core=rw+0x18000;val gatedNorm=rw+0x1a000
  val inputGamma=BigInt(0x60000);val postGamma=BigInt(0x61000)
  val oW=BigInt(0x1600000);val gateW=BigInt(0x1a00000);val upW=BigInt(0x2100000);val downW=BigInt(0x2800000)
  val inputNorm=rw+0x20000;val o=rw+0x22000;val residual1=rw+0x23000;val postNorm=rw+0x24000
  val gate=rw+0x26000;val up=rw+0x28000;val silu=rw+0x2a000;val down=rw+0x2c000;val finalD=rw+0x2d000
  val h0=rw+0x100000;val h1=rw+0x110000;val s0=rw+0x200000;val s1=rw+0x400000
  case class T(address:BigInt,m:Int,n:Int,dtype:Int=5)
  case class E(kind:Int,a:BigInt,b:BigInt,dst:BigInt,n:Int,k:Int,bytes:BigInt,c:BigInt=0,hout:BigInt=0,
               sout:BigInt=0,alog:BigInt=0,dt:BigInt=0,cold:Boolean=false,generation:BigInt=0,mode:Boolean=false,elementOp:Int=0)
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
    def gp(op:Int,role:Int):BigInt=BigInt(3)|(BigInt(op)<<8)|(BigInt(if(cold)1 else 0)<<24)|
      (BigInt(if(cold)0 else 1)<<25)|(BigInt(role)<<26)|(generation<<32)
    def add(op:Int,role:Int,a:T,b:T,d:T,extras:Vector[T]=Vector.empty,e:Option[E]=None):Unit={
      val start=records.size;val pc=commands.size
      val matrix=op==2;val tail:BigInt=if(matrix || extras.nonEmpty)BigInt(start+11) else nil
      val policies=if(matrix)Vector(rec(0x10,start+10,BigInt(1)|(BigInt(d.n)<<16)|(BigInt(a.n)<<32)),
        rec(0x12,start+11,BigInt("004000040020ffffff",16)),rec(0x21,nil,gp(op,role)))
      else {
        val inType=if(op==4)7 else 5;val outType=if(op==3)7 else 5
        val sfu=BigInt(0x30)|(BigInt(2)<<16)|(BigInt(1)<<24)|(BigInt(inType)<<32)|
          (BigInt(outType)<<36)|(BigInt(16)<<40)|(BigInt(1)<<48)
        Vector(rec(0x20,start+10,sfu),rec(0x21,tail,gp(op,role)))++
          (if(extras.nonEmpty)Vector(rec(if(op==1)0x22 else 0x23,nil,BigInt(start+12)|((if(extras.size==2)BigInt(start+15) else nil)<<24))) else Vector.empty)
      }
      records=records++prefix(a,start,start+9)++prefix(b,start+3,nil)++prefix(d,start+6,nil)++policies++
        extras.zipWithIndex.flatMap{case(t,i)=>prefix(t,start+12+3*i,nil)}
      commands=commands:+(BigInt(if(matrix)0x220 else 0x330)|(BigInt(pc)<<24)|(BigInt(pc+1)<<40)|
        (BigInt(start)<<56)|(BigInt(start+3)<<80)|(BigInt(start+6)<<104))
      e.foreach(x=>expected=expected:+x)
    }
    add(8,0,T(hidden,1,1024),T(inputGamma,1,1024),T(inputNorm,1,1024),
      e=Some(E(QwenOwnerKind.GdnRmsNorm,hidden,inputGamma,inputNorm,1024,1024,2048)))
    for(((n,w,d),role)<-Seq((6144,qkvW,qkv),(2048,zW,z),(32,abW,ab)).zipWithIndex)
      add(2,role,T(inputNorm,1,1024),T(w,1024,n),T(d,1,n),e=Some(E(QwenOwnerKind.Dense,inputNorm,w,d,n,1024,n*2)))
    add(1,0,T(qkv,1,6144),T(convW,6144,4),T(conv,1,6144),Vector(T(hin,6144,4),T(hout,6144,4)),
      Some(E(QwenOwnerKind.GdnConv,qkv,convW,conv,6144,4,6144*2+6144*4*2,c=hin,hout=hout,cold=cold,generation=generation)))
    add(3,0,T(conv,1,6144),T(ab,1,32),T(prep,1,6400,7),Vector(T(aLog,1,16,7),T(dtBias,1,16)),
      Some(E(QwenOwnerKind.GdnInputPrep,conv,ab,prep,16,128,6400*4,alog=aLog,dt=dtBias,mode= !cold)))
    add(4,0,T(prep,1,6400,7),T(sin,2048,128,7),T(core,1,2048),Vector(T(sout,2048,128,7)),
      Some(E(QwenOwnerKind.GdnRecurrent,prep,sin,core,16,128,2048*2+2048*128*4,sout=sout,cold=cold,generation=generation)))
    add(5,0,T(core,1,2048),T(z,1,2048),T(gatedNorm,1,2048),Vector(T(gamma,1,128,7)),
      Some(E(QwenOwnerKind.GdnGatedNorm,core,z,gatedNorm,16,128,2048*2,c=gamma)))
    add(2,3,T(gatedNorm,1,2048),T(oW,2048,1024),T(o,1,1024),
      e=Some(E(QwenOwnerKind.Dense,gatedNorm,oW,o,1024,2048,2048)))
    add(9,0,T(hidden,1,1024),T(o,1,1024),T(residual1,1,1024),
      e=Some(E(QwenOwnerKind.GdnElementwise,hidden,o,residual1,1024,1024,2048)))
    add(8,1,T(residual1,1,1024),T(postGamma,1,1024),T(postNorm,1,1024),
      e=Some(E(QwenOwnerKind.GdnRmsNorm,residual1,postGamma,postNorm,1024,1024,2048)))
    for((role,w,d)<-Seq((4,gateW,gate),(5,upW,up)))
      add(2,role,T(postNorm,1,1024),T(w,1024,3584),T(d,1,3584),
        e=Some(E(QwenOwnerKind.Dense,postNorm,w,d,3584,1024,7168)))
    add(9,1,T(gate,1,3584),T(up,1,3584),T(silu,1,3584),
      e=Some(E(QwenOwnerKind.GdnElementwise,gate,up,silu,3584,3584,7168,elementOp=1)))
    add(2,6,T(silu,1,3584),T(downW,3584,1024),T(down,1,1024),
      e=Some(E(QwenOwnerKind.Dense,silu,downW,down,1024,3584,2048)))
    add(9,2,T(residual1,1,1024),T(down,1,1024),T(finalD,1,1024),
      e=Some(E(QwenOwnerKind.GdnElementwise,residual1,down,finalD,1024,1024,2048)))
    add(6,0,T(hout,6144,4),T(sout,2048,128,7),T(finalD,1,1024))
    P(commands,records,expected,generation,hout,sout)
  }
  def root(p:P,pc:Int,operand:Int=0):Int=((p.commands(pc)>>(56+24*operand))&nil).toInt
  def gpIndex(p:P,pc:Int):Int=root(p,pc)+(if((p.commands(pc)&255)==0x20)11 else 10)
  def edit(p:P,i:Int,lo:Int,width:Int,v:BigInt):P=p.copy(records=p.records.updated(i,field(p.records(i),lo,width,v)))
  def setup(d:GdnBlockFrontendControlHarness,p:P,reset:Boolean):Unit={
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
  def run(d:GdnBlockFrontendControlHarness,p:P,reset:Boolean=true,faultJob:Int= -1,fault:Int=0,
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
        d.io.job.bits.gdnALog.expect(e.alog.U);d.io.job.bits.gdnDtBias.expect(e.dt.U);d.io.job.bits.gdnRecurrentMode.expect(e.mode.B);d.io.job.bits.gdnElementwiseOp.expect(e.elementOp.U)
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
        if(ok){completed+=1;if(pc==16){generation=p.generation+1;history=p.hout;state=p.sout;valid=true}}
        unchanged()
      }else d.clock.step()
      ticks+=1
    }
    d.io.result.valid.expect(true.B);d.io.result.bits.completed.expect(completed.U);d.io.result.bits.epoch.expect(9.U)
    val status=d.io.result.bits.status.peek().litValue.toInt
    // A malformed launch count is rejected before a transaction starts and
    // does not poison an otherwise usable interface. In-flight faults lock.
    val launchRejected=p.commands.size!=17
    if(launchRejected){status shouldBe Status.Bounds;jobs shouldBe 0;completed shouldBe 0}
    d.io.issuedJobs.expect(jobs.U);d.io.writeBytes.expect(written.U);d.io.resetRequired.expect((status!=0 && !launchRejected).B);unchanged()
    d.clock.step(2);d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
    d.io.launch.ready.expect((status==0 || launchRejected).B)
    (status,jobs,completed)
  }
  "Host full GDN block CONTROL_ONLY" should "bind the actual 17-command block and publish state only after final residual ACK and fence" in {
    test(new GdnBlockFrontendControlHarness).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val p=program();p.commands.size shouldBe 17;p.expected.size shouldBe 16
      run(d,p) shouldBe (0,16,17)
      run(d,program(1,false,h0,h1,s0,s1),reset=false) shouldBe (0,16,17)
      run(d,program(2,false,h1,h0,s1,s0),reset=false) shouldBe (0,16,17)
      run(d,program(cold=false)) shouldBe (Status.Dependency,0,0)
      run(d,program(generation=1)) shouldBe (Status.Dependency,0,0)
      // The original raw hidden changes per token, while both residuals use
      // actual earlier producers and checkpoint parameters remain unchanged.
      run(d,p) shouldBe (0,16,17)
      var next=program(1,false,h0,h1,s0,s1)
      for(pc<-Seq(0,9))next=edit(next,root(next,pc),56,48,hidden+0x1000)
      next=next.copy(expected=next.expected.zipWithIndex.map{case(e,i)=>if(i==0||i==9)e.copy(a=hidden+0x1000) else e})
      run(d,next,reset=false) shouldBe (0,16,17)
      // Every extension requires BF16; role 7 and reserved fields are invalid.
      for(pc<-Seq(0,8,9,10,11,12,13,14,15);operand<-0 to 2)
        run(d,edit(p,root(p,pc,operand),108,4,BigInt(7)))._1 should not be 0
      for(pc<-0 until 17){
        run(d,edit(p,gpIndex(p,pc),82,3,BigInt(7)))._1 should not be 0
        run(d,edit(p,gpIndex(p,pc),85,1,BigInt(1)))._1 should not be 0
        run(d,edit(p,gpIndex(p,pc),81,1,BigInt(1)))._1 should not be 0
        run(d,edit(p,gpIndex(p,pc),88,32,BigInt(1)))._1 should not be 0
      }
      // External tensors and the raw hidden cannot substitute for a producer.
      for((pc,operand)<-Seq((1,0),(2,0),(3,0),(4,0),(5,0),(5,1),(6,0),(7,0),(7,1),
        (8,0),(9,1),(10,0),(11,0),(12,0),(13,0),(13,1),(14,0),(15,0),(15,1),(16,2)))
        run(d,edit(p,root(p,pc,operand),56,48,hidden))._1 should not be 0
      val wrongRole=edit(p,gpIndex(p,12),82,3,BigInt(4))
      run(d,wrongRole) shouldBe (Status.Dependency,12,12)
      val skippedWait=p.copy(commands=p.commands.updated(1,field(p.commands(1),24,16,BigInt(0))))
      run(d,skippedWait) shouldBe (Status.Dependency,1,1)
      // All thirteen committed parameters are protected across carried tokens.
      val parameterRoots=Seq(root(p,0,1),root(p,1,1),root(p,2,1),root(p,3,1),root(p,4,1),
        root(p,5)+12,root(p,5)+15,root(p,7)+12,root(p,8,1),root(p,10,1),root(p,11,1),root(p,12,1),root(p,14,1))
      for(r<-parameterRoots){
        run(d,p) shouldBe (0,16,17)
        val carry=program(1,false,h0,h1,s0,s1)
        val address=((carry.records(r)>>56)&((BigInt(1)<<48)-1))+64
        run(d,edit(carry,r,56,48,address),reset=false)._1 shouldBe Status.Permission
      }
      // Semantically distinct readonly sources must never overlap, even before
      // any arithmetic would consume cold history or recurrent-state payloads.
      for((r,address)<-Seq((root(p,0,1),hidden),(root(p,2,1),qkvW),(root(p,4)+12,inputGamma),
        (root(p,6,1),qkvW),(root(p,8,1),qkvW),(root(p,10,1),inputGamma),(root(p,12,1),gateW),(root(p,14,1),upW)))
        run(d,edit(p,r,56,48,address))._1 shouldBe Status.Permission
      // The final residual ACK is necessary but cannot publish either root.
      // The run helper stalls every completion and checks old roots throughout.
      for(job<-Seq(0,4,6,8,9,10,11,12,13,14,15);fault<-1 to 4){
        run(d,p) shouldBe (0,16,17)
        run(d,program(1,false,h0,h1,s0,s1),reset=false,faultJob=job,fault=fault) shouldBe
          (if(fault==1)Status.Memory else Status.Protocol,job+1,job)
      }
      for((operand,address)<-Seq((0,h1),(1,s1),(2,gatedNorm),(2,finalD+64))){
        run(d,p) shouldBe (0,16,17)
        val carry=program(1,false,h0,h1,s0,s1)
        val wrong=if(operand==0)h0 else if(operand==1)s0 else address
        run(d,edit(carry,root(carry,16,operand),56,48,wrong),reset=false)._1 should not be 0
      }
      for(target<-Seq(h0,s0)){
        run(d,p) shouldBe (0,16,17)
        val carry=program(1,false,h0,h1,s0,s1)
        run(d,edit(carry,root(carry,0,2),56,48,target),reset=false) shouldBe (Status.Permission,0,0)
      }
      // Previously committed parameter spans remain protected even if a later
      // launch reclassifies those addresses as writable before visiting them.
      val highGamma=rw-0x10000
      var high=edit(p,root(p,10,1),56,48,highGamma)
      high=high.copy(expected=high.expected.updated(10,high.expected(10).copy(b=highGamma)))
      run(d,high,readonlyLimit=rw) shouldBe (0,16,17)
      var destructive=program(1,false,h0,h1,s0,s1)
      destructive=edit(destructive,root(destructive,10,1),56,48,highGamma)
      destructive=edit(destructive,root(destructive,0,2),56,48,highGamma)
      run(d,destructive,reset=false,readonlyLimit=highGamma,writableBase=highGamma) shouldBe (Status.Permission,0,0)
      run(d,p.copy(commands=p.commands.dropRight(1))) shouldBe (Status.Bounds,0,0)
      run(d,p,badMemoryTag=true)._1 should not be 0
      run(d,p,writeOnly=true)._1 should not be 0
      run(d,p) shouldBe (0,16,17)
    }
  }
  it should "reject version 3 without the explicit full-block flag" in {
    test(new GdnBlockFrontendControlHarness(false)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      run(d,program()) shouldBe (Status.Malformed,0,0)
    }
  }
}

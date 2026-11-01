package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.{VerilatorBackendAnnotation,VerilatorCFlags}

/** Local component fixture only: one true shared vector bank and the original
  * shared scalar primitive. No DPI/Python arithmetic response substitution. */
class RuntimeRms32BankFixture extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new GdnRuntimeRmsNormJobV3))
    val done=Decoupled(new GdnRuntimeRmsNormResultV16)
    val memory=Decoupled(new MemoryRequest)
    val response=Flipped(Decoupled(new MemoryResponse))
    val vectorIssueEnable=Input(Bool());val vectorRetireEnable=Input(Bool())
    val scalarIssueEnable=Input(Bool());val scalarRetireEnable=Input(Bool())
    val parentFault=Input(Bool());val resetRequired=Output(Bool());val drained=Output(Bool())
    val vectorIssue=Output(Bool());val vectorRetire=Output(Bool())
    val vectorRequest=Output(new UnifiedVectorElement32PayloadV4)
    val vectorResult=Output(new UnifiedVectorElement32ResultPayloadV4)
    val scalarIssue=Output(Bool());val scalarRetire=Output(Bool())
    val scalarRequest=Output(new UnifiedScalarRequestV2)
    val scalarResult=Output(new UnifiedScalarResultV2)
  })
  val owner=Module(new GdnRuntimeRmsNormOwnerV3)
  val bank=Module(new UnifiedVectorElement32BankV4)
  val scalar=Module(new BlockScalarFloatPolicyV2)
  owner.io.job<>io.job;io.done<>owner.io.done;io.memory<>owner.io.memory;owner.io.response<>io.response
  owner.io.parentFault:=io.parentFault;io.resetRequired:=owner.io.resetRequired;io.drained:=owner.io.resourcesDrained
  owner.io.published.memory:=io.memory.valid
  owner.io.formatRequest.ready:=false.B;owner.io.formatResult.valid:=false.B
  owner.io.formatResult.bits:=0.U.asTypeOf(new UnifiedRawFp32FormatResultV3);owner.io.published.format:=false.B
  // Once visible, keep request published until accepted even if enable drops.
  val vectorHeld=RegInit(false.B);val scalarHeld=RegInit(false.B)
  val vectorVisible=io.vectorIssueEnable || vectorHeld
  bank.io.request.valid:=owner.io.vectorRequest.valid && vectorVisible
  bank.io.request.bits.identity:=0.U.asTypeOf(new UnifiedSharedOperationTagV3)
  bank.io.request.bits.payload:=owner.io.vectorRequest.bits
  owner.io.vectorRequest.ready:=bank.io.request.ready && vectorVisible
  owner.io.published.vector:=bank.io.request.valid
  when(bank.io.request.valid){vectorHeld:= !bank.io.request.ready}
  owner.io.vectorResult.valid:=bank.io.result.valid && io.vectorRetireEnable
  owner.io.vectorResult.bits:=bank.io.result.bits.payload
  bank.io.result.ready:=owner.io.vectorResult.ready && io.vectorRetireEnable
  val scalarVisible=io.scalarIssueEnable || scalarHeld
  scalar.io.request.valid:=owner.io.scalar.request.valid && scalarVisible
  scalar.io.request.bits:=owner.io.scalar.request.bits
  owner.io.scalar.request.ready:=scalar.io.request.ready && scalarVisible
  owner.io.published.scalar:=scalar.io.request.valid
  when(scalar.io.request.valid){scalarHeld:= !scalar.io.request.ready}
  owner.io.scalar.result.valid:=scalar.io.result.valid && io.scalarRetireEnable
  owner.io.scalar.result.bits:=scalar.io.result.bits
  scalar.io.result.ready:=owner.io.scalar.result.ready && io.scalarRetireEnable
  io.vectorIssue:=bank.io.request.fire;io.vectorRetire:=owner.io.vectorResult.fire
  io.vectorRequest:=owner.io.vectorRequest.bits;io.vectorResult:=owner.io.vectorResult.bits
  io.scalarIssue:=scalar.io.request.fire;io.scalarRetire:=owner.io.scalar.result.fire
  io.scalarRequest:=owner.io.scalar.request.bits;io.scalarResult:=owner.io.scalar.result.bits
}

object RuntimeRms32ModelTest extends App {
  // Host calculations are expectations only; all responses above come from
  // actual HardFloat/Verilator circuits. Float operations explicitly stage FP32.
  def raw(x:Float):BigInt=BigInt(java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL)
  def fp(x:BigInt):Float=java.lang.Float.intBitsToFloat(x.toInt)
  def add(a:BigInt,b:BigInt):BigInt=raw((fp(a)+fp(b)).toFloat)
  def mul(a:BigInt,b:BigInt):BigInt=raw((fp(a)*fp(b)).toFloat)
  def bf(a:BigInt):BigInt=((a+0x7fff+((a>>16)&1))>>16)&0xffff
  val zero=BigInt(0);val one=raw(1.0f)
  case class V(policy:Int,multiply:Boolean,a:Vector[BigInt],b:Vector[BigInt],result:Vector[BigInt])
  case class Expected(x:Vector[BigInt],w:Vector[BigInt],v:Vector[V],scalar:Vector[(Int,BigInt,BigInt,BigInt)],out:Vector[BigInt])
  def expected(h:Int):Expected={
    val x=Vector.tabulate(h)(i=>raw((if(i%5==0)-1.0f else 1.0f)*(0.25f+(i%7)*0.25f)))
    val w=Vector.tabulate(h)(i=>raw((if(i%3==0)-1.0f else 1.0f)*(i%4)*0.0625f))
    val tx=scala.collection.mutable.ArrayBuffer.empty[V]
    def send(policy:Int,multiply:Boolean,a:Vector[BigInt],b:Vector[BigInt]):Vector[BigInt]={
      val y=if(policy==4)a.map(q=>bf(q)<<16)else a.zip(b).map{case(l,r)=>if(multiply)mul(l,r)else add(l,r)}
      tx+=V(policy,multiply,a,b,y);y
    }
    var partial=Vector.fill(32)(zero)
    for(chunk<-0 until h/1024;block<-0 until 2){
      var sum=Vector.fill(32)(zero)
      for(term<-0 until 16){
        val values=Vector.tabulate(32)(i=>x(chunk*1024+block*512+term*32+(i%4)*8+i/4))
        val square=send(3,true,values,values);sum=send(0,false,sum,square)
      }
      partial=send(0,false,if(chunk==0 && block==0)Vector.fill(32)(zero)else partial,sum)
    }
    var folded=Vector.fill(32)(zero)
    for(res<-0 until 4)folded=send(0,false,folded,Vector.tabulate(32)(i=>if(i<8)partial(i*4+res)else zero))
    var total=zero
    for(lane<-0 until 8){total=send(0,false,Vector.tabulate(32)(i=>if(i==0)total else zero),Vector.tabulate(32)(i=>if(i==0)folded(lane)else zero))(0)}
    // Cross-check independent original scalar permutation and sequential folds.
    val old=Array.fill[BigInt](32)(zero)
    for(chunk<-0 until h/1024){var acc=zero
      for(lane<-0 until 1024){
        val cpu=(lane>>7)&7;val res=(lane>>5)&3;val block=(lane>>4)&1;val term=lane&15
        val q=x(chunk*1024+block*512+term*32+res*8+cpu);acc=add(acc,mul(q,q))
        if(term==15){val i=cpu*4+res;old(i)=add(if(chunk==0 && block==0)zero else old(i),acc);acc=zero}
      }
    }
    var oldTotal=zero
    for(cpu<-0 until 8){var a=zero;for(res<-0 until 4)a=add(a,old(cpu*4+res));oldTotal=add(oldTotal,a)}
    assert(old.toVector==partial && oldTotal==total)
    val mean=mul(oldTotal,raw(1.0f/h));val eps=add(mean,raw(1e-6f));val root=raw(Math.sqrt(fp(eps).toDouble).toFloat);val inv=raw((1.0f/fp(root)).toFloat)
    val scalar=Vector((ScalarOp.MulIeeeRne,oldTotal,raw(1.0f/h),mean),(ScalarOp.Add,mean,raw(1e-6f),eps),(ScalarOp.Sqrt,eps,zero,root),(ScalarOp.Div,one,root,inv))
    val output=scala.collection.mutable.ArrayBuffer.empty[BigInt]
    for(start<-0 until h by 32){
      val norm=send(3,true,x.slice(start,start+32),Vector.fill(32)(inv))
      val gamma=send(0,false,Vector.fill(32)(one),w.slice(start,start+32))
      val weighted=send(3,true,norm,gamma)
      val fmt=send(4,false,weighted,Vector.fill(32)(zero));output++=fmt.map(_>>16)
    }
    val independent=x.zip(w).map{case(a,b)=>bf(mul(mul(a,inv),add(one,b)))}
    assert(independent==output.toVector && tx.size==(if(h==1024)206 else 400))
    Expected(x,w,tx.toVector,scalar,output.toVector)
  }
  println("RUNTIME_RMS_LOCAL_BEFORE_ELABORATION_NOT_FULL_BLOCK")
  RawTester.test(new RuntimeRms32BankFixture,Seq(VerilatorBackendAnnotation,VerilatorCFlags(Seq("-O0","-fno-fast-math","-ffp-contract=off")))){c=>
    c.io.job.valid.poke(false.B);c.io.done.ready.poke(false.B);c.io.memory.ready.poke(false.B)
    c.io.response.valid.poke(false.B);c.io.response.bits.data.poke(0.U);c.io.response.bits.tag.poke(0.U);c.io.response.bits.error.poke(false.B)
    c.io.parentFault.poke(false.B);c.io.vectorIssueEnable.poke(true.B);c.io.vectorRetireEnable.poke(true.B);c.io.scalarIssueEnable.poke(true.B);c.io.scalarRetireEnable.poke(true.B)
    c.clock.step(2)
    def job(h:Int,tag:Int):Unit={
      c.io.job.bits.tokens.poke(1.U);c.io.job.bits.hiddenWidth.poke(h.U);c.io.job.bits.input.poke(0x1000.U)
      c.io.job.bits.weight.poke(0x10000.U);c.io.job.bits.output.poke(0x20000.U);c.io.job.bits.tag.poke(tag.U)
      c.io.job.bits.reductionRecipe.poke(1.U);c.io.job.bits.phase.poke(0.U)
      c.io.job.valid.poke(true.B);c.io.job.ready.expect(true.B);c.clock.step();c.io.job.valid.poke(false.B)
    }
    for((h,index)<-Seq(1024,2048).zipWithIndex){
      val e=expected(h);val mem=scala.collection.mutable.Map.empty[BigInt,BigInt]
      for(i<-0 until h){mem(BigInt(0x1000+2*i))=e.x(i)>>16;mem(BigInt(0x10000+2*i))=e.w(i)>>16}
      job(h,index+1)
      var pending:Option[(BigInt,BigInt)]=None;var cycles=0;var memoryCount=0;var writes=0
      var vi=0;var vr=0;var si=0;var sr=0
      while(!c.io.done.valid.peek().litToBoolean && cycles<20000){
        c.io.memory.ready.poke((pending.isEmpty && cycles%3!=0).B)
        c.io.response.valid.poke((pending.nonEmpty && cycles%5!=0).B)
        c.io.response.bits.tag.poke(pending.map(_._1).getOrElse(zero).U);c.io.response.bits.data.poke(pending.map(_._2).getOrElse(zero).U)
        c.io.vectorIssueEnable.poke((cycles%4!=0).B);c.io.vectorRetireEnable.poke((cycles%7!=0).B)
        c.io.scalarIssueEnable.poke((cycles%3!=0).B);c.io.scalarRetireEnable.poke((cycles%5!=0).B)
        val takeMem=c.io.memory.valid.peek().litToBoolean && c.io.memory.ready.peek().litToBoolean
        val takeResp=c.io.response.valid.peek().litToBoolean && c.io.response.ready.peek().litToBoolean
        var next:Option[(BigInt,BigInt)]=None
        if(takeMem){
          val addr=c.io.memory.bits.address.peek().litValue;val tag=c.io.memory.bits.tag.peek().litValue
          assert(tag==((BigInt(index+1)<<32)+memoryCount));memoryCount+=1
          if(c.io.memory.bits.write.peek().litToBoolean){
            assert(addr>=0x20000 && addr<BigInt(0x20000+2*h));c.io.memory.bits.mask.expect(((BigInt(1)<<64)-1).U)
            val data=c.io.memory.bits.data.peek().litValue
            for(i<-0 until 32)mem(addr+2*i)=(data>>(16*i))&0xffff
            writes+=1;next=Some((tag,zero))
          }else{assert((addr>=0x1000 && addr<BigInt(0x1000+2*h))||(addr>=0x10000 && addr<BigInt(0x10000+2*h)))
            next=Some((tag,(0 until 32).foldLeft(zero)((a,i)=>a|(mem(addr+2*i)<<(16*i)))))
          }
        }
        if(c.io.vectorIssue.peek().litToBoolean){
          assert(vi<e.v.size);val v=e.v(vi);c.io.vectorRequest.policy.expect(v.policy.U);c.io.vectorRequest.multiply.expect(v.multiply.B)
          for(i<-0 until 32){c.io.vectorRequest.a(i).expect(v.a(i).U);c.io.vectorRequest.b(i).expect(v.b(i).U)};vi+=1
        }
        if(c.io.vectorRetire.peek().litToBoolean){
          assert(vr<vi);val v=e.v(vr);c.io.vectorResult.policy.expect(v.policy.U);c.io.vectorResult.error.expect(false.B)
          c.io.vectorResult.arithFlagsValid.expect((v.policy!=4).B);c.io.vectorResult.formatFlagsValid.expect(false.B)
          for(i<-0 until 32)c.io.vectorResult.value(i).expect(v.result(i).U);vr+=1
        }
        if(c.io.scalarIssue.peek().litToBoolean){val(op,a,b,y)=e.scalar(si);c.io.scalarRequest.policy.expect(0.U);c.io.scalarRequest.payload.op.expect(op.U);c.io.scalarRequest.payload.a.expect(a.U);c.io.scalarRequest.payload.b.expect(b.U);si+=1}
        if(c.io.scalarRetire.peek().litToBoolean){c.io.scalarResult.error.expect(false.B);c.io.scalarResult.value.expect(e.scalar(sr)._4.U);sr+=1}
        c.clock.step();if(takeResp)pending=None;if(takeMem)pending=next;cycles+=1
      }
      assert(cycles<20000 && pending.isEmpty && memoryCount==4*(h/32) && writes==h/32)
      assert(vi==e.v.size && vr==vi && si==4 && sr==4)
      c.io.done.bits.status.expect(Status.Ok.U);c.io.done.bits.outputCommitted.expect(true.B)
      c.io.done.bits.writeBytes.expect((h*2).U);c.io.done.bits.outputAckBytes.expect((h*2).U)
      c.io.done.bits.scalarAccepted.expect(4.U);c.io.done.bits.scalarReturned.expect(4.U)
      c.io.done.bits.vectorAccepted.expect(e.v.size.U);c.io.done.bits.vectorReturned.expect(e.v.size.U)
      c.io.done.bits.formatAccepted.expect(0.U);c.io.done.bits.formatReturned.expect(0.U)
      c.io.done.bits.memoryAccepted.expect(memoryCount.U);c.io.done.bits.memoryReturned.expect(memoryCount.U)
      c.io.done.bits.resourcesDrained.expect(true.B);c.io.resetRequired.expect(false.B)
      for(i<-0 until h)assert(mem(BigInt(0x20000+2*i))==e.out(i),s"BF16 output width=$h index=$i")
      c.clock.step(3);c.io.done.valid.expect(true.B);c.io.done.bits.outputCommitted.expect(true.B)
      c.io.done.ready.poke(true.B);c.clock.step();c.io.done.ready.poke(false.B)
      println(s"RUNTIME_RMS_LOCAL_H${h}_TRUE_BANK_TRUE_SCALAR_EXACT_INTERMEDIATES_PASS cycles=$cycles NO_FULL_BLOCK_PASS")
    }
    // Actual held memory offer survives parent fault; then retire its matching
    // response and report non-commit. No hidden cancel/refund or fake memory ack.
    c.io.memory.ready.poke(false.B);c.io.response.valid.poke(false.B);job(1024,3)
    def memorySnapshot():Vector[BigInt]=Vector(c.io.memory.bits.address.peek().litValue,c.io.memory.bits.data.peek().litValue,c.io.memory.bits.mask.peek().litValue,c.io.memory.bits.tag.peek().litValue,c.io.memory.bits.write.peek().litValue)
    c.io.memory.valid.expect(true.B);val held=memorySnapshot()
    c.clock.step(2);c.io.parentFault.poke(true.B)
    c.clock.step(2);c.io.memory.valid.expect(true.B);assert(memorySnapshot()==held)
    val faultTag=c.io.memory.bits.tag.peek().litValue
    c.io.memory.ready.poke(true.B);c.clock.step();c.io.memory.ready.poke(false.B)
    c.io.response.bits.tag.poke(faultTag.U);c.io.response.bits.data.poke(0.U);c.io.response.valid.poke(true.B)
    c.io.response.ready.expect(true.B);c.clock.step();c.io.response.valid.poke(false.B)
    var stop=0;while(!c.io.done.valid.peek().litToBoolean && stop<20){c.clock.step();stop+=1}
    assert(stop<20);c.io.done.bits.status.expect(Status.Protocol.U);c.io.done.bits.outputCommitted.expect(false.B)
    c.io.done.bits.writeBytes.expect(0.U);c.io.resetRequired.expect(true.B)
    c.clock.step(2);c.io.done.valid.expect(true.B);c.io.done.ready.poke(true.B);c.clock.step();c.io.job.ready.expect(false.B)
    println("RUNTIME_RMS_LOCAL_HELD_PUBLICATION_PARENT_FAULT_NONCOMMIT_PASS_NO_FULL_BLOCK_PASS")
  }
}

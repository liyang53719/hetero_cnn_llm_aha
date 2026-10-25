// SOURCE-ONLY CANDIDATE: never compiled/elaborated/executed during preparation.
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import scala.collection.mutable

/** One case per JVM. No hidden FSM poke, no host-filled scores/probabilities.
  * Test stubs only external Memory + Matrix interfaces; real local SRAM/ALUs/
  * Scalar/PackedClient remain in the exact selected production core.
  */
class OrderedQkBehaviorSpec extends AnyFlatSpec with ChiselScalatestTester {
  "Exact ordered core with unchanged PackedClient" should "meet one bounded protocol case" in {
    val name=sys.props("qwen.case")
    val cases=Set("normal_m1","normal_m2","normal_m3","early_scan","early_fold",
      "early_scale","early_retire_first","early_retire_last","foreign_scan",
      "ordered_add_fault_m3","ordered_scale_fault_m3")
    require(cases(name),"closed case set")
    Seq("heteronpu.continuous.Qwen2ContinuousBlock", "heteronpu.continuous.PackedAttentionStreamClient",
      "treadle2.TreadleTester", "firrtl2.stage.FirrtlStage", "chisel3.RawModule",
      "org.scalatest.tools.Runner", "scala.Predef$").foreach{n=>
      val c=Class.forName(n,false,getClass.getClassLoader)
      println(s"CORE_CLASS_ORIGIN $n ${c.getProtectionDomain.getCodeSource.getLocation.toURI.toASCIIString}")
    }
    val m=if(name=="normal_m1")1 else if(name=="normal_m2")2 else 3
    val failing= !name.startsWith("normal")
    val faultCase=name.startsWith("ordered_")
    val q=BigInt("100000",16);val k=BigInt("200000",16)
    val v=BigInt("300000",16);val dst=BigInt("400000",16)
    val tag=BigInt("7000c",16)
    val cap=99997L
    test(new OrderedQkBehaviorCore(true)).withAnnotations(Seq(TreadleBackendAnnotation, firrtl2.options.TargetDirAnnotation("simulation"), firrtl2.passes.NoCommonSubexpressionEliminationAnnotation)){d=>
      println(s"CORE_SIM_READY case=$name m=$m backend=treadle2 scripted_matrix=true")
      d.clock.setTimeout(0) // Framework reset1 + explicit reset2 + <=99997 body steps = <=100000.
      def zero(x:Data):Unit=x match {
        case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U)
        case r:Record=>r.elements.values.foreach(zero)
        case a:Vec[_]=>a.foreach(zero)
        case _=>throw new IllegalArgumentException("unsupported test input")
      }
      def b(x:Bool)=x.peek().litToBoolean
      def u(x:UInt)=x.peek().litValue
      def fire(v:Bool,r:Bool)=b(v)&&b(r)
      d.io.launch.valid.poke(false.B);zero(d.io.launch.bits)
      d.io.ownerJob.get.valid.poke(false.B);zero(d.io.ownerJob.get.bits)
      d.io.result.ready.poke(false.B)
      d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B);zero(d.io.response.bits)
      d.io.matrixRequest.get.ready.poke(false.B)
      d.io.matrixResult.get.valid.poke(false.B);zero(d.io.matrixResult.get.bits)
      d.io.matrixAcceptedSteps.get.poke(0.U)
      d.io.packedQkStepsDrained.get.poke(false.B)
      val p=d.io.packedQk.get
      p.group.ready.poke(false.B);p.step.ready.poke(false.B)
      p.result.valid.poke(false.B);zero(p.result.bits)
      p.done.valid.poke(false.B);zero(p.done.bits)
      d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B)
      var cycles=0L;var physicalSteps=BigInt(0)
      case class MemoryReply(tag:BigInt,data:BigInt,due:Long)
      var mem:Option[MemoryReply]=None
      var memAccepted=0;var memReturned=0;var writeBytes=0
      val stored=mutable.Set.empty[BigInt]
      var pvPending=false;var pvDue=0L;var pvRequests=0;var pvReturns=0
      var group:Option[BigInt]=None;var steps=0;var qkAcceptedSteps=0;var groups=0;var results=0;var dones=0
      var resultPending=false;var donePending=false;var injected=false
      var targetToken=0;var targetHead=0
      var terminal=false;var jobAccepted=false;var ownerAcceptCount=0
      var heldRequests=Map.empty[String,Vector[(String,BigInt)]]
      var requestHoldChecks=0
      var holdChecksByPort=Map("memory"->0,"group"->0,"step"->0,"pv"->0)
      var targetWrites=Vector.empty[Int];var allWrites=0
      var firstFault2:Option[Long]=None;var firstFault1:Option[Long]=None
      var lastVectorPhase=0;var sawResultHeld=false
      def snapshot(x:Data,path:String=""):Vector[(String,BigInt)]=x match {
        case z:Bool=>Vector(path->(if(b(z))BigInt(1)else BigInt(0)))
        case z:UInt=>Vector(path->u(z))
        case z:Record=>z.elements.toVector.sortBy(_._1).flatMap{case(n,v)=>snapshot(v,path+"."+n)}
        case z:Vec[_]=>z.zipWithIndex.toVector.flatMap{case(v,i)=>snapshot(v,path+"["+i+"]")}
        case _=>throw new IllegalArgumentException("unsupported request snapshot")
      }
      def checkHold(label:String,valid:Bool,ready:Bool,bits:Data):Unit={
        // Normal cases have no cancel/poison. Do not misapply ordinary hold
        // rules to deliberately malformed offers and real abort cancellation.
        if(!failing){
          val now=if(b(valid))Some(snapshot(bits))else None
          heldRequests.get(label).foreach{old=>
            require(now.contains(old),s"$label changed/dropped stalled request")
            requestHoldChecks+=1;holdChecksByPort += (label -> (holdChecksByPort(label)+1))
          }
          if(b(valid) && !b(ready))heldRequests += (label -> now.get) else heldRequests -= label
        }
      }
      def target=targetToken==2 && targetHead==0
      def tileWord(row:Int,column:Int):BigInt={
        val key=column/16;val stripe=column%16
        // Inactive/off-diagonal cells are deliberately nonfinite. Only actual
        // active (row,16*key+row) stripes may influence scan/fold/retire.
        if(key>targetToken || stripe!=row)BigInt("7fc00000",16)
        else if(target && name=="ordered_add_fault_m3" && key==1 && (row==0||row==15))BigInt("7f7fffff",16)
        else if(target && name=="ordered_add_fault_m3" && key==2 && row==0)BigInt("7fc00000",16)
        else if(target && name=="ordered_scale_fault_m3" && key==1 && row==0)BigInt("00010000",16)
        else if(target && name=="ordered_scale_fault_m3" && key==2 && (row==0||row==1))BigInt("7f7fffff",16)
        else BigInt(0)
      }
      def offerTile():Unit={
        p.result.bits.context.poke(0.U);p.result.bits.last.poke(true.B);p.result.bits.error.poke(false.B)
        for(r<-0 until 16;c<-0 until 256)p.result.bits.value(r)(c).poke(tileWord(r,c).U)
      }
      def isInjection(phase:Int,selected:Int):Boolean= target && !injected && (name match {
        case "early_scan"|"foreign_scan"=>phase==1
        case "early_fold"=>phase==2
        case "early_scale"=>phase==3
        case "early_retire_first"=>phase==4 && selected==0
        case "early_retire_last"=>phase==4 && selected==2
        case _=>false
      })
      def step():Unit={
        require(cycles<cap,"100000-clock cap")
        val phase=u(d.observation.vectorPhase).toInt
        val selected=u(d.observation.selected).toInt
        val injection=isInjection(phase,selected)
        d.io.memory.ready.poke((mem.isEmpty && cycles%5!=0 && !terminal).B)
        d.io.response.valid.poke(mem.exists(_.due<=cycles).B)
        mem.foreach{x=>d.io.response.bits.tag.poke(x.tag.U);d.io.response.bits.data.poke(x.data.U);d.io.response.bits.error.poke(false.B)}
        d.io.matrixRequest.get.ready.poke((!pvPending && cycles%3!=0 && !terminal).B)
        d.io.matrixResult.get.valid.poke((pvPending && cycles>=pvDue).B)
        d.io.matrixResult.get.bits.error.poke(false.B)
        // All accepted scripted PV results are zero, consistent with zero V;
        // this is not numerical verification of a Matrix implementation.
        d.io.matrixAcceptedSteps.get.poke(physicalSteps.U)
        p.group.ready.poke((group.isEmpty && cycles%3!=0 && !terminal).B)
        p.step.ready.poke((group.nonEmpty && !resultPending && !donePending && cycles%4!=0).B)
        p.result.valid.poke(resultPending.B)
        p.done.valid.poke((donePending || injection).B)
        p.done.bits.tag.poke((if(injection&&name=="foreign_scan")group.get+1 else group.getOrElse(BigInt(0))).U)
        // Matching done keeps tag/error stable until its accepted handshake.
        // Consumer poison, not a changing external error bit, signals failure.
        p.done.bits.error.poke(false.B)
        // No in-flight endpoint work remains once our accepted eighth step has
        // been scripted; this is a stub status, NOT service-drain coverage.
        d.io.packedQkStepsDrained.get.poke((steps==8).B)
        if(injection){
          injected=true;p.done.ready.expect(false.B);d.testScoreWrite.valid.expect(false.B)
          d.observation.committed.expect(false.B);p.result.ready.expect(false.B)
          println(s"INJECT cycle=$cycles case=$name phase=$phase selected=$selected tag=${u(p.done.bits.tag)}")
        }
        val gf=fire(p.group.valid,p.group.ready);val sf=fire(p.step.valid,p.step.ready)
        val rf=fire(p.result.valid,p.result.ready);val df=fire(p.done.valid,p.done.ready)
        val mf=fire(d.io.memory.valid,d.io.memory.ready);val mr=fire(d.io.response.valid,d.io.response.ready)
        val pf=fire(d.io.matrixRequest.get.valid,d.io.matrixRequest.get.ready)
        val pr=fire(d.io.matrixResult.get.valid,d.io.matrixResult.get.ready)
        checkHold("memory",d.io.memory.valid,d.io.memory.ready,d.io.memory.bits)
        checkHold("group",p.group.valid,p.group.ready,p.group.bits)
        checkHold("step",p.step.valid,p.step.ready,p.step.bits)
        checkHold("pv",d.io.matrixRequest.get.valid,d.io.matrixRequest.get.ready,d.io.matrixRequest.get.bits)
        val jf=fire(d.io.ownerJob.get.valid,d.io.ownerJob.get.ready)
        if(jf){require(!jobAccepted);jobAccepted=true;ownerAcceptCount+=1}
        val nmem=if(mf){
          require(mem.isEmpty,"one memory debt")
          val at=u(d.io.memory.bits.address);require(at%64==0,"aligned DDR request")
          val write=b(d.io.memory.bits.write)
          if(write){require(at>=dst && at+64<=dst+m*1536*4,"output address")
            d.io.memory.bits.data.expect(0.U);d.io.memory.bits.mask.expect(((BigInt(1)<<64)-1).U)
            require(!stored(at),"duplicate output beat");stored+=at;writeBytes+=64
          }else{require(Seq((q,m*1536*4),(k,m*256*4),(v,m*256*4)).exists{case(base,n)=>at>=base && at+64<=base+n},"input address")}
          Some(MemoryReply(u(d.io.memory.bits.tag),BigInt(0),cycles+2+(cycles%3)))
        }else None
        val ng=if(gf){require(group.isEmpty);p.group.bits.opcode.expect(0x23.U);p.group.bits.sliceMask.expect(255.U)
          require(u(p.group.bits.tag)>0);Some(u(p.group.bits.tag))
        }else None
        if(sf){require(group.nonEmpty && steps<8);p.step.bits.context.expect(0.U)
          p.step.bits.clear.expect((steps==0).B);p.step.bits.last.expect((steps==7).B)
          p.step.bits.finish.expect((steps==7).B);p.step.bits.emit.expect((steps==7).B)
          for(x<-p.step.bits.a)x.expect(0.U);for(x<-p.step.bits.b)x.expect(0.U)
        }
        if(pf){d.io.matrixRequest.get.bits.opcode.expect(0x24.U);d.io.matrixRequest.get.bits.sliceMask.expect(1.U)}
        if(phase!=0){
          require(resultPending,"real held Matrix head during vector phases")
          // Once the real client enters draining it must accept the held
          // result even if the core state has not yet advanced to finish.
          if(!b(p.abort)){p.result.ready.expect(false.B);sawResultHeld=true}
          else d.testScoreWrite.valid.expect(false.B)
          d.observation.committed.expect(false.B)
          d.observation.scalarIssue.expect(false.B)
          val faults=u(d.observation.faults)
          if(target&&faults.testBit(2)&&firstFault2.isEmpty)firstFault2=Some(cycles)
          if(target&&faults.testBit(1)&&firstFault1.isEmpty)firstFault1=Some(cycles)
          println(s"OBS cycle=$cycles token=${u(d.observation.token)} head=${u(d.observation.head)} phase=$phase lane=${u(d.observation.lane)} selected=$selected faults=$faults scoreWrite=${b(d.testScoreWrite.valid)} scoreIndex=${u(d.testScoreWrite.bits.index)} scoreData=${u(d.testScoreWrite.bits.data)} max=${u(d.observation.maxScore)} resultReady=${b(p.result.ready)}")
        }
        if(b(d.testScoreWrite.valid)){
          val index=u(d.testScoreWrite.bits.index).toInt
          require(index>=0 && index<=u(d.observation.token).toInt)
          d.testScoreWrite.bits.data.expect(0.U);allWrites+=1
          if(target)targetWrites=targetWrites:+index
        }
        if(terminal)require(!gf && !sf && !rf && !df && !mf && !mr && !pf && !pr,"traffic after terminal")
        d.clock.step();cycles+=1
        if(mr){mem=None;memReturned+=1};if(mf){mem=nmem;memAccepted+=1}
        if(pr){pvPending=false;pvReturns+=1}
        if(pf){require(!pvPending);pvPending=true;pvDue=cycles+2;pvRequests+=1;physicalSteps+=1}
        if(gf){group=ng;steps=0;groups+=1;targetToken=u(d.observation.token).toInt;targetHead=u(d.observation.head).toInt}
        if(sf){steps+=1;qkAcceptedSteps+=1;physicalSteps+=8;if(steps==8){resultPending=true;offerTile()}}
        if(rf){
          resultPending=false;results+=1;donePending=true
          if(name=="foreign_scan" && injected){
            require(b(p.abort),"matching recovery follows real abort drain")
            println(s"FOREIGN_RECOVERY cycle=$cycles drained_result=true foreign_retired=false")
          }
        }
        // foreign_scan is intentionally one adversarial, non-handshaken offer,
        // NOT a legal held terminal. Withdraw it for one full cycle, drain the
        // held result through the real abort path, then offer matching done.
        if(injection && name!="foreign_scan"){donePending=true}
        if(df){donePending=false;group=None;dones+=1}
        // A selected arithmetic fault uses the real core poison/client abort.
        if(faultCase && target && b(d.io.resetRequired))injected=true
        lastVectorPhase=phase
      }
      step();d.io.ownerJob.get.ready.expect(true.B)
      val j=d.io.ownerJob.get.bits
      j.kind.poke(QwenOwnerKind.Attention.U);j.m.poke(m.U);j.n.poke(1536.U);j.k.poke(128.U)
      j.a.poke(q.U);j.b.poke(k.U);j.c.poke(v.U);j.dst.poke(dst.U)
      j.writeBytes.poke((m*1536*4).U);j.tag.poke(tag.U)
      d.io.ownerJob.get.valid.poke(true.B)
      while(!jobAccepted)step()
      d.io.ownerJob.get.valid.poke(false.B)
      while(!b(d.io.result.valid))step()
      require(mem.isEmpty && memAccepted==memReturned && !pvPending && pvRequests==pvReturns)
      require(group.isEmpty && !resultPending && !donePending && groups==dones)
      d.observation.owned.expect(false.B);d.observation.memoryDebt.expect(false.B)
      d.observation.localDebt.expect(false.B);d.observation.scalarDebt.expect(false.B)
      if(failing){
        require(injected);d.io.resetRequired.expect(true.B)
        d.io.result.bits.status.expect((if(faultCase)Status.Numerical else Status.Protocol).U)
        val expected=if(name=="early_retire_last")Vector(0,1) else if(faultCase)Vector(0) else Vector.empty[Int]
        require(targetWrites==expected,s"ordered committed prefix $targetWrites expected $expected")
        if(faultCase)require(firstFault2.nonEmpty && firstFault1.nonEmpty && firstFault2.get<firstFault1.get,"discovery order must oppose retirement order")
      }else{
        d.io.result.bits.status.expect(0.U);d.io.resetRequired.expect(false.B)
        require(groups==12*m && results==groups && qkAcceptedSteps==96*m)
        require(pvRequests==48*m*(m+1),"independent causal PV acceptance count")
        require(requestHoldChecks>0 && heldRequests.isEmpty,"normal request backpressure hold evidence")
        require(allWrites==12*m*(m+1)/2)
        require(writeBytes==m*1536*4 && stored.size==m*96)
        d.io.acknowledgedWriteBytes.expect((m*1536*4).U)
      }
      require(sawResultHeld && jobAccepted && ownerAcceptCount==1)
      terminal=true
      def resultWords=d.io.result.bits.elements.toSeq.map{case(n,x)=>(n,x.asInstanceOf[UInt].peek().litValue)}
      val held=resultWords
      for(_<-0 until 8){d.io.result.valid.expect(true.B);require(resultWords==held);step()}
      d.io.result.ready.poke(true.B);step();d.io.result.ready.poke(false.B)
      for(_<-0 until 3){d.io.result.valid.expect(false.B);step()}
      println(s"CORE_CASE_PASS case=$name m=$m cycles=$cycles groups=$groups qkAcceptedSteps=$qkAcceptedSteps accounting512Steps=${physicalSteps} results=$results dones=$dones scoreWrites=$allWrites targetPrefix=${targetWrites.mkString(",")} ownerAccepts=$ownerAcceptCount pvRequests=$pvRequests pvReturns=$pvReturns requestHoldChecks=$requestHoldChecks holdChecksByPort=${holdChecksByPort.toSeq.sorted.mkString(",")} memoryAccepted=$memAccepted memoryReturned=$memReturned outputBytes=$writeBytes numerical_matrix_verified=false")
    }
  }
}

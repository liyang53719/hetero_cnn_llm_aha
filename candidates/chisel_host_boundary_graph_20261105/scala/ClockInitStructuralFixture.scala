package chiseltest.simulator

import firrtl2.{CircuitState,Parser}
import firrtl2.ir._
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import java.io.{OutputStream,PrintStream}
import java.nio.file.{Files,Path,Paths}
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest
import treadle2.TreadleCircuitStateAnnotation
import treadle2.executable.{Symbol,SymbolTable}
import treadle2.stage.phases.{GetFirrtlAst,PrepareAst,SetImplicitOutputInfo}

/** Structural/equation fixture only. Never instantiate an execution engine. */
object ClockInitStructuralFixture {
  private def sha(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  private def hash(s:String):String=sha(s.getBytes(UTF_8))
  private def encode(x:Any):String=x match {
    case null=>"null"
    case s:Symbol=>"symbol:"+s.name
    case n:FirrtlNode=>"ir:"+n.serialize
    case s:String=>s.length+":"+s
    case n:java.lang.Number=>n.toString
    case b:Boolean=>b.toString
    case p:Product=>p.productPrefix+p.productIterator.map(encode).mkString("(",",",")")
    case _=>throw new IllegalArgumentException("unsupported fixture metadata type")
  }
  private def digestTable(t:SymbolTable):String={
    require(t.size<=4096,"small fixture symbol cap")
    val rows=Vector.newBuilder[String]
    t.symbols.toVector.sortBy(_.name).foreach{s=>
      rows+=Seq(s.name,s.dataSize.toString,s.dataType.toString,s.dataKind.toString,s.bitWidth.toString,
        s.slots.toString,s.firrtlType.serialize,s.info.serialize,s.index.toString,s.cardinalNumber.toString).map(encode).mkString("symbol:","|","")
      rows+=t.childrenOf.getEdges(s).toVector.map(_.name).sorted.map(encode).mkString("children:"+s.name+":","|","")
      rows+=t.parentsOf.getEdges(s).toVector.map(_.name).sorted.map(encode).mkString("parents:"+s.name+":","|","")
    }
    def names(label:String,x:Iterable[String]):Unit={rows+=x.toVector.sorted.map(encode).mkString(label+":","|","")}
    def pairs(label:String,x:Iterable[(Any,Any)]):Unit={rows+=x.toVector.map{case(a,b)=>encode(a)+"="+encode(b)}.sorted.mkString(label+":","|","")}
    names("orphans",t.orphans.map(_.name));names("instances",t.instanceNames);names("registers",t.registerNames)
    names("inputs",t.inputPortsNames);names("outputs",t.outputPortsNames)
    pairs("instanceModules",t.instanceNameToModuleName);pairs("registerClocks",t.registerToClock)
    pairs("stopInfo",t.stopToStopInfo);pairs("printInfo",t.printToPrintInfo);pairs("verifyInfo",t.verifyInfo)
    hash(rows.result().mkString("\n"))
  }
  private def loaded(c:Class[_],expectedLocation:String):String={
    require(Paths.get(c.getProtectionDomain.getCodeSource.getLocation.toURI).toRealPath()==Paths.get(expectedLocation).toRealPath(),"actual code source")
    val in=c.getResourceAsStream("/"+c.getName.replace('.','/')+".class")
    require(in!=null)
    try{val b=in.readAllBytes();require(b.length<=1024*1024);sha(b)}finally{in.close()}
  }
  private def source(mode:String):String={
    val print=if(mode!="stop")"    printf(clock, en, \"fixture %d\", data) @[clock_fixture_print 1:1]\n"else ""
    val stop=if(mode!="print")"    stop(clock, stop_en, 0) @[clock_fixture_stop 1:1]\n"else ""
    "circuit ClockFixture :\n  module ClockFixture :\n    input clock : Clock\n    input en : UInt<1>\n    input stop_en : UInt<1>\n    input data : UInt<8>\n    output out : UInt<1>\n    reg q : UInt<1>, clock with :\n      reset => (UInt<1>(0), UInt<1>(0))\n    q <= en\n    out <= q\n"+print+stop
  }
  private def flat(s:Statement):Vector[Statement]=s match{case Block(xs)=>xs.toVector.flatMap(flat);case x=>Vector(x)}
  private def replace(c:Circuit,f:Statement=>Statement):Circuit={
    def go(s:Statement):Statement=f(s.mapStmt(go))
    c.copy(modules=c.modules.map{case m:Module=>m.copy(body=go(m.body));case x=>x})
  }
  private def append(c:Circuit,ss:Seq[Statement]):Circuit=c.copy(modules=c.modules.map{case m:Module=>m.copy(body=Block(flat(m.body)++ss));case x=>x})
  private def check(c:Circuit):Unit={
    require(firrtl2.passes.CheckTypes.run(c) eq c)
    require(firrtl2.passes.CheckFlows.run(c) eq c)
  }
  private def originalErrors(c:Circuit,n:Int):Unit={
    val errors=try{firrtl2.passes.CheckTypes.run(c);Vector.empty[Throwable]}catch{
      case e:firrtl2.passes.PassExceptions=>e.exceptions.toVector
      case e:firrtl2.passes.PassException=>Vector(e)
    }
    require(errors.count(_.getClass.getName=="firrtl2.passes.CheckTypes$InvalidRegInit")==n)
    require(errors.forall(e=>Set("firrtl2.passes.CheckTypes$InvalidRegInit","firrtl2.passes.PassException")(e.getClass.getName)))
    require(errors.size==n+(if(n>1)1 else 0))
  }
  private def unchanged(a:Circuit,b:Circuit,n:Int):Unit={
    require(a.main==b.main && a.info==b.info && a.modules.size==b.modules.size)
    var changed=0
    def stmts(x:Statement,y:Statement):Unit=(x,y)match{
      case (p:Block,q:Block)=>require(p.stmts.size==q.stmts.size);p.stmts.zip(q.stmts).foreach{case(l,r)=>stmts(l,r)}
      case (p:DefRegister,q:DefRegister)if p!=q=>
        require(p.tpe==ClockType && p.copy(init=q.init)==q)
        q.init match{case DoPrim(firrtl2.PrimOps.AsClock,Seq(v),cs,ClockType)=>require(cs.isEmpty && (v eq p.init));case _=>require(false)}
        changed+=1
      case _=>require(x eq y)
    }
    a.modules.zip(b.modules).foreach{
      case (p:Module,q:Module)=>require(p.copy(body=q.body)==q);stmts(p.body,q.body)
      case (p,q)=>require(p eq q)
    }
    require(changed==n)
  }
  // Independent equations, not an interpreter or scheduler execution claim.
  // For a literal-false nonasync reset, init is absent from the state recurrence.
  private def equations():Int={
    var vectors=0
    for(initial<-0 to 1;clocks<-0 until 16;enables<-0 until 16){
      var oldState=initial;var newState=initial;var previous=0
      for(i<-0 until 4){
        val clock=(clocks>>i)&1;val enabled=(enables>>i)&1
        val edge=previous==0 && clock==1
        val originalNext=if(edge)clock else oldState
        val correctedNext=if(edge)clock else newState
        require(originalNext==correctedNext && ((oldState&enabled)==(newState&enabled)))
        oldState=originalNext;newState=correctedNext;previous=clock
      }
      require(oldState==newState);vectors+=1
    }
    require(vectors==512);vectors
  }
  private def negative(before:Circuit,prepared:Circuit,annotations:firrtl2.AnnotationSeq):Int={
    val regs=prepared.modules.collect{case m:Module=>flat(m.body).collect{case r:DefRegister if r.tpe==ClockType=>r}}.flatten
    require(regs.size==2);val r=regs.head
    val ref=Reference(r.name,ClockType,firrtl2.NodeKind,firrtl2.SourceFlow)
    val sinkRef=ref.copy(flow=firrtl2.SinkFlow)
    def badReg(f:DefRegister=>DefRegister)=replace(prepared,{case x:DefRegister if x.name==r.name=>f(x);case x=>x})
    val driver=prepared.modules.collect{case m:Module=>flat(m.body).collect{case c:Connect if c.loc==sinkRef=>c}}.flatten
    require(driver.size==1)
    val consumer=prepared.modules.collect{case m:Module=>flat(m.body).collect{case p:Print if p.clk==ref=>p;case p:Stop if p.clk==ref=>p}}.flatten
    require(consumer.size==1)
    val zero=UIntLiteral(0,IntWidth(1));val one=UIntLiteral(1,IntWidth(1))
    def withSink(kind:firrtl2.Kind,flow:firrtl2.Flow):Circuit=replace(prepared,{
      case c:Connect if c.loc==sinkRef=>c.copy(loc=sinkRef.copy(kind=kind,flow=flow));case x=>x})
    def withConsumer(kind:firrtl2.Kind,flow:firrtl2.Flow):Circuit=replace(prepared,{
      case p:Print if p.clk==ref=>p.copy(clk=ref.copy(kind=kind,flow=flow))
      case p:Stop if p.clk==ref=>p.copy(clk=ref.copy(kind=kind,flow=flow));case x=>x})
    val mutations=Vector[(Circuit,Circuit,firrtl2.AnnotationSeq)](
      (before,withSink(firrtl2.NodeKind,firrtl2.SourceFlow),annotations),
      (before,withSink(firrtl2.NodeKind,firrtl2.UnknownFlow),annotations),
      (before,withSink(firrtl2.RegKind,firrtl2.SinkFlow),annotations),
      (before,withConsumer(firrtl2.NodeKind,firrtl2.SinkFlow),annotations),
      (before,withConsumer(firrtl2.NodeKind,firrtl2.UnknownFlow),annotations),
      (before,withConsumer(firrtl2.RegKind,firrtl2.SourceFlow),annotations),
      (before,badReg(_.copy(init=one)),annotations),
      (before,badReg(_.copy(init=SIntLiteral(0,IntWidth(1)))),annotations),
      (before,append(badReg(_.copy(clock=Reference("alias_clock",ClockType,firrtl2.NodeKind,firrtl2.SourceFlow))),Seq(DefNode(NoInfo,"alias_clock",r.clock))),annotations),
      (before,prepared,annotations:+firrtl2.annotations.PresetRegAnnotation(firrtl2.annotations.CircuitTarget(prepared.main).module(prepared.main).ref(r.name))),
      (before,badReg(_.copy(reset=one)),annotations),
      (before,badReg(_.copy(reset=DoPrim(firrtl2.PrimOps.AsAsyncReset,Seq(zero),Seq.empty,AsyncResetType))),annotations),
      (before,badReg(_.copy(tpe=SIntType(IntWidth(1)))),annotations),
      (before,badReg(_.copy(tpe=UnknownType)),annotations),
      (before,badReg(_.copy(init=UIntLiteral(0,IntWidth(2)))),annotations),
      (before,badReg(_.copy(reset=UIntLiteral(0,IntWidth(0)))),annotations),
      (append(before,Seq(DefWire(NoInfo,r.name,ClockType))),prepared,annotations),
      (before,append(prepared,driver),annotations),
      (before,replace(prepared,{case c:Connect if c.loc==sinkRef=>EmptyStmt;case x=>x}),annotations),
      (before,replace(prepared,{case c:Connect if c.loc==sinkRef=>c.copy(expr=DoPrim(firrtl2.PrimOps.AsClock,Seq(zero),Seq.empty,ClockType));case x=>x}),annotations),
      (before,append(prepared,consumer),annotations),
      (before,append(prepared,Seq(DefNode(NoInfo,"unexpected_alias",ref))),annotations),
      (before,badReg(_.copy(info=NoInfo)),annotations),
      (before,replace(prepared,{case c:Connect if c.loc==sinkRef=>c.copy(info=FileInfo("different"));case x=>x}),annotations),
      (replace(before,{case _:Print=>EmptyStmt;case _:Stop=>EmptyStmt;case x=>x}),prepared,annotations),
      (append(before,before.modules.collect{case m:Module=>flat(m.body).collect{case p:Print=>p;case p:Stop=>p}}.flatten),prepared,annotations),
      (before,append(prepared,Seq(DefRegister(NoInfo,"other_mismatch",SIntType(IntWidth(1)),r.clock,zero,zero))),annotations)
    )
    mutations.zipWithIndex.foreach{case((b,p,a),index)=>
      var rejected=false
      try{ClockInitRepresentationRepair(b,p,a,2)}catch{case e:IllegalArgumentException=>
        val code=ClockInitRepresentationRepair.guardCode(e)
        rejected=if(index<3)code=="DRIVER"else if(index<6)code=="CONSUMER"else ClockInitRepresentationRepair.GuardCodes(code)
      }
      require(rejected,"exact repair guard rejection")
    }
    mutations.size
  }
  private def driverDiagnostics():Int={
    // Hand-authored metadata shapes test the formatter before the real fixture
    // can reject; these never replace or normalize the actual prepared circuit.
    val inf=FileInfo("driver_diagnostic_synthetic")
    val clock=Reference("clock",ClockType,firrtl2.PortKind,firrtl2.SourceFlow)
    val zero=UIntLiteral(0,IntWidth(1))
    val r=DefRegister(inf,"delay",ClockType,clock,zero,zero)
    val delayed=Reference(r.name,ClockType,firrtl2.NodeKind,firrtl2.SourceFlow)
    val print=Print(inf,StringLit("synthetic"),Seq.empty,clock,zero)
    val ports=Seq(Port(NoInfo,"clock",Input,ClockType))
    def circuit(body:Statement)=Circuit(NoInfo,Seq(Module(NoInfo,"Diagnostic",ports,body)),"Diagnostic")
    val before=circuit(print)
    val prepared=circuit(Block(Seq(r,Connect(inf,delayed.copy(flow=firrtl2.SinkFlow),clock),print.copy(clk=delayed))))
    val annotations=Seq.empty[firrtl2.annotations.Annotation];val n=1
    require(ClockInitRepresentationRepair(before,prepared,annotations,n).corrected==1)
    val name=r.name
    def sinkChange(c:Connect):Connect=c.loc match {
      case x:Reference if x.name==name=>c.copy(loc=x.copy(flow=firrtl2.SourceFlow))
      case _=>c
    }
    val sink=replace(prepared,{case c:Connect=>sinkChange(c);case x=>x})
    val rhs=replace(prepared,{
      case c:Connect if c.loc.isInstanceOf[Reference] && c.loc.asInstanceOf[Reference].name==name=>
        c.expr match{case x:Reference=>c.copy(expr=x.copy(flow=firrtl2.UnknownFlow));case _=>throw new IllegalArgumentException("synthetic clock reference")}
      case x=>x
    })
    val consumer=replace(sink,{
      case p:Print if p.clk.isInstanceOf[Reference] && p.clk.asInstanceOf[Reference].name==name=>p.copy(clk=p.clk.asInstanceOf[Reference].copy(kind=firrtl2.RegKind))
      case p:Stop if p.clk.isInstanceOf[Reference] && p.clk.asInstanceOf[Reference].name==name=>p.copy(clk=p.clk.asInstanceOf[Reference].copy(kind=firrtl2.RegKind))
      case x=>x
    })
    val cases=Vector(
      sink->"SELECT:ONE:CLOCK:NODE:SOURCE:TRUE:TRUE:TRUE:TRUE:ONE:CLOCK:NODE:SOURCE",
      rhs->"RHS:ONE:CLOCK:NODE:SINK:TRUE:TRUE:TRUE:FALSE:ONE:CLOCK:NODE:SOURCE",
      consumer->"SELECT:ONE:CLOCK:NODE:SOURCE:TRUE:TRUE:TRUE:TRUE:ONE:CLOCK:REG:SOURCE")
    cases.foreach{case(c,expected)=>
      var error:Option[IllegalArgumentException]=None
      try{ClockInitRepresentationRepair(before,c,annotations,n)}catch{case e:IllegalArgumentException=>error=Some(e)}
      require(error.nonEmpty && error.get.getClass==classOf[IllegalArgumentException])
      require(ClockInitRepresentationRepair.guardCode(error.get)=="DRIVER")
      require(ClockInitRepresentationRepair.driverEvidence(error.get)==expected)
      error.get.addSuppressed(new IllegalArgumentException("synthetic duplicate"))
      require(ClockInitRepresentationRepair.driverEvidence(error.get)=="UNAVAILABLE")
    }
    require(ClockInitRepresentationRepair.driverEvidence(new IllegalArgumentException("DRIVER"))=="UNAVAILABLE")
    require(ClockInitRepresentationRepair.driverEvidence(new IllegalArgumentException("SHAPE"))=="NONE")
    cases.size
  }
  private def cycle(c:Circuit):Circuit={
    val u=UIntType(IntWidth(1));def ref(n:String,flow:firrtl2.Flow)=Reference(n,u,firrtl2.WireKind,flow)
    val a="fixture_cycle_a";val b="fixture_cycle_b"
    append(c,Seq(DefWire(NoInfo,a,u),DefWire(NoInfo,b,u),Connect(NoInfo,ref(a,firrtl2.SinkFlow),ref(b,firrtl2.SourceFlow)),Connect(NoInfo,ref(b,firrtl2.SinkFlow),ref(a,firrtl2.SourceFlow))))
  }
  def main(args:Array[String]):Unit={
    val out=System.out;val err=System.err;val muted=new PrintStream(OutputStream.nullOutputStream())
    var ok=false;var rows=Vector.empty[String];var target:Option[Path]=None;var phase="IDENTITY"
    try{
      require(args.length==6 && Set("official","cached")(args(0)))
      require(loaded(classOf[SymbolTable],args(3))==args(1) && loaded(SymbolTable.getClass,args(3))==args(2))
      require(loaded(ClockInitRepresentationRepair.getClass,args(5))==args(4))
      val base=Paths.get(".").toAbsolutePath.normalize();val abs=Files.createTempDirectory(base,"clock-init-fixture-");val rel=base.relativize(abs)
      require(abs.getParent==base && !rel.isAbsolute && rel.getNameCount==1 && rel.normalize()==rel && rel.toString!="." && rel.toString!="..");target=Some(rel)
      System.setOut(muted);System.setErr(muted)
      Console.withOut(muted){Console.withErr(muted){
        rows=Vector("print","stop","both").map{mode=>
          phase="LOWER"
          val low=Compiler.toLowFirrtl(CircuitState(Parser.parse(source(mode)),Seq(TargetDirAnnotation(rel.toString)))).circuit
          check(low)
          phase="PREPARE"
          val anns=Seq(FirrtlCircuitAnnotation(low),TargetDirAnnotation(rel.toString))
          val prepared=(new PrepareAst).transform(SetImplicitOutputInfo.transform(GetFirrtlAst.transform(anns)))
          val states=prepared.collect{case TreadleCircuitStateAnnotation(s)=>s};require(states.size==1)
          val state=states.head;val n=if(mode=="both")2 else 1
          phase="ORIGINAL_ERRORS";originalErrors(state.circuit,n)
          phase="NEGATIVE";val driverChecks=driverDiagnostics();require(driverChecks==3)
          val boundChecks=ClockInitRepresentationRepair.boundDiagnosticSelfChecks();require(boundChecks==9)
          phase="REPAIR"
          val fixed=ClockInitRepresentationRepair(low,state.circuit,state.annotations,n)
          require(fixed.corrected==n);unchanged(state.circuit,fixed.circuit,n)
          phase="VALIDATE";check(fixed.circuit)
          // Force nested/empty structure regardless of official pass flattening.
          val nested=state.circuit.copy(modules=state.circuit.modules.map{
            case m:Module=>m.copy(body=Block(Seq(EmptyStmt,Block(Seq(m.body,EmptyStmt)),EmptyStmt)))
            case x=>x
          })
          phase="REPAIR"
          val nestedFixed=ClockInitRepresentationRepair(low,nested,state.annotations,n)
          phase="VALIDATE"
          require(nestedFixed.corrected==n);unchanged(nested,nestedFixed.circuit,n);check(nestedFixed.circuit)
          phase="NEGATIVE";val guards=if(mode=="both")negative(low,state.circuit,state.annotations)else 0
          phase="GRAPH"
          val oldTable=SymbolTable(state.circuit,Seq.empty,allowCycles=false);val newTable=SymbolTable(fixed.circuit,Seq.empty,allowCycles=false)
          val digest=digestTable(oldTable);require(digest==digestTable(newTable))
          require(digest==digestTable(SymbolTable(nestedFixed.circuit,Seq.empty,allowCycles=false)))
          if(mode=="both"){
            val cyc=cycle(state.circuit)
            val fixedCycle=ClockInitRepresentationRepair(low,cyc,state.annotations,2).circuit
            unchanged(cyc,fixedCycle,2);check(fixedCycle)
            Vector(cyc,fixedCycle).foreach{x=>
              var seen=false;try{SymbolTable(x,Seq.empty,allowCycles=false)}catch{case _:firrtl2.graph.CyclicException=>seen=true};require(seen)
            }
          }
          phase="EQUATIONS";val vectors=equations()
          "CLOCK_INIT_CASE_V1 id="+mode+" corrected="+n+" negativeGuards="+guards+" equations="+vectors+" shapeChecks=1 driverChecks=3 boundChecks=9 graphDigest="+digest
        }
        ok=true
      }}
    }catch{case e:Throwable=>rows=Vector("CLOCK_INIT_FAILURE_V1 phase="+phase+" guard="+(if(phase=="REPAIR")ClockInitRepresentationRepair.guardCode(e)else "NONE")+" driver="+(if(phase=="REPAIR")ClockInitRepresentationRepair.driverEvidence(e)else "NONE")+" exceptionClassSha="+hash(e.getClass.getName))}
    finally{
      System.setOut(out);System.setErr(err)
      try{target.foreach{dir=>val stream=Files.walk(dir);val xs=try{val it=stream.iterator();val b=Vector.newBuilder[Path];var n=0;while(it.hasNext && n<257){b+=it.next();n+=1};require(n<=256 && !it.hasNext);b.result()}finally{stream.close()};xs.sortBy(p=> -p.getNameCount).foreach(Files.delete(_))}}
      catch{case e:Throwable=>ok=false;rows=Vector("CLOCK_INIT_FAILURE_V1 phase=CLEANUP guard=NONE driver=NONE exceptionClassSha="+hash(e.getClass.getName))}
      muted.close()
    }
    rows.foreach(out.println)
    out.println("CLOCK_INIT_RUN_V1 label="+args.headOption.filter(Set("official","cached")).getOrElse("invalid")+" pass="+ok+" cases="+(if(ok)3 else 0)+" numericalPass=false interpreterExecuted=false fullHostAccepted=false")
    if(!ok)System.exit(2)
  }
}

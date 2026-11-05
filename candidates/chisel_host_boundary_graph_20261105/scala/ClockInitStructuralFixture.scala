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
  // Tiny differential oracle only. Production input never enters this fixture.
  // Compare tree shape/metadata as well as the existing per-input identity proof.
  private def sameCorrection(a:Circuit,b:Circuit):Unit={
    require(a.info==b.info && a.main==b.main && a.modules.size==b.modules.size)
    def statements(x:Statement,y:Statement):Unit=(x,y) match {
      case (p:Block,q:Block)=>
        require(p.stmts.size==q.stmts.size)
        p.stmts.zip(q.stmts).foreach{case(l,r)=>statements(l,r)}
      case (p:DefRegister,q:DefRegister)=>require(p==q)
      case _=>require(x eq y)
    }
    a.modules.zip(b.modules).foreach{
      case (p:Module,q:Module)=>require(p.copy(body=q.body)==q);statements(p.body,q.body)
      case (p,q)=>require(p eq q)
    }
  }
  private def differentialChecks(before:Circuit,prepared:Circuit,annotations:firrtl2.AnnotationSeq,n:Int):Int={
    var checks=0
    def repaired(input:Circuit):(Circuit,Circuit)={
      val legacy=LegacyRepairOracle(before,input,annotations,n)
      val current=ClockInitRepresentationRepair(before,input,annotations,n)
      require(legacy.corrected==n && current.corrected==n)
      unchanged(input,legacy.circuit,n);unchanged(input,current.circuit,n)
      sameCorrection(legacy.circuit,current.circuit)
      require(legacy.proofTicks==current.noninterferenceTicks && legacy.proofTicks>0)
      (legacy.circuit,current.circuit)
    }
    def accepted(input:Circuit):Unit={
      val (legacy,current)=repaired(input)
      check(legacy);check(current)
      require(digestTable(SymbolTable(legacy,Seq.empty,allowCycles=false))==
        digestTable(SymbolTable(current,Seq.empty,allowCycles=false)))
      checks+=1
    }
    def forwardReferences(input:Circuit):Unit={
      val (legacy,current)=repaired(input)
      // CheckTypes is structural; CheckFlows populates its declaration map in
      // statement order. Repair must preserve, not legitimize, invalid order.
      def rejectsFlow(c:Circuit):Unit={
        require(firrtl2.passes.CheckTypes.run(c) eq c)
        var rejected=false
        try{firrtl2.passes.CheckFlows.run(c)}catch{case _:NoSuchElementException=>rejected=true}
        require(rejected,"forward declaration order remains invalid")
      }
      rejectsFlow(legacy);rejectsFlow(current)
      checks+=1
    }
    def body(f:Statement=>Statement):Circuit=prepared.copy(modules=prepared.modules.map{
      case m:Module=>m.copy(body=f(m.body));case m=>m
    })
    accepted(prepared)
    accepted(body(s=>Block(Seq(EmptyStmt,Block(Seq(s,EmptyStmt)),EmptyStmt))))
    // Forward references: declaration traversal order must not supply authority.
    forwardReferences(body(s=>Block(flat(s).reverse)))
    // A changed broad Block retains all untouched siblings and empty structure.
    accepted(body(s=>Block(Vector.fill(512)(EmptyStmt)++Vector(s,Block(Seq.empty),EmptyStmt))))
    // Actual register feedback is a state boundary, not a combinational cycle.
    val feedback=replace(prepared,{
      case c:Connect=>c.loc match {
        case r:Reference if r.name=="q"=>c.copy(expr=r.copy(flow=firrtl2.SourceFlow))
        case _=>c
      }
      case x=>x
    })
    require(feedback!=prepared)
    accepted(feedback)
    def rejected(b:Circuit,p:Circuit,expected:String):Unit={
      def code(f:()=>Unit):String=try{f();"ACCEPTED"}catch{
        case e:IllegalArgumentException=>ClockInitRepresentationRepair.guardCode(e)
      }
      require(code(()=>{LegacyRepairOracle(b,p,annotations,n);()})==expected)
      require(code(()=>{ClockInitRepresentationRepair(b,p,annotations,n);()})==expected)
      checks+=1
    }
    // A duplicate in an unrelated module still rejects globally, including a
    // distinct String identity with equal contents late in that namespace.
    val name=new String(Array('u','n','r','e','l','a','t','e','d'))
    val equalName=new String(name.toCharArray);require(!(name eq equalName) && name==equalName)
    val unrelated=Module(NoInfo,"Unrelated",Seq.empty,Block(Seq(
      DefWire(NoInfo,name,UIntType(IntWidth(1))),EmptyStmt,
      DefWire(NoInfo,equalName,UIntType(IntWidth(1))))))
    rejected(before.copy(modules=before.modules:+unrelated),prepared,"DUPLICATE")
    rejected(before,prepared.copy(modules=prepared.modules:+unrelated),"DUPLICATE")
    require(checks==7);checks
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
          val sizingChecks=ClockInitRepresentationRepair.sizingSelfChecks();require(sizingChecks==13)
          val differential=differentialChecks(low,state.circuit,state.annotations,n);require(differential==7)
          val streamingChecks=ClockInitRepresentationRepair.streamingSelfChecks();require(streamingChecks==62)
          val preexistingChecks=ClockInitRepresentationRepair.preexistingSelfChecks();require(preexistingChecks==24)
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
          "CLOCK_INIT_CASE_V1 id="+mode+" corrected="+n+" negativeGuards="+guards+" equations="+vectors+" shapeChecks=1 driverChecks=3 boundChecks=9 sizingChecks=13 streamingChecks=62 differentialChecks=7 preexistingChecks=24 graphDigest="+digest
        }
        ok=true
      }}
    }catch{case e:Throwable=>rows=Vector("CLOCK_INIT_FAILURE_V1 phase="+phase+" guard="+(if(phase=="REPAIR")ClockInitRepresentationRepair.guardCode(e)else "NONE")+" driver="+(if(phase=="REPAIR")ClockInitRepresentationRepair.driverEvidence(e)else "NONE")+" aux="+(if(phase=="REPAIR")ClockInitRepresentationRepair.auxiliaryEvidence(e)else "NONE")+" preexisting="+(if(phase=="REPAIR")ClockInitRepresentationRepair.preexistingEvidence(e)else "NONE")+" exceptionClassSha="+hash(e.getClass.getName))}
    finally{
      System.setOut(out);System.setErr(err)
      try{target.foreach{dir=>val stream=Files.walk(dir);val xs=try{val it=stream.iterator();val b=Vector.newBuilder[Path];var n=0;while(it.hasNext && n<257){b+=it.next();n+=1};require(n<=256 && !it.hasNext);b.result()}finally{stream.close()};xs.sortBy(p=> -p.getNameCount).foreach(Files.delete(_))}}
      catch{case e:Throwable=>ok=false;rows=Vector("CLOCK_INIT_FAILURE_V1 phase=CLEANUP guard=NONE driver=NONE aux=NONE preexisting=NONE exceptionClassSha="+hash(e.getClass.getName))}
      muted.close()
    }
    rows.foreach(out.println)
    out.println("CLOCK_INIT_RUN_V1 label="+args.headOption.filter(Set("official","cached")).getOrElse("invalid")+" pass="+ok+" cases="+(if(ok)3 else 0)+" numericalPass=false interpreterExecuted=false fullHostAccepted=false")
    if(!ok)System.exit(2)
  }

  // BEGIN FROZEN LEGACY REPAIR ORACLE
  private object LegacyRepairOracle {
    import firrtl2.{AnnotationSeq,NodeKind,PortKind,SourceFlow}
    import firrtl2.annotations._
    // The frozen legacy oracle is inaccessible outside the tiny fixture.
    private def tinyOnly(before:Circuit,prepared:Circuit,expected:Int):Unit={
      require(expected>0 && expected<=16)
      var visits=0;var queued=0
      Seq(before,prepared).foreach{c=>
        require(c.modules.size<=8)
        c.modules.foreach{m=>
          require(m.ports.size<=64)
          m match {
            case mm:Module=>
              queued+=1;require(queued<=4096)
              var pending=List((mm.body,0))
              while(pending.nonEmpty){
                val (statement,depth)=pending.head;pending=pending.tail
                visits+=1;require(visits<=4096 && depth<=256)
                statement.foreachStmt{s=>queued+=1;require(queued<=4096);pending=(s,depth+1)::pending}
              }
            case _:ExtModule=>()
            case _=>require(false)
          }
        }
      }
    }
  
    final case class Result(circuit:Circuit,corrected:Int,proofTicks:Int)
    val GuardCodes:Set[String]=Set("BOUND","TYPE","INFO","STRUCTURE","DUPLICATE","COUNT","SHAPE",
      "ORIGINAL_MODULE","PREEXISTING","CLOCK","ANNOTATION_TARGET","ANNOTATION_SHAPE",
      "ANNOTATION_PRESET","ANNOTATION_EXTENSION","REFERENCES","DRIVER","CONSUMER","ANCHOR","NONINTERFERENCE")
    def guardCode(error:Throwable):String={
      if(error==null || error.getClass!=classOf[IllegalArgumentException])"UNKNOWN"
      else {val message=error.getMessage;if(message!=null && message.length<=64 && GuardCodes(message))message else "UNKNOWN"}
    }
    // Failure-only finite evidence attached to the original exception, never AST.
    private final class DriverEvidence(val code:String) extends RuntimeException(null,null,false,false)
    def driverEvidence(error:Throwable):String={
      if(error==null || guardCode(error)!="DRIVER")"NONE"
      else {
        val entries=error.getSuppressed
        if(entries.length!=1)"UNAVAILABLE"else entries.head match{case e:DriverEvidence=>e.code;case _=>"UNAVAILABLE"}
      }
    }
    private def driverFail(step:String,found:Vector[Use],clock:Reference):Nothing={
      val error=new IllegalArgumentException("DRIVER")
      val evidence=try{
        def count(n:Int):String=if(n==0)"ZERO"else if(n==1)"ONE"else "MANY"
        def kind(r:Reference):String=r.kind match {
          case firrtl2.NodeKind=>"NODE";case firrtl2.RegKind=>"REG";case firrtl2.PortKind=>"PORT";case _=>"OTHER"
        }
        def flow(r:Reference):String=r.flow match {
          case firrtl2.SourceFlow=>"SOURCE";case firrtl2.SinkFlow=>"SINK";case firrtl2.DuplexFlow=>"DUPLEX"
          case firrtl2.UnknownFlow=>"UNKNOWN";case _=>"OTHER"
        }
        def metadata(e:Option[Expression]):Vector[String]=e match {
          case Some(r:Reference)=>Vector(if(r.tpe==ClockType)"CLOCK"else "OTHER",kind(r),flow(r))
          case _=>Vector("NA","NA","NA")
        }
        def bool(v:Boolean):String=if(v)"TRUE"else "FALSE"
        val raw=found.collect{case Use(x:Connect,root,true) if root eq x.loc=>x}
        val sink=if(raw.size==1)Some(raw.head.loc)else None
        val rhs=if(raw.size==1)Some(raw.head.expr)else None
        val equals=rhs match {
          case Some(r:Reference)=>Vector(bool(r.name==clock.name),bool(r.tpe==clock.tpe),bool(r.kind==clock.kind),bool(r.flow==clock.flow))
          case _=>Vector.fill(4)("NA")
        }
        val consumers=found.collect{
          case Use(x:Print,root,true) if root eq x.clk=>x.clk
          case Use(x:Stop,root,true) if root eq x.clk=>x.clk
        }
        val consumer=if(consumers.size==1)Some(consumers.head)else None
        (Vector(step,count(raw.size))++metadata(sink)++equals++Vector(count(consumers.size))++metadata(consumer)).mkString(":")
      }catch{case _:Throwable=>"UNAVAILABLE"}
      error.addSuppressed(new DriverEvidence(evidence));throw error
    }
    private def fail(code:String):Nothing=throw new IllegalArgumentException(code)
    private def need(p:Boolean,code:String):Unit=if(!p)fail(code)
    private final class BoundEvidence(val code:String) extends RuntimeException(null,null,false,false)
    def boundEvidence(error:Throwable):String={
      if(error==null || guardCode(error)!="BOUND")"NONE"
      else {
        val entries=error.getSuppressed
        if(entries.length!=1)"UNAVAILABLE"else entries.head match{case e:BoundEvidence=>e.code;case _=>"UNAVAILABLE"}
      }
    }
    private final class Budget {
      private var n=0
      var proofTicks=0
      var phase="INDEX_BEFORE"
      def bound(p:Boolean,reason:String):Unit=if(!p){
        val error=new IllegalArgumentException("BOUND")
        error.addSuppressed(new BoundEvidence(reason+":"+phase+":"+n));throw error
      }
      def tick():Unit={if(phase=="NONINTERFERENCE")proofTicks+=1;n+=1;bound(n<=5000000,"GLOBAL_WORK")}
      def name(s:String):Unit=bound(s!=null && s.nonEmpty && s.length<=4096,"NAME")
    }
    private def boundedType(t:Type,b:Budget):Unit={
      var stack=List((t,0));var count=0
      while(stack.nonEmpty){
        val (x,d)=stack.head;stack=stack.tail;b.tick();count+=1
        b.bound(d<=64,"TYPE_DEPTH");b.bound(count<=4096,"TYPE_NODES")
        x match {
          case VectorType(a,n)=>need(n>=0,"TYPE");stack=(a,d+1)::stack
          case BundleType(fs)=>b.bound(fs.size<=4096,"TYPE_FIELDS");fs.foreach{f=>b.name(f.name);stack=(f.tpe,d+1)::stack}
          case _=>()
        }
      }
    }
    private def isMismatch(r:DefRegister,b:Budget):Boolean=r.tpe match {
      case AnalogType(_)=>false // Exact preceding CheckTypes branch.
      case _=>boundedType(r.tpe,b);boundedType(r.init.tpe,b)
        firrtl2.WrappedType.wt(r.tpe)!=firrtl2.WrappedType.wt(r.init.tpe)
    }
    private def checkedInfo(info:Info,b:Budget):Boolean={
      var stack=List((info,0));var count=0;var present=false
      while(stack.nonEmpty){
        val (x,d)=stack.head;stack=stack.tail;b.tick();count+=1
        b.bound(d<=16,"INFO_DEPTH");b.bound(count<=256,"INFO_NODES")
        x match {
          case NoInfo=>()
          case FileInfo(s)=>b.bound(s.length<=4096,"INFO_STRING");if(s.nonEmpty)present=true
          case MultiInfo(xs)=>b.bound(xs.size<=64,"INFO_CHILDREN");xs.foreach(i=>stack=(i,d+1)::stack)
          case _=>fail("INFO")
        }
      }
      present
    }
    private def sameInfo(a:Info,b:Info,budget:Budget):Boolean={
      val pa=checkedInfo(a,budget);val pb=checkedInfo(b,budget)
      pa && pb && a==b
    }
    private def isZero(e:Expression):Boolean=e match {
      case UIntLiteral(v,IntWidth(w))=>v==0 && w==1
      case _=>false
    }
    private def clockRef(e:Expression):Option[Reference]=e match {
      case r@Reference(_,ClockType,PortKind,SourceFlow)=>Some(r)
      case _=>None
    }
    private def delayedRef(e:Expression,n:String):Boolean=e match {
      case Reference(name,ClockType,NodeKind,SourceFlow)=>name==n
      case _=>false
    }
    private def delayedSink(e:Expression,n:String):Boolean=e match {
      case Reference(name,ClockType,NodeKind,firrtl2.SinkFlow)=>name==n
      case _=>false
    }
    private final case class Index(module:DefModule,names:Set[String],ports:Map[String,Port],statements:Vector[Statement])
    private def index(c:Circuit,b:Budget):Map[String,Index]={
      b.name(c.main);b.bound(c.modules.size<=4096,"MODULES")
      val out=scala.collection.mutable.HashMap.empty[String,Index]
      c.modules.foreach{m=>
        b.tick();b.name(m.name);need(!out.contains(m.name),"DUPLICATE")
        val names=scala.collection.mutable.HashSet.empty[String]
        val ports=scala.collection.mutable.HashMap.empty[String,Port]
        b.bound(m.ports.size<=250000,"PORTS")
        m.ports.foreach{p=>b.tick();b.name(p.name);need(names.add(p.name),"DUPLICATE");ports(p.name)=p}
        val ss=Vector.newBuilder[Statement]
        m match {
          case mm:Module=>
            var stack=List((mm.body,0))
            while(stack.nonEmpty){
              val (s,d)=stack.head;stack=stack.tail;b.tick();b.bound(d<=256,"STATEMENT_DEPTH");ss+=s
              s match {
                // Unnamed instrumentation carries no referenceable symbol. Keep
                // its statement for anchor matching; never excuse empty state names.
                case p:Print if p.name.isEmpty=>()
                case p:Stop if p.name.isEmpty=>()
                case p:Verification if p.name.isEmpty=>()
                case decl:IsDeclaration=>b.name(decl.name);need(names.add(decl.name),"DUPLICATE")
                case _=>()
              }
              b.bound(names.size<=250000,"DECLARATIONS")
              s.foreachStmt{x=>b.tick();stack=(x,d+1)::stack}
            }
          case _:ExtModule=>()
          case _=>fail("STRUCTURE")
        }
        out(m.name)=Index(m,names.toSet,ports.toMap,ss.result())
      }
      out.toMap
    }
    private final case class Candidate(module:String,reg:DefRegister,clock:Reference)
    private final case class Use(statement:Statement,root:Expression,direct:Boolean)
    private final case class AnchorKey(module:String,print:Boolean,clock:String,info:Info,format:String,ret:Int)
    private def anchorKey(module:String,s:Statement,b:Budget):Option[AnchorKey]=s match {
      case p:Print=>
        b.bound(p.string.string.length<=4096,"PRINT_STRING")
        clockRef(p.clk).filter(_=>checkedInfo(p.info,b)).map(c=>AnchorKey(module,true,c.name,p.info,p.string.string,0))
      case p:Stop=>clockRef(p.clk).filter(_=>checkedInfo(p.info,b)).map(c=>AnchorKey(module,false,c.name,p.info,"",p.ret))
      case _=>None
    }
  
  
    private def checkAnnotations(as:AnnotationSeq,selected:Set[(String,String)],circuit:String,b:Budget):Unit={
      b.bound(as.size<=100000,"ANNOTATIONS")
      def target(t:Target):Unit={
        b.tick()
        t match {
          case r:ReferenceTarget=>
            b.name(r.circuit);b.name(r.module);b.name(r.ref)
            b.bound(r.path.size<=64,"TARGET_PATH");b.bound(r.component.size<=64,"TARGET_COMPONENT")
            r.path.foreach{case(i,m)=>b.name(i.value);b.name(m.value)}
            // Any component of the register, including init/reset/clock, is excluded.
            val module=if(r.path.isEmpty)r.module else r.path.last._2.value
            need(!(r.circuit==circuit && selected((module,r.ref))),"ANNOTATION_TARGET")
            r.component.foreach{
              case TargetToken.Field(s)=>b.name(s)
              case TargetToken.Index(i)=>need(i>=0,"ANNOTATION_SHAPE")
              case TargetToken.Init | TargetToken.Reset | TargetToken.Clock=>()
              case _=>fail("ANNOTATION_SHAPE")
            }
          case c:CircuitTarget=>b.name(c.circuit);need(c.circuit!=circuit,"ANNOTATION_SHAPE")
          case m:ModuleTarget=>b.name(m.circuit);b.name(m.module)
            need(!(m.circuit==circuit && selected.exists(_._1==m.module)),"ANNOTATION_SHAPE")
          case _:InstanceTarget=>fail("ANNOTATION_SHAPE")
          case _=>fail("ANNOTATION_SHAPE")
        }
      }
      def named(n:Named):Unit=n match {
        case t:Target=>target(t)
        case c:ComponentName=>b.name(c.name);b.name(c.module.name);b.name(c.module.circuit.name);target(c.toTarget)
        case m:ModuleName=>b.name(m.name);b.name(m.circuit.name);target(m.toTarget)
        case c:CircuitName=>b.name(c.name);target(c.toTarget)
        case _=>fail("ANNOTATION_SHAPE")
      }
      as.foreach{a=>b.tick();a match {
        // Exclude preset propagation and custom AST-observing data-store plugins.
        case _:PresetAnnotation | _:PresetRegAnnotation=>fail("ANNOTATION_PRESET")
        case _:treadle2.DataStorePlugInAnnotation | _:treadle2.BlackBoxFactoriesAnnotation |
             _:treadle2.TreadleTesterAnnotation=>fail("ANNOTATION_EXTENSION")
        case x if Set("firrtl2.stage.RunFirrtlTransformAnnotation","firrtl2.stage.RunFirrtlTransformAnnotation$",
          "firrtl2.options.RunFirrtlTransformAnnotation")(x.getClass.getName)=>fail("ANNOTATION_EXTENSION")
        case x:SingleTargetAnnotation[_]=>named(x.target)
        case x:MultiTargetAnnotation=>
          b.bound(x.targets.size<=1024,"TARGET_GROUPS")
          x.targets.foreach{xs=>b.bound(xs.size<=1024,"TARGET_MEMBERS");xs.foreach(target)}
        case _:NoTargetAnnotation=>()
        case _=>fail("ANNOTATION_SHAPE")
      }}
    }
  
    /** Tiny qualification only: exercise the same private bounds and evidence code. */
    def boundDiagnosticSelfChecks():Int={
      var checks=0
      def rejected(reason:String)(operation:Budget=>Unit):Unit={
        val b=new Budget;b.phase="CANDIDATES"
        var caught:Throwable=null
        try{operation(b)}catch{case e:IllegalArgumentException=>caught=e}
        require(caught!=null && caught.getClass==classOf[IllegalArgumentException] && guardCode(caught)=="BOUND")
        val code=boundEvidence(caught).split(":",-1)
        require(code.length==3 && code(0)==reason && code(1)=="CANDIDATES")
        val work=code(2).toInt
        require(work>=0 && work<=5000001 && (if(reason=="GLOBAL_WORK")work==5000001 else work<=5000000))
        checks+=1
      }
      rejected("GLOBAL_WORK"){b=>var n=0;while(n<5000000){b.tick();n+=1};b.tick()}
      rejected("NAME"){b=>b.name("x"*4096);b.name("x"*4097)}
      def deepType(n:Int):Type=(0 until n).foldLeft[Type](ClockType)((t,_)=>VectorType(t,1))
      rejected("TYPE_DEPTH"){b=>boundedType(deepType(64),b);boundedType(deepType(65),b)}
      rejected("TYPE_FIELDS"){b=>boundedType(BundleType(Vector.fill(4097)(Field("x",Default,ClockType))),b)}
      rejected("TYPE_NODES"){b=>boundedType(BundleType(Vector.fill(4096)(Field("x",Default,ClockType))),b)}
      def deepInfo(n:Int):Info=(0 until n).foldLeft[Info](FileInfo("x"))((i,_)=>new MultiInfo(Seq(i)))
      rejected("INFO_DEPTH"){b=>checkedInfo(deepInfo(16),b);checkedInfo(deepInfo(17),b)}
      rejected("INFO_STRING"){b=>checkedInfo(FileInfo("x"*4096),b);checkedInfo(FileInfo("x"*4097),b)}
      rejected("INFO_CHILDREN"){b=>checkedInfo(new MultiInfo(Vector.fill(64)(NoInfo)),b);checkedInfo(new MultiInfo(Vector.fill(65)(NoInfo)),b)}
      rejected("INFO_NODES"){b=>checkedInfo(new MultiInfo(Vector.fill(5)(new MultiInfo(Vector.fill(64)(NoInfo)))),b)}
      require(boundEvidence(null)=="NONE" && boundEvidence(new IllegalArgumentException("DRIVER"))=="NONE")
      val missing=new IllegalArgumentException("BOUND")
      require(boundEvidence(missing)=="UNAVAILABLE")
      missing.addSuppressed(new BoundEvidence("NAME:CANDIDATES:0"))
      missing.addSuppressed(new BoundEvidence("NAME:CANDIDATES:0"))
      require(boundEvidence(missing)=="UNAVAILABLE")
      checks
    }
  
    // BEGIN INDEX SIZING DIAGNOSTIC
    // Failure-only diagnostic. It never supplies authority to the matcher below.
    private final class SizingCounts {
      var modules=0L;var roots=0L;var ports=0L;var statements=0L
      var namedDeclarations=0L;var namespaceOccurrences=0L
      var maxPortsPerModule=0L;var maxStatementsPerModule=0L;var maxNamespacePerModule=0L
      var totalNameChars=0L;var maxNameLength=0L;var registers=0L
      def csv:String=Seq(modules,roots,ports,statements,namedDeclarations,namespaceOccurrences,
        maxPortsPerModule,maxStatementsPerModule,maxNamespacePerModule,totalNameChars,maxNameLength,registers).mkString(",")
      def name(s:String):Unit={
        sizingName(s)
        require(totalNameChars<=20480000000L-s.length.toLong)
        totalNameChars+=s.length.toLong;maxNameLength=math.max(maxNameLength,s.length.toLong)
        namespaceOccurrences+=1
      }
    }
    private def sizingName(s:String):Unit=require(s!=null && s.nonEmpty && s.length<=4096)
    private final class SizingBudget(val limit:Int) {
      var visits=0
      def visit():Boolean=if(visits==limit)false else {visits+=1;true}
    }
    private def sizingTrigger(error:Throwable):Boolean={
      if(guardCode(error)!="BOUND")false
      else {
        val code=boundEvidence(error);val prefix="DECLARATIONS:INDEX_BEFORE:"
        if(!code.startsWith(prefix))false
        else {
          val n=code.substring(prefix.length)
          n.nonEmpty && n.length<=7 && (n.length==1 || n.charAt(0)!='0') &&
            n.forall(c=>c>='0' && c<='9') && n.toInt<=5000000
        }
      }
    }
    // One iterator per ancestor, not one entry per child. No expression or Info
    // traversal, name collection, deduplication, AST export or exception messages.
    private def sizingScan(c:Circuit,out:SizingCounts,b:SizingBudget):Boolean={
      sizingName(c.main)
      val modules=c.modules.iterator
      while(modules.hasNext){
        if(!b.visit())return false
        val m=modules.next();out.modules+=1;require(out.modules<=4096);sizingName(m.name)
        var modulePorts=0L;var moduleStatements=0L;var moduleNamespace=0L
        val ports=m.ports.iterator
        while(ports.hasNext){
          if(!b.visit())return false
          val p=ports.next();modulePorts+=1;require(modulePorts<=250000)
          out.name(p.name);out.ports+=1;moduleNamespace+=1
          out.maxPortsPerModule=math.max(out.maxPortsPerModule,modulePorts)
          out.maxNamespacePerModule=math.max(out.maxNamespacePerModule,moduleNamespace)
        }
        m match {
          case mm:Module=>
            val stack=new Array[Iterator[Statement]](258)
            stack(0)=Iterator.single(mm.body)
            var depth=0
            while(depth>=0){
              val current=stack(depth)
              if(!current.hasNext){stack(depth)=null;depth-=1}
              else {
                if(!b.visit())return false
                require(depth<=256)
                val s=current.next();out.statements+=1;moduleStatements+=1
                if(depth==0)out.roots+=1
                out.maxStatementsPerModule=math.max(out.maxStatementsPerModule,moduleStatements)
                s match {
                  case p:Print if p.name.isEmpty=>()
                  case p:Stop if p.name.isEmpty=>()
                  case p:Verification if p.name.isEmpty=>()
                  case d:IsDeclaration=>out.name(d.name);out.namedDeclarations+=1;moduleNamespace+=1
                  case _=>()
                }
                out.maxNamespacePerModule=math.max(out.maxNamespacePerModule,moduleNamespace)
                s match {case _:DefRegister=>out.registers+=1;case _=>()}
                val children:Iterator[Statement]=s match {
                  case block:Block=>block.stmts.iterator
                  case cond:Conditionally=>Iterator(cond.conseq,cond.alt)
                  case _=>
                    // Fail closed if a future statement form introduces children.
                    s.foreachStmt{_=>throw new IllegalArgumentException()}
                    Iterator.empty
                }
                if(children.hasNext){depth+=1;stack(depth)=children}
              }
            }
          case _:ExtModule=>()
          case _=>throw new IllegalArgumentException()
        }
      }
      true
    }
    private def sizingCollect(before:Circuit,prepared:Circuit,limit:Int):String={
      require(limit>=0 && limit<=5000000)
      val b=new SizingBudget(limit);val old=new SizingCounts;val fresh=new SizingCounts
      val status=if(!sizingScan(before,old,b))"TRUNCATED:BEFORE"
        else if(!sizingScan(prepared,fresh,b))"TRUNCATED:PREPARED" else "COMPLETE:DONE"
      status+":"+b.visits+":"+old.csv+":"+fresh.csv
    }
    def sizingEvidence(before:Circuit,prepared:Circuit,error:Throwable):String=try{
      if(!sizingTrigger(error))"NONE" else sizingCollect(before,prepared,5000000)
    }catch{case _:Throwable=>"UNAVAILABLE"}
  
    /** Small synthetic cases invoke the production private scanner, never repair. */
    def sizingSelfChecks():Int={
      var checks=0
      def check(p:Boolean):Unit={require(p);checks+=1}
      val error=new IllegalArgumentException("BOUND")
      error.addSuppressed(new BoundEvidence("DECLARATIONS:INDEX_BEFORE:1"))
      val zero=UIntLiteral(0,IntWidth(1));val clk=Reference("clk",ClockType)
      def circuit(body:Statement,ports:Seq[Port]=Seq.empty):Circuit=
        Circuit(NoInfo,Seq(Module(NoInfo,"Sizing",ports,body)),"Sizing")
      val tiny=circuit(Block(Seq(DefWire(NoInfo,"a",ClockType),
        DefRegister(NoInfo,"rr",ClockType,clk,zero,zero),
        Print(NoInfo,StringLit(""),Seq.empty,clk,zero),Stop(NoInfo,0,clk,zero))),
        Seq(Port(NoInfo,"a",Input,ClockType),Port(NoInfo,"a",Input,ClockType)))
      val full="1,1,2,5,2,4,2,5,4,5,2,1"
      val partial="1,1,2,4,2,4,2,4,4,5,2,1"
      val empty="0,0,0,0,0,0,0,0,0,0,0,0"
      check(sizingEvidence(tiny,tiny,error)=="COMPLETE:DONE:16:"+full+":"+full)
      check(sizingCollect(tiny,tiny,16)=="COMPLETE:DONE:16:"+full+":"+full)
      check(sizingCollect(tiny,tiny,15)=="TRUNCATED:PREPARED:15:"+full+":"+partial)
      check(sizingCollect(tiny,tiny,7)=="TRUNCATED:BEFORE:7:"+partial+":"+empty)
      check(sizingCollect(tiny,tiny,8)=="TRUNCATED:PREPARED:8:"+full+":"+empty)
      val broad=circuit(Block(Vector.fill(4096)(EmptyStmt)))
      val broadCsv="1,1,0,4097,0,0,0,4097,0,0,0,0"
      check(sizingEvidence(broad,broad,error)=="COMPLETE:DONE:8196:"+broadCsv+":"+broadCsv)
      def deep(n:Int):Circuit=circuit((0 until n).foldLeft[Statement](EmptyStmt)((s,_)=>Block(Seq(s))))
      val deepCsv="1,1,0,257,0,0,0,257,0,0,0,0"
      check(sizingEvidence(deep(256),deep(256),error)=="COMPLETE:DONE:516:"+deepCsv+":"+deepCsv)
      check(sizingEvidence(deep(257),tiny,error)=="UNAVAILABLE")
      val longName=circuit(EmptyStmt,Seq(Port(NoInfo,"x"*4096,Input,ClockType)))
      val longCsv="1,1,1,1,0,1,1,1,1,4096,4096,0"
      check(sizingEvidence(longName,longName,error)=="COMPLETE:DONE:6:"+longCsv+":"+longCsv)
      check(sizingEvidence(circuit(DefWire(NoInfo,"x"*4097,ClockType)),tiny,error)=="UNAVAILABLE")
      check(sizingEvidence(tiny.copy(main=""),tiny,error)=="UNAVAILABLE" &&
        sizingEvidence(tiny.copy(modules=Seq(Module(NoInfo,"x"*4097,Seq.empty,EmptyStmt))),tiny,error)=="UNAVAILABLE")
      val wrong=new IllegalArgumentException("BOUND")
      wrong.addSuppressed(new BoundEvidence("DECLARATIONS:INDEX_PREPARED:1"))
      check(sizingEvidence(null,null,null)=="NONE" && sizingEvidence(null,null,wrong)=="NONE" &&
        sizingEvidence(null,null,new IllegalArgumentException("DRIVER"))=="NONE" &&
        sizingEvidence(null,null,new IllegalArgumentException("BOUND"))=="NONE")
      val conditional=circuit(Conditionally(NoInfo,zero,EmptyStmt,EmptyStmt))
      val conditionalCsv="1,1,0,3,0,0,0,3,0,0,0,0"
      check(sizingEvidence(conditional,conditional,error)=="COMPLETE:DONE:8:"+conditionalCsv+":"+conditionalCsv)
      require(checks==13);checks
    }
  
    // END INDEX SIZING DIAGNOSTIC
    def apply(before:Circuit,prepared:Circuit,annotations:AnnotationSeq,expected:Int):Result={
      tinyOnly(before,prepared,expected)
      need(expected>0 && expected<=1024,"COUNT")
      val b=new Budget
      need(before.main==prepared.main,"STRUCTURE")
      val old=index(before,b);b.phase="INDEX_PREPARED";val fresh=index(prepared,b)
      b.phase="CANDIDATES"
      val candidates=Vector.newBuilder[Candidate]
      var candidateCount=0
      fresh.foreach{case(module,idx)=>idx.statements.foreach{
        case r:DefRegister if isMismatch(r,b)=>
          need(r.tpe==ClockType && isZero(r.reset) && isZero(r.init),"SHAPE")
          val original=old.getOrElse(module,fail("ORIGINAL_MODULE"))
          need(!original.names(r.name),"PREEXISTING")
          val clk=clockRef(r.clock).getOrElse(fail("CLOCK"))
          val port=original.ports.getOrElse(clk.name,fail("CLOCK"))
          need(port.direction==Input && port.tpe==ClockType,"CLOCK")
          val nowPort=idx.ports.getOrElse(clk.name,fail("CLOCK"))
          need(nowPort.direction==Input && nowPort.tpe==ClockType,"CLOCK")
          need(checkedInfo(r.info,b),"INFO")
          candidateCount+=1;need(candidateCount<=expected,"COUNT")
          candidates+=Candidate(module,r,clk)
        case _=>()
      }}
      val selected=candidates.result()
      need(selected.size==expected,"COUNT")
      val keys=selected.map(c=>(c.module,c.reg.name)).toSet
      b.phase="ANNOTATIONS"
      checkAnnotations(annotations,keys,prepared.main,b)
      b.phase="USES"
      val uses=scala.collection.mutable.HashMap.empty[(String,String),Vector[Use]]
      keys.foreach(k=>uses(k)=Vector.empty)
      // Count every Reference occurrence through every expression, including unused
      // branches, connection sinks, declaration fields, aliases and nested accesses.
      fresh.foreach{case(module,idx)=>idx.statements.foreach{s=>
        s.foreachExpr{root=>
          var stack=List((root,0))
          while(stack.nonEmpty){
            val (e,d)=stack.head;stack=stack.tail;b.tick();b.bound(d<=256,"EXPRESSION_DEPTH")
            e match {
              case r:Reference=>
                b.name(r.name)
                val key=(module,r.name)
                if(keys(key)){
                  val next=uses(key):+Use(s,root,d==0)
                  need(next.size<=2,"REFERENCES");uses(key)=next
                }
              case _=>()
            }
            e.foreachExpr{x=>b.tick();stack=(x,d+1)::stack}
          }
        }
      }}
      b.phase="ANCHORS"
      val anchorCounts=scala.collection.mutable.HashMap.empty[AnchorKey,Int]
      old.foreach{case(module,idx)=>idx.statements.foreach{s=>
        b.tick();anchorKey(module,s,b).foreach{k=>anchorCounts(k)=anchorCounts.getOrElse(k,0)+1}
      }}
      b.phase="MATCHING"
      selected.foreach{c=>
        val found=uses((c.module,c.reg.name))
        need(found.size==2,"REFERENCES")
        val drivers=found.collect{case Use(x:Connect,root,true) if (root eq x.loc) && delayedSink(x.loc,c.reg.name)=>x}
        if(drivers.size!=1)driverFail("SELECT",found,c.clock)
        val driver=drivers.head
        if(driver.expr!=c.clock)driverFail("RHS",found,c.clock)
        need(sameInfo(c.reg.info,driver.info,b),"INFO")
        val consumers=found.collect{
          case Use(x:Print,root,true) if (root eq x.clk) && delayedRef(x.clk,c.reg.name)=>x:Statement
          case Use(x:Stop,root,true) if (root eq x.clk) && delayedRef(x.clk,c.reg.name)=>x:Statement
        }
        need(consumers.size==1,"CONSUMER")
        val consumer=consumers.head
        val key=consumer match {
          case p:Print=>
            need(sameInfo(c.reg.info,p.info,b),"INFO");b.bound(p.string.string.length<=4096,"PRINT_STRING")
            AnchorKey(c.module,true,c.clock.name,p.info,p.string.string,0)
          case p:Stop=>need(sameInfo(c.reg.info,p.info,b),"INFO");AnchorKey(c.module,false,c.clock.name,p.info,"",p.ret)
          case _=>fail("CONSUMER")
        }
        need(anchorCounts.getOrElse(key,0)==1,"ANCHOR")
      }
      // Only after all checks: rebuild changed ancestors, reusing every other node.
      b.phase="REBUILD"
      val replacements=new java.util.IdentityHashMap[Statement,Statement]()
      selected.foreach{c=>
        val typedZero=DoPrim(firrtl2.PrimOps.AsClock,Seq(c.reg.init),Seq.empty,ClockType)
        replacements.put(c.reg,c.reg.copy(init=typedZero))
      }
      val modules=prepared.modules.map{
        case m:Module=>
          fresh(m.name).statements.reverseIterator.foreach{s=>
            if(!replacements.containsKey(s)){
              var changed=false
              s.foreachStmt{x=>if(replacements.containsKey(x))changed=true}
              if(changed)s match {
                // Block.mapStmt flattens nested Blocks and drops EmptyStmt. Preserve
                // the exact immediate children instead; no other ancestor may change.
                case block:Block=>replacements.put(s,block.copy(stmts=block.stmts.map{x=>Option(replacements.get(x)).getOrElse(x)}))
                case _=>fail("NONINTERFERENCE")
              }
            }
          }
          if(replacements.containsKey(m.body))m.copy(body=replacements.get(m.body))else m
        case m=>m
      }
      val result=prepared.copy(modules=modules)
      // Production noninterference proof: identity checks, never Host serialization
      // or whole-tree structural equality. Changed paths may contain Blocks only.
      need((result.info eq prepared.info) && (result.main eq prepared.main) &&
        result.modules.size==prepared.modules.size,"NONINTERFERENCE")
      b.phase="NONINTERFERENCE"
      val selectedRegisters=new java.util.IdentityHashMap[Statement,java.lang.Boolean]()
      selected.foreach(c=>selectedRegisters.put(c.reg,java.lang.Boolean.TRUE))
      var changedRegisters=0
      val oldModules=prepared.modules.iterator;val newModules=result.modules.iterator
      while(oldModules.hasNext && newModules.hasNext){
        b.tick()
        val prior=oldModules.next();val revised=newModules.next()
        if(!(prior eq revised)){
          (prior,revised) match {
            case (om:Module,nm:Module)=>
              need((om.name eq nm.name) && (om.info eq nm.info) && (om.ports eq nm.ports),"NONINTERFERENCE")
              var pairs=List((om.body,nm.body))
              while(pairs.nonEmpty){
                val (os,ns)=pairs.head;pairs=pairs.tail;b.tick()
                if(!(os eq ns)){
                  (os,ns) match {
                    case (o:DefRegister,n:DefRegister)=>
                      need(selectedRegisters.containsKey(o),"NONINTERFERENCE")
                      need((o.info eq n.info) && (o.name eq n.name) && (o.tpe eq n.tpe) &&
                        (o.clock eq n.clock) && (o.reset eq n.reset),"NONINTERFERENCE")
                      n.init match {
                        case DoPrim(firrtl2.PrimOps.AsClock,Seq(value),constants,ClockType)=>
                          need(constants.isEmpty && (value eq o.init),"NONINTERFERENCE")
                        case _=>fail("NONINTERFERENCE")
                      }
                      changedRegisters+=1
                      need(changedRegisters<=expected,"NONINTERFERENCE")
                    case (o:Block,n:Block)=>
                      need(o.stmts.size==n.stmts.size,"NONINTERFERENCE")
                      val oi=o.stmts.iterator;val ni=n.stmts.iterator
                      while(oi.hasNext && ni.hasNext){b.tick();pairs=(oi.next(),ni.next())::pairs}
                      need(!oi.hasNext && !ni.hasNext,"NONINTERFERENCE")
                    case _=>fail("NONINTERFERENCE")
                  }
                }
              }
            case _=>fail("NONINTERFERENCE")
          }
        }
      }
      need(!oldModules.hasNext && !newModules.hasNext && changedRegisters==expected,"NONINTERFERENCE")
      Result(result,changedRegisters,b.proofTicks)
    }
  }
  // END FROZEN LEGACY REPAIR ORACLE
}

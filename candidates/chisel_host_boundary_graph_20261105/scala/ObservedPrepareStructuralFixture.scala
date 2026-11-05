package chiseltest.simulator

import firrtl2.{AnnotationSeq,CircuitState,Parser}
import firrtl2.ir._
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import treadle2.TreadleCircuitStateAnnotation
import treadle2.stage.phases.{PrepareAst,HandleFormalStatements}
import treadle2.utils.AugmentPrintf
import treadle2.executable.SymbolTable
import java.io.{OutputStream,PrintStream}
import java.nio.file.{Files,Path,Paths}
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest

/** Tiny observation qualification only. Never invoke repair or an execution engine. */
object ObservedPrepareStructuralFixture {
  private def sha(bytes:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(bytes).map(x=>f"${x&255}%02x").mkString
  private def loaded(c:Class[_],location:String):String={
    require(Paths.get(c.getProtectionDomain.getCodeSource.getLocation.toURI).toRealPath()==Paths.get(location).toRealPath())
    val in=c.getResourceAsStream("/"+c.getName.replace('.','/')+".class");require(in!=null)
    try{val bytes=in.readNBytes(1048577);require(bytes.length<=1048576);sha(bytes)}finally in.close()
  }
  private def family(xs:scala.collection.Seq[_]):Unit=xs match {
    case _:List[_]|_:Vector[_]|_:scala.collection.immutable.ArraySeq.ofRef[_]=>()
    case _=>throw new IllegalArgumentException("TINY_SEQUENCE")
  }
  // Exact pinned constructor whitelist. Unknown classes cannot invoke arbitrary
  // Product accessors merely because they implement a familiar interface.
  private val nodes:Set[Class[_]]=Set(classOf[Circuit],classOf[Module],classOf[Port],
    classOf[Block],classOf[Conditionally],classOf[DefWire],classOf[DefRegister],classOf[DefNode],
    classOf[Connect],classOf[IsInvalid],classOf[Print],classOf[Stop],classOf[Verification],
    classOf[Reference],classOf[SubField],classOf[SubIndex],classOf[SubAccess],classOf[Mux],classOf[ValidIf],
    classOf[UIntLiteral],classOf[SIntLiteral],classOf[DoPrim],classOf[UIntType],classOf[SIntType],
    classOf[AnalogType],classOf[BundleType],classOf[VectorType],classOf[Field],classOf[IntWidth],
    classOf[StringLit],classOf[FileInfo],classOf[MultiInfo])
  private val annotations:Set[Class[_]]=Set(classOf[FirrtlCircuitAnnotation],classOf[TreadleCircuitStateAnnotation],
    classOf[TargetDirAnnotation],classOf[firrtl2.stage.OutputFileAnnotation],
    classOf[firrtl2.transforms.BlackBoxTargetDirAnno],classOf[firrtl2.annotations.DeletedAnnotation])
  private val atoms:Array[AnyRef]=Array(NoInfo,EmptyStmt,ClockType,ResetType,AsyncResetType,UnknownType,UnknownWidth,
    Input,Output,Default,Flip,firrtl2.NodeKind,firrtl2.PortKind,firrtl2.RegKind,firrtl2.WireKind,
    firrtl2.InstanceKind,firrtl2.MemKind,firrtl2.ExpKind,firrtl2.UnknownKind,
    firrtl2.SourceFlow,firrtl2.SinkFlow,firrtl2.DuplexFlow,firrtl2.UnknownFlow,
    firrtl2.PrimOps.Add,firrtl2.PrimOps.Sub,firrtl2.PrimOps.Mul,firrtl2.PrimOps.Div,firrtl2.PrimOps.Rem,
    firrtl2.PrimOps.Lt,firrtl2.PrimOps.Leq,firrtl2.PrimOps.Gt,firrtl2.PrimOps.Geq,firrtl2.PrimOps.Eq,firrtl2.PrimOps.Neq,
    firrtl2.PrimOps.Pad,firrtl2.PrimOps.AsUInt,firrtl2.PrimOps.AsSInt,firrtl2.PrimOps.AsClock,firrtl2.PrimOps.AsAsyncReset,
    firrtl2.PrimOps.Shl,firrtl2.PrimOps.Shr,firrtl2.PrimOps.Dshl,firrtl2.PrimOps.Dshr,firrtl2.PrimOps.Cvt,
    firrtl2.PrimOps.Neg,firrtl2.PrimOps.Not,firrtl2.PrimOps.And,firrtl2.PrimOps.Or,firrtl2.PrimOps.Xor,
    firrtl2.PrimOps.Andr,firrtl2.PrimOps.Orr,firrtl2.PrimOps.Xorr,firrtl2.PrimOps.Cat,firrtl2.PrimOps.Bits,
    firrtl2.PrimOps.Head,firrtl2.PrimOps.Tail,Formal.Assert,Formal.Assume,Formal.Cover)
  private def atom(x:AnyRef):Boolean={var i=0;while(i<atoms.length){if(atoms(i) eq x)return true;i+=1};false}
  private final class Parity {
    private var statements=0;private var expressions=0;private var annotationCount=0
    private var text=0;private var visits=0
    private def string(a:String,b:String):Unit={
      require(a!=null && b!=null && a.length==b.length && a.length<=(65536-text)/2)
      text+=2*a.length;var i=0;while(i<a.length){require(a.charAt(i)==b.charAt(i));i+=1}
    }
    private def seq(a:scala.collection.Seq[_],b:scala.collection.Seq[_],limit:Int,depth:Int,ed:Int,td:Int):Unit={
      family(a);family(b);val ai=a.iterator;val bi=b.iterator;var count=0
      while(ai.hasNext && bi.hasNext){require(count<limit);count+=1;value(ai.next(),bi.next(),depth+1,ed,td)}
      require(!ai.hasNext && !bi.hasNext)
    }
    private def product(a:Product,b:Product,depth:Int,ed:Int,td:Int):Unit={
      require(a.productArity==b.productArity && a.productArity<=16)
      var i=0;while(i<a.productArity){value(a.productElement(i),b.productElement(i),depth+1,ed,td);i+=1}
    }
    def value(a:Any,b:Any,depth:Int=0,expressionDepth:Int=0,typeDepth:Int=0):Unit={
      require(a!=null && b!=null && depth<=256 && visits<65536);visits+=1
      require(a.getClass eq b.getClass)
      val ed=if(a.isInstanceOf[Expression])expressionDepth+1 else expressionDepth
      val td=if(a.isInstanceOf[Type])typeDepth+1 else typeDepth
      require((!a.isInstanceOf[Expression] || expressionDepth<=64) && (!a.isInstanceOf[Type] || typeDepth<=64))
      a match {
        case _:Statement=>require(statements<4096);statements+=1
        case _:Expression=>require(expressions<16384);expressions+=1
        case _=>()
      }
      a match {
        case x:String=>string(x,b.asInstanceOf[String])
        case x:Int=>require(x==b.asInstanceOf[Int])
        case x:Long=>require(x==b.asInstanceOf[Long])
        case x:Boolean=>require(x==b.asInstanceOf[Boolean])
        case x:BigInt=>val y=b.asInstanceOf[BigInt];require(x.getClass==classOf[BigInt]);require(x.bitLength<=64 && y.bitLength<=64 && x.signum==y.signum && x.longValue==y.longValue)
        case x:CircuitState=>
          require(x.getClass==classOf[CircuitState]);val y=b.asInstanceOf[CircuitState]
          // Pinned FIRRTL2 6.0.0 has exactly these three fields and no form API.
          require(x.productArity==3 && y.productArity==3 && (x.renames eq None) && (y.renames eq None))
          value(x.circuit,y.circuit,depth+1,0,0);seq(x.annotations,y.annotations,64,depth+1,0,0)
        case x:Circuit=>require(x.getClass==classOf[Circuit]);val y=b.asInstanceOf[Circuit]
          value(x.info,y.info,depth+1,0,0);string(x.main,y.main);seq(x.modules,y.modules,8,depth+1,0,0)
        case x:Module=>require(x.getClass==classOf[Module]);val y=b.asInstanceOf[Module]
          value(x.info,y.info,depth+1,0,0);string(x.name,y.name);seq(x.ports,y.ports,64,depth+1,0,0)
          value(x.body,y.body,depth+1,0,0)
        case x:firrtl2.annotations.Annotation=>
          require(annotations(x.getClass) && annotationCount<64);annotationCount+=1
          product(x.asInstanceOf[Product],b.asInstanceOf[Product],depth,ed,td)
        case x:scala.collection.Seq[_]=>seq(x,b.asInstanceOf[scala.collection.Seq[_]],16384,depth,ed,td)
        case x:AnyRef if atom(x)=>require(x eq b.asInstanceOf[AnyRef])
        case x:FirrtlNode=>require(nodes(x.getClass));product(x.asInstanceOf[Product],b.asInstanceOf[Product],depth,ed,td)
        case _=>throw new IllegalArgumentException("TINY_CONSTRUCTOR")
      }
    }
    def apply(a:AnnotationSeq,b:AnnotationSeq):Unit=seq(a,b,64,0,0,0)
  }
  private def visit(c:Circuit)(f:Statement=>Unit):Unit={
    family(c.modules);require(c.modules.size<=8);var count=0
    def go(s:Statement,d:Int):Unit={require(d<=256 && count<4096 && (nodes(s.getClass) || (s eq EmptyStmt)));count+=1;f(s)
      s match{case b:Block=>family(b.stmts);b.stmts.foreach(x=>go(x,d+1))
        case x:Conditionally=>go(x.conseq,d+1);go(x.alt,d+1)
        case _=>require(nodes(s.getClass) || (s eq EmptyStmt))}}
    family(c.modules);c.modules.foreach{case m:Module=>require(m.getClass==classOf[Module]);family(m.ports);require(m.ports.size<=64);go(m.body,0);case _=>require(false)}
  }
  private def registers(c:Circuit):Vector[DefRegister]={
    val out=Vector.newBuilder[DefRegister];var n=0
    visit(c){case r:DefRegister if r.tpe==ClockType=>require(n<16);out+=r;n+=1;case _=>()};out.result()
  }
  private def state(as:AnnotationSeq):CircuitState={
    family(as);require(as.size<=64);val states=as.collect{case TreadleCircuitStateAnnotation(s)=>s}
    require(states.size==1);states.head
  }
  private final case class UnsupportedAnnotation(value:Int) extends firrtl2.annotations.NoTargetAnnotation
  private def paritySelfChecks():Int={
    var count=0
    def rejected(f: =>Unit):Unit={var seen=false;try{f}catch{case _:IllegalArgumentException=>seen=true};require(seen);count+=1}
    val empty=Circuit(NoInfo,Seq(Module(NoInfo,"Tiny",Seq.empty,EmptyStmt)),"Tiny")
    val state=CircuitState(empty,Seq.empty)
    new Parity().value(state,state);count+=1
    rejected{new Parity().value(state,state.copy(renames=Some(null)))}
    rejected{new Parity().value(empty,empty.copy(info=FileInfo("different")))}
    rejected{new Parity().apply(Seq(TargetDirAnnotation("a"),FirrtlCircuitAnnotation(empty)),Seq(FirrtlCircuitAnnotation(empty),TargetDirAnnotation("a")))}
    rejected{new Parity().value(UnsupportedAnnotation(1),UnsupportedAnnotation(1))}
    rejected{new Parity().value(scala.collection.immutable.Queue(EmptyStmt),scala.collection.immutable.Queue(EmptyStmt))}
    rejected{new Parity().value(UIntLiteral(0,IntWidth(1)),UIntLiteral(1,IntWidth(1)))}
    val ref=Reference("clock",ClockType,firrtl2.PortKind,firrtl2.SourceFlow)
    rejected{new Parity().value(ref,ref.copy(flow=firrtl2.SinkFlow))}
    rejected{new Parity().value(new MultiInfo(Seq(FileInfo("a"),FileInfo("b"))),new MultiInfo(Seq(FileInfo("b"),FileInfo("a"))))}
    val max="x"*32768;val p=new Parity;p.value(max,max)
    rejected{p.value("x","x")}
    def deep(n:Int):Type={var t:Type=ClockType;var i=0;while(i<n){t=VectorType(t,1);i+=1};t}
    val admitted=deep(64);new Parity().value(admitted,admitted)
    rejected{val over=deep(65);new Parity().value(over,over)}
    require(count==11);count
  }
  private def source(mode:String):String={
    val print=if(mode!="stop")"    printf(clock, en, \"fixture %d\", data) @[observed_print 1:1]\n"else ""
    val stop=if(mode!="print")"    stop(clock, stop_en, 0) @[observed_stop 1:1]\n"else ""
    "circuit ObservedFixture :\n  module ObservedFixture :\n    input clock : Clock\n    input en : UInt<1>\n    input stop_en : UInt<1>\n    input data : UInt<8>\n    output out : UInt<1>\n    reg q : UInt<1>, clock with :\n      reset => (UInt<1>(0), UInt<1>(0))\n    q <= en\n    out <= q\n"+print+stop
  }
  private def body(c:Circuit,f:Statement=>Statement):Circuit=c.copy(modules=c.modules.map{
    case m:Module=>m.copy(body=f(m.body));case x=>x})
  private def suffix(c:Circuit,n:Int):Int={
    val original=CircuitState(c,Seq.empty)
    val first=(new AugmentPrintf).runTransform(original)
    val r1=registers(first.circuit);require(r1.size==n)
    val second=(new HandleFormalStatements).runTransform(first);val r2=registers(second.circuit)
    val third=firrtl2.passes.memlib.VerilogMemDelays.runTransform(second);val r3=registers(third.circuit)
    val fourth=firrtl2.passes.ResolveFlows.runTransform(third);val r4=registers(fourth.circuit)
    require(r2.size==n && r3.size==n && r4.size==n)
    var i=0;while(i<n){
      val a=r1(i);val b=r2(i);val d=r3(i);val e=r4(i)
      require(a eq b)
      require(!(b eq d) && (b.name eq d.name) && (b.info eq d.info) && (b.tpe eq d.tpe) &&
        (b.clock eq d.clock) && (b.reset eq d.reset) && (b.init eq d.init))
      require(!(d eq e) && (d.name eq e.name) && (d.info eq e.info) && (d.tpe eq e.tpe) &&
        (d.reset eq e.reset) && (d.init eq e.init))
      val dc=d.clock.asInstanceOf[Reference];val ec=e.clock.asInstanceOf[Reference]
      require(dc.getClass==classOf[Reference] && ec.getClass==classOf[Reference] && !(dc eq ec) &&
        (dc.name eq ec.name) && (dc.tpe eq ec.tpe) && (dc.kind eq ec.kind) && ec.flow==firrtl2.SourceFlow)
      i+=1
    }
    n*3
  }
  private def graphChecks(c:Circuit):Int={
    val typ=UIntType(IntWidth(1))
    def ref(name:String,flow:firrtl2.Flow)=Reference(name,typ,firrtl2.WireKind,flow)
    val cycle=body(c,s=>Block(Seq(s,DefWire(NoInfo,"cycle_a",typ),DefWire(NoInfo,"cycle_b",typ),
      Connect(NoInfo,ref("cycle_a",firrtl2.SinkFlow),ref("cycle_b",firrtl2.SourceFlow)),
      Connect(NoInfo,ref("cycle_b",firrtl2.SinkFlow),ref("cycle_a",firrtl2.SourceFlow)))))
    def rejects(x:Circuit):Unit={var rejected=false;try{SymbolTable(x,Seq.empty,allowCycles=false)}catch{
      case _:firrtl2.graph.CyclicException=>rejected=true};require(rejected)}
    rejects(cycle)
    val after52=(new HandleFormalStatements).runTransform(CircuitState(cycle,Seq.empty))
    val after53=firrtl2.passes.memlib.VerilogMemDelays.runTransform(after52)
    rejects(firrtl2.passes.ResolveFlows.runTransform(after53).circuit)
    var cuts=0
    def feedback(s:Statement):Statement=s match {
      case b:Block=>b.copy(stmts=b.stmts.map(feedback))
      case x:Connect=>x.loc match{case r:Reference if r.name=="q"=>cuts+=1;x.copy(expr=r.copy(flow=firrtl2.SourceFlow));case _=>x}
      case x=>x
    }
    val cut=body(c,feedback);require(cuts==1)
    SymbolTable(cut,Seq.empty,allowCycles=false)
    val cut52=(new HandleFormalStatements).runTransform(CircuitState(cut,Seq.empty))
    val cut53=firrtl2.passes.memlib.VerilogMemDelays.runTransform(cut52)
    SymbolTable(firrtl2.passes.ResolveFlows.runTransform(cut53).circuit,Seq.empty,allowCycles=false)
    4
  }
  def main(args:Array[String]):Unit={
    val out=System.out;val err=System.err;val muted=new PrintStream(OutputStream.nullOutputStream())
    var rows=Vector.empty[String];var ok=false;var phase="IDENTITY";var target:Path=null
    try{
      require(args.length==8 && Set("official","cached")(args(0)))
      require(loaded(classOf[ObservedPrepareAst],args(1))==args(2))
      require(loaded(ObservedPrepareAst.getClass,args(1))==args(3))
      require(loaded(ObservedScheduleIdentity.getClass,args(1))==args(4))
      require(loaded(classOf[SymbolTable],args(5))==args(6) && loaded(SymbolTable.getClass,args(5))==args(7))
      val base=Paths.get(".").toAbsolutePath.normalize()
      target=Files.createTempDirectory(base,"observed-prepare-fixture-")
      val relative=base.relativize(target)
      require(target.getParent==base && !relative.isAbsolute && relative.getNameCount==1 && relative.normalize()==relative &&
        relative.toString!="." && relative.toString!="..")
      val targetName=relative.toString
      System.setOut(muted);System.setErr(muted)
      Console.withOut(muted){Console.withErr(muted){
        // Shared prerequisites execute once per process; repeated row counts
        // identify that same result, not nine separate executions.
        phase="SELFTEST";val selfChecks=ObservedPrepareAst.selfChecks();require(selfChecks==69)
        val parityChecks=paritySelfChecks();require(parityChecks==11)
        val sizingChecks=ObservedPrepareAst.sizingSelfChecks();require(sizingChecks==56)
        rows=Vector("print","stop","both").flatMap{mode=>
          phase="LOWER"
          val low=Compiler.toLowFirrtl(CircuitState(Parser.parse(source(mode)),Seq(TargetDirAnnotation(targetName)))).circuit
          val n=if(mode=="both")2 else 1
          val baseAnnotations=Seq(FirrtlCircuitAnnotation(low),TargetDirAnnotation(targetName))
          phase="OFFICIAL";val officialBase=(new PrepareAst).transform(baseAnnotations)
          val selected=registers(state(officialBase).circuit);require(selected.size==n)
          val firstName=selected.head.name
          val recycled=body(low,s=>Block(Seq(s,DefNode(FileInfo("recycled 1:1"),firstName,UIntLiteral(1,IntWidth(1))))))
          Vector("base"->low,"nested"->body(low,s=>Block(Seq(EmptyStmt,Block(Seq(s,EmptyStmt)),EmptyStmt))),"recycled"->recycled).map{case(kind,input)=>
            phase="OFFICIAL";val as=Seq(FirrtlCircuitAnnotation(input),TargetDirAnnotation(targetName))
            val official=if(kind=="base")officialBase else (new PrepareAst).transform(as)
            phase="OBSERVED";val observer=new ObservedPrepareAst(n);val observed=observer.transform(as)
            phase="PARITY";new Parity().apply(official,observed)
            val expected="COMPLETE:DONE:NONE:"+Vector.fill(7)(n.toString).mkString(":")+":"
            require(observer.evidence.startsWith(expected))
            require(observer.budgetEvidence=="NONE" && observer.sizingEvidence=="NONE")
            if(kind=="recycled")require(registers(state(observed).circuit).exists(_.name==firstName))
            val failureParity=if(kind=="base"){
              phase="OBSERVED_FAILURE";val rejected=new ObservedPrepareAst(n+1)
              val unchangedOutput=rejected.transform(as)
              phase="PARITY";new Parity().apply(official,unchangedOutput)
              require(rejected.evidence.startsWith("UNAVAILABLE:DISCOVERY:COUNT:0:0:0:0:0:0:0:"))
              require(rejected.budgetEvidence=="NONE" && rejected.sizingEvidence=="NONE");1
            }else 0
            phase="SUFFIX";val relations=if(kind=="base")suffix(low,n)else 0
            phase="GRAPH";val graphs=if(kind=="base")graphChecks(state(observed).circuit)else 0
            "OBSERVED_PREPARE_CASE_V1 mode="+mode+" kind="+kind+" parity=true records="+n+" suffixChecks="+relations+" graphChecks="+graphs+" observerChecks="+selfChecks+" parityChecks="+parityChecks+" failureParityChecks="+failureParity+" sizingChecks="+sizingChecks+" stateFields=3 form=ABSENT_IN_PINNED_API renames=NONE evidence="+observer.evidence
          }
        }
        ok=true
      }}
    }catch{case _:Throwable=>rows=Vector("OBSERVED_PREPARE_FAILURE_V1 phase="+phase+" code=REJECTED")}
    finally{
      System.setOut(out);System.setErr(err)
      try{if(target!=null){val stream=Files.walk(target);val paths=try{val it=stream.iterator();val b=Vector.newBuilder[Path];var n=0
        while(it.hasNext){require(n<256);b+=it.next();n+=1};b.result()}finally stream.close()
        paths.sortBy(p=> -p.getNameCount).foreach(Files.delete(_))}}
      catch{case _:Throwable=>ok=false;rows=Vector("OBSERVED_PREPARE_FAILURE_V1 phase=CLEANUP code=REJECTED")}
      muted.close()
    }
    rows.foreach(out.println)
    out.println("OBSERVED_PREPARE_RUN_V1 label="+args.headOption.filter(Set("official","cached")).getOrElse("invalid")+" pass="+ok+" cases="+(if(ok)9 else 0)+" diagnosticOnly=true interpreterExecuted=false fullHostAccepted=false")
    if(!ok)System.exit(2)
  }
}

package chiseltest.simulator

import firrtl2.{AnnotationSeq,CircuitState,Parser}
import firrtl2.ir._
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import firrtl2.annotations.{ModuleTarget,InstanceTarget,ReferenceTarget,TargetToken}
import firrtl2.transforms.{DedupedResult,CombinationalPath,CheckCombLoops}
import treadle2.TreadleCircuitStateAnnotation
import treadle2.stage.phases.{GetFirrtlAst,SetImplicitOutputInfo,PrepareAst,HandleFormalStatements}
import treadle2.utils.AugmentPrintf
import treadle2.executable.SymbolTable
import java.io.{OutputStream,PrintStream}
import java.nio.file.{Files,Path,Paths}
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest

/** Tiny observation/repair qualification only. Never invoke an execution engine. */
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
        // Exact historical metadata constructors only, under the same parity budgets.
        case x:Double=>require(!x.isNaN && !x.isInfinity && java.lang.Double.doubleToRawLongBits(x)==java.lang.Double.doubleToRawLongBits(b.asInstanceOf[Double]))
        case x:DedupedResult=>
          require(x.getClass==classOf[DedupedResult]);val y=b.asInstanceOf[DedupedResult]
          require(annotationCount<64);annotationCount+=1
          value(x.original,y.original,depth+1,ed,td);value(x.duplicate,y.duplicate,depth+1,ed,td)
          value(x.index,y.index,depth+1,ed,td);seq(x.targets,y.targets,2,depth+1,ed,td)
        case x:CombinationalPath=>
          require(x.getClass==classOf[CombinationalPath]);val y=b.asInstanceOf[CombinationalPath]
          require(annotationCount<64);annotationCount+=1
          value(x.sink,y.sink,depth+1,ed,td);seq(x.sources,y.sources,64,depth+1,ed,td)
        case x:ReferenceTarget=>require(x.getClass==classOf[ReferenceTarget]);product(x,b.asInstanceOf[ReferenceTarget],depth,ed,td)
        case x:ModuleTarget=>require(x.getClass==classOf[ModuleTarget]);product(x,b.asInstanceOf[ModuleTarget],depth,ed,td)
        case x:InstanceTarget=>require(x.getClass==classOf[InstanceTarget]);product(x,b.asInstanceOf[InstanceTarget],depth,ed,td)
        case x:TargetToken.Instance=>require(x.getClass==classOf[TargetToken.Instance]);product(x,b.asInstanceOf[TargetToken.Instance],depth,ed,td)
        case x:TargetToken.OfModule=>require(x.getClass==classOf[TargetToken.OfModule]);product(x,b.asInstanceOf[TargetToken.OfModule],depth,ed,td)
        case x:Tuple2[_,_]=>require(x.getClass==classOf[Tuple2[Any,Any]]);product(x,b.asInstanceOf[Tuple2[_,_]],depth,ed,td)
        case x:Some[_]=>require(x.getClass==classOf[Some[Any]]);value(x.get,b.asInstanceOf[Some[_]].get,depth+1,ed,td)
        case None=>require(b.asInstanceOf[AnyRef] eq None)
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
  // One real official Augment witness. This qualifies rejection and unchanged
  // output, never expands the accepted consumer grammar to Verification.
  private def consumerParityCheck(targetName:String):Int={
    val low=Compiler.toLowFirrtl(CircuitState(Parser.parse(source("print")),Seq(TargetDirAnnotation(targetName)))).circuit
    val clock=Reference("clock",ClockType,firrtl2.PortKind,firrtl2.SourceFlow)
    val enabled=Reference("en",UIntType(IntWidth(1)),firrtl2.PortKind,firrtl2.SourceFlow)
    val verification=Verification(Formal.Assert,FileInfo("consumer_witness 1:1"),clock,enabled,enabled,StringLit("nonempty"),"consumer_witness")
    val input=body(low,s=>Block(Seq(s,verification)))
    val augmented=(new AugmentPrintf).runTransform(CircuitState(input,Seq.empty))
    val selected=registers(augmented.circuit);require(selected.size==2)
    var witnesses=0
    visit(augmented.circuit){
      case v:Verification=>
        require(v.clk.getClass==classOf[Reference])
        val ref=v.clk.asInstanceOf[Reference]
        require((ref.tpe eq ClockType) && (ref.kind eq firrtl2.NodeKind) && (ref.flow eq firrtl2.SourceFlow))
        require(selected.count(r=>r.name==ref.name)==1);witnesses+=1
      case _=>()
    }
    require(witnesses==1)
    val annotations=Seq(FirrtlCircuitAnnotation(input),TargetDirAnnotation(targetName))
    val official=(new PrepareAst).transform(annotations)
    val observer=new ObservedPrepareAst(2);val observed=observer.transform(annotations)
    new Parity().apply(official,observed)
    require(observer.evidence.startsWith("UNAVAILABLE:INITIAL_USES:CONSUMER:0:0:0:0:0:0:0:"))
    require(observer.anchorEvidence=="NONE")
    require(observer.formalEvidence=="UNAVAILABLE:0:0:0:0")
    require(observer.consumerEvidence=="MISSING:CONNECT:1:TRUE:CLOCK:NODE:SOURCE:NA:NA:VERIFICATION:1:TRUE:CLOCK:NODE:SOURCE:ASSERT:NONEMPTY")
    require(observer.budgetEvidence=="NONE" && observer.sizingEvidence=="NONE")
    1
  }
  // Separate positive empty-Assert qualification. Each of the two cases checks
  // full official output parity, actual suffix fields, and four graph controls.
  private def formalParityChecks(targetName:String):Int={
    var count=0
    Vector(false,true).foreach{mixed=>
      val text=if(mixed)source("print")else source("print").linesIterator.filterNot(_.trim.startsWith("printf(")).mkString("\n")+"\n"
      val low=Compiler.toLowFirrtl(CircuitState(Parser.parse(text),Seq(TargetDirAnnotation(targetName)))).circuit
      val clk=Reference("clock",ClockType,firrtl2.PortKind,firrtl2.SourceFlow)
      val en=Reference("en",UIntType(IntWidth(1)),firrtl2.PortKind,firrtl2.SourceFlow)
      val original=Verification(Formal.Assert,FileInfo("formal_witness 1:1"),clk,en,en,StringLit(""),"formal_witness")
      val input=body(low,s=>Block(Seq(s,original)));val n=if(mixed)2 else 1
      val first=(new AugmentPrintf).runTransform(CircuitState(input,Seq.empty))
      var terminal:Verification=null;var found=0
      visit(first.circuit){case v:Verification=>found+=1;terminal=v;case _=>()}
      require(found==1 && terminal.getClass==classOf[Verification] && (terminal.op eq Formal.Assert))
      require((terminal.name eq original.name) && (terminal.info eq original.info) && terminal.msg.getClass==classOf[StringLit] && terminal.msg.string.isEmpty)
      def reference(e:Expression,clock:Boolean):Reference={
        require(e.getClass==classOf[Reference]);val r=e.asInstanceOf[Reference]
        require(r.name.nonEmpty && r.name.length<=4096 && (r.kind eq firrtl2.NodeKind) && (r.flow eq firrtl2.SourceFlow))
        if(clock)require(r.tpe eq ClockType)else{
          require(r.tpe.getClass==classOf[UIntType]);val t=r.tpe.asInstanceOf[UIntType]
          require(t.width.getClass==classOf[IntWidth] && t.width.asInstanceOf[IntWidth].width==1)
        };r
      }
      val clock=reference(terminal.clk,true);val pred=reference(terminal.pred,false);val enabled=reference(terminal.en,false)
      require(registers(first.circuit).count(_.name==clock.name)==1)
      def stop(c:Circuit):Stop={var result:Stop=null;var matches=0
        visit(c){case x:Stop if x.name==terminal.name=>matches+=1;result=x;case _=>()}
        require(matches==1 && result.getClass==classOf[Stop] && result.ret==65 &&
          (result.name eq terminal.name) && (result.info eq terminal.info));result
      }
      def trigger(s:Stop):(Reference,Reference)={
        require(s.en.getClass==classOf[DoPrim]);val and=s.en.asInstanceOf[DoPrim]
        family(and.args);family(and.consts);require((and.op eq firrtl2.PrimOps.And) && and.args.size==2 && and.consts.isEmpty && (and.tpe eq pred.tpe))
        require(and.args.head.getClass==classOf[DoPrim]);val not=and.args.head.asInstanceOf[DoPrim]
        family(not.args);family(not.consts);require((not.op eq firrtl2.PrimOps.Not) && not.args.size==1 && not.consts.isEmpty && (not.tpe eq pred.tpe))
        (reference(not.args.head,false),reference(and.args(1),false))
      }
      val second=(new HandleFormalStatements).runTransform(first);val s2=stop(second.circuit);val p2=trigger(s2)
      require((s2.clk eq clock) && (p2._1 eq pred) && (p2._2 eq enabled))
      val third=firrtl2.passes.memlib.VerilogMemDelays.runTransform(second);val s3=stop(third.circuit);val p3=trigger(s3)
      require((s3.clk eq clock) && (p3._1 eq pred) && (p3._2 eq enabled))
      val fourth=firrtl2.passes.ResolveFlows.runTransform(third);val s4=stop(fourth.circuit);val p4=trigger(s4)
      def copied(a:Reference,b:Reference):Unit=require(!(a eq b) && (a.name eq b.name) && (a.tpe eq b.tpe) && (a.kind eq b.kind) && (b.flow eq firrtl2.SourceFlow))
      copied(clock,reference(s4.clk,true));copied(pred,p4._1);copied(enabled,p4._2)
      require(suffix(input,n)==n*3)
      val annotations=Seq(FirrtlCircuitAnnotation(input),TargetDirAnnotation(targetName))
      val official=(new PrepareAst).transform(annotations)
      val observer=new ObservedPrepareAst(n);val observed=observer.transform(checkedInputChain(input,annotations))
      new Parity().apply(official,observed)
      require(observer.evidence.startsWith("COMPLETE:DONE:NONE:"+Vector.fill(7)(n.toString).mkString(":")+":"))
      require(observer.anchorEvidence=="NONE")
      require(observer.formalEvidence=="COMPLETE:1:1:1:1")
      require(observer.budgetEvidence=="NONE" && observer.sizingEvidence=="NONE" && observer.consumerEvidence=="NONE")
      qualifyGrantRepair(input,observed,observer,n)
      require(graphChecks(state(observed).circuit)==4)
      count+=1
    }
    require(count==2);count
  }
  // Four actual producer/parity witnesses: ordinary kind x original order.
  // Each also runs four retained graph controls; no interpreter is constructed.
  private def selectionParityChecks(targetName:String):Int={
    var checks=0
    Vector(false,true).foreach{stopping=>Vector(false,true).foreach{reverse=>
      val text=source("print").linesIterator.filterNot(_.trim.startsWith("printf(")).mkString("\n")+"\n"
      val low=Compiler.toLowFirrtl(CircuitState(Parser.parse(text),Seq(TargetDirAnnotation(targetName)))).circuit
      val info=FileInfo("selection_witness 1:1");val format=StringLit("same format")
      val clock=Reference("clock",ClockType,firrtl2.PortKind,firrtl2.SourceFlow)
      val enabled=Reference("en",UIntType(IntWidth(1)),firrtl2.PortKind,firrtl2.SourceFlow)
      val nameA=new String("selection_a".toCharArray);val nameB=new String("selection_b".toCharArray)
      require(!(nameA eq nameB) && nameA!=nameB && nameA.nonEmpty && nameB.nonEmpty)
      def terminal(name:String):Statement=if(stopping)Stop(info,0,clock,enabled,name)
        else Print(info,format,Seq.empty,clock,enabled,name)
      val a=terminal(nameA);val b=terminal(nameB)
      val originals=if(reverse)Vector(b,a)else Vector(a,b)
      val input=body(low,s=>Block(Seq(s,originals(0),originals(1))))
      val first=(new AugmentPrintf).runTransform(CircuitState(input,Seq.empty))
      val regs=registers(first.circuit);require(regs.size==2)
      val consumers=Vector.newBuilder[Statement];var consumerCount=0
      visit(first.circuit){case x:Print if !stopping=>consumerCount+=1;require(consumerCount<=2);consumers+=x
        case x:Stop if stopping=>consumerCount+=1;require(consumerCount<=2);consumers+=x;case _=>()}
      val produced=consumers.result();require(produced.size==2)
      def name(x:Statement):String=x match{case p:Print=>p.name;case p:Stop=>p.name;case _=>throw new IllegalArgumentException("TINY_TERMINAL")}
      def originalClock(x:Statement):Expression=x match{case p:Print=>p.clk;case p:Stop=>p.clk;case _=>throw new IllegalArgumentException("TINY_TERMINAL")}
      def sameAttributes(original:Statement,consumer:Statement):Boolean=(original,consumer)match{
        case (p:Print,q:Print)=>(p.info eq q.info) && (p.string eq q.string) && (p.clk eq clock)
        case (p:Stop,q:Stop)=>(p.info eq q.info) && p.ret==q.ret && (p.clk eq clock)
        case _=>false
      }
      val oldClaims=Array(0,0);val selectedClaims=Array(0,0);var oldCollision=false
      originals.foreach{original=>var index=0;while(index<2){val consumer=produced(index)
        if(sameAttributes(original,consumer)){
          if(oldClaims(index)!=0)oldCollision=true;oldClaims(index)+=1
          if(name(original) eq name(consumer))selectedClaims(index)+=1
        };index+=1}}
      require(oldCollision && oldClaims.toVector==Vector(2,2) && selectedClaims.toVector==Vector(1,1))
      produced.foreach{consumer=>
        val matching=originals.filter(x=>name(x) eq name(consumer));require(matching.size==1)
        val original=matching.head;require(sameAttributes(original,consumer))
        val clk=originalClock(consumer);require(clk.getClass==classOf[Reference]);val delayed=clk.asInstanceOf[Reference]
        require((delayed.tpe eq ClockType) && (delayed.kind eq firrtl2.NodeKind) && (delayed.flow eq firrtl2.SourceFlow))
        val matchingRegs=regs.filter(_.name==delayed.name);require(matchingRegs.size==1)
        require((matchingRegs.head.info eq info) && (matchingRegs.head.clock eq originalClock(original)))
        var drivers=0
        visit(first.circuit){case c:Connect=>c.loc match{case r:Reference if r.name==delayed.name=>
          drivers+=1;require(c.expr eq originalClock(original));case _=>()};case _=>()}
        require(drivers==1)
      }
      val annotations=Seq(FirrtlCircuitAnnotation(input),TargetDirAnnotation(targetName))
      val official=(new PrepareAst).transform(annotations)
      val observer=new ObservedPrepareAst(2);val observed=observer.transform(checkedInputChain(input,annotations))
      new Parity().apply(official,observed)
      require(observer.evidence.startsWith("COMPLETE:DONE:NONE:2:2:2:2:2:2:2:"))
      require(observer.formalEvidence=="COMPLETE:0:0:0:0" && observer.anchorEvidence=="NONE" && observer.consumerEvidence=="NONE")
      require(observer.budgetEvidence=="NONE" && observer.sizingEvidence=="NONE")
      qualifyGrantRepair(input,observed,observer,2)
      require(graphChecks(state(observed).circuit)==4)
      checks+=1
    }}
    require(checks==4);checks
  }
  // Qualification counters are fixture-local scalars, never proof authority.
  private var grantParityChecks=0
  private def uniqueInput(input:Circuit,annotations:AnnotationSeq):Unit={
    family(annotations);var seen=0;var total=0
    annotations.foreach{a=>require(total<64);total+=1;a match{
      case FirrtlCircuitAnnotation(c)=>require(c eq input);seen+=1
      case _=>()
    }};require(seen==1)
  }
  private def checkedInputChain(input:Circuit,annotations:AnnotationSeq):AnnotationSeq={
    uniqueInput(input,annotations)
    require(annotations.exists(_.isInstanceOf[TargetDirAnnotation]))
    val obtained=GetFirrtlAst.transform(annotations);require(obtained eq annotations)
    uniqueInput(input,obtained)
    val withInfo=SetImplicitOutputInfo.transform(obtained)
    uniqueInput(input,withInfo);family(withInfo);require(withInfo.size==annotations.size)
    val a=annotations.iterator;val b=withInfo.iterator
    while(a.hasNext && b.hasNext)require(a.next() eq b.next())
    require(!a.hasNext && !b.hasNext);withInfo
  }
  private def inputChainSelfChecks(targetName:String):Int={
    var checks=0
    val circuit=Circuit(NoInfo,Seq(Module(NoInfo,"Chain",Seq.empty,EmptyStmt)),"Chain")
    val annotation=FirrtlCircuitAnnotation(circuit)
    checkedInputChain(circuit,Seq(annotation,TargetDirAnnotation(targetName)));checks+=1
    val bare:AnnotationSeq=Seq(annotation);val obtained=GetFirrtlAst.transform(bare)
    require(obtained eq bare);val withInfo=SetImplicitOutputInfo.transform(obtained)
    uniqueInput(circuit,withInfo);require(withInfo.size==3 && (withInfo.head eq annotation))
    require(withInfo(1)==firrtl2.stage.OutputFileAnnotation("Chain") && withInfo(2)==TargetDirAnnotation("test_run_dir/Chain"));checks+=1
    def rejected(input:Circuit,as:AnnotationSeq):Unit={var bad=false
      try{uniqueInput(input,as)}catch{case _:IllegalArgumentException=>bad=true};require(bad);checks+=1}
    val copied=circuit.copy();require(!(copied eq circuit))
    rejected(circuit,Seq(FirrtlCircuitAnnotation(copied)))
    rejected(circuit,Seq(annotation,annotation))
    rejected(circuit,Seq(annotation,FirrtlCircuitAnnotation(copied)))
    rejected(copied,Seq(annotation));require(checks==6);checks
  }
  private def grantLifecycleSelfChecks(targetName:String):Int={
    var checks=0
    val before=Compiler.toLowFirrtl(CircuitState(Parser.parse(source("print")),Seq(TargetDirAnnotation(targetName)))).circuit
    def prepare(observer:ObservedPrepareAst):AnnotationSeq={
      val input=Seq(FirrtlCircuitAnnotation(before),TargetDirAnnotation(targetName))
      observer.transform(checkedInputChain(before,input))
    }
    def rejected(reason:String)(f: =>Unit):Unit={var code="NONE"
      try{f}catch{case e:IllegalArgumentException=>code=ObservedPrepareAst.provenanceReason(e)}
      require(code==reason)
    }
    locally{val observer=new ObservedPrepareAst(1);val outer=prepare(observer);val prepared=state(outer)
      rejected("UNAVAILABLE"){ClockInitRepresentationRepair.applyWithProvenance(before,prepared,outer,1,null)};checks+=1}
    Vector("BEFORE","STATE","OUTER","COUNT").foreach{kind=>
      val observer=new ObservedPrepareAst(1);val outer=prepare(observer);val prepared=state(outer);val grant=observer.takeGrant();require(grant!=null)
      val copiedOuter:AnnotationSeq=outer.iterator.toList;require(outer.nonEmpty && !(copiedOuter eq outer))
      val copiedBefore=before.copy();require(!(copiedBefore eq before))
      val copiedState=prepared.copy();require(!(copiedState eq prepared))
      rejected(if(kind=="COUNT")"COUNT"else"CONTEXT"){
        ClockInitRepresentationRepair.applyWithProvenance(if(kind=="BEFORE")copiedBefore else before,
          if(kind=="STATE")copiedState else prepared,if(kind=="OUTER")copiedOuter else outer,
          if(kind=="COUNT")2 else 1,grant)
      }
      rejected("REPLAY"){ClockInitRepresentationRepair.applyWithProvenance(before,prepared,outer,1,grant)};checks+=1
    }
    locally{val observer=new ObservedPrepareAst(1);val outer=prepare(observer);val prepared=state(outer);val grant=observer.takeGrant();require(grant!=null)
      prepare(observer)
      rejected("REVOKED"){ClockInitRepresentationRepair.applyWithProvenance(before,prepared,outer,1,grant)}
      rejected("REPLAY"){ClockInitRepresentationRepair.applyWithProvenance(before,prepared,outer,1,grant)};checks+=1}
    locally{val observer=new ObservedPrepareAst(2)
      val both=Compiler.toLowFirrtl(CircuitState(Parser.parse(source("both")),Seq(TargetDirAnnotation(targetName)))).circuit
      val outer=observer.transform(checkedInputChain(both,Seq(FirrtlCircuitAnnotation(both),TargetDirAnnotation(targetName))))
      val prepared=state(outer);val grant=observer.takeGrant();require(grant!=null)
      prepare(observer)
      require(observer.evidence.startsWith("UNAVAILABLE:DISCOVERY:COUNT:") && observer.takeGrant()==null)
      rejected("REVOKED"){ClockInitRepresentationRepair.applyWithProvenance(both,prepared,outer,2,grant)}
      rejected("REPLAY"){ClockInitRepresentationRepair.applyWithProvenance(both,prepared,outer,2,grant)};checks+=1}
    locally{val observer=new ObservedPrepareAst(1);val outer=prepare(observer);val prepared=state(outer)
      val grant=observer.takeGrant();require(grant!=null)
      observer.transform(Seq(FirrtlCircuitAnnotation(before),FirrtlCircuitAnnotation(before),TargetDirAnnotation(targetName)))
      require(observer.takeGrant()==null)
      rejected("REVOKED"){ClockInitRepresentationRepair.applyWithProvenance(before,prepared,outer,1,grant)}
      rejected("REPLAY"){ClockInitRepresentationRepair.applyWithProvenance(before,prepared,outer,1,grant)};checks+=1}
    require(checks==8);checks
  }
  // Bounded, fixture-only oracle: explicit constructor fields, no production
  // Uses callbacks, Budget counters, identity deduplication or observer walkers.
  // Every occurrence in the complete official prepared circuit is counted.
  private var p54WorkParityChecks=0
  private def p54WorkUnavailable(observer:ObservedPrepareAst):Unit={
    require(observer.p54WorkEvidence=="UNAVAILABLE");p54WorkParityChecks+=1
  }
  private def p54WorkParity(official:AnnotationSeq,observer:ObservedPrepareAst):Unit={
    var visits=0L;var expressionNodes=0L;var expressionEdges=0L;var roots=0L
    def expression(e:Expression,depth:Int):Unit={
      require(e!=null && nodes(e.getClass) && depth<=64 && expressionNodes<16384);expressionNodes+=1
      def child(x:Expression):Unit={expressionEdges+=1;expression(x,depth+1)}
      e match{
        case _:Reference|_:UIntLiteral|_:SIntLiteral=>()
        case x:SubField=>child(x.expr)
        case x:SubIndex=>child(x.expr)
        case x:SubAccess=>child(x.expr);child(x.index)
        case x:Mux=>child(x.cond);child(x.tval);child(x.fval)
        case x:ValidIf=>child(x.cond);child(x.value)
        case x:DoPrim=>family(x.args);require(x.args.size<=64);x.args.foreach(child)
        case _=>throw new IllegalArgumentException("TINY_P54_EXPRESSION")
      }
    }
    def root(e:Expression):Unit={roots+=1;expression(e,0)}
    def statement(s:Statement,depth:Int):Unit={
      require(s!=null && (nodes(s.getClass) || (s eq EmptyStmt)) && depth<=64 && visits<4096);visits+=1
      s match{
        case x:Block=>family(x.stmts);require(x.stmts.size<=4096);x.stmts.foreach(statement(_,depth+1))
        case x:Conditionally=>root(x.pred);statement(x.conseq,depth+1);statement(x.alt,depth+1)
        case x:DefRegister=>root(x.clock);root(x.reset);root(x.init)
        case x:DefNode=>root(x.value)
        case x:Connect=>root(x.loc);root(x.expr)
        case x:IsInvalid=>root(x.expr)
        case x:Print=>root(x.clk);root(x.en);family(x.args);require(x.args.size<=64);x.args.foreach(root)
        case x:Stop=>root(x.clk);root(x.en)
        case _:DefWire=>()
        case EmptyStmt=>()
        case _=>throw new IllegalArgumentException("TINY_P54_STATEMENT")
      }
    }
    val circuit=state(official).circuit;family(circuit.modules);require(circuit.modules.size<=8)
    circuit.modules.foreach{
      case m:Module=>require(m.getClass==classOf[Module]);visits+=1;family(m.ports);require(m.ports.size<=64)
        m.ports.foreach(p=>require(p.getClass==classOf[Port]));visits+=m.ports.size;statement(m.body,0)
      case _=>throw new IllegalArgumentException("TINY_P54_MODULE")
    }
    val fields=observer.p54WorkEvidence.split(":",-1)
    require(fields.length==10 && fields(0)=="AVAILABLE" && fields(1)=="P54")
    val values=fields.drop(2).map{x=>require(x.nonEmpty && x.length<=18 && x.forall(c=>c>='0' && c<='9'));x.toLong}
    require(values(0)==visits && values(4)==expressionNodes && values(5)==expressionEdges && values(7)==roots)
    require(expressionNodes==expressionEdges+roots && roots>0)
    require(values(1)==values(2)+values(3)+values(4)+values(5)+values(6))
    p54WorkParityChecks+=1
  }
  private def p54WorkLifecycleChecks(targetName:String):Unit={
    val before=p54WorkParityChecks
    def low(mode:String):Circuit=Compiler.toLowFirrtl(CircuitState(Parser.parse(source(mode)),Seq(TargetDirAnnotation(targetName)))).circuit
    val print=low("print");val both=low("both")
    def chain(c:Circuit):AnnotationSeq=checkedInputChain(c,Seq(FirrtlCircuitAnnotation(c),TargetDirAnnotation(targetName)))
    val input=chain(print);val official=(new PrepareAst).transform(input)
    val observer=new ObservedPrepareAst(1);p54WorkUnavailable(observer)
    def success():Unit={val observed=observer.transform(input);new Parity().apply(official,observed);p54WorkParity(official,observer)}
    success();val firstEvidence=observer.p54WorkEvidence;success()
    require(observer.p54WorkEvidence==firstEvidence)
    val rejectedInput=chain(both);val rejectedOfficial=(new PrepareAst).transform(rejectedInput)
    val rejectedOutput=observer.transform(rejectedInput);new Parity().apply(rejectedOfficial,rejectedOutput)
    require(observer.evidence.startsWith("UNAVAILABLE:DISCOVERY:COUNT:"));p54WorkUnavailable(observer)
    success()
    observer.transform(Seq(FirrtlCircuitAnnotation(print),FirrtlCircuitAnnotation(print),TargetDirAnnotation(targetName)))
    p54WorkUnavailable(observer)
    observer.transform(Seq(TargetDirAnnotation(targetName)));p54WorkUnavailable(observer)
    success();require(observer.p54WorkEvidence==firstEvidence)
    require(p54WorkParityChecks-before==8)
  }
  private def originalInitErrors(c:Circuit,n:Int):Unit={
    val errors=try{firrtl2.passes.CheckTypes.run(c);Vector.empty[Throwable]}catch{
      case e:firrtl2.passes.PassExceptions=>e.exceptions.toVector
      case e:firrtl2.passes.PassException=>Vector(e)
    }
    require(errors.count(_.getClass.getName=="firrtl2.passes.CheckTypes$InvalidRegInit")==n)
    require(errors.forall(e=>Set("firrtl2.passes.CheckTypes$InvalidRegInit","firrtl2.passes.PassException")(e.getClass.getName)))
    require(errors.size==n+(if(n>1)1 else 0))
  }
  private def initOnly(before:Circuit,after:Circuit,expected:Int):Unit={
    family(before.modules);family(after.modules);require(before.modules.size<=8 && before.modules.size==after.modules.size)
    require((before.info eq after.info) && (before.main eq after.main));var changed=0;var visits=0
    def statement(a:Statement,b:Statement,depth:Int):Unit={require(depth<=256 && visits<4096);visits+=1
      if(!(a eq b))a match{
        case x:Block=>require(b.getClass==classOf[Block]);val y=b.asInstanceOf[Block]
          family(x.stmts);family(y.stmts);require(x.stmts.size==y.stmts.size && x.stmts.size<=4096)
          x.stmts.zip(y.stmts).foreach{case(p,q)=>statement(p,q,depth+1)}
        case x:DefRegister=>require(b.getClass==classOf[DefRegister]);val y=b.asInstanceOf[DefRegister]
          require((x.tpe eq ClockType) && (x.info eq y.info) && (x.name eq y.name) && (x.tpe eq y.tpe) &&
            (x.clock eq y.clock) && (x.reset eq y.reset))
          require(y.init.getClass==classOf[DoPrim]);val p=y.init.asInstanceOf[DoPrim]
          family(p.args);family(p.consts);require((p.op eq firrtl2.PrimOps.AsClock) && (p.tpe eq ClockType) &&
            p.args.size==1 && p.consts.isEmpty && (p.args.head eq x.init));changed+=1
        case _=>require(false)
      }
    }
    before.modules.zip(after.modules).foreach{case(a:Module,b:Module)=>
      require((a.info eq b.info) && (a.name eq b.name) && (a.ports eq b.ports));statement(a.body,b.body,0)
      case(a,b)=>require(a eq b)}
    require(changed==expected)
  }
  private def symbolDependencyParity(before:Circuit,after:Circuit):Unit={
    val old=SymbolTable(before,Seq.empty,allowCycles=false);val fresh=SymbolTable(after,Seq.empty,allowCycles=false)
    require(old.size<=4096 && old.size==fresh.size)
    val a=old.symbols.toVector.sortBy(_.name);val b=fresh.symbols.toVector.sortBy(_.name)
    require(a.size==b.size)
    a.zip(b).foreach{case(x,y)=>
      require(x.name==y.name && x.dataSize==y.dataSize && x.dataType==y.dataType && x.dataKind==y.dataKind &&
        x.bitWidth==y.bitWidth && x.slots==y.slots && x.index==y.index && x.cardinalNumber==y.cardinalNumber)
      new Parity().value(x.firrtlType,y.firrtlType);new Parity().value(x.info,y.info)
      require(old.childrenOf.getEdges(x).toVector.map(_.name).sorted==fresh.childrenOf.getEdges(y).toVector.map(_.name).sorted)
      require(old.parentsOf.getEdges(x).toVector.map(_.name).sorted==fresh.parentsOf.getEdges(y).toVector.map(_.name).sorted)
    }
    require(old.inputPortsNames.toSet==fresh.inputPortsNames.toSet && old.outputPortsNames.toSet==fresh.outputPortsNames.toSet &&
      old.registerNames.toSet==fresh.registerNames.toSet && old.instanceNames.toSet==fresh.instanceNames.toSet &&
      old.orphans.map(_.name).toSet==fresh.orphans.map(_.name).toSet)
  }
  private def qualifyGrantRepair(before:Circuit,outer:AnnotationSeq,observer:ObservedPrepareAst,expected:Int,countLegacy:Boolean=true):CircuitState={
    val prepared=state(outer);require(prepared.productArity==3 && (prepared.renames eq None))
    originalInitErrors(prepared.circuit,expected)
    val grant=observer.takeGrant();require(grant!=null && observer.takeGrant()==null)
    val result=ClockInitRepresentationRepair.applyWithProvenance(before,prepared,outer,expected,grant)
    require((state(outer) eq prepared) && result.state.productArity==3 && result.corrected==expected && result.noninterferenceTicks>0 && (result.state.annotations eq prepared.annotations) && (result.state.renames eq None))
    initOnly(prepared.circuit,result.state.circuit,expected)
    require(firrtl2.passes.CheckTypes.run(result.state.circuit) eq result.state.circuit)
    require(firrtl2.passes.CheckFlows.run(result.state.circuit) eq result.state.circuit)
    symbolDependencyParity(prepared.circuit,result.state.circuit)
    require(graphChecks(result.state.circuit)==4)
    var replay=false;try{ClockInitRepresentationRepair.applyWithProvenance(before,prepared,outer,expected,grant)}
      catch{case e:IllegalArgumentException=>replay=ObservedPrepareAst.provenanceReason(e)=="REPLAY"}
    require(replay);if(countLegacy)grantParityChecks+=1
    result.state
  }
  // Three real metadata records enter before the verified pipeline, never after a grant.
  private def dedupRecord(c:CircuitState,mode:String):DedupedResult={
    family(c.annotations);require(c.annotations.size<=64)
    var found:DedupedResult=null;var count=0
    c.annotations.foreach {a=>if(a.getClass==classOf[DedupedResult]){found=a.asInstanceOf[DedupedResult];count+=1}}
    require(count==1 && found!=null && found.original.getClass==classOf[ModuleTarget])
    require(found.original.circuit==c.circuit.main)
    family(found.targets);require(found.targets.size==2)
    val first=found.targets(0);val second=found.targets(1);family(first);family(second)
    require(first.size==1 && (first.head.asInstanceOf[AnyRef] eq found.original))
    if(mode=="INSTANCE"){
      require(found.original.module=="HistoricalAbsent" && !c.circuit.modules.exists(_.name==found.original.module))
      require(found.duplicate.getClass==classOf[Some[Any]] && found.duplicate.get.getClass==classOf[InstanceTarget])
      require(found.index==0.0)
      val target=found.duplicate.get.asInstanceOf[InstanceTarget]
      require(target.circuit==c.circuit.main && target.module==c.circuit.main && target.path.isEmpty &&
        target.instance=="historical_instance" && target.ofModule=="HistoricalAbsent")
    }else{
      require(found.original.module==c.circuit.main && registers(c.circuit).nonEmpty)
      if(mode=="MODULE"){
        require(found.duplicate.getClass==classOf[Some[Any]] && found.duplicate.get.getClass==classOf[ModuleTarget])
        val target=found.duplicate.get.asInstanceOf[ModuleTarget]
        require(target.circuit==c.circuit.main && target.module==c.circuit.main && found.index==1.0)
      }else require(mode=="NONE" && (found.duplicate eq None) && found.index == -1.0)
    }
    if(found.duplicate eq None)require(second.isEmpty)
    else require(second.size==1 && (second.head.asInstanceOf[AnyRef] eq found.duplicate.get.asInstanceOf[AnyRef]))
    found
  }
  private def dedupMetadataParityChecks(targetName:String):Int={
    // Five mandatory negative prerequisites; the returned count remains three real cases.
    var negatives=0
    def rejected(a:Any,b:Any):Unit={var failed=false;try{new Parity().value(a,b)}catch{
      case _:IllegalArgumentException=>failed=true};require(failed);negatives+=1}
    val target=ModuleTarget("Parity","Parity")
    val record=DedupedResult(target,Some(target),0.0)
    rejected(record,record.copy(index=1.0))
    rejected(record,record.copy(index = -0.0))
    val nan=record.copy(index=Double.NaN);rejected(nan,nan)
    rejected(record,record.copy(original=ModuleTarget("Parity","Changed")))
    val unknown=new DedupedResult(target,Some(target),0.0){};rejected(unknown,unknown)
    require(negatives==5)
    var checks=0
    Vector("MODULE","INSTANCE","NONE").foreach {mode=>
      val input=Compiler.toLowFirrtl(CircuitState(Parser.parse(source(if(mode=="INSTANCE")"stop"else"print")),Seq(TargetDirAnnotation(targetName)))).circuit
      val selected=ModuleTarget(input.main,input.main)
      val seeded=if(mode=="MODULE")DedupedResult(selected,Some(selected),1.0)
        else if(mode=="INSTANCE")DedupedResult(ModuleTarget(input.main,"HistoricalAbsent"),
          Some(InstanceTarget(input.main,input.main,Nil,"historical_instance","HistoricalAbsent")),0.0)
        else DedupedResult(selected,None,-1.0)
      val annotations=Seq(FirrtlCircuitAnnotation(input),TargetDirAnnotation(targetName),seeded)
      val chain=checkedInputChain(input,annotations)
      val official=(new PrepareAst).transform(chain)
      val observer=new ObservedPrepareAst(1);val observed=observer.transform(chain)
      new Parity().apply(official,observed)
      require(observer.evidence.startsWith("COMPLETE:DONE:NONE:1:1:1:1:1:1:1:"))
      require(observer.anchorEvidence=="NONE" && observer.consumerEvidence=="NONE" && observer.formalEvidence=="COMPLETE:0:0:0:0")
      require(observer.budgetEvidence=="NONE" && observer.sizingEvidence=="NONE")
      dedupRecord(state(official),mode)
      val prepared=state(observed);val record=dedupRecord(prepared,mode)
      val groups=record.targets;val first=groups(0);val second=groups(1)
      val original=record.original;val duplicate=record.duplicate
      var strictRejected=false
      try{ClockInitRepresentationRepair(input,prepared.circuit,prepared.annotations,1)}catch{
        case e:IllegalArgumentException=>strictRejected=ClockInitRepresentationRepair.guardCode(e)=="ANNOTATION_SHAPE" &&
          ClockInitRepresentationRepair.annotationShapeEvidence(e)==(if(mode=="INSTANCE")"INSTANCE_TARGET"else"MODULE_SELECTED")}
      require(strictRejected)
      val repaired=qualifyGrantRepair(input,observed,observer,1,countLegacy=false)
      require((repaired.annotations eq prepared.annotations) && (dedupRecord(repaired,mode) eq record))
      require((record.targets eq groups) && (record.targets(0) eq first) && (record.targets(1) eq second) &&
        (record.original eq original) && (record.duplicate eq duplicate))
      require(first.head.asInstanceOf[AnyRef] eq original)
      if(duplicate.nonEmpty)require(second.head.asInstanceOf[AnyRef] eq duplicate.get.asInstanceOf[AnyRef])
      checks+=1
    }
    require(checks==3);checks
  }
  // Comparator-only malformed pairs never enter a preparation pipeline.
  private def combinationalPathParitySelfChecks():Int={
    var checks=0
    def rejected(a:Any,b:Any):Unit={var bad=false;try{new Parity().value(a,b)}catch{
      case _:IllegalArgumentException=>bad=true};require(bad);checks+=1}
    val top=ModuleTarget("PathParity","PathParity")
    val sink=top.ref("out");val a=top.ref("a");val b=top.ref("b")
    val path=CombinationalPath(sink,List(a,b))
    new Parity().value(path,path.copy());checks+=1
    rejected(path,path.copy(sink=top.ref("other")))
    rejected(path,path.copy(sources=List(a,top.ref("other"))))
    rejected(path,path.copy(sources=List(b,a)))
    val other=path.copy(sink=top.ref("other"))
    rejected(List(path,other),List(other,path))
    val subclass=new CombinationalPath(sink,List(a,b)){};rejected(subclass,subclass)
    rejected(a,a.copy(module="Other"))
    require(checks==7);checks
  }
  private def pathRecords(as:AnnotationSeq):Vector[CombinationalPath]={
    family(as);require(as.size<=64)
    val result=as.collect{case p:CombinationalPath=>require(p.getClass==classOf[CombinationalPath]);p}.toVector
    require(result.nonEmpty && result.size<=4);result
  }
  // Canonicalization is confined to tiny recomputation comparisons; production
  // annotations, source order and endpoint identities are never rewritten.
  private def pathEdges(as:AnnotationSeq,main:String):Vector[(String,Vector[String])]={
    pathRecords(as).map{p=>
      def endpoint(r:ReferenceTarget):String={require(r!=null && r.getClass==classOf[ReferenceTarget])
        family(r.path);family(r.component)
        require(r.circuit==main && r.module==main && r.path.isEmpty && r.component.isEmpty &&
          r.ref.nonEmpty && r.ref.length<=64);r.ref}
      family(p.sources);require(p.sources.nonEmpty && p.sources.size<=4)
      endpoint(p.sink)->p.sources.map(endpoint).toVector.sorted
    }.sortBy(_._1)
  }
  // An independent producer establishes expected edges before the observer.
  // PrepareAst itself produces admitted records. Every fixture retains q.
  private def combinationalPathParityChecks(targetName:String):Int={
    var checks=0
    Vector("DIRECT","BINARY","TWO_SINKS").foreach{mode=>
      val base=source(if(mode=="BINARY")"stop"else"print")
      // Keep the original out <= q observable so lowering cannot erase q.
      val ports="    output out : UInt<1>\n    output path_out : UInt<1>\n"+
        (if(mode=="TWO_SINKS")"    output tap : UInt<1>\n"else "")
      val connections="    out <= q\n    path_out <= "+
        (if(mode=="BINARY")"or(en, stop_en)"else "en")+"\n"+
        (if(mode=="TWO_SINKS")"    tap <= stop_en\n"else "")
      val text=base.replace("    output out : UInt<1>\n",ports).replace("    out <= q\n",connections)
      val input=Compiler.toLowFirrtl(CircuitState(Parser.parse(text),Seq(TargetDirAnnotation(targetName)))).circuit
      val produced=(new CheckCombLoops).runTransform(CircuitState(input,Seq.empty))
      require(produced.circuit eq input)
      val expected=if(mode=="DIRECT")Vector("path_out"->Vector("en"))
        else if(mode=="BINARY")Vector("path_out"->Vector("en","stop_en"))
        else Vector("path_out"->Vector("en"),"tap"->Vector("stop_en"))
      require(pathEdges(produced.annotations,input.main)==expected)
      // PrepareAst includes CheckCombLoops and appends its own records. The
      // independent producer above is an oracle only; seeding it would duplicate
      // summaries. Let the actual official/observed pipeline produce metadata.
      val annotations:AnnotationSeq=Seq(FirrtlCircuitAnnotation(input),TargetDirAnnotation(targetName))
      val chain=checkedInputChain(input,annotations)
      val official=(new PrepareAst).transform(chain)
      val observer=new ObservedPrepareAst(1);val observed=observer.transform(chain)
      new Parity().apply(official,observed)
      require(observer.evidence.startsWith("COMPLETE:DONE:NONE:1:1:1:1:1:1:1:"))
      require(observer.anchorEvidence=="NONE" && observer.consumerEvidence=="NONE" && observer.formalEvidence=="COMPLETE:0:0:0:0")
      require(observer.budgetEvidence=="NONE" && observer.sizingEvidence=="NONE")
      val prepared=state(observed);val records=pathRecords(prepared.annotations)
      require(pathEdges(prepared.annotations,input.main)==expected)
      val sinks=records.map(_.sink);val sources=records.map(_.sources)
      val endpoints=sources.map(_.toVector)
      var strict=false
      try{ClockInitRepresentationRepair(input,prepared.circuit,prepared.annotations,1)}catch{
        case e:IllegalArgumentException=>strict=ClockInitRepresentationRepair.guardCode(e)=="ANNOTATION_SHAPE" &&
          ClockInitRepresentationRepair.annotationShapeEvidence(e)=="ANNOTATION_OTHER" &&
          ClockInitRepresentationRepair.annotationOtherOwnerEvidence(e)=="COMBINATIONAL_PATH"}
      require(strict)
      val repaired=qualifyGrantRepair(input,observed,observer,1,countLegacy=false)
      require(repaired.annotations eq prepared.annotations)
      val retained=pathRecords(repaired.annotations);require(retained.size==records.size)
      records.indices.foreach{i=>
        require((retained(i) eq records(i)) && (retained(i).sink eq sinks(i)) && (retained(i).sources eq sources(i)))
        require(retained(i).sources.size==endpoints(i).size)
        retained(i).sources.indices.foreach{j=>require(retained(i).sources(j) eq endpoints(i)(j))}
      }
      // Tiny test only: recompute both sides without carrying old summaries.
      val beforeGraph=(new CheckCombLoops).runTransform(CircuitState(prepared.circuit,Seq.empty))
      val afterGraph=(new CheckCombLoops).runTransform(CircuitState(repaired.circuit,Seq.empty))
      require(pathEdges(beforeGraph.annotations,input.main)==expected && pathEdges(afterGraph.annotations,input.main)==expected)
      require(pathEdges(repaired.annotations,input.main)==expected)
      checks+=1
    }
    require(checks==3);checks
  }
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
      require(args.length==9 && Set("official","cached")(args(0)))
      require(loaded(classOf[ObservedPrepareAst],args(1))==args(2))
      require(loaded(ObservedPrepareAst.getClass,args(1))==args(3))
      require(loaded(ObservedScheduleIdentity.getClass,args(1))==args(4))
      require(loaded(ClockInitRepresentationRepair.getClass,args(1))==args(8))
      require(loaded(classOf[SymbolTable],args(5))==args(6) && loaded(SymbolTable.getClass,args(5))==args(7))
      ObservedScheduleIdentity.verifyAnnotationOwner()
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
        grantParityChecks=0;p54WorkParityChecks=0
        phase="SELFTEST";val selfChecks=ObservedPrepareAst.selfChecks();require(selfChecks==69)
        val parityChecks=paritySelfChecks();require(parityChecks==11)
        val combinationalPathParityChecksCount=combinationalPathParitySelfChecks();require(combinationalPathParityChecksCount==7)
        val inputChainChecks=inputChainSelfChecks(targetName);require(inputChainChecks==6)
        val grantLifecycleChecks=grantLifecycleSelfChecks(targetName);require(grantLifecycleChecks==8)
        val grantChecks=ObservedPrepareAst.grantSelfChecks();require(grantChecks==72)
        val annotationShapeChecks=ClockInitRepresentationRepair.annotationShapeDiagnosticSelfChecks();require(annotationShapeChecks==25)
        val ownerChecks=ClockInitRepresentationRepair.annotationInstanceOwnerDiagnosticSelfChecks();require(ownerChecks==22)
        val dedupMetadataChecks=ClockInitRepresentationRepair.dedupMetadataSelfChecks();require(dedupMetadataChecks==82)
        val otherOwnerChecks=ClockInitRepresentationRepair.annotationOtherOwnerDiagnosticSelfChecks();require(otherOwnerChecks==23)
        val combinationalPathChecks=ClockInitRepresentationRepair.combinationalPathSelfChecks();require(combinationalPathChecks==99)
        val usesWorkChecks=ClockInitRepresentationRepair.usesWorkDiagnosticSelfChecks();require(usesWorkChecks==67)
        val workV2Checks=ClockInitRepresentationRepair.workV2SelfChecks();require(workV2Checks==66)
        val lookupChecks=ClockInitRepresentationRepair.selectedLookupSelfChecks();require(lookupChecks==1301)
        val p54WorkChecks=ObservedPrepareAst.p54WorkSelfChecks();require(p54WorkChecks==55)
        val sizingChecks=ObservedPrepareAst.sizingSelfChecks();require(sizingChecks==56)
        val quotaChecks=ObservedPrepareAst.quotaSelfChecks();require(quotaChecks==6)
        val consumerChecks=ObservedPrepareAst.consumerSelfChecks();require(consumerChecks==24)
        val formalChecks=ObservedPrepareAst.formalSelfChecks();require(formalChecks==58)
        val anchorChecks=ObservedPrepareAst.anchorSelfChecks();require(anchorChecks==31)
        val selectionChecks=ObservedPrepareAst.selectionSelfChecks();require(selectionChecks==39)
        phase="OBSERVED_FAILURE";val consumerParityChecks=consumerParityCheck(targetName);require(consumerParityChecks==1)
        val formalParity= formalParityChecks(targetName);require(formalParity==2)
        val selectionParity=selectionParityChecks(targetName);require(selectionParity==4)
        val dedupMetadataParity=dedupMetadataParityChecks(targetName);require(dedupMetadataParity==3)
        val combinationalPathParity=combinationalPathParityChecks(targetName);require(combinationalPathParity==3)
        p54WorkLifecycleChecks(targetName)
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
            phase="OBSERVED";val observer=new ObservedPrepareAst(n);val observed=observer.transform(checkedInputChain(input,as))
            phase="PARITY";new Parity().apply(official,observed)
            p54WorkParity(official,observer)
            val expected="COMPLETE:DONE:NONE:"+Vector.fill(7)(n.toString).mkString(":")+":"
            require(observer.evidence.startsWith(expected))
            require(observer.anchorEvidence=="NONE")
            require(observer.formalEvidence=="COMPLETE:0:0:0:0")
            require(observer.consumerEvidence=="NONE")
            require(observer.budgetEvidence=="NONE" && observer.sizingEvidence=="NONE")
            if(kind=="recycled")require(registers(state(observed).circuit).exists(_.name==firstName))
            val failureParity=if(kind=="base"){
              phase="OBSERVED_FAILURE";val rejected=new ObservedPrepareAst(n+1)
              val unchangedOutput=rejected.transform(as)
              phase="PARITY";new Parity().apply(official,unchangedOutput)
              require(rejected.evidence.startsWith("UNAVAILABLE:DISCOVERY:COUNT:0:0:0:0:0:0:0:"))
              p54WorkUnavailable(rejected)
              require(rejected.anchorEvidence=="NONE")
              require(rejected.formalEvidence=="UNAVAILABLE:0:0:0:0")
              require(rejected.consumerEvidence=="NONE")
              require(rejected.budgetEvidence=="NONE" && rejected.sizingEvidence=="NONE");1
            }else 0
            qualifyGrantRepair(input,observed,observer,n)
            phase="SUFFIX";val relations=if(kind=="base")suffix(low,n)else 0
            phase="GRAPH";val graphs=if(kind=="base")graphChecks(state(observed).circuit)else 0
            "OBSERVED_PREPARE_CASE_V1 mode="+mode+" kind="+kind+" parity=true records="+n+" suffixChecks="+relations+" graphChecks="+graphs+" observerChecks="+selfChecks+" parityChecks="+parityChecks+" failureParityChecks="+failureParity+" sizingChecks="+sizingChecks+" quotaChecks="+quotaChecks+" consumerChecks="+consumerChecks+" consumerParityChecks="+consumerParityChecks+" formalChecks="+formalChecks+" formalParityChecks="+formalParity+" anchorChecks="+anchorChecks+" selectionChecks="+selectionChecks+" selectionParityChecks="+selectionParity+" inputChainChecks="+inputChainChecks+" grantChecks="+grantChecks+" grantParityChecks=15 grantLifecycleChecks="+grantLifecycleChecks+" annotationShapeChecks="+annotationShapeChecks+" ownerChecks="+ownerChecks+" dedupMetadataChecks="+dedupMetadataChecks+" dedupMetadataParityChecks="+dedupMetadataParity+" otherOwnerChecks="+otherOwnerChecks+" combinationalPathChecks="+combinationalPathChecks+" combinationalPathParitySelfChecks="+combinationalPathParityChecksCount+" combinationalPathParityChecks="+combinationalPathParity+" usesWorkChecks="+usesWorkChecks+" workV2Checks="+workV2Checks+" lookupChecks="+lookupChecks+" p54WorkChecks="+p54WorkChecks+" p54WorkParityChecks=20 stateFields=3 form=ABSENT_IN_PINNED_API renames=NONE evidence="+observer.evidence
          }
        }
        require(grantParityChecks==15)
        require(p54WorkParityChecks==20)
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

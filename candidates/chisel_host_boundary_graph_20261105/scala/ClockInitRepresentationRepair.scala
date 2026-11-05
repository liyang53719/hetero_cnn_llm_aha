package chiseltest.simulator

import firrtl2.{AnnotationSeq,CircuitState,NodeKind,PortKind,SourceFlow}
import firrtl2.ir._
import firrtl2.annotations._

/** Prepared-AST-only, fail-closed initializer representation correction.
  * No lowering, evaluation, external output, annotation updates or state changes.
  */
object ClockInitRepresentationRepair {
  final case class Result(circuit:Circuit,corrected:Int,noninterferenceTicks:Int=0)
  val GuardCodes:Set[String]=Set("PROVENANCE","BOUND","TYPE","INFO","STRUCTURE","DUPLICATE","COUNT","SHAPE",
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
    def work:Int=n
    var phase="INDEX_BEFORE"
    def bound(p:Boolean,reason:String):Unit=if(!p){
      val error=new IllegalArgumentException("BOUND")
      error.addSuppressed(new BoundEvidence(reason+":"+phase+":"+n));throw error
    }
    def tick():Unit={n+=1;bound(n<=5000000,"GLOBAL_WORK")}
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
  private def isZero(e:Expression):Boolean=e match {
    case UIntLiteral(v,IntWidth(w))=>v==0 && w==1
    case _=>false
  }
  private final case class Use(statement:Statement,root:Expression,direct:Boolean)
  // Keep the official parser, but bound its recursive suffix tokenizer before
  // calling it. This is an explicit conservative resource-admission restriction,
  // not a measurement of its actual allocation and not a new semantic parser.
  private def reserveNamed(name:String,a:Aux):Unit={
    val n=name.length;require(n>0 && n<=4096)
    var d=0;var i=0
    while(i<n){a.charge(AX.Equal,3);val c=name.charAt(i);if(c=='.' || c=='[' || c==']')d+=1;i+=1}
    require(d<=n)
    val linear=Math.addExact(256L,Math.addExact(Math.multiplyExact(2L,n.toLong),255L)/256L)
    var k=1L
    while(k<=d.toLong+1L){
      val quadratic=Math.multiplyExact(256L,Math.subtractExact(Math.multiplyExact(2L,k),1L))
      a.transient(Math.addExact(quadratic,linear));k+=1L
    }
    // Covers the bounded tokenizer scans, copying and delimiter comparisons.
    a.charge(AX.Equal,Math.multiplyExact(16L,Math.multiplyExact(n.toLong,d.toLong+1L)))
  }
  private def checkedNamed(c:ComponentName,a:Aux):ReferenceTarget={
    reserveNamed(c.name,a)
    a.namedConversions+=1
    c.toTarget
  }
  private def boundedSize[A](xs:Seq[A],cap:Int,reason:String,a:Aux,b:Budget):Int={
    val it=a.iter(xs);var n=0
    while(it.hasNext){b.bound(n<cap,reason);a.charge(AX.Probe);it.next();n+=1};n
  }
  private def checkStreamingAnnotations(as:AnnotationSeq,selected:Selected,modules:Modules,circuit:String,b:Budget,a:Aux):Unit={
    boundedSize(as,100000,"ANNOTATIONS",a,b)
    def target(t:Target):Unit={
      b.tick()
      t match {
        case r:ReferenceTarget=>
          b.name(r.circuit);b.name(r.module);b.name(r.ref)
          boundedSize(r.path,64,"TARGET_PATH",a,b);boundedSize(r.component,64,"TARGET_COMPONENT",a,b)
          val path=a.iter(r.path);var module=r.module
          while(path.hasNext){a.charge(AX.Probe);val pair=path.next();b.name(pair._1.value);b.name(pair._2.value);module=pair._2.value}
          need(!(a.equal(r.circuit,circuit) && selected.find(modules.id(module),r.ref)>=0),"ANNOTATION_TARGET")
          val parts=a.iter(r.component)
          while(parts.hasNext){a.charge(AX.Probe);parts.next() match {
            case TargetToken.Field(s)=>b.name(s)
            case TargetToken.Index(i)=>need(i>=0,"ANNOTATION_SHAPE")
            case TargetToken.Init | TargetToken.Reset | TargetToken.Clock=>()
            case _=>fail("ANNOTATION_SHAPE")
          }}
        case c:CircuitTarget=>b.name(c.circuit);need(!a.equal(c.circuit,circuit),"ANNOTATION_SHAPE")
        case m:ModuleTarget=>b.name(m.circuit);b.name(m.module)
          need(!(a.equal(m.circuit,circuit) && selected.moduleSelected(modules.id(m.module))),"ANNOTATION_SHAPE")
        case _:InstanceTarget=>fail("ANNOTATION_SHAPE")
        case _=>fail("ANNOTATION_SHAPE")
      }
    }
    def named(n:Named):Unit=n match {
      case t:Target=>target(t)
      case c:ComponentName=>b.name(c.name);b.name(c.module.name);b.name(c.module.circuit.name)
        target(checkedNamed(c,a))
      case m:ModuleName=>b.name(m.name);b.name(m.circuit.name);a.transient(16);target(m.toTarget)
      case c:CircuitName=>b.name(c.name);a.transient(16);target(c.toTarget)
      case _=>fail("ANNOTATION_SHAPE")
    }
    val annotations=a.iter(as)
    while(annotations.hasNext){b.tick();val annotation=annotations.next();annotation match {
      case _:PresetAnnotation | _:PresetRegAnnotation=>fail("ANNOTATION_PRESET")
      case _:treadle2.DataStorePlugInAnnotation | _:treadle2.BlackBoxFactoriesAnnotation |
           _:treadle2.TreadleTesterAnnotation=>fail("ANNOTATION_EXTENSION")
      case x if x.getClass.getName=="firrtl2.stage.RunFirrtlTransformAnnotation" ||
        x.getClass.getName=="firrtl2.stage.RunFirrtlTransformAnnotation$" || x.getClass.getName=="firrtl2.options.RunFirrtlTransformAnnotation"=>fail("ANNOTATION_EXTENSION")
      case x:SingleTargetAnnotation[_]=>named(x.target)
      case x:MultiTargetAnnotation=>
        boundedSize(x.targets,1024,"TARGET_GROUPS",a,b);val groups=a.iter(x.targets)
        while(groups.hasNext){a.charge(AX.Probe);val xs=groups.next();boundedSize(xs,1024,"TARGET_MEMBERS",a,b)
          val members=a.iter(xs);while(members.hasNext)target(members.next())}
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
  // V1 streaming resource contract. Only index charges move out of Budget.
  // All names below are finite telemetry enums, never input-derived text.
  private object AX {
    final val Visit=0;final val Names=1;final val Entries=2;final val Hash=3;final val Probe=4
    final val Equal=5;final val Clear=6;final val Uses=7;final val Rewrite=8;final val Copy=9
    final val ArrayCopy=10;final val Anchor=11;final val Info=12;final val Replace=13
    final val Candidate=14;final val UseRecord=15;final val Live=16;final val Iterator=17;final val Family=18
    val reasons=Array("INDEX_VISITS","NAMESPACE_OCCURRENCES","NAMESPACE_ENTRIES","HASH_CHARS","PROBES",
      "EQUALITY_CHARS","CLEAR_OPS","USE_VISITS","REWRITE_VISITS","COPY_TOTAL","COPY_ARRAY",
      "ANCHOR_ATTEMPTS","INFO_VISITS","REPLACEMENTS","CANDIDATES","USE_RECORDS","LIVE_BYTES","ITERATOR_UNITS","SEQUENCE_FAMILY")
    val limits=Array[Long](4194304,4194304,1048576,67108864,33554432,268435456,4194304,
      4194304,4194304,4194304,1048576,1048576,16777216,263168,1024,2048,335544320,16777216,0)
  }
  private final class AuxiliaryEvidence(val reason:Int,val phase:String,val used:Long,val requested:Long,val limit:Long)
    extends RuntimeException(null,null,false,false) {
    def code:String={
      val validPhase=phase=="INDEX_PREPARED" || phase=="INDEX_BEFORE" || phase=="USES" ||
        phase=="ANCHORS" || phase=="REBUILD" || phase=="NONINTERFERENCE"
      if(reason<0 || reason>=AX.limits.length || !validPhase || limit<0 || limit>AX.limits(reason) ||
        used<0 || used>limit || requested<=limit-used)"UNAVAILABLE"
      else AX.reasons(reason)+":"+phase+":"+used+":"+requested+":"+limit
    }
  }
  def auxiliaryEvidence(error:Throwable):String={
    if(error==null || guardCode(error)!="BOUND")"NONE"
    else {val xs=error.getSuppressed
      if(xs.length==1)xs(0) match {case e:AuxiliaryEvidence=>e.code;case _=>"NONE"}
      else if(xs.length==0)"NONE" else "UNAVAILABLE"
    }
  }
  private final class Aux(private val testReason:Int = -1,private val testLimit:Long = 0L) {
    // Bootstrap: one Aux object + one 19-Long array (two 256-byte object/header
    // units + 152 payload bytes), rounded up to 768 bytes, is statically checked
    // before production construction. Tiny private limits exclude test harness
    // bootstrap, so the exact helpers can exercise zero remaining capacity.
    require(testReason>= -1 && testReason<AX.limits.length && testLimit>=0 &&
      (testReason<0 || testLimit<=AX.limits(testReason)))
    private val initialLive=if(testReason<0)768L else 0L
    require(initialLive<=AX.limits(AX.Live))
    private val used=new Array[Long](19)
    used(AX.Live)=initialLive
    var phase="INDEX_PREPARED"
    var namedConversions=0L // Private qualification witness, never emitted.
    def limit(i:Int):Long=if(i==testReason)testLimit else AX.limits(i)
    def value(i:Int):Long=used(i)
    def check(i:Int,n:Long,current:Long):Unit=checkCap(i,n,current,limit(i))
    def checkCap(i:Int,n:Long,current:Long,cap:Long):Unit={
      require(n>=0 && current>=0 && current<=cap)
      if(n>cap-current){
        val error=new IllegalArgumentException("BOUND")
        error.addSuppressed(new AuxiliaryEvidence(i,phase,current,n,cap))
        throw error
      }
    }
    def charge(i:Int,n:Long=1L):Unit={check(i,n,used(i));used(i)+=n}
    def alloc(bytes:Long):Unit=charge(AX.Live,bytes)
    def transient(n:Long=1L):Unit=charge(AX.Iterator,n)
    // New, explicit resource domain. These pinned families have verified bounded
    // iterator/builder layouts; arbitrary Seq callbacks are not admitted.
    def family[A](s:scala.collection.Seq[A]):Unit=s match {
      case _:scala.collection.immutable.List[_] | _:scala.collection.immutable.Vector[_] |
           _:scala.collection.immutable.ArraySeq.ofRef[_]=>()
      case _=>charge(AX.Family) // Pinned zero: always fails before iterator/zip.
    }
    def iter[A](s:Seq[A]):Iterator[A]={family(s);transient();s.iterator}
    def hash(s:String):Int={
      var h=0x811c9dc5;var i=0
      while(i<s.length){charge(AX.Hash);h=(h ^ s.charAt(i).toInt)*0x01000193;i+=1};h
    }
    def equal(a:String,b:String):Boolean={
      charge(AX.Probe)
      if(a==null || b==null)return a eq b
      if(a.length!=b.length)return false
      var i=0
      while(i<a.length){charge(AX.Equal);if(a.charAt(i)!=b.charAt(i))return false;i+=1};true
    }
  }
  private final class ExactNames(a:Aux,slots:Int=1<<21,entries:Int=1<<20) {
    require(slots>0 && (slots & (slots-1))==0 && entries<=slots/2)
    a.alloc(slots.toLong*8+entries.toLong*4+512)
    private val keys=new Array[String](slots)
    private val occupied=new Array[Int](entries)
    private var count=0
    def size:Int=count
    def retainedForTest:Int={var i=0;var n=0;while(i<keys.length){if(keys(i)!=null)n+=1;i+=1};n}
    private def slot(name:String):Int={
      var p=a.hash(name)&(slots-1)
      while(true){a.charge(AX.Probe);val k=keys(p)
        if(k==null)return ~p
        if(a.equal(k,name))return p
        p=(p+1)&(slots-1)
      }; -1
    }
    def contains(name:String):Boolean=slot(name)>=0
    def add(name:String):Unit={
      a.charge(AX.Names);val found=slot(name);need(found<0,"DUPLICATE");val p= ~found
      a.checkCap(AX.Entries,1,count,math.min(a.limit(AX.Entries),entries.toLong))
      keys(p)=name;occupied(count)=p;count+=1
    }
    def clear():Unit={
      var i=0;while(i<count){a.charge(AX.Clear);keys(occupied(i))=null;i+=1};count=0
    }
  }
  // Two fixed module tables; IDs are prepared-circuit order, not String tuples.
  private final class Modules(a:Aux) {
    a.alloc(8192L*20+768)
    private val names=new Array[String](8192)
    private val modules=new Array[DefModule](8192)
    private val ids=new Array[Int](8192)
    var count=0
    private def slot(name:String):Int={var p=a.hash(name)&8191
      while(true){a.charge(AX.Probe);val k=names(p);if(k==null || a.equal(k,name))return p;p=(p+1)&8191}; -1
    }
    def add(m:DefModule,id:Int):Unit={val p=slot(m.name);need(names(p)==null,"DUPLICATE")
      names(p)=m.name;modules(p)=m;ids(p)=id;count+=1
    }
    def get(name:String):DefModule=modules(slot(name))
    def id(name:String):Int={val p=slot(name);if(names(p)==null)-1 else ids(p)}
  }
  private final class Selected(a:Aux) {
    // Payload: 2048*(8+4+4) + 1024*(8*7+4*5) + 2048*(8*2+1)
    // = 145408 bytes; below the reserved 256 KiB metadata + 32 KiB lookup.
    a.alloc(32768L+262144L+32L*256)
    private val keyNames=new Array[String](2048)
    private val keyModules=new Array[Int](2048)
    private val keyIds=new Array[Int](2048)
    val regs=new Array[DefRegister](1024);val clocks=new Array[Reference](1024)
    val moduleNames=new Array[String](1024);val moduleIds=new Array[Int](1024)
    val uses=new Array[Int](1024);val useStatements=new Array[Statement](2048)
    val useRoots=new Array[Expression](2048);val direct=new Array[Boolean](2048)
    val consumers=new Array[Statement](1024);val anchors=new Array[Int](1024)
    val originalSeen=new Array[Boolean](1024)
    var count=0
    def find(mid:Int,name:String):Int={var p=(a.hash(name)^mid*0x9e3779b9)&2047
      while(true){a.charge(AX.Probe);val k=keyNames(p)
        if(k==null)return -1
        if(keyModules(p)==mid && a.equal(k,name))return keyIds(p)
        p=(p+1)&2047
      }; -1
    }
    def add(mid:Int,module:String,r:DefRegister,c:Reference):Unit={
      a.charge(AX.Candidate);val id=count;var p=(a.hash(r.name)^mid*0x9e3779b9)&2047
      var found=false
      while(!found){a.charge(AX.Probe);if(keyNames(p)==null)found=true else p=(p+1)&2047}
      keyNames(p)=r.name;keyModules(p)=mid;keyIds(p)=id
      regs(id)=r;clocks(id)=c;moduleNames(id)=module;moduleIds(id)=mid;count+=1
    }
    def addUse(id:Int,s:Statement,root:Expression,isDirect:Boolean):Unit={
      need(uses(id)<2,"REFERENCES");a.charge(AX.UseRecord)
      val p=id*2+uses(id);useStatements(p)=s;useRoots(p)=root;direct(p)=isDirect;uses(id)+=1
    }
    def selectedIdentity(s:Statement):Boolean={var i=0
      while(i<count){a.charge(AX.Probe);if(regs(i) eq s)return true;i+=1};false
    }
    def moduleSelected(mid:Int):Boolean={var i=0
      while(i<count){a.charge(AX.Probe);if(moduleIds(i)==mid)return true;i+=1};false
    }
  }
  private final class Replacements(a:Aux,slots:Int=1<<20) {
    require(slots>0 && (slots & (slots-1))==0)
    a.alloc(slots.toLong*16+512)
    private val keys=new Array[Statement](slots);private val values=new Array[Statement](slots)
    private def slot(s:Statement):Int={a.charge(AX.Probe);var p=System.identityHashCode(s)&(slots-1)
      while(true){a.charge(AX.Probe);val k=keys(p);if(k==null || (k eq s))return p;p=(p+1)&(slots-1)}; -1
    }
    def get(s:Statement):Statement=values(slot(s))
    def put(s:Statement,n:Statement):Unit={val p=slot(s);need(keys(p)==null,"NONINTERFERENCE")
      a.charge(AX.Replace);keys(p)=s;values(p)=n
    }
    def reserveEntry():Unit={a.check(AX.Replace,1,a.value(AX.Replace));a.alloc(768)}
  }
  private val rejectStatementChild:Statement=>Unit=_=>fail("STRUCTURE")
  // A two-child iterator has three fields and is reserved before construction.
  private final class Two[A](first:A,second:A) extends Iterator[A] {
    private var n=0
    def hasNext:Boolean=n<2
    def next():A={if(!hasNext)throw new NoSuchElementException();n+=1;if(n==1)first else second}
  }
  // Pinned firrtl2 6.0.0 IR.scala: only Block and Conditionally bear Statement
  // children. WIR.scala statement forms are leaves. A future form is rejected,
  // never silently omitted from validation or rewriting.
  private def children(s:Statement,a:Aux):Iterator[Statement]=s match {
    case b:Block=>a.iter(b.stmts)
    case c:Conditionally=>a.transient();new Two(c.conseq,c.alt)
    case _=>s.foreachStmt(rejectStatementChild);Iterator.empty
  }
  private final class Walk(a:Aux,b:Budget) {
    // Shared active frame reserve covers this and proof/expression/info frames.
    private val stack=new Array[Iterator[Statement]](258)
    private var depth = -1
    private var root:Statement=null
    def start(s:Statement):Unit={require(depth<0 && root==null);root=s}
    var currentDepth=0
    def next(counter:Int):Statement={
      if(root!=null){if(counter>=0)a.charge(counter)else b.tick();val s=root;root=null;currentDepth=0;return s}
      while(depth>=0){val it=stack(depth)
        if(it.hasNext){if(counter>=0)a.charge(counter)else b.tick();currentDepth=depth+1;b.bound(currentDepth<=256,"STATEMENT_DEPTH");return it.next()}
        stack(depth)=null;depth-=1
      };null
    }
    def descend(s:Statement):Unit={val it=children(s,a)
      if(it.hasNext){depth+=1;stack(depth)=it}
    }
  }
  private final class Checked(a:Aux,b:Budget) {
    private var nodes=0
    private var present=false
    private var typeNames=0L
    private def typ(t:Type,depth:Int):Unit={
      b.tick();nodes+=1;b.bound(depth<=64,"TYPE_DEPTH");b.bound(nodes<=4096,"TYPE_NODES")
      t match {
        case VectorType(x,n)=>need(n>=0,"TYPE");typ(x,depth+1)
        case BundleType(fs)=>
          boundedSize(fs,4096,"TYPE_FIELDS",a,b);val it=a.iter(fs)
          while(it.hasNext){val f=it.next();b.name(f.name);typeNames+=f.name.length;typ(f.tpe,depth+1)}
        case _=>()
      }
    }
    def checkType(t:Type):Unit={nodes=0;typeNames=0;typ(t,0)}
    def mismatch(r:DefRegister):Boolean=r.tpe match {
      case AnalogType(_)=>false
      case _=>nodes=0;typeNames=0;typ(r.tpe,0);val leftNodes=nodes;nodes=0
        a.transient();val initType=r.init.tpe;typ(initType,0)
        // WrappedType is the exact CheckTypes comparison, not an approximation.
        a.transient(2L+8L*(leftNodes+nodes));a.charge(AX.Equal,typeNames)
        firrtl2.WrappedType.wt(r.tpe)!=firrtl2.WrappedType.wt(initType)
    }
    private def info(i:Info,depth:Int):Unit={
      b.tick();nodes+=1;b.bound(depth<=16,"INFO_DEPTH");b.bound(nodes<=256,"INFO_NODES")
      i match {
        case NoInfo=>()
        case FileInfo(s)=>b.bound(s.length<=4096,"INFO_STRING");if(s.nonEmpty)present=true
        case MultiInfo(xs)=>boundedSize(xs,64,"INFO_CHILDREN",a,b);val it=a.iter(xs)
          while(it.hasNext)info(it.next(),depth+1)
        case _=>fail("INFO")
      }
    }
    def infoPresent(i:Info):Boolean={nodes=0;present=false;info(i,0);present}
    private def equalInfo(x:Info,y:Info,depth:Int):Boolean={
      a.charge(AX.Info);b.bound(depth<=16,"INFO_DEPTH")
      x match {
        case NoInfo=>y eq NoInfo
        case f:FileInfo=>y match {case g:FileInfo=>a.equal(f.escaped,g.escaped);case _=>false}
        case m:MultiInfo=>y match {
          case n:MultiInfo=>
            val xi=a.iter(m.infos);val yi=a.iter(n.infos)
            while(xi.hasNext && yi.hasNext){if(!equalInfo(xi.next(),yi.next(),depth+1))return false}
            !xi.hasNext && !yi.hasNext
          case _=>false
        }
        case _=>false
      }
    }

    def same(x:Info,y:Info):Boolean={val px=infoPresent(x);val py=infoPresent(y);px && py && equalInfo(x,y,0)}
    def equalValidated(x:Info,y:Info):Boolean=equalInfo(x,y,0)
  }
  private def inputPort(m:DefModule,name:String,a:Aux):Boolean={
    val it=a.iter(m.ports)
    while(it.hasNext){val p=it.next();if(a.equal(p.name,name))return p.direction==Input && p.tpe==ClockType};false
  }
  // Pinned IR.scala/WIR.scala direct-expression arities: SubField/SubIndex/
  // InfoExpr=1, SubAccess/ValidIf=2, Mux=3, Reference/literals/WVoid/WInvalid/
  // EmptyExpression=0. Only DoPrim has an unbounded child Seq; it is iterated.
  // Statement.foreachExpr uses one reused callback, so Print/Attach/CDefMPort/
  // WDefInstanceConnector root-expression sequences never build a pending queue.
  private def rootSequenceFamilies(s:Statement,a:Aux):Unit=s match {
    case p:Print=>a.family(p.args)
    case p:Attach=>a.family(p.exprs)
    case p:firrtl2.WDefInstanceConnector=>a.family(p.portCons)
    case p:firrtl2.CDefMPort=>a.family(p.exps)
    // Pinned DefRandom has only Option(clock) and scalar en, no Seq.
    case _=>()
  }
  private final class Expressions(a:Aux,b:Budget,selected:Selected) {
    private val its=new Array[Iterator[Expression]](258)
    private val first=new Array[Expression](258);private val second=new Array[Expression](258)
    private val third=new Array[Expression](258);private val pos=new Array[Int](258)
    private var collecting=0
    private val collect:Expression=>Unit=x=>{
      val d=collecting
      pos(d) match {case 0=>first(d)=x;case 1=>second(d)=x;case 2=>third(d)=x;case _=>fail("STRUCTURE")}
      pos(d)+=1
    }
    private def init(e:Expression,d:Int):Unit={
      first(d)=null;second(d)=null;third(d)=null;pos(d)=0;its(d)=null
      e match {
        case p:DoPrim=>its(d)=a.iter(p.args)
        case _=>collecting=d;e.foreachExpr(collect);pos(d)=0
      }
    }
    private def child(d:Int):Expression={
      val it=its(d)
      if(it!=null){if(it.hasNext){b.tick();it.next()}else null}
      else {val x=pos(d) match {case 0=>first(d);case 1=>second(d);case 2=>third(d);case _=>null}
        if(x!=null){b.tick();pos(d)+=1};x}
    }
    var statement:Statement=null;var moduleId=0;var hasSelected=false
    val root:Expression=>Unit=r=>{
      a.transient(2) // Pinned foreachExpr callback/tuple churn, before traversal.
      var depth=0;var e=r;var active=true
      while(active){
        b.tick();b.bound(depth<=256,"EXPRESSION_DEPTH")
        e match {case ref:Reference=>b.name(ref.name)
          if(hasSelected){val id=selected.find(moduleId,ref.name);if(id>=0)selected.addUse(id,statement,r,depth==0)}
          case _=>()}
        init(e,depth)
        var next=child(depth)
        while(next==null && depth>0){its(depth)=null;first(depth)=null;second(depth)=null;third(depth)=null;depth-=1;next=child(depth)}
        if(next==null)active=false else {depth+=1;e=next}
      }
      its(0)=null;first(0)=null;second(0)=null;third(0)=null
    }
  }
  private def delayed(e:Expression,name:String,sink:Boolean,a:Aux):Boolean=e match {
    case r:Reference=>r.tpe==ClockType && r.kind==NodeKind &&
      r.flow==(if(sink)firrtl2.SinkFlow else SourceFlow) && a.equal(r.name,name)
    case _=>false
  }
  private def driverFailure(step:String,s:Selected,id:Int,a:Aux):Nothing={
    a.transient(128);a.charge(AX.Equal,8192);a.charge(AX.Probe,16)
    // Failure-only existing finite diagnostic, bounded to exactly two records.
    driverFail(step,Vector(Use(s.useStatements(id*2),s.useRoots(id*2),s.direct(id*2)),
      Use(s.useStatements(id*2+1),s.useRoots(id*2+1),s.direct(id*2+1))),s.clocks(id))
  }
  private def matchUses(s:Selected,a:Aux,b:Budget,c:Checked,claim:ObservedPrepareAst.Claim=null):Unit={
    var i=0
    while(i<s.count){
      need(s.uses(i)==2,"REFERENCES");var driver:Connect=null;var consumer:Statement=null;var drivers=0;var consumers=0
      var j=0
      while(j<2){val k=i*2+j
        if(s.direct(k))s.useStatements(k) match {
          case x:Connect if (s.useRoots(k) eq x.loc) && delayed(x.loc,s.regs(i).name,true,a)=>driver=x;drivers+=1
          case x:Print if (s.useRoots(k) eq x.clk) && delayed(x.clk,s.regs(i).name,false,a)=>consumer=x;consumers+=1
          case x:Stop if (s.useRoots(k) eq x.clk) && delayed(x.clk,s.regs(i).name,false,a)=>consumer=x;consumers+=1
          case _=>()
        };j+=1
      }
      if(drivers!=1)driverFailure("SELECT",s,i,a)
      val equal=driver.expr match {case r:Reference=>a.equal(r.name,s.clocks(i).name) &&
        r.tpe==s.clocks(i).tpe && r.kind==s.clocks(i).kind && r.flow==s.clocks(i).flow;case _=>false}
      if(!equal)driverFailure("RHS",s,i,a)
      need(c.same(s.regs(i).info,driver.info),"INFO");need(consumers==1,"CONSUMER")
      consumer match {
        case p:Print=>need(c.same(s.regs(i).info,p.info),"INFO");b.bound(p.string.string.length<=4096,"PRINT_STRING")
        case p:Stop=>need(c.same(s.regs(i).info,p.info),"INFO")
        case _=>fail("CONSUMER")
      }
      if(claim!=null)claim.requireUses(i,driver,consumer)
      s.consumers(i)=consumer;i+=1
    }
  }
  private def anchor(s:Statement,mid:Int,selected:Selected,a:Aux,b:Budget,c:Checked,proven:Boolean=false):Unit={
    var clock:Reference=null;var info:Info=null;var format:String=null;var ret=0;var print=false
    s match {
      case p:Print=>b.bound(p.string.string.length<=4096,"PRINT_STRING")
        p.clk match {case r:Reference if r.tpe==ClockType && r.kind==PortKind && r.flow==SourceFlow=>
          if(c.infoPresent(p.info)){clock=r;info=p.info;format=p.string.string;print=true};case _=>()}
      case p:Stop=>p.clk match {case r:Reference if r.tpe==ClockType && r.kind==PortKind && r.flow==SourceFlow=>
          if(c.infoPresent(p.info)){clock=r;info=p.info;ret=p.ret};case _=>()}
      case _=>()
    }
    if(proven)return // Original-global validation above remains mandatory.
    if(clock!=null){var i=0
      while(i<selected.count){
        a.charge(AX.Anchor)
        if(selected.moduleIds(i)==mid){val consumer=selected.consumers(i)
          var shape=false;var selectedInfo:Info=null
          consumer match {
            case p:Print if print=>shape=a.equal(format,p.string.string);selectedInfo=p.info
            case p:Stop if !print && p.ret==ret=>shape=true;selectedInfo=p.info
            case _=>()
          }
          if(shape && a.equal(clock.name,selected.clocks(i).name) && c.equalValidated(info,selectedInfo))selected.anchors(i)+=1
        };i+=1
      }
    }
  }
  private final class Rewriter(replacements:Replacements,a:Aux,b:Budget) {
    private val nodes=new Array[Statement](258);val its=new Array[Iterator[Statement]](258)
    private val counts=new Array[Int](258);private val changed=new Array[Boolean](258)
    def rewrite(root:Statement):Statement={
      counts(0)=0;changed(0)=false
      var depth=0;nodes(0)=root
      a.charge(AX.Rewrite);its(0)=children(root,a)
      while(depth>=0){
        val it=its(depth)
        if(it.hasNext){
          a.check(AX.ArrayCopy,1,counts(depth));counts(depth)+=1
          a.charge(AX.Rewrite);b.bound(depth<256,"STATEMENT_DEPTH")
          val child=it.next();depth+=1;nodes(depth)=child;counts(depth)=0;changed(depth)=false;its(depth)=children(child,a)
        }else{
          val s=nodes(depth)
          if(changed(depth) && replacements.get(s)==null)s match {
            case block:Block=>
              val n=counts(depth)
              // Both reservations precede allocating or copying any child.
              a.check(AX.Copy,n,a.value(AX.Copy));a.check(AX.Live,768L+n.toLong*8,a.value(AX.Live))
              replacements.reserveEntry();a.charge(AX.Copy,n);a.alloc(n.toLong*8)
              val out=new Array[Statement](n);val source=a.iter(block.stmts);var i=0
              while(source.hasNext){need(i<n,"NONINTERFERENCE")
                // Aggregate copy work was reserved above; each exact lookup is separately metered.
                val old=source.next();val replacement=replacements.get(old);out(i)=if(replacement==null)old else replacement;i+=1
              }
              need(i==n,"NONINTERFERENCE")
              val wrapped=scala.collection.immutable.ArraySeq.unsafeWrapArray(out)
              replacements.put(s,block.copy(stmts=wrapped))
            case _=>fail("NONINTERFERENCE")
          }
          val replacement=replacements.get(s)
          its(depth)=null;nodes(depth)=null;depth-=1
          if(depth>=0 && replacement!=null)changed(depth)=true
        }
      }
      val n=replacements.get(root);if(n==null)root else n
    }
  }
  private def prove(prepared:Circuit,result:Circuit,s:Selected,expected:Int,a:Aux,b:Budget):Int={
    need((result.info eq prepared.info) && (result.main eq prepared.main),"NONINTERFERENCE")
    val oi=new Array[Iterator[Statement]](258);val ni=new Array[Iterator[Statement]](258)
    var ticks=0;var changed=0
    def tick():Unit={b.tick();ticks+=1}
    val oldModules=a.iter(prepared.modules);val newModules=a.iter(result.modules)
    while(oldModules.hasNext && newModules.hasNext){
      tick();val prior=oldModules.next();val revised=newModules.next()
      if(!(prior eq revised)){
        prior match {
          case om:Module=>
            need(revised.isInstanceOf[Module],"NONINTERFERENCE");val nm=revised.asInstanceOf[Module]
            need((om.name eq nm.name) && (om.info eq nm.info) && (om.ports eq nm.ports),"NONINTERFERENCE")
            var old:Statement=om.body;var fresh:Statement=nm.body;var depth = -1;var active=true
            while(active){
              tick()
              if(!(old eq fresh))old match {
                case o:DefRegister=>
                  need(fresh.isInstanceOf[DefRegister],"NONINTERFERENCE");val n=fresh.asInstanceOf[DefRegister]
                  need(s.selectedIdentity(o),"NONINTERFERENCE")
                  need((o.info eq n.info) && (o.name eq n.name) && (o.tpe eq n.tpe) &&
                    (o.clock eq n.clock) && (o.reset eq n.reset),"NONINTERFERENCE")
                  n.init match {
                    case p:DoPrim if p.op==firrtl2.PrimOps.AsClock && p.tpe==ClockType=>
                      val args=a.iter(p.args);need(args.hasNext,"NONINTERFERENCE");val value=args.next()
                      need(!args.hasNext && p.consts.isEmpty && (value eq o.init),"NONINTERFERENCE")
                    case _=>fail("NONINTERFERENCE")
                  }
                  changed+=1;need(changed<=expected,"NONINTERFERENCE")
                case o:Block=>
                  need(fresh.isInstanceOf[Block],"NONINTERFERENCE");val n=fresh.asInstanceOf[Block]
                  b.bound(depth<256,"STATEMENT_DEPTH");depth+=1;oi(depth)=a.iter(o.stmts);ni(depth)=a.iter(n.stmts)
                case _=>fail("NONINTERFERENCE")
              }
              var found=false
              while(depth>=0 && !found){
                val x=oi(depth);val y=ni(depth)
                if(x.hasNext && y.hasNext){tick();old=x.next();fresh=y.next();found=true}
                else {need(!x.hasNext && !y.hasNext,"NONINTERFERENCE");oi(depth)=null;ni(depth)=null;depth-=1}
              }
              active=found
            }
          case _=>fail("NONINTERFERENCE")
        }
      }
    }
    need(!oldModules.hasNext && !newModules.hasNext && changed==expected,"NONINTERFERENCE");ticks
  }
  // Semantic-work inventory (all complete traversals retain the legacy totals):
  // one tick per checked Type/Info node; one per annotation/target; expression
  // root/processing and every child enqueue each retain one tick; one per original
  // anchor statement; proof module/root and child enqueue+processing ticks unchanged.
  // Only old index ticks are replaced. Iterator scans and ordering may encounter a
  // finite guard earlier, but cannot turn a rejected incomplete scan into success.
  // BEGIN PROOF BOUND REPAIR ENTRY
  final case class ProvenanceResult(state:CircuitState,corrected:Int,noninterferenceTicks:Int)
  def provenanceReason(error:Throwable):String=ObservedPrepareAst.provenanceReason(error)
  def applyWithProvenance(before:Circuit,prepared:CircuitState,outer:AnnotationSeq,expected:Int,
    grant:ObservedPrepareAst.Grant):ProvenanceResult={
    if(grant==null){val error=new IllegalArgumentException("PROVENANCE");throw error}
    grant.consume(before,prepared,outer,expected)
  }
  private[simulator] def applyClaimed(before:Circuit,prepared:CircuitState,expected:Int,
    claim:ObservedPrepareAst.Claim):ProvenanceResult={
    if(claim==null)throw new IllegalArgumentException("PROVENANCE")
    claim.beginRepair()
    val result=applyCore(before,prepared.circuit,prepared.annotations,expected,claim)
    val state=prepared.copy(circuit=result.circuit)
    claim.requireCommit()
    ProvenanceResult(state,result.corrected,result.noninterferenceTicks)
  }
  private def reserveProvenance(a:Aux,expected:Int):Unit={
    a.alloc(2097152L);a.transient(8192);a.charge(AX.Clear,16384)
    a.charge(AX.Probe,4L*expected*expected+64L*expected+128L)
  }
  private[simulator] def provenanceBudgetSelfChecks():Int={
    var checks=0
    val reservations=List((AX.Live,2097152L),(AX.Iterator,8192L),(AX.Clear,16384L),(AX.Probe,4259968L))
    reservations.foreach{case(id,n)=>
      val exact=new Aux(id,n);reserveProvenance(exact,1024);require(exact.value(id)==n,"GRANT_BUDGET_SELFCHECK");checks+=1
      val short=new Aux(id,n-1);var failure:Throwable=null
      try{reserveProvenance(short,1024)}catch{case e:IllegalArgumentException=>failure=e}
      require(failure!=null&&guardCode(failure)=="BOUND"&&short.value(id)==0,"GRANT_BUDGET_SELFCHECK");checks+=1
    };checks
  }
  // END PROOF BOUND REPAIR ENTRY
  def apply(before:Circuit,prepared:Circuit,annotations:AnnotationSeq,expected:Int):Result=
    applyCore(before,prepared,annotations,expected,null)
  private def applyCore(before:Circuit,prepared:Circuit,annotations:AnnotationSeq,expected:Int,
    claim:ObservedPrepareAst.Claim):Result={
    need(expected>0 && expected<=1024,"COUNT")
    // Static bootstrap precheck precedes even the budget object/counter array.
    need(AX.limits(AX.Live)>=768,"BOUND")
    val a=new Aux
    // Allocation inventory: 38 fixed arrays total (Aux1, namespace2, modules6,
    // selected14, replacements2, Walk1, Expressions5, Rewriter4, proof2, outer1).
    // Their headers and <64 scalar/closure objects fit the 64 KiB fixed reserve;
    // enumerated table/metadata payloads are charged by their constructors. The
    // traversal array payload is <24 KiB including headers. At most516 active
    // iterators at256 bytes each plus these pools fit the256 KiB frame allowance.
    // Changed entries reserve three separate256-byte units; child payloads,
    // initializer objects, changed Modules and outer sequence are charged below.
    // Maximum reservations including both scratch pools:317140224 bytes,
    // i.e.302.448486328125 MiB, below the unchanged335544320-byte ceiling.
    // Dedicated standard-library live scratch, reserved once, not per call:
    // WrappedType zip 8 MiB; bounded official Named parser 32 MiB.
    a.alloc(65536L+262144L-768L+8L*1024*1024+32L*1024*1024)
    if(claim!=null){
      // Entire2MiB handoff overlap and cleanup reserved before consumer scratch.
      reserveProvenance(a,expected)
      claim.reserve(expected)
    }
    val b=new Budget
    b.name(before.main);b.name(prepared.main);need(a.equal(before.main,prepared.main),"STRUCTURE")
    val names=new ExactNames(a);val fresh=new Modules(a);val old=new Modules(a)
    val selected=new Selected(a);val checked=new Checked(a,b);val walker=new Walk(a,b)
    b.phase="CANDIDATES"
    def scan(c:Circuit,table:Modules,preparedPass:Boolean):Unit={
      val modules=a.iter(c.modules);var mid=0
      while(modules.hasNext){
        b.bound(mid<4096,"MODULES");a.charge(AX.Visit);val m=modules.next();b.name(m.name);table.add(m,mid)
        val ports=a.iter(m.ports);var portCount=0
        while(ports.hasNext){b.bound(portCount<250000,"PORTS");a.charge(AX.Visit);val p=ports.next();b.name(p.name);names.add(p.name);portCount+=1}
        m match {
          case mm:Module=>
            walker.start(mm.body);var st=walker.next(AX.Visit)
            while(st!=null){
              st match {
                case p:Print if p.name.isEmpty=>()
                case p:Stop if p.name.isEmpty=>()
                case p:Verification if p.name.isEmpty=>()
                case d:IsDeclaration=>b.name(d.name);names.add(d.name)
                case _=>()
              }
              if(preparedPass)st match {
                case r:DefRegister if checked.mismatch(r)=>
                  need(r.tpe==ClockType && isZero(r.reset) && isZero(r.init),"SHAPE")
                  val clk=r.clock match {case x:Reference if x.tpe==ClockType && x.kind==PortKind && x.flow==SourceFlow=>x;case _=>fail("CLOCK")}
                  need(inputPort(m,clk.name,a),"CLOCK");need(checked.infoPresent(r.info),"INFO")
                  need(selected.count<expected,"COUNT");selected.add(mid,m.name,r,clk)
                  if(claim!=null)claim.bind(selected.count-1,mm,r)
                case _=>()
              }
              walker.descend(st);st=walker.next(AX.Visit)
            }
          case _:ExtModule=>()
          case _=>fail("STRUCTURE")
        }
        if(!preparedPass){val preparedId=fresh.id(m.name);var i=0
          while(i<selected.count){a.charge(AX.Probe)
            if(selected.moduleIds(i)==preparedId){
              val priorName=names.contains(selected.regs(i).name)
              if(priorName&&claim==null)preexistingFail(m,fresh,selected.regs(i),selected.clocks(i))
              need(inputPort(m,selected.clocks(i).name,a),"CLOCK");selected.originalSeen(i)=true
            };i+=1
          }
        }
        names.clear();mid+=1
      }
    }
    scan(prepared,fresh,true);need(selected.count==expected,"COUNT")
    if(claim!=null)claim.requireRecords(selected.count)
    a.phase="INDEX_BEFORE";b.phase="INDEX_BEFORE";scan(before,old,false)
    var i=0;while(i<selected.count){need(selected.originalSeen(i),"ORIGINAL_MODULE");i+=1}
    a.phase="USES";b.phase="ANNOTATIONS"
    checkStreamingAnnotations(annotations,selected,fresh,prepared.main,b,a)
    b.phase="USES"
    val expressions=new Expressions(a,b,selected);val modules=a.iter(prepared.modules);var mid=0
    while(modules.hasNext){modules.next() match {
      case m:Module=>
        expressions.hasSelected=selected.moduleSelected(mid)
        walker.start(m.body);var st=walker.next(AX.Uses)
        while(st!=null){expressions.statement=st;expressions.moduleId=mid;rootSequenceFamilies(st,a);a.transient(2);st.foreachExpr(expressions.root)
          walker.descend(st);st=walker.next(AX.Uses)}
      case _=>()
    };mid+=1}
    b.phase="MATCHING";matchUses(selected,a,b,checked,claim)
    a.phase="ANCHORS";b.phase="ANCHORS"
    val originalModules=a.iter(before.modules)
    while(originalModules.hasNext){originalModules.next() match {
      case m:Module=>
        val id=fresh.id(m.name);walker.start(m.body);var st=walker.next(-1)
        while(st!=null){anchor(st,id,selected,a,b,checked,claim!=null);walker.descend(st);st=walker.next(-1)}
      case _=>()
    }}
    if(claim==null){i=0;while(i<selected.count){need(selected.anchors(i)==1,"ANCHOR");i+=1}}
    else claim.requireCommit()
    a.phase="REBUILD";b.phase="REBUILD"
    val replacements=new Replacements(a)
    i=0;while(i<selected.count){val reg=selected.regs(i)
      if(replacements.get(reg)==null){
        a.check(AX.Live,1280,a.value(AX.Live));replacements.reserveEntry();a.alloc(512)
        val typedZero=DoPrim(firrtl2.PrimOps.AsClock,reg.init::Nil,Nil,ClockType)
        replacements.put(reg,reg.copy(init=typedZero))
      };i+=1
    }
    a.alloc(fresh.count.toLong*8+768)
    val rewriter=new Rewriter(replacements,a,b)
    val rebuilt=new Array[DefModule](fresh.count);val source=a.iter(prepared.modules);mid=0
    while(source.hasNext){val m=source.next()
      rebuilt(mid)=m match {
        case mm:Module if selected.moduleSelected(mid)=>
          val body=rewriter.rewrite(mm.body)
          if(body eq mm.body)mm else {a.alloc(256);mm.copy(body=body)}
        case _=>m
      };mid+=1
    }
    need(mid==rebuilt.length,"NONINTERFERENCE")
    val result=prepared.copy(modules=scala.collection.immutable.ArraySeq.unsafeWrapArray(rebuilt))
    a.phase="NONINTERFERENCE";b.phase="NONINTERFERENCE"
    val ticks=prove(prepared,result,selected,expected,a,b)
    Result(result,expected,ticks)
  }

  /** Qualification only. Production constants are never parameterized by callers. */
  def streamingSelfChecks():Int={
    var checks=0
    def check(p:Boolean):Unit={require(p);checks+=1}
    def error(op: =>Unit):Throwable={var caught:Throwable=null
      try{op}catch{case e:IllegalArgumentException=>caught=e};require(caught!=null);caught}
    var k=0
    while(k<18){
      val a=new Aux(k,3);a.phase="USES";a.charge(k,3)
      val before=a.value(k);val e=error(a.charge(k))
      check(a.value(k)==before && guardCode(e)=="BOUND" && boundEvidence(e)=="UNAVAILABLE" &&
        auxiliaryEvidence(e)==AX.reasons(k)+":USES:3:1:3")
      k+=1
    }
    locally {
      val a=new Aux;val n=new ExactNames(a,8,4);n.add("same")
      val distinct=new String(Array('s','a','m','e'));val e=error(n.add(distinct))
      check(guardCode(e)=="DUPLICATE" && n.size==1 && n.contains(distinct));n.clear()
    }
    locally {
      val a=new Aux;val n=new ExactNames(a,8,4)
      val x="lrgmpljekmot";val y="ukvnvtragfjx"
      require(a.hash(x)==a.hash(y));n.add(x);n.add(y)
      check(n.contains(x) && n.contains(y) && !n.contains("ukvnvtragfjz") && n.size==2);n.clear()
    }
    locally {
      val a=new Aux;val n=new ExactNames(a,8,4);var first:String=null;var second:String=null;var i=0
      while(second==null){val s="wrap"+i;if((a.hash(s)&7)==7){if(first==null)first=s else second=s};i+=1}
      n.add(first);n.add(second);check(n.contains(first) && n.contains(second));n.clear()
    }
    locally {
      val a=new Aux;val n=new ExactNames(a);var i=0
      while(i<=250000){n.add("large"+i);i+=1}
      val e=error(n.add(new String("large250000")))
      check(guardCode(e)=="DUPLICATE" && n.size==250001 && n.contains("large250000"));n.clear()
    }
    locally {
      val a=new Aux;val ms=new Modules(a);val m=Module(NoInfo,"M",Nil,EmptyStmt);ms.add(m,3)
      val e=error(ms.add(m.copy(name=new String("M")),4))
      check(guardCode(e)=="DUPLICATE" && (ms.get("M") eq m) && ms.id("M")==3 && ms.id("Absent")== -1)
    }
    val zero=UIntLiteral(0,IntWidth(1));val clk=Reference("clk",ClockType,PortKind,SourceFlow)
    val reg=DefRegister(FileInfo("source"),"delay",ClockType,clk,zero,zero)
    locally {
      val a=new Aux;val selected=new Selected(a);selected.add(4,"M",reg,clk)
      check(selected.find(4,new String("delay"))==0 && selected.find(5,"delay")== -1 &&
        selected.selectedIdentity(reg) && !selected.selectedIdentity(reg.copy()))
    }
    locally {
      val a=new Aux;val r=new Replacements(a,8);val x=Block(Nil);val y=Block(Nil)
      r.reserveEntry();r.put(x,y)
      check((r.get(x) eq y) && r.get(Block(Nil))==null)
    }
    locally {
      val a=new Aux;val b=new Budget;val c=new Checked(a,b)
      val x=new MultiInfo(Seq(FileInfo(new String("one")),FileInfo("two")))
      val y=new MultiInfo(Seq(FileInfo("one"),FileInfo(new String("two"))))
      val z=new MultiInfo(Seq(FileInfo("two"),FileInfo("one")))
      val legacy=new Budget;val p=checkedInfo(x,legacy);val q=checkedInfo(y,legacy)
      val same=c.same(x,y)
      check(p && q && same && b.work==legacy.work && !c.equalValidated(x,z))
    }
    def typeBoundary(t:Type,reason:String):Unit={
      val a=new Aux;val b=new Budget;val c=new Checked(a,b);val old=new Budget
      val x=error(c.checkType(t));val y=error(boundedType(t,old))
      check(guardCode(x)=="BOUND" && guardCode(y)=="BOUND" &&
        boundEvidence(x).startsWith(reason+":") && boundEvidence(y).startsWith(reason+":"))
    }
    def deepType(n:Int):Type=(0 until n).foldLeft[Type](ClockType)((t,_)=>VectorType(t,1))
    typeBoundary(deepType(65),"TYPE_DEPTH")
    typeBoundary(BundleType(Vector.fill(4097)(Field("x",Default,ClockType))),"TYPE_FIELDS")
    typeBoundary(BundleType(Vector.fill(4096)(Field("x",Default,ClockType))),"TYPE_NODES")
    locally {
      val a=new Aux;val b=new Budget;val c=new Checked(a,b);val old=new Budget;val t=deepType(64)
      c.checkType(t);boundedType(t,old);check(b.work==old.work && b.work==65)
    }
    def infoBoundary(info:Info,reason:String):Unit={
      val a=new Aux;val b=new Budget;val c=new Checked(a,b);val old=new Budget
      val x=error(c.infoPresent(info));val y=error(checkedInfo(info,old))
      check(guardCode(x)=="BOUND" && guardCode(y)=="BOUND" &&
        boundEvidence(x).startsWith(reason+":") && boundEvidence(y).startsWith(reason+":"))
    }
    def deepInfo(n:Int):Info=(0 until n).foldLeft[Info](FileInfo("x"))((i,_)=>new MultiInfo(Seq(i)))
    infoBoundary(deepInfo(17),"INFO_DEPTH")
    infoBoundary(new MultiInfo(Vector.fill(65)(NoInfo)),"INFO_CHILDREN")
    infoBoundary(new MultiInfo(Vector.fill(5)(new MultiInfo(Vector.fill(64)(NoInfo)))),"INFO_NODES")
    infoBoundary(FileInfo("x"*4097),"INFO_STRING")
    def replacement(a:Aux):Replacements={val r=new Replacements(a,16);r.reserveEntry()
      r.put(reg,reg.copy(init=DoPrim(firrtl2.PrimOps.AsClock,Seq(zero),Nil,ClockType)));r}
    locally {
      val a=new Aux;val r=replacement(a);val w=new Rewriter(r,a,new Budget)
      val empty=Block(Nil);val nested=Block(Seq(empty,reg));val root=Block(Seq(EmptyStmt,nested))
      val result=w.rewrite(root).asInstanceOf[Block];val it=result.stmts.iterator;val first=it.next()
      val child=it.next().asInstanceOf[Block];val ci=child.stmts.iterator
      check((first eq EmptyStmt) && (ci.next() eq empty) && (ci.next() eq r.get(reg)) &&
        !ci.hasNext && !it.hasNext && a.value(AX.Copy)==4)
    }
    locally {
      val a=new Aux;val b=new Budget;val s=new Selected(a);s.add(0,"M",reg,clk)
      val r=replacement(a);val w=new Rewriter(r,a,b)
      val root=Block(Vector.fill[Statement](4096)(EmptyStmt):+reg)
      val before=Circuit(NoInfo,Seq(Module(NoInfo,"M",Nil,root)),"M")
      val revised=before.copy(modules=Seq(before.modules.head.asInstanceOf[Module].copy(body=w.rewrite(root))))
      val ticks=prove(before,revised,s,1,a,b)
      val changed=root.stmts.toArray;changed(4095)=DefWire(NoInfo,"unrelated",ClockType)
      changed(4096)=r.get(reg)
      val bad=before.copy(modules=Seq(before.modules.head.asInstanceOf[Module].copy(body=Block(scala.collection.immutable.ArraySeq.unsafeWrapArray(changed)))))
      val e=error(prove(before,bad,s,1,a,new Budget))
      check(ticks==8196 && guardCode(e)=="NONINTERFERENCE")
    }
    locally {
      val a=new Aux(AX.ArrayCopy,3);val r=replacement(a);val w=new Rewriter(r,a,new Budget)
      val before=a.value(AX.Live);val e=error(w.rewrite(Block(Seq(EmptyStmt,EmptyStmt,EmptyStmt,reg))))
      check(auxiliaryEvidence(e).startsWith("COPY_ARRAY:") && a.value(AX.Copy)==0 && a.value(AX.Live)==before)
    }
    locally {
      val a=new Aux(AX.Copy,3);val r=replacement(a);val w=new Rewriter(r,a,new Budget)
      val before=a.value(AX.Live);val e=error(w.rewrite(Block(Seq(EmptyStmt,EmptyStmt,EmptyStmt,reg))))
      check(auxiliaryEvidence(e).startsWith("COPY_TOTAL:") && a.value(AX.Copy)==0 && a.value(AX.Live)==before)
    }
    locally {
      val a=new Aux(AX.Copy,4);val r=replacement(a);val w=new Rewriter(r,a,new Budget)
      val result=w.rewrite(Block(Seq(EmptyStmt,EmptyStmt,EmptyStmt,reg)))
      check(result.isInstanceOf[Block] && a.value(AX.Copy)==4)
    }
    locally {
      val a=new Aux(AX.Hash,3);val n=new ExactNames(a,8,4);val e=error(n.add("four"))
      check(auxiliaryEvidence(e).startsWith("HASH_CHARS:") && a.value(AX.Hash)==3 && n.size==0 && n.retainedForTest==0)
    }
    locally {
      val a=new Aux(AX.Probe,0);val n=new ExactNames(a,8,4);val e=error(n.add("x"))
      check(auxiliaryEvidence(e).startsWith("PROBES:") && a.value(AX.Probe)==0 && n.size==0 && n.retainedForTest==0)
    }
    locally {
      val a=new Aux(AX.Equal,2);val n=new ExactNames(a,8,4);n.add("same");val e=error(n.contains(new String("same")))
      check(auxiliaryEvidence(e).startsWith("EQUALITY_CHARS:") && a.value(AX.Equal)==2 && n.size==1 && n.retainedForTest==1)
    }
    locally {
      val a=new Aux(AX.Clear,1);val n=new ExactNames(a,8,4);n.add("x");n.add("y");val e=error(n.clear())
      check(auxiliaryEvidence(e).startsWith("CLEAR_OPS:") && a.value(AX.Clear)==1 && n.retainedForTest==1)
    }
    locally {
      val a=new Aux(AX.Entries,1);val n=new ExactNames(a,8,4);n.add("x");val e=error(n.add("y"))
      check(auxiliaryEvidence(e).startsWith("NAMESPACE_ENTRIES:") && n.size==1 && n.retainedForTest==1)
    }
    locally {
      val seed=new Aux;val words=new Array[String](5);var i=0;var found=0
      while(found<5){val word="chain"+i;if((seed.hash(word)&15)==15){words(found)=word;found+=1};i+=1}
      val a=new Aux(AX.Probe,12);val n=new ExactNames(a,16,8);var admitted=0
      val e=error{while(admitted<5){n.add(words(admitted));admitted+=1}}
      check(auxiliaryEvidence(e).startsWith("PROBES:") && a.value(AX.Probe)==12 && n.size==admitted && admitted<5)
    }
    locally {
      def deep(n:Int):Statement=(0 until n).foldLeft[Statement](EmptyStmt)((x,_)=>Block(Seq(x)))
      val a=new Aux;val b=new Budget;val w=new Walk(a,b);w.start(deep(256));var visits=0;var st=w.next(AX.Uses)
      while(st!=null){visits+=1;w.descend(st);st=w.next(AX.Uses)}
      w.start(deep(257));val e=error{var x=w.next(AX.Uses);while(x!=null){w.descend(x);x=w.next(AX.Uses)}}
      check(visits==257 && boundEvidence(e).startsWith("STATEMENT_DEPTH:"))
    }
    locally {
      val a=new Aux(AX.Copy,3);val r=replacement(a);val w=new Rewriter(r,a,new Budget)
      val root=Block(Seq(EmptyStmt,Block(Seq(EmptyStmt,reg))))
      val e=error(w.rewrite(root))
      check(auxiliaryEvidence(e).startsWith("COPY_TOTAL:") && a.value(AX.Copy)==2 && r.get(root)==null)
    }
    locally {
      val a=new Aux(AX.Info,2);val c=new Checked(a,new Budget)
      val x=new MultiInfo(Seq(FileInfo("same"),FileInfo("last")))
      val e=error(c.equalValidated(x,x))
      check(auxiliaryEvidence(e).startsWith("INFO_VISITS:") && a.value(AX.Info)==2)
    }
    locally {
      val a=new Aux(AX.Uses,1);val w=new Walk(a,new Budget);val root=Block(Seq(EmptyStmt))
      w.start(root);require(w.next(AX.Uses) eq root);w.descend(root);val e=error(w.next(AX.Uses))
      check(auxiliaryEvidence(e).startsWith("USE_VISITS:") && a.value(AX.Uses)==1)
    }
    locally {
      val a=new Aux(AX.Live,0);val e=error{new ExactNames(a,8,4);()}
      check(auxiliaryEvidence(e).startsWith("LIVE_BYTES:") && a.value(AX.Live)==0)
    }
    locally {
      val c=ComponentName("foo.field[12]",ModuleName("M",CircuitName("C")))
      val a=new Aux(AX.Iterator,5124);val target=checkedNamed(c,a)
      check(target.ref=="foo" && target.component==Seq(TargetToken.Field("field"),TargetToken.Index(12)) &&
        a.value(AX.Iterator)==5124 && a.namedConversions==1)
    }
    locally {
      val c=ComponentName("foo.field[12]",ModuleName("M",CircuitName("C")))
      val a=new Aux(AX.Iterator,5123);val live=a.value(AX.Live);val e=error(checkedNamed(c,a))
      check(auxiliaryEvidence(e).startsWith("ITERATOR_UNITS:") && a.namedConversions==0 && a.value(AX.Live)==live)
    }
    locally {
      val c=ComponentName("foo",ModuleName("M",CircuitName("C")))
      val a=new Aux(AX.Iterator,1026);a.transient(513);checkedNamed(c,a)
      val e=error(checkedNamed(c,a))
      check(auxiliaryEvidence(e)=="ITERATOR_UNITS:INDEX_PREPARED:1026:513:1026" && a.namedConversions==1)
    }
    locally {
      val c=ComponentName("x"+"]"*4095,ModuleName("M",CircuitName("C")))
      val a=new Aux;val live=a.value(AX.Live);val e=error(checkedNamed(c,a))
      val evidence=auxiliaryEvidence(e).split(":",-1)
      check(evidence(0)=="ITERATOR_UNITS" && evidence(3).toLong<(1L<<30) &&
        a.namedConversions==0 && a.value(AX.Live)==live)
    }
    locally {
      val c=ComponentName("foo]]",ModuleName("M",CircuitName("C")))
      val a=new Aux(AX.Iterator,3075);val target=checkedNamed(c,a)
      check(target.ref=="foo" && target.component.isEmpty && a.namedConversions==1 && a.value(AX.Iterator)==3075)
    }
    def infoSuccess(info:Info):Unit={
      val a=new Aux;val b=new Budget;val old=new Budget;val c=new Checked(a,b)
      val result=c.infoPresent(info);val legacy=checkedInfo(info,old)
      check(result==legacy && b.work==old.work)
    }
    infoSuccess(deepInfo(16))
    infoSuccess(new MultiInfo(Vector.fill(64)(NoInfo)))
    infoSuccess(FileInfo("x"*4096))
    locally {
      val t=BundleType(Seq(Field("left",Default,VectorType(UIntType(IntWidth(3)),4)),
        Field("right",Flip,BundleType(Seq(Field("clock",Default,ClockType),Field("data",Default,VectorType(UIntType(IntWidth(1)),2)))))))
      val a=new Aux;val b=new Budget;val old=new Budget;val c=new Checked(a,b)
      c.checkType(t);boundedType(t,old);check(b.work==old.work && b.work==7)
    }
    locally {
      val root=DoPrim(firrtl2.PrimOps.Add,Seq(Mux(clk,zero,zero,UIntType(IntWidth(1))),
        ValidIf(clk,zero,UIntType(IntWidth(1)))),Nil,UIntType(IntWidth(1)))
      val a=new Aux;val b=new Budget;val old=new Budget;val selected=new Selected(a)
      val walker=new Expressions(a,b,selected);walker.statement=DefNode(NoInfo,"holder",root);walker.root(root)
      var stack=List((root:Expression,0))
      while(stack.nonEmpty){val (e,d)=stack.head;stack=stack.tail;old.tick();old.bound(d<=256,"EXPRESSION_DEPTH")
        e match {case r:Reference=>old.name(r.name);case _=>()}
        e.foreachExpr{x=>old.tick();stack=(x,d+1)::stack}
      }
      check(b.work==old.work && b.work==15)
    }
    locally {
      val a=new Aux;val b=new Budget;val c=new Checked(a,b);val selected=new Selected(a)
      val e=error(anchor(Print(FileInfo("x"*4097),StringLit(""),Nil,clk,zero),-1,selected,a,b,c))
      val f=error(anchor(Stop(FileInfo("x"*4097),0,clk,zero),-1,selected,a,b,c))
      check(boundEvidence(e).startsWith("INFO_STRING:") && boundEvidence(f).startsWith("INFO_STRING:"))
    }
    locally {
      val a=new Aux
      a.iter(List(EmptyStmt));a.iter(Vector(EmptyStmt))
      a.iter(scala.collection.immutable.ArraySeq.unsafeWrapArray(Array[Statement](EmptyStmt)))
      // BEGIN WIR COLLECTION SEQUENCE SIGNATURE REGRESSION
      val sequenceUnits=a.value(AX.Iterator)
      val generalExpressions:scala.collection.Seq[Expression]=List(zero)
      val generalConnections:scala.collection.Seq[(Expression,Expression)]=List((clk,clk))
      rootSequenceFamilies(firrtl2.WDefInstanceConnector(NoInfo,"fixture_instance","M",UnknownType,generalConnections),a)
      rootSequenceFamilies(firrtl2.CDefMPort(NoInfo,"fixture_port",ClockType,"memory",generalExpressions,firrtl2.MRead),a)
      val mutableExpressions=scala.collection.mutable.ArrayBuffer[Expression](zero)
      val mutableConnections=scala.collection.mutable.ArrayBuffer[(Expression,Expression)]((clk,clk))
      val rejectedConnection=error(rootSequenceFamilies(firrtl2.WDefInstanceConnector(NoInfo,"fixture_instance","M",UnknownType,mutableConnections),a))
      val rejectedPort=error(rootSequenceFamilies(firrtl2.CDefMPort(NoInfo,"fixture_port",ClockType,"memory",mutableExpressions,firrtl2.MRead),a))
      require(auxiliaryEvidence(rejectedConnection)=="SEQUENCE_FAMILY:INDEX_PREPARED:0:1:0" &&
        auxiliaryEvidence(rejectedPort)=="SEQUENCE_FAMILY:INDEX_PREPARED:0:1:0" &&
        mutableExpressions.length==1 && (mutableExpressions.head eq zero) && mutableConnections.length==1 && a.value(AX.Iterator)==sequenceUnits)
      // END WIR COLLECTION SEQUENCE SIGNATURE REGRESSION
      val units=a.value(AX.Iterator)
      val e=error(a.iter(scala.collection.immutable.Queue(EmptyStmt)))
      val c=new Checked(a,new Budget)
      val f=error(c.checkType(BundleType(scala.collection.immutable.Queue(Field("x",Default,ClockType)))))
      check(auxiliaryEvidence(e)=="SEQUENCE_FAMILY:INDEX_PREPARED:0:1:0" &&
        auxiliaryEvidence(f)=="SEQUENCE_FAMILY:INDEX_PREPARED:0:1:0" && a.value(AX.Iterator)==units)
    }
    require(checks==62);checks
  }
  // BEGIN PREEXISTING COLLISION DIAGNOSTIC
  // Failure-only evidence. It cannot authorize a repair or replace PREEXISTING.
  private final class PreexistingEvidence(val code:String) extends RuntimeException(null,null,false,false)
  private final class CollisionTruncated extends RuntimeException(null,null,false,false)
  private final class CollisionUnknown extends RuntimeException(null,null,false,false)
  private def collisionCodeValid(code:String):Boolean={
    if(code==null || code.length>384)return false
    if(code=="UNAVAILABLE")return true
    var i=0
    while(i<code.length){val c=code.charAt(i)
      if(!((c>='A' && c<='Z') || (c>='0' && c<='9') || c==':' || c=='_'))return false;i+=1}
    val fields=code.split(":",-1);if(fields.length!=14)return false
    def number(s:String,max:Long):Boolean={
      if(s.isEmpty || s.length>9 || (s.length>1 && s.charAt(0)=='0'))return false
      var value=0L;var j=0
      while(j<s.length){val c=s.charAt(j);if(c<'0' || c>'9')return false;value=value*10+c-'0';j+=1}
      value<=max
    }
    def role(s:String):Boolean=s match {
      case "NONE" | "PORT" | "WIRE" | "REGISTER" | "NODE" | "INSTANCE" | "MEMORY" |
           "PRINT" | "STOP" | "VERIFICATION" | "OTHER" | "MIXED"=>true
      case _=>false
    }
    def tpe(s:String):Boolean=s match {
      case "NONE" | "CLOCK" | "UINT" | "SINT" | "ANALOG" | "RESET" | "ASYNCRESET" |
           "BUNDLE" | "VECTOR" | "OTHER" | "MIXED" | "UNKNOWN"=>true
      case _=>false
    }
    def count(s:String):Boolean=s=="ZERO" || s=="ONE" || s=="MANY"
    def flag(s:String):Boolean=s=="TRUE" || s=="FALSE" || s=="NA" || s=="UNKNOWN"
    if(!number(fields(2),2097152L) || !number(fields(3),268435456L))return false
    if(fields(0)=="TRUNCATED"){
      if(fields(1)!="ORIGINAL" && fields(1)!="PREPARED" && fields(1)!="RELATIONS")return false
      i=4;while(i<14){if(fields(i)!="UNKNOWN")return false;i+=1};true
    }else if(fields(0)=="COMPLETE" && fields(1)=="DONE"){
      role(fields(4)) && tpe(fields(5)) && count(fields(6)) && role(fields(7)) && tpe(fields(8)) && count(fields(9)) &&
        (fields(10)=="TRUE" || fields(10)=="FALSE") && flag(fields(11)) && flag(fields(12)) && flag(fields(13))
    }else false
  }
  def preexistingEvidence(error:Throwable):String=try{
    if(error==null || guardCode(error)!="PREEXISTING")"NONE"
    else {val xs=error.getSuppressed
      if(xs.length==1)xs(0) match {case e:PreexistingEvidence=>if(collisionCodeValid(e.code))e.code else "UNAVAILABLE";case _=>"UNAVAILABLE"}
      else "UNAVAILABLE"
    }
  }catch{case _:Throwable=>"UNAVAILABLE"}
  private final class CollisionBudget(val visitLimit:Int=2097152,val charLimit:Long=268435456L) {
    require(visitLimit>=0 && visitLimit<=2097152 && charLimit>=0 && charLimit<=268435456L)
    var visits=0;var characters=0L;var step="ORIGINAL"
    def visit():Unit={if(visits==visitLimit)throw new CollisionTruncated;visits+=1}
    def equal(x:String,y:String):Boolean={
      require(x!=null && y!=null)
      if(x.length!=y.length)return false
      var i=0
      while(i<x.length){if(characters==charLimit)throw new CollisionTruncated
        characters+=1;if(x.charAt(i)!=y.charAt(i))return false;i+=1};true
    }
    def iterator[A](xs:Seq[A]):Iterator[A]=xs match {
      case _:scala.collection.immutable.List[_] | _:scala.collection.immutable.Vector[_] |
           _:scala.collection.immutable.ArraySeq.ofRef[_]=>xs.iterator
      case _=>throw new CollisionUnknown
    }
    def partial:String="TRUNCATED:"+step+":"+visits+":"+characters+
      ":UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN"
  }
  private final class CollisionMatch {
    var count=0;var role="NONE";var tpe="NONE";var info:Info=null
    var statement:Statement=null;var reference:Expression=null
    var selectedSeen=false;var originalSurvives=false
    def add(r:String,t:String,i:Info,s:Statement,e:Expression):Unit={
      if(count==0){role=r;tpe=t;info=i;statement=s;reference=e}
      else {if(role!=r)role="MIXED";if(tpe!=t)tpe="MIXED"}
      count+=1
    }
    def multiplicity:String=if(count==0)"ZERO"else if(count==1)"ONE"else "MANY"
  }
  // This is a top-constructor classification, not structural type equality.
  // In particular it never visits Bundle/Vector children or compares widths.
  private def collisionType(t:Type):String=t match {
    case ClockType=>"CLOCK";case _:UIntType=>"UINT";case _:SIntType=>"SINT"
    case _:AnalogType=>"ANALOG";case ResetType=>"RESET";case AsyncResetType=>"ASYNCRESET"
    case _:BundleType=>"BUNDLE";case _:VectorType=>"VECTOR";case UnknownType=>"UNKNOWN";case null=>"OTHER";case _=>"OTHER"
  }
  private def collisionExpressionType(e:Expression):String=e match {
    // These exact pinned classes have stored type fields. InfoExpr and unknown
    // delegating wrappers deliberately remain OTHER without invoking .tpe.
    case x:Reference if x.getClass==classOf[Reference]=>collisionType(x.tpe)
    case x:SubField if x.getClass==classOf[SubField]=>collisionType(x.tpe)
    case x:SubIndex if x.getClass==classOf[SubIndex]=>collisionType(x.tpe)
    case x:SubAccess if x.getClass==classOf[SubAccess]=>collisionType(x.tpe)
    case x:Mux if x.getClass==classOf[Mux]=>collisionType(x.tpe)
    case x:ValidIf if x.getClass==classOf[ValidIf]=>collisionType(x.tpe)
    case x:DoPrim if x.getClass==classOf[DoPrim]=>collisionType(x.tpe)
    case x:UIntLiteral if x.getClass==classOf[UIntLiteral]=>"UINT"
    case x:SIntLiteral if x.getClass==classOf[SIntLiteral]=>"SINT"
    case _=>"OTHER"
  }
  private def collisionDeclaration(s:Statement,out:CollisionMatch):Unit=s match {
    case x:DefRegister=>out.add("REGISTER",collisionType(x.tpe),x.info,x,x.clock)
    case x:DefNode=>out.add("NODE",collisionExpressionType(x.value),x.info,x,x.value)
    case x:DefWire=>out.add("WIRE",collisionType(x.tpe),x.info,x,null)
    case x:DefInstance=>out.add("INSTANCE",collisionType(x.tpe),x.info,x,null)
    case x:DefMemory=>out.add("MEMORY",collisionType(x.dataType),x.info,x,null)
    case x:Print=>out.add("PRINT","OTHER",x.info,x,null)
    case x:Stop=>out.add("STOP","OTHER",x.info,x,null)
    case x:Verification=>out.add("VERIFICATION","OTHER",x.info,x,null)
    case x:IsDeclaration=>out.add("OTHER","OTHER",x.info,s,null)
    case _=>throw new CollisionUnknown
  }
  private def collisionScan(m:DefModule,selected:DefRegister,original:Statement,out:CollisionMatch,b:CollisionBudget):Unit={
    val ports=b.iterator(m.ports)
    while(ports.hasNext){b.visit();val p=ports.next()
      if(b.equal(p.name,selected.name))out.add("PORT",collisionType(p.tpe),p.info,null,null)
    }
    m match {
      case mm:Module=>
        // 258 reference slots; at most257 live standard iterators/Two objects.
        // Together with bounded Info recursion and scalar records this is <128KiB.
        val frames=new Array[Iterator[Statement]](258)
        b.visit();var depth = -1;var s:Statement=mm.body;var active=true
        while(active){
          if(s eq original)out.originalSurvives=true
          s match {case d:IsDeclaration if b.equal(d.name,selected.name)=>
            collisionDeclaration(s,out);if(s eq selected)out.selectedSeen=true
            case _=>()}
          val children:Iterator[Statement]=s match {
            case x:Block=>b.iterator(x.stmts)
            case x:Conditionally=>new Two(x.conseq,x.alt)
            case _=>s.foreachStmt(rejectStatementChild);Iterator.empty
          }
          if(children.hasNext){if(depth==255)throw new CollisionTruncated;depth+=1;frames(depth)=children}
          var next:Statement=null
          while(depth>=0 && next==null){val it=frames(depth)
            if(it.hasNext){b.visit();next=it.next()}else{frames(depth)=null;depth-=1}}
          if(next==null)active=false else s=next
        }
      case _:ExtModule=>()
      case _=>throw new CollisionUnknown
    }
  }
  private final class CollisionInfo(b:CollisionBudget) {
    private var count=0
    private def validate(i:Info,depth:Int):Unit={
      if(depth>16 || count==256)throw new CollisionUnknown;count+=1
      i match {
        case NoInfo=>()
        case x:FileInfo=>if(x.escaped==null || x.escaped.length>4096)throw new CollisionUnknown
        case x:MultiInfo=>val it=b.iterator(x.infos);var children=0
          while(it.hasNext){if(children==64)throw new CollisionUnknown;children+=1;validate(it.next(),depth+1)}
        case _=>throw new CollisionUnknown
      }
    }
    private def equal(x:Info,y:Info,depth:Int):Boolean={
      if(depth>16)throw new CollisionUnknown
      x match {
        case NoInfo=>y eq NoInfo
        case f:FileInfo=>y match {case g:FileInfo=>b.equal(f.escaped,g.escaped);case _=>false}
        case m:MultiInfo=>y match {
          case n:MultiInfo=>val xi=b.iterator(m.infos);val yi=b.iterator(n.infos)
            while(xi.hasNext && yi.hasNext){if(!equal(xi.next(),yi.next(),depth+1))return false}
            !xi.hasNext && !yi.hasNext
          case _=>false
        }
        case _=>throw new CollisionUnknown
      }
    }
    def relation(x:Info,y:Info):String=try{
      count=0;validate(x,0);count=0;validate(y,0)
      if(equal(x,y,0))"TRUE"else"FALSE"
    }catch{case _:CollisionUnknown=>"UNKNOWN"}
  }
  private def collisionReference(e:Expression,clock:Reference,b:CollisionBudget):String=e match {
    // Selected clock was already qualified as ClockType/PortKind/SourceFlow.
    // Exact equality therefore only needs its name and these singleton fields;
    // no recursive Type.equals, widths or arbitrary expression equality is used.
    case r:Reference=>
      if(clock.tpe!=ClockType || clock.kind!=PortKind || clock.flow!=SourceFlow)"UNKNOWN"
      else if(r.tpe!=ClockType || r.kind!=PortKind || r.flow!=SourceFlow)"FALSE"
      else if(b.equal(r.name,clock.name))"TRUE"else"FALSE"
    case _=>"FALSE"
  }
  private def collisionCollect(original:DefModule,prepared:DefModule,selected:DefRegister,clock:Reference,b:CollisionBudget):String=try{
    require(selected.name!=null && selected.name.nonEmpty && selected.name.length<=4096)
    val old=new CollisionMatch;val fresh=new CollisionMatch
    collisionScan(original,selected,null,old,b)
    b.step="PREPARED";collisionScan(prepared,selected,if(old.count==1)old.statement else null,fresh,b)
    b.step="RELATIONS"
    val info=if(old.count==0)"NA"else if(old.count!=1)"UNKNOWN"else(new CollisionInfo(b)).relation(old.info,selected.info)
    val reference=if(old.count==0)"NA"else if(old.count!=1)"UNKNOWN"
      else if(old.role=="REGISTER" || old.role=="NODE")collisionReference(old.reference,clock,b)else"NA"
    val survives=if(old.count==0)"NA"else if(old.count!=1)"UNKNOWN"
      else if(old.statement==null)"NA"else if(fresh.originalSurvives)"TRUE"else"FALSE"
    "COMPLETE:DONE:"+b.visits+":"+b.characters+":"+old.role+":"+old.tpe+":"+old.multiplicity+
      ":"+fresh.role+":"+fresh.tpe+":"+fresh.multiplicity+":"+(if(fresh.selectedSeen)"TRUE"else"FALSE")+
      ":"+info+":"+reference+":"+survives
  }catch{case _:CollisionTruncated=>b.partial;case _:Throwable=>"UNAVAILABLE"}
  private def preexistingFail(original:DefModule,fresh:Modules,selected:DefRegister,clock:Reference):Nothing={
    val error=new IllegalArgumentException("PREEXISTING")
    try{
      // Any lookup/allocation/scan problem stays inside this diagnostic boundary.
      val prepared=fresh.get(original.name)
      val code=collisionCollect(original,prepared,selected,clock,new CollisionBudget)
      error.addSuppressed(new PreexistingEvidence(code))
    }catch{case _:Throwable=>()}
    throw error
  }
  // END PREEXISTING COLLISION DIAGNOSTIC
  // BEGIN PREEXISTING COLLISION SELFCHECKS
  def preexistingSelfChecks():Int={
    var checks=0
    def check(p:Boolean):Unit={require(p);checks+=1}
    val info=FileInfo("origin");val zero=UIntLiteral(0,IntWidth(1))
    val clock=Reference("clk",ClockType,PortKind,SourceFlow)
    val selected=DefRegister(info,"delay",ClockType,clock,zero,zero)
    val node=DefNode(info,"delay",clock)
    def module(s:Statement,ports:Seq[Port]=Nil):Module=Module(NoInfo,"M",ports,s)
    def collect(old:DefModule,fresh:DefModule,b:CollisionBudget=new CollisionBudget):String=
      collisionCollect(old,fresh,selected,clock,b)
    def fields(s:String):Array[String]={val xs=s.split(":",-1);require(xs.length==14);xs}
    def partial(step:String,visits:Int,chars:Long):String="TRUNCATED:"+step+":"+visits+":"+chars+
      ":UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN:UNKNOWN"
    val exact="COMPLETE:DONE:2:19:NODE:CLOCK:ONE:REGISTER:CLOCK:ONE:TRUE:TRUE:TRUE:FALSE"
    check(collect(module(node),module(selected))==exact)
    locally {
      val original=selected.copy();val xs=fields(collect(module(original),module(Block(Seq(original,selected)))))
      check(xs(4)=="REGISTER" && xs(6)=="ONE" && xs(9)=="MANY" && xs(10)=="TRUE" && xs(13)=="TRUE")
    }
    locally {
      val xs=fields(collect(module(EmptyStmt,Seq(Port(info,"delay",Input,ClockType))),module(selected)))
      check(xs(4)=="PORT" && xs(5)=="CLOCK" && xs(6)=="ONE" && xs(11)=="TRUE" && xs(12)=="NA" && xs(13)=="NA")
    }
    locally {
      val xs=fields(collect(module(DefWire(NoInfo,"delay",UIntType(IntWidth(3)))),module(selected)))
      check(xs(4)=="WIRE" && xs(5)=="UINT" && xs(11)=="FALSE" && xs(12)=="NA" && xs(13)=="FALSE")
    }
    locally {
      val xs=fields(collect(module(Block(Seq(node,DefWire(info,"delay",UIntType(IntWidth(1)))))),module(selected)))
      check(xs(4)=="MIXED" && xs(5)=="MIXED" && xs(6)=="MANY" && xs(11)=="UNKNOWN" && xs(12)=="UNKNOWN" && xs(13)=="UNKNOWN")
    }
    locally {
      val xs=fields(collect(module(Block(Seq(node,node.copy()))),module(selected)))
      check(xs(4)=="NODE" && xs(5)=="CLOCK" && xs(6)=="MANY" && xs(11)=="UNKNOWN")
    }
    locally {
      val xs=fields(collect(module(node),module(selected.copy())))
      check(xs(9)=="ONE" && xs(10)=="FALSE")
    }
    locally {
      val xs=fields(collect(module(EmptyStmt),module(EmptyStmt)))
      check(xs.drop(4).mkString(":")=="NONE:NONE:ZERO:NONE:NONE:ZERO:FALSE:NA:NA:NA")
    }
    locally {
      val xs=fields(collect(module(node.copy(value=clock.copy(flow=firrtl2.SinkFlow))),module(selected)))
      check(xs(12)=="FALSE")
    }
    locally {
      val multi=new MultiInfo(Seq(FileInfo("first"),FileInfo("second")))
      val reversed=new MultiInfo(Seq(FileInfo("second"),FileInfo("first")))
      val reg=selected.copy(info=multi)
      val xs=fields(collisionCollect(module(node.copy(info=reversed)),module(reg),reg,clock,new CollisionBudget))
      check(xs(11)=="FALSE")
    }
    locally {
      val deep=(0 until 17).foldLeft[Info](info)((i,_)=>new MultiInfo(Seq(i)))
      val xs=fields(collect(module(node.copy(info=deep)),module(selected)))
      check(xs(0)=="COMPLETE" && xs(11)=="UNKNOWN" && xs(12)=="TRUE")
    }
    check(collect(module(node),module(selected),new CollisionBudget(2097152,18))==partial("RELATIONS",2,18))
    check(collect(module(node),module(selected),new CollisionBudget(1,268435456L))==partial("PREPARED",1,5))
    check(collect(module(node),module(selected),new CollisionBudget(0,268435456L))==partial("ORIGINAL",0,0))
    locally {
      val tree=(0 until 256).foldLeft[Statement](node)((s,_)=>Block(Seq(s)))
      val xs=fields(collect(module(tree),module(selected)))
      check(xs(0)=="COMPLETE" && xs(2)=="258" && xs(4)=="NODE")
    }
    locally {
      val tree=(0 until 257).foldLeft[Statement](node)((s,_)=>Block(Seq(s)))
      check(collect(module(tree),module(selected))==partial("ORIGINAL",257,0))
    }
    locally {
      val b=new CollisionBudget(2,19);val out=collect(module(node),module(selected),b)
      check(out==exact && b.visits==2 && b.characters==19)
    }
    locally {
      val sentinel="PRIVATE_COLLISION_NAME_"+"z"*32
      val reg=selected.copy(name=sentinel);val n=node.copy(name=sentinel)
      val out=collisionCollect(module(n),module(reg),reg,clock,new CollisionBudget)
      check(out.startsWith("COMPLETE:DONE:") && !out.contains(sentinel) && !out.contains(info.escaped))
    }
    locally {
      val a=new Aux;val ms=new Modules(a);ms.add(module(selected),0)
      var caught:Throwable=null
      try{preexistingFail(module(node),ms,selected,clock)}catch{case e:IllegalArgumentException=>caught=e}
      check(caught!=null && caught.getClass==classOf[IllegalArgumentException] && guardCode(caught)=="PREEXISTING" && preexistingEvidence(caught)==exact)
    }
    locally {
      val a=new Aux(AX.Hash,1);val ms=new Modules(a);ms.add(module(selected),0)
      var caught:Throwable=null
      try{preexistingFail(module(node),ms,selected,clock)}catch{case e:IllegalArgumentException=>caught=e}
      check(caught!=null && guardCode(caught)=="PREEXISTING" && preexistingEvidence(caught)=="UNAVAILABLE")
    }
    locally {
      val missing=new IllegalArgumentException("PREEXISTING")
      val bad=new IllegalArgumentException("PREEXISTING");bad.addSuppressed(new RuntimeException())
      val duplicate=new IllegalArgumentException("PREEXISTING")
      duplicate.addSuppressed(new PreexistingEvidence(exact));duplicate.addSuppressed(new PreexistingEvidence(exact))
      check(preexistingEvidence(null)=="NONE" && preexistingEvidence(new IllegalArgumentException("CLOCK"))=="NONE" &&
        preexistingEvidence(missing)=="UNAVAILABLE" && preexistingEvidence(bad)=="UNAVAILABLE" && preexistingEvidence(duplicate)=="UNAVAILABLE")
    }
    locally {
      val xs=fields(collect(module(DefWire(info,"delay",UnknownType)),module(selected)))
      check(xs(4)=="WIRE" && xs(5)=="UNKNOWN" && xs(6)=="ONE")
    }
    locally {
      val xs=fields(collect(module(node.copy(value=firrtl2.EmptyExpression)),module(selected)))
      val deep=(0 until 4096).foldLeft[Expression](firrtl2.EmptyExpression)((e,_)=>ValidIf(clock,e,ClockType))
      val ys=fields(collect(module(node.copy(value=deep)),module(selected),new CollisionBudget(2,16)))
      check(xs(0)=="COMPLETE" && xs(4)=="NODE" && xs(5)=="OTHER" && xs(12)=="FALSE" &&
        ys(0)=="COMPLETE" && ys(2)=="2" && ys(5)=="CLOCK")
    }
    locally {
      val bad=new IllegalArgumentException("PREEXISTING")
      bad.addSuppressed(new PreexistingEvidence(exact.replace(":NODE:",":INVENTED_TOKEN:")))
      val badCounter=new IllegalArgumentException("PREEXISTING")
      badCounter.addSuppressed(new PreexistingEvidence(exact.replace(":2:19:",":02:19:")))
      check(preexistingEvidence(bad)=="UNAVAILABLE" && preexistingEvidence(badCounter)=="UNAVAILABLE" &&
        !collisionCodeValid("x"*385) && !collisionCodeValid(exact.replace(":2:19:",":2097153:19:")))
    }
    require(checks==24);checks
  }
  // END PREEXISTING COLLISION SELFCHECKS

}

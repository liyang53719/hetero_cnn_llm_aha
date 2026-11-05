package chiseltest.simulator

import firrtl2.{AnnotationSeq,CircuitState,NodeKind,PortKind,SourceFlow,SinkFlow,Transform}
import firrtl2.ir._
import firrtl2.options.{Dependency,Phase}
import firrtl2.passes.memlib.VerilogMemDelays
import firrtl2.stage.{FirrtlCircuitAnnotation,Forms}
import firrtl2.transforms.BlackBoxSourceHelper
import treadle2.TreadleCircuitStateAnnotation
import treadle2.stage.phases.HandleFormalStatements
import treadle2.utils.AugmentPrintf
import java.lang.ref.WeakReference

/** Diagnostic only. No result from this phase permits or performs a repair. */
final class ObservedPrepareAst(expected:Int=394) extends Phase {
  import ObservedPrepareAst._
  private val targets = Seq(
    Dependency(firrtl2.transforms.EnsureNamedStatements),
    Dependency[BlackBoxSourceHelper],
    Dependency[AugmentPrintf],
    Dependency[HandleFormalStatements]
  ) ++ Forms.LowFormOptimized ++ Seq(Dependency(VerilogMemDelays))
  private def compiler = new firrtl2.stage.transforms.Compiler(targets,currentState=Nil)
  private val transforms = compiler.flattenedTransformOrder
  ObservedScheduleIdentity.verify(transforms)
  private var result="UNAVAILABLE:CENSUS:NOT_RUN:0:0:0:0:0:0:0:0:0"
  def evidence:String=result
  private var budgetResult="NONE";private var sizingResult="NONE"
  def budgetEvidence:String=budgetResult
  def sizingEvidence:String=sizingResult
  private var consumerResult="NONE"
  def consumerEvidence:String=consumerResult
  private var anchorResult="NONE"
  def anchorEvidence:String=anchorResult
  private var formalResult="UNAVAILABLE:0:0:0:0"
  def formalEvidence:String=formalResult
  override def transform(annotationSeq:AnnotationSeq):AnnotationSeq={
    result="UNAVAILABLE:CENSUS:NOT_RUN:0:0:0:0:0:0:0:0:0"
    budgetResult="NONE";sizingResult="NONE";consumerResult="NONE";anchorResult="NONE";formalResult="UNAVAILABLE:0:0:0:0"
    var circuits=0
    annotationSeq.flatMap {
      case FirrtlCircuitAnnotation(circuit)=>
        circuits=if(circuits==0)1 else 2
        val observation=if(circuits==1)try{new Observation(expected)}catch{case _:Throwable=>null}else null
        val state=CircuitState(circuit,annotationSeq)
        var index=0
        try {
          val newState=transforms.foldLeft(state){case(prevState,transform)=>
            // The previous fold invocation has returned: its old accumulator is
            // no longer retained by an observer scan. No transform intervenes.
            if(observation!=null && index==52)observation.sizePending(prevState)
            if(observation!=null && (index==53 || index==54))observation.afterSuffix(index-1,prevState)
            if(observation!=null)observation.before(index,prevState)
            val admittedInput=if(index==51 && observation!=null && observation.retainsInput)prevState else null
            val nextState=transform.runTransform(prevState)
            if(admittedInput!=null)observation.afterAugment(admittedInput,nextState)
            index+=1
            nextState
          }
          if(observation!=null)observation.afterSuffix(54,newState)
          result=if(circuits>1)"UNAVAILABLE:DONE:MULTIPLE_CIRCUITS:0:0:0:0:0:0:0:0:0" else if(observation==null)"UNAVAILABLE:CENSUS:UNEXPECTED:0:0:0:0:0:0:0:0:0" else observation.evidence
          if(circuits==1 && observation!=null){budgetResult=observation.budgetEvidence;sizingResult=observation.sizingEvidence;consumerResult=observation.consumerEvidence;anchorResult=observation.anchorEvidence;formalResult=observation.formalEvidence}
          else {budgetResult="NONE";sizingResult="NONE";consumerResult="NONE";anchorResult="NONE";formalResult="UNAVAILABLE:0:0:0:0"}
          Some(TreadleCircuitStateAnnotation(newState))
        } finally if(observation!=null)observation.release()
      case other=>Some(other)
    }
  }
}

object ObservedPrepareAst {
  private final class Abort(val reason:String,val bounded:Boolean=false) extends RuntimeException(null,null,false,false) {
    var consumerCode:String="NONE"
    var anchorCode:String="NONE"
  }
  // BEGIN FIRST CONSUMER FAILURE DIAGNOSTIC
  private def consumerSlot(out:java.lang.StringBuilder,s:Statement,root:Expression,direct:Boolean):Unit={
    need(s!=null&&root!=null,"CONSUMER")
    val sc=s.getClass
    var role="OTHER";var mask=0;var op="NA";var message="NA"
    if(sc==classOf[Connect]){val x=s.asInstanceOf[Connect];role="CONNECT"
      if(root eq x.loc)mask|=1;if(root eq x.expr)mask|=2}
    else if(sc==classOf[Print]){val x=s.asInstanceOf[Print];role="PRINT"
      if(root eq x.clk)mask|=1;if(root eq x.en)mask|=2}
    else if(sc==classOf[Stop]){val x=s.asInstanceOf[Stop];role="STOP"
      if(root eq x.clk)mask|=1;if(root eq x.en)mask|=2}
    else if(sc==classOf[Verification]){val x=s.asInstanceOf[Verification];role="VERIFICATION"
      if(root eq x.clk)mask|=1;if(root eq x.pred)mask|=2;if(root eq x.en)mask|=4
      op=if(x.op eq Formal.Assert)"ASSERT"else if(x.op eq Formal.Assume)"ASSUME"else if(x.op eq Formal.Cover)"COVER"else"OTHER"
      need(x.msg!=null&&x.msg.getClass==classOf[StringLit],"CONSUMER")
      message=if(x.msg.string.length==0)"EMPTY"else"NONEMPTY"
    }
    var typ="NA";var kind="NA";var flow="NA"
    if(root.getClass==classOf[Reference]){val r=root.asInstanceOf[Reference]
      typ=if(r.tpe eq ClockType)"CLOCK"else if(r.tpe!=null&&r.tpe.getClass==classOf[UIntType])"UINT"else"OTHER"
      val k=r.kind
      kind=if(k eq NodeKind)"NODE"else if(k eq PortKind)"PORT"else if(k eq firrtl2.RegKind)"REG"
        else if(k eq firrtl2.WireKind)"WIRE"else if(k eq firrtl2.InstanceKind)"INSTANCE"
        else if(k eq firrtl2.MemKind)"MEM"else if(k eq firrtl2.ExpKind)"EXP"
        else if(k eq firrtl2.UnknownKind)"UNKNOWN"else if(k eq firrtl2.PoisonKind)"POISON"
        else if(k eq firrtl2.RandomKind)"RANDOM"else"OTHER"
      val f=r.flow
      flow=if(f eq SourceFlow)"SOURCE"else if(f eq SinkFlow)"SINK"else if(f eq firrtl2.DuplexFlow)"DUPLEX"
        else if(f eq firrtl2.UnknownFlow)"UNKNOWN"else"OTHER"
    }
    out.append(':').append(role).append(':').append(mask).append(':').append(if(direct)"TRUE"else"FALSE")
      .append(':').append(typ).append(':').append(kind).append(':').append(flow).append(':').append(op).append(':').append(message)
  }
  private def consumerToken(s:String,start:Int,end:Int,t:String):Boolean=
    end-start==t.length&&s.regionMatches(start,t,0,t.length)
  private def validConsumerCode(s:String):Boolean={
    if(s==null||s.length==0||s.length>512)return false
    var i=0;var start=0;var field=0;var role=0;var referenceNA=false
    while(i<=s.length){
      if(i==s.length||s.charAt(i)==':'){
        val end=i
        def is(t:String):Boolean=consumerToken(s,start,end,t)
        val valid=if(field==0)is("DUPLICATE")||is("MISSING")||is("FINAL_KIND") else ((field-1)%8)match{
          case 0=>role=if(is("VERIFICATION"))4 else if(is("CONNECT"))1 else if(is("PRINT"))2 else if(is("STOP"))3 else if(is("OTHER"))0 else -1;role>=0
          case 1=>end-start==1&&s.charAt(start)>='0'&&s.charAt(start)<=(if(role==4)'7'else if(role==0)'0'else'3')
          case 2=>is("TRUE")||is("FALSE")
          case 3=>referenceNA=is("NA");referenceNA||is("CLOCK")||is("UINT")||is("OTHER")
          case 4=>if(referenceNA)is("NA")else is("NODE")||is("PORT")||is("REG")||is("WIRE")||is("INSTANCE")||is("MEM")||is("EXP")||is("UNKNOWN")||is("POISON")||is("RANDOM")||is("OTHER")
          case 5=>if(referenceNA)is("NA")else is("SOURCE")||is("SINK")||is("DUPLEX")||is("UNKNOWN")||is("OTHER")
          case 6=>if(role==4)is("ASSERT")||is("ASSUME")||is("COVER")||is("OTHER")else is("NA")
          case 7=>if(role==4)is("EMPTY")||is("NONEMPTY")else is("NA")
        }
        if(!valid)return false
        field+=1;if(field>17)return false;start=i+1
      }else {val c=s.charAt(i);if(!((c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'))return false}
      i+=1
    };field==17
  }
  private def consumerCode(error:Abort):String=try{
    val code=error.consumerCode
    if(validConsumerCode(code))code else "UNAVAILABLE"
  }catch{case _:Throwable=>"UNAVAILABLE"}
  private def consumerAbort(site:String,s0:Statement,r0:Expression,d0:Boolean,s1:Statement,r1:Expression,d1:Boolean):Abort={
    // Primary rejection exists before formatting. Only bounded scalar strings
    // can escape.160 ASCII capacity exceeds the maximum130-character record;
    // builder/result/header/primary objects fit the fixed2KiB failure reserve.
    val primary=new Abort("CONSUMER")
    primary.consumerCode="UNAVAILABLE"
    try{
      need(site=="DUPLICATE"||site=="MISSING"||site=="FINAL_KIND","CONSUMER")
      val out=new java.lang.StringBuilder(160);out.append(site)
      consumerSlot(out,s0,r0,d0);consumerSlot(out,s1,r1,d1)
      val code=out.toString
      if(validConsumerCode(code))primary.consumerCode=code
    }catch{case _:Throwable=>()}
    primary
  }
  // END FIRST CONSUMER FAILURE DIAGNOSTIC

  // BEGIN FIRST ANCHOR FAILURE DIAGNOSTIC
  private def anchorRole(s:Statement):String={
    if(s==null)"OTHER"
    else if(s.getClass==classOf[Print])"PRINT"
    else if(s.getClass==classOf[Stop])"STOP"
    else if(s.getClass==classOf[Verification]){val v=s.asInstanceOf[Verification]
      if((v.op eq Formal.Assert)&&v.msg!=null&&v.msg.getClass==classOf[StringLit]&&v.msg.string.length==0)"EMPTY_ASSERT"else"OTHER"}
    else "OTHER"
  }
  private def validAnchorCode(s:String):Boolean={
    if(s==null||s.length>160)return false
    var field=0;var start=0;var i=0
    while(i<=s.length){
      if(i==s.length||s.charAt(i)==':'){
        def is(v:String):Boolean=s.regionMatches(start,v,0,i-start)&&v.length==i-start
        val ok=field match{
          case 0=>is("AVAILABLE")
          case 1=>is("FORMAL_NAME_INFO")||is("FORMAL_CLOCK")||is("FORMAL_DUPLICATE")||is("ORDINARY_DUPLICATE")||is("FINAL_MISSING")
          case 2=>is("PRINT")||is("STOP")||is("EMPTY_ASSERT")||is("OTHER")
          case 3|4|5=>is("TRUE")||is("FALSE")||is("NA")
          case 6=>is("ZERO")||is("ONE")||is("OTHER")
          case _=>false}
        if(!ok)return false
        field+=1;start=i+1
      }else {val c=s.charAt(i);if(!((c>='A'&&c<='Z')||c=='_'))return false}
      i+=1
    };field==7
  }
  private def anchorCode(error:Abort):String=try{
    if(validAnchorCode(error.anchorCode))error.anchorCode else "UNAVAILABLE"
  }catch{case _:Throwable=>"UNAVAILABLE"}
  private def anchorAbort(site:String,s:Statement,other:Statement,reg:DefRegister,name:String,prior:Int):Abort={
    // No object escapes except the primary rejection and its bounded scalar code.
    // Existing fixed2KiB failure scratch covers builder/result and local scalars.
    val primary=new Abort("ANCHOR");primary.anchorCode="UNAVAILABLE"
    try{
      val role=anchorRole(s);var ni="NA";var ii="NA";var ci="NA"
      def flag(v:Boolean):String=if(v)"TRUE"else"FALSE"
      if(site=="FORMAL_NAME_INFO"||site=="FORMAL_CLOCK"||site=="FORMAL_DUPLICATE"){
        if(role!="EMPTY_ASSERT"||reg==null||reg.getClass!=classOf[DefRegister])return primary
        val v=s.asInstanceOf[Verification]
        ni=flag(v.name eq name);ii=flag(v.info eq reg.info);ci=flag(v.clk eq reg.clock)
      }else if(site=="ORDINARY_DUPLICATE"){
        if(role=="PRINT"&&other!=null&&other.getClass==classOf[Print]){
          val a=s.asInstanceOf[Print];val z=other.asInstanceOf[Print];ni=flag(a.name eq z.name);ii=flag(a.info eq z.info)
        }else if(role=="STOP"&&other!=null&&other.getClass==classOf[Stop]){
          val a=s.asInstanceOf[Stop];val z=other.asInstanceOf[Stop];ni=flag(a.name eq z.name);ii=flag(a.info eq z.info)
        }else return primary
      }else if(site!="FINAL_MISSING")return primary
      val p=if(prior==0)"ZERO"else if(prior==1)"ONE"else"OTHER"
      val out=new java.lang.StringBuilder(160)
      out.append("AVAILABLE:").append(site).append(':').append(role).append(':').append(ni).append(':').append(ii).append(':').append(ci).append(':').append(p)
      val code=out.toString;if(validAnchorCode(code))primary.anchorCode=code
    }catch{case _:Throwable=>()}
    primary
  }
  // END FIRST ANCHOR FAILURE DIAGNOSTIC

  private def fail(code:String):Nothing=throw new Abort(code)
  private def need(value:Boolean,code:String):Unit=if(!value)fail(code)
  // All allocations belong either to the explicit fixed inventory or to Temp.
  // Fixed: namespace20MiB, module/key/record/frame pools<2MiB, comparison8MiB,
  // transitive names4MiB, Info nodes64MiB + child backing0.5MiB: <128MiB.
  // The independent416MiB old-root lifetime admission is checked by census.
  private object C {
    val Visit=0;val Expr=1;val Names=2;val Hash=3;val Equal=4;val Probe=5;val Clear=6;val Temp=7
    val ScanExpr:Long=1L<<24
    val limits=Array[Long](1L<<24,1L<<25,1L<<22,1L<<29,1L<<30,1L<<26,1L<<22,1L<<24)
  }
  private final class Budget {
    val used=new Array[Long](8)
    var scanVisit=0L;var scanExpr=0L
    def start():Unit={scanVisit=0;scanExpr=0}
    // Successful categories TYPE/INFO/NODE/EDGE/OTHER. No rejected charge is
    // included, and default OTHER preserves every existing generic charge site.
    val prefix=new Array[Long](5)
    var failedDimension = -1
    private var failedUsed=0L;private var failedScan=0L;private var failedRequest=0L;private var failedLimit=0L
    private var failedExpr=0L;private var failedScanExpr=0L
    private def reject(id:Int,n:Long,dimension:Int,limit:Long,code:String):Nothing={
      if(failedDimension<0 && n>=0){failedDimension=dimension;failedUsed=used(id)
        failedScan=if(id==C.Visit)scanVisit else if(id==C.Expr)scanExpr else 0L
        failedRequest=n;failedLimit=limit;failedExpr=used(C.Expr);failedScanExpr=scanExpr}
      throw new Abort(code,true)
    }
    def charge(id:Int,n:Long=1,category:Int=4):Unit={
      if(n<0 || n>C.limits(id)-used(id))reject(id,n,id,C.limits(id),"BUDGET")
      if(id==C.Visit && n>(1L<<22)-scanVisit)reject(id,n,8,1L<<22,"SCAN_BUDGET")
      if(id==C.Expr && n>(C.ScanExpr)-scanExpr)reject(id,n,9,C.ScanExpr,"SCAN_BUDGET")
      used(id)+=n;if(id==C.Visit)scanVisit+=n;if(id==C.Expr){scanExpr+=n;prefix(category)+=n}
    }
    def failureEvidence:String={
      if(failedDimension<0)return "NONE"
      val dim=failedDimension match{case 0=>"GLOBAL_VISIT";case 1=>"GLOBAL_EXPR";case 2=>"NAMES"
        case 3=>"HASH";case 4=>"EQUAL";case 5=>"PROBE";case 6=>"CLEAR";case 7=>"TEMP"
        case 8=>"SCAN_VISIT";case 9=>"SCAN_EXPR"}
      s"$dim:$failedUsed:$failedScan:$failedRequest:$failedLimit:$failedExpr:$failedScanExpr:${prefix(0)}:${prefix(1)}:${prefix(2)}:${prefix(3)}:${prefix(4)}"
    }
    def bound(p:Boolean):Unit=if(!p)throw new Abort("BOUND",true)
    def name(s:String):Unit=bound(s!=null && s.nonEmpty && s.length<=4096)
    def family(s:scala.collection.Seq[_]):Unit=s match {
      case _:List[_]|_:Vector[_]|_:scala.collection.immutable.ArraySeq.ofRef[_]=>()
      case _=>fail("FAMILY")
    }
    def iter[A](s:scala.collection.Seq[A]):Iterator[A]={family(s);charge(C.Temp);s.iterator}
    def hash(s:String):Int={name(s);var h=0x811c9dc5;var i=0
      while(i<s.length){charge(C.Hash);h=(h^s.charAt(i).toInt)*0x01000193;i+=1};h}
    def equal(x:String,y:String):Boolean={charge(C.Probe)
      if(x==null||y==null)return x eq y
      if(x.length!=y.length)return false
      var i=0;while(i<x.length){charge(C.Equal);if(x.charAt(i)!=y.charAt(i))return false;i+=1};true}
    def size[A](s:scala.collection.Seq[A],cap:Int):Int={val it=iter(s);var n=0
      while(it.hasNext){bound(n<cap);charge(C.Probe);it.next();n+=1};n}
  }
  private final class Names(b:Budget,slots:Int=1<<21,capacity:Int=1<<20) {
    private val keys=new Array[String](slots);private val occupied=new Array[Int](capacity)
    private var count=0
    private def slot(s:String):Int={var p=b.hash(s)&(slots-1)
      while(true){b.charge(C.Probe);val k=keys(p);if(k==null)return ~p
        if(b.equal(k,s))return p;p=(p+1)&(slots-1)}; -1}
    def contains(s:String):Boolean=slot(s)>=0
    def add(s:String):Unit={b.charge(C.Names);val p=slot(s);need(p<0,"DUPLICATE");b.bound(count<capacity)
      keys(~p)=s;occupied(count)= ~p;count+=1}
    def clear():Unit={var i=0;while(i<count){b.charge(C.Clear);keys(occupied(i))=null;i+=1};count=0}
  }
  private final class Two[A](x:A,y:A) extends Iterator[A] {
    private var n=0;def hasNext:Boolean=n<2
    def next():A={need(hasNext,"STRUCTURE");n+=1;if(n==1)x else y}
  }
  private def supported(s:Statement):Unit={
    val c=s.getClass
    need(c==classOf[Block]||c==classOf[Conditionally]||c==classOf[DefWire]||c==classOf[DefRegister]||
      c==classOf[DefInstance]||c==classOf[DefMemory]||c==classOf[DefNode]||c==classOf[Connect]||
      c==classOf[IsInvalid]||c==classOf[Attach]||c==classOf[Print]||
      c==classOf[Stop]||c==classOf[Verification]||c==classOf[firrtl2.WDefInstanceConnector]||
      c==classOf[firrtl2.CDefMemory]||c==classOf[firrtl2.CDefMPort]||
      c==classOf[firrtl2.backends.experimental.smt.random.DefRandom]||(s eq EmptyStmt),"STRUCTURE")
  }
  private def children(s:Statement,b:Budget):Iterator[Statement]={supported(s);s match {
    case x:Block=>b.iter(x.stmts)
    case x:Conditionally=>b.charge(C.Temp);new Two(x.conseq,x.alt)
    case _=>Iterator.empty
  }}
  private final class Walk(b:Budget) {
    private val stack=new Array[Iterator[Statement]](257);private var depth = -1;private var pending:Statement=null
    var level=0
    def start(s:Statement):Unit={need(depth<0&&pending==null,"STRUCTURE");pending=s}
    def next():Statement={
      if(pending!=null){b.charge(C.Visit);val s=pending;pending=null;level=0;return s}
      while(depth>=0){val it=stack(depth)
        if(it.hasNext){b.bound(depth<256);b.charge(C.Visit);level=depth+1;return it.next()}
        stack(depth)=null;depth-=1};null
    }
    def descend(s:Statement):Unit={val it=children(s,b);if(it.hasNext){b.bound(depth<255);depth+=1;stack(depth)=it}}
    def clear():Unit={java.util.Arrays.fill(stack.asInstanceOf[Array[AnyRef]],null);pending=null;depth = -1}
  }
  private def printText(p:Print,b:Budget):String={
    need(p.string.getClass==classOf[StringLit],"STRUCTURE");val s=p.string.string;b.bound(s.length<=4096);s
  }
  private def exactReference(e:Expression):Reference={need(e!=null&&e.getClass==classOf[Reference],"CLOCK");e.asInstanceOf[Reference]}
  private def zero(e:Expression):Boolean={
    if(e==null||e.getClass!=classOf[UIntLiteral])return false
    val u=e.asInstanceOf[UIntLiteral];val w=u.width
    u.value==0 && w.getClass==classOf[IntWidth] && w.asInstanceOf[IntWidth].width==1
  }
  private def clock(r:DefRegister,b:Budget):Reference={
    need(r.getClass==classOf[DefRegister]&&(r.tpe eq ClockType)&&zero(r.reset)&&zero(r.init),"SHAPE")
    val c=exactReference(r.clock);b.name(r.name);b.name(c.name)
    need((c.tpe eq ClockType)&&(c.kind eq PortKind)&&(c.flow eq SourceFlow),"CLOCK");c
  }
  // No generic Expression.tpe: private InfoExpr can recursively delegate it.
  private def expressionType(e:Expression):Type={val c=e.getClass
    if(c==classOf[Reference])e.asInstanceOf[Reference].tpe
    else if(c==classOf[SubField])e.asInstanceOf[SubField].tpe
    else if(c==classOf[SubIndex])e.asInstanceOf[SubIndex].tpe
    else if(c==classOf[SubAccess])e.asInstanceOf[SubAccess].tpe
    else if(c==classOf[Mux])e.asInstanceOf[Mux].tpe
    else if(c==classOf[ValidIf])e.asInstanceOf[ValidIf].tpe
    else if(c==classOf[DoPrim])e.asInstanceOf[DoPrim].tpe
    else if(c==classOf[UIntLiteral])e.asInstanceOf[UIntLiteral].tpe
    else if(c==classOf[SIntLiteral])e.asInstanceOf[SIntLiteral].tpe
    else fail("EXPRESSION")
  }
  private final class Checked(b:Budget) {
    private var nodes=0;private var chars=0L;private var present=false
    var snapshot=false;var text=0L;var infoNodes=0L;var slots=0L
    def resetSnapshot():Unit={text=0;infoNodes=0;slots=0;snapshot=true}
    private def typ(t:Type,d:Int):Unit={
      val tc=t.getClass
      need(tc==classOf[VectorType]||tc==classOf[BundleType]||tc==classOf[UIntType]||tc==classOf[SIntType]||
        tc==classOf[AnalogType]||(t eq ClockType)||(t eq ResetType)||(t eq AsyncResetType)||(t eq UnknownType),"TYPE")
      b.charge(C.Temp,2);b.charge(C.Expr,1,0);b.bound(d<=64);nodes+=1;b.bound(nodes<=4096)
      t match {
        case VectorType(x,n)=>b.bound(n>=0);typ(x,d+1)
        case BundleType(fs)=>b.size(fs,4096);val it=b.iter(fs)
          while(it.hasNext){b.charge(C.Probe);val f=it.next();need(f.getClass==classOf[Field],"TYPE");b.name(f.name);need((f.flip eq Default)||(f.flip eq Flip),"TYPE");chars+=f.name.length;typ(f.tpe,d+1)}
        case x:UIntType=>width(x.width)
        case x:SIntType=>width(x.width)
        case x:AnalogType=>width(x.width)
        case ClockType|ResetType|AsyncResetType|UnknownType=>()
        case _=>fail("TYPE")
      }
    }
    private def width(w:Width):Unit=need((w eq UnknownWidth)||w.getClass==classOf[IntWidth],"TYPE")
    def mismatch(r:DefRegister):Boolean=r.tpe match {
      case x:AnalogType=>need(x.getClass==classOf[AnalogType],"TYPE");width(x.width);false
      case _=>nodes=0;chars=0;typ(r.tpe,0);val left=nodes;nodes=0;b.charge(C.Temp)
        val t=expressionType(r.init);typ(t,0);b.charge(C.Temp,2L+8L*(left+nodes));b.charge(C.Equal,chars)
        firrtl2.WrappedType.wt(r.tpe)!=firrtl2.WrappedType.wt(t)
    }
    private def info(i:Info,d:Int):Unit={
      need((i eq NoInfo)||i.getClass==classOf[FileInfo]||i.getClass==classOf[MultiInfo],"INFO")
      b.charge(C.Temp,2);b.charge(C.Expr,1,1);b.bound(d<=16);nodes+=1;b.bound(nodes<=256)
      if(snapshot){b.bound(infoNodes<65536);infoNodes+=1}
      i match {
        case NoInfo=>()
        case f:FileInfo=>b.bound(f.escaped.length<=4096);if(f.escaped.nonEmpty)present=true
          if(snapshot){b.bound(f.escaped.length<=(1L<<20)-text);text+=f.escaped.length}
        case m:MultiInfo=>val n=b.size(m.infos,64)
          if(snapshot){b.bound(n<=65536-slots);slots+=n}
          val it=b.iter(m.infos);while(it.hasNext)info(it.next(),d+1)
        case _=>fail("INFO")
      }
    }
    def infoPresent(i:Info):Boolean={nodes=0;present=false;info(i,0);present}
    private def eqInfo(x:Info,y:Info,d:Int):Boolean={b.charge(C.Expr,1,1);b.bound(d<=16)
      x match {
        case NoInfo=>y eq NoInfo
        case f:FileInfo=>y match{case g:FileInfo=>b.equal(f.escaped,g.escaped);case _=>false}
        case m:MultiInfo=>y match{case n:MultiInfo=>val xi=b.iter(m.infos);val yi=b.iter(n.infos)
          while(xi.hasNext&&yi.hasNext){if(!eqInfo(xi.next(),yi.next(),d+1))return false};!xi.hasNext && !yi.hasNext
          case _=>false}
        case _=>false
      }
    }
    def same(x:Info,y:Info):Boolean={val a=infoPresent(x);val z=infoPresent(y);a&&z&&eqInfo(x,y,0)}
  }
  // BEGIN EMPTY ASSERT CLOCK TERMINAL LINEAGE
  private def emptyAssert(s:Statement,b:Budget):Boolean={
    b.charge(C.Probe,4)
    if(s.getClass!=classOf[Verification])return false
    val v=s.asInstanceOf[Verification]
    (v.op eq Formal.Assert)&&v.msg!=null&&v.msg.getClass==classOf[StringLit]&&v.msg.string.length==0
  }
  private final class CompactFormal(val clock:Reference,val pred:Reference,val en:Reference)
  private def formalRef(e:Expression,isClock:Boolean,b:Budget):Reference={
    b.charge(C.Probe,8);b.charge(C.Expr)
    need(e!=null&&e.getClass==classOf[Reference],"SHAPE");val r=e.asInstanceOf[Reference];b.name(r.name)
    need((r.kind eq NodeKind)&&(r.flow eq SourceFlow),"SHAPE")
    if(isClock)need(r.tpe eq ClockType,"SHAPE")
    else {need(r.tpe!=null&&r.tpe.getClass==classOf[UIntType],"SHAPE")
      val w=r.tpe.asInstanceOf[UIntType].width
      need(w!=null&&w.getClass==classOf[IntWidth],"SHAPE")
      // Reject subclass backing before numeric equality can dispatch through it.
      // Numeric equality alone can also hide inconsistent backing/cache fields.
      b.charge(C.Temp,2);b.charge(C.Probe,4)
      val value=w.asInstanceOf[IntWidth].width
      need(value!=null&&value.getClass==classOf[scala.math.BigInt],"SHAPE")
      val backing=value.bigInteger
      need(backing!=null&&backing.getClass==classOf[java.math.BigInteger]&&java.math.BigInteger.ONE.equals(backing),"SHAPE")
      need(value==1,"SHAPE")}
    r
  }
  private def formalFields(s:Statement,assertStage:Boolean,b:Budget):CompactFormal={
    b.charge(C.Probe,8)
    var clk:Expression=null;var pred:Expression=null;var en:Expression=null
    if(assertStage){need(emptyAssert(s,b),"SHAPE");val v=s.asInstanceOf[Verification]
      clk=v.clk;pred=v.pred;en=v.en
    }else {
      need(s.getClass==classOf[Stop],"RELATION");val stop=s.asInstanceOf[Stop]
      need(stop.ret==65,"RELATION");clk=stop.clk
      need(stop.en.getClass==classOf[DoPrim],"RELATION");val and=stop.en.asInstanceOf[DoPrim]
      need(and.op eq firrtl2.PrimOps.And,"RELATION")
      need(b.size(and.args,2)==2&&b.size(and.consts,0)==0,"RELATION")
      val ai=b.iter(and.args);val n=ai.next();en=ai.next()
      need(n.getClass==classOf[DoPrim],"RELATION");val not=n.asInstanceOf[DoPrim]
      need(not.op eq firrtl2.PrimOps.Not,"RELATION")
      need(b.size(not.args,1)==1&&b.size(not.consts,0)==0,"RELATION")
      val ni=b.iter(not.args);pred=ni.next()
      // Read stored type only after exact Reference admission below.
      val pr=formalRef(pred,false,b)
      need((and.tpe eq pr.tpe)&&(not.tpe eq pr.tpe),"RELATION")
    }
    val c=formalRef(clk,true,b);val p=formalRef(pred,false,b);val e=formalRef(en,false,b)
    b.charge(C.Temp);new CompactFormal(c,p,e)
  }
  private def formalLeafRelation(old:Reference,fresh:Reference,index:Int,b:Budget):Unit={
    b.charge(C.Probe,5)
    if(index==52||index==53)need(old eq fresh,"RELATION")
    else {need(index==54,"RELATION")
      need((old.name eq fresh.name)&&(old.tpe eq fresh.tpe)&&(old.kind eq fresh.kind)&&(fresh.flow eq SourceFlow),"RELATION")}
  }
  private final class FormalRecords(b:Budget,owner:Records,capacity:Int=1024,nameLimit:Long=1L<<19) {
    need(capacity>=0&&capacity<=1024&&nameLimit>=0&&nameLimit<=(1L<<19),"BOUND")
    // Eight arrays,53KiB payload; fixed12MiB slice is reserved before Records.
    // All allocations also consume the unchanged shared transient quota.
    b.charge(C.Temp,256)
    // Reserve all bounded lifecycle cleanup before retaining anything. Normal
    // production calls clearSnapshot at most5 times plus2048 terminal/name clears;
    // failure paths call fewer.32768 covers these writes, so finally never charges.
    b.charge(C.Clear,32768)
    private val names=new Array[String](1024)
    private val weak=new Array[WeakReference[Statement]](1024)
    private val stage=new Array[Int](1024);private val seen=new Array[Boolean](1024)
    private val clocks=new Array[Reference](1024);private val predicates=new Array[Reference](1024);private val enables=new Array[Reference](1024)
    private val keys=Array.fill(2048)(-1)
    private var persistentChars=0L
    var count=0;var p52=0;var p53=0;var p54=0
    private def slot(mid:Int,name:String):Int={var p=(b.hash(name)^mid*0x9e3779b9)&2047
      while(true){b.charge(C.Probe);val id=keys(p)
        if(id<0||owner.moduleIds(id)==mid&&b.equal(names(id),name))return p
        p=(p+1)&2047}; -1}
    def contains(id:Int):Boolean={b.charge(C.Probe);names(id)!=null}
    private def terminal(id:Int):Statement={b.charge(C.Probe);val s=weak(id).get;need(s!=null,"RECLAIMED");s}
    private def named(s:Statement):String=s match{case v:Verification=>v.name;case x:Stop=>x.name;case _=>fail("RELATION")}
    private def info(s:Statement):Info=s match{case v:Verification=>v.info;case x:Stop=>x.info;case _=>fail("RELATION")}
    def add(id:Int,v:Verification):Unit={
      b.charge(C.Probe,4);b.charge(C.Names)
      need(names(id)==null,"DUPLICATE");b.bound(count<capacity);b.name(v.name)
      val fields=formalFields(v,true,b)
      need(v.info eq owner.get(id).info,"INFO")
      b.bound(v.name.length<=nameLimit-persistentChars)
      val p=slot(owner.moduleIds(id),v.name);need(keys(p)<0,"DUPLICATE")
      b.charge(C.Temp);val w=new WeakReference[Statement](v)
      names(id)=v.name;weak(id)=w;stage(id)=51;keys(p)=id;persistentChars+=v.name.length;count+=1
    }
    def anchor(v:Verification,mid:Int,anchors:Array[Int]):Unit={
      if(!emptyAssert(v,b))return
      val id=keys(slot(mid,v.name))
      if(id>=0){b.charge(C.Probe,6);val reg=owner.get(id)
        if(!((v.name eq names(id))&&(v.info eq reg.info)))throw anchorAbort("FORMAL_NAME_INFO",v,null,reg,names(id),anchors(id))
        if(!(v.clk eq reg.clock))throw anchorAbort("FORMAL_CLOCK",v,null,reg,names(id),anchors(id))
        if(anchors(id)!=0)throw anchorAbort("FORMAL_DUPLICATE",v,null,reg,names(id),anchors(id));anchors(id)=1
      }
    }
    def capture():Unit={var chars=persistentChars;var id=0
      while(id<owner.count){b.charge(C.Probe)
        if(names(id)!=null){
          val t=terminal(id);val f=formalFields(t,stage(id)==51,b)
          need((named(t) eq names(id))&&(info(t) eq owner.snapshot(id).info),"RELATION")
          val n=f.clock.name.length.toLong+f.pred.name.length+f.en.name.length
          b.bound(n<=nameLimit-chars);chars+=n
          clocks(id)=f.clock;predicates(id)=f.pred;enables(id)=f.en;seen(id)=false
        };id+=1
      }
    }
    def inspect(s:Statement,mid:Int,index:Int):Unit={
      b.charge(C.Probe)
      s match{case d:IsDeclaration if d.name.nonEmpty=>
        val id=keys(slot(mid,d.name))
        if(id>=0){b.charge(C.Probe,8);need(!seen(id),"DUPLICATE")
          need(s.getClass==classOf[Stop],"RELATION");val stop=s.asInstanceOf[Stop]
          need(stage(id)==index-1&&(stop.name eq names(id))&&(stop.info eq owner.snapshot(id).info),"RELATION")
          val f=formalFields(stop,false,b)
          formalLeafRelation(clocks(id),f.clock,index,b)
          formalLeafRelation(predicates(id),f.pred,index,b)
          formalLeafRelation(enables(id),f.en,index,b)
          b.charge(C.Temp);weak(id)=new WeakReference[Statement](stop);stage(id)=index;seen(id)=true
        }
        case _=>()}
    }
    def finish(index:Int):Unit={var id=0;var done=0
      while(id<owner.count){b.charge(C.Probe);if(names(id)!=null){need(seen(id)&&stage(id)==index,"COUNT");done+=1};id+=1}
      need(done==count,"COUNT")
      if(index==52)p52=done else if(index==53)p53=done else p54=done
    }
    def sameFinal(id:Int,s:Statement):Boolean={b.charge(C.Probe);stage(id)==54&&(terminal(id) eq s)}
    def clearSnapshot():Unit={var id=0;while(id<1024){clocks(id)=null;predicates(id)=null;enables(id)=null;id+=1}}
    def clear():Unit={clearSnapshot();var id=0;while(id<1024){names(id)=null;weak(id)=null;id+=1}}
    def clearWeakForTest(id:Int):Unit=weak(id).clear()
    def snapshotsEmpty:Boolean={var id=0;while(id<1024){if(clocks(id)!=null||predicates(id)!=null||enables(id)!=null)return false;id+=1};true}
  }
  // END EMPTY ASSERT CLOCK TERMINAL LINEAGE

  private final class Records(b:Budget) {
    val formals=new FormalRecords(b,this)
    val refs=new Array[WeakReference[DefRegister]](1024)
    val moduleNames=new Array[String](1024);val moduleIds=new Array[Int](1024)
    val names=new Array[String](1024);val clockNames=new Array[String](1024)
    val lost=new Array[Boolean](1024);val clockChanged=new Array[Boolean](1024)
    val keyIds=Array.fill(2048)(-1);val clockHeads=Array.fill(2048)(-1);val clockNext=new Array[Int](1024)
    val snapshot=new Array[DefRegister](1024);val seen=new Array[Boolean](1024)
    var count=0
    private def slot(mid:Int,name:String,clocks:Boolean):Int={var p=(b.hash(name)^mid*0x9e3779b9)&2047
      while(true){b.charge(C.Probe);val id=if(clocks)clockHeads(p)else keyIds(p)
        if(id<0)return p
        if(moduleIds(id)==mid && b.equal(if(clocks)clockNames(id)else names(id),name))return p
        p=(p+1)&2047}; -1}
    def find(mid:Int,name:String):Int=keyIds(slot(mid,name,false))
    def firstClock(mid:Int,name:String):Int=clockHeads(slot(mid,name,true))
    def get(id:Int):DefRegister={val r=refs(id).get;need(r!=null,"RECLAIMED");r}
    def add(mid:Int,module:String,r:DefRegister,c:Reference):Unit={b.bound(count<1024);val p=slot(mid,r.name,false)
      need(keyIds(p)<0,"DUPLICATE");val cp=slot(mid,c.name,true);val id=count
      b.charge(C.Temp);refs(id)=new WeakReference(r);names(id)=r.name;moduleNames(id)=module
      moduleIds(id)=mid;clockNames(id)=c.name;keyIds(p)=id;clockNext(id)=clockHeads(cp);clockHeads(cp)=id;count+=1}
    def capture(checked:Checked):Unit={checked.resetSnapshot();var chars=0L;var i=0
      while(i<count){b.charge(C.Probe);val r=get(i);val c=clock(r,b)
        val n=moduleNames(i).length.toLong+r.name.length+c.name.length
        b.bound(n<=(1L<<20)-chars);chars+=n;need(checked.infoPresent(r.info),"INFO")
        snapshot(i)=r;seen(i)=false;i+=1};checked.snapshot=false;formals.capture()}
    def clearSnapshot():Unit={java.util.Arrays.fill(snapshot.asInstanceOf[Array[AnyRef]],null);formals.clearSnapshot()}
    def update(i:Int,r:DefRegister):Unit={b.charge(C.Temp);refs(i)=new WeakReference(r)}
  }
  private final class Modules(b:Budget) {
    private val keys=new Array[String](8192);private val ids=new Array[Int](8192)
    private def slot(s:String):Int={var p=b.hash(s)&8191
      while(true){b.charge(C.Probe);val k=keys(p);if(k==null||b.equal(k,s))return p;p=(p+1)&8191}; -1}
    def add(s:String,id:Int):Unit={b.charge(C.Names);val p=slot(s);need(keys(p)==null,"DUPLICATE");keys(p)=s;ids(p)=id}
    def find(s:String):Int={val p=slot(s);if(keys(p)==null)-1 else ids(p)}
  }
  private def relation(index:Int,old:DefRegister,fresh:DefRegister,b:Budget):Unit={
    clock(old,b);clock(fresh,b)
    if(index==52)need(old eq fresh,"RELATION")
    else {
      need((old.name eq fresh.name)&&(old.info eq fresh.info)&&(old.tpe eq fresh.tpe)&&
        (old.reset eq fresh.reset)&&(old.init eq fresh.init),"RELATION")
      if(index==53)need(old.clock eq fresh.clock,"RELATION")
      else {need(index==54,"RELATION");val x=exactReference(old.clock);val y=exactReference(fresh.clock)
        need((x.name eq y.name)&&(x.tpe eq y.tpe)&&(x.kind eq y.kind)&&(y.flow eq SourceFlow),"RELATION")}
    }
  }
  private def delayed(e:Expression,name:String,driver:Boolean,finalStage:Boolean,b:Budget):Boolean={
    if(e.getClass!=classOf[Reference])return false
    val r=e.asInstanceOf[Reference]
    (r.tpe eq ClockType)&&(r.kind eq NodeKind)&&
      (r.flow eq (if(driver&&finalStage)SinkFlow else SourceFlow))&&b.equal(r.name,name)
  }
  // These arrays are callback-local. No terminal/expression root survives a hook.
  private final class Uses(b:Budget,records:Records,checked:Checked,finalStage:Boolean) {
    private val counts=new Array[Int](1024);private val statements=new Array[Statement](2048)
    private val roots=new Array[Expression](2048);private val direct=new Array[Boolean](2048)
    val consumers=new Array[Statement](1024);val anchors=new Array[Int](1024);val portSeen=new Array[Boolean](1024)
    private val its=new Array[Iterator[Expression]](257)
    private val first=new Array[Expression](257);private val second=new Array[Expression](257)
    private val third=new Array[Expression](257);private val pos=new Array[Int](257)
    private var collectDepth=0
    private val collect:Expression=>Unit=e=>{val d=collectDepth
      pos(d) match{case 0=>first(d)=e;case 1=>second(d)=e;case 2=>third(d)=e;case _=>fail("EXPRESSION")};pos(d)+=1}
    private def init(e:Expression,d:Int):Unit={
      first(d)=null;second(d)=null;third(d)=null;pos(d)=0;its(d)=null
      val c=e.getClass
      if(c==classOf[DoPrim])its(d)=b.iter(e.asInstanceOf[DoPrim].args)
      else {need(c==classOf[Reference]||c==classOf[SubField]||c==classOf[SubIndex]||c==classOf[SubAccess]||
        c==classOf[Mux]||c==classOf[ValidIf]||c==classOf[UIntLiteral]||c==classOf[SIntLiteral]||
        (e eq firrtl2.WVoid)||(e eq firrtl2.WInvalid)||(e eq firrtl2.EmptyExpression),"EXPRESSION")
        collectDepth=d;e.foreachExpr(collect);pos(d)=0}
    }
    private def child(d:Int):Expression={val it=its(d)
      if(it!=null){if(it.hasNext){b.charge(C.Expr,1,3);it.next()}else null}
      else{val e=pos(d)match{case 0=>first(d);case 1=>second(d);case 2=>third(d);case _=>null}
        if(e!=null){b.charge(C.Expr,1,3);pos(d)+=1};e}}
    private var statement:Statement=null;private var mid=0
    private val root:Expression=>Unit=r=>{
      var e=r;var depth=0;var active=true
      while(active){b.charge(C.Expr,1,2);b.bound(depth<=256)
        if(e.getClass==classOf[Reference]){val ref=e.asInstanceOf[Reference];b.name(ref.name)
          val id=records.find(mid,ref.name)
          if(id>=0){need(counts(id)<2,"REFERENCES");val k=id*2+counts(id)
            statements(k)=statement;roots(k)=r;direct(k)=depth==0;counts(id)+=1}}
        init(e,depth);var next=child(depth)
        while(next==null&&depth>0){its(depth)=null;first(depth)=null;second(depth)=null;third(depth)=null
          depth-=1;next=child(depth)}
        if(next==null)active=false else{b.bound(depth<256);depth+=1;e=next}
      };its(0)=null;first(0)=null;second(0)=null;third(0)=null
    }
    def scan(s:Statement,moduleId:Int):Unit={supported(s);statement=s;mid=moduleId
      s match{case p:Print=>b.family(p.args);case p:Attach=>b.family(p.exprs)
        case p:firrtl2.WDefInstanceConnector=>b.family(p.portCons)
        case p:firrtl2.CDefMPort=>b.family(p.exps);case _=>()}
      b.charge(C.Temp,2);s.foreachExpr(root);statement=null
    }
    def port(mid:Int,p:Port):Unit={var id=records.firstClock(mid,p.name)
      while(id>=0){b.charge(C.Probe);need(p.direction==Input&&(p.tpe eq ClockType),"CLOCK")
        need(!portSeen(id),"DUPLICATE");portSeen(id)=true;id=records.clockNext(id)}}
    private def consumerFailure(site:String,id:Int):Nothing={
      if(finalStage)fail("CONSUMER")
      val k=id*2
      throw consumerAbort(site,statements(k),roots(k),direct(k),statements(k+1),roots(k+1),direct(k+1))
    }
    def finish():Unit={var i=0
      while(i<records.count){need(portSeen(i),"CLOCK");need(counts(i)==2,"REFERENCES")
        var driver:Connect=null;var consumer:Statement=null;var j=0
        while(j<2){val k=i*2+j
          if(direct(k))statements(k)match{
            case x:Connect if (roots(k) eq x.loc)&&delayed(x.loc,records.names(i),true,finalStage,b)=>
              need(driver==null,"DRIVER");driver=x
            case x:Print if (roots(k) eq x.clk)&&delayed(x.clk,records.names(i),false,finalStage,b)=>
              if(consumer!=null)consumerFailure("DUPLICATE",i);consumer=x
            case x:Stop if (roots(k) eq x.clk)&&delayed(x.clk,records.names(i),false,finalStage,b)=>
              if(consumer!=null)consumerFailure("DUPLICATE",i);consumer=x
            case x:Verification if !finalStage && emptyAssert(x,b) && (roots(k) eq x.clk)&&delayed(x.clk,records.names(i),false,false,b)=>
              if(consumer!=null)consumerFailure("DUPLICATE",i);consumer=x
            case _=>()
          };j+=1
        }
        need(driver!=null,"DRIVER");if(consumer==null)consumerFailure("MISSING",i)
        val reg=records.get(i);val c=clock(reg,b);val rhs=exactReference(driver.expr)
        need(b.equal(rhs.name,c.name)&&(rhs.tpe eq c.tpe)&&(rhs.kind eq c.kind)&&(rhs.flow eq c.flow),"DRIVER")
        need(checked.same(reg.info,driver.info),"INFO")
        consumer match{case p:Print=>printText(p,b);need(checked.same(reg.info,p.info),"INFO")
          case p:Stop=>need(checked.same(reg.info,p.info),"INFO")
          case v:Verification if !finalStage=>need(v.info eq reg.info,"INFO");records.formals.add(i,v)
          case _=>consumerFailure("FINAL_KIND",i)}
        if(finalStage&&records.formals.contains(i))need(records.formals.sameFinal(i,consumer),"RELATION")
        consumers(i)=consumer;i+=1
      }
    }
    def anchor(s:Statement,moduleId:Int):Unit={
      if(s.getClass==classOf[Verification])records.formals.anchor(s.asInstanceOf[Verification],moduleId,anchors)
      var c:Reference=null;var info:Info=null;var format:String=null;var ret=0;var print=false
      s match {
        case p:Print=>printText(p,b)
          val present=checked.infoPresent(p.info)
          if(p.clk.getClass==classOf[Reference]){val x=p.clk.asInstanceOf[Reference]
            if((x.tpe eq ClockType)&&(x.kind eq PortKind)&&(x.flow eq SourceFlow)&&present){
              c=x;info=p.info;format=printText(p,b);print=true}}
        case p:Stop=>val present=checked.infoPresent(p.info)
          if(p.clk.getClass==classOf[Reference]){val x=p.clk.asInstanceOf[Reference]
            if((x.tpe eq ClockType)&&(x.kind eq PortKind)&&(x.flow eq SourceFlow)&&present){c=x;info=p.info;ret=p.ret}}
        case _=>()
      }
      if(c!=null){var id=records.firstClock(moduleId,c.name)
        while(id>=0){b.charge(C.Probe);val consumer=consumers(id);var same=false
          consumer match{
            case p:Print if print=>same=b.equal(format,printText(p,b))&&checked.same(info,p.info)
            case p:Stop if !print&&p.ret==ret=>same=checked.same(info,p.info)
            case _=>()
          }
          if(same){if(anchors(id)!=0)throw anchorAbort("ORDINARY_DUPLICATE",s,consumer,null,null,anchors(id));anchors(id)=1};id=records.clockNext(id)
        }
      }
    }
  }
  private final class Observation(expected:Int) {
    // Bootstrap constant check precedes all observer pools. Logical live reserve,
    // not a claim about JVM RSS or forced reclamation. Full fixed inventory:
    // Budget1; Names2; two Modules4; Records12; Walk1; Uses12; originalSeen1
    // =33 arrays at initial-hook peak. Metadata payload<512KiB, headers/closures
    // and <=550 active standard iterators fit the separate2MiB fixed allowance.
    //20MiB names +2MiB pools +4MiB text +64MiB Info +.5MiB childpayload
    // +8MiB official comparison scratch +2MiB weak/temporary admission =100.5MiB.
    need(105381888L+12L*1024*1024<=128L*1024*1024,"BOUND")
    private val b=new Budget
    private var step="CENSUS";private var status="UNAVAILABLE";private var reason="NOT_RUN"
    private var active=true;private var complete=false;private var records:Records=null
    private var walk:Walk=null;private var checked:Checked=null
    private var created=0;private var p52=0;private var p53=0;private var p54=0
    private var count=0;private var lost=0;private var changed=0
    private var pendingSizing=false
    private var budgetResult="NONE";private var sizingResult="NONE"
    def budgetEvidence:String=budgetResult
    def sizingEvidence:String=sizingResult
    private var consumerResult="NONE"
    def consumerEvidence:String=consumerResult
    private var anchorResult="NONE"
    def anchorEvidence:String=anchorResult
    private var formalResult="UNAVAILABLE:0:0:0:0"
    def formalEvidence:String=if(complete)formalResult else "UNAVAILABLE:0:0:0:0"
    // Only invoked from this object's bounded sizingSelfChecks; not a public hook.
    def sizingFixtureFailure(where:String,mode:Int):Unit={
      step=where
      if(mode==0){b.scanExpr=C.ScanExpr;b.used(C.Expr)=C.ScanExpr;b.prefix(2)=C.ScanExpr;guard{b.charge(C.Expr,1,3)}}
      else if(mode==1)guard{b.bound(false)}
      else{if(mode==3)b.failedDimension=99;b.used(C.Expr)=1L<<25;b.prefix(4)=1L<<25;guard{b.charge(C.Expr)}}
    }
    def consumerFixtureFailure(where:String,error:Abort):Unit={step=where;guard{throw error}}
    def sizingPendingForTest:Boolean=pendingSizing
    def sizePending(state:CircuitState):Unit=if(pendingSizing){
      pendingSizing=false
      // Independent counters; no old-input handle or exhausted-budget reuse.
      try{sizingResult=runSizing(state.circuit)}catch{case _:Throwable=>sizingResult="ERROR:UNEXPECTED:0:0:0:0:0:0:0:0:0:0:0"}
    }
    private def guard(body: =>Unit):Unit=if(active){try body catch{
      case e:Abort=>
        val eligible=step=="INITIAL_USES" && (e.reason=="BUDGET" || e.reason=="SCAN_BUDGET") && b.failedDimension>=0
        // Preserve the primary failure and release AST-owning pools before any
        // failure-only string formatting. A catch-body failure needs its own catch.
        status=if(e.bounded)"TRUNCATED"else"UNAVAILABLE";reason=e.reason;active=false;release()
        if(step=="INITIAL_USES" && e.reason=="CONSUMER")consumerResult=consumerCode(e)
        if(step=="ORIGINAL" && e.reason=="ANCHOR")anchorResult=anchorCode(e)
        if(eligible)try{
          val record=b.failureEvidence
          if(record!="NONE" && record.length<=512){budgetResult=record;pendingSizing=true}
          else {budgetResult="UNAVAILABLE";sizingResult="ERROR:UNEXPECTED:0:0:0:0:0:0:0:0:0:0:0";pendingSizing=false}
        }catch{case _:Throwable=>budgetResult="UNAVAILABLE";sizingResult="ERROR:UNEXPECTED:0:0:0:0:0:0:0:0:0:0:0";pendingSizing=false}
      case _:Throwable=>status="UNAVAILABLE";reason="UNEXPECTED";active=false;release()
    }}
    // Shared module/port/statement traversal. f never escapes this callback.
    private def scan(c:Circuit,port:(Int,DefModule,Port)=>Unit,node:(Int,DefModule,Statement)=>Unit,
      begin:(Int,DefModule)=>Unit,end:(Int,DefModule)=>Unit):Unit={
      b.start();b.charge(C.Temp,8);val ms=b.iter(c.modules);var mid=0
      while(ms.hasNext){b.bound(mid<4096);b.charge(C.Visit);val m=ms.next();b.name(m.name)
        need(m.getClass==classOf[Module]||m.getClass==classOf[ExtModule],"STRUCTURE");begin(mid,m)
        val ps=b.iter(m.ports);var ports=0
        while(ps.hasNext){b.charge(C.Visit);b.bound(ports<250000);val p=ps.next();need(p.getClass==classOf[Port],"STRUCTURE");b.name(p.name);port(mid,m,p);ports+=1}
        m match{case mm:Module=>walk.start(mm.body);var s=walk.next()
          while(s!=null){supported(s);node(mid,m,s);walk.descend(s);s=walk.next()}
          case _=>()}
        end(mid,m);mid+=1
      }
    }
    private val noPort:(Int,DefModule,Port)=>Unit=(_,_,_)=>()
    private val noModule:(Int,DefModule)=>Unit=(_,_)=>()
    private def census(c:Circuit):Unit={
      var containers=0L;var childrenCount=0L;var terminals=0L;var arguments=0L
      scan(c,noPort,(_,_,s)=>s match{
        case x:Block=>b.bound(containers<(1L<<18));containers+=1
          val n=b.size(x.stmts,((1L<<22)-childrenCount).toInt);childrenCount+=n
        case _:Conditionally=>b.bound(containers<(1L<<18));b.bound(2<=(1L<<22)-childrenCount)
          containers+=1;childrenCount+=2
        case p:Print=>b.bound(terminals<4096);terminals+=1
          arguments+=b.size(p.args,(65536-arguments).toInt)
        case _:Stop|_:Verification=>b.bound(terminals<4096);terminals+=1
        case _=>()
      },noModule,noModule)
      // Fixed conservative admission: 392.25MiB max enumerated old objects,
      // plus23.75MiB fixed-root/header margin, independently capped at416MiB.
      b.bound(containers*512+childrenCount*64+terminals*512+arguments*64+4096L*576+1048576L<=416L*1024*1024)
    }
    private def declaration(s:Statement,names:Names):Unit=s match{
      case p:Print if p.name.isEmpty=>()
      case p:Stop if p.name.isEmpty=>()
      case p:Verification if p.name.isEmpty=>()
      case d:IsDeclaration=>b.name(d.name);names.add(d.name)
      case _=>()
    }
    private def initial(before:Circuit,after:Circuit):Unit={
      step="DISCOVERY"
      b.name(before.main);b.name(after.main);need(b.equal(before.main,after.main),"STRUCTURE")
      // Callback-local20MiB namespace and small module table are released here.
      b.charge(C.Temp,256);val names=new Names(b);val modules=new Modules(b)
      checked.resetSnapshot();var nameChars=0L
      scan(after,(_,_,p)=>names.add(p.name),(mid,m,s)=>{
        declaration(s,names)
        s match{case r:DefRegister if checked.mismatch(r)=>
          val c=clock(r,b);need(checked.infoPresent(r.info),"INFO")
          val n=m.name.length.toLong+r.name.length+c.name.length
          b.bound(n<=(1L<<20)-nameChars);nameChars+=n
          need(records.count<expected,"COUNT");records.add(mid,m.name,r,c)
          case _=>()}
      },(mid,m)=>modules.add(m.name,mid),(_,_)=>names.clear())
      checked.snapshot=false;need(records.count==expected,"COUNT")
      b.charge(C.Temp,256);val uses=new Uses(b,records,checked,false)
      step="INITIAL_USES"
      scan(after,(mid,_,p)=>uses.port(mid,p),(mid,_,s)=>uses.scan(s,mid),noModule,noModule);uses.finish()
      step="ORIGINAL"
      b.charge(C.Temp,64);val oldModules=new Modules(b);val originalSeen=new Array[Boolean](1024)
      java.util.Arrays.fill(uses.portSeen,false)
      scan(before,(_,m,p)=>{names.add(p.name);val id=modules.find(m.name);if(id>=0)uses.port(id,p)},(_,m,s)=>{
        declaration(s,names);val mid=modules.find(m.name);if(mid>=0)uses.anchor(s,mid)
      },(mid,m)=>oldModules.add(m.name,mid),(_,m)=>{
        val mid=modules.find(m.name);var i=0
        while(i<records.count){b.charge(C.Probe)
          if(records.moduleIds(i)==mid){need(!names.contains(records.names(i)),"PREEXISTING");originalSeen(i)=true};i+=1}
        names.clear()
      })
      var i=0;while(i<records.count){need(originalSeen(i),"ORIGINAL_MODULE");need(uses.portSeen(i),"CLOCK")
        if(uses.anchors(i)!=1)throw anchorAbort("FINAL_MISSING",uses.consumers(i),null,null,null,uses.anchors(i));i+=1}
      created=records.count
    }
    private def suffix(index:Int,c:Circuit):Unit={
      val finalStage=index==54
      b.charge(C.Temp,256);val uses=if(finalStage)new Uses(b,records,checked,true)else null
      scan(c,(mid,_,p)=>if(finalStage)uses.port(mid,p),(mid,m,s)=>{
        s match{case r:DefRegister=>
          val id=records.find(mid,r.name)
          if(id>=0){need(!records.seen(id),"DUPLICATE");need(m.name eq records.moduleNames(id),"RELATION")
            val old=records.snapshot(id);need(old!=null,"RECLAIMED");relation(index,old,r,b)
            if(index==53||index==54)need(!(old eq r),"RELATION")
            if(index==54)need(!(old.clock eq r.clock),"RELATION")
            if(!(old eq r))records.lost(id)=true
            if(!(old.clock eq r.clock))records.clockChanged(id)=true
            records.seen(id)=true;records.update(id,r)
          }
          if(finalStage){val mismatch=checked.mismatch(r)
            if(mismatch){need(id>=0,"COUNT");clock(r,b);need(checked.infoPresent(r.info),"INFO")}
            else need(id<0,"SHAPE")}
          case _=>()}
        records.formals.inspect(s,mid,index)
        if(finalStage)uses.scan(s,mid)
      },noModule,noModule)
      var i=0;while(i<records.count){need(records.seen(i),"COUNT");i+=1}
      records.formals.finish(index)
      if(finalStage)uses.finish()
      if(index==52)p52=records.count else if(index==53)p53=records.count else p54=records.count
    }
    def retainsInput:Boolean=active && records!=null && step=="CENSUS"
    def before(index:Int,state:CircuitState):Unit=guard{
      if(index==51){need(expected>0&&expected<=1024,"COUNT");step="CENSUS"
        // Pre-reserved fixed arrays/objects and active iterator frames<2MiB.
        b.charge(C.Temp,256);walk=new Walk(b);checked=new Checked(b);records=new Records(b)
        census(state.circuit)
      } else if(index>=52&&index<=54){step=if(index==52)"P52"else if(index==53)"P53"else"P54"
        records.capture(checked)}
    }
    def afterAugment(before:CircuitState,after:CircuitState):Unit=guard{initial(before.circuit,after.circuit)}
    def afterSuffix(index:Int,after:CircuitState):Unit={
      try guard{
        if(index>=52&&index<=54){suffix(index,after.circuit)
          if(index==54){count=records.count;var i=0
            while(i<count){if(records.lost(i))lost+=1;if(records.clockChanged(i))changed+=1;i+=1}
            need(lost==expected&&changed==expected,"RELATION")
            val f=records.formals
            need(f.count<=count&&f.p52==f.count&&f.p53==f.count&&f.p54==f.count,"COUNT")
            formalResult=s"COMPLETE:${f.count}:${f.p52}:${f.p53}:${f.p54}"
            complete=true;status="COMPLETE";step="DONE";reason="NONE"
          }
        }
      } finally {
        if(records!=null)records.clearSnapshot()
        if(index==54)release()
      }
    }
    def evidence:String={
      val semantic=if(complete)s"$count:$created:$p52:$p53:$p54:$lost:$changed"else"0:0:0:0:0:0:0"
      // Seven semantic counters plus status/step/reason and two work counters.
      s"$status:$step:$reason:$semantic:${b.used(C.Visit)}:${b.used(C.Expr)}"
    }
    def cleaned:Boolean=records==null&&walk==null&&checked==null
    def release():Unit={if(records!=null){records.clearSnapshot();records.formals.clear()};records=null
      if(walk!=null)walk.clear();walk=null;checked=null}
  }
  // BEGIN INDEPENDENT INITIAL USES SIZING
  private final class SizingAbort(val reason:String,val error:Boolean=false) extends RuntimeException(null,null,false,false)
  private final class Sizer(visitLimit:Long=1L<<22,nodeLimit:Long=1L<<24,edgeLimit:Long=1L<<24,
    workLimit:Long=1L<<26,transientLimit:Long=1L<<24,depthLimit:Int=256) {
    // Private small limits are used only by same-code selfchecks. Production uses
    // every default unchanged. Fixed arrays/headers+256KiB frames+1MiB scratch<2MiB.
    if(!(visitLimit>=0&&visitLimit<=(1L<<22)&&nodeLimit>=0&&nodeLimit<=(1L<<24)&&
      edgeLimit>=0&&edgeLimit<=(1L<<24)&&workLimit>=0&&workLimit<=(1L<<26)&&
      transientLimit>=0&&transientLimit<=(1L<<24)&&depthLimit>=0&&depthLimit<=256))
      throw new SizingAbort("UNEXPECTED",true)
    var modules=0L;var ports=0L;var statements=0L;var roots=0L;var nodes=0L;var edges=0L
    var work=0L;var transient=0L;var maxStatementDepth=0;var maxExpressionDepth=0
    private var status="COMPLETE";private var reason="NONE"
    private def stop(code:String):Nothing=throw new SizingAbort(code)
    private def error(code:String):Nothing=throw new SizingAbort(code,true)
    private def tick(n:Long=1):Unit={if(n>workLimit-work)stop("WORK");work+=n}
    private def allocate(n:Long,objects:Long=1):Unit={
      if(n>transientLimit-transient)stop("TRANSIENT")
      tick(objects);transient+=n
    }
    // Six arrays: five reference[257] + one Int[257]=11,308 payload bytes.
    //48 payload units +eight header/object units. Constructor/closures are included.
    allocate(56,8)
    private val statementIts=new Array[Iterator[Statement]](257)
    private val expressionIts=new Array[Iterator[Expression]](257)
    private val first=new Array[Expression](257);private val second=new Array[Expression](257)
    private val third=new Array[Expression](257);private val pos=new Array[Int](257)
    private def family(s:scala.collection.Seq[_]):Unit=s match{
      case _:List[_]|_:Vector[_]|_:scala.collection.immutable.ArraySeq.ofRef[_]=>()
      case _=>error("FAMILY")
    }
    private def iter[A](s:scala.collection.Seq[A]):Iterator[A]={family(s);allocate(1);s.iterator}
    private def visit(kind:Int):Unit={
      if(modules+ports+statements>=visitLimit)stop("VISITS")
      tick();if(kind==0)modules+=1 else if(kind==1)ports+=1 else statements+=1
    }
    private def node(depth:Int):Unit={
      if(depth>depthLimit)stop("DEPTH")
      if(nodes>=nodeLimit)stop("NODES")
      tick();nodes+=1;if(depth>maxExpressionDepth)maxExpressionDepth=depth
    }
    private def edge():Unit={if(edges>=edgeLimit)stop("EDGES");tick();edges+=1}
    private var collecting=0
    allocate(1)
    private val collect:Expression=>Unit=e=>{
      val d=collecting
      pos(d)match{case 0=>first(d)=e;case 1=>second(d)=e;case 2=>third(d)=e;case _=>error("EXPRESSION")}
      pos(d)+=1
    }
    private def init(e:Expression,d:Int):Unit={
      expressionIts(d)=null;first(d)=null;second(d)=null;third(d)=null;pos(d)=0
      val c=e.getClass
      if(c==classOf[DoPrim])expressionIts(d)=iter(e.asInstanceOf[DoPrim].args)
      else if(c==classOf[Reference]||c==classOf[UIntLiteral]||c==classOf[SIntLiteral]||
        (e eq firrtl2.WVoid)||(e eq firrtl2.WInvalid)||(e eq firrtl2.EmptyExpression)){
        // Pinned exact leaf foreachExpr methods are literal no-ops. No callback
        // or iterator is allocated; the node charge and cleared child slots stay.
        ()
      }else {
        if(!(c==classOf[SubField]||c==classOf[SubIndex]||c==classOf[SubAccess]||
          c==classOf[Mux]||c==classOf[ValidIf]))error("EXPRESSION")
        allocate(2);collecting=d;e.foreachExpr(collect);pos(d)=0
      }
    }
    private def child(d:Int):Expression={val it=expressionIts(d)
      if(it!=null){if(it.hasNext){edge();it.next()}else null}
      else {val e=pos(d)match{case 0=>first(d);case 1=>second(d);case 2=>third(d);case _=>null}
        if(e!=null){edge();pos(d)+=1};e}
    }
    allocate(1)
    private val root:Expression=>Unit=r=>{
      // A root dispatch can succeed before its node charge fails. Prefix roots
      // therefore need not be<=nodes; its independent bound still holds.
      if(roots>=nodeLimit)stop("NODES");tick();roots+=1
      var e=r;var depth=0;var active=true
      while(active){node(depth);init(e,depth);var next=child(depth)
        while(next==null&&depth>0){expressionIts(depth)=null;first(depth)=null;second(depth)=null;third(depth)=null
          depth-=1;next=child(depth)}
        if(next==null)active=false else{if(depth>=depthLimit)stop("DEPTH");depth+=1;e=next}
      }
      expressionIts(0)=null;first(0)=null;second(0)=null;third(0)=null
    }
    private def children(s:Statement):Iterator[Statement]=s match{
      case x:Block=>iter(x.stmts)
      case x:Conditionally=>allocate(1);new Two(x.conseq,x.alt)
      case _=>Iterator.empty
    }
    private def statement(s:Statement,depth:Int):Unit={
      if(depth>depthLimit)stop("DEPTH")
      visit(2);if(depth>maxStatementDepth)maxStatementDepth=depth
      try supported(s)catch{case _:Abort=>error("STRUCTURE")}
      s match{case p:Print=>family(p.args);case p:Attach=>family(p.exprs)
        case p:firrtl2.WDefInstanceConnector=>family(p.portCons)
        case p:firrtl2.CDefMPort=>family(p.exps);case _=>()}
      allocate(2);s.foreachExpr(root)
    }
    private def walk(s:Statement):Unit={
      var depth=0;var current=s;var active=true
      while(active){statement(current,depth);val it=children(current)
        if(it.hasNext){if(depth>=depthLimit)stop("DEPTH");statementIts(depth)=it;depth+=1;tick();current=it.next()}
        else {var found=false
          while(depth>0 && !found){val parent=statementIts(depth-1)
            if(parent.hasNext){tick();current=parent.next();found=true}
            else{statementIts(depth-1)=null;depth-=1}}
          if(!found)active=false
        }
      }
    }
    def cleaned:Boolean={var i=0;while(i<257){
      if(statementIts(i)!=null||expressionIts(i)!=null||first(i)!=null||second(i)!=null||third(i)!=null)return false
      i+=1};true}
    private def clear():Unit={var i=0;while(i<257){statementIts(i)=null;expressionIts(i)=null
      first(i)=null;second(i)=null;third(i)=null;pos(i)=0;i+=1}}
    def run(c:Circuit):String={
      try {
        val ms=iter(c.modules)
        while(ms.hasNext){if(modules>=4096)stop("VISITS");visit(0);val m=ms.next()
          if(m.getClass!=classOf[Module]&&m.getClass!=classOf[ExtModule])error("STRUCTURE")
          val ps=iter(m.ports);var pc=0
          while(ps.hasNext){if(pc>=250000)stop("VISITS");visit(1);val p=ps.next()
            if(p.getClass!=classOf[Port])error("STRUCTURE");pc+=1}
          m match{case mm:Module=>walk(mm.body);case _=>()}
        }
        if(edges!=nodes-roots)error("UNEXPECTED")
      }catch{
        case e:SizingAbort=>status=if(e.error)"ERROR"else"TRUNCATED";reason=e.reason
        case _:Throwable=>status="ERROR";reason="UNEXPECTED"
      }finally clear()
      s"$status:$reason:$modules:$ports:$statements:$roots:$nodes:$edges:$maxStatementDepth:$maxExpressionDepth:$work:$transient:${nodes+edges}"
    }
  }
  private def runSizing(c:Circuit):String={
    // Bootstrap reserve is static and checked before any Sizer object or arrays.
    if(11308L+8L*256+1024L*256+1048576L>2L*1024*1024)
      return "ERROR:UNEXPECTED:0:0:0:0:0:0:0:0:0:0:0"
    var s:Sizer=null
    try{s=new Sizer;s.run(c)}catch{
      case e:SizingAbort=>val status=if(e.error)"ERROR"else"TRUNCATED"
        s"$status:${e.reason}:0:0:0:0:0:0:0:0:0:0:0"
      case _:Throwable=>"ERROR:UNEXPECTED:0:0:0:0:0:0:0:0:0:0:0"
    }
  }
  // END INDEPENDENT INITIAL USES SIZING

  /** Bounded production-helper tests; no transformations or external output. */
  def selfChecks():Int={
    var checks=0
    def check(p:Boolean):Unit={require(p,"OBSERVER_SELFCHECK");checks+=1}
    def rejected(code:String)(body: =>Unit):Boolean=try{body;false}catch{case e:Abort=>e.reason==code}
    var i=0
    while(i<8){val b=new Budget;b.used(i)=C.limits(i)-1
      // Per-scan counters are independent and initialized to zero.
      b.charge(i);val n=b.used(i)
      check(n==C.limits(i)&&rejected("BUDGET"){b.charge(i)}&&b.used(i)==n);i+=1}
    locally {val b=new Budget;b.scanVisit=(1L<<22)-1;b.charge(C.Visit)
      check(rejected("SCAN_BUDGET"){b.charge(C.Visit)}&&b.used(C.Visit)==1)}
    locally {val b=new Budget;b.scanExpr=(C.ScanExpr)-1;b.charge(C.Expr)
      check(rejected("SCAN_BUDGET"){b.charge(C.Expr)}&&b.used(C.Expr)==1)}
    locally {val b=new Budget;val n=new Names(b,8,4);n.add("a");n.add("b");n.add("c");n.add("d")
      check(n.contains("d")&&rejected("BOUND"){n.add("e")})
      check(rejected("DUPLICATE"){n.add("a")});n.clear();n.add("e");check(n.contains("e") && !n.contains("a"))}
    locally {val b=new Budget;b.family(List(1));b.family(Vector(1));b.family(scala.collection.immutable.ArraySeq("one"))
      check(rejected("FAMILY"){b.family(scala.collection.immutable.LazyList(1))})}
    def nested(n:Int):Statement={var s:Statement=EmptyStmt;var j=0;while(j<n){s=Block(s::Nil);j+=1};s}
    def walkAll(s:Statement):Int={val b=new Budget;val w=new Walk(b);w.start(s);var n=0;var x=w.next()
      while(x!=null){n+=1;w.descend(x);x=w.next()};n}
    check(walkAll(nested(256))==257)
    check(rejected("BOUND"){walkAll(nested(257))})
    val info=FileInfo("observer:1");val c=Reference("clock",ClockType,PortKind,SourceFlow)
    val r=DefRegister(info,"sample",ClockType,c,UIntLiteral(0),UIntLiteral(0))
    locally {val b=new Budget;val ck=new Checked(b)
      check(ck.same(info,FileInfo("observer:1")) && !ck.same(info,FileInfo("observer:2")))
      def infos(n:Int):Info={var x:Info=info;var j=0;while(j<n){x=new MultiInfo(x::Nil);j+=1};x}
      check(ck.infoPresent(infos(16)))
      check(rejected("BOUND"){ck.infoPresent(infos(17))})
      check(ck.mismatch(r) && !ck.mismatch(r.copy(tpe=UIntType(IntWidth(1)))))
    }
    locally {val b=new Budget;relation(52,r,r,b);check(rejected("RELATION"){relation(52,r,r.copy(),b)})
      val copy=r.copy();relation(53,r,copy,b);check(!(copy eq r))
      val copiedClock=c.copy();val flowCopy=copy.copy(clock=copiedClock);relation(54,copy,flowCopy,b)
      check(!(flowCopy.clock eq copy.clock))
      check(rejected("RELATION"){relation(53,r,r.copy(name=new String(r.name)),b)})
      check(rejected("RELATION"){relation(53,r,r.copy(info=FileInfo("observer:1")),b)})
      check(rejected("SHAPE"){relation(53,r,r.copy(tpe=UIntType(IntWidth(1))),b)})
      check(rejected("RELATION"){relation(53,r,r.copy(reset=UIntLiteral(0)),b)})
      check(rejected("RELATION"){relation(53,r,r.copy(init=UIntLiteral(0)),b)})
      check(rejected("RELATION"){relation(53,r,r.copy(clock=c.copy()),b)})
      check(rejected("RELATION"){relation(54,r,r.copy(clock=c.copy(name=new String(c.name))),b)})
      check(rejected("CLOCK"){relation(54,r,r.copy(clock=c.copy(flow=SinkFlow)),b)})
      check(rejected("CLOCK"){relation(54,r,r.copy(clock=c.copy(kind=NodeKind)),b)})
    }
    locally {val b=new Budget;val records=new Records(b);records.add(0,"Top",r,c)
      records.capture(new Checked(b));check(records.snapshot(0) eq r)
      records.clearSnapshot();check(records.snapshot(0)==null)
      records.refs(0)=new WeakReference[DefRegister](null)
      check(rejected("RECLAIMED"){records.capture(new Checked(b))})}
    // Same production hooks, exact unchanged-state identity, complete synthetic
    // creation and each narrow copy relation. Official-pass parity lives in the
    // separate bounded fixture; this test does not pretend to execute passes.
    val port=Port(NoInfo,c.name,Input,ClockType)
    val originalPrint=Print(info,StringLit("test"),Nil,c,UIntLiteral(1),"print")
    def state(s:Statement):CircuitState=CircuitState(Circuit(NoInfo,Module(NoInfo,"Top",port::Nil,s)::Nil,"Top"),Seq.empty)
    val original=state(originalPrint)
    def prepared(reg:DefRegister,finalStage:Boolean):CircuitState={
      val loc=Reference(reg.name,ClockType,NodeKind,if(finalStage)SinkFlow else SourceFlow)
      val consumer=Reference(reg.name,ClockType,NodeKind,SourceFlow)
      state(Block(List(reg,Connect(info,loc,c),originalPrint.copy(clk=consumer))))
    }
    val first=prepared(r,false);val second=prepared(r.copy(),false)
    val thirdReg=second.circuit.modules.head.asInstanceOf[Module].body.asInstanceOf[Block].stmts.head.asInstanceOf[DefRegister]
    val third=prepared(thirdReg.copy(clock=c.copy()),true)
    locally {val o=new Observation(1);val originalCircuit=original.circuit;val originalAnnotations=original.annotations
      o.before(51,original);o.afterAugment(original,first);o.before(52,first);o.afterSuffix(52,first)
      o.before(53,first);o.afterSuffix(53,second);o.before(54,second);o.afterSuffix(54,third)
      check(o.evidence.startsWith("COMPLETE:DONE:NONE:1:1:1:1:1:1:1:"))
      check((original.circuit eq originalCircuit)&&(original.annotations eq originalAnnotations))
      check(o.cleaned)
    }
    locally {val o=new Observation(1);o.before(51,original);o.afterAugment(original,first)
      o.before(52,first);o.afterSuffix(52,second)
      check(o.evidence.startsWith("UNAVAILABLE:P52:RELATION:0:0:0:0:0:0:0:"))
      check(o.cleaned)
    }
    def initialFailure(before:CircuitState,after:CircuitState,code:String):Boolean={
      val o=new Observation(1);val c0=before.circuit;val a0=before.annotations
      o.before(51,before);if(o.retainsInput)o.afterAugment(before,after)
      val result=o.evidence
      o.release()
      result.contains(":"+code+":0:0:0:0:0:0:0:") && o.cleaned &&
        (before.circuit eq c0)&&(before.annotations eq a0)
    }
    val body=first.circuit.modules.head.asInstanceOf[Module].body.asInstanceOf[Block]
    val driver=body.stmts(1).asInstanceOf[Connect]
    val terminal=body.stmts(2).asInstanceOf[Print]
    check(initialFailure(state(Block(List(DefNode(info,r.name,UIntLiteral(0)),originalPrint))),first,"PREEXISTING"))
    val module=first.circuit.modules.head
    check(initialFailure(original,first.copy(circuit=first.circuit.copy(modules=List(module,module))),"DUPLICATE"))
    check(initialFailure(original,state(Block(body.stmts :+ DefWire(info,r.name,ClockType))),"DUPLICATE"))
    check(initialFailure(original,state(Block(body.stmts :+ driver)),"REFERENCES"))
    check(initialFailure(original,state(Block(body.stmts :+ terminal.copy(name="print2"))),"REFERENCES"))
    check(initialFailure(original,state(Block(List(r,driver.copy(loc=Reference(r.name,ClockType,NodeKind,SinkFlow)),terminal))),"DRIVER"))
    check(initialFailure(original,state(Block(body.stmts :+ DefNode(info,"extra",Reference(r.name,ClockType,NodeKind,SourceFlow)))),"REFERENCES"))
    check(initialFailure(state(originalPrint.copy(string=StringLit("different"))),first,"ANCHOR"))
    check(initialFailure(state(Block(List(originalPrint,originalPrint.copy(name="another")))),first,"ANCHOR"))
    check(initialFailure(original,state(Block(List(r,driver,terminal.copy(clk=Reference(r.name,ClockType,NodeKind,SinkFlow))))),"CONSUMER"))
    check(initialFailure(original,state(Block(List(r.copy(init=UIntLiteral(0,IntWidth(2))),driver,terminal))),"SHAPE"))
    // An inadmissible old-root family must fail census and never grant retention.
    locally {val o=new Observation(1);val bad=state(Block(scala.collection.immutable.LazyList(originalPrint)))
      o.before(51,bad);check(!o.retainsInput && o.cleaned && o.evidence.startsWith("UNAVAILABLE:CENSUS:FAMILY:"))}
    locally {val b=new Budget;val checked=new Checked(b)
      check(checked.infoPresent(FileInfo("x"*4096)))
      check(rejected("BOUND"){checked.infoPresent(FileInfo("x"*4097))})
      check(checked.infoPresent(new MultiInfo(List.fill(64)(info))))
      check(rejected("BOUND"){checked.infoPresent(new MultiInfo(List.fill(65)(info)))})
      //1 root +4 intermediate +251 leaves =256 visited Info nodes.
      val branches=List(new MultiInfo(List.fill(63)(info)),new MultiInfo(List.fill(63)(info)),
        new MultiInfo(List.fill(63)(info)),new MultiInfo(List.fill(62)(info)))
      check(checked.infoPresent(new MultiInfo(branches)))
      check(rejected("BOUND"){checked.infoPresent(new MultiInfo(branches.init :+ new MultiInfo(List.fill(63)(info))))})
      checked.resetSnapshot();checked.text=(1L<<20)-4096
      check(checked.infoPresent(FileInfo("x"*4096))&&checked.text==(1L<<20))
      check(rejected("BOUND"){checked.infoPresent(info)})
      checked.resetSnapshot();checked.infoNodes=65535
      check(checked.infoPresent(info)&&checked.infoNodes==65536)
      check(rejected("BOUND"){checked.infoPresent(info)})
      checked.resetSnapshot();checked.slots=65535
      check(checked.infoPresent(new MultiInfo(info::Nil))&&checked.slots==65536)
      check(rejected("BOUND"){checked.infoPresent(new MultiInfo(info::Nil))})
    }
    locally {val b=new Budget;b.used(C.Hash)=C.limits(C.Hash)
      check(rejected("BUDGET"){b.hash("a")}&&b.used(C.Hash)==C.limits(C.Hash))}
    locally {val b=new Budget;b.used(C.Equal)=C.limits(C.Equal)
      check(rejected("BUDGET"){b.equal("a","a")}&&b.used(C.Equal)==C.limits(C.Equal))}
    locally {val b=new Budget;val n=new Names(b,8,4);n.add("a");b.used(C.Probe)=C.limits(C.Probe)
      check(rejected("BUDGET"){n.contains("a")}&&b.used(C.Probe)==C.limits(C.Probe))}
    locally {val b=new Budget;val n=new Names(b,8,4);n.add("a");b.used(C.Clear)=C.limits(C.Clear)
      check(rejected("BUDGET"){n.clear()}&&n.contains("a"))}
    locally {val b=new Budget;b.used(C.Temp)=C.limits(C.Temp)
      check(rejected("BUDGET"){b.iter(List(1))}&&b.used(C.Temp)==C.limits(C.Temp))}
    checks
  }
  /** Independent sizing tests; the original69 checks are deliberately unchanged. */
  def sizingSelfChecks():Int={
    var checks=0
    def check(ok:Boolean):Unit={require(ok,"SIZING_SELFCHECK");checks+=1}
    def rejected(code:String)(body: =>Unit):Boolean=try{body;false}catch{
      case x:Abort=>x.reason==code;case x:SizingAbort=>x.reason==code}
    def fields(s:String):Array[String]=s.split(":",-1)
    val info=FileInfo("sizing:1");val clk=Reference("clock",ClockType,PortKind,SourceFlow)
    val leaf=UIntLiteral(0)
    val shared=DoPrim(firrtl2.PrimOps.And,List(leaf,leaf),Nil,UIntType(IntWidth(1)))
    val mux=Mux(leaf,shared,shared,UIntType(IntWidth(1)))
    val con=Connect(info,Reference("out",UIntType(IntWidth(1))),mux)
    val print=Print(info,StringLit("size"),List(shared,shared),clk,leaf,"print")
    val body=Block(List(con,print))
    def circuit(s:Statement):Circuit=Circuit(NoInfo,List(Module(NoInfo,"Top",List(Port(NoInfo,"clock",Input,ClockType)),s)),"Top")
    val input=circuit(body)
    val sized=new Sizer;val receipt=fields(sized.run(input))
    check(receipt.take(2).toList==List("COMPLETE","NONE"))
    check(receipt.slice(2,8).map(_.toLong).toList==List(1L,1L,3L,6L,17L,11L))
    check(receipt(8)=="1"&&receipt(9)=="2"&&receipt(12)=="28"&&sized.cleaned)
    locally {val b=new Budget;val r=new Records(b);val uses=new Uses(b,r,new Checked(b),false);val walk=new Walk(b)
      walk.start(body);var s=walk.next();while(s!=null){uses.scan(s,0);walk.descend(s);s=walk.next()}
      check(b.used(C.Expr)==28&&b.prefix(2)==17&&b.prefix(3)==11&&b.prefix.sum==28)
    }
    locally {val b=new Budget;val checked=new Checked(b)
      val r=DefRegister(info,"r",ClockType,clk,leaf,leaf)
      checked.mismatch(r);checked.infoPresent(info);checked.same(info,info);b.charge(C.Expr)
      check(b.prefix.toList==List(2L,4L,0L,0L,1L)&&b.prefix.sum==b.used(C.Expr))
    }
    val dimensions=Array("GLOBAL_VISIT","GLOBAL_EXPR","NAMES","HASH","EQUAL","PROBE","CLEAR","TEMP")
    var i=0
    while(i<8){val b=new Budget;b.used(i)=C.limits(i);if(i==C.Expr)b.prefix(4)=C.limits(i)
      val before=b.prefix.clone();val failure=rejected("BUDGET"){b.charge(i)};val first=b.failureEvidence
      rejected("BUDGET"){b.charge(i)}
      check(failure&&fields(first)(0)==dimensions(i)&&fields(first)(1).toLong==C.limits(i)&&
        fields(first)(2)=="0"&&fields(first)(3)=="1"&&before.toList==b.prefix.toList&&b.failureEvidence==first)
      i+=1
    }
    locally {val b=new Budget;b.scanVisit=1L<<22;b.used(C.Visit)=1L<<22
      check(rejected("SCAN_BUDGET"){b.charge(C.Visit)}&&b.failureEvidence.startsWith("SCAN_VISIT:4194304:4194304:1:4194304:"))}
    locally {val b=new Budget;b.scanExpr=C.ScanExpr;b.used(C.Expr)=C.ScanExpr;b.prefix(2)=C.ScanExpr
      check(rejected("SCAN_BUDGET"){b.charge(C.Expr,1,3)}&&b.failureEvidence.startsWith("SCAN_EXPR:16777216:16777216:1:16777216:")&&b.prefix(3)==0)}
    locally {val b=new Budget;b.scanExpr=C.ScanExpr;b.used(C.Expr)=1L<<25;b.prefix(4)=1L<<25
      check(rejected("BUDGET"){b.charge(C.Expr)}&&fields(b.failureEvidence)(0)=="GLOBAL_EXPR")}
    val totalVisits=receipt(2).toLong+receipt(3).toLong+receipt(4).toLong
    def run(s:Sizer,c:Circuit=input):Array[String]=fields(s.run(c))
    check(run(new Sizer(visitLimit=totalVisits))(0)=="COMPLETE")
    check(run(new Sizer(visitLimit=totalVisits-1))(1)=="VISITS")
    check(run(new Sizer(nodeLimit=17))(0)=="COMPLETE")
    check(run(new Sizer(nodeLimit=16))(1)=="NODES")
    check(run(new Sizer(edgeLimit=11))(0)=="COMPLETE")
    check(run(new Sizer(edgeLimit=10))(1)=="EDGES")
    val work=receipt(10).toLong;val transient=receipt(11).toLong
    check(run(new Sizer(workLimit=work))(0)=="COMPLETE")
    check(run(new Sizer(workLimit=work-1))(1)=="WORK")
    check(run(new Sizer(transientLimit=transient))(0)=="COMPLETE")
    check(run(new Sizer(transientLimit=transient-1))(1)=="TRANSIENT")
    check(rejected("TRANSIENT"){new Sizer(transientLimit=55)})
    check(rejected("WORK"){new Sizer(workLimit=7)})
    check(run(new Sizer(depthLimit=2))(0)=="COMPLETE")
    check(run(new Sizer(depthLimit=1))(1)=="DEPTH")
    locally {var deep:Statement=EmptyStmt;var j=0;while(j<256){deep=Block(deep::Nil);j+=1}
      check(run(new Sizer,circuit(deep))(0)=="COMPLETE")
      check(run(new Sizer,circuit(Block(deep::Nil)))(1)=="DEPTH")}
    locally {var deep:Expression=leaf;var j=0;while(j<256){deep=ValidIf(leaf,deep,UIntType(IntWidth(1)));j+=1}
      check(run(new Sizer,circuit(DefNode(info,"deep",deep)))(0)=="COMPLETE")
      check(run(new Sizer,circuit(DefNode(info,"deep",ValidIf(leaf,deep,UIntType(IntWidth(1))))))(1)=="DEPTH")}
    locally {val s=new Sizer;val r=run(s,circuit(Block(scala.collection.immutable.LazyList(EmptyStmt))))
      check(r(0)=="ERROR"&&r(1)=="FAMILY"&&s.cleaned)}
    locally {val s=new Sizer;val r=run(s,circuit(DefNode(info,"x",DoPrim(firrtl2.PrimOps.And,
        scala.collection.immutable.LazyList(leaf),Nil,UIntType(IntWidth(1))))))
      check(r(0)=="ERROR"&&r(1)=="FAMILY"&&s.cleaned)}
    locally {val s=new Sizer;val r=run(s,circuit(Block(List.fill(1024)(EmptyStmt))))
      check(r(0)=="COMPLETE"&&r(4)=="1025"&&r(6)=="0"&&r(7)=="0"&&s.cleaned)}
    locally {val s=new Sizer;val r=run(s,circuit(DefNode(info,"empty",firrtl2.EmptyExpression)))
      check(r(0)=="COMPLETE"&&r(5)=="1"&&r(6)=="1"&&r(7)=="0")}
    locally {val s=new Sizer(nodeLimit=1);val r=run(s,circuit(Connect(info,leaf,leaf)))
      check(r(0)=="TRUNCATED"&&r(1)=="NODES"&&r(5)=="1"&&r(6)=="1"&&s.cleaned)}
    locally {val s=new Sizer(nodeLimit=1);val r=run(s,circuit(DefNode(info,"node",shared)))
      check(r(0)=="TRUNCATED"&&r(1)=="NODES"&&r(6)=="1"&&r(7)=="1"&&s.cleaned)}
    // Trigger using the production budget/guard and next-iteration callback.
    // It is an internal callback identity test, not official full-pipeline parity.
    locally {val o=new Observation(1);val state=CircuitState(input,Seq.empty)
      o.sizingFixtureFailure("INITIAL_USES",0)
      val primary=o.evidence;val budget=o.budgetEvidence;val c0=state.circuit;val a0=state.annotations
      check(primary.startsWith("TRUNCATED:INITIAL_USES:SCAN_BUDGET:")&&o.sizingEvidence=="NONE"&&o.sizingPendingForTest)
      o.sizePending(state)
      check(o.evidence==primary&&o.budgetEvidence==budget&&fields(o.sizingEvidence)(0)=="COMPLETE"&&
        (state.circuit eq c0)&&(state.annotations eq a0) && !o.sizingPendingForTest)
      val once=o.sizingEvidence;o.sizePending(CircuitState(circuit(EmptyStmt),Seq.empty))
      check(o.sizingEvidence==once)
    }
    locally {val o=new Observation(1);o.sizingFixtureFailure("INITIAL_USES",1)
      check(o.evidence.startsWith("TRUNCATED:INITIAL_USES:BOUND:")&&o.budgetEvidence=="NONE"&&o.sizingEvidence=="NONE" && !o.sizingPendingForTest)}
    locally {val o=new Observation(1);o.sizingFixtureFailure("ORIGINAL",2)
      check(o.budgetEvidence=="NONE"&&o.sizingEvidence=="NONE" && !o.sizingPendingForTest)}
    locally {val o=new Observation(1);o.sizingFixtureFailure("INITIAL_USES",0);val primary=o.evidence;val budget=o.budgetEvidence
      o.sizePending(CircuitState(circuit(Block(scala.collection.immutable.LazyList(EmptyStmt))),Seq.empty))
      check(o.evidence==primary&&o.budgetEvidence==budget&&o.sizingEvidence.startsWith("ERROR:FAMILY:"))}
    val leaves=List[Expression](clk,leaf,SIntLiteral(0),firrtl2.WVoid,firrtl2.WInvalid,firrtl2.EmptyExpression)
    var li=0
    while(li<6){val expression=leaves(li);val stmt=DefNode(info,"leaf",expression)
      val census=run(new Sizer,circuit(stmt));val b=new Budget;val records=new Records(b)
      new Uses(b,records,new Checked(b),false).scan(stmt,0)
      check(census(0)=="COMPLETE"&&census(5)=="1"&&census(6)=="1"&&census(7)=="0"&&
        b.used(C.Expr)==1&&b.prefix(2)==1&&b.prefix(3)==0)
      li+=1
    }
    locally {val expr=new Reference("subclass",ClockType,PortKind,SourceFlow){}
      val s=new Sizer;val r=run(s,circuit(DefNode(info,"bad",expr)))
      check(r(0)=="ERROR"&&r(1)=="EXPRESSION"&&s.cleaned)}
    locally {val stmt=new DefNode(info,"bad",leaf){}
      val s=new Sizer;val r=run(s,circuit(stmt))
      check(r(0)=="ERROR"&&r(1)=="STRUCTURE"&&s.cleaned)}
    locally {val r=run(new Sizer,circuit(DefNode(info,"emptyprim",DoPrim(firrtl2.PrimOps.And,Nil,Nil,UIntType(IntWidth(1))))))
      check(r(0)=="COMPLETE"&&r(5)=="1"&&r(6)=="1"&&r(7)=="0")}
    locally {val o=new Observation(1);o.sizingFixtureFailure("INITIAL_USES",3)
      val original=o.evidence;o.sizePending(CircuitState(input,Seq.empty))
      check(original.startsWith("TRUNCATED:INITIAL_USES:BUDGET:")&&o.evidence==original&&
        o.budgetEvidence=="UNAVAILABLE"&&o.sizingEvidence=="ERROR:UNEXPECTED:0:0:0:0:0:0:0:0:0:0:0"&&
        !o.sizingPendingForTest&&o.cleaned)}
    checks
  }

  /** Explicit measured per-scan revision; no other quota changes. */
  def quotaSelfChecks():Int={
    var checks=0
    def check(ok:Boolean):Unit={require(ok,"QUOTA_SELFCHECK");checks+=1}
    def rejected(body: =>Unit):Boolean=try{body;false}catch{case _:Abort=>true}
    locally {val b=new Budget;b.used(C.Expr)=1L<<23;b.scanExpr=1L<<23;b.prefix(2)=1L<<23
      b.charge(C.Expr,1,3)
      check(b.scanExpr==(1L<<23)+1&&b.used(C.Expr)==(1L<<23)+1&&b.prefix(3)==1&&b.failureEvidence=="NONE")}
    locally {val b=new Budget;b.used(C.Expr)=C.ScanExpr-1;b.scanExpr=C.ScanExpr-1;b.prefix(2)=C.ScanExpr-1
      b.charge(C.Expr,1,3);val accepted=b.used(C.Expr)
      check(accepted==C.ScanExpr&&rejected{b.charge(C.Expr,1,3)}&&b.used(C.Expr)==accepted&&b.prefix(3)==1&&
        b.failureEvidence=="SCAN_EXPR:16777216:16777216:1:16777216:16777216:16777216:0:0:16777215:1:0")}
    locally {val b=new Budget;b.used(C.Expr)=C.limits(C.Expr);b.scanExpr=C.ScanExpr;b.prefix(2)=C.limits(C.Expr)
      check(rejected{b.charge(C.Expr)}&&b.failureEvidence.startsWith("GLOBAL_EXPR:33554432:16777216:1:33554432:"))}
    locally {val b=new Budget;b.charge(C.Expr,17,1);b.charge(C.Visit,3);b.start()
      check(b.scanExpr==0&&b.scanVisit==0&&b.used(C.Expr)==17&&b.used(C.Visit)==3&&b.prefix(1)==17)}
    locally {val b=new Budget;b.charge(C.Expr,C.ScanExpr,2);b.start();b.charge(C.Expr,C.ScanExpr,3);b.start()
      check(b.used(C.Expr)==(1L<<25)&&b.prefix(2)==C.ScanExpr&&b.prefix(3)==C.ScanExpr&&
        rejected{b.charge(C.Expr)}&&b.failureEvidence.startsWith("GLOBAL_EXPR:33554432:0:1:33554432:"))}
    check(C.ScanExpr==(1L<<24)&&C.limits.toList==List[Long](1L<<24,1L<<25,1L<<22,1L<<29,1L<<30,1L<<26,1L<<22,1L<<24))
    checks
  }

  /** Same private descriptor/Uses helpers; no formal consumer is accepted. */
  def consumerSelfChecks():Int={
    var checks=0
    def check(ok:Boolean):Unit={require(ok,"CONSUMER_SELFCHECK");checks+=1}
    val info=FileInfo("private-info-never-exported:99")
    val clock=Reference("private-clock-never-exported",ClockType,PortKind,SourceFlow)
    val ref=Reference("private-register-never-exported",ClockType,NodeKind,SourceFlow)
    val reg=DefRegister(info,ref.name,ClockType,clock,UIntLiteral(0),UIntLiteral(0))
    val driver=Connect(info,ref,clock)
    val print=Print(info,StringLit("private-format"),Nil,ref,UIntLiteral(1),"private-print")
    val stop=Stop(info,0,ref,UIntLiteral(1),"private-stop")
    val formal=Verification(Formal.Assert,info,ref,UIntLiteral(1),UIntLiteral(1),StringLit("nonempty-negative"),"private-formal")
    def finish(a:Statement,z:Statement,finalStage:Boolean=false):Abort={
      val b=new Budget;val records=new Records(b);records.add(0,"private-module",reg,clock)
      val uses=new Uses(b,records,new Checked(b),finalStage)
      uses.port(0,Port(NoInfo,clock.name,Input,ClockType));uses.scan(a,0);uses.scan(z,0)
      try{uses.finish();new Abort("UNEXPECTED")}catch{case e:Abort=>e}
    }
    val missing=finish(driver,formal)
    check(missing.reason=="CONSUMER"&&consumerCode(missing)==
      "MISSING:CONNECT:1:TRUE:CLOCK:NODE:SOURCE:NA:NA:VERIFICATION:1:TRUE:CLOCK:NODE:SOURCE:ASSERT:NONEMPTY")
    val duplicate=finish(print,stop)
    check(duplicate.reason=="CONSUMER"&&consumerCode(duplicate).startsWith("DUPLICATE:PRINT:1:TRUE:CLOCK:NODE:SOURCE:NA:NA:STOP:1:"))
    check(finish(formal,formal.copy(name="other-formal")).reason=="DRIVER")
    val nested=DoPrim(firrtl2.PrimOps.AsClock,ref::Nil,Nil,ClockType)
    check(consumerCode(finish(driver,print.copy(clk=nested)))==
      "MISSING:CONNECT:1:TRUE:CLOCK:NODE:SOURCE:NA:NA:PRINT:1:FALSE:NA:NA:NA:NA:NA")
    val alias=print.copy(en=ref)
    check(consumerCode(consumerAbort("DUPLICATE",alias,ref,true,alias,ref,true)).contains("PRINT:3:TRUE:"))
    val allFields=formal.copy(pred=ref,en=ref)
    check(consumerCode(consumerAbort("MISSING",driver,ref,true,allFields,ref,true)).contains("VERIFICATION:7:TRUE:"))
    val printArg=print.copy(args=ref::Nil,clk=clock)
    check(consumerCode(consumerAbort("MISSING",driver,ref,true,printArg,ref,true)).contains("PRINT:0:TRUE:"))
    check(consumerCode(consumerAbort("FINAL_KIND",driver,ref,true,formal,ref,true)).startsWith("FINAL_KIND:"))
    check(consumerCode(consumerAbort("MISSING",driver,ref,true,formal.copy(op=Formal.Assume,msg=StringLit("secret-message")),ref,true)).endsWith(":ASSUME:NONEMPTY"))
    check(consumerCode(consumerAbort("MISSING",driver,ref,true,formal.copy(op=Formal.Cover,msg=StringLit("")),ref,true)).endsWith(":COVER:EMPTY"))
    val uint=ref.copy(tpe=UIntType(IntWidth(1)),kind=firrtl2.RegKind,flow=SinkFlow)
    check(consumerCode(consumerAbort("MISSING",driver,uint,false,formal,uint,false)).contains(":UINT:REG:SINK:"))
    val other=ref.copy(tpe=ResetType,kind=firrtl2.UnknownKind,flow=firrtl2.UnknownFlow)
    check(consumerCode(consumerAbort("MISSING",driver,other,false,formal,other,false)).contains(":OTHER:UNKNOWN:UNKNOWN:"))
    val malformed=consumerAbort("MISSING",null,ref,true,formal,ref,true)
    check(malformed.reason=="CONSUMER"&&consumerCode(malformed)=="UNAVAILABLE")
    val badMessage=formal.copy(msg=new StringLit("private-subclass"){})
    check(consumerAbort("MISSING",driver,ref,true,badMessage,ref,true).consumerCode=="UNAVAILABLE")
    val invalid=new Abort("CONSUMER");invalid.consumerCode="MISSING:"+"PRIVATE"*100
    check(consumerCode(invalid)=="UNAVAILABLE")
    invalid.consumerCode=consumerCode(missing).replace("ASSERT","secret-token")
    check(consumerCode(invalid)=="UNAVAILABLE")
    invalid.consumerCode=consumerCode(missing)+":EXTRA"
    check(consumerCode(invalid)=="UNAVAILABLE")
    invalid.consumerCode=consumerCode(missing).replace(":CONNECT:1:",":CONNECT:7:")
    check(consumerCode(invalid)=="UNAVAILABLE")
    val code=consumerCode(missing)
    check(code.length<=512&&code.forall(c=>c<=127) && !code.contains("private") && !code.contains("99") && !code.contains("secret"))
    check(finish(driver.copy(loc=ref.copy(flow=SinkFlow)),formal,true).consumerCode=="NONE")
    locally {val o=new Observation(1);o.consumerFixtureFailure("INITIAL_USES",missing)
      check(o.evidence.startsWith("UNAVAILABLE:INITIAL_USES:CONSUMER:0:0:0:0:0:0:0:")&&o.consumerEvidence==code&&o.cleaned)}
    locally {val o=new Observation(1);o.consumerFixtureFailure("P54",missing)
      check(o.evidence.startsWith("UNAVAILABLE:P54:CONSUMER:")&&o.consumerEvidence=="NONE")}
    locally {val o=new Observation(1);o.consumerFixtureFailure("INITIAL_USES",malformed)
      check(o.evidence.startsWith("UNAVAILABLE:INITIAL_USES:CONSUMER:")&&o.consumerEvidence=="UNAVAILABLE"&&o.cleaned)}
    invalid.consumerCode=consumerCode(missing).replace(":CLOCK:NODE:SOURCE:",":NA:NODE:SOURCE:")
    check(consumerCode(invalid)=="UNAVAILABLE")
    checks
  }

  /** Narrow empty-Assert source/transition checks using the production helpers. */
  def formalSelfChecks():Int={
    var checks=0
    def check(ok:Boolean):Unit={require(ok,"FORMAL_SELFCHECK");checks+=1}
    def rejected(body: =>Unit):Boolean=try{body;false}catch{case _:Abort=>true}
    val info=FileInfo("formal:1");val source=Reference("clock",ClockType,PortKind,SourceFlow)
    val delayedClock=Reference("sample",ClockType,NodeKind,SourceFlow)
    val pred=Reference("predicate",UIntType(IntWidth(1)),NodeKind,SourceFlow)
    val en=Reference("enable",UIntType(IntWidth(1)),NodeKind,SourceFlow)
    val reg=DefRegister(info,delayedClock.name,ClockType,source,UIntLiteral(0),UIntLiteral(0))
    val v=Verification(Formal.Assert,info,delayedClock,pred,en,StringLit(""),"assertion")
    val original=v.copy(clk=source,pred=UIntLiteral(1),en=UIntLiteral(1))
    def stop(c:Expression=delayedClock,p:Expression=pred,e:Expression=en):Stop={
      val not=DoPrim(firrtl2.PrimOps.Not,p::Nil,Nil,p.tpe)
      Stop(info,65,c,DoPrim(firrtl2.PrimOps.And,List(not,e),Nil,p.tpe),v.name)
    }
    final case class Fixture(b:Budget,r:Records,f:FormalRecords)
    def fixture(cap:Int=1024,limit:Long=1L<<19):Fixture={
      val b=new Budget;val r=new Records(b);r.add(0,"Top",reg,source)
      val f=if(cap==1024&&limit==(1L<<19))r.formals else new FormalRecords(b,r,cap,limit)
      Fixture(b,r,f)
    }
    def capture(x:Fixture):Unit={x.r.capture(new Checked(x.b));if(!(x.f eq x.r.formals))x.f.capture()}
    def admitted(value:Verification):Boolean={val x=fixture();!rejected{x.f.add(0,value)}}
    check(admitted(v))
    check(!admitted(v.copy(msg=StringLit("nonempty"))))
    check(!admitted(v.copy(op=Formal.Assume)))
    check(!admitted(v.copy(op=Formal.Cover)))
    check(!admitted(new Verification(v.op,v.info,v.clk,v.pred,v.en,v.msg,v.name){}))
    check(!admitted(v.copy(msg=new StringLit(""){})))
    check(!admitted(v.copy(pred=UIntLiteral(1))))
    check(!admitted(v.copy(pred=pred.copy(tpe=UIntType(IntWidth(2))))))
    check(!admitted(v.copy(pred=pred.copy(kind=firrtl2.RegKind))))
    check(!admitted(v.copy(en=en.copy(flow=SinkFlow))))
    check(!admitted(v.copy(clk=source)))
    check(!admitted(v.copy(info=FileInfo("formal:1"))))
    locally {val x=fixture();x.f.add(0,v);val anchors=new Array[Int](1024);x.f.anchor(original,0,anchors)
      check(anchors(0)==1)
      check(rejected{x.f.anchor(original,0,anchors)})}
    locally {val x=fixture();x.f.add(0,v);val anchors=new Array[Int](1024)
      check(rejected{x.f.anchor(original.copy(name=new String(v.name)),0,anchors)})
      check(rejected{x.f.anchor(original.copy(info=FileInfo("formal:1")),0,anchors)})
      check(rejected{x.f.anchor(original.copy(clk=source.copy()),0,anchors)})
      x.f.anchor(original.copy(msg=StringLit("nonempty")),0,anchors);check(anchors(0)==0)
      x.f.anchor(original,1,anchors);check(anchors(0)==0)}
    locally {val x=fixture();x.f.add(0,v);capture(x);val s52=stop()
      x.f.inspect(s52,0,52);x.f.finish(52);x.f.clearSnapshot();check(x.f.p52==1&&x.f.snapshotsEmpty)
      capture(x);val s53=stop();x.f.inspect(s53,0,53);x.f.finish(53);x.f.clearSnapshot()
      check(x.f.p53==1&&x.f.snapshotsEmpty)
      capture(x);val s54=stop(delayedClock.copy(),pred.copy(),en.copy())
      x.f.inspect(s54,0,54);x.f.finish(54)
      check(x.f.p54==1&&x.f.sameFinal(0,s54) && !x.f.sameFinal(0,s54.copy()))
      x.f.clear();check(x.f.snapshotsEmpty);java.lang.ref.Reference.reachabilityFence(s52);java.lang.ref.Reference.reachabilityFence(s53);java.lang.ref.Reference.reachabilityFence(s54)}
    def rejects52(s:Statement):Boolean={val x=fixture();x.f.add(0,v);capture(x);rejected{x.f.inspect(s,0,52)}}
    check(rejects52(stop().copy(ret=66)))
    check(rejects52(stop().copy(name=new String(v.name))))
    check(rejects52(stop().copy(info=FileInfo("formal:1"))))
    check(rejects52(stop(c=delayedClock.copy())))
    check(rejects52(stop(p=pred.copy())))
    check(rejects52(stop(e=en.copy())))
    check(rejects52(stop(p=en,e=pred)))
    check(rejects52(stop().copy(en=DoPrim(firrtl2.PrimOps.Or,List(pred,en),Nil,pred.tpe))))
    check(rejects52(stop().copy(en=DoPrim(firrtl2.PrimOps.And,List(pred,en),Nil,pred.tpe))))
    val good=stop().en.asInstanceOf[DoPrim]
    check(rejects52(stop().copy(en=good.copy(args=good.args :+ en))))
    check(rejects52(stop().copy(en=good.copy(consts=BigInt(0)::Nil))))
    check(rejects52(stop().copy(en=good.copy(tpe=UIntType(IntWidth(1))))))
    check(rejects52(stop().copy(en=good.copy(args=scala.collection.immutable.LazyList(good.args.head,en)))))
    locally {val x=fixture();x.f.add(0,v);capture(x);val s=stop();x.f.inspect(s,0,52)
      check(rejected{x.f.inspect(s,0,52)})}
    locally {val x=fixture();x.f.add(0,v);capture(x);check(rejected{x.f.finish(52)})}
    locally {val x=fixture();x.f.add(0,v);x.f.clearWeakForTest(0);check(rejected{capture(x)})}
    locally {val x=fixture(cap=1);x.f.add(0,v)
      x.r.add(0,"Top",reg.copy(name="second"),source)
      check(rejected{x.f.add(1,v.copy(name="second-assert",clk=delayedClock.copy(name="second")))})}
    val live=v.name.length.toLong+delayedClock.name.length+pred.name.length+en.name.length
    locally {val x=fixture(limit=live);x.f.add(0,v);capture(x);check(!x.f.snapshotsEmpty);x.f.clear()}
    locally {val x=fixture(limit=live-1);x.f.add(0,v);check(rejected{capture(x)});x.f.clear();check(x.f.snapshotsEmpty)}
    locally {val x=fixture();x.b.used(C.Temp)=C.limits(C.Temp)
      check(rejected{x.f.add(0,v)}&&x.f.count==0)}
    locally {val x=fixture();x.f.add(0,v);capture(x);val keep52=stop();x.f.inspect(keep52,0,52);x.f.finish(52);x.f.clearSnapshot();capture(x)
      check(rejected{x.f.inspect(stop(p=pred.copy()),0,53)});java.lang.ref.Reference.reachabilityFence(keep52)}
    locally {val x=fixture();x.f.add(0,v);capture(x);val keep52=stop();x.f.inspect(keep52,0,52);x.f.finish(52);x.f.clearSnapshot();capture(x)
      val keep53=stop();x.f.inspect(keep53,0,53);x.f.finish(53);x.f.clearSnapshot();capture(x)
      check(rejected{x.f.inspect(stop(p=pred.copy(name=new String(pred.name))),0,54)});java.lang.ref.Reference.reachabilityFence(keep52);java.lang.ref.Reference.reachabilityFence(keep53)}
    locally {val x=fixture();x.f.add(0,v);capture(x);val keep52=stop();x.f.inspect(keep52,0,52);x.f.finish(52);x.f.clearSnapshot();capture(x)
      val keep53=stop();x.f.inspect(keep53,0,53);x.f.finish(53);x.f.clearSnapshot();capture(x)
      check(rejected{x.f.inspect(stop(e=en.copy(flow=SinkFlow)),0,54)});java.lang.ref.Reference.reachabilityFence(keep52);java.lang.ref.Reference.reachabilityFence(keep53)}
    // Full private observation path including original anchor and final same-object
    // Uses agreement. Actual official pass parity is a separately counted fixture.
    def state(s:Statement):CircuitState=CircuitState(Circuit(NoInfo,Module(NoInfo,"Top",
      Port(NoInfo,source.name,Input,ClockType)::Nil,s)::Nil,"Top"),Seq.empty)
    def post(r:DefRegister,t:Statement,finalStage:Boolean):CircuitState={
      val loc=delayedClock.copy(flow=if(finalStage)SinkFlow else SourceFlow)
      state(Block(List(r,Connect(info,loc,source),t)))
    }
    locally {val o=new Observation(1);val before=state(original);val s51=post(reg,v,false)
      o.before(51,before);o.afterAugment(before,s51)
      o.before(52,s51);val s52=post(reg,stop(),false);o.afterSuffix(52,s52)
      val r53=reg.copy();o.before(53,s52);val s53=post(r53,stop(),false);o.afterSuffix(53,s53)
      o.before(54,s53);val s54=post(r53.copy(clock=source.copy()),stop(delayedClock.copy(),pred.copy(),en.copy()),true)
      o.afterSuffix(54,s54)
      check(o.evidence.startsWith("COMPLETE:DONE:NONE:1:1:1:1:1:1:1:")&&o.formalEvidence=="COMPLETE:1:1:1:1"&&o.cleaned)}
    locally {val o=new Observation(1);val before=state(original.copy(name="missing-anchor"));val s51=post(reg,v,false)
      o.before(51,before);o.afterAugment(before,s51)
      check(o.evidence.startsWith("UNAVAILABLE:ORIGINAL:ANCHOR:")&&o.formalEvidence=="UNAVAILABLE:0:0:0:0"&&o.cleaned)}
    val not=good.args.head.asInstanceOf[DoPrim]
    check(rejects52(stop().copy(en=good.copy(args=List(not.copy(op=firrtl2.PrimOps.And),en)))))
    check(rejects52(stop().copy(en=good.copy(args=List(not.copy(args=List(pred,pred)),en)))))
    check(rejects52(stop().copy(en=good.copy(args=List(not.copy(consts=BigInt(0)::Nil),en)))))
    check(rejects52(stop().copy(en=good.copy(args=List(not.copy(tpe=UIntType(IntWidth(1))),en)))))
    locally {val x=fixture();x.b.used(C.Clear)=C.limits(C.Clear)
      check(rejected{new FormalRecords(x.b,x.r)})}
    locally {val x=fixture();x.f.add(0,v);capture(x);x.b.used(C.Clear)=C.limits(C.Clear)
      x.f.clear();check(x.f.snapshotsEmpty)}
    val honestWidth=new scala.math.BigInt(new java.math.BigInteger("1"))
    check(admitted(v.copy(pred=pred.copy(tpe=UIntType(new IntWidth(honestWidth))))))
    val hugeWidth=new scala.math.BigInt(java.math.BigInteger.ONE.shiftLeft(512))
    check(!admitted(v.copy(pred=pred.copy(tpe=UIntType(new IntWidth(hugeWidth))))))
    val deceptiveBacking=new java.math.BigInteger("123456789012345678901234567890"){
      override def bitLength():Int=1
      override def longValue():Long=1L
    }
    val deceptiveWidth=new scala.math.BigInt(deceptiveBacking)
    check(!admitted(v.copy(pred=pred.copy(tpe=UIntType(new IntWidth(deceptiveWidth))))))
    checks
  }

  /** Same-code first-anchor diagnostics; no new production traversal. */
  def anchorSelfChecks():Int={
    var checks=0
    def check(ok:Boolean):Unit={require(ok,"ANCHOR_SELFCHECK");checks+=1}
    val info=FileInfo("private-anchor:1");val clk=Reference("clock",ClockType,PortKind,SourceFlow)
    val reg=DefRegister(info,"sample",ClockType,clk,UIntLiteral(0),UIntLiteral(0))
    val v=Verification(Formal.Assert,info,clk,UIntLiteral(1),UIntLiteral(1),StringLit(""),"private-terminal")
    def code(site:String,s:Statement=v,z:Statement=null,r:DefRegister=reg,n:String=v.name,p:Int=0):String=
      anchorCode(anchorAbort(site,s,z,r,n,p))
    check(code("FORMAL_NAME_INFO",n=new String(v.name))=="AVAILABLE:FORMAL_NAME_INFO:EMPTY_ASSERT:FALSE:TRUE:TRUE:ZERO")
    check(code("FORMAL_NAME_INFO",s=v.copy(info=FileInfo("private-anchor:1")))=="AVAILABLE:FORMAL_NAME_INFO:EMPTY_ASSERT:TRUE:FALSE:TRUE:ZERO")
    check(code("FORMAL_NAME_INFO",s=v.copy(info=NoInfo),n="different").contains(":FALSE:FALSE:TRUE:"))
    check(code("FORMAL_CLOCK",s=v.copy(clk=clk.copy()))=="AVAILABLE:FORMAL_CLOCK:EMPTY_ASSERT:TRUE:TRUE:FALSE:ZERO")
    check(code("FORMAL_DUPLICATE",p=1)=="AVAILABLE:FORMAL_DUPLICATE:EMPTY_ASSERT:TRUE:TRUE:TRUE:ONE")
    val print=Print(info,StringLit("private-format"),Nil,clk,UIntLiteral(1),v.name)
    val stop=Stop(info,65,clk,UIntLiteral(1),v.name)
    check(code("ORDINARY_DUPLICATE",print,print,p=1)=="AVAILABLE:ORDINARY_DUPLICATE:PRINT:TRUE:TRUE:NA:ONE")
    check(code("ORDINARY_DUPLICATE",stop,stop.copy(name=new String(stop.name),info=FileInfo("private-anchor:1")),p=1)=="AVAILABLE:ORDINARY_DUPLICATE:STOP:FALSE:FALSE:NA:ONE")
    check(code("FINAL_MISSING")=="AVAILABLE:FINAL_MISSING:EMPTY_ASSERT:NA:NA:NA:ZERO")
    check(code("FINAL_MISSING",print)=="AVAILABLE:FINAL_MISSING:PRINT:NA:NA:NA:ZERO")
    check(code("FINAL_MISSING",stop)=="AVAILABLE:FINAL_MISSING:STOP:NA:NA:NA:ZERO")
    check(code("FINAL_MISSING",EmptyStmt)=="AVAILABLE:FINAL_MISSING:OTHER:NA:NA:NA:ZERO")
    check(code("FORMAL_DUPLICATE",p=2).endsWith(":OTHER"))
    check(code("BAD_SITE")=="UNAVAILABLE")
    check(code("FORMAL_CLOCK",s=null)=="UNAVAILABLE")
    check(code("FORMAL_CLOCK",s=new Verification(v.op,v.info,v.clk,v.pred,v.en,v.msg,v.name){})=="UNAVAILABLE")
    check(code("ORDINARY_DUPLICATE",print,stop,p=1)=="UNAVAILABLE")
    val invalid=new Abort("ANCHOR");invalid.anchorCode="AVAILABLE:"+"PRIVATE"*100
    check(anchorCode(invalid)=="UNAVAILABLE")
    invalid.anchorCode=code("FINAL_MISSING")+":EXTRA";check(anchorCode(invalid)=="UNAVAILABLE")
    invalid.anchorCode=code("FINAL_MISSING").replace("EMPTY_ASSERT","secret");check(anchorCode(invalid)=="UNAVAILABLE")
    val failure=anchorAbort("FORMAL_CLOCK",null,null,null,null,0)
    check(failure.reason=="ANCHOR"&& !failure.bounded&&anchorCode(failure)=="UNAVAILABLE")
    val o=new Observation(1);o.consumerFixtureFailure("ORIGINAL",failure)
    check(o.evidence.startsWith("UNAVAILABLE:ORIGINAL:ANCHOR:")&&o.anchorEvidence=="UNAVAILABLE"&&o.cleaned)
    val outside=new Observation(1);outside.consumerFixtureFailure("INITIAL_USES",failure)
    check(outside.anchorEvidence=="NONE")
    val unrelated=new Observation(1);unrelated.consumerFixtureFailure("ORIGINAL",new Abort("INFO"))
    check(unrelated.anchorEvidence=="NONE")
    check(new Observation(1).anchorEvidence=="NONE")
    def thrown(body: =>Unit):String=try{body;"NONE"}catch{case e:Abort=>anchorCode(e)}
    locally {val b=new Budget;val records=new Records(b);records.add(0,"Top",reg,clk)
      val delayed=Reference(reg.name,ClockType,NodeKind,SourceFlow)
      val one=Reference("one",UIntType(IntWidth(1)),NodeKind,SourceFlow)
      records.formals.add(0,v.copy(clk=delayed,pred=one,en=one));val anchors=new Array[Int](1024)
      check(thrown{records.formals.anchor(v.copy(name=new String(v.name)),0,anchors)}.startsWith("AVAILABLE:FORMAL_NAME_INFO:"))
      check(thrown{records.formals.anchor(v.copy(clk=clk.copy()),0,anchors)}.startsWith("AVAILABLE:FORMAL_CLOCK:"))
      records.formals.anchor(v,0,anchors)
      check(thrown{records.formals.anchor(v,0,anchors)}.startsWith("AVAILABLE:FORMAL_DUPLICATE:"))}
    locally {val b=new Budget;val records=new Records(b);records.add(0,"Top",reg,clk)
      val uses=new Uses(b,records,new Checked(b),false);uses.consumers(0)=print;uses.anchors(0)=1
      check(thrown{uses.anchor(print,0)}.startsWith("AVAILABLE:ORDINARY_DUPLICATE:PRINT:"))
      uses.consumers(0)=stop
      check(thrown{uses.anchor(stop,0)}.startsWith("AVAILABLE:ORDINARY_DUPLICATE:STOP:"))}
    check(!code("FORMAL_CLOCK",s=v.copy(clk=clk.copy())).contains("private"))
    locally {def state(body:Statement):CircuitState=CircuitState(Circuit(NoInfo,Module(NoInfo,"Top",
        Port(NoInfo,clk.name,Input,ClockType)::Nil,body)::Nil,"Top"),Seq.empty)
      val delayed=Reference(reg.name,ClockType,NodeKind,SourceFlow)
      val before=state(EmptyStmt);val after=state(Block(List(reg,Connect(info,delayed,clk),print.copy(clk=delayed))))
      val observed=new Observation(1);observed.before(51,before);observed.afterAugment(before,after)
      check(observed.evidence.startsWith("UNAVAILABLE:ORIGINAL:ANCHOR:")&&
        observed.anchorEvidence=="AVAILABLE:FINAL_MISSING:PRINT:NA:NA:NA:ZERO"&&observed.cleaned)}
    checks
  }

}

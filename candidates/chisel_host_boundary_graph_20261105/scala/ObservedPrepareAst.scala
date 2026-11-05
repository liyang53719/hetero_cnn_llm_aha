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
  override def transform(annotationSeq:AnnotationSeq):AnnotationSeq={
    result="UNAVAILABLE:CENSUS:NOT_RUN:0:0:0:0:0:0:0:0:0"
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
          Some(TreadleCircuitStateAnnotation(newState))
        } finally if(observation!=null)observation.release()
      case other=>Some(other)
    }
  }
}

object ObservedPrepareAst {
  private final class Abort(val reason:String,val bounded:Boolean=false) extends RuntimeException(null,null,false,false)
  private def fail(code:String):Nothing=throw new Abort(code)
  private def need(value:Boolean,code:String):Unit=if(!value)fail(code)
  // All allocations belong either to the explicit fixed inventory or to Temp.
  // Fixed: namespace20MiB, module/key/record/frame pools<2MiB, comparison8MiB,
  // transitive names4MiB, Info nodes64MiB + child backing0.5MiB: <128MiB.
  // The independent416MiB old-root lifetime admission is checked by census.
  private object C {
    val Visit=0;val Expr=1;val Names=2;val Hash=3;val Equal=4;val Probe=5;val Clear=6;val Temp=7
    val limits=Array[Long](1L<<24,1L<<25,1L<<22,1L<<29,1L<<30,1L<<26,1L<<22,1L<<24)
  }
  private final class Budget {
    val used=new Array[Long](8)
    var scanVisit=0L;var scanExpr=0L
    def start():Unit={scanVisit=0;scanExpr=0}
    def charge(id:Int,n:Long=1):Unit={
      if(n<0 || n>C.limits(id)-used(id))throw new Abort("BUDGET",true)
      if(id==C.Visit && n>(1L<<22)-scanVisit)throw new Abort("SCAN_BUDGET",true)
      if(id==C.Expr && n>(1L<<23)-scanExpr)throw new Abort("SCAN_BUDGET",true)
      used(id)+=n;if(id==C.Visit)scanVisit+=n;if(id==C.Expr)scanExpr+=n
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
      b.charge(C.Temp,2);b.charge(C.Expr);b.bound(d<=64);nodes+=1;b.bound(nodes<=4096)
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
      b.charge(C.Temp,2);b.charge(C.Expr);b.bound(d<=16);nodes+=1;b.bound(nodes<=256)
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
    private def eqInfo(x:Info,y:Info,d:Int):Boolean={b.charge(C.Expr);b.bound(d<=16)
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
  private final class Records(b:Budget) {
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
        snapshot(i)=r;seen(i)=false;i+=1};checked.snapshot=false}
    def clearSnapshot():Unit={java.util.Arrays.fill(snapshot.asInstanceOf[Array[AnyRef]],null)}
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
      if(it!=null){if(it.hasNext){b.charge(C.Expr);it.next()}else null}
      else{val e=pos(d)match{case 0=>first(d);case 1=>second(d);case 2=>third(d);case _=>null}
        if(e!=null){b.charge(C.Expr);pos(d)+=1};e}}
    private var statement:Statement=null;private var mid=0
    private val root:Expression=>Unit=r=>{
      var e=r;var depth=0;var active=true
      while(active){b.charge(C.Expr);b.bound(depth<=256)
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
    def finish():Unit={var i=0
      while(i<records.count){need(portSeen(i),"CLOCK");need(counts(i)==2,"REFERENCES")
        var driver:Connect=null;var consumer:Statement=null;var j=0
        while(j<2){val k=i*2+j
          if(direct(k))statements(k)match{
            case x:Connect if (roots(k) eq x.loc)&&delayed(x.loc,records.names(i),true,finalStage,b)=>
              need(driver==null,"DRIVER");driver=x
            case x:Print if (roots(k) eq x.clk)&&delayed(x.clk,records.names(i),false,finalStage,b)=>
              need(consumer==null,"CONSUMER");consumer=x
            case x:Stop if (roots(k) eq x.clk)&&delayed(x.clk,records.names(i),false,finalStage,b)=>
              need(consumer==null,"CONSUMER");consumer=x
            case _=>()
          };j+=1
        }
        need(driver!=null,"DRIVER");need(consumer!=null,"CONSUMER")
        val reg=records.get(i);val c=clock(reg,b);val rhs=exactReference(driver.expr)
        need(b.equal(rhs.name,c.name)&&(rhs.tpe eq c.tpe)&&(rhs.kind eq c.kind)&&(rhs.flow eq c.flow),"DRIVER")
        need(checked.same(reg.info,driver.info),"INFO")
        consumer match{case p:Print=>printText(p,b);need(checked.same(reg.info,p.info),"INFO")
          case p:Stop=>need(checked.same(reg.info,p.info),"INFO");case _=>fail("CONSUMER")}
        consumers(i)=consumer;i+=1
      }
    }
    def anchor(s:Statement,moduleId:Int):Unit={
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
          if(same){need(anchors(id)==0,"ANCHOR");anchors(id)=1};id=records.clockNext(id)
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
    need(105381888L<=128L*1024*1024,"BOUND")
    private val b=new Budget
    private var step="CENSUS";private var status="UNAVAILABLE";private var reason="NOT_RUN"
    private var active=true;private var complete=false;private var records:Records=null
    private var walk:Walk=null;private var checked:Checked=null
    private var created=0;private var p52=0;private var p53=0;private var p54=0
    private var count=0;private var lost=0;private var changed=0
    private def guard(body: =>Unit):Unit=if(active){try body catch{
      case e:Abort=>status=if(e.bounded)"TRUNCATED"else"UNAVAILABLE";reason=e.reason;active=false;release()
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
        need(uses.anchors(i)==1,"ANCHOR");i+=1}
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
        if(finalStage)uses.scan(s,mid)
      },noModule,noModule)
      var i=0;while(i<records.count){need(records.seen(i),"COUNT");i+=1}
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
    def release():Unit={if(records!=null)records.clearSnapshot();records=null
      if(walk!=null)walk.clear();walk=null;checked=null}
  }
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
    locally {val b=new Budget;b.scanExpr=(1L<<23)-1;b.charge(C.Expr)
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
}

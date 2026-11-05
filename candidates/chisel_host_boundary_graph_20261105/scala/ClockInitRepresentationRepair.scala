package chiseltest.simulator

import firrtl2.{AnnotationSeq,NodeKind,PortKind,SourceFlow}
import firrtl2.ir._
import firrtl2.annotations._

/** Prepared-AST-only, fail-closed initializer representation correction.
  * No lowering, evaluation, external output, annotation updates or state changes.
  */
object ClockInitRepresentationRepair {
  final case class Result(circuit:Circuit,corrected:Int)
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

  def apply(before:Circuit,prepared:Circuit,annotations:AnnotationSeq,expected:Int):Result={
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
    Result(result,changedRegisters)
  }
}

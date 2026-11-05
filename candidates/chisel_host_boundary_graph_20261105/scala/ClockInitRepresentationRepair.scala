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
  private def fail(code:String):Nothing=throw new IllegalArgumentException(code)
  private def need(p:Boolean,code:String):Unit=if(!p)fail(code)
  private final class Budget {
    private var n=0
    def tick():Unit={n+=1;need(n<=5000000,"BOUND")}
    def name(s:String):Unit=need(s!=null && s.nonEmpty && s.length<=4096,"BOUND")
  }
  private def boundedType(t:Type,b:Budget):Unit={
    var stack=List((t,0));var count=0
    while(stack.nonEmpty){
      val (x,d)=stack.head;stack=stack.tail;b.tick();count+=1
      need(d<=64 && count<=4096,"BOUND")
      x match {
        case VectorType(a,n)=>need(n>=0,"TYPE");stack=(a,d+1)::stack
        case BundleType(fs)=>need(fs.size<=4096,"BOUND");fs.foreach{f=>b.name(f.name);stack=(f.tpe,d+1)::stack}
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
      need(d<=16 && count<=256,"BOUND")
      x match {
        case NoInfo=>()
        case FileInfo(s)=>need(s.length<=4096,"BOUND");if(s.nonEmpty)present=true
        case MultiInfo(xs)=>need(xs.size<=64,"BOUND");xs.foreach(i=>stack=(i,d+1)::stack)
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
  private final case class Index(module:DefModule,names:Set[String],ports:Map[String,Port],statements:Vector[Statement])
  private def index(c:Circuit,b:Budget):Map[String,Index]={
    b.name(c.main);need(c.modules.size<=4096,"BOUND")
    val out=scala.collection.mutable.HashMap.empty[String,Index]
    c.modules.foreach{m=>
      b.tick();b.name(m.name);need(!out.contains(m.name),"DUPLICATE")
      val names=scala.collection.mutable.HashSet.empty[String]
      val ports=scala.collection.mutable.HashMap.empty[String,Port]
      need(m.ports.size<=250000,"BOUND")
      m.ports.foreach{p=>b.tick();b.name(p.name);need(names.add(p.name),"DUPLICATE");ports(p.name)=p}
      val ss=Vector.newBuilder[Statement]
      m match {
        case mm:Module=>
          var stack=List((mm.body,0))
          while(stack.nonEmpty){
            val (s,d)=stack.head;stack=stack.tail;b.tick();need(d<=256,"BOUND");ss+=s
            s match {
              // Unnamed instrumentation carries no referenceable symbol. Keep
              // its statement for anchor matching; never excuse empty state names.
              case p:Print if p.name.isEmpty=>()
              case p:Stop if p.name.isEmpty=>()
              case p:Verification if p.name.isEmpty=>()
              case decl:IsDeclaration=>b.name(decl.name);need(names.add(decl.name),"DUPLICATE")
              case _=>()
            }
            need(names.size<=250000,"BOUND")
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
      need(p.string.string.length<=4096,"BOUND")
      clockRef(p.clk).filter(_=>checkedInfo(p.info,b)).map(c=>AnchorKey(module,true,c.name,p.info,p.string.string,0))
    case p:Stop=>clockRef(p.clk).filter(_=>checkedInfo(p.info,b)).map(c=>AnchorKey(module,false,c.name,p.info,"",p.ret))
    case _=>None
  }


  private def checkAnnotations(as:AnnotationSeq,selected:Set[(String,String)],circuit:String,b:Budget):Unit={
    need(as.size<=100000,"BOUND")
    def target(t:Target):Unit={
      b.tick()
      t match {
        case r:ReferenceTarget=>
          b.name(r.circuit);b.name(r.module);b.name(r.ref)
          need(r.path.size<=64 && r.component.size<=64,"BOUND")
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
        need(x.targets.size<=1024,"BOUND")
        x.targets.foreach{xs=>need(xs.size<=1024,"BOUND");xs.foreach(target)}
      case _:NoTargetAnnotation=>()
      case _=>fail("ANNOTATION_SHAPE")
    }}
  }

  def apply(before:Circuit,prepared:Circuit,annotations:AnnotationSeq,expected:Int):Result={
    need(expected>0 && expected<=1024,"COUNT")
    val b=new Budget
    need(before.main==prepared.main,"STRUCTURE")
    val old=index(before,b);val fresh=index(prepared,b)
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
    checkAnnotations(annotations,keys,prepared.main,b)
    val uses=scala.collection.mutable.HashMap.empty[(String,String),Vector[Use]]
    keys.foreach(k=>uses(k)=Vector.empty)
    // Count every Reference occurrence through every expression, including unused
    // branches, connection sinks, declaration fields, aliases and nested accesses.
    fresh.foreach{case(module,idx)=>idx.statements.foreach{s=>
      s.foreachExpr{root=>
        var stack=List((root,0))
        while(stack.nonEmpty){
          val (e,d)=stack.head;stack=stack.tail;b.tick();need(d<=256,"BOUND")
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
    val anchorCounts=scala.collection.mutable.HashMap.empty[AnchorKey,Int]
    old.foreach{case(module,idx)=>idx.statements.foreach{s=>
      b.tick();anchorKey(module,s,b).foreach{k=>anchorCounts(k)=anchorCounts.getOrElse(k,0)+1}
    }}
    selected.foreach{c=>
      val found=uses((c.module,c.reg.name))
      need(found.size==2,"REFERENCES")
      val drivers=found.collect{case Use(x:Connect,root,true) if (root eq x.loc) && delayedRef(x.loc,c.reg.name)=>x}
      need(drivers.size==1,"DRIVER")
      val driver=drivers.head
      need(driver.expr==c.clock,"DRIVER")
      need(sameInfo(c.reg.info,driver.info,b),"INFO")
      val consumers=found.collect{
        case Use(x:Print,root,true) if (root eq x.clk) && delayedRef(x.clk,c.reg.name)=>x:Statement
        case Use(x:Stop,root,true) if (root eq x.clk) && delayedRef(x.clk,c.reg.name)=>x:Statement
      }
      need(consumers.size==1,"CONSUMER")
      val consumer=consumers.head
      val key=consumer match {
        case p:Print=>
          need(sameInfo(c.reg.info,p.info,b),"INFO");need(p.string.string.length<=4096,"BOUND")
          AnchorKey(c.module,true,c.clock.name,p.info,p.string.string,0)
        case p:Stop=>need(sameInfo(c.reg.info,p.info,b),"INFO");AnchorKey(c.module,false,c.clock.name,p.info,"",p.ret)
        case _=>fail("CONSUMER")
      }
      need(anchorCounts.getOrElse(key,0)==1,"ANCHOR")
    }
    // Only after all checks: rebuild changed ancestors, reusing every other node.
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

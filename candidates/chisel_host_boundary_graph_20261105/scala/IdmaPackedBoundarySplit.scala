package heteronpu.continuous.model

import firrtl2.ir._
import firrtl2.{PrimOps,PortKind,InstanceKind,SourceFlow,SinkFlow,UnknownFlow}
import scala.collection.mutable

/** ISOLATED, NOT COMPILED OR QUALIFIED. Apply only to official low FIRRTL,
  * after the independently pinned IdmaFieldSplitTransform, before PrepareAst.
  * Pure simulation representation: no edge deletion, state or timing changes.
  * Every new input is constrained by a same-cycle projection of the original
  * input driver. The extended wrapper is NOT interchangeable in isolation.
  */
object IdmaPackedBoundarySplit {
  private val prefix="__sim_idma_field__"
  private def fieldName(f:IdmaSplitLayout.Field):String=prefix+f.name
  private def width(e:Expression):Int=width(e.tpe)
  private def width(t:Type):Int=t match {
    case UIntType(IntWidth(w)) if w>0 && w<=4096 => w.toInt
    case _=>throw new IllegalArgumentException("known bounded UInt required")
  }
  private def uint(w:Int):Type=UIntType(IntWidth(w))
  private def ref(n:String,t:Type,flow:firrtl2.Flow=SourceFlow):Expression=Reference(n,t,PortKind,flow)
  private def cat(xs:Seq[Expression]):Expression={
    require(xs.nonEmpty)
    xs.reduceLeft((a,b)=>DoPrim(PrimOps.Cat,Seq(a,b),Seq.empty,uint(width(a)+width(b))))
  }
  private def bits(e:Expression,h:Int,l:Int):Expression={
    require(l>=0 && h>=l && h<width(e))
    if(l==0 && h==width(e)-1)e else DoPrim(PrimOps.Bits,Seq(e),Seq(BigInt(h),BigInt(l)),uint(h-l+1))
  }
  private def statements(s:Statement):Vector[Statement]=s match {
    case Block(ss)=>ss.toVector.flatMap(statements)
    case EmptyStmt=>Vector.empty
    case x=>Vector(x)
  }
  private def bundle(ports:Seq[Port]):Type=BundleType(ports.map(p=>Field(p.name,if(p.direction==Input)Flip else Default,p.tpe)))
  private def port(instance:String,tpe:Type,name:String,t:Type,flow:firrtl2.Flow):Expression=
    SubField(Reference(instance,tpe,InstanceKind,SourceFlow),name,t,flow)
  private def target(e:Expression):Option[(String,String)]=e match {
    case SubField(Reference(n,_,_,_),p,_,_)=>Some(n->p)
    case _=>None
  }

  /** Single-driver, exact-width aliases only. Register next state is never an
    * alias. Low FIRRTL is mandatory; conditional statements are rejected.
    */
  private def drivers(m:Module):Map[String,Vector[Expression]]={
    val out=mutable.Map.empty[String,Vector[Expression]]
    val ss=statements(m.body)
    require(!ss.exists(_.isInstanceOf[Conditionally]),"must be unconditional low FIRRTL")
    val registers=ss.collect{case r:DefRegister=>r.name}.toSet
    val invalid=ss.collect{case IsInvalid(_,Reference(n,_,_,_))=>n}.toSet
    def add(n:String,e:Expression):Unit=out(n)=out.getOrElse(n,Vector.empty):+e
    ss.foreach {
      case DefNode(_,n,e)=>add(n,e)
      case Connect(_,Reference(n,_,_,_),e) if !registers(n)=>add(n,e)
      case _=>()
    }
    invalid.foreach(n=>out(n)=Vector.empty)
    out.toMap
  }

  /** Exact unsigned bit projection. Generic primitives retain all original
    * operands and operators; only their aliases are expanded. Partial results
    * of arithmetic are sliced AFTER the operation, never operand-wise.
    */
  private final class Project(m:Module,packed:Map[(String,String),Expression]) {
    private val ds=drivers(m)
    // Identity keys avoid recursively hashing a shared or deeply nested AST
    // before the projection/expanded-occurrence bounds can run.
    private val ids=new java.util.IdentityHashMap[Expression,java.lang.Integer]()
    private def identity(e:Expression):Int={
      val old=ids.get(e)
      if(old!=null)old.intValue else {
        require(ids.size<100000,"bounded expression identities")
        val id=ids.size;ids.put(e,java.lang.Integer.valueOf(id));id
      }
    }
    private val active=mutable.Set.empty[(Int,Int,Int)]
    private val memo=mutable.Map.empty[(Int,Int,Int),Expression]
    private val sizes=new java.util.IdentityHashMap[Expression,(Long,Int)]()
    private var work=0
    def used:Int=work
    // Count expanded occurrences, not just unique objects: downstream FIRRTL
    // visitors may revisit a shared DAG through every parent edge.
    def expanded(e:Expression):Long=measure(e,0)._1
    private def measure(e:Expression,stack:Int):(Long,Int)={
      require(stack<128,"bounded expression recursion")
      val previous=sizes.get(e)
      if(previous!=null){require(stack+previous._2<=128,"bounded expression recursion");previous} else {
        var count=1L;var depth=1
        e.foreachExpr{x=>val(n,d)=measure(x,stack+1);count=math.min(16385L,count+n);depth=math.max(depth,d+1)}
        require(count<=16384 && depth<=128,"bounded expanded expression")
        val result=(count,depth);sizes.put(e,result);result
      }
    }
    def apply(e:Expression,h:Int,l:Int):Expression={
      require(l>=0 && h>=l && h<width(e),"projection range")
      val key=(identity(e),h,l)
      memo.getOrElseUpdate(key,{
        work+=1;require(work<=100000 && active.size<256,"bounded alias projection")
        require(!active(key),"alias cycle is not a repairable packed view")
        active+=key
        val out:Expression=try {
          target(e).flatMap(packed.get) match {
            case Some(x)=>require(width(x)==width(e));apply(x,h,l)
            case None=>e match {
              case Reference(n,_,_,_) if ds.contains(n)=>
                require(ds(n).size==1,"one non-invalid driver required")
                val x=ds(n).head;require(width(x)==width(e),"implicit coercion forbidden")
                apply(x,h,l)
              case UIntLiteral(v,_)=>UIntLiteral((v>>l)&((BigInt(1)<<(h-l+1))-1),IntWidth(h-l+1))
              case DoPrim(PrimOps.Bits,Seq(x),Seq(a,b),_)=>
                require(a-b+1==width(e));apply(x,h+b.toInt,l+b.toInt)
              case DoPrim(PrimOps.Cat,Seq(a,b),Seq(),_)=>
                val n=width(b);require(width(a)+n==width(e))
                if(h<n)apply(b,h,l)
                else if(l>=n)apply(a,h-n,l-n)
                else cat(Seq(apply(a,h-n,0),apply(b,n-1,l)))
              case Mux(c,a,b,_)=>
                // Low FIRRTL permits unequal UInt arms before PadWidths.
                // Reject signed/unknown widths and require the exact max-width result.
                require(width(c)==1 && math.max(width(a),width(b))==width(e),"exact mux widths")
                def unsignedArm(x:Expression):Expression={
                  val n=width(x)
                  if(h<n)apply(x,h,l)
                  else if(l>=n)UIntLiteral(0,IntWidth(h-l+1))
                  else cat(Seq(UIntLiteral(0,IntWidth(h-n+1)),apply(x,n-1,l)))
                }
                Mux(apply(c,0,0),unsignedArm(a),unsignedArm(b),uint(h-l+1))
              case p:DoPrim=>
                // Keep shifts, arithmetic, comparison and casts intact.
                // Unsupported signed/unknown operands fail width validation.
                val q=p.copy(args=p.args.map(x=>apply(x,width(x)-1,0)))
                bits(q,h,l)
              case _:Reference | _:SubField | _:SubIndex=>bits(e,h,l)
              case _=>throw new IllegalArgumentException("unsupported projected expression")
            }
          }
        }finally{active-=key}
        require(width(out)==h-l+1);expanded(out);out
      })
    }
  }

  /** Check every retained caller expression, including sliced-away operands,
    * before fixStmt/fixExpr or any other recursive rewrite sees the old body.
    * Identity-keyed iterative traversal never structurally hashes input AST. */
  private def preflightCaller(m:Module):Unit={
    val sizes=new java.util.IdentityHashMap[Expression,(Long,Int)]()
    val active=new java.util.IdentityHashMap[Expression,java.lang.Boolean]()
    var rootsTotal=0L;var statementsSeen=0
    val pending=mutable.ArrayBuffer[Statement](m.body)
    def check(root:Expression):Unit={
      val stack=mutable.ArrayBuffer[(Expression,Boolean,Int)]((root,false,0))
      while(stack.nonEmpty){
        val (e,exit,level)=stack.remove(stack.size-1)
        require(level<128,"bounded caller expression depth")
        if(exit){
          var count=1L;var depth=1
          e.foreachExpr{x=>
            val child=sizes.get(x);require(child!=null,"caller expression postorder")
            count=math.min(16385L,count+child._1);depth=math.max(depth,child._2+1)
          }
          require(count<=16384 && depth<=128,"bounded caller expression expansion")
          sizes.put(e,(count,depth));active.remove(e)
        }else{
          val prior=sizes.get(e)
          if(prior!=null)require(level+prior._2<=128,"bounded caller expression depth")
          else{
            require(!active.containsKey(e),"cyclic expression object")
            require(sizes.size+active.size<1000000,"bounded caller expression identities")
            active.put(e,java.lang.Boolean.TRUE);stack+=((e,true,level))
            var children=0
            e.foreachExpr{x=>
              children+=1;require(children<=16384 && stack.size<1000000,"bounded caller expression children")
              stack+=((x,false,level+1))
            }
          }
        }
      }
      rootsTotal+=sizes.get(root)._1
      require(rootsTotal<=1000000,"bounded total caller expression occurrences")
    }
    while(pending.nonEmpty){
      val s=pending.remove(pending.size-1);statementsSeen+=1
      require(statementsSeen<=1000000,"bounded caller statements")
      s.foreachExpr(check)
      s.foreachStmt{x=>require(pending.size<1000000,"bounded caller statements");pending+=x}
    }
  }

  final case class Result(circuit:Circuit,wrapper:String,callerModules:Vector[String],instances:Int,projectedFields:Int)

  def apply(c:Circuit,wrapperName:String):Result={
    IdmaSplitLayout.checkLayout()
    val mods=c.modules.map(m=>m.name->m).toMap
    require(mods.size==c.modules.size,"unique modules")
    val wrapper=mods(wrapperName).asInstanceOf[Module]
    val leaf=mods(IdmaSplitLayout.modelName).asInstanceOf[ExtModule]
    require(leaf.ports==IdmaSplitLayout.ports,"exact split leaf ABI including order")
    val oldExpected=IdmaSplitLayout.controlPorts.map(p=>p.name->(p.direction,p.tpe)).toMap ++
      IdmaSplitLayout.busWidths.map{case(n,w)=>n->((if(n.endsWith("_i"))Input else Output),uint(w))}
    require(wrapper.ports.size==oldExpected.size && wrapper.ports.map(p=>p.name->(p.direction,p.tpe)).toMap==oldExpected,"exact original packed wrapper ABI")
    val ws=statements(wrapper.body)
    require(ws.forall {
      case _:DefInstance | _:DefNode | _:DefWire | _:Connect=>true
      case _=>false
    },"transparent generated wrapper only")
    val wi=ws.collect{case i:DefInstance=>i}
    require(wi.size==1 && wi.head.name=="model" && wi.head.module==leaf.name,"unchanged split model binding")
    val modelType=bundle(leaf.ports)
    val check=new Project(wrapper,Map.empty)
    val connections=ws.collect{case Connect(_,lhs,rhs)=>lhs.serialize->rhs}.groupBy(_._1)
    require(connections.forall(_._2.size==1),"wrapper unique drivers")
    def driver(n:String):Expression=connections.getOrElse(n,Vector.empty).headOption.map(_._2).getOrElse(throw new IllegalArgumentException("missing wrapper driver"))
    for(p<-IdmaSplitLayout.controlPorts){
      val lhs=if(p.direction==Input)"model."+p.name else p.name
      val expected=if(p.direction==Input)p.name else "model."+p.name
      require(driver(lhs).serialize==expected,"unchanged direct control passthrough")
    }
    // Verify every original input field is exactly the pinned packed slice.
    for(f<-IdmaSplitLayout.fields if f.direction==Input){
      val actual=check(driver("model."+f.name),f.width-1,0)
      val expected=bits(ref(f.bus,uint(IdmaSplitLayout.busWidths(f.bus))),f.lsb+f.width-1,f.lsb)
      require(actual.serialize==expected.serialize,"original wrapper input projection")
    }
    // Verify original packed outputs reproduce every model field bit.
    for(f<-IdmaSplitLayout.fields if f.direction==Output){
      val actual=check(driver(f.bus),f.lsb+f.width-1,f.lsb)
      val expected=port("model",modelType,f.name,uint(f.width),SourceFlow)
      require(actual.serialize==expected.serialize,"original wrapper output packing")
    }
    val additions=IdmaSplitLayout.fields.map(f=>Port(NoInfo,fieldName(f),f.direction,uint(f.width)))
    val namespace=wrapper.ports.map(_.name).toSet++ws.collect{
      case x:DefNode=>x.name
      case x:DefWire=>x.name
      case x:DefInstance=>x.name
    }
    require((namespace intersect additions.map(_.name).toSet).isEmpty,"fresh private field namespace")
    val extended=wrapper.ports++additions;val wrapperType=bundle(extended)
    val fieldsByName=IdmaSplitLayout.fields.map(f=>f.name->f).toMap
    val newBody=ws.map {
      case x@Connect(_,lhs,_) if target(lhs).exists{case(n,p)=>n=="model" && fieldsByName.get(p).exists(_.direction==Input)}=>
        val f=fieldsByName(target(lhs).get._2);x.copy(expr=ref(fieldName(f),uint(f.width)))
      case x=>x
    }++IdmaSplitLayout.fields.filter(_.direction==Output).map(f=>
      Connect(NoInfo,ref(fieldName(f),uint(f.width),SinkFlow),port("model",modelType,f.name,uint(f.width),SourceFlow)))
    val newWrapper=wrapper.copy(ports=extended,body=Block(newBody))
    var instanceCount=0;var fieldCount=0;val callers=Vector.newBuilder[String]
    val newModules=c.modules.map {
      case m if m.name==wrapperName=>newWrapper
      case m:Module=>
        val ss=statements(m.body);val instances=ss.collect{case i:DefInstance if i.module==wrapperName=>i}
        if(instances.isEmpty)m else {
          preflightCaller(m)
          callers+=m.name;instanceCount+=instances.size
          val names=instances.map(_.name).toSet
          require(names.size==instances.size && !names("model"),"distinct caller instances")
          val packed=instances.flatMap{i=>
            IdmaSplitLayout.busWidths.keys.filter(_.endsWith("_o")).map{b=>
              val fs=IdmaSplitLayout.fields.filter(_.bus==b).sortBy(f=> -f.lsb)
              (i.name,b)->cat(fs.map(f=>port(i.name,wrapperType,fieldName(f),uint(f.width),SourceFlow)))
            }
          }.toMap
          val project=new Project(m,packed)
          var expandedTotal=0L
          val newConnections=instances.flatMap{i=>
            IdmaSplitLayout.fields.filter(_.direction==Input).map{f=>
              val cs=ss.collect{case Connect(_,lhs,rhs) if target(lhs).contains(i.name->f.bus)=>rhs}
              require(cs.size==1,"each caller has exactly one original packed input driver")
              require(width(cs.head)==IdmaSplitLayout.busWidths(f.bus),"packed input driver width")
              val value=project(cs.head,f.lsb+f.width-1,f.lsb)
              expandedTotal+=project.expanded(value)
              require(expandedTotal<=65536,"bounded total expanded field expressions")
              // No old packed request output is permitted anywhere in a new
              // field cone. A true whole-bus use must retain every field.
              def rejectOld(e:Expression):Unit={require(!target(e).exists(packed.contains),"unresolved packed boundary");e.foreachExpr(rejectOld)}
              rejectOld(value);fieldCount+=1
              Connect(NoInfo,port(i.name,wrapperType,fieldName(f),uint(f.width),SinkFlow),value)
            }
          }
          def fixExpr(e:Expression):Expression=e.mapExpr(fixExpr) match {
            case r@Reference(n,_,_,_) if names(n)=>r.copy(tpe=wrapperType)
            case x=>x
          }
          def fixStmt(s:Statement):Statement=s.mapStmt(fixStmt).mapExpr(fixExpr) match {
            case i:DefInstance if names(i.name)=>i.copy(tpe=wrapperType)
            case x=>x
          }
          m.copy(body=Block(Seq(fixStmt(m.body))++newConnections.map(fixStmt)))
        }
      case x=>x
    }
    require(instanceCount==1 && fieldCount==IdmaSplitLayout.fields.count(_.direction==Input),"one original iDMA boundary only")
    Result(c.copy(modules=newModules),wrapperName,callers.result(),instanceCount,fieldCount)
  }
}

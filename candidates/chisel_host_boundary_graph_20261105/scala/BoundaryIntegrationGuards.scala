package heteronpu.continuous.model

import firrtl2.ir._
import firrtl2.{PortKind,SourceFlow}

/** Read-only admission/noninterference checks for the actual original Host.
  * No simulation or alternative oracle. Projection semantics remain those of
  * the separately pinned/qualified transform and its conditional bit argument.
  */
object BoundaryIntegrationGuards {
  final case class Topology(wrapper:String,caller:String,instance:String,leafPath:String)
  private val prefix="__sim_idma_field__"
  private def statements(root:Statement):Vector[Statement]={
    val out=Vector.newBuilder[Statement];var pending=List(root);var visited=0
    while(pending.nonEmpty){
      val s=pending.head;pending=pending.tail;visited+=1
      require(visited<=1000000,"bounded integration statements")
      s match {case Block(xs)=>pending=xs.toList:::pending;case EmptyStmt=>();case x=>out+=x}
    }
    out.result()
  }
  private def modules(c:Circuit):Map[String,DefModule]={
    val ms=c.modules.map(m=>m.name->m).toMap;require(ms.size==c.modules.size);ms
  }
  def topology(c:Circuit,wrapperName:String,bindings:Map[String,String]):Topology={
    require(bindings.size==17,"same seventeen leaf paths")
    val ms=modules(c)
    val leafPaths=bindings.toVector.filter(_._2==IdmaSplitLayout.modelName)
    require(leafPaths.size==1,"one actual iDMA hierarchy path")
    val path=leafPaths.head._1;val parts=path.split("\\.").toVector
    require(parts.size>=2 && parts.size<=64 && parts.forall(_.nonEmpty),"bounded exact hierarchy path")
    var current=ms(c.main);var caller="";var instance=""
    parts.zipWithIndex.foreach{case(segment,index)=>
      val m=current.asInstanceOf[Module]
      val matches=statements(m.body).collect{case i:DefInstance if i.name==segment=>i}
      require(matches.size==1,"unique exact instance segment")
      if(index==parts.size-2){
        caller=m.name;instance=segment
        require(matches.head.module==wrapperName,"original high wrapper module identity")
      }
      if(index==parts.size-1){
        require(m.name==wrapperName && segment=="model","exact generated wrapper/leaf binding")
      }
      current=ms(matches.head.module)
    }
    val leaf=current.asInstanceOf[ExtModule]
    require(leaf.defname==IdmaSplitLayout.modelName && leaf.ports==IdmaSplitLayout.ports,"unchanged split leaf ABI")
    require(caller.nonEmpty && instance.nonEmpty && ms(wrapperName).isInstanceOf[Module])
    Topology(wrapperName,caller,instance,path)
  }
  def checkTypesAndFlows(c:Circuit):Unit={
    // These read-only passes return the same Circuit; no compiler rescheduling
    // or whole-Host serialization is needed for this non-mutation postcondition.
    require(firrtl2.passes.CheckTypes.run(c) eq c,"CheckTypes returned another circuit")
    require(firrtl2.passes.CheckFlows.run(c) eq c,"CheckFlows returned another circuit")
  }
  private def sameOriginalStatement(a:Statement,b:Statement,instance:String,oldType:Type,newType:Type):Unit={
    require(a.getClass==b.getClass && a.serialize==b.serialize,"unchanged original statement/state/driver")
    (a,b) match {
      case (x:DefInstance,y:DefInstance) if x.name==instance=>
        require(x.tpe==oldType && y.tpe==newType,"only admitted instance bundle extension")
      case (x:DefInstance,y:DefInstance)=>require(x.tpe==y.tpe,"other instance type unchanged")
      case _=>()
    }
    def roots(s:Statement):Vector[Expression]={val out=Vector.newBuilder[Expression];s.foreachExpr(e=>out+=e);out.result()}
    val left=roots(a);val right=roots(b);require(left.size==right.size)
    var pending=left.zip(right).toList;var count=0
    while(pending.nonEmpty){
      val (x,y)=pending.head;pending=pending.tail;count+=1;require(count<=1000000,"bounded original expression metadata check")
      require(x.getClass==y.getClass,"unchanged original expression kind")
      (x,y) match {
        case (u:Reference,v:Reference) if u.name==instance=>
          require(u.tpe==oldType && v.tpe==newType && u.kind==v.kind && u.flow==v.flow,"only admitted instance reference type changes")
        case _=>require(x.tpe==y.tpe,"unchanged original expression type")
      }
      val ax=Vector.newBuilder[Expression];val ay=Vector.newBuilder[Expression]
      x.foreachExpr(e=>ax+=e);y.foreachExpr(e=>ay+=e)
      val xs=ax.result();val ys=ay.result();require(xs.size==ys.size);pending=xs.zip(ys).toList:::pending
    }
  }
  def verify(before:Circuit,result:IdmaPackedBoundarySplit.Result,t:Topology,bindings:Map[String,String]):Unit={
    val after=result.circuit;val a=modules(before);val b=modules(after)
    require(before.main==after.main && before.info==after.info && before.modules.map(_.name)==after.modules.map(_.name),"same main/module order/info")
    require(result.wrapper==t.wrapper && result.instances==1 && result.projectedFields==26 && result.callerModules==Vector(t.caller),"exact original boundary caller")
    require(topology(after,t.wrapper,bindings)==t,"unchanged actual boundary hierarchy path")
    before.modules.foreach{m=>
      if(m.name!=t.wrapper && m.name!=t.caller)require(m eq b(m.name),"unaffected module object unchanged")
    }
    val ow=a(t.wrapper).asInstanceOf[Module];val nw=b(t.wrapper).asInstanceOf[Module]
    val inputs=IdmaSplitLayout.fields.filter(_.direction==Input);val outputs=IdmaSplitLayout.fields.filter(_.direction==Output)
    require(inputs.size==26 && outputs.size==64 && inputs.map(_.width).sum==1064 && outputs.map(_.width).sum==1570,"all original boundary bits")
    val additions=IdmaSplitLayout.fields.map(f=>Port(NoInfo,prefix+f.name,f.direction,UIntType(IntWidth(f.width))))
    require(ow.ports.size==15 && nw.ports==ow.ports++additions && nw.ports.size==105 && nw.info==ow.info,"only ninety exact private field ports")
    require(nw.ports.map(_.name).distinct.size==105,"unique extended wrapper ports")
    val os=statements(ow.body);val ns=statements(nw.body)
    require(ns.size==os.size+outputs.size,"only private output pass-through additions")
    val byName=inputs.map(f=>f.name->f).toMap
    os.zip(ns).foreach{case(x,y)=>
      x match {
        case c@Connect(_,SubField(Reference("model",_,_,_),name,_,_),_) if byName.contains(name)=>
          val f=byName(name)
          val expected=c.copy(expr=Reference(prefix+name,UIntType(IntWidth(f.width)),PortKind,SourceFlow))
          require(y==expected,"only exact split model input rewiring")
        case _=>require(x eq y,"all other wrapper statements unchanged")
      }
    }
    ns.drop(os.size).zip(outputs).foreach{case(s,f)=>
      s match {
        case Connect(NoInfo,Reference(n,UIntType(IntWidth(w)),_,_),SubField(Reference("model",_,_,_),p,UIntType(IntWidth(v)),_))=>
          require(n==prefix+f.name && p==f.name && w==f.width && v==f.width,"exact same-cycle private output field")
        case _=>throw new IllegalArgumentException("private outputs are direct field connections")
      }
    }
    val oc=a(t.caller).asInstanceOf[Module];val nc=b(t.caller).asInstanceOf[Module]
    require(oc.ports==nc.ports && oc.info==nc.info,"unchanged caller interface/info")
    val oldType=BundleType(ow.ports.map(p=>Field(p.name,if(p.direction==Input)Flip else Default,p.tpe)))
    val newType=BundleType(nw.ports.map(p=>Field(p.name,if(p.direction==Input)Flip else Default,p.tpe)))
    val original=statements(oc.body);val changed=statements(nc.body)
    require(changed.size==original.size+26,"only twenty-six new caller field connects")
    original.zip(changed).foreach{case(x,y)=>sameOriginalStatement(x,y,t.instance,oldType,newType)}
    changed.drop(original.size).zip(inputs).foreach{case(s,f)=>
      s match {
        case Connect(NoInfo,SubField(Reference(n,ty,_,_),p,UIntType(IntWidth(w)),_),rhs)=>
          require(n==t.instance && ty==newType && p==prefix+f.name && w==f.width && rhs.tpe==UIntType(IntWidth(f.width)),"unique exact-width same-cycle input projection")
        case _=>throw new IllegalArgumentException("new field input must be a connection, never state")
      }
    }
    require(new StructuralMetadataFactory(after,seed=true).bindings==bindings,"all original seventeen leaf paths/ABIs unchanged")
  }
}

package chiseltest.simulator

import firrtl2.{CircuitState,Parser,WireKind,SourceFlow,SinkFlow}
import firrtl2.ir._
import firrtl2.stage.FirrtlCircuitAnnotation
import firrtl2.options.TargetDirAnnotation
import heteronpu.continuous.model.{IdmaFieldSplitTransform,IdmaPackedBoundarySplit,IdmaSplitLayout}
import java.io.{OutputStream,PrintStream}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Path,Paths}
import java.security.MessageDigest
import treadle2.{ScalaBlackBox,ScalaBlackBoxFactory,TreadleCircuitStateAnnotation}
import treadle2.executable.{SymbolTable,Transition}
import treadle2.stage.phases.{GetFirrtlAst,PrepareAst,SetImplicitOutputInfo}

/** ISOLATED FUTURE TEST, NOT COMPILED/RUN. No engine, native or numerical DUT.
  * Run identical class in separate pinned official/cached processes and compare
  * every emitted outcome/digest. Small-fixture agreement is not Host acceptance.
  */
object BoundarySplitStructuralFixture {
  private def hash(s:String):String=sha(s.getBytes(UTF_8))
  private def sha(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  private def typ(t:Type):String=t.serialize
  // Interpolate numeric width, never Width.toString (IntWidth(n) is not FIRRTL).
  private def zeroUInt(t:Type):String=t match {
    case UIntType(IntWidth(w)) if w>0=>s"UInt<$w>(0)"
    case _=>throw new IllegalArgumentException("known positive UInt control width")
  }
  private def cat(xs:Seq[String]):String=xs.reduceLeft((a,b)=>s"cat($a, $b)")
  private val original="idma_backend_rw_axi_flat_wrap"
  private val unsignedMuxModes=Set("mux_narrow_true","mux_narrow_false","mux_boundary_cycle","mux_boundary_registered")
  private def boundaryRegisterMode(mode:String):Boolean=Set("boundary_registered","mux_boundary_registered")(mode)
  private def source(control:String):String={
    val ins=IdmaSplitLayout.fields.filter(_.direction==Input)
    val inputPorts=ins.map(f=>s"    input in_${f.name} : UInt<${f.width}>").mkString("\n")
    val controls=IdmaSplitLayout.controlPorts.filter(_.direction==Input).map{p=>
      val rhs=if(p.name=="clk_i")"clock" else if(p.name=="rst_ni")"UInt<1>(1)" else zeroUInt(p.tpe)
      s"    b.${p.name} <= $rhs"
    }.mkString("\n")
    val packed=IdmaSplitLayout.busWidths.keys.filter(_.endsWith("_i")).toVector.sorted.map{bus=>
      val parts=ins.filter(_.bus==bus).sortBy(f=> -f.lsb).map{f=>
        // Base r_id is selected from ar_id; dedicated modes add real feedback.
        // Whole-symbol packed dependencies manufacture the forbidden path.
        if(f.name=="axi_read_rsp_i__r_last" && Set("boundary_cycle","mux_boundary_cycle")(control)){
          "bits(b.axi_read_req_o, 0, 0)"
        }else if(f.name=="axi_read_rsp_i__r_last" && boundaryRegisterMode(control)){
          "q_boundary"
        }else if(control=="arithmetic" && f.name=="axi_read_rsp_i__r_data"){
          "bits(add(in_axi_read_rsp_i__r_data, in_axi_write_rsp_i__r_data), 511, 0)"
        }else if(control=="arithmetic" && f.name=="axi_write_rsp_i__r_data"){
          "bits(sub(in_axi_read_rsp_i__r_data, in_axi_write_rsp_i__r_data), 511, 0)"
        }else if(control=="arithmetic" && f.name=="axi_write_rsp_i__b_id"){
          "bits(dshl(in_axi_write_rsp_i__b_id, in_axi_write_rsp_i__b_resp), 3, 0)"
        }else if(control=="arithmetic" && f.name=="axi_read_rsp_i__b_id"){
          "pad(shr(in_axi_read_rsp_i__b_id, 1), 4)"
        }else if(control=="arithmetic" && f.name=="axi_write_rsp_i__r_last"){
          "lt(in_axi_read_rsp_i__r_data, in_axi_write_rsp_i__r_data)"
        }else if(control=="whole_bus" && f.name=="axi_read_rsp_i__r_id"){
          "pad(orr(b.axi_read_req_o), 4)"
        }else if(f.name=="axi_read_rsp_i__r_id"){
          val ar=IdmaSplitLayout.fields.find(_.name=="axi_read_req_o__ar_id").get
          s"bits(b.axi_read_req_o, ${ar.lsb+ar.width-1}, ${ar.lsb})"
        }else if(f.name=="axi_read_rsp_i__r_resp"){
          val av=IdmaSplitLayout.fields.find(_.name=="axi_read_req_o__ar_valid").get
          s"mux(bits(b.axi_read_req_o, ${av.lsb}, ${av.lsb}), in_${f.name}, UInt<2>(3))"
        }else s"in_${f.name}"
      }
      if(unsignedMuxModes(control) && bus=="axi_read_rsp_i"){
        // Nested unequal arms and exact-width node aliases must survive official low.
        val short12="bits(in_axi_write_rsp_i__r_data, 11, 0)"
        val short20="bits(in_axi_write_rsp_i__r_data, 19, 0)"
        val narrowFirst=control!="mux_narrow_false"
        val short=if(narrowFirst)s"mux(in_axi_write_rsp_i__b_valid, $short12, $short20)"else
          s"mux(in_axi_write_rsp_i__b_valid, $short20, $short12)"
        val outer=if(narrowFirst)"mux(in_axi_read_rsp_i__b_valid, __fixture_mux_short, __fixture_mux_wide)"else
          "mux(in_axi_read_rsp_i__b_valid, __fixture_mux_wide, __fixture_mux_short)"
        s"    node __fixture_mux_short = $short\n    node __fixture_mux_wide = ${cat(parts)}\n    b.$bus <= $outer"
      }else s"    b.$bus <= ${cat(parts)}"
    }.mkString("\n")
    // Packed input expressions may read this register, so declare it first.
    val declarations=if(boundaryRegisterMode(control))"    reg q_boundary : UInt<1>, clock\n"else ""
    val extra=control match {
      case "base" | "arithmetic" | "whole_bus" | "boundary_cycle" | "mux_narrow_true" | "mux_narrow_false" | "mux_boundary_cycle"=>"    fixture_sentinel <= bits(b.axi_read_req_o, 0, 0)\n"
      case "boundary_registered" | "mux_boundary_registered"=>"    q_boundary <= bits(b.axi_read_req_o, 0, 0)\n    fixture_sentinel <= q_boundary\n"
      // Normal lowering/preparation must never receive intentional local cycles.
      case "true_cycle" | "self_loop"=>"    fixture_sentinel <= UInt<1>(0)\n"
      case "registered"=>"    reg q : UInt<1>, clock\n    q <= not(q)\n    fixture_sentinel <= q\n"
      case _=>throw new IllegalArgumentException("fixture mode")
    }
    val extPorts=(IdmaSplitLayout.controlPorts++IdmaSplitLayout.busWidths.toVector.sortBy(_._1).map{case(n,w)=>
      Port(NoInfo,n,if(n.endsWith("_i"))Input else Output,UIntType(IntWidth(w)))
    }).map(p=>s"    ${if(p.direction==Input)"input" else "output"} ${p.name} : ${typ(p.tpe)}").mkString("\n")
    s"circuit Top :\n  module Top :\n    input clock : Clock\n    output fixture_sentinel : UInt<1>\n$inputPorts\n    inst b of $original\n$controls\n$declarations$packed\n$extra  extmodule $original :\n$extPorts\n    defname = $original\n"
  }
  private final class Factory extends ScalaBlackBoxFactory {
    var n=0
    override def createInstance(instance:String,kind:String):Option[ScalaBlackBox]={
      require(kind==IdmaSplitLayout.modelName && n==0);n+=1
      Some(add(new ScalaBlackBox {
        val name=instance
        private def never():Nothing=throw new IllegalStateException("structural fixture cannot evaluate")
        override def inputChanged(p:String,v:BigInt):Unit=never()
        override def clockChange(t:Transition,n:String):Unit=never()
        override def getOutput(v:Seq[BigInt],t:Type,n:String):BigInt=never()
        override def getDependencies:Seq[(String,Set[String])]=IdmaSplitLayout.ports.filter(p=>p.direction==Input && p.name!="clk_i" && p.name!="rst_ni").map(p=>p.name->Set("req_ready_o"))
        override def outputDependencies(p:String):Seq[String]=Seq("clk_i","rst_ni")++
          (if(p=="axi_read_req_o__r_ready")Seq("axi_read_rsp_i__r_last") else Seq.empty)
      }))
    }
  }
  private def prepared(c:Circuit,target:Path):Circuit={
    val a=Seq(FirrtlCircuitAnnotation(c),TargetDirAnnotation(target.toString))
    val p=(new PrepareAst).transform(SetImplicitOutputInfo.transform(GetFirrtlAst.transform(a)))
    val states=p.collect{case TreadleCircuitStateAnnotation(s)=>s};require(states.size==1);states.head.circuit
  }
  private def requireUnequalMuxes(c:Circuit,mode:String):Unit={
    if(!unsignedMuxModes(mode))return
    val seen=scala.collection.mutable.Set.empty[(Int,Int,Int)]
    def expr(e:Expression):Unit={
      e match {
        case Mux(_,a,b,UIntType(IntWidth(w)))=>
          (a.tpe,b.tpe) match {
            case (UIntType(IntWidth(wa)),UIntType(IntWidth(wb))) if wa!=wb=>seen+=((wa.toInt,wb.toInt,w.toInt))
            case _=>()
          }
        case _=>()
      }
      e.foreachExpr(expr)
    }
    def stmt(s:Statement):Unit={s.foreachExpr(expr);s.foreachStmt(stmt)}
    c.modules.collect{case m:Module if m.name=="Top"=>m}.foreach(m=>stmt(m.body))
    val wanted=if(mode=="mux_narrow_false")Set((532,20,532),(20,12,20))else Set((20,532,532),(12,20,20))
    require(wanted.subsetOf(seen.toSet),"actual unequal UInt muxes survived official low")
  }
  private def digest(t:SymbolTable):String={
    require(t.size<10000)
    hash(t.symbols.toVector.sortBy(_.name).flatMap{s=>Vector(
      "N|"+s.name+"|"+s.firrtlType.serialize+"|"+s.cardinalNumber,
      "C|"+s.name+"|"+t.childrenOf.getEdges(s).toVector.map(_.name).sorted.mkString(","),
      "P|"+s.name+"|"+t.parentsOf.getEdges(s).toVector.map(_.name).sorted.mkString(","))
    }.mkString("\n"))
  }
  // Independent BigInt interpreter: no use of Project/Bits normalization.
  // This verifies fixture bit equations, not any simulated hardware arithmetic.
  private def valueComparison(before:Circuit,after:Circuit,mode:String):Int={
    def stmts(s:Statement):Vector[Statement]=s match {case Block(xs)=>xs.toVector.flatMap(stmts);case x=>Vector(x)}
    def module(c:Circuit)=c.modules.collectFirst{case m:Module if m.name=="Top"=>m}.get
    def width(e:Expression):Int=e.tpe match{case UIntType(IntWidth(w))=>w.toInt;case _=>throw new IllegalArgumentException("value fixture UInt")}
    def drivers(m:Module):Map[String,Expression]=stmts(m.body).flatMap{
      case DefNode(_,n,v)=>Some(n->v)
      case Connect(_,l,r)=>Some(l.serialize->r)
      case _=>None
    }.toMap
    val old=drivers(module(before));val fresh=drivers(module(after))
    def evaluate(e:Expression,ds:Map[String,Expression],env:Map[String,BigInt],active:Set[String]=Set.empty):BigInt={
      def run(x:Expression)=evaluate(x,ds,env,active)
      val value=e match {
        case UIntLiteral(v,_)=>v
        case _:Reference | _:SubField=>
          val n=e.serialize;env.getOrElse(n,{require(!active(n));evaluate(ds(n),ds,env,active+n)})
        case Mux(c,a,b,_)=>if(run(c)!=0)run(a)else run(b)
        case firrtl2.ir.DoPrim(firrtl2.PrimOps.Cat,Seq(a,b),_,_) => (run(a)<<width(b))|run(b)
        case firrtl2.ir.DoPrim(firrtl2.PrimOps.Bits,Seq(a),Seq(h,l),_) => (run(a)>>l.toInt)&((BigInt(1)<<(h-l+1).toInt)-1)
        case firrtl2.ir.DoPrim(firrtl2.PrimOps.Pad,Seq(a),_,_)=>run(a)
        case DoPrim(firrtl2.PrimOps.Add,Seq(a,b),_,_)=>run(a)+run(b)
        case DoPrim(firrtl2.PrimOps.Sub,Seq(a,b),_,_)=>run(a)-run(b)
        case DoPrim(firrtl2.PrimOps.Dshl,Seq(a,b),_,_)=>run(a)<<run(b).toInt
        case DoPrim(firrtl2.PrimOps.Shr,Seq(a),Seq(n),_)=>run(a)>>n.toInt
        case DoPrim(firrtl2.PrimOps.Lt,Seq(a,b),_,_)=>if(run(a)<run(b))BigInt(1)else BigInt(0)
        case DoPrim(firrtl2.PrimOps.Orr,Seq(a),_,_)=>if(run(a)!=0)BigInt(1)else BigInt(0)
        case _=>throw new IllegalArgumentException("unimplemented independent fixture operator")
      }
      value&((BigInt(1)<<width(e))-1)
    }
    val inputs=IdmaSplitLayout.fields.filter(_.direction==Input)
    val outputs=IdmaSplitLayout.fields.filter(_.direction==Output)
    val vars=(inputs.map(f=>("in_"+f.name,f.width))++outputs.map(f=>("b.__sim_idma_field__"+f.name,f.width)))++
      (if(boundaryRegisterMode(mode))Vector("q_boundary"->1)else Vector.empty)
    require(vars.map(_._2).sum==2634+(if(boundaryRegisterMode(mode))1 else 0))
    val zero=vars.map{case(n,_)=>n->BigInt(0)}.toMap
    val basis=vars.flatMap{case(n,w)=>(0 until w).map(i=>zero.updated(n,BigInt(1)<<i))}
    val random=new scala.util.Random(0x52734L)
    val mixed=Vector.fill(64)(vars.map{case(n,w)=>n->BigInt(w,random)}.toMap)
    // Carry/borrow across every bit, all ones, and shift amounts 0..3.
    val ones=vars.map{case(n,w)=>n->((BigInt(1)<<w)-1)}.toMap
    val directed=(0 to 512).flatMap{i=>
      val a=(BigInt(1)<<i)-1
      Vector(zero.updated("in_axi_read_rsp_i__r_data",a).updated("in_axi_write_rsp_i__r_data",BigInt(1)),
        zero.updated("in_axi_read_rsp_i__r_data",BigInt(0)).updated("in_axi_write_rsp_i__r_data",a))
    }++(0 to 3).map(i=>ones.updated("in_axi_write_rsp_i__b_resp",BigInt(i)))
    val muxDirected=if(unsignedMuxModes(mode)){
      for(outer<-Vector(0,1);inner<-Vector(0,1);
          small<-Vector(BigInt(0),BigInt(1),BigInt(1)<<19,(BigInt(1)<<20)-1);
          large<-Vector(BigInt(0),BigInt(1),BigInt(1)<<511,(BigInt(1)<<512)-1))yield
        ones.updated("in_axi_read_rsp_i__b_valid",BigInt(outer))
          .updated("in_axi_write_rsp_i__b_valid",BigInt(inner))
          .updated("in_axi_write_rsp_i__r_data",small)
          .updated("in_axi_read_rsp_i__r_data",large)
    }else Vector.empty[Map[String,BigInt]]
    require(muxDirected.size==(if(unsignedMuxModes(mode))64 else 0))
    val samples=Vector(zero,ones)++basis++mixed++directed++muxDirected
    samples.foreach { base=>
      val packed=IdmaSplitLayout.busWidths.keys.filter(_.endsWith("_o")).map{bus=>
        val v=outputs.filter(_.bus==bus).foldLeft(BigInt(0)){case(acc,f)=>acc|(base("b.__sim_idma_field__"+f.name)<<f.lsb)}
        ("b."+bus)->v
      }.toMap
      val env=base++packed
      val oldValues=IdmaSplitLayout.busWidths.keys.filter(_.endsWith("_i")).map(bus=>bus->evaluate(old("b."+bus),old,env)).toMap
      inputs.foreach{f=>
        val expected=(oldValues(f.bus)>>f.lsb)&((BigInt(1)<<f.width)-1)
        val observed=evaluate(fresh("b.__sim_idma_field__"+f.name),fresh,env)
        require(observed==expected,"independent packed bit equation mismatch")
        if(f.name=="axi_read_rsp_i__r_last" && Set("boundary_cycle","boundary_registered")(mode)){
          val wanted=if(mode=="boundary_cycle")base("b.__sim_idma_field__axi_read_req_o__r_ready") else base("q_boundary")
          require(observed==wanted,"boundary feedback bit equation must survive")
        }
      }
    }
    samples.size
  }
  /** Inject only into an already lowered/prepared isolated fixture. Neither
    * compiler loop checks nor SymbolTable allowCycles are disabled. */
  private def injectLocalCycle(c:Circuit,mode:String):Circuit={
    if(!Set("true_cycle","self_loop")(mode))return c
    def stmts(s:Statement):Vector[Statement]=s match{case Block(xs)=>xs.toVector.flatMap(stmts);case x=>Vector(x)}
    val t=UIntType(IntWidth(1));val x="__fixture_cycle_x";val y="__fixture_cycle_y"
    def r(n:String,sink:Boolean=false):Expression=Reference(n,t,WireKind,if(sink)SinkFlow else SourceFlow)
    c.copy(modules=c.modules.map{
      case m:Module if m.name=="Top"=>
        val ss=stmts(m.body)
        val names=m.ports.map(_.name).toSet++ss.collect{
          case d:DefNode=>d.name;case d:DefWire=>d.name;case d:DefRegister=>d.name;case d:DefInstance=>d.name
        }
        require(!names(x) && !names(y),"fresh local-cycle fixture names")
        require(ss.count{case Connect(_,l,_)=>l.serialize=="fixture_sentinel";case _=>false}==1,"unique scaffold sentinel")
        val body=ss.map{case a@Connect(_,l,_) if l.serialize=="fixture_sentinel"=>a.copy(expr=r(x));case a=>a}
        // CheckFlows builds its declaration environment in statement order.
        // Declare every injected wire before the sentinel or any cycle edge uses it.
        val declarations=if(mode=="self_loop")Vector(DefWire(NoInfo,x,t))else
          Vector(DefWire(NoInfo,x,t),DefWire(NoInfo,y,t))
        val loop=if(mode=="self_loop")Vector(Connect(NoInfo,r(x,true),r(x)))else
          Vector(Connect(NoInfo,r(x,true),r(y)),Connect(NoInfo,r(y,true),r(x)))
        m.copy(body=Block(declarations++body++loop))
      case m=>m
    })
  }
  private def sentinelSurvives(c:Circuit,mode:String,split:Boolean):Unit={
    def stmts(s:Statement):Vector[Statement]=s match{case Block(xs)=>xs.toVector.flatMap(stmts);case x=>Vector(x)}
    val top=c.modules.collectFirst{case m:Module if m.name=="Top"=>m}.get
    require(top.ports.exists(p=>p.name=="fixture_sentinel" && p.direction==Output),"observable sentinel port survived")
    val ss=stmts(top.body)
    val regs=ss.collect{case r:DefRegister=>r.name}.toSet
    val ds=ss.flatMap{case DefNode(_,n,e)=>Some(n->e);case Connect(_,l,r)=>Some(l.serialize->r);case _=>None}.toMap
    require(ds.contains("fixture_sentinel"),"sentinel driver survived")
    def refs(e:Expression):Set[String]=e match{
      case _:Reference | _:SubField=>Set(e.serialize)
      case _=>var out=Set.empty[String];e.foreachExpr(x=>out++=refs(x));out
    }
    def reaches(start:String,wanted:String,seen:Set[String]=Set.empty):Boolean=
      start==wanted || (!seen(start) && !regs(start) && ds.get(start).exists(e=>refs(e).exists(n=>reaches(n,wanted,seen+start))))
    def cyclic(start:String,active:Set[String]=Set.empty):Boolean=
      !regs(start) && (active(start) || ds.get(start).exists(e=>refs(e).exists(n=>cyclic(n,active+start))))
    mode match{
      case "true_cycle" | "self_loop"=>require(cyclic("fixture_sentinel"),"real combinational cycle sentinel survived")
      case "registered"=>require(regs("q") && reaches("fixture_sentinel","q"),"register sentinel survived")
      case "boundary_registered" | "mux_boundary_registered"=>
        require(regs("q_boundary") && reaches("fixture_sentinel","q_boundary"),"boundary register survived")
        require(ds.get("q_boundary").exists(e=>refs(e).exists(n=>reaches(n,"b.axi_read_req_o"))),"boundary register next state survived")
        if(split)require(reaches("b.__sim_idma_field__axi_read_rsp_i__r_last","q_boundary"),"boundary register cut survived")
      case "boundary_cycle" | "mux_boundary_cycle" if split=>
        require(reaches("b.__sim_idma_field__axi_read_rsp_i__r_last","b.__sim_idma_field__axi_read_req_o__r_ready"),"real boundary feedback survived")
      case "whole_bus" if split=>
        IdmaSplitLayout.fields.filter(_.bus=="axi_read_req_o").foreach{f=>
          require(reaches("b.__sim_idma_field__axi_read_rsp_i__r_id","b.__sim_idma_field__"+f.name),"whole-bus dependency must retain every field")
        }
      case _=>()
    }
  }
  // Direct check-only passes do not schedule CheckCombLoops or optimize away
  // deliberate injected negative fixtures. Every graph still rejects cycles.
  private def checkTypesAndFlows(c:Circuit):Unit={
    val before=c.serialize
    val typed=firrtl2.passes.CheckTypes.run(c)
    require(typed.serialize==before,"CheckTypes changed fixture")
    val flowed=firrtl2.passes.CheckFlows.run(typed)
    require(flowed.serialize==before && c.serialize==before,"type/flow checks mutated fixture")
  }
  private def outcome(c:Circuit):String={
    val before=c.serialize;val factory=new Factory
    val result=try{val t=SymbolTable(c,Seq(factory),allowCycles=false);require(factory.n==1);"GRAPH:"+digest(t)}
      catch{case _:firrtl2.graph.CyclicException=>"CYCLE"}
    require(c.serialize==before,"fixture AST unchanged by graph construction");result
  }
  private def negativeCases(c:Circuit):Int={
    def stmts(s:Statement):Vector[Statement]=s match{case Block(xs)=>xs.toVector.flatMap(stmts);case x=>Vector(x)}
    val top=c.modules.collectFirst{case m:Module if m.name=="Top"=>m}.get
    val ss=stmts(top.body)
    val connection=ss.collectFirst{case x:Connect if x.loc.serialize=="b.axi_read_rsp_i"=>x}.get
    val t=UIntType(IntWidth(532))
    def withTop(xs:Seq[Statement]):Circuit=c.copy(modules=c.modules.map{case m if m.name=="Top"=>top.copy(body=Block(xs));case m=>m})
    def replacing(e:Expression,extra:Seq[Statement]):Circuit=withTop(ss.map{case x:Connect if x.loc.serialize==connection.loc.serialize=>x.copy(expr=e);case x=>x}++extra)
    def rejected(x:Circuit,message:String):Unit={
      var seen=false
      try{IdmaPackedBoundarySplit(x,original)}catch{case e:IllegalArgumentException=>seen=e.getMessage.contains(message)}
      require(seen,"negative fixture did not fail at required guard")
    }
    rejected(withTop(ss:+connection),"exactly one original packed input driver")
    rejected(replacing(SIntLiteral(0,IntWidth(532)),Seq.empty),"known bounded UInt")
    val a=Reference("alias_a",t);val b=Reference("alias_b",t)
    rejected(replacing(a,Seq(DefWire(NoInfo,"alias_a",t),DefWire(NoInfo,"alias_b",t),Connect(NoInfo,a,b),Connect(NoInfo,b,a))),"alias cycle")
    // A tiny shared expression DAG must not expand exponentially downstream.
    val dag=Vector.newBuilder[Statement]
    dag+=DefNode(NoInfo,"dag_0",UIntLiteral(0,IntWidth(532)))
    for(i<-1 to 18){val r=Reference("dag_"+(i-1),t);dag+=DefNode(NoInfo,"dag_"+i,DoPrim(firrtl2.PrimOps.Or,Seq(r,r),Seq.empty,t))}
    rejected(replacing(Reference("dag_18",t),dag.result()),"bounded expanded expression")
    // Direct expression sharing must not recursively hash the expanded tree.
    var shared:Expression=UIntLiteral(0,IntWidth(532))
    for(_<-1 to 18)shared=DoPrim(firrtl2.PrimOps.Or,Seq(shared,shared),Seq.empty,t)
    rejected(replacing(shared,Seq.empty),"bounded caller expression")
    // A deep input tree must fail iterative caller preflight before any
    // recursive rewriting or downstream traversal can occur.
    var deep:Expression=UIntLiteral(0,IntWidth(532))
    for(_<-1 to 300)deep=DoPrim(firrtl2.PrimOps.Not,Seq(deep),Seq.empty,t)
    rejected(replacing(deep,Seq.empty),"bounded caller expression")
    // Projection discards the lower Cat half, but the original packed driver
    // remains in the caller and will still be visited by fixStmt/PrepareAst.
    def slicedAway(hidden:Expression):Expression={
      val joined=DoPrim(firrtl2.PrimOps.Cat,Seq(UIntLiteral(0,IntWidth(532)),hidden),Seq.empty,UIntType(IntWidth(1064)))
      DoPrim(firrtl2.PrimOps.Bits,Seq(joined),Seq(BigInt(1063),BigInt(532)),t)
    }
    rejected(replacing(slicedAway(deep),Seq.empty),"bounded caller expression")
    rejected(replacing(slicedAway(shared),Seq.empty),"bounded caller expression")
    val collision="__sim_idma_field__"+IdmaSplitLayout.fields.head.name
    val wrong=c.copy(modules=c.modules.map{
      case m:Module if m.name==original=>m.copy(body=Block(Seq(m.body,DefWire(NoInfo,collision,UIntType(IntWidth(1))))))
      case m=>m
    })
    rejected(wrong,"fresh private field namespace")
    // New UInt mux domain: reject malformed condition/arm/result widths and types.
    val wide=UIntLiteral(0,IntWidth(532));val narrow=UIntLiteral(0,IntWidth(20));val cond=UIntLiteral(0,IntWidth(1))
    def badMux(cnd:Expression,a:Expression,b:Expression,result:Type=t,message:String="known bounded UInt"):Unit=
      rejected(replacing(Mux(cnd,a,b,result),Seq.empty),message)
    badMux(UIntLiteral(0,IntWidth(2)),wide,narrow,message="exact mux widths")
    badMux(SIntLiteral(0,IntWidth(1)),wide,narrow)
    badMux(Reference("bad_mux_cond",UIntType(UnknownWidth)),wide,narrow)
    badMux(cond,SIntLiteral(0,IntWidth(20)),wide)
    badMux(cond,wide,Reference("bad_mux_arm",UIntType(UnknownWidth)))
    badMux(cond,UIntLiteral(0,IntWidth(0)),wide)
    badMux(cond,UIntLiteral(0,IntWidth(531)),narrow,message="exact mux widths")
    badMux(cond,UIntLiteral(0,IntWidth(533)),narrow,message="exact mux widths")
    badMux(cond,wide,narrow,result=UIntType(UnknownWidth))
    badMux(cond,wide,narrow,result=SIntType(IntWidth(532)))
    19
  }
  private def loaded(c:Class[_],location:String):String={
    require(Paths.get(c.getProtectionDomain.getCodeSource.getLocation.toURI).toRealPath()==Paths.get(location).toRealPath())
    val in=c.getResourceAsStream("/"+c.getName.replace('.','/')+".class")
    require(in!=null);try{val b=in.readAllBytes();require(b.length<1024*1024);sha(b)}finally{in.close()}
  }
  def main(args:Array[String]):Unit={
    // label, actual SymbolTable class SHA, companion SHA, code location.
    val out=System.out;val err=System.err;val muted=new PrintStream(OutputStream.nullOutputStream())
    var rows=Vector.empty[String];var ok=false
    var currentCase="none";var phase="identity"
    // Fixed enums and exception-class digest only; never messages, names or AST.
    def failure(e:Throwable):String="BOUNDARY_GRAPH_FAILURE_V1 case="+currentCase+
      " phase="+phase+" exceptionClassSha="+hash(e.getClass.getName)
    val label=args.headOption.filter(Set("official","cached")).getOrElse("invalid")
    var target:Option[Path]=None
    try{
      require(args.length==4 && Set("official","cached")(args(0)))
      require(args.slice(1,3).forall(_.matches("[0-9a-f]{64}")))
      require(loaded(classOf[SymbolTable],args(3))==args(1) && loaded(SymbolTable.getClass,args(3))==args(2))
      // SimulatorCompiler.requireTargetDir consumes os.RelPath, not an absolute path.
      // Keep the one-component owned directory under this process's supervised cwd.
      val base=Paths.get(".").toAbsolutePath.normalize()
      val absoluteTarget=Files.createTempDirectory(base,"idma-boundary-fixture-")
      val relativeTarget=base.relativize(absoluteTarget)
      require(absoluteTarget.getParent==base && !relativeTarget.isAbsolute &&
        relativeTarget.getNameCount==1 && relativeTarget.normalize()==relativeTarget &&
        relativeTarget.toString!="." && relativeTarget.toString!="..","owned relative fixture target")
      target=Some(relativeTarget)
      System.setOut(muted);System.setErr(muted)
      Console.withOut(muted){Console.withErr(muted){
        rows=Vector("base","true_cycle","self_loop","registered","boundary_cycle","boundary_registered","arithmetic","whole_bus","mux_narrow_true","mux_narrow_false","mux_boundary_cycle","mux_boundary_registered").map{mode=>
          currentCase=mode;phase="parse"
          val c=Parser.parse(source(mode))
          val ext=c.modules.collect{case e:ExtModule=>e};require(ext.size==1)
          phase="projection"
          val split=IdmaFieldSplitTransform(c,hash(ext.head.serialize))
          phase="lower"
          val scaffold=Compiler.toLowFirrtl(CircuitState(split,Seq(TargetDirAnnotation(target.get.toString)))).circuit
          requireUnequalMuxes(scaffold,mode)
          phase="negative_guards"
          if(mode=="base")require(negativeCases(scaffold)==19)
          val localCycle=Set("true_cycle","self_loop")(mode)
          val low=injectLocalCycle(scaffold,mode)
          phase="type_flow"
          checkTypesAndFlows(low)
          sentinelSurvives(low,mode,false)
          phase="projection"
          val repaired=IdmaPackedBoundarySplit(low,original)
          phase="type_flow"
          checkTypesAndFlows(repaired.circuit)
          require(repaired.instances==1 && repaired.projectedFields==26)
          phase="bit_equations"
          val vectors=valueComparison(low,repaired.circuit,mode)
          require(vectors==3730+(if(boundaryRegisterMode(mode))1 else 0)+(if(unsignedMuxModes(mode))64 else 0))
          phase="graph"
          sentinelSurvives(repaired.circuit,mode,true)
          // Exercise the candidate on the injected low graph. No intentional
          // local cycle enters Compiler/PrepareAst, where CheckCombLoops runs.
          val lowOld=outcome(low);val lowNew=outcome(repaired.circuit)
          if(localCycle)require(lowOld=="CYCLE" && lowNew=="CYCLE","low local cycle cannot be bypassed")
          phase="prepare"
          val oldPrepared=injectLocalCycle(prepared(scaffold,target.get),mode)
          val newPrepared=if(localCycle){
            // Prepare a separate noncyclic transformed scaffold, then inject
            // the identical typed sentinel loop. Never prepare repaired.circuit.
            val repairedScaffold=IdmaPackedBoundarySplit(scaffold,original).circuit
            injectLocalCycle(prepared(repairedScaffold,target.get),mode)
          }else prepared(repaired.circuit,target.get)
          phase="type_flow"
          checkTypesAndFlows(oldPrepared);checkTypesAndFlows(newPrepared)
          sentinelSurvives(oldPrepared,mode,false)
          sentinelSurvives(newPrepared,mode,true)
          phase="bit_equations"
          require(valueComparison(oldPrepared,newPrepared,mode)==vectors,"prepared bit equations survived")
          phase="graph"
          val oldResult=outcome(oldPrepared);require(oldResult=="CYCLE")
          val result=outcome(newPrepared)
          if(localCycle)require(result=="CYCLE","prepared local cycle cannot be bypassed")
          require((result=="CYCLE")==Set("true_cycle","self_loop","boundary_cycle","mux_boundary_cycle")(mode),"no true cycle bypass")
          "BOUNDARY_GRAPH_CASE_V1 id="+mode+" lowOriginal="+lowOld+" lowTransformed="+lowNew+
            " original="+oldResult+" transformed="+result+" bitEquationPhases=2 bitEquationVectors="+vectors
        }
        ok=true
      }}
    }catch{case e:Throwable=>ok=false;rows=Vector(failure(e))}
    finally{
      System.setOut(out);System.setErr(err)
      phase="cleanup"
      try{target.foreach{dir=>
        val stream=Files.walk(dir)
        val paths=try{
          val iterator=stream.iterator();val found=Vector.newBuilder[Path];var n=0
          while(iterator.hasNext && n<257){found+=iterator.next();n+=1}
          require(n<=256 && !iterator.hasNext,"bounded fixture cleanup")
          found.result()
        }finally{stream.close()}
        paths.sortBy(p=> -p.getNameCount).foreach(p=>Files.delete(p))
      }}catch{case e:Throwable=>ok=false;rows=Vector(failure(e))}
      muted.close()
    }
    rows.foreach(out.println)
    val coverage=if(ok)" cases=12 negativeGuards=19"else ""
    out.println("BOUNDARY_GRAPH_RUN_V1 label="+label+" pass="+ok+coverage+" numericalPass=false fullHostAccepted=false")
    if(!ok)System.exit(2)
  }
}

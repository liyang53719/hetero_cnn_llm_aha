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
  private val validityModes=Set("validif_full","validif_mixed","validif_nested","validif_zero","validif_cycle","validif_registered")
  private def boundaryRegisterMode(mode:String):Boolean=Set("boundary_registered","mux_boundary_registered","validif_registered")(mode)
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
        if(f.name=="axi_read_rsp_i__r_data" && control=="validif_mixed"){
          "cat(bits(in_axi_read_rsp_i__r_data, 511, 256), mux(in_axi_read_rsp_i__b_valid, pad(validif(in_axi_write_rsp_i__b_valid, bits(in_axi_read_rsp_i__r_data, 19, 0)), 128), bits(in_axi_read_rsp_i__r_data, 255, 0)))"
        }else if(f.name=="axi_read_rsp_i__r_data" && control=="validif_nested"){
          "validif(in_axi_write_rsp_i__b_valid, mux(in_axi_read_rsp_i__b_valid, cat(validif(in_axi_write_rsp_i__r_valid, bits(in_axi_read_rsp_i__r_data, 255, 0)), bits(in_axi_read_rsp_i__r_data, 255, 0)), in_axi_read_rsp_i__r_data))"
        }else if(f.name=="axi_read_rsp_i__b_resp" && control=="validif_zero"){
          "validif(in_axi_write_rsp_i__b_valid, UInt<2>(0))"
        }else if(f.name=="axi_read_rsp_i__r_last" && control=="validif_cycle"){
          "validif(in_axi_write_rsp_i__b_valid, bits(b.axi_read_req_o, 0, 0))"
        }else if(f.name=="axi_read_rsp_i__r_last" && control=="validif_registered"){
          "validif(in_axi_write_rsp_i__b_valid, q_boundary)"
        }else if(f.name=="axi_read_rsp_i__r_last" && Set("boundary_cycle","mux_boundary_cycle")(control)){
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
      }else if(control=="validif_full" && bus=="axi_read_rsp_i")
        s"    b.$bus <= validif(in_axi_write_rsp_i__b_valid, ${cat(parts)})"
      else s"    b.$bus <= ${cat(parts)}"
    }.mkString("\n")
    // Packed input expressions may read this register, so declare it first.
    val declarations=if(boundaryRegisterMode(control))"    reg q_boundary : UInt<1>, clock\n"else ""
    val extra=control match {
      case "base" | "arithmetic" | "whole_bus" | "boundary_cycle" | "mux_narrow_true" | "mux_narrow_false" | "mux_boundary_cycle" | "validif_full" | "validif_mixed" | "validif_nested" | "validif_zero" | "validif_cycle"=>"    fixture_sentinel <= bits(b.axi_read_req_o, 0, 0)\n"
      case "boundary_registered" | "mux_boundary_registered" | "validif_registered"=>"    q_boundary <= bits(b.axi_read_req_o, 0, 0)\n    fixture_sentinel <= q_boundary\n"
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
  private val validityControls=Vector("in_axi_write_rsp_i__b_valid","in_axi_read_rsp_i__b_valid","in_axi_write_rsp_i__r_valid")
  private def validityDirected(vars:Seq[(String,Int)],zero:Map[String,BigInt],ones:Map[String,BigInt]):Vector[Map[String,BigInt]]={
    val activeZero=validityControls.foldLeft(zero)((env,n)=>env.updated(n,BigInt(1)))
    val activeBasis=vars.toVector.flatMap{case(n,w)=>(0 until w).map(i=>activeZero.updated(n,BigInt(1)<<i))}
    val grid=(for(bits<-0 until 8;base<-Vector(zero,ones))yield
      validityControls.zipWithIndex.foldLeft(base){case(env,(n,i))=>env.updated(n,BigInt((bits>>i)&1))}).toVector
    require(grid.size==16,"validity deterministic condition grid")
    // Select the other authored Mux arm while the enclosing ValidIf remains true.
    val alternateZero=activeZero.updated("in_axi_read_rsp_i__b_valid",BigInt(0))
    val alternateBasis=(0 until 512).map(i=>alternateZero.updated("in_axi_read_rsp_i__r_data",BigInt(1)<<i)).toVector
    activeBasis++alternateBasis++grid
  }
  // Standalone low-stage oracle. Does not call the transform or concrete evaluator.
  private def validityComparison(before:Circuit,after:Circuit,mode:String):Int={
    require(Set("validif_full","validif_mixed","validif_nested","validif_zero","validif_cycle","validif_registered")(mode),"validity fixture mode")
    def mask(w:Int):BigInt={require(w>0 && w<=16384,"validity bounded width");(BigInt(1)<<w)-1}
    def width(e:Expression):Int=e.tpe match {
      case UIntType(IntWidth(w)) if w>0 && w<=16384=>w.toInt
      case _=>throw new IllegalArgumentException("validity fixture UInt")
    }
    case class Result(value:BigInt,definedMask:BigInt,width:Int){
      require((value & ~mask(width))==0 && (definedMask & ~mask(width))==0,"validity normalized result")
    }
    def result(v:BigInt,m:BigInt,w:Int):Result=Result(v&mask(w),m&mask(w),w)
    def known(v:BigInt,w:Int):Result=result(v,mask(w),w)
    def fully(r:Result):Boolean=r.definedMask==mask(r.width)
    def pad(r:Result,w:Int):Result={
      require(w>=r.width,"validity pad width")
      result(r.value,r.definedMask|(mask(w)^mask(r.width)),w)
    }
    def slice(r:Result,h:Int,l:Int):Result={
      require(l>=0 && h>=l && h<r.width,"validity slice bounds")
      result(r.value>>l,r.definedMask>>l,h-l+1)
    }
    def concat(a:Result,b:Result):Result=
      result((a.value<<b.width)|b.value,(a.definedMask<<b.width)|b.definedMask,a.width+b.width)
    def stmts(s:Statement):Vector[Statement]=s match{case Block(xs)=>xs.toVector.flatMap(stmts);case x=>Vector(x)}
    def top(c:Circuit):Module=c.modules.collectFirst{case m:Module if m.name=="Top"=>m}.get
    def drivers(m:Module):Map[String,Expression]=stmts(m.body).flatMap{
      case DefNode(_,n,v)=>Some(n->v)
      case Connect(_,l,r)=>Some(l.serialize->r)
      case _=>None
    }.toMap
    // Count actual reached ValidIf conditions separately on each side, not Mux conditions.
    final class Seen(val track:Boolean=true) {
      var trueConditions=0L;var falseConditions=0L;var definedBits=0L;var undefinedBits=0L
      val conditions=scala.collection.mutable.Map.empty[String,(Long,Long)]
      def record(c:Expression,on:Boolean):Unit={
        if(!track)return
        val n=c match{case Reference(n,_,_,_) if validityControls.contains(n)=>n
          case _=>throw new IllegalArgumentException("validity sampled condition identity")}
        val previous=conditions.getOrElse(n,(0L,0L))
        conditions(n)=if(on)(previous._1+1,previous._2)else(previous._1,previous._2+1)
      }
    }
    def evaluate(e:Expression,ds:Map[String,Expression],env:Map[String,BigInt],seen:Seen,
        active:Set[String]=Set.empty):Result={
      val w=width(e)
      def run(x:Expression):Result=evaluate(x,ds,env,seen,active)
      def condition(c:Expression):Boolean={
        require(width(c)==1,"validity condition width")
        val r=run(c)
        require(fully(r),"validity undefined condition")
        r.value!=0
      }
      val out=e match {
        case UIntLiteral(v,_)=>known(v,w)
        case _:Reference | _:SubField=>
          val n=e.serialize
          env.get(n) match {
            case Some(v)=>known(v,w) // Registers are environment leaves, never next-state recursion.
            case None=>
              require(!active(n),"validity alias cycle")
              val r=evaluate(ds.getOrElse(n,throw new IllegalArgumentException("validity missing driver")),ds,env,seen,active+n)
              require(r.width==w,"validity alias width");r
          }
        case ValidIf(c,v,_)=>
          require(width(v)==w,"validity ValidIf width")
          val on=condition(c);seen.record(c,on)
          if(on){seen.trueConditions+=1;run(v)}
          else{seen.falseConditions+=1;result(0,0,w)}
        case Mux(c,a,b,_)=>
          require(w==math.max(width(a),width(b)),"validity mux width")
          pad(if(condition(c))run(a)else run(b),w)
        case DoPrim(firrtl2.PrimOps.Cat,Seq(a,b),Seq(),_)=>
          require(w==width(a)+width(b),"validity cat width");concat(run(a),run(b))
        case DoPrim(firrtl2.PrimOps.Bits,Seq(a),Seq(h,l),_)=>
          require(l>=0 && h>=l && h<width(a) && h-l+1==w,"validity bits width")
          slice(run(a),h.toInt,l.toInt)
        case DoPrim(firrtl2.PrimOps.Pad,Seq(a),Seq(n),_)=>
          require(n>=0 && n<=16384 && w==math.max(width(a),n.toInt),"validity pad width")
          pad(run(a),w)
        case DoPrim(op,args,consts,_)=>
          val rs=args.map(run)
          require(rs.forall(fully),"validity partial arithmetic unsupported")
          val value=(op,rs,consts) match {
            case (firrtl2.PrimOps.And,Seq(a,b),Seq())=>
              require(w==math.max(a.width,b.width),"validity AND width");a.value&b.value
            case (firrtl2.PrimOps.Add,Seq(a,b),Seq())=>
              require(w==math.max(a.width,b.width)+1,"validity ADD width");a.value+b.value
            case (firrtl2.PrimOps.Sub,Seq(a,b),Seq())=>
              require(w==math.max(a.width,b.width)+1,"validity SUB width");a.value-b.value
            case (firrtl2.PrimOps.Dshl,Seq(a,b),Seq())=>
              require(b.width<=14 && w==a.width+(1<<b.width)-1,"validity DSHL width");a.value<<b.value.toInt
            case (firrtl2.PrimOps.Shr,Seq(a),Seq(n))=>
              require(n>=0 && n.isValidInt && w==math.max(1,a.width-n.toInt),"validity SHR width");a.value>>n.toInt
            case (firrtl2.PrimOps.Lt,Seq(a,b),Seq())=>
              require(w==1,"validity LT width");if(a.value<b.value)BigInt(1)else BigInt(0)
            case (firrtl2.PrimOps.Orr,Seq(a),Seq())=>
              require(w==1,"validity ORR width");if(a.value!=0)BigInt(1)else BigInt(0)
            case _=>throw new IllegalArgumentException("unimplemented independent validity operator")
          }
          known(value,w)
        case _=>throw new IllegalArgumentException("unimplemented independent validity operator")
      }
      require(out.width==w,"validity result width");out
    }
    // Direct tests are constructed from literals, not transformed expressions.
    val selfSeen=new Seen(false)
    def lit(v:Int,w:Int):Expression=UIntLiteral(BigInt(v),IntWidth(w))
    def vi(c:Expression,v:Expression):Expression=ValidIf(c,v,v.tpe)
    def check(e:Expression):Result=evaluate(e,Map.empty,Map.empty,selfSeen)
    def rejects(e:Expression,message:String):Unit={
      val rejected=try{check(e);false}catch{
        case x:IllegalArgumentException if x.getMessage==message || x.getMessage=="requirement failed: "+message=>true
      }
      require(rejected,"validity rejection selfcheck")
    }
    val invalid=vi(lit(0,1),lit(3,2))
    require(check(vi(lit(1,1),lit(3,2)))==known(3,2),"validity true selfcheck")
    require(check(invalid).definedMask==0,"validity false selfcheck")
    val padded=DoPrim(firrtl2.PrimOps.Pad,Seq(invalid),Seq(BigInt(4)),UIntType(IntWidth(4)))
    require(check(padded)==result(0,12,4),"validity padded zero selfcheck")
    val joined=DoPrim(firrtl2.PrimOps.Cat,Seq(lit(2,2),padded),Seq.empty,UIntType(IntWidth(6)))
    require(check(joined)==result(32,60,6),"validity mixed cat selfcheck")
    val extracted=DoPrim(firrtl2.PrimOps.Bits,Seq(joined),Seq(BigInt(4),BigInt(1)),UIntType(IntWidth(4)))
    require(check(extracted)==result(0,14,4),"validity mixed bits selfcheck")
    require(check(vi(lit(0,1),DoPrim(firrtl2.PrimOps.Pad,Seq(lit(3,2)),Seq(BigInt(4)),UIntType(IntWidth(4))))).definedMask==0,
      "validity invalid wide differs from padded invalid narrow")
    require(check(Mux(lit(1,1),padded,lit(15,4),UIntType(IntWidth(4))))==check(padded),"validity mux true selfcheck")
    require(check(Mux(lit(0,1),padded,lit(15,4),UIntType(IntWidth(4))))==known(15,4),"validity mux false selfcheck")
    val unknownCondition=vi(lit(0,1),lit(1,1))
    rejects(vi(unknownCondition,lit(3,2)),"validity undefined condition")
    rejects(Mux(unknownCondition,lit(1,1),lit(0,1),UIntType(IntWidth(1))),"validity undefined condition")
    rejects(DoPrim(firrtl2.PrimOps.Add,Seq(invalid,lit(1,2)),Seq.empty,UIntType(IntWidth(3))),"validity partial arithmetic unsupported")
    rejects(DoPrim(firrtl2.PrimOps.Not,Seq(lit(1,1)),Seq.empty,UIntType(IntWidth(1))),"unimplemented independent validity operator")
    // Exercise the mask algebra exhaustively on small independently chosen values/masks.
    for(w<-1 to 4;v<-0 until (1<<w);m<-0 until (1<<w)){
      val r=result(v,m,w)
      for(l<-0 until w;h<-l until w){
        val s=slice(r,h,l)
        for(i<-0 until s.width){
          require(s.value.testBit(i)==r.value.testBit(i+l) && s.definedMask.testBit(i)==r.definedMask.testBit(i+l),"validity slice selfcheck")
        }
      }
      val p=pad(r,w+2)
      require((p.definedMask>>w)==3 && (p.value>>w)==0 && slice(p,w-1,0)==r,"validity pad selfcheck")
      val c=concat(known(2,2),r)
      require(slice(c,w-1,0)==r && slice(c,w+1,w)==known(2,2),"validity cat selfcheck")
    }
    val old=drivers(top(before));val fresh=drivers(top(after))
    val inputs=IdmaSplitLayout.fields.filter(_.direction==Input)
    val outputs=IdmaSplitLayout.fields.filter(_.direction==Output)
    require(inputs.size==26 && inputs.map(_.width).sum==1064,"validity full input coverage")
    val vars=(inputs.map(f=>("in_"+f.name,f.width))++outputs.map(f=>("b.__sim_idma_field__"+f.name,f.width)))++
      (if(boundaryRegisterMode(mode))Vector("q_boundary"->1)else Vector.empty)
    require(vars.map(_._2).sum==2634+(if(boundaryRegisterMode(mode))1 else 0))
    val zero=vars.map{case(n,_)=>n->BigInt(0)}.toMap
    val basis=vars.flatMap{case(n,w)=>(0 until w).map(i=>zero.updated(n,BigInt(1)<<i))}
    val random=new scala.util.Random(0x52734L)
    val mixed=Vector.fill(64)(vars.map{case(n,w)=>n->BigInt(w,random)}.toMap)
    val ones=vars.map{case(n,w)=>n->mask(w)}.toMap
    val directed=(0 to 512).flatMap{i=>
      val a=(BigInt(1)<<i)-1
      Vector(zero.updated("in_axi_read_rsp_i__r_data",a).updated("in_axi_write_rsp_i__r_data",BigInt(1)),
        zero.updated("in_axi_read_rsp_i__r_data",BigInt(0)).updated("in_axi_write_rsp_i__r_data",a))
    }++(0 to 3).map(i=>ones.updated("in_axi_write_rsp_i__b_resp",BigInt(i)))
    val samples=Vector(zero,ones)++basis++mixed++directed++validityDirected(vars,zero,ones)
    require(samples.size==6892+(if(boundaryRegisterMode(mode))2 else 0),"validity sample count")
    val oldSeen=new Seen;val newSeen=new Seen
    samples.foreach{base=>
      val packed=IdmaSplitLayout.busWidths.keys.filter(_.endsWith("_o")).map{bus=>
        val v=outputs.filter(_.bus==bus).foldLeft(BigInt(0)){case(acc,f)=>acc|(base("b.__sim_idma_field__"+f.name)<<f.lsb)}
        ("b."+bus)->v
      }.toMap
      val env=base++packed
      val oldValues=IdmaSplitLayout.busWidths.keys.filter(_.endsWith("_i")).map{bus=>
        bus->evaluate(old("b."+bus),old,env,oldSeen)
      }.toMap
      inputs.foreach{f=>
        val expected=slice(oldValues(f.bus),f.lsb+f.width-1,f.lsb)
        val observed=evaluate(fresh("b.__sim_idma_field__"+f.name),fresh,env,newSeen)
        require(observed.width==f.width && observed.definedMask==expected.definedMask,"independent validity mask mismatch")
        require(((observed.value^expected.value)&expected.definedMask)==0,"independent validity known bit mismatch")
        oldSeen.definedBits+=expected.definedMask.bitCount;oldSeen.undefinedBits+=f.width-expected.definedMask.bitCount
        newSeen.definedBits+=observed.definedMask.bitCount;newSeen.undefinedBits+=f.width-observed.definedMask.bitCount
        if(f.name=="axi_read_rsp_i__r_last" && Set("validif_cycle","validif_registered")(mode)){
          val wanted=if(mode=="validif_cycle")base("b.__sim_idma_field__axi_read_req_o__r_ready")else base("q_boundary")
          require(((observed.value^wanted)&observed.definedMask)==0,"validity boundary feedback equation")
        }
      }
    }
    for(s<-Seq(oldSeen,newSeen)){
      require(s.trueConditions>0 && s.falseConditions>0,"validity condition coverage")
      val expectedConditions=if(mode=="validif_nested")Set("in_axi_write_rsp_i__b_valid","in_axi_write_rsp_i__r_valid")else Set("in_axi_write_rsp_i__b_valid")
      require(s.conditions.keySet.toSet==expectedConditions && s.conditions.values.forall{case(t,f)=>t>0 && f>0},"validity per-condition coverage")
      require(s.definedBits>0 && s.undefinedBits>0,"validity defined and undefined coverage")
      require(s.definedBits+s.undefinedBits==samples.size.toLong*1064,"validity every bit covered")
    }
    samples.size
  }

  private def requireNoValidIf(c:Circuit):Unit={
    def expr(e:Expression):Unit={require(!e.isInstanceOf[ValidIf],"official preparation removed ValidIf");e.foreachExpr(expr)}
    def stmt(s:Statement):Unit={s.foreachExpr(expr);s.foreachStmt(stmt)}
    c.modules.collect{case m:Module if m.name=="Top"=>m}.foreach(m=>stmt(m.body))
  }
  private def checkValidityStructure(before:Circuit,after:Circuit,mode:String):Unit={
    def stmts(s:Statement):Vector[Statement]=s match{case Block(xs)=>xs.toVector.flatMap(stmts);case x=>Vector(x)}
    def inspect(c:Circuit,split:Boolean):(Set[String],Int,Boolean,Boolean,Boolean)={
      val top=c.modules.collectFirst{case m:Module if m.name=="Top"=>m}.get
      val ss=stmts(top.body);val regs=ss.collect{case r:DefRegister=>r.name}.toSet
      val ds=ss.flatMap{case DefNode(_,n,e)=>Some(n->e);case Connect(_,l,r)=>Some(l.serialize->r);case _=>None}.toMap
      var conditions=Set.empty[String];var count=0;var zero=false;var unequal=false;var padded=false
      def walk(e:Expression,active:Set[String]=Set.empty):Unit=e match{
        case Reference(n,_,_,_) if ds.contains(n) && !regs(n)=>
          require(!active(n),"validity structural alias cycle");walk(ds(n),active+n)
        case ValidIf(cond,value,_)=>
          count+=1
          cond match{case Reference(n,UIntType(IntWidth(w)),_,_) if w==1 && n.startsWith("in_")=>conditions+=n
            case _=>throw new IllegalArgumentException("validity fixture condition structure")}
          value match{case UIntLiteral(v,_) if v==0=>zero=true;case _=>()}
          walk(value,active)
        case x@Mux(_,a,b,_)=>
          (a.tpe,b.tpe,x.tpe) match{case (UIntType(IntWidth(wa)),UIntType(IntWidth(wb)),UIntType(IntWidth(w))) if wa==128 && wb==256 && w==256=>unequal=true;case _=>()}
          x.foreachExpr(y=>walk(y,active))
        case x@DoPrim(firrtl2.PrimOps.Pad,Seq(_:ValidIf),Seq(n),_) if n==128=>
          padded=true;x.foreachExpr(y=>walk(y,active))
        case x=>x.foreachExpr(y=>walk(y,active))
      }
      val roots=if(split)IdmaSplitLayout.fields.filter(_.direction==Input).map(f=>"b.__sim_idma_field__"+f.name)
        else IdmaSplitLayout.busWidths.keys.filter(_.endsWith("_i")).toVector.map("b."+_)
      roots.foreach(n=>walk(ds(n)))
      (conditions,count,zero,unequal,padded)
    }
    val old=inspect(before,false);val fresh=inspect(after,true)
    require(old._2>0 && fresh._2>0 && old._1.nonEmpty && fresh._1==old._1,"low validity condition cones preserved")
    if(mode=="validif_mixed")require(old._4 && old._5,"actual unequal mux and padded invalid narrow survived low")
    if(mode=="validif_zero")require(old._3 && fresh._3,"zero data retains validity condition")
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
        case DoPrim(firrtl2.PrimOps.And,Seq(a,b),Seq(),_)=>
          require(width(a)>0 && width(b)>0 && width(e)==math.max(width(a),width(b)),"independent AND width")
          run(a)&run(b)
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
    // Direct independent-oracle checks use literal operands, not transform output.
    for(wa<-1 to 4;wb<-1 to 4;a<-0 until (1<<wa);b<-0 until (1<<wb)){
      val w=math.max(wa,wb)
      val expr=DoPrim(firrtl2.PrimOps.And,Seq(UIntLiteral(BigInt(a),IntWidth(wa)),UIntLiteral(BigInt(b),IntWidth(wb))),Seq.empty,UIntType(IntWidth(w)))
      val expected=(0 until w).foldLeft(BigInt(0)){case(v,i)=>
        if(((a>>i)&1)==1 && ((b>>i)&1)==1)v.setBit(i)else v}
      require(evaluate(expr,Map.empty,Map.empty)==expected,"independent AND selfcheck")
    }
    val maskedAnd=DoPrim(firrtl2.PrimOps.And,Seq(Reference("oracle_mask",UIntType(IntWidth(1))),UIntLiteral(3,IntWidth(2))),Seq.empty,UIntType(IntWidth(2)))
    require(evaluate(maskedAnd,Map.empty,Map("oracle_mask"->BigInt(3)))==1,"independent AND selfcheck")
    val malformedAnd=maskedAnd.copy(tpe=UIntType(IntWidth(1)))
    val rejectedAnd=try{evaluate(malformedAnd,Map.empty,Map("oracle_mask"->BigInt(3)));false}catch{
      case e:IllegalArgumentException if e.getMessage=="requirement failed: independent AND width"=>true
    }
    require(rejectedAnd,"independent AND selfcheck")
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
    val samples=Vector(zero,ones)++basis++mixed++directed++muxDirected++(if(validityModes(mode))validityDirected(vars,zero,ones)else Vector.empty)
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
      case "boundary_registered" | "mux_boundary_registered" | "validif_registered"=>
        require(regs("q_boundary") && reaches("fixture_sentinel","q_boundary"),"boundary register survived")
        require(ds.get("q_boundary").exists(e=>refs(e).exists(n=>reaches(n,"b.axi_read_req_o"))),"boundary register next state survived")
        if(split)require(reaches("b.__sim_idma_field__axi_read_rsp_i__r_last","q_boundary"),"boundary register cut survived")
      case "boundary_cycle" | "mux_boundary_cycle" | "validif_cycle" if split=>
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
    def badValid(cnd:Expression,value:Expression,result:Type=t,message:String="known bounded UInt"):Unit=
      rejected(replacing(ValidIf(cnd,value,result),Seq.empty),message)
    badValid(UIntLiteral(0,IntWidth(2)),wide,message="exact validif widths")
    badValid(SIntLiteral(0,IntWidth(1)),wide)
    badValid(Reference("bad_valid_cond",UIntType(UnknownWidth)),wide)
    badValid(cond,SIntLiteral(0,IntWidth(532)))
    badValid(cond,Reference("bad_valid_value",UIntType(UnknownWidth)))
    badValid(cond,UIntLiteral(0,IntWidth(0)))
    badValid(cond,wide,result=SIntType(IntWidth(532)))
    badValid(cond,wide,result=UIntType(UnknownWidth))
    badValid(cond,wide,result=UIntType(IntWidth(0)))
    badValid(cond,UIntLiteral(0,IntWidth(531)),message="exact validif widths")
    29
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
    var currentCase="none";var phase="identity";var comparisonStep="NONE"
    // Exact static messages select fixed codes; never emit messages or AST.
    def failureCode(e:Throwable):String={
      if(phase!="bit_equations" || e.getClass!=classOf[IllegalArgumentException])return "UNKNOWN"
      Option(e.getMessage).getOrElse("") match {
        case "unimplemented independent fixture operator"=>"UNSUPPORTED_OPERATOR"
        case "value fixture UInt"=>"UNSUPPORTED_WIDTH"
        case "requirement failed: independent packed bit equation mismatch"=>"BIT_MISMATCH"
        case "requirement failed: boundary feedback bit equation must survive"=>"FEEDBACK_MISMATCH"
        case "requirement failed: prepared bit equations survived"=>"VECTOR_MISMATCH"
        case "requirement failed: independent AND width"=>"AND_WIDTH"
        case "requirement failed: independent AND selfcheck"=>"AND_SELFCHECK"
        case "requirement failed: independent validity mask mismatch"=>"VALIDITY_MASK_MISMATCH"
        case "requirement failed: independent validity known bit mismatch"=>"VALIDITY_VALUE_MISMATCH"
        case "requirement failed: validity undefined condition"=>"VALIDITY_UNDEFINED_CONDITION"
        case "requirement failed: validity partial arithmetic unsupported"=>"VALIDITY_PARTIAL_OPERATOR"
        case "unimplemented independent validity operator"=>"VALIDITY_UNSUPPORTED_OPERATOR"
        case "requirement failed: validity condition coverage"=>"VALIDITY_COVERAGE"
        case "requirement failed: validity defined and undefined coverage"=>"VALIDITY_COVERAGE"
        case "requirement failed: validity every bit covered"=>"VALIDITY_COVERAGE"
        case "requirement failed: low validity condition cones preserved"=>"VALIDITY_STRUCTURE"
        case "requirement failed: zero data retains validity condition"=>"VALIDITY_STRUCTURE"
        case "requirement failed: official preparation removed ValidIf"=>"VALIDITY_PREPARED_RESIDUE"
        case _=>"UNKNOWN"
      }
    }
    def failure(e:Throwable):String="BOUNDARY_GRAPH_FAILURE_V1 case="+currentCase+
      " phase="+phase+" comparisonStep="+(if(phase=="bit_equations")comparisonStep else "NONE")+
      " failureCode="+failureCode(e)+" exceptionClassSha="+hash(e.getClass.getName)
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
        rows=Vector("base","true_cycle","self_loop","registered","boundary_cycle","boundary_registered","arithmetic","whole_bus","mux_narrow_true","mux_narrow_false","mux_boundary_cycle","mux_boundary_registered","validif_full","validif_mixed","validif_nested","validif_zero","validif_cycle","validif_registered").map{mode=>
          currentCase=mode;phase="parse"
          val c=Parser.parse(source(mode))
          val ext=c.modules.collect{case e:ExtModule=>e};require(ext.size==1)
          phase="projection"
          val split=IdmaFieldSplitTransform(c,hash(ext.head.serialize))
          phase="lower"
          val scaffold=Compiler.toLowFirrtl(CircuitState(split,Seq(TargetDirAnnotation(target.get.toString)))).circuit
          requireUnequalMuxes(scaffold,mode)
          phase="negative_guards"
          if(mode=="base")require(negativeCases(scaffold)==29)
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
          phase="bit_equations";comparisonStep="LOW"
          if(validityModes(mode))checkValidityStructure(low,repaired.circuit,mode)
          val vectors=if(validityModes(mode))validityComparison(low,repaired.circuit,mode)else valueComparison(low,repaired.circuit,mode)
          require(vectors==(if(validityModes(mode))6892+(if(boundaryRegisterMode(mode))2 else 0)else 3730+(if(boundaryRegisterMode(mode))1 else 0)+(if(unsignedMuxModes(mode))64 else 0)))
          phase="graph"
          sentinelSurvives(repaired.circuit,mode,true)
          // Exercise the candidate on the injected low graph. No intentional
          // local cycle enters Compiler/PrepareAst, where CheckCombLoops runs.
          val lowOld=outcome(low);val lowNew=outcome(repaired.circuit)
          require(lowOld=="CYCLE" && (lowNew=="CYCLE")==Set("true_cycle","self_loop","boundary_cycle","mux_boundary_cycle","validif_cycle")(mode),"low cycle and register outcomes preserved")
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
          phase="bit_equations";comparisonStep="PREPARED"
          if(validityModes(mode)){requireNoValidIf(oldPrepared);requireNoValidIf(newPrepared)}
          require(valueComparison(oldPrepared,newPrepared,mode)==vectors,"prepared bit equations survived")
          phase="graph"
          val oldResult=outcome(oldPrepared);require(oldResult=="CYCLE")
          val result=outcome(newPrepared)
          if(localCycle)require(result=="CYCLE","prepared local cycle cannot be bypassed")
          require((result=="CYCLE")==Set("true_cycle","self_loop","boundary_cycle","mux_boundary_cycle","validif_cycle")(mode),"no true cycle bypass")
          "BOUNDARY_GRAPH_CASE_V1 id="+mode+" lowOriginal="+lowOld+" lowTransformed="+lowNew+
            " original="+oldResult+" transformed="+result+" bitEquationPhases=2 bitEquationVectors="+vectors+
            " lowSemantics="+(if(validityModes(mode))"VALIDITY_MASK"else"CONCRETE")+" preparedSemantics=CONCRETE"
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
    val coverage=if(ok)" cases=18 negativeGuards=29 validityCases=6"else ""
    out.println("BOUNDARY_GRAPH_RUN_V1 label="+label+" pass="+ok+coverage+" numericalPass=false fullHostAccepted=false")
    if(!ok)System.exit(2)
  }
}

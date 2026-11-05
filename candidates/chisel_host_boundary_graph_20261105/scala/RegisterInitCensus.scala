package chiseltest.simulator

import firrtl2.ir._

/** Failure-only, finite census. This file is compiled as RegisterInitCensus.scala.
  * Call only from the catch around the unchanged prepared CheckTypes call:
  *   catch { case original:Throwable =>
  *     record = RegisterInitCensus.record(preparedCircuit,boundaryLowCircuit)
  *     throw original
  *   }
  * The enclosing original failure remains authoritative. Never print diagnostic
  * exceptions, names, Info, expressions, type serialization, or AST hashes.
  */
object RegisterInitCensus {
  private val Unavailable="REG_INIT_CENSUS_V1 regCensus=UNAVAILABLE"
  private val SampleCap=1024
  private val ScanCap=5000000
  private final class Budget {var n=0;def tick():Unit={require(n<ScanCap);n+=1}}
  private final class Hist {
    private val counts=scala.collection.mutable.Map.empty[String,Int]
    def add(k:String):Unit=counts(k)=counts.getOrElse(k,0)+1
    def text:String=if(counts.isEmpty)"NONE"else counts.toVector.sortBy(_._1).map{case(k,v)=>k+":"+v}.mkString(",")
    def count(k:String):Int=counts.getOrElse(k,0)
  }
  private def kind(t:Type):String=t match {
    case _:UIntType=>"U";case _:SIntType=>"S";case ClockType=>"C"
    case ResetType=>"R";case AsyncResetType=>"A";case UnknownType=>"N"
    case _:VectorType=>"V";case _:BundleType=>"B";case _=>"O"
  }
  private def widthRelation(a:Type,b:Type):String={
    def numeric(t:Type):Option[Width]=t match {
      case UIntType(w)=>Some(w);case SIntType(w)=>Some(w);case _=>None
    }
    (numeric(a),numeric(b)) match {
      case (Some(IntWidth(x)),Some(IntWidth(y)))=>if(x==y)"EQ"else "NE"
      case (Some(_),Some(_))=>"UNKNOWN"
      case _=>"NA"
    }
  }
  private def expressionKind(e:Expression):String=e match {
    case _:Reference=>"REF";case _:UIntLiteral=>"ULIT";case _:SIntLiteral=>"SLIT"
    case _:Mux=>"MUX";case _:ValidIf=>"VALIDIF";case _:DoPrim=>"PRIM";case _=>"OTHER"
  }
  private def zeroKind(e:Expression):String=e match {
    case UIntLiteral(v,_) if v==0=>"UZERO"
    case SIntLiteral(v,_) if v==0=>"SZERO"
    case _=>"OTHER"
  }
  // WrappedType.equals recurses over aggregates. Bound it BEFORE invoking it.
  private def checkedType(t:Type,b:Budget):Unit={
    var pending=List((t,0));var local=0
    while(pending.nonEmpty){
      val (x,depth)=pending.head;pending=pending.tail
      b.tick();local+=1;require(local<=4096 && depth<=64)
      x match {
        case VectorType(elem,n)=>require(n>=0);pending=(elem,depth+1)::pending
        case BundleType(fields)=>
          require(fields.size<=4096)
          fields.foreach{f=>require(f.name.length<=4096);pending=(f.tpe,depth+1)::pending}
        case _=>()
      }
    }
  }
  // Exactly CheckTypes' T09 branch, including its preceding Analog exclusion.
  private def mismatch(r:DefRegister,b:Budget):Boolean=r.tpe match {
    case AnalogType(_)=>false
    case _=>
      checkedType(r.tpe,b);checkedType(r.init.tpe,b)
      firrtl2.WrappedType.wt(r.tpe)!=firrtl2.WrappedType.wt(r.init.tpe)
  }
  private def checkedInfo(info:Info,b:Budget):Unit={
    var pending=List((info,0));var local=0
    while(pending.nonEmpty){
      val (x,depth)=pending.head;pending=pending.tail;b.tick();local+=1
      require(local<=256 && depth<=16)
      x match {
        case NoInfo=>()
        case FileInfo(s)=>require(s.length<=4096)
        case MultiInfo(xs)=>require(xs.size<=64);xs.foreach(i=>pending=(i,depth+1)::pending)
        case _=>throw new IllegalArgumentException("unsupported census info")
      }
    }
  }
  private def walk(c:Circuit,b:Budget)(visit:(String,Statement)=>Unit):Unit={
    require(c.modules.size<=4096)
    c.modules.foreach{
      case m:Module=>
        require(m.name.length<=4096);b.tick()
        var pending=List(m.body)
        while(pending.nonEmpty){
          val s=pending.head;pending=pending.tail;visit(m.name,s)
          // Budget at enqueue, not dequeue: even very broad Blocks stay bounded.
          s.foreachStmt{x=>b.tick();pending=x::pending}
        }
      case _:ExtModule=>b.tick()
      case _=>throw new IllegalArgumentException("unsupported census module")
    }
  }
  private final case class Evidence(scanned:Int,total:Int,sampled:Int,truncated:Boolean,
      decl:Hist,init:Hist,reset:Hist,widths:Hist,expr:Hist,iz:Hist,rz:Hist,self:Hist,origin:Hist,uses:Hist,info:Hist){
    def record:String={
      val s="REG_INIT_CENSUS_V1 regCensus=OK regScanned="+scanned+" regMismatchTotal="+total+
        " regMismatchSampled="+sampled+" regMismatchTruncated="+truncated+
        " regDeclTypes="+decl.text+" regInitTypes="+init.text+" regResetTypes="+reset.text+
        " regInitExpr="+expr.text+" regInitZero="+iz.text+" regResetZero="+rz.text+
        " regSelf="+self.text+" regOrigin="+origin.text+" regWidths="+widths.text+" regUses="+uses.text+" regUseInfo="+info.text
      require(s.length<=1024);s
    }
  }
  private def collect(c:Circuit,before:Circuit):Evidence={
    val budget=new Budget
    val beforeNames=scala.collection.mutable.HashSet.empty[(String,String)]
    walk(before,budget){(module,s)=>s match {
      case r:DefRegister=>require(r.name.length<=4096 && beforeNames.size<250000);beforeNames+=((module,r.name))
      case _=>()
    }}
    val decl=new Hist;val init=new Hist;val reset=new Hist;val widths=new Hist;val expr=new Hist
    val iz=new Hist;val rz=new Hist;val self=new Hist;val origin=new Hist;val uses=new Hist;val info=new Hist
    val sampled=scala.collection.mutable.HashMap.empty[(String,String),DefRegister]
    var scanned=0;var total=0
    walk(c,budget){(module,s)=>s match {
      case r:DefRegister=>
        scanned+=1;require(r.name.length<=4096)
        if(mismatch(r,budget)){
          total+=1
          if(total<=SampleCap){
            val key=(module,r.name);require(!sampled.contains(key));sampled(key)=r
            decl.add(kind(r.tpe));init.add(kind(r.init.tpe));reset.add(kind(r.reset.tpe));widths.add(widthRelation(r.tpe,r.init.tpe))
            expr.add(expressionKind(r.init));iz.add(zeroKind(r.init));rz.add(zeroKind(r.reset))
            self.add(r.init match{case Reference(n,_,_,_) if n==r.name=>"DIRECT";case _=>"OTHER"})
            origin.add(if(beforeNames(key))"PRESENT"else "ADDED")
          }
        }
      case _=>()
    }}
    val usedKinds=scala.collection.mutable.HashSet.empty[((String,String),String)]
    val infoKinds=scala.collection.mutable.HashSet.empty[((String,String),String)]
    // Direct means an immediate Reference operand of the statement itself.
    // No alias expansion, graph reachability, nested-expression or name heuristic.
    // Histograms count sampled registers having each flag, at most1024/bin.
    // Flags may overlap: marginal sums need not equal the sampled count.
    walk(c,budget){(module,s)=>
      val selected:Option[(String,Info)]=s match {
        case p:Print=>Some(("PRINT",p.info))
        case p:Stop=>Some(("STOP",p.info))
        case p:Verification=>Some(("VERIFY",p.info))
        case _=>None
      }
      selected.foreach{case(code,statementInfo)=>
        val hit=scala.collection.mutable.HashSet.empty[(String,String)]
        s.foreachExpr{e=>budget.tick();e match {
          case Reference(n,_,_,_)=>val key=(module,n);if(sampled.contains(key))hit+=key
          case _=>()
        }}
        hit.foreach{key=>
          val registerInfo=sampled(key).info
          checkedInfo(registerInfo,budget);checkedInfo(statementInfo,budget)
          val relation=if(registerInfo!=statementInfo)"DIFFERENT"else if(registerInfo==NoInfo)"SAME_NONE"else "SAME_PRESENT"
          if(usedKinds.add((key,code)))uses.add(code)
          if(infoKinds.add((key,relation)))info.add(relation)
        }
      }
    }
    Evidence(scanned,total,sampled.size,total>SampleCap,decl,init,reset,widths,expr,iz,rz,self,origin,uses,info)
  }
  /** Failure-safe record only; neither mutate circuits nor replace original error. */
  def record(after:Circuit,before:Circuit):String=
    try{collect(after,before).record}catch{case _:Throwable=>Unavailable}

  // The synthetic gate pins the exact companion bytes and canonical code source.
  def loadedIdentity(location:String):String={
    val cls=RegisterInitCensus.getClass
    require(java.nio.file.Paths.get(cls.getProtectionDomain.getCodeSource.getLocation.toURI).toRealPath()==
      java.nio.file.Paths.get(location).toRealPath())
    val in=cls.getResourceAsStream("/"+cls.getName.replace('.','/')+".class")
    require(in!=null)
    try{
      val bytes=in.readNBytes(1024*1024+1)
      require(bytes.length<=1024*1024)
      java.security.MessageDigest.getInstance("SHA-256").digest(bytes).map(x=>f"${x&255}%02x").mkString
    }finally{in.close()}
  }
  /** Same-code synthetic gate. No compiler, simulator, DUT, or production AST. */
  def main(args:Array[String]):Unit={
    require(args.length==2)
    require(args(0).matches("[0-9a-f]{64}"))
    require(loadedIdentity(args(1))==args(0))
    val u1=UIntType(IntWidth(1));val clock=Reference("clk",ClockType)
    val zero=UIntLiteral(0,IntWidth(1))
    def reg(n:String,t:Type,i:Expression,inf:Info=NoInfo):DefRegister=DefRegister(inf,n,t,clock,zero,i)
    def circuit(ss:Seq[Statement]):Circuit=Circuit(NoInfo,Seq(Module(NoInfo,"Synthetic",Seq.empty,Block(ss))),"Synthetic")
    val empty=circuit(Seq.empty)
    val clk=reg("clock_mismatch",ClockType,zero)
    val sint=reg("signed_mismatch",SIntType(IntWidth(8)),zero)
    val unequal=reg("uint_width_ok",UIntType(IntWidth(8)),zero)
    val unknown=reg("unknown_self",UnknownType,Reference("unknown_self",UnknownType))
    val analog=reg("analog_excluded",AnalogType(IntWidth(1)),zero)
    val b=new Budget
    require(mismatch(clk,b) && mismatch(sint,b) && !mismatch(unequal,b) && mismatch(unknown,b) && !mismatch(analog,b))
    val base=circuit(Seq(clk,sint,unequal,unknown,analog))
    val e=collect(base,circuit(Seq(clk)))
    require(e.scanned==5 && e.total==3 && e.sampled==3 && !e.truncated)
    require(e.decl.count("C")==1 && e.decl.count("S")==1 && e.decl.count("N")==1)
    require(e.widths.count("NE")==1 && e.widths.count("NA")==2)
    require(widthRelation(SIntType(IntWidth(1)),u1)=="EQ")
    require(widthRelation(SIntType(UnknownWidth),u1)=="UNKNOWN")
    require(widthRelation(unequal.tpe,unequal.init.tpe)=="NE" && !mismatch(unequal,new Budget))
    require(e.init.count("U")==2 && e.init.count("N")==1 && e.iz.count("UZERO")==2)
    require(e.self.count("DIRECT")==1 && e.origin.count("PRESENT")==1 && e.origin.count("ADDED")==2)
    def many(n:Int)=circuit((0 until n).map(i=>reg("r"+i,ClockType,zero)))
    val exact=collect(many(SampleCap),empty);val over=collect(many(SampleCap+1),empty)
    require(exact.total==SampleCap && exact.sampled==SampleCap && !exact.truncated)
    require(over.total==SampleCap+1 && over.sampled==SampleCap && over.truncated)
    val inf=FileInfo("synthetic-only")
    val r=reg("used",ClockType,zero,inf);val ref=Reference("used",ClockType)
    val statements=Seq[Statement](r,
      Print(inf,StringLit(""),Seq(ref,ref),clock,zero),
      Print(inf,StringLit(""),Seq(ref),clock,zero),
      Stop(NoInfo,0,ref,zero),
      Verification(Formal.Assert,inf,ref,zero,zero,StringLit("")))
    val direct=collect(circuit(statements),empty)
    require(direct.uses.count("PRINT")==1 && direct.uses.count("STOP")==1 && direct.uses.count("VERIFY")==1)
    require(direct.info.count("SAME_PRESENT")==1 && direct.info.count("DIFFERENT")==1)
    val none=collect(circuit(Seq(clk,Stop(NoInfo,0,Reference(clk.name,ClockType),zero))),empty)
    require(none.info.count("SAME_NONE")==1)
    val alias=DefNode(NoInfo,"alias",ref)
    val indirect=collect(circuit(Seq(r,alias,Print(inf,StringLit(""),Seq(Reference("alias",ClockType)),clock,zero))),empty)
    require(indirect.uses.count("PRINT")==0 && indirect.info.count("SAME_PRESENT")==0)
    val deep=(0 until 65).foldLeft[Type](u1){case(t,_)=>VectorType(t,1)}
    require(record(circuit(Seq(reg("deep",deep,zero))),empty)==Unavailable)
    val oversizedInfo=FileInfo("x"*4097)
    val oversizedReg=reg("oversized",ClockType,zero,oversizedInfo)
    require(record(circuit(Seq(oversizedReg,Stop(oversizedInfo,0,Reference("oversized",ClockType),zero))),empty)==Unavailable)
    require(record(null,empty)==Unavailable)
    val limited=new Budget;limited.n=ScanCap-1;limited.tick();require(limited.n==ScanCap);val rejected=try{limited.tick();false}catch{case _:IllegalArgumentException=>true}
    require(rejected)
    require(e.record.length<=1024 && exact.record.length<=1024 && over.record.length<=1024)
    println("REGISTER_INIT_CENSUS_FIXTURE_V1 status=PASS")
  }
}

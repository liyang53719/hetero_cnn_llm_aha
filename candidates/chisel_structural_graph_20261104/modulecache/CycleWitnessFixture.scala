package treadle2.executable

import java.io.{OutputStream,PrintStream}
import firrtl2.ir._

/** Pure small-graph tests plus original exception noninterference. No engine. */
object CycleWitnessFixture {
  import BoundedCycleWitness._
  private final class N(val name:String)
  private val a=new N("a");private val b=new N("b");private val c=new N("c")
  private def run(edges:Map[N,Vector[N]],limits:Limits=Limits(),valid:Boolean=true,role:String="OTHER",clock:()=>Long=()=>System.nanoTime()):Result=
    find[N](a,n=>edges.getOrElse(n,Vector.empty).iterator,(child,parent)=>valid && edges.getOrElse(parent,Vector.empty).exists(_ eq child),_.name,_=>role,limits,clock)
  def main(args:Array[String]):Unit={
    val out=System.out;val err=System.err;var bytes=0L;var passed=0;var failed=false
    val sink=new PrintStream(new OutputStream{override def write(b:Int):Unit={bytes+=1;require(bytes<=1048576)}},true,"UTF-8")
    def check(id:String)(f: => Unit):Unit={
      try{f;passed+=1;out.println("CYCLE_FIXTURE_V1 case="+id+" outcome=PASS")}
      catch{case _:Throwable=>failed=true;out.println("CYCLE_FIXTURE_V1 case="+id+" outcome=FAIL")}
    }
    try{System.setOut(sink);System.setErr(sink);Console.withOut(sink){Console.withErr(sink){
      check("self_loop"){val r=run(Map(a->Vector(a)));require(r.complete && r.nodeHashes.size==1 && r.json.length<=8192)}
      check("multi_loop"){val r=run(Map(a->Vector(b),b->Vector(c),c->Vector(a)));require(r.complete && r.nodeHashes.distinct.size==3 && r.inspected==3)}
      check("acyclic"){require(run(Map(a->Vector(b),b->Vector(c))).reason=="NO_CLOSED_PATH")}
      check("reachable_other_cycle"){require(run(Map(a->Vector(b),b->Vector(c),c->Vector(b))).reason=="NO_CLOSED_PATH")}
      check("node_cap"){require(run(Map(a->Vector(b),b->Vector(a)),Limits(nodes=1)).reason=="NODE_CAP")}
      check("edge_cap"){require(run(Map(a->Vector(b),b->Vector(a)),Limits(edges=1)).reason=="EDGE_CAP")}
      check("output_cap"){require(run(Map(a->Vector(b),b->Vector(a)),Limits(output=1)).reason=="OUTPUT_CAP")}
      check("time_cap"){var t=0L;require(run(Map(a->Vector(a)),Limits(nanos=1),clock=()=>{t+=1;t}).reason=="TIME_CAP")}
      check("reverse_edge"){require(run(Map(a->Vector(a)),valid=false).reason=="REVERSE_EDGE_MISSING")}
      check("invalid_role"){require(run(Map(a->Vector(a)),role="raw-private-string").reason=="INVALID_ROLE")}
      check("name_cap"){val x=new N("x"*4097);require(find[N](x,_=>Iterator(x),(_,_)=>true,_.name,_=>"OTHER").reason=="NAME_CAP")}
      check("lazy_edges"){var n=0;val r=find[N](a,_=>Iterator.continually{n+=1;b},(_,_)=>true,_.name,_=>"OTHER",Limits(edges=5));require(r.reason=="EDGE_CAP" && n==5)}
      check("callback_error"){require(find[N](a,_=>throw new IllegalStateException,(_,_)=>true,_.name,_=>"OTHER").reason=="INTERNAL_ERROR")}
      check("malformed_record"){
        var rejected=false;try{Result("CLOSED_WITNESS","NONE",Vector("invalid"),Vector("OTHER"),1,1)}catch{case _:IllegalArgumentException=>rejected=true};require(rejected)
      }
      check("record_disclosure"){val r=run(Map(a->Vector(a)));require(!r.json.contains("raw-private") && r.nodeHashes.head.length==64 && r.json.forall(_<128))}
      check("exception_noninterference"){
        val u=UIntType(IntWidth(1));val m=Module(NoInfo,"Loop",Seq.empty,Block(Seq(DefWire(NoInfo,"x",u),DefWire(NoInfo,"y",u),Connect(NoInfo,Reference("x",u),Reference("y",u)),Connect(NoInfo,Reference("y",u),Reference("x",u)))))
        val circuit=Circuit(NoInfo,Seq(m),"Loop");val before=circuit.serialize;var seen=0;var thrown=false
        try{withDiagnostic(Map.empty,r=>{require(r.complete);seen+=1;throw new IllegalArgumentException("suppressed diagnostic failure")}){SymbolTable(circuit,Seq.empty,allowCycles=false)}}
        catch{case _:firrtl2.graph.CyclicException=>thrown=true}
        require(thrown && seen==1 && circuit.serialize==before)
        // A subsequent construction cannot inherit the prior observer.
        thrown=false;try{SymbolTable(circuit,Seq.empty,allowCycles=false)}catch{case _:firrtl2.graph.CyclicException=>thrown=true}
        require(thrown && seen==1)
      }
    }}}finally{System.setOut(out);System.setErr(err)}
    out.println("CYCLE_FIXTURE_FINAL_V1 cases="+passed+" status="+(if(failed)"FAIL" else "PASS"));out.flush()
    if(failed || passed!=16 || out.checkError())System.exit(2)
  }
}

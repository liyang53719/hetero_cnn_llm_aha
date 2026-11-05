package treadle2.executable

import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest
import scala.collection.mutable
import scala.util.control.NonFatal

/** Read-only, bounded failure diagnostic. It cannot return a SymbolTable or
  * authorize a graph pass. Names never leave this process, only SHA256 values.
  * No traversal sorts/materializes all neighbours or uses recursive DFS.
  */
object BoundedCycleWitness {
  val roles=Set("OTHER","IDMA_READ_REQUEST_PACKED","IDMA_READ_RESPONSE_PACKED","IDMA_SPLIT_R_READY","IDMA_SPLIT_R_LAST")
  val reasons=Set("NONE","NO_CLOSED_PATH","NODE_CAP","EDGE_CAP","OUTPUT_CAP","TIME_CAP","REVERSE_EDGE_MISSING","NAME_CAP","INVALID_ROLE","INTERNAL_ERROR")
  final case class Limits(nodes:Int=4096,edges:Int=16384,output:Int=32,nanos:Long=2000000000L) {
    require(nodes>0 && nodes<=4096 && edges>0 && edges<=16384 && output>0 && output<=32 && nanos>0 && nanos<=2000000000L)
  }
  final case class Result(status:String,reason:String,nodeHashes:Vector[String],nodeRoles:Vector[String],visited:Int,inspected:Int) {
    require(Set("CLOSED_WITNESS","INCOMPLETE_WITNESS")(status) && reasons(reason))
    require(visited>=0 && visited<=4096 && inspected>=0 && inspected<=16384)
    require(nodeHashes.size<=32 && nodeHashes.size==nodeRoles.size)
    require(nodeHashes.forall(_.matches("[0-9a-f]{64}")) && nodeRoles.forall(roles))
    val complete=status=="CLOSED_WITNESS"
    require(if(complete)reason=="NONE" && nodeHashes.nonEmpty else reason!="NONE" && nodeHashes.isEmpty)
    // Closure is implicit: final node's edge returns to the first node. Every
    // node occurs once. Origin UNKNOWN is honest; no source-derived guess.
    val digest=sha((nodeHashes zip nodeRoles).map{case(h,r)=>h+":"+r}.mkString("\n"))
    def json:String={
      val s="{\"schema\":\"BOUNDED_CYCLE_WITNESS_V1\",\"status\":\""+status+"\",\"reason\":\""+reason+"\",\"digest\":\""+digest+
        "\",\"node_hashes\":["+nodeHashes.map(x=>"\""+x+"\"").mkString(",")+"],\"roles\":["+nodeRoles.map(x=>"\""+x+"\"").mkString(",")+
        "],\"edge_origins\":["+nodeHashes.map(_=>"\"UNKNOWN\"").mkString(",")+"],\"closed\":"+complete+",\"edge_checked\":"+complete+",\"visited\":"+visited+",\"inspected\":"+inspected+"}"
      require(s.getBytes(UTF_8).length<=8192);s
    }
  }
  private def sha(s:String):String=MessageDigest.getInstance("SHA-256").digest(s.getBytes(UTF_8)).map(x=>f"${x&255}%02x").mkString
  private final case class Capped(reason:String) extends RuntimeException
  def find[N <: AnyRef](start:N,children:N=>Iterator[N],hasParent:(N,N)=>Boolean,name:N=>String,role:N=>String,
                       limits:Limits=Limits(),clock:()=>Long=()=>System.nanoTime()):Result={
    val begin=clock();var inspected=0;var count=0
    def incomplete(r:String)=Result("INCOMPLETE_WITNESS",r,Vector.empty,Vector.empty,count,inspected)
    def tick():Unit=if(clock()-begin>=limits.nanos)throw Capped("TIME_CAP")
    val seen=new java.util.IdentityHashMap[N,java.lang.Boolean]()
    val path=mutable.ArrayBuffer.empty[N]
    val iters=mutable.ArrayBuffer.empty[Iterator[N]]
    def enter(n:N):Unit={
      tick();if(count>=limits.nodes)throw Capped("NODE_CAP")
      seen.put(n,java.lang.Boolean.TRUE);count+=1;path+=n;iters+=children(n)
    }
    try {
      enter(start)
      while(iters.nonEmpty){
        tick()
        val it=iters.last
        if(!it.hasNext){iters.remove(iters.size-1);path.remove(path.size-1)}
        else {
          tick();if(inspected>=limits.edges)throw Capped("EDGE_CAP")
          val next=it.next();inspected+=1;tick()
          // Checked while visiting, against the independently built reverse graph.
          if(!hasParent(next,path.last))throw Capped("REVERSE_EDGE_MISSING")
          if(next eq start){
            if(path.size>limits.output)throw Capped("OUTPUT_CAP")
            val hashes=Vector.newBuilder[String];val rs=Vector.newBuilder[String]
            path.foreach{n=>
              tick();val s=name(n);if(s==null || s.length>4096)throw Capped("NAME_CAP")
              val r=role(n);if(!roles(r))throw Capped("INVALID_ROLE")
              hashes+=sha(s);rs+=r
            }
            tick();return Result("CLOSED_WITNESS","NONE",hashes.result(),rs.result(),count,inspected)
          }
          if(!seen.containsKey(next))enter(next)
        }
      }
      incomplete("NO_CLOSED_PATH")
    }catch{case Capped(r)=>incomplete(r);case NonFatal(_)=>incomplete("INTERNAL_ERROR")}
  }
  // This is enabled only around one synchronous SymbolTable construction.
  // Always restore prior state, even when construction throws its original error.
  private val observer=new ThreadLocal[(Map[String,String],Result=>Unit)]()
  def withDiagnostic[T](roleByName:Map[String,String],emit:Result=>Unit)(body: => T):T={
    require(roleByName.size<=64 && roleByName.forall{case(n,r)=>n.length<=4096 && roles(r)})
    require(observer.get()==null,"no nested observer")
    observer.set((roleByName,emit));try body finally observer.remove()
  }
  def observe(table:SymbolTable,node:Symbol):Unit={
    val f=observer.get();if(f!=null)try {
      val result=find[Symbol](node,n=>table.childrenOf.getEdges(n).iterator,
        (child,parent)=>table.parentsOf.getEdges(child).contains(parent),_.name,
        n=>f._1.getOrElse(n.name,"OTHER"))
      f._2(result)
    } catch{case NonFatal(_)=>()}
  }
}

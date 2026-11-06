package chiseltest.simulator

import firrtl2.CircuitState
import firrtl2.ir._
import java.io.{OutputStream,OutputStreamWriter}
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest
import scala.collection.mutable

/** ISOLATED SOURCE CANDIDATE. No CLI, no compilation/runtime qualification,
  * no connection to the frozen Host preparation path, no admission authority.
  * Rebinds only exact structured FileInfo filename tokens BEFORE preparation.
  */
object ExactHighSourceInfoRebinding {
  final case class FilenamePair(localEscaped:String,remoteEscaped:String)
  final case class Limits(maxSyntaxNodes:Long,maxInfoNodes:Long,maxDepth:Int,maxSerializedBytes:Long) {
    require(maxSyntaxNodes>0 && maxSyntaxNodes<=4000000)
    require(maxInfoNodes>0 && maxInfoNodes<=8000000)
    require(maxDepth>0 && maxDepth<=512)
    require(maxSerializedBytes>0 && maxSerializedBytes<=512L*1024*1024)
  }
  final case class Digest(sha256:String,bytes:Long)
  final case class PathCount(localEscaped:String,remoteEscaped:String,occurrences:Long)
  final case class Evidence(raw:Digest,rebound:Option[Digest],
    changedFilenameCounts:Vector[PathCount],unchangedFilenameCounts:Vector[(String,Long)],
    syntaxNodes:Long,infoNodes:Long,completedRebinding:Boolean)
  final case class Result(state:CircuitState,raw:Digest,rebound:Digest,
    changedFilenameCounts:Vector[PathCount],unchangedFilenameCounts:Vector[(String,Long)],
    syntaxNodes:Long,infoNodes:Long,qualified:Boolean=false,hostIntegrationPermitted:Boolean=false)

  private val statements=Set("DefWire","DefRegister","DefInstance","DefMemory","DefNode",
    "Conditionally","Block","Connect","IsInvalid","Attach","Stop","Print","Verification","EmptyStmt$")
    .map("firrtl2.ir."+_) ++ Set("firrtl2.CDefMemory","firrtl2.CDefMPort","firrtl2.WDefInstanceConnector")
  private def hex(b:Array[Byte]):String=b.map(x=>f"${x&255}%02x").mkString
  private def same(a:Any,b:Any):Boolean=(a,b)match{
    case(x:AnyRef,y:AnyRef)=>x eq y
    case _=>a==b
  }

  /** Stateful UTF-8 writer carries an incomplete surrogate pair across chunks.
    * No whole-circuit String, getBytes array, file, or serializer replacement.
    * The official serializer's own largest fragment remains RAM-budgeted.
    */
  def digest(c:Circuit,limit:Long):Digest=digestChunks(Serializer.lazily(c).iterator,limit)
  private[simulator] def digestChunks(chunks:Iterator[String],limit:Long):Digest={
    require(limit>0 && limit<=512L*1024*1024)
    val md=MessageDigest.getInstance("SHA-256");var bytes=0L
    val sink=new OutputStream {
      private def admit(n:Int):Unit={require(n>=0 && bytes<=limit-n,"serialized byte cap");bytes+=n}
      override def write(b:Int):Unit={admit(1);md.update(b.toByte)}
      override def write(b:Array[Byte],off:Int,len:Int):Unit={admit(len);md.update(b,off,len)}
    }
    val writer=new OutputStreamWriter(sink,UTF_8)
    try chunks.foreach(s=>writer.write(s)) finally writer.close()
    Digest(hex(md.digest()),bytes)
  }

  /** Owner must verify the complete filename catalog against immutable source
    * and class evidence. Exact remote high SHA is independently fixed, never
    * learned from this function's output. Unknowns stop before any transform.
    */
  def rebind(high:CircuitState,pairs:Vector[FilenamePair],unchangedEscaped:Set[String],
    expectedRemoteHighSha256:String,limits:Limits,recordEvidence:Evidence=>Unit):Result={
    require(expectedRemoteHighSha256.matches("[0-9a-f]{64}"))
    require(high.circuit.getClass==classOf[Circuit],"exact standard Circuit implementation")
    require(high.renames.isEmpty,"no pending renames")
    val allowed=Set("firrtl2.transforms.DontTouchAnnotation","firrtl2.options.TargetDirAnnotation")
    require(high.annotations.forall(a=>allowed(a.getClass.getName)),"same original high annotation classes")
    require(high.annotations.count(_.getClass.getName=="firrtl2.options.TargetDirAnnotation")==1)
    require(high.annotations.exists(_.getClass.getName=="firrtl2.transforms.DontTouchAnnotation"))
    require(pairs.nonEmpty && pairs.size<=162 && unchangedEscaped.size<=4096,"bounded independently verified filename catalog")
    def token(s:String):Unit={
      require(s.nonEmpty && s.length<=4096 && !s.exists(_.isWhitespace),"one exact escaped filename token")
      require(FileInfo.escape(FileInfo.unescape(s))==s,"canonical escaped filename token")
    }
    pairs.foreach{p=>token(p.localEscaped);token(p.remoteEscaped);require(p.localEscaped!=p.remoteEscaped)}
    unchangedEscaped.foreach(token)
    val locals=pairs.map(_.localEscaped);val remotes=pairs.map(_.remoteEscaped)
    require(locals.distinct.size==pairs.size && remotes.distinct.size==pairs.size,"filename bijection")
    require((locals.toSet intersect remotes.toSet).isEmpty,"no chained or colliding relocation")
    require((unchangedEscaped intersect (locals.toSet++remotes.toSet)).isEmpty,"no unchanged-path collision")
    val mapping=pairs.map(p=>p.localEscaped->p.remoteEscaped).toMap
    val changed=mutable.HashMap.empty[String,Long];val unchanged=mutable.HashMap.empty[String,Long]
    var nodes=0L;var infos=0L
    val raw=digest(high.circuit,limits.maxSerializedBytes)
    var canonical:Option[Digest]=None;var completed=false
    def evidence:Evidence=Evidence(raw,canonical,
      changed.toVector.sortBy(_._1).map{case(k,v)=>PathCount(k,mapping(k),v)},
      unchanged.toVector.sortBy(_._1),nodes,infos,completed)
    // Owner supplies a bounded append-only evidence writer. Persist raw identity
    // before any mutation candidate, and final/partial census even on failure.
    recordEvidence(evidence)
    def count(depth:Int):Unit={require(depth<=limits.maxDepth,"syntax depth cap");nodes+=1;require(nodes<=limits.maxSyntaxNodes,"syntax node cap")}
    def filename(i:FileInfo):(String,String)={
      val (file,line,column)=i.split
      require(line!=null && column!=null && line.nonEmpty && column.nonEmpty,"only exact high filename line:column Info")
      val suffix=" "+line+":"+column
      require(i.escaped==file+suffix,"exact original filename/suffix decomposition")
      token(file);(file,suffix)
    }
    def info(i:Info,depth:Int):Info={
      require(depth<=limits.maxDepth,"Info depth cap");infos+=1;require(infos<=limits.maxInfoNodes,"Info node cap")
      i match{
        case NoInfo=>NoInfo
        case f:FileInfo if f.getClass==classOf[FileInfo]=>
          val(file,suffix)=filename(f)
          mapping.get(file) match{
            case Some(to)=>changed(file)=changed.getOrElse(file,0L)+1;FileInfo.fromEscaped(to+suffix)
            case None=>require(unchangedEscaped(file),"unknown FileInfo filename: "+file)
              unchanged(file)=unchanged.getOrElse(file,0L)+1;f
          }
        case m:MultiInfo if m.getClass==classOf[MultiInfo]=>
          // Do not call flatten/compressInfo or varargs apply: structure/order
          // and explicit NoInfo entries must be retained exactly.
          new MultiInfo(m.infos.map(x=>info(x,depth+1)))
        case _=>throw new IllegalArgumentException("unapproved Info implementation: "+i.getClass.getName)
      }
    }
    def stmt(s:Statement,depth:Int):Statement={
      count(depth);require(statements(s.getClass.getName),"unapproved statement implementation: "+s.getClass.getName)
      // Official Block.mapStmt flattens nested Blocks and drops EmptyStmt.
      // Copy its exact ordered children instead: no non-Info normalization.
      s match {
        case b:Block=>b.copy(stmts=b.stmts.map(x=>stmt(x,depth+1)))
        case _=>s.mapStmt(x=>stmt(x,depth+1)).mapInfo(x=>info(x,depth+1))
      }
    }
    def port(p:Port,depth:Int):Port={count(depth);require(p.getClass==classOf[Port]);p.copy(info=info(p.info,depth+1))}
    def module(m:DefModule,depth:Int):DefModule={
      count(depth)
      m match{
        case x:Module if x.getClass==classOf[Module]=>x.copy(info=info(x.info,depth+1),ports=x.ports.map(p=>port(p,depth+1)),body=stmt(x.body,depth+1))
        case x:ExtModule if x.getClass==classOf[ExtModule]=>x.copy(info=info(x.info,depth+1),ports=x.ports.map(p=>port(p,depth+1)))
        case _=>throw new IllegalArgumentException("unapproved module implementation: "+m.getClass.getName)
      }
    }
    var primaryFailure:Throwable=null
    try {
    count(0)
    val rebound=high.circuit.copy(info=info(high.circuit.info,1),modules=high.circuit.modules.map(m=>module(m,1)))

    // Independent paired walk checks every product field, not serialized text.
    // Expressions, types, widths, parameters and any opaque object must retain
    // exact identity. Only standard syntax containers and Info can differ.
    def verify(a:Any,b:Any,depth:Int):Unit={
      require(depth<=limits.maxDepth*3+8,"paired verification depth cap")
      if(!same(a,b)) (a,b)match{
        case(x:FileInfo,y:FileInfo)=>val(f,s)=filename(x);require(y.escaped==mapping.getOrElse(f,f)+s)
        case(x:MultiInfo,y:MultiInfo)=>verify(x.infos,y.infos,depth+1)
        case(x:Seq[_],y:Seq[_])=>require(x.size==y.size,"unchanged ordered field length");x.iterator.zip(y.iterator).foreach{case(v,w)=>verify(v,w,depth+1)}
        case(x:Product,y:Product) if (x.isInstanceOf[Circuit]||x.isInstanceOf[DefModule]||x.isInstanceOf[Port]||x.isInstanceOf[Statement])=>
          require(x.getClass==y.getClass && x.productArity==y.productArity,"same syntax node type")
          x.productIterator.zip(y.productIterator).foreach{case(v,w)=>verify(v,w,depth+1)}
        case(x:String,y:String)=>require(x==y,"unchanged non-Info text")
        case(x:java.lang.Number,y:java.lang.Number)=>require(x.getClass==y.getClass && x==y,"unchanged scalar")
        case(x:java.lang.Boolean,y:java.lang.Boolean)=>require(x==y,"unchanged scalar")
        case _=>throw new IllegalArgumentException("changed non-Info field or opaque object")
      }
    }
    verify(high.circuit,rebound,0)
    canonical=Some(digest(rebound,limits.maxSerializedBytes))
    require(canonical.get.sha256==expectedRemoteHighSha256,"fixed remote full high identity; no fallback or learned expected hash")
    val state=high.copy(circuit=rebound)
    require(state.annotations eq high.annotations,"same original annotation objects/order")
    require(state.renames eq high.renames,"same original rename option")
    completed=true
    Result(state,raw,canonical.get,changed.toVector.sortBy(_._1).map{case(k,v)=>PathCount(k,mapping(k),v)},
      unchanged.toVector.sortBy(_._1),nodes,infos)
    } catch {case t:Throwable=>primaryFailure=t;throw t}
    finally {
      try recordEvidence(evidence)
      catch {case t:Throwable=>if(primaryFailure!=null)primaryFailure.addSuppressed(t) else throw t}
    }
  }
}

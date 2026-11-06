package chiseltest.simulator

import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Path,Paths,StandardOpenOption}
import java.security.MessageDigest
import org.json4s._
import org.json4s.native.JsonMethods

/** Passive evidence from this JVM, never from the supervising Python process.
  * No Treadle/native API calls. This observes mappings at one bounded interval;
  * the owning verifier must check actual identities and required mapped objects.
  */
object ActualJvmProcessObservation {
  private def bounded(path:Path,cap:Int):Array[Byte]={
    val in=Files.newInputStream(path)
    val out=new java.io.ByteArrayOutputStream()
    val buffer=new Array[Byte](8192)
    try{
      var n=in.read(buffer)
      while(n != -1){require(out.size().toLong+n<=cap,s"observation cap: $path");out.write(buffer,0,n);n=in.read(buffer)}
      out.toByteArray
    }finally{in.close()}
  }
  private def hash(bytes:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(bytes).map(b=>f"${b&255}%02x").mkString
  private def identity(bytes:Array[Byte]):(Long,String)={
    val line=new String(bytes,UTF_8);val end=line.lastIndexOf(')');val begin=line.indexOf('(')
    require(begin>0 && end>begin,"complete /proc/self/stat comm field")
    val pid=line.substring(0,begin).trim.toLong
    val fields=line.substring(end+1).trim.split("\\s+")
    require(fields.length>=20 && fields(19).matches("[0-9]+"),"stat starttime field 22")
    pid->fields(19)
  }
  def capture(output:Path,label:String):Unit={
    require(label.matches("[a-z][a-z0-9_]{0,63}"),"bounded observation label")
    require(Files.isDirectory(output) && !Files.isSymbolicLink(output),"existing owned observation directory")
    val prefix="ACTUAL_JVM_"+label
    def save(suffix:String,bytes:Array[Byte]):Unit={
      Files.write(output.resolve(prefix+suffix),bytes,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);()
    }
    val beforeNanos=System.nanoTime()
    val pid=java.lang.ProcessHandle.current().pid()
    val before=bounded(Paths.get("/proc/self/stat"),16*1024);save(".stat.before",before)
    val exe=Files.readSymbolicLink(Paths.get("/proc/self/exe")).toString
    val maps=bounded(Paths.get("/proc/self/maps"),4*1024*1024);save(".maps",maps)
    val environment=System.getenv()
    val names=scala.collection.mutable.Set("LD_PRELOAD","LD_LIBRARY_PATH","LD_AUDIT","JAVA_TOOL_OPTIONS","_JAVA_OPTIONS","JDK_JAVA_OPTIONS","CLASSPATH")
    val iterator=environment.keySet().iterator()
    while(iterator.hasNext){val key=iterator.next();if(key.startsWith("LD_"))names+=key}
    val env=JObject(names.toVector.sorted.map(n=>n->Option(environment.get(n)).map(JString).getOrElse(JNull)).toList)
    val envBytes=JsonMethods.compact(JsonMethods.render(env)).getBytes(UTF_8)
    require(envBytes.length<=64*1024,"bounded loader environment evidence")
    val after=bounded(Paths.get("/proc/self/stat"),16*1024);save(".stat.after",after)
    val beforeIdentity=identity(before);val afterIdentity=identity(after)
    val metadata=JObject(List(
      "schema"->JString("ACTUAL_CURRENT_JVM_PASSIVE_PROCESS_OBSERVATION_V1"),
      "label"->JString(label),"pid"->JInt(pid),"startTicks"->JString(beforeIdentity._2),
      "exeSymlinkTarget"->JString(exe),"observationStartMonotonicNanos"->JInt(beforeNanos),
      "observationEndMonotonicNanos"->JInt(System.nanoTime()),"loaderEnvironment"->env,
      "mapsFile"->JString(prefix+".maps"),"mapsBytes"->JInt(maps.length),"mapsSha256"->JString(hash(maps)),
      "statBeforeSha256"->JString(hash(before)),"statAfterSha256"->JString(hash(after)),
      "sameProcessAcrossObservation"->JBool(beforeIdentity==afterIdentity && beforeIdentity._1==pid),
      "scope"->JString("PASSIVE_CURRENT_PROCESS_MAPPING_EVIDENCE_NOT_NATIVE_OR_SCHEDULER_QUALIFICATION")))
    val bytes=(JsonMethods.compact(JsonMethods.render(metadata))+"\n").getBytes(UTF_8)
    require(bytes.length<=128*1024,"bounded observation metadata");save(".json",bytes)
    require(beforeIdentity==afterIdentity && beforeIdentity._1==pid,"actual JVM process identity remained stable")
  }
}

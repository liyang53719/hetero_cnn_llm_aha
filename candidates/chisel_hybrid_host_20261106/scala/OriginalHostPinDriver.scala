package chiseltest.simulator

import java.io.{BufferedInputStream,BufferedOutputStream,DataInputStream,DataOutputStream,EOFException}
import java.nio.{ByteBuffer,ByteOrder}
import java.nio.file.{Files,Path}
import java.security.MessageDigest
import java.util.concurrent.{Callable,FutureTask,TimeUnit}

/** Actual pin endpoint for the returned original Host TreadleTester.
  * There is no Scala memory model or AXI reconstruction here: the byte-identical
  * original full C++ driver owns all memory, bursts, handshakes and observation.
  * One original d.eval() -> one complete pin batch -> one evaluateCircuit().
  * Complete inputs, including reset and clock, are sampled before evaluation.
  * The bridge neither calls step/peek nor injects a DUT output/internal signal.
  */
object OriginalHostPinDriver {
  import OriginalHostPorts._
  final case class Plan(binary:Path,runtime:Path,output:Path,log:Path,profile:Int,
    maxActiveCycles:Long,wallSeconds:Long,processReceipt:Path)
  final case class Report(engine:String,frames:Long,risingEdges:Long,fallingEdges:Long,
    completeInputOutputTraceSha256:String,driverExit:Int,finalRequested:Boolean,
    binarySha256:String,runtimeSha256:String,logSha256:String,
    transport:String="PIN_ONLY_NO_HOST_RTL_OR_ARITHMETIC",numericalPass:Boolean=false,
    actualChildPid:Long=0L,actualChildStartTicks:String="",actualDriverArgv:Vector[String]=Vector.empty)
  private def serve(session:OriginalHostTreadleBinding.Session,child:Process,maxFrames:Long):Report=
    OriginalHostFrameTransport.serve(session.tester.engine,child,maxFrames)

  /** Caller retains its enclosing owner lease/supervisor and resource caps.
    * This method also bounds blocking IPC and joins/kills its exact child.
    * Returned result is execution/transport evidence only, never block PASS.
    */
  def run(session:OriginalHostTreadleBinding.Session,plan:Plan,gate:HybridExecutionGate):Report={
    require(plan.maxActiveCycles>0 && plan.maxActiveCycles<=1000000000L,"unchanged driver watchdog domain")
    require(plan.wallSeconds>0 && plan.wallSeconds<=7L*24*3600,"finite admitted wall bound")
    require(plan.output.isAbsolute && plan.log.isAbsolute && !Files.exists(plan.output) && !Files.exists(plan.log),"fresh output and log")
    gate.requireDriverLaunch(plan.binary,plan.runtime,plan.profile)
    gate.requireStartupDriverAdmission(session.prepared.pins,session.startupAudit)
    require(plan.processReceipt.isAbsolute && !Files.exists(plan.processReceipt),"fresh concrete child identity receipt")
    val binaryPin=HybridExecutionGate.hash(plan.binary);val runtimePin=HybridExecutionGate.hash(plan.runtime)
    val builder=new ProcessBuilder(plan.binary.toString,plan.runtime.toString,plan.output.toString,plan.maxActiveCycles.toString)
    builder.redirectError(plan.log.toFile)
    val child=builder.start()
    var failure:Throwable=null
    val task=new FutureTask[Report](new Callable[Report]{def call():Report=session.withEngine(gate) {serve(session,child,4L*plan.maxActiveCycles+64L)}})
    val thread=new Thread(task,"original-host-full-pin-transport");thread.setDaemon(true);thread.start()
    try {
      val childStat=Files.readString(java.nio.file.Paths.get("/proc/"+child.pid()+"/stat"))
      val childStart=childStat.substring(childStat.lastIndexOf(')')+2).trim.split(" +")(19)
      require(childStart.matches("[0-9]+"),"actual child start tick")
      import org.json4s._
      import org.json4s.native.JsonMethods
      import scala.jdk.CollectionConverters._
      val command=builder.command().asScala.toVector
      val popen=JObject(List("schema"->JString("ACTUAL_ORIGINAL_HOST_PIN_DRIVER_POPEN_V1"),
        "pid"->JInt(child.pid()),"parentPid"->JInt(ProcessHandle.current().pid()),"childStartTicks"->JString(childStart),
        "argv"->JArray(command.map(JString).toList),"binarySha256"->JString(binaryPin),"runtimeSha256"->JString(runtimePin)))
      Files.writeString(plan.processReceipt,JsonMethods.compact(JsonMethods.render(popen)),java.nio.charset.StandardCharsets.UTF_8,java.nio.file.StandardOpenOption.CREATE_NEW)
      val result=task.get(plan.wallSeconds,TimeUnit.SECONDS)
      require(child.waitFor(30,TimeUnit.SECONDS),"original driver exit after full EOF")
      require(child.exitValue()==0,"original driver completed all handshakes/dumps/drain")
      require(HybridExecutionGate.hash(plan.binary)==binaryPin && HybridExecutionGate.hash(plan.runtime)==runtimePin,"pre/post binary/runtime identity")
      result.copy(driverExit=0,binarySha256=binaryPin,runtimeSha256=runtimePin,logSha256=HybridExecutionGate.hash(plan.log),actualChildPid=child.pid(),actualChildStartTicks=childStart,actualDriverArgv=command)
    }catch{case t:Throwable=>failure=t;throw t}
    finally {
      // Do not finish Treadle concurrently with an in-flight native edge.
      if(child.isAlive){child.destroy();if(!child.waitFor(2,TimeUnit.SECONDS)){child.destroyForcibly();child.waitFor(5,TimeUnit.SECONDS)}}
      try child.getOutputStream.close() catch {case _:Throwable=>()}
      try child.getInputStream.close() catch {case _:Throwable=>()}
      try child.getErrorStream.close() catch {case _:Throwable=>()}
      thread.join(5000)
      if(thread.isAlive || child.isAlive){
        val t=new IllegalStateException("transport/driver cleanup incomplete; outer supervisor required")
        if(failure!=null)failure.addSuppressed(t)else throw t
      }
    }
  }
}

// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
/** Emit the original production top, not a substituted control harness.
  * Capacity remains 1024. No job is launched; M128 is not an elaboration capacity.
  */
object ProductionHostStructure extends App {
  require(args.length==1,"one fresh CHIRRTL directory required")
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  val s=QwenBlockShape(hidden=1536,ffn=8960,heads=12,kvHeads=2,headDim=128,
    maxTokens=1024,retainedMatrix=true,matrixColumns=256)
  println("PRODUCTION_HOST_CHIRRTL_BEGIN")
  val text=ChiselStage.emitCHIRRTL(new HostBlockTop(s,weightReadBeats=16,
    pipelined=true,burstWrites=true,commitTailRead=false,overlapSilu=false,
    enableTransposedDown=true,enableResidentFfn=true,enablePublic21QkvReduction=true,
    numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2))
  val byteCount=text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length
  val moduleCount="(?m)^  module ".r.findAllMatchIn(text).length
  val externalCount="(?m)^  extmodule ".r.findAllMatchIn(text).length
  val topName="(?m)^circuit ([A-Za-z0-9_]+)\\s*:".r.findFirstMatchIn(text).map(_.group(1)).getOrElse("MISSING")
  println(s"PRODUCTION_HOST_CHIRRTL_SIZE bytes=$byteCount modules=$moduleCount extmodules=$externalCount top=$topName")
  require(byteCount<=48*1024*1024,"CHIRRTL 48MiB cap")
  Files.writeString(out.resolve("HostBlockTop.fir"),text)
  println("PRODUCTION_HOST_CHIRRTL_WRITTEN")
}

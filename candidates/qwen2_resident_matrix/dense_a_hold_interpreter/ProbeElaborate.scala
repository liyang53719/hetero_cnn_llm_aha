// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files, Paths}

/** Report the actual classes loaded in the selected ScalaTest JVM. */
object InterpreterOrigins {
  def emit():Unit={
    val names=Seq("treadle2.TreadleTester","firrtl2.stage.FirrtlStage",
      "chisel3.RawModule","org.json4s.JValue","com.sun.jna.Native",
      "org.scalatest.tools.Runner","scala.Predef$")
    names.foreach{name=>
      val clazz=Class.forName(name,false,getClass.getClassLoader)
      val location=clazz.getProtectionDomain.getCodeSource.getLocation.toURI.toASCIIString
      println(s"AHOLD_CLASS_ORIGIN $name $location")
    }
  }
}

/** Fresh original CHIRRTL for the selected real owner and its observation IO. */
object ProbeElaborate extends App {
  require(args.length==1,"one fresh structural evidence directory required")
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  Files.writeString(out.resolve("owner.fir"),ChiselStage.emitCHIRRTL(
    new TransposedDenseDownOwner(burstWrites=true,enableFfnTiles=true,
      enableFfnWindow=true,enableFfnDrain=true,enableKWindow=true,
      enableDenseDrain=true,enableRawKv=true,enableAHold=true)))
  Files.writeString(out.resolve("probe.fir"),ChiselStage.emitCHIRRTL(new AHoldProbe(true)))
}

// SPDX-License-Identifier: Apache-2.0
package heteronpu.experimental.contracttests

import chisel3._
import chisel3.reflect.DataMirror
import heteronpu.experimental._
import gemmini.{HeteroBF16FmaMul, HeteroBF16FmaPost, HeteroBF16FmaRound}
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path, Paths, StandardOpenOption}
import java.security.{MessageDigest, Permission}
import java.util.concurrent.atomic.AtomicInteger

/** One owner frontend elaboration only. No simulation, firtool or RTL emission. */
object StrictFp32LaneChirrtl {
  private final class NoExternalTools extends SecurityManager {
    val execAttempts = new AtomicInteger(0)
    val networkAttempts = new AtomicInteger(0)
    val replacementAttempts = new AtomicInteger(0)
    override def checkPermission(p: Permission): Unit = {
      if (p.getName == "setSecurityManager") {
        replacementAttempts.incrementAndGet()
        throw new SecurityException("elaboration guard replacement forbidden")
      }
    }
    override def checkPermission(p: Permission, context: AnyRef): Unit = checkPermission(p)
    override def checkExec(command: String): Unit = {
      execAttempts.incrementAndGet()
      throw new SecurityException("external process forbidden during CHIRRTL elaboration")
    }
    private def denyNetwork(): Unit = {
      networkAttempts.incrementAndGet()
      throw new SecurityException("network forbidden during CHIRRTL elaboration")
    }
    override def checkConnect(host: String, port: Int): Unit = denyNetwork()
    override def checkConnect(host: String, port: Int, context: AnyRef): Unit = denyNetwork()
    override def checkListen(port: Int): Unit = denyNetwork()
    override def checkAccept(host: String, port: Int): Unit = denyNetwork()
    override def checkMulticast(address: java.net.InetAddress): Unit = denyNetwork()
  }

  private def canonicalProperty(name: String): Path = {
    val p = Paths.get(Option(System.getProperty(name)).getOrElse(
      throw new IllegalArgumentException("missing fixed path property")))
    require(p.isAbsolute && p.normalize == p && p.toRealPath() == p, "canonical fixed root")
    p
  }
  private def sourceBound(c: Class[_], root: Path): Unit = {
    val location = c.getProtectionDomain.getCodeSource.getLocation.toURI
    require(Paths.get(location).toRealPath() == root, "wrong loaded class root: " + c.getName)
  }

  def main(args: Array[String]): Unit = {
    require(args.isEmpty, "no variable elaboration arguments")
    require(System.getSecurityManager == null, "unexpected pre-existing security manager")
    val guard = new NoExternalTools
    System.setSecurityManager(guard) // Unsupported/refused installation is a hard failure.
    require(System.getSecurityManager eq guard, "elaboration guard not installed")
    val inputRoot = canonicalProperty("chunk.expected.input.classes")
    val emitterRoot = canonicalProperty("chunk.expected.emitter.classes")
    val irRoot = canonicalProperty("chunk.expected.ir.root")
    sourceBound(classOf[StrictFp32MatrixLane], inputRoot)
    sourceBound(classOf[HeteroFullFp32FmaPre], inputRoot)
    sourceBound(classOf[HeteroBF16FmaMul], inputRoot)
    sourceBound(classOf[HeteroBF16FmaPost], inputRoot)
    sourceBound(classOf[HeteroBF16FmaRound], inputRoot)
    sourceBound(getClass, emitterRoot)
    var constructors = 0
    var leaves = 0
    def leaf(d: Data, width: Int, direction: ActualDirection): Unit = {
      require(d.getWidth == width, "bound IO width mismatch")
      require(DataMirror.directionOf(d) == direction, "bound IO direction mismatch")
      leaves += 1
    }
    def in(d: Data, width: Int): Unit = leaf(d, width, ActualDirection.Input)
    def out(d: Data, width: Int): Unit = leaf(d, width, ActualDirection.Output)
    val text = circt.stage.ChiselStage.emitCHIRRTL({
      constructors += 1
      require(constructors == 1, "exactly one isolated lane constructor")
      val m = new StrictFp32MatrixLane
      in(m.clock, 1)
      in(m.reset, 1)
      in(m.io.request.valid, 1)
      out(m.io.request.ready, 1)
      in(m.io.request.bits.tag, 32)
      in(m.io.request.bits.mode, 2)
      in(m.io.request.bits.a, 32)
      in(m.io.request.bits.b, 32)
      in(m.io.request.bits.acc, 32)
      in(m.io.result.ready, 1)
      out(m.io.result.valid, 1)
      out(m.io.result.bits.tag, 32)
      out(m.io.result.bits.mode, 2)
      out(m.io.result.bits.status, 3)
      out(m.io.result.bits.product, 32)
      out(m.io.result.bits.productValid, 1)
      out(m.io.result.bits.value, 32)
      out(m.io.result.bits.valueValid, 1)
      out(m.io.result.bits.accCommit, 1)
      out(m.io.result.bits.mulFlags, 5)
      out(m.io.result.bits.mulFlagsValid, 1)
      out(m.io.result.bits.addFlags, 5)
      out(m.io.result.bits.addFlagsValid, 1)
      out(m.io.result.bits.fmaFlags, 5)
      out(m.io.result.bits.fmaFlagsValid, 1)
      out(m.io.result.bits.passesCompleted, 2)
      out(m.io.busy, 1)
      require(m.io.request.bits.getWidth == 130 && m.io.result.bits.getWidth == 124,
        "exact request/response payloads")
      require(m.pre.io.a.getWidth == 32 && m.pre.io.b.getWidth == 32 && m.pre.io.c.getWidth == 32,
        "full FP32 inputs, not BF16 width")
      require(m.pre.io.mulAddA.getWidth == 24 && m.pre.io.mulAddB.getWidth == 24 &&
        m.pre.io.mulAddC.getWidth == 48 && m.pre.io.meta.getWidth == 54, "Pre stage widths")
      require(m.mul.io.mulAddA.getWidth == 24 && m.mul.io.mulAddB.getWidth == 24 &&
        m.mul.io.mulAddC.getWidth == 48 && m.mul.io.mulAddResult.getWidth == 49, "one Mul stage widths")
      require(m.post.io.meta.getWidth == 54 && m.post.io.mulAddResult.getWidth == 49 &&
        m.post.io.raw.getWidth == 41 && m.post.io.invalid.getWidth == 1, "Post stage widths")
      require(m.round.io.raw.getWidth == 41 && m.round.io.invalid.getWidth == 1 &&
        m.round.io.out.getWidth == 32 && m.round.io.exceptionFlags.getWidth == 5, "Round stage widths")
      require(m.preA.getWidth == 24 && m.preB.getWidth == 24 && m.preC.getWidth == 48 &&
        m.preMeta.getWidth == 54 && m.mulValue.getWidth == 49 && m.mulMeta.getWidth == 54 &&
        m.postRaw.getWidth == 41 && m.postInvalid.getWidth == 1, "stage register widths")
      require(leaves == 27, "complete fixed top IO inventory")
      m
    }, Array.empty[String])
    require(constructors == 1 && leaves == 27, "frontend checks did not complete")
    require(System.getSecurityManager eq guard, "guard changed during elaboration")
    require(guard.execAttempts.get == 0 && guard.networkAttempts.get == 0 &&
      guard.replacementAttempts.get == 0, "forbidden operation attempted")
    val lines = text.linesIterator.map(_.trim).toVector
    require(lines.headOption.exists(_.startsWith("FIRRTL version ")), "CHIRRTL version header")
    require(lines.count(_.startsWith("circuit StrictFp32MatrixLane :")) == 1, "circuit top")
    require(lines.count(_.startsWith("module ")) == 9 && lines.count(_.startsWith("inst ")) == 8,
      "nine modules and eight edges, not a second chain")
    require(!lines.exists(x => Seq("extmodule ", "mem ", "cmem ", "smem ").exists(x.startsWith)),
      "no external or memory instances")
    // Parent performs exact module-name, per-parent edge, all port type and one-mul checks.
    val bytes = text.getBytes(StandardCharsets.UTF_8)
    require(bytes.nonEmpty && bytes.length <= 2 * 1024 * 1024, "bounded CHIRRTL artifact")
    val target = irRoot.resolve("StrictFp32MatrixLane.fir")
    Files.write(target, bytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
    val digest = MessageDigest.getInstance("SHA-256").digest(bytes).map(b => f"${b & 255}%02x").mkString
    println(s"""{"status":"PASS_ISOLATED_LANE_CHIRRTL_FRONTEND_ONLY","constructors":$constructors,"io_leaf_checks":$leaves,"request_payload_bits":130,"response_payload_bits":124,"stage_width_checks":true,"sources_bound":true,"guard_locked":true,"external_exec_attempts":0,"network_attempts":0,"guard_replacement_attempts":0,"modules":9,"instances":8,"fir_bytes":${bytes.length},"fir_sha256":"$digest","RTL_generated":false,"actual_handshake_tested":false,"numerical_tested":false,"old_cpp_flags_integration_blocker":true}""")
  }
}

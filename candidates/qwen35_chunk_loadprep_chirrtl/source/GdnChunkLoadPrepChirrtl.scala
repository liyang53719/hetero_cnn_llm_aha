// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.contracttests

import chisel3._
import chisel3.reflect.DataMirror
import heteronpu.continuous._
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path, Paths, StandardOpenOption}
import java.security.{MessageDigest, Permission}
import java.util.concurrent.atomic.AtomicInteger

/** One owner frontend elaboration only. No simulation, firtool or RTL emission. */
object GdnChunkLoadPrepChirrtl {
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
    sourceBound(classOf[GdnChunkLoadPrepOwner], inputRoot)
    sourceBound(classOf[GdnChunkJob], inputRoot)
    sourceBound(classOf[MemoryRequest], inputRoot)
    sourceBound(classOf[GdnScalarClient], inputRoot)
    sourceBound(classOf[ScalarRequest], inputRoot)
    sourceBound(GdnChunkAddressPlan.getClass, inputRoot)
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
    def receipt(r: GdnChunkStageReceipt, incoming: Boolean): Unit = {
      def port(d: Data, width: Int): Unit = if (incoming) in(d, width) else out(d, width)
      port(r.tag, 32); port(r.expectedGeneration, 32); port(r.head, 4); port(r.chunk, 1)
      port(r.phase, 5); port(r.status, 8); port(r.scratchAckBytes, 64)
      port(r.outputAckBytes, 64); port(r.stateAckBytes, 64); port(r.drained, 1)
    }
    val text = circt.stage.ChiselStage.emitCHIRRTL({
      constructors += 1
      require(constructors == 1, "exactly one owner constructor")
      val m = new GdnChunkLoadPrepOwner
      in(m.clock, 1); in(m.reset, 1)
      in(m.io.job.valid, 1); out(m.io.job.ready, 1)
      val j = m.io.job.bits
      val c = j.context
      in(c.tag, 32); in(c.tokens, 16); in(c.cold, 1); in(c.expectedGeneration, 32)
      in(c.vectorPolicy, 1); in(c.input, 64); in(c.stateIn, 64); in(c.stateOut, 64)
      in(c.output, 64); in(c.scratch, 64); in(j.head, 16); in(j.chunk, 16)
      val prep = j.prepReady
      in(prep.tag, 32); in(prep.expectedGeneration, 32); in(prep.tokens, 16)
      in(prep.input, 64); in(prep.status, 8); in(prep.writeBytes, 64)
      in(prep.preparedComplete, 1); in(prep.drained, 1); in(prep.recurrentMode, 1)
      receipt(j.initialReady, true); receipt(j.previousStateReady, true); receipt(j.previousOutputReady, true)
      in(m.io.committed.valid, 1); in(m.io.committed.generation, 32); in(m.io.committed.state, 64)
      in(m.io.memory.ready, 1); out(m.io.memory.valid, 1)
      val request = m.io.memory.bits
      out(request.write, 1); out(request.address, 64); out(request.data, 512)
      out(request.mask, 64); out(request.tag, 64)
      out(m.io.response.ready, 1); in(m.io.response.valid, 1)
      in(m.io.response.bits.data, 512); in(m.io.response.bits.tag, 64); in(m.io.response.bits.error, 1)
      in(m.io.scalar.request.ready, 1); out(m.io.scalar.request.valid, 1)
      out(m.io.scalar.request.bits.op, 3); out(m.io.scalar.request.bits.a, 32); out(m.io.scalar.request.bits.b, 32)
      out(m.io.scalar.result.ready, 1); in(m.io.scalar.result.valid, 1)
      in(m.io.scalar.result.bits, 32); in(m.io.scalar.error, 1)
      in(m.io.done.ready, 1); out(m.io.done.valid, 1)
      val result = m.io.done.bits
      receipt(result.receipt, false)
      out(result.readBytes, 64); out(result.addRequests, 7); out(result.addResults, 7)
      out(result.cycles, 64); out(result.stageComplete, 1)
      out(m.io.resetRequired, 1)
      require(leaves == 97, "complete fixed IO leaf inventory")
      m
    }, Array.empty[String])
    require(constructors == 1 && leaves == 97, "frontend checks did not complete")
    require(System.getSecurityManager eq guard, "guard changed during elaboration")
    require(guard.execAttempts.get == 0 && guard.networkAttempts.get == 0 &&
      guard.replacementAttempts.get == 0, "forbidden operation attempted")
    val lines = text.linesIterator.map(_.trim).toVector
    require(lines.headOption.exists(_.startsWith("FIRRTL version ")), "CHIRRTL version header")
    require(lines.count(_.startsWith("circuit GdnChunkLoadPrepOwner :")) == 1, "circuit top")
    require(lines.count(_.startsWith("module ")) == 1 &&
      lines.count(_.startsWith("module GdnChunkLoadPrepOwner :")) == 1, "single owner module")
    require(!lines.exists(x => Seq("extmodule ", "inst ", "mem ", "cmem ", "smem ").exists(x.startsWith)),
      "no external, child module or memory instances")
    val bytes = text.getBytes(StandardCharsets.UTF_8)
    require(bytes.nonEmpty && bytes.length <= 2 * 1024 * 1024, "bounded CHIRRTL artifact")
    val target = irRoot.resolve("GdnChunkLoadPrepOwner.fir")
    Files.write(target, bytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
    val digest = MessageDigest.getInstance("SHA-256").digest(bytes).map(b => f"${b & 255}%02x").mkString
    println(s"""{"status":"PASS_OWNER_CHIRRTL_FRONTEND_ONLY","constructors":$constructors,"io_leaf_checks":$leaves,"sources_bound":true,"guard_locked":true,"external_exec_attempts":0,"network_attempts":0,"guard_replacement_attempts":0,"modules":1,"instances":0,"fir_bytes":${bytes.length},"fir_sha256":"$digest","RTL_generated":false,"actual_handshake_tested":false,"numerical_tested":false}""")
  }
}

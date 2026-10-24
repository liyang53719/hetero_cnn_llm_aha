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
object GdnChunkDerivedChirrtl {
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
    sourceBound(classOf[GdnChunkDerivedAndPairOwner], inputRoot)
    sourceBound(classOf[GdnChunkJob], inputRoot)
    sourceBound(classOf[MemoryRequest], inputRoot)
    sourceBound(classOf[GdnScalarClient], inputRoot)
    sourceBound(classOf[ScalarRequest], inputRoot)
    sourceBound(classOf[ElementwiseLoanPort], inputRoot)
    sourceBound(classOf[GdnChunkLoadPrepResult], inputRoot)
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
    val text = circt.stage.ChiselStage.emitCHIRRTL({
      constructors += 1
      require(constructors == 1, "exactly one owner constructor")
      val m = new GdnChunkDerivedAndPairOwner
      in(m.clock, 1)
      in(m.reset, 1)
      in(m.io.job.valid, 1)
      out(m.io.job.ready, 1)
      in(m.io.job.bits.context.tag, 32)
      in(m.io.job.bits.context.tokens, 16)
      in(m.io.job.bits.context.cold, 1)
      in(m.io.job.bits.context.expectedGeneration, 32)
      in(m.io.job.bits.context.vectorPolicy, 1)
      in(m.io.job.bits.context.input, 64)
      in(m.io.job.bits.context.stateIn, 64)
      in(m.io.job.bits.context.stateOut, 64)
      in(m.io.job.bits.context.output, 64)
      in(m.io.job.bits.context.scratch, 64)
      in(m.io.job.bits.head, 16)
      in(m.io.job.bits.chunk, 16)
      in(m.io.job.bits.phase1Context.tag, 32)
      in(m.io.job.bits.phase1Context.tokens, 16)
      in(m.io.job.bits.phase1Context.cold, 1)
      in(m.io.job.bits.phase1Context.expectedGeneration, 32)
      in(m.io.job.bits.phase1Context.vectorPolicy, 1)
      in(m.io.job.bits.phase1Context.input, 64)
      in(m.io.job.bits.phase1Context.stateIn, 64)
      in(m.io.job.bits.phase1Context.stateOut, 64)
      in(m.io.job.bits.phase1Context.output, 64)
      in(m.io.job.bits.phase1Context.scratch, 64)
      in(m.io.job.bits.phase1Ready.receipt.tag, 32)
      in(m.io.job.bits.phase1Ready.receipt.expectedGeneration, 32)
      in(m.io.job.bits.phase1Ready.receipt.head, 4)
      in(m.io.job.bits.phase1Ready.receipt.chunk, 1)
      in(m.io.job.bits.phase1Ready.receipt.phase, 5)
      in(m.io.job.bits.phase1Ready.receipt.status, 8)
      in(m.io.job.bits.phase1Ready.receipt.scratchAckBytes, 64)
      in(m.io.job.bits.phase1Ready.receipt.outputAckBytes, 64)
      in(m.io.job.bits.phase1Ready.receipt.stateAckBytes, 64)
      in(m.io.job.bits.phase1Ready.receipt.drained, 1)
      in(m.io.job.bits.phase1Ready.readBytes, 64)
      in(m.io.job.bits.phase1Ready.addRequests, 7)
      in(m.io.job.bits.phase1Ready.addResults, 7)
      in(m.io.job.bits.phase1Ready.cycles, 64)
      in(m.io.job.bits.phase1Ready.stageComplete, 1)
      in(m.io.committed.valid, 1)
      in(m.io.committed.generation, 32)
      in(m.io.committed.state, 64)
      in(m.io.memory.ready, 1)
      out(m.io.memory.valid, 1)
      out(m.io.memory.bits.write, 1)
      out(m.io.memory.bits.address, 64)
      out(m.io.memory.bits.data, 512)
      out(m.io.memory.bits.mask, 64)
      out(m.io.memory.bits.tag, 64)
      out(m.io.response.ready, 1)
      in(m.io.response.valid, 1)
      in(m.io.response.bits.data, 512)
      in(m.io.response.bits.tag, 64)
      in(m.io.response.bits.error, 1)
      in(m.io.scalar.request.ready, 1)
      out(m.io.scalar.request.valid, 1)
      out(m.io.scalar.request.bits.op, 3)
      out(m.io.scalar.request.bits.a, 32)
      out(m.io.scalar.request.bits.b, 32)
      out(m.io.scalar.result.ready, 1)
      in(m.io.scalar.result.valid, 1)
      in(m.io.scalar.result.bits, 32)
      in(m.io.scalar.error, 1)
      in(m.io.loan.request.ready, 1)
      out(m.io.loan.request.valid, 1)
      out(m.io.loan.request.bits.tag, 32)
      out(m.io.loan.request.bits.op, 3)
      out(m.io.loan.request.bits.a, 512)
      out(m.io.loan.request.bits.b, 512)
      out(m.io.loan.request.bits.inverse, 32)
      out(m.io.loan.result.ready, 1)
      in(m.io.loan.result.valid, 1)
      in(m.io.loan.result.bits.tag, 32)
      in(m.io.loan.result.bits.status, 8)
      in(m.io.loan.result.bits.value, 512)
      out(m.io.loan.abort, 1)
      out(m.io.loan.resetLoan, 1)
      in(m.io.loan.busy, 1)
      in(m.io.loan.resetRequired, 1)
      in(m.io.done.ready, 1)
      out(m.io.done.valid, 1)
      out(m.io.done.bits.receipt.tag, 32)
      out(m.io.done.bits.receipt.expectedGeneration, 32)
      out(m.io.done.bits.receipt.head, 4)
      out(m.io.done.bits.receipt.chunk, 1)
      out(m.io.done.bits.receipt.phase, 5)
      out(m.io.done.bits.receipt.status, 8)
      out(m.io.done.bits.receipt.scratchAckBytes, 64)
      out(m.io.done.bits.receipt.outputAckBytes, 64)
      out(m.io.done.bits.receipt.stateAckBytes, 64)
      out(m.io.done.bits.receipt.drained, 1)
      out(m.io.done.bits.decay.context.tag, 32)
      out(m.io.done.bits.decay.context.tokens, 16)
      out(m.io.done.bits.decay.context.cold, 1)
      out(m.io.done.bits.decay.context.expectedGeneration, 32)
      out(m.io.done.bits.decay.context.vectorPolicy, 1)
      out(m.io.done.bits.decay.context.input, 64)
      out(m.io.done.bits.decay.context.stateIn, 64)
      out(m.io.done.bits.decay.context.stateOut, 64)
      out(m.io.done.bits.decay.context.output, 64)
      out(m.io.done.bits.decay.context.scratch, 64)
      out(m.io.done.bits.decay.head, 4)
      out(m.io.done.bits.decay.chunk, 1)
      out(m.io.done.bits.decay.value, 32)
      out(m.io.done.bits.decay.valid, 1)
      out(m.io.done.bits.readBytes, 64)
      out(m.io.done.bits.expRequests, 12)
      out(m.io.done.bits.expResults, 12)
      out(m.io.done.bits.addRequests, 12)
      out(m.io.done.bits.addResults, 12)
      out(m.io.done.bits.mulRequests, 12)
      out(m.io.done.bits.mulResults, 12)
      out(m.io.done.bits.cycles, 64)
      out(m.io.done.bits.stageComplete, 1)
      out(m.io.resetRequired, 1)
      require(leaves == 117, "complete fixed IO leaf inventory")
      m
    }, Array.empty[String])
    require(constructors == 1 && leaves == 117, "frontend checks did not complete")
    require(System.getSecurityManager eq guard, "guard changed during elaboration")
    require(guard.execAttempts.get == 0 && guard.networkAttempts.get == 0 &&
      guard.replacementAttempts.get == 0, "forbidden operation attempted")
    val lines = text.linesIterator.map(_.trim).toVector
    require(lines.headOption.exists(_.startsWith("FIRRTL version ")), "CHIRRTL version header")
    require(lines.count(_.startsWith("circuit GdnChunkDerivedAndPairOwner :")) == 1, "circuit top")
    require(lines.count(_.startsWith("module ")) == 1 &&
      lines.count(_.startsWith("module GdnChunkDerivedAndPairOwner :")) == 1, "single owner module")
    require(!lines.exists(x => Seq("extmodule ", "inst ", "mem ", "cmem ", "smem ").exists(x.startsWith)),
      "no external, child module or memory instances")
    val bytes = text.getBytes(StandardCharsets.UTF_8)
    require(bytes.nonEmpty && bytes.length <= 2 * 1024 * 1024, "bounded CHIRRTL artifact")
    val target = irRoot.resolve("GdnChunkDerivedAndPairOwner.fir")
    Files.write(target, bytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
    val digest = MessageDigest.getInstance("SHA-256").digest(bytes).map(b => f"${b & 255}%02x").mkString
    println(s"""{"status":"PASS_OWNER_CHIRRTL_FRONTEND_ONLY","constructors":$constructors,"io_leaf_checks":$leaves,"sources_bound":true,"guard_locked":true,"external_exec_attempts":0,"network_attempts":0,"guard_replacement_attempts":0,"modules":1,"instances":0,"fir_bytes":${bytes.length},"fir_sha256":"$digest","RTL_generated":false,"actual_handshake_tested":false,"numerical_tested":false}""")
  }
}

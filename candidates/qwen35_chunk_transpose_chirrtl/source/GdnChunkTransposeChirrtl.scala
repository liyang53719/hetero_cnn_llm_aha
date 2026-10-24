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
object GdnChunkTransposeChirrtl {
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
    sourceBound(classOf[GdnChunkTransposeOwner], inputRoot)
    sourceBound(classOf[GdnChunkJob], inputRoot)
    sourceBound(classOf[MemoryRequest], inputRoot)
    sourceBound(classOf[GdnChunkDerivedAndPairResult], inputRoot)
    sourceBound(classOf[GdnChunkPrivateDecay], inputRoot)
    sourceBound(classOf[GdnChunkStageReceipt], inputRoot)
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
      val m = new GdnChunkTransposeOwner
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
      in(m.io.job.bits.phase2Ready.receipt.tag, 32)
      in(m.io.job.bits.phase2Ready.receipt.expectedGeneration, 32)
      in(m.io.job.bits.phase2Ready.receipt.head, 4)
      in(m.io.job.bits.phase2Ready.receipt.chunk, 1)
      in(m.io.job.bits.phase2Ready.receipt.phase, 5)
      in(m.io.job.bits.phase2Ready.receipt.status, 8)
      in(m.io.job.bits.phase2Ready.receipt.scratchAckBytes, 64)
      in(m.io.job.bits.phase2Ready.receipt.outputAckBytes, 64)
      in(m.io.job.bits.phase2Ready.receipt.stateAckBytes, 64)
      in(m.io.job.bits.phase2Ready.receipt.drained, 1)
      in(m.io.job.bits.phase2Ready.decay.context.tag, 32)
      in(m.io.job.bits.phase2Ready.decay.context.tokens, 16)
      in(m.io.job.bits.phase2Ready.decay.context.cold, 1)
      in(m.io.job.bits.phase2Ready.decay.context.expectedGeneration, 32)
      in(m.io.job.bits.phase2Ready.decay.context.vectorPolicy, 1)
      in(m.io.job.bits.phase2Ready.decay.context.input, 64)
      in(m.io.job.bits.phase2Ready.decay.context.stateIn, 64)
      in(m.io.job.bits.phase2Ready.decay.context.stateOut, 64)
      in(m.io.job.bits.phase2Ready.decay.context.output, 64)
      in(m.io.job.bits.phase2Ready.decay.context.scratch, 64)
      in(m.io.job.bits.phase2Ready.decay.head, 4)
      in(m.io.job.bits.phase2Ready.decay.chunk, 1)
      in(m.io.job.bits.phase2Ready.decay.value, 32)
      in(m.io.job.bits.phase2Ready.decay.valid, 1)
      in(m.io.job.bits.phase2Ready.readBytes, 64)
      in(m.io.job.bits.phase2Ready.expRequests, 12)
      in(m.io.job.bits.phase2Ready.expResults, 12)
      in(m.io.job.bits.phase2Ready.addRequests, 12)
      in(m.io.job.bits.phase2Ready.addResults, 12)
      in(m.io.job.bits.phase2Ready.mulRequests, 12)
      in(m.io.job.bits.phase2Ready.mulResults, 12)
      in(m.io.job.bits.phase2Ready.cycles, 64)
      in(m.io.job.bits.phase2Ready.stageComplete, 1)
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
      in(m.io.done.ready, 1)
      out(m.io.done.valid, 1)
      out(m.io.done.bits.phase3.tag, 32)
      out(m.io.done.bits.phase3.expectedGeneration, 32)
      out(m.io.done.bits.phase3.head, 4)
      out(m.io.done.bits.phase3.chunk, 1)
      out(m.io.done.bits.phase3.phase, 5)
      out(m.io.done.bits.phase3.status, 8)
      out(m.io.done.bits.phase3.scratchAckBytes, 64)
      out(m.io.done.bits.phase3.outputAckBytes, 64)
      out(m.io.done.bits.phase3.stateAckBytes, 64)
      out(m.io.done.bits.phase3.drained, 1)
      out(m.io.done.bits.phase4.tag, 32)
      out(m.io.done.bits.phase4.expectedGeneration, 32)
      out(m.io.done.bits.phase4.head, 4)
      out(m.io.done.bits.phase4.chunk, 1)
      out(m.io.done.bits.phase4.phase, 5)
      out(m.io.done.bits.phase4.status, 8)
      out(m.io.done.bits.phase4.scratchAckBytes, 64)
      out(m.io.done.bits.phase4.outputAckBytes, 64)
      out(m.io.done.bits.phase4.stateAckBytes, 64)
      out(m.io.done.bits.phase4.drained, 1)
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
      out(m.io.done.bits.phase3ReadBytes, 64)
      out(m.io.done.bits.phase4ReadBytes, 64)
      out(m.io.done.bits.cycles, 64)
      out(m.io.done.bits.phase3Complete, 1)
      out(m.io.done.bits.phase4Complete, 1)
      out(m.io.done.bits.stageComplete, 1)
      out(m.io.done.bits.drained, 1)
      out(m.io.done.bits.status, 8)
      out(m.io.resetRequired, 1)
      require(m.tile.length == 16 && m.tile.forall(_.getWidth == 512) && m.tile.getWidth == 8192,
        "exact 16x512-bit register tile, 1024 payload bytes")
      require(leaves == 109, "complete fixed IO leaf inventory")
      m
    }, Array.empty[String])
    require(constructors == 1 && leaves == 109, "frontend checks did not complete")
    require(System.getSecurityManager eq guard, "guard changed during elaboration")
    require(guard.execAttempts.get == 0 && guard.networkAttempts.get == 0 &&
      guard.replacementAttempts.get == 0, "forbidden operation attempted")
    val lines = text.linesIterator.map(_.trim).toVector
    require(lines.headOption.exists(_.startsWith("FIRRTL version ")), "CHIRRTL version header")
    require(lines.count(_.startsWith("circuit GdnChunkTransposeOwner :")) == 1, "circuit top")
    require(lines.count(_.startsWith("module ")) == 1 &&
      lines.count(_.startsWith("module GdnChunkTransposeOwner :")) == 1, "single owner module")
    require(!lines.exists(x => Seq("extmodule ", "inst ", "mem ", "cmem ", "smem ").exists(x.startsWith)),
      "no external, child module or memory instances")
    val tileDeclarations = lines.filter(x => x.startsWith("regreset tile :") || x.startsWith("reg tile :"))
    require(tileDeclarations.size == 1 && tileDeclarations.head.startsWith("regreset tile : UInt<512>[16], clock, reset, "),
      "exact reset register tile declaration, not a memory instance")
    val bytes = text.getBytes(StandardCharsets.UTF_8)
    require(bytes.nonEmpty && bytes.length <= 2 * 1024 * 1024, "bounded CHIRRTL artifact")
    val target = irRoot.resolve("GdnChunkTransposeOwner.fir")
    Files.write(target, bytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
    val digest = MessageDigest.getInstance("SHA-256").digest(bytes).map(b => f"${b & 255}%02x").mkString
    println(s"""{"status":"PASS_OWNER_CHIRRTL_FRONTEND_ONLY","constructors":$constructors,"io_leaf_checks":$leaves,"sources_bound":true,"guard_locked":true,"external_exec_attempts":0,"network_attempts":0,"guard_replacement_attempts":0,"modules":1,"instances":0,"register_tile_rows":16,"register_tile_row_bits":512,"register_tile_payload_bytes":1024,"fir_bytes":${bytes.length},"fir_sha256":"$digest","RTL_generated":false,"actual_handshake_tested":false,"numerical_tested":false}""")
  }
}

// SPDX-License-Identifier: Apache-2.0
package gemmini

import chisel3._
import circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}

/** Only an emission harness. The original arithmetic and elastic stages are unchanged.
  * Live top-level inputs prevent inter-module constant propagation from specializing
  * the pipeline primitives as it can in the historical dummy emission top.
  */
class MatrixNormRoPEHardwarePrimitives extends Module {
  val io = IO(new Bundle {
    val bf16A = Input(UInt(16.W)); val bf16B = Input(UInt(16.W)); val accumulator = Input(UInt(32.W))
    val fmaOut = Output(UInt(32.W)); val fmaFlags = Output(UInt(5.W))
    val op = Input(Bool()); val x = Input(UInt(32.W)); val y = Input(UInt(32.W))
    val inValid = Input(Bool()); val outReady = Input(Bool()); val tag = Input(UInt(12.W))
    val aluOut = Output(UInt(32.W)); val aluFlags = Output(UInt(5.W))
    val mulReady = Output(Bool()); val mulValid = Output(Bool()); val mulOut = Output(UInt(32.W)); val mulFlags = Output(UInt(5.W)); val mulTag = Output(UInt(12.W))
    val addReady = Output(Bool()); val addValid = Output(Bool()); val addOut = Output(UInt(32.W)); val addFlags = Output(UInt(5.W)); val addTag = Output(UInt(12.W))
    val mulBitReady = Output(Bool()); val mulBitValid = Output(Bool()); val mulBitOut = Output(UInt(32.W)); val mulBitFlags = Output(UInt(5.W)); val mulBitTag = Output(UInt(1.W))
    val addBitReady = Output(Bool()); val addBitValid = Output(Bool()); val addBitOut = Output(UInt(32.W)); val addBitFlags = Output(UInt(5.W)); val addBitTag = Output(UInt(1.W))
  })
  // Live ports keep the exact production split HardFloat FMA primitives.
  // This emission harness changes no Matrix dataflow or arithmetic.
  val pre = Module(new HeteroBF16FmaPre)
  pre.io.a := io.bf16A; pre.io.b := io.bf16B; pre.io.c := io.accumulator
  val fmaMul = Module(new HeteroBF16FmaMul)
  fmaMul.io.mulAddA := pre.io.mulAddA; fmaMul.io.mulAddB := pre.io.mulAddB
  fmaMul.io.mulAddC := pre.io.mulAddC
  val post = Module(new HeteroBF16FmaPost)
  post.io.meta := pre.io.meta; post.io.mulAddResult := fmaMul.io.mulAddResult
  val round = Module(new HeteroBF16FmaRound)
  round.io.raw := post.io.raw; round.io.invalid := post.io.invalid
  io.fmaOut := round.io.out; io.fmaFlags := round.io.exceptionFlags
  val alu = Module(new HeteroFP32Alu)
  alu.io.op := io.op; alu.io.x := io.x; alu.io.y := io.y
  io.aluOut := alu.io.out; io.aluFlags := alu.io.exceptionFlags
  val mul = Module(new HeteroFP32MulPipe(12, "HeteroFP32MulPipeTag12"))
  mul.io.inValid := io.inValid; mul.io.outReady := io.outReady; mul.io.x := io.x; mul.io.y := io.y; mul.io.userIn := io.tag
  io.mulReady := mul.io.inReady; io.mulValid := mul.io.outValid; io.mulOut := mul.io.out; io.mulFlags := mul.io.exceptionFlags; io.mulTag := mul.io.userOut
  val add = Module(new HeteroFP32AddPipe(12, "HeteroFP32AddPipeTag12"))
  add.io.inValid := io.inValid; add.io.outReady := io.outReady; add.io.x := io.x; add.io.y := io.y; add.io.userIn := io.tag
  io.addReady := add.io.inReady; io.addValid := add.io.outValid; io.addOut := add.io.out; io.addFlags := add.io.exceptionFlags; io.addTag := add.io.userOut
  val mulBit = Module(new HeteroFP32MulPipe(1, "HeteroFP32MulPipeBit1"))
  mulBit.io.inValid := io.inValid; mulBit.io.outReady := io.outReady; mulBit.io.x := io.x; mulBit.io.y := io.y; mulBit.io.userIn := io.tag(0)
  io.mulBitReady := mulBit.io.inReady; io.mulBitValid := mulBit.io.outValid; io.mulBitOut := mulBit.io.out; io.mulBitFlags := mulBit.io.exceptionFlags; io.mulBitTag := mulBit.io.userOut
  val addBit = Module(new HeteroFP32AddPipe(1, "HeteroFP32AddPipeBit1"))
  addBit.io.inValid := io.inValid; addBit.io.outReady := io.outReady; addBit.io.x := io.x; addBit.io.y := io.y; addBit.io.userIn := io.tag(0)
  io.addBitReady := addBit.io.inReady; io.addBitValid := addBit.io.outValid; io.addBitOut := addBit.io.out; io.addBitFlags := addBit.io.exceptionFlags; io.addBitTag := addBit.io.userOut
}
object EmitMatrixNormRoPEHardwarePrimitives extends App {
  require(args.length == 1, "Expected output SystemVerilog path")
  val output = Paths.get(args(0))
  val sv = ChiselStage.emitSystemVerilog(new MatrixNormRoPEHardwarePrimitives,
    firtoolOpts = Array("--disable-all-randomization", "--strip-debug-info"))
  Files.createDirectories(output.getParent)
  Files.writeString(output, sv, StandardCharsets.UTF_8)
}

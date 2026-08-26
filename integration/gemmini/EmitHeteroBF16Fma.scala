package gemmini

import chisel3._
import chisel3.util.Cat
import circt.stage.ChiselStage
import hardfloat._
import hardfloat.consts._
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}

class HeteroBF16FmaLane extends Module {
  val io = IO(new Bundle {
    val a = Input(UInt(16.W))
    val b = Input(UInt(16.W))
    val c = Input(UInt(32.W))
    val out = Output(UInt(32.W))
    val exceptionFlags = Output(UInt(5.W))
  })
  val fma = Module(new MulAddRecFN(8, 24))
  fma.io.op := 0.U
  fma.io.a := recFNFromFN(8, 24, Cat(io.a, 0.U(16.W)))
  fma.io.b := recFNFromFN(8, 24, Cat(io.b, 0.U(16.W)))
  fma.io.c := recFNFromFN(8, 24, io.c)
  fma.io.roundingMode := round_near_even
  fma.io.detectTininess := tininess_afterRounding
  io.out := fNFromRecFN(8, 24, fma.io.out)
  io.exceptionFlags := fma.io.exceptionFlags
}

object EmitHeteroBF16Fma extends App {
  require(args.length == 1, "expected output SystemVerilog path")
  val output = Paths.get(args(0))
  val sv = ChiselStage.emitSystemVerilog(new HeteroBF16FmaLane)
  Files.createDirectories(output.getParent)
  Files.writeString(output, sv, StandardCharsets.UTF_8)
}

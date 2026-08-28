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

/** Combinational first stage of the BF16-input/FP32-accumulator FMA. */
class HeteroBF16FmaPre extends RawModule {
  val io = IO(new Bundle {
    val a = Input(UInt(16.W))
    val b = Input(UInt(16.W))
    val c = Input(UInt(32.W))
    val mulAddA = Output(UInt(24.W))
    val mulAddB = Output(UInt(24.W))
    val mulAddC = Output(UInt(48.W))
    val meta = Output(UInt(54.W))
  })
  val pre = Module(new MulAddRecFNToRaw_preMul(8, 24))
  pre.io.op := 0.U
  pre.io.a := recFNFromFN(8, 24, Cat(io.a, 0.U(16.W)))
  pre.io.b := recFNFromFN(8, 24, Cat(io.b, 0.U(16.W)))
  pre.io.c := recFNFromFN(8, 24, io.c)
  require(pre.io.toPostMul.getWidth == 54)
  io.mulAddA := pre.io.mulAddA
  io.mulAddB := pre.io.mulAddB
  io.mulAddC := pre.io.mulAddC
  io.meta := pre.io.toPostMul.asUInt
}

/** Exact HardFloat multiply-add integer core, isolated as its own stage. */
class HeteroBF16FmaMul extends RawModule {
  val io = IO(new Bundle {
    val mulAddA = Input(UInt(24.W))
    val mulAddB = Input(UInt(24.W))
    val mulAddC = Input(UInt(48.W))
    val mulAddResult = Output(UInt(49.W))
  })
  io.mulAddResult := (io.mulAddA * io.mulAddB) +& io.mulAddC
}

/** HardFloat normalization stage after the integer multiply-add. */
class HeteroBF16FmaPost extends RawModule {
  val io = IO(new Bundle {
    val meta = Input(UInt(54.W))
    val mulAddResult = Input(UInt(49.W))
    val raw = Output(UInt(41.W))
    val invalid = Output(Bool())
  })
  val post = Module(new MulAddRecFNToRaw_postMul(8, 24))
  post.io.fromPreMul := io.meta.asTypeOf(new MulAddRecFN_interIo(8, 24))
  post.io.mulAddResult := io.mulAddResult
  post.io.roundingMode := round_near_even
  require(post.io.rawOut.getWidth == 41)
  io.raw := post.io.rawOut.asUInt
  io.invalid := post.io.invalidExc
}

/** HardFloat rounding stage producing the architectural IEEE FP32 result. */
class HeteroBF16FmaRound extends RawModule {
  val io = IO(new Bundle {
    val raw = Input(UInt(41.W))
    val invalid = Input(Bool())
    val out = Output(UInt(32.W))
    val exceptionFlags = Output(UInt(5.W))
  })
  val round = Module(new RoundRawFNToRecFN(8, 24, 0))
  round.io.invalidExc := io.invalid
  round.io.infiniteExc := false.B
  round.io.in := io.raw.asTypeOf(new RawFloat(8, 26))
  round.io.roundingMode := round_near_even
  round.io.detectTininess := tininess_afterRounding
  io.out := fNFromRecFN(8, 24, round.io.out)
  io.exceptionFlags := round.io.exceptionFlags
}

object EmitHeteroBF16Fma extends App {
  require(args.length == 1, "expected output SystemVerilog path")
  val output = Paths.get(args(0))
  val sv = ChiselStage.emitSystemVerilog(new HeteroBF16FmaLane)
  Files.createDirectories(output.getParent)
  Files.writeString(output, sv, StandardCharsets.UTF_8)
}

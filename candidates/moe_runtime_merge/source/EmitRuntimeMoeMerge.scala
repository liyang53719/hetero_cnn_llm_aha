package gemmini
/** Native ChiselStage output, not edited Treadle low-FIR. */
object EmitRuntimeMoeMerge {
  def main(args:Array[String]):Unit={
    require(args.length==1,"one fresh CHIRRTL output path required")
    val p=java.nio.file.Paths.get(args(0))
    require(!java.nio.file.Files.exists(p),"must not overwrite evidence")
    val text=circt.stage.ChiselStage.emitCHIRRTL(new HeteroRuntimeMoeMerge)
    java.nio.file.Files.write(p,text.getBytes(java.nio.charset.StandardCharsets.UTF_8))
  }
}

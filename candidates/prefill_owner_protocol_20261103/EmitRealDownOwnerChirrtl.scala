// Planning source only. Compilation and emission need separate resource admission.
package heteronpu.continuous

import circt.stage.ChiselStage

/** Direct production owner, original complete banks, no Matrix arithmetic module.
  * The real DenseOwnerIO remains the external protocol boundary. No tied inputs,
  * substitute banks, observer wrapper, ChiselTest simulator, or full Top.
  */
object EmitRealDownOwnerChirrtl {
  def main(args: Array[String]): Unit = {
    require(args.length == 0, "Only the fixed relative design output is admitted")
    val started = System.nanoTime()
    def mark(name: String): Unit = {
      println(s"OWNER_CHIRRTL_PHASE=$name elapsed_ns=${System.nanoTime() - started}")
      Console.out.flush()
    }
    mark("BEFORE_STAGE")
    ChiselStage.emitCHIRRTLFile({
      mark("BEFORE_PRODUCTION_CONSTRUCTION")
      val owner = new TransposedDenseDownOwner(
        burstWrites = true,
        enableFfnTiles = true,
        enableFfnWindow = true,
        enableFfnDrain = true,
        numericPolicy = Qwen2NumericPolicy.Qwen2OfficialBf16V2,
        enableKWindow = true,
        enableDenseDrain = true,
        enableActivationResidency = true)
      mark("AFTER_PRODUCTION_CONSTRUCTION")
      owner
    }, Array("--target-dir", "design"))
    mark("AFTER_CHIRRTL_FILE_RETURN")
    // Process exit and supervisor cleanup, not this marker, authorizes a later
    // independent firtool process. No emitSystemVerilog or subprocess invocation.
  }
}

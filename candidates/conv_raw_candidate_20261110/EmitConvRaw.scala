object EmitConvRaw extends App {
 val text=circt.stage.ChiselStage.emitCHIRRTL(new ColdInitToPhase17Chain)
 val p=new java.io.PrintWriter("results/ConvRaw.chirrtl");try{p.write(text)}finally{p.close()}
 println("CHIRRTL_ELABORATION_ONLY_NOT_NUMERICAL_PASS")
}

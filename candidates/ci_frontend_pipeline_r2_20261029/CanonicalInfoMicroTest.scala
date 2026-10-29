// TEMP_UNCOMPILED, tiny parser-only negative tests; no hardware elaboration.
package chiseltest.simulator
object CanonicalInfoMicroTest {
 def main(a:Array[String]):Unit={
  val base="""circuit Mini : @[old/root.scala 1:1]
  module Mini : @[old/root.scala 2:1]
    input in : UInt<8> @[old/root.scala 3:1]
    output out : UInt<8> @[old/root.scala 4:1]
    out <= UInt<8>(1) @[old/root.scala 5:1]
    out <= in @[old/root.scala 6:1]
"""
  def h(s:String)=CanonicalHighGate.circuitSemanticSha(firrtl2.Parser.parse(s))
  require(h(base)==h(base.replace("old/root.scala","fresh/ci/root.scala")),"Info-only accepted")
  Seq(base.replace("UInt<8>(1)","UInt<8>(2)"),
      base.replace("input in : UInt<8>","input in : UInt<9>"),
      base.replace("input in :", "output in :"),
      base.replace("out <= in", "out <= UInt<8>(0)"),
      base.replace("out <= UInt<8>(1) @[old/root.scala 5:1]\n    out <= in @[old/root.scala 6:1]",
        "out <= in @[old/root.scala 6:1]\n    out <= UInt<8>(1) @[old/root.scala 5:1]"))
    .foreach(s=>require(h(base)!=h(s),"constant/type/port/connection/order drift rejected"))
  def ann(dir:String,target:String)=s"""[{"class":"firrtl2.options.TargetDirAnnotation","directory":"$dir"},{"class":"firrtl2.transforms.DontTouchAnnotation","target":"$target"}]"""
  val one=ann("old","~Mini|Mini>in")
  require(CanonicalHighGate.annotationSemanticSha(one)==CanonicalHighGate.annotationSemanticSha(ann("fresh","~Mini|Mini>in")))
  require(CanonicalHighGate.annotationSemanticSha(one)!=CanonicalHighGate.annotationSemanticSha(ann("old","~Mini|Mini>out")))
  println("PASS_TINY_PARSER_METADATA_ONLY_NOT_FULL_HIGH_OR_TRANSFORM_OR_NUMERICAL")
 }
}

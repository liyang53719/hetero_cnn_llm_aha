// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator
import firrtl2.ir._
import heteronpu.continuous.model._
import java.nio.charset.StandardCharsets.UTF_8

/** Candidate generation precondition ONLY. New core whole hashes are observed
  * identity, never independent acceptance. Original exact storage substitutions
  * retain their own register/type/address/write/read/count/priority predicates.
  * The old locked NewToolchainTransformGate remains unchanged and is not called.
  */
object ModelCandidateTransformGateV1 {
  def main(a:Array[String]):Unit=ModelCandidateDiagnosticV1.run("transform_new_toolchain"){
    ModelCandidateDiagnosticV1.phase("INPUT_BOUNDS_OR_PIN")
    require(a.length==4,"fresh HIGH observed-canonical observed-SHA NEW-summary.json")
    val raw=ModelCandidateHighDescriptorV1.read(a(0),384L<<20)
    ModelCandidateDiagnosticV1.number("high_bytes",raw.length);ModelCandidateDiagnosticV1.hash("high_sha256",ModelCandidateHighDescriptorV1.sha(raw))
    ModelCandidateDiagnosticV1.phase("HIGH_ROUNDTRIP")
    val high=firrtl2.Parser.parse(new String(raw,UTF_8))
    require(java.util.Arrays.equals(high.serialize.getBytes(UTF_8),raw),"exact complete HIGH roundtrip")
    ModelCandidateDiagnosticV1.phase("CANONICAL_IDENTITY")
    val observed=ModelCandidateHighDescriptorV1.read(a(1),512L<<10)
    require(a(2).matches("[0-9a-f]{64}")&&ModelCandidateHighDescriptorV1.sha(observed)==a(2),"same-run descriptor integrity, not acceptance")
    val lines=new String(observed,UTF_8).split("\n").toSeq
    require(lines.head==ModelCandidateHighDescriptorV1.Header)
    val row=lines.tail.map(_.split("\t").toSeq)
    require(row.forall(r=>r.size==2||(r.size==3&&r.head=="module")))
    require(row.filter(_.size==2).map(_.head).distinct.size==3&&row.count(_.size==2)==3)
    val head=row.filter(_.size==2).map(r=>r.head->r(1)).toMap
    require(head.keySet==Set("main","circuit","annotations_order_preserved")&&head("main")=="HostBlockTopV4")
    val moduleRows=row.filter(_.size==3)
    require(moduleRows.nonEmpty&&moduleRows.size<=4096&&moduleRows.map(_(1)).distinct.size==moduleRows.size)
    val modules=moduleRows.map(r=>r(1)->r(2)).toMap
    require(high.modules.map(_.name)==moduleRows.map(_(1)),"all actual module order and names bound")
    require(CanonicalHighGate.circuitSemanticSha(high)==head("circuit"))
    require(high.modules.forall(m=>CanonicalHighGate.moduleSemanticSha(m)==modules(m.name)))
    ModelCandidateDiagnosticV1.number("module_count",high.modules.size);ModelCandidateDiagnosticV1.hash("canonical_sha256",a(2))
    val core=high.modules.find(_.name=="Qwen2ContinuousBlock").get
    val fifo=high.modules.find(_.name=="MatrixResultFifo").get
    val cp=CanonicalHighGate.moduleSemanticSha(core)
    val fp="eb44e4267684bbb9cf265e88ea89a6910dedd67b2bd2896bb6367928d4ecf831"
    ModelCandidateDiagnosticV1.phase("FIXED_MODULE_HASH")
    require(CanonicalHighGate.moduleSemanticSha(fifo)==fp,"unchanged independently reviewed full-capacity FIFO")
    val sentinel=Module(NoInfo,"Sentinel",Seq.empty,EmptyStmt)
    val input=Circuit(NoInfo,Seq(core,fifo,sentinel),"Qwen2ContinuousBlock")
    ModelCandidateDiagnosticV1.phase("FIFO_LOCAL_SHAPE")
    val intermediate=PortableHostMatrixResultFifoMemoryLowering(input,fp)
    ModelCandidateDiagnosticV1.phase("DENSE_ACC_LOCAL_SHAPE")
    val result=PortableHostDenseAccMemoryLowering(intermediate,cp)
    require(result.modules.size==3&&result.modules.last.eq(sentinel))
    require(result.modules(0).info==core.info&&result.modules(1).info==fifo.info,"fresh Info preserved")
    require(result.modules(0).ports==core.ports&&result.modules(1).ports==fifo.ports,"all public ports preserved")
    PortableHostDenseAccMemoryLowering.check(result)
    val summary=ujson.Obj("schema"->"MODEL_CANDIDATE_STORAGE_TRANSFORM_PRECONDITIONS_V1",
      "scope"->"CANDIDATE_GENERATION_PRECONDITIONS_ONLY_UNREVIEWED",
      "observed_high_sha256"->ModelCandidateHighDescriptorV1.sha(raw),"observed_canonical_sha256"->a(2),
      "original_core_semantic_sha256"->cp,"original_fifo_semantic_sha256"->fp,
      "transformed_core_semantic_sha256"->CanonicalHighGate.moduleSemanticSha(result.modules(0)),
      "transformed_fifo_semantic_sha256"->CanonicalHighGate.moduleSemanticSha(result.modules(1)),
      "sentinel_same_object"->true,"ports_unchanged"->true,"info_unchanged"->true,
      "original_exact_local_storage_rules_passed"->true,"numerical_pass"->false,"post_build_structure_accepted"->false)
    ModelCandidateDiagnosticV1.phase("METADATA_BOUNDS")
    ModelCandidateHighDescriptorV1.write(a(3),(ujson.write(summary,indent=2)+"\n").getBytes(UTF_8),64<<10)
    println("MODEL_CANDIDATE_STORAGE_RULES_ONLY_NOT_ACCEPTANCE")
  }
}

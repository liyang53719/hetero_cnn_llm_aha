package chiseltest.simulator

import heteronpu.continuous.model.NativeLibraryPin
import java.nio.file.{Files,Path,LinkOption}
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest
import org.json4s._
import org.json4s.native.JsonMethods

/** Consumer of supervisor/qualification evidence, NEVER a producer of PASS.
  * Receipt hash must be supplied by the independent owning supervisor. This
  * class cannot establish source/class provenance or qualify a native bridge.
  * No default/fixture/current graph receipt satisfies this admission schema.
  */
final class HybridExecutionGate private(val path:Path,val sha256:String,val receipt:JValue) {
  import HybridExecutionGate._
  private def field(name:String):JValue=receipt \ name
  private def yes(name:String):Unit=require(field(name)==JBool(true),"missing actual qualification: "+name)
  private def pin(name:String,expected:String):Unit=require(field(name)==JString(expected),"qualification identity mismatch: "+name)
  private def live():Unit={
    require(hash(path)==sha256,"admission receipt remained frozen")
    val expires=field("expires_at_epoch_seconds") match {case JInt(n) if n.isValidLong=>n.toLong;case _=>0L}
    require(expires>java.time.Instant.now().getEpochSecond,"live supervisor resource lease")
    val reserve=field("min_free_disk_bytes") match {case JInt(n)=>n;case _=>BigInt(0)}
    val allowance=field("remaining_output_allowance_bytes") match {case JInt(n)=>n;case _=>BigInt(-1)}
    require(reserve==BigInt(8L<<30) && allowance>=0,"unchanged 8GiB reserve plus output allowance")
    require(BigInt(Files.getFileStore(path).getUsableSpace)>=reserve+allowance,"current disk admission")
    yes("owned_outer_supervisor_active");yes("memory_cpu_tree_log_limits_admitted")
  }
  def requirePreparation(p:OriginalHostTreadleBinding.SourcePins):Unit={
    live()
    pin("engine",OriginalHostTreadleBinding.Engine)
    pin("source_manifest_sha256",p.sourceManifestSha);pin("loaded_classes_sha256",p.loadedClassesSha)
    pin("high_sha256",p.highSha);pin("annotations_sha256",p.annotationsSha)
    pin("idma_ext_module_sha256",p.idmaExtModuleSha)
    yes("fresh_actual162_seed_enabled_source_class_identity_verified")
    yes("all_4096_macs_vector32_and_five_m128_profiles_preserved")
  }
  def requireEngineConstruction(p:OriginalHostTreadleBinding.SourcePins,preparedSha:String,
    matrix:NativeLibraryPin,icg:NativeLibraryPin,idma:NativeLibraryPin):Unit={
    live()
    pin("status","ADMITTED_AFTER_ACTUAL_QUALIFICATION")
    pin("engine",OriginalHostTreadleBinding.Engine)
    pin("source_manifest_sha256",p.sourceManifestSha);pin("loaded_classes_sha256",p.loadedClassesSha)
    pin("high_sha256",p.highSha);pin("annotations_sha256",p.annotationsSha)
    pin("idma_ext_module_sha256",p.idmaExtModuleSha);pin("prepared_sha256",preparedSha)
    pin("port_schema_sha256",OriginalHostPorts.schemaSha)
    for((name,native)<-Seq("matrix"->matrix,"icg"->icg,"idma"->idma)){
      pin(name+"_library_sha256",native.sha256)
      require(hash(java.nio.file.Paths.get(native.path))==native.sha256,"exact current native library")
    }
    Seq("fresh_actual162_seed_enabled_source_class_identity_verified",
      "all_4096_macs_vector32_and_five_m128_profiles_preserved",
      "native_direct_cabi_jna_treadle_halfcycle_differential_passed",
      "native_complete_snapshot_order_permutation_repeat_getter_reset_passed",
      "native_matrix_seed_icg_pair_eight_way_service_qualified",
      "native_idma_original_adapter_all_channels_streaming_cutthrough_burst_fault_reset_drain_qualified",
      "manual_treadle_register_icg_native_leaf_pin_facade_differential_passed").foreach(yes)
  }
  def requireDriverLaunch(binary:Path,runtime:Path,profile:Int):Unit={
    live();require(profile>=0&&profile<5,"unchanged profile")
    pin("status","ADMITTED_AFTER_ACTUAL_QUALIFICATION")
    pin("driver_binary_sha256",hash(binary));pin("runtime_manifest_sha256",hash(runtime))
    require(field("profile")==JInt(profile),"profile-specific material identity")
    yes("fresh_original_driver_headers_and_pin_facade_identity_verified")
    yes("current_profile_program_views_weights_input_only_aliases_verified")
    yes("no_reference_only_or_expected_outputs_in_stimulus")
    yes("full_host_reset_and_finite_transactions_qualified")
  }
  /** A captured constructor audit never qualifies itself. The owning reviewer
    * may admit the pinned-source + actual orphan/counter + tiny-differential
    * proof route without pretending the old iDMA ABI has native telemetry.
    */
  def requireStartupDriverAdmission(p:OriginalHostTreadleBinding.SourcePins,
    audit:OriginalHostStartupAudit.Receipt):Unit={
    live();pin("status","ADMITTED_AFTER_ACTUAL_QUALIFICATION")
    pin("source_manifest_sha256",p.sourceManifestSha);pin("loaded_classes_sha256",p.loadedClassesSha)
    pin("startup_audit_sha256",textHash(audit.json))
    pin("startup_no_native_call_proof_mode","PINNED_SOURCE_AND_ACTUAL_ORPHAN_AUDIT_V1")
    require(field("startup_idma_native_edge_telemetry_available")==JBool(false),"do not invent unavailable iDMA telemetry")
    field("startup_no_native_call_proof_sha256") match{
      case JString(s)=>require(s.matches("[0-9a-f]{64}"),"independently pinned startup call-path proof")
      case _=>throw new IllegalArgumentException("missing startup call-path proof identity")
    }
    Seq("startup_source_class_native_create_no_eval_paths_verified",
      "startup_actual_constructor_orphan_set_native_intersection_empty",
      "startup_original_initialization_annotations_preserved",
      "startup_tiny_constructor_and_first_frame_differential_passed",
      "startup_original_reset_polarity_ancestry_qualified",
      "startup_actual_known_native_and_adapter_edge_counters_zero").foreach(yes)
  }
}
object HybridExecutionGate {
  def textHash(s:String):String=MessageDigest.getInstance("SHA-256").digest(s.getBytes(UTF_8)).map(x=>f"${x&255}%02x").mkString
  def hash(path:Path):String={
    require(path.isAbsolute && Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS),"absolute regular pinned file")
    val d=MessageDigest.getInstance("SHA-256");val in=Files.newInputStream(path);val b=new Array[Byte](1048576)
    try {var n=in.read(b);while(n>=0){if(n>0)d.update(b,0,n);n=in.read(b)}}finally in.close()
    d.digest().map(x=>f"${x&255}%02x").mkString
  }
  def load(path:Path,expectedSha:String):HybridExecutionGate={
    require(expectedSha.matches("[0-9a-f]{64}") && Files.size(path)<=65536,"bounded independently pinned admission")
    require(hash(path)==expectedSha,"supervisor receipt identity")
    val data=JsonMethods.parse(new String(Files.readAllBytes(path),UTF_8))
    def unique(v:JValue):Unit=v match {case JObject(xs)=>require(xs.map(_._1).distinct.size==xs.size,"unique evidence keys");xs.foreach(x=>unique(x._2));case JArray(xs)=>xs.foreach(unique);case _=>()}
    unique(data)
    require((data \ "schema")==JString("HYBRID_ORIGINAL_HOST_EXECUTION_ADMISSION_V1"),"new engine-specific admission required")
    require(Set[JValue](JString("ADMITTED_AFTER_ACTUAL_QUALIFICATION"),
      JString("ADMITTED_FOR_SOURCE_IDENTITY_AND_PREPARATION_ONLY"))(data \ "status"),"bounded owning admission stage")
    new HybridExecutionGate(path,expectedSha,data)
  }
}

package heteronpu.operator

import chisel3.RawModule

final case class OperatorBinding(model: String, operator: String, owner: String, root: String)
final case class RootSpec(name: String, program: Seq[MicroOpTemplate], generator: () => RawModule)

object ThreeModelOperatorCatalog {
  val Qwen2 = "qwen2_1p5b"
  val Qwen35 = "qwen3_5_35b_a3b"
  val Qwen38 = "qwen3_8_flash_next"

  val roots: Seq[RootSpec] = Seq(
    RootSpec("HeteroTokenEmbeddingPrimitiveV3", TextPrograms.TokenEmbedding, () => new HeteroTokenEmbeddingPrimitiveV3),
    RootSpec("HeteroQwen2DecoderBlockPrimitiveV3", TextPrograms.Qwen2DecoderBlock, () => new HeteroQwen2DecoderBlockPrimitiveV3),
    RootSpec("HeteroQwen35DenseAttentionPrimitiveV3", TextPrograms.Qwen35DenseAttention, () => new HeteroQwen35DenseAttentionPrimitiveV3),
    RootSpec("HeteroGatedDeltaNetPrimitiveV3", TextPrograms.GatedDeltaNet, () => new HeteroGatedDeltaNetPrimitiveV3),
    RootSpec("HeteroMoePrimitiveV3", TextPrograms.Moe, () => new HeteroMoePrimitiveV3),
    RootSpec("HeteroQwen38GatedResidualReadPrimitiveV3", Qwen38Programs.GatedResidualRead, () => new HeteroQwen38GatedResidualReadPrimitiveV3),
    RootSpec("HeteroQwen38GatedResidualWritePrimitiveV3", Qwen38Programs.GatedResidualWrite, () => new HeteroQwen38GatedResidualWritePrimitiveV3),
    RootSpec("HeteroPlePrimitiveV3", Qwen38Programs.Ple, () => new HeteroPlePrimitiveV3),
    RootSpec("HeteroQsaPrimitiveV3", Qwen38Programs.Qsa, () => new HeteroQsaPrimitiveV3),
    RootSpec("HeteroQwen38FinalHyperMergePrimitiveV3", Qwen38Programs.FinalHyperMerge, () => new HeteroQwen38FinalHyperMergePrimitiveV3),
    RootSpec("HeteroVisionPatchEmbedPrimitiveV3", VisionAndBoundaryPrograms.VisionPatchEmbed, () => new HeteroVisionPatchEmbedPrimitiveV3),
    RootSpec("HeteroVisionTransformerBlockPrimitiveV3", VisionAndBoundaryPrograms.VisionTransformerBlock, () => new HeteroVisionTransformerBlockPrimitiveV3),
    RootSpec("HeteroVisionPatchMergePrimitiveV3", VisionAndBoundaryPrograms.VisionPatchMerge, () => new HeteroVisionPatchMergePrimitiveV3),
    RootSpec("HeteroMultimodalInjectPrimitiveV3", VisionAndBoundaryPrograms.MultimodalInject, () => new HeteroMultimodalInjectPrimitiveV3),
    RootSpec("HeteroFinalNormPrimitiveV3", VisionAndBoundaryPrograms.FinalNorm, () => new HeteroFinalNormPrimitiveV3),
    RootSpec("HeteroLmHeadArgmaxPrimitiveV3", VisionAndBoundaryPrograms.LmHeadArgmax, () => new HeteroLmHeadArgmaxPrimitiveV3),
    RootSpec("HeteroMtpDraftPrimitiveV3", VisionAndBoundaryPrograms.MtpDraft, () => new HeteroMtpDraftPrimitiveV3),
    RootSpec("HeteroMtpVerifyResolvePrimitiveV3", VisionAndBoundaryPrograms.MtpVerifyResolve, () => new HeteroMtpVerifyResolvePrimitiveV3)
  )

  val qwen2: Seq[OperatorBinding] = Seq(
    OperatorBinding(Qwen2, "token_embedding", "memory", "HeteroTokenEmbeddingPrimitiveV3"),
    OperatorBinding(Qwen2, "input_rmsnorm", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "q_projection", "matrix", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "k_projection", "matrix", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "v_projection", "matrix", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "q_bias", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "k_bias", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "v_bias", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "q_rope", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "k_rope", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "kv_append", "kv", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "kv_gather", "kv", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "gqa_mapping", "matrix_kv", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "qk_matmul", "matrix", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "attention_scale", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "causal_mask", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "online_softmax", "attention_sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "pv_matmul", "matrix", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "o_projection", "matrix", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "attention_residual", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "post_attention_rmsnorm", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "mlp_gate_projection", "matrix", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "mlp_up_projection", "matrix", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "silu", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "swiglu_multiply", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "mlp_down_projection", "matrix", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "mlp_residual", "sfu", "HeteroQwen2DecoderBlockPrimitiveV3"),
    OperatorBinding(Qwen2, "final_rmsnorm", "sfu", "HeteroFinalNormPrimitiveV3"),
    OperatorBinding(Qwen2, "lm_head", "matrix", "HeteroLmHeadArgmaxPrimitiveV3"),
    OperatorBinding(Qwen2, "argmax", "selection", "HeteroLmHeadArgmaxPrimitiveV3")
  )

  private val q35Gdn = Seq(
    "input_rmsnorm", "gdn_qkv_projection", "gdn_z_projection", "gdn_beta_projection",
    "gdn_decay_projection", "gdn_causal_conv1d", "gdn_conv_state_read",
    "gdn_conv_state_write", "gdn_q_l2norm", "gdn_k_l2norm", "gdn_query_scale",
    "gdn_softplus", "gdn_decay_exp", "gdn_beta_sigmoid", "gdn_recurrent_state_read",
    "gdn_state_decay", "gdn_state_key_read", "gdn_delta", "gdn_outer_product_update",
    "gdn_state_query", "gdn_output_rmsnorm", "gdn_output_silu_gate",
    "gdn_output_projection", "gdn_residual"
  ).map(op => OperatorBinding(Qwen35, op, "matrix_sfu_state", "HeteroGatedDeltaNetPrimitiveV3"))

  private val q35Dense = Seq(
    "dense_q_projection", "dense_k_projection", "dense_v_projection", "dense_gate_projection",
    "dense_q_rmsnorm", "dense_k_rmsnorm", "partial_interleaved_mrope",
    "dense_kv_append", "dense_kv_gather", "dense_gqa_mapping", "dense_qk_matmul",
    "dense_attention_scale", "dense_causal_mask", "dense_online_softmax", "dense_pv_matmul",
    "attention_output_sigmoid_gate", "dense_o_projection", "dense_residual"
  ).map(op => OperatorBinding(Qwen35, op, "matrix_sfu_kv", "HeteroQwen35DenseAttentionPrimitiveV3"))

  private val q35Moe = Seq(
    "post_attention_rmsnorm", "moe_router_projection", "moe_stable_top8",
    "moe_selected_softmax", "moe_dispatch", "expert_weight_fetch",
    "routed_expert_gate_projection", "routed_expert_up_projection", "routed_expert_silu",
    "routed_expert_multiply", "routed_expert_down_projection", "routed_expert_weighted_reduce",
    "shared_expert_gate_projection", "shared_expert_up_projection", "shared_expert_silu",
    "shared_expert_multiply", "shared_expert_down_projection", "shared_expert_router_gate",
    "routed_shared_reduce", "moe_residual"
  ).map(op => OperatorBinding(Qwen35, op, "matrix_sfu_dma", "HeteroMoePrimitiveV3"))

  private val vision35 = Seq(
    OperatorBinding(Qwen35, "vision_patch_projection", "matrix", "HeteroVisionPatchEmbedPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_position_interpolation", "control_sfu", "HeteroVisionPatchEmbedPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_position_add", "sfu", "HeteroVisionPatchEmbedPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_layernorm1", "sfu", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_qkv_projection", "matrix", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_rope", "sfu", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_window_mask", "sfu", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_noncausal_qk", "matrix", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_online_softmax", "attention_sfu", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_pv", "matrix", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_output_projection", "matrix", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_attention_residual", "sfu", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_layernorm2", "sfu", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_mlp_fc1", "matrix", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_gelu", "sfu", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_mlp_fc2", "matrix", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_mlp_residual", "sfu", "HeteroVisionTransformerBlockPrimitiveV3"),
    OperatorBinding(Qwen35, "vision_spatial_merge", "memory_sfu", "HeteroVisionPatchMergePrimitiveV3"),
    OperatorBinding(Qwen35, "vision_merge_layernorm", "sfu", "HeteroVisionPatchMergePrimitiveV3"),
    OperatorBinding(Qwen35, "vision_merge_fc1", "matrix", "HeteroVisionPatchMergePrimitiveV3"),
    OperatorBinding(Qwen35, "vision_merge_gelu", "sfu", "HeteroVisionPatchMergePrimitiveV3"),
    OperatorBinding(Qwen35, "vision_merge_fc2", "matrix", "HeteroVisionPatchMergePrimitiveV3"),
    OperatorBinding(Qwen35, "multimodal_feature_gather", "memory", "HeteroMultimodalInjectPrimitiveV3"),
    OperatorBinding(Qwen35, "multimodal_token_scatter", "memory", "HeteroMultimodalInjectPrimitiveV3")
  )

  val qwen35: Seq[OperatorBinding] = Seq(
    OperatorBinding(Qwen35, "token_embedding", "memory", "HeteroTokenEmbeddingPrimitiveV3")
  ) ++ q35Gdn ++ q35Dense ++ q35Moe ++ Seq(
    OperatorBinding(Qwen35, "final_rmsnorm", "sfu", "HeteroFinalNormPrimitiveV3"),
    OperatorBinding(Qwen35, "lm_head", "matrix", "HeteroLmHeadArgmaxPrimitiveV3"),
    OperatorBinding(Qwen35, "argmax", "selection", "HeteroLmHeadArgmaxPrimitiveV3"),
    OperatorBinding(Qwen35, "mtp_draft", "matrix_state", "HeteroMtpDraftPrimitiveV3"),
    OperatorBinding(Qwen35, "mtp_target_verify", "control_state", "HeteroMtpVerifyResolvePrimitiveV3"),
    OperatorBinding(Qwen35, "mtp_state_commit_rollback", "control_state", "HeteroMtpVerifyResolvePrimitiveV3")
  ) ++ vision35

  private val q38Gdn = q35Gdn.map(x => x.copy(
    model = Qwen38,
    operator = if (x.operator == "gdn_output_silu_gate") "gdn_output_configured_gate" else x.operator
  ))

  private val q38Moe = q35Moe.map(x => x.copy(
    model = Qwen38,
    operator = if (x.operator == "moe_stable_top8") "moe_stable_top10" else x.operator
  ))

  private val hyperReadOps = Seq(
    "attention_hyper_state_read", "attention_hyper_group_rmsnorm", "attention_hyper_lowrank_down",
    "attention_hyper_branch_scale", "attention_hyper_silu", "attention_hyper_lowrank_up",
    "attention_hyper_sigmoid", "attention_hyper_weighted_reduce",
    "moe_hyper_state_read", "moe_hyper_group_rmsnorm", "moe_hyper_lowrank_down",
    "moe_hyper_branch_scale", "moe_hyper_silu", "moe_hyper_lowrank_up",
    "moe_hyper_sigmoid", "moe_hyper_weighted_reduce"
  ).map(op => OperatorBinding(Qwen38, op, "matrix_sfu_state", "HeteroQwen38GatedResidualReadPrimitiveV3"))

  private val hyperWriteOps = Seq(
    "attention_hyper_block_broadcast", "attention_hyper_inject_gate", "attention_hyper_state_write",
    "moe_hyper_block_broadcast", "moe_hyper_inject_gate", "moe_hyper_state_write"
  ).map(op => OperatorBinding(Qwen38, op, "matrix_sfu_state", "HeteroQwen38GatedResidualWritePrimitiveV3"))

  private val pleOps = Seq(
    "ple_eos_history_reset", "ple_ngram_hash", "ple_sparse_row_fetch", "ple_embedding_lookup",
    "ple_key_projection", "ple_value_projection", "ple_key_group_rmsnorm",
    "ple_query_group_rmsnorm", "ple_gate_dot", "ple_gate_scale", "ple_signed_sqrt",
    "ple_sigmoid_gate", "ple_value_gate", "ple_conv_group_rmsnorm",
    "ple_dilated_depthwise_conv", "ple_conv_state", "ple_residual"
  ).map(op => OperatorBinding(Qwen38, op, "matrix_sfu_memory_state", "HeteroPlePrimitiveV3"))

  private val qsaOps = Seq(
    "qsa_index_q_projection", "qsa_index_k_projection", "qsa_index_l2norm", "qsa_index_rope",
    "qsa_index_state_append", "qsa_block_sum", "qsa_block_average", "qsa_block_l2norm",
    "qsa_index_score", "qsa_score_clamp", "qsa_head_reduce", "qsa_score_scale",
    "qsa_stable_top512", "qsa_block_expand", "qsa_selected_sort", "qsa_run_coalesce",
    "qsa_sparse_kv_gather", "qsa_q_projection", "qsa_k_projection", "qsa_v_projection",
    "qsa_gate_projection", "qsa_q_rmsnorm", "qsa_k_rmsnorm", "qsa_partial_mrope",
    "qsa_kv_append", "qsa_sparse_qk", "qsa_attention_scale", "qsa_causal_mask",
    "qsa_online_softmax", "qsa_sparse_pv", "qsa_output_sigmoid_gate", "qsa_o_projection"
  ).map(op => OperatorBinding(Qwen38, op, "matrix_sfu_kv_selection_state", "HeteroQsaPrimitiveV3"))

  private val vision38 = vision35.map(_.copy(model = Qwen38))

  val qwen38: Seq[OperatorBinding] = Seq(
    OperatorBinding(Qwen38, "token_embedding", "memory", "HeteroTokenEmbeddingPrimitiveV3")
  ) ++ hyperReadOps ++ hyperWriteOps ++ q38Gdn ++ pleOps ++ qsaOps ++ q38Moe ++ Seq(
    OperatorBinding(Qwen38, "final_hyper_state_read", "state", "HeteroQwen38FinalHyperMergePrimitiveV3"),
    OperatorBinding(Qwen38, "final_hyper_group_rmsnorm", "sfu", "HeteroQwen38FinalHyperMergePrimitiveV3"),
    OperatorBinding(Qwen38, "final_hyper_lowrank_gate", "matrix_sfu", "HeteroQwen38FinalHyperMergePrimitiveV3"),
    OperatorBinding(Qwen38, "final_hyper_weighted_reduce", "sfu", "HeteroQwen38FinalHyperMergePrimitiveV3"),
    OperatorBinding(Qwen38, "final_rmsnorm", "sfu", "HeteroQwen38FinalHyperMergePrimitiveV3"),
    OperatorBinding(Qwen38, "lm_head", "matrix", "HeteroLmHeadArgmaxPrimitiveV3"),
    OperatorBinding(Qwen38, "argmax", "selection", "HeteroLmHeadArgmaxPrimitiveV3"),
    OperatorBinding(Qwen38, "mtp_draft", "matrix_state", "HeteroMtpDraftPrimitiveV3"),
    OperatorBinding(Qwen38, "mtp_target_verify", "control_state", "HeteroMtpVerifyResolvePrimitiveV3"),
    OperatorBinding(Qwen38, "mtp_state_commit_rollback", "control_state", "HeteroMtpVerifyResolvePrimitiveV3")
  ) ++ vision38

  val all: Seq[OperatorBinding] = qwen2 ++ qwen35 ++ qwen38
  val byModel: Map[String, Seq[OperatorBinding]] = Map(Qwen2 -> qwen2, Qwen35 -> qwen35, Qwen38 -> qwen38)

  private val rootNames = roots.map(_.name).toSet
  require(roots.map(_.name).distinct.size == roots.size, "duplicate root name")
  require(all.map(x => (x.model, x.operator)).distinct.size == all.size, "duplicate model/operator binding")
  require(all.forall(x => rootNames.contains(x.root)), "catalog references a missing root")
  require(byModel.values.forall(_.nonEmpty), "empty model inventory")
}

package gemmini

import chisel3._
import chisel3.util._

case class HeteroOperatorBindingV2(
    model: String,
    operator: String,
    owner: String,
    module: String
)

/** Compile-time catalog written by the emitter and independently audited in Python. */
object HeteroThreeModelOperatorCatalogV2 {
  val qwen2: Seq[HeteroOperatorBindingV2] = Seq(
    HeteroOperatorBindingV2("qwen2_1p5b","token_embedding","memory","HeteroLanguageModelBoundaryOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen2_1p5b","rmsnorm","sfu","HeteroQwen2DecoderBlockOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen2_1p5b","qkv_projection_bias","matrix_sfu","HeteroQwen2DecoderBlockOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen2_1p5b","rope","sfu","HeteroQwen2DecoderBlockOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen2_1p5b","gqa_kv_append","kv","HeteroQwen2DecoderBlockOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen2_1p5b","causal_attention","matrix_sfu_kv","HeteroQwen2DecoderBlockOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen2_1p5b","swiglu_mlp","matrix_sfu","HeteroQwen2DecoderBlockOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen2_1p5b","residual_add","sfu","HeteroQwen2DecoderBlockOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen2_1p5b","lm_head_argmax","matrix_selection","HeteroLanguageModelBoundaryOperatorPrimitiveV2")
  )

  val qwen35: Seq[HeteroOperatorBindingV2] = Seq(
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","token_embedding","memory","HeteroLanguageModelBoundaryOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","rmsnorm_partial_mrope","sfu","HeteroQwen35DenseAttentionOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","gdn_projection_causal_conv","matrix_state","HeteroGdnOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","gdn_recurrent_update","matrix_state","HeteroGdnOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","gdn_gated_norm_output","matrix_sfu","HeteroGdnOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","dense_full_attention","matrix_sfu_kv","HeteroQwen35DenseAttentionOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","attention_output_gate","sfu","HeteroQwen35DenseAttentionOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","moe_top8_routed_shared","matrix_sfu_dma","HeteroMoeOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","mtp_verify_commit_rollback","control_state","HeteroMtpDraftTargetOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","vision_patch_block_merge","vision","HeteroVisionTransformerBlockOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_5_35b_a3b","lm_head_argmax","matrix_selection","HeteroLanguageModelBoundaryOperatorPrimitiveV2")
  )

  val qwen38: Seq[HeteroOperatorBindingV2] = Seq(
    HeteroOperatorBindingV2("qwen3_8_flash_next","token_embedding","memory","HeteroLanguageModelBoundaryOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","four_branch_gated_residual","matrix_sfu_state","HeteroGatedResidualOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","group_rmsnorm","sfu","HeteroGatedResidualOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","gdn_projection_causal_conv","matrix_state","HeteroGdnOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","gdn_recurrent_update","matrix_state","HeteroGdnOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","ple_ngram_hash_sparse_row_fetch","memory_state","HeteroPleOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","ple_projection_dilated_dwconv","matrix_state","HeteroPleOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","qsa_index_block_summary_top512","matrix_selection_state","HeteroQsaOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","qsa_sparse_kv_gather_attention","matrix_sfu_kv","HeteroQsaOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","attention_output_gate","matrix_sfu","HeteroQsaOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","moe_top10_routed_shared","matrix_sfu_dma","HeteroMoeOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","mtp_verify_commit_rollback","control_state","HeteroMtpDraftTargetOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","vision_patch_block_merge","vision","HeteroVisionTransformerBlockOperatorPrimitiveV2"),
    HeteroOperatorBindingV2("qwen3_8_flash_next","lm_head_argmax","matrix_selection","HeteroLanguageModelBoundaryOperatorPrimitiveV2")
  )

  val all: Seq[HeteroOperatorBindingV2] = qwen2 ++ qwen35 ++ qwen38
  require(qwen2.nonEmpty && qwen35.nonEmpty && qwen38.nonEmpty)
  require(all.map(x => (x.model, x.operator)).distinct.size == all.size)
}

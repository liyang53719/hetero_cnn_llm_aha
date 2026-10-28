// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model
// Static ABI metadata only, exact original companion InputWidths; no model or arithmetic.
object RetainedEndpointPortContract {
  val InputWidths: Map[String, Int] = Map(
    "clk_i" -> 1, "rst_ni" -> 1, "cmd_valid_i" -> 1, "cmd_i" -> 128,
    "step_valid_i" -> 1, "step_context_i" -> 3, "step_clear_i" -> 1, "step_last_i" -> 1,
    "command_last_tile_i" -> 1, "step_a_i" -> 256, "step_b_i" -> 512,
    "out_ready_i" -> 1, "completion_ready_i" -> 1, "seed_begin_valid_i" -> 1,
    "seed_context_i" -> 3, "seed_group_tag_i" -> 32, "seed_group_sequence_i" -> 32,
    "seed_source_generation_i" -> 32, "seed_beat_valid_i" -> 1, "seed_cluster_i" -> 5,
    "seed_data_i" -> 512, "seed_commit_valid_i" -> 1, "seed_abort_i" -> 1, "seed_ack_ready_i" -> 1)
}

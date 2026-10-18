// Generated from fixed actual VHostBlockTop__Dpi.h. Each argument is forwarded unchanged.
#pragma once
#include "startup_ledger.hpp"
#include "VHostBlockTop__Dpi.h"
extern "C" {
void __real_qwen2_matrix_command_endpoint_3_protectlib_check_hash(int protectlib_hash___05FV);
void __real_qwen2_matrix_command_endpoint_3_protectlib_combo_ignore(void* handle___05FV, svLogic seed_begin_valid_i, const svLogicVecVal* seed_context_i, const svLogicVecVal* seed_group_tag_i, const svLogicVecVal* seed_group_sequence_i, const svLogicVecVal* seed_source_generation_i, svLogic seed_beat_valid_i, const svLogicVecVal* seed_cluster_i, const svLogicVecVal* seed_data_i, svLogic seed_commit_valid_i, svLogic seed_abort_i, svLogic seed_ack_ready_i, svLogic cmd_valid_i, const svLogicVecVal* cmd_i, svLogic step_valid_i, const svLogicVecVal* step_context_i, svLogic step_clear_i, svLogic step_last_i, svLogic command_last_tile_i, const svLogicVecVal* step_a_i, const svLogicVecVal* step_b_i, svLogic out_ready_i, svLogic completion_ready_i);
long long __real_qwen2_matrix_command_endpoint_3_protectlib_combo_update(void* handle___05FV, svLogic seed_begin_valid_i, svLogic* seed_begin_ready_o, const svLogicVecVal* seed_context_i, const svLogicVecVal* seed_group_tag_i, const svLogicVecVal* seed_group_sequence_i, const svLogicVecVal* seed_source_generation_i, svLogic seed_beat_valid_i, svLogic* seed_beat_ready_o, const svLogicVecVal* seed_cluster_i, const svLogicVecVal* seed_data_i, svLogic seed_commit_valid_i, svLogic* seed_commit_ready_o, svLogic seed_abort_i, svLogic* seed_ack_valid_o, svLogic seed_ack_ready_i, svLogicVecVal* seed_ack_context_o, svLogicVecVal* seed_ack_group_tag_o, svLogicVecVal* seed_ack_group_sequence_o, svLogicVecVal* seed_ack_source_generation_o, svLogic* seed_ack_error_o, svLogic* seed_reset_required_o, svLogicVecVal* arithmetic_busy_o, svLogic* arithmetic_out_valid_o, svLogic cmd_valid_i, svLogic* cmd_ready_o, const svLogicVecVal* cmd_i, svLogic step_valid_i, svLogic* step_ready_o, const svLogicVecVal* step_context_i, svLogic step_clear_i, svLogic step_last_i, svLogic command_last_tile_i, const svLogicVecVal* step_a_i, const svLogicVecVal* step_b_i, svLogic* out_valid_o, svLogic out_ready_i, svLogicVecVal* out_context_o, svLogic* out_last_o, svLogicVecVal* out_acc_o, svLogic* completion_valid_o, svLogic completion_ready_i, svLogicVecVal* completion_data_o, svLogic* protocol_error_o);
void* __real_qwen2_matrix_command_endpoint_3_protectlib_create(const char* scope___05FV);
void __real_qwen2_matrix_command_endpoint_3_protectlib_final(void* handle___05FV);
long long __real_qwen2_matrix_command_endpoint_3_protectlib_seq_update(void* handle___05FV, svLogic* seed_begin_ready_o, svLogic* seed_beat_ready_o, svLogic* seed_commit_ready_o, svLogic* seed_ack_valid_o, svLogicVecVal* seed_ack_context_o, svLogicVecVal* seed_ack_group_tag_o, svLogicVecVal* seed_ack_group_sequence_o, svLogicVecVal* seed_ack_source_generation_o, svLogic* seed_ack_error_o, svLogic* seed_reset_required_o, svLogicVecVal* arithmetic_busy_o, svLogic* arithmetic_out_valid_o, svLogic clk_i, svLogic rst_ni, svLogic* cmd_ready_o, svLogic* step_ready_o, svLogic* out_valid_o, svLogicVecVal* out_context_o, svLogic* out_last_o, svLogicVecVal* out_acc_o, svLogic* completion_valid_o, svLogicVecVal* completion_data_o, svLogic* protocol_error_o);
void __wrap_qwen2_matrix_command_endpoint_3_protectlib_check_hash(int protectlib_hash___05FV) {
    auto& a=host_startup::ledger();
    try {
        a.before_hash(protectlib_hash___05FV);
        __real_qwen2_matrix_command_endpoint_3_protectlib_check_hash(protectlib_hash___05FV);
        a.after_hash();
    } catch(...) {a.poison();throw;}
}
void __wrap_qwen2_matrix_command_endpoint_3_protectlib_combo_ignore(void* handle___05FV, svLogic seed_begin_valid_i, const svLogicVecVal* seed_context_i, const svLogicVecVal* seed_group_tag_i, const svLogicVecVal* seed_group_sequence_i, const svLogicVecVal* seed_source_generation_i, svLogic seed_beat_valid_i, const svLogicVecVal* seed_cluster_i, const svLogicVecVal* seed_data_i, svLogic seed_commit_valid_i, svLogic seed_abort_i, svLogic seed_ack_ready_i, svLogic cmd_valid_i, const svLogicVecVal* cmd_i, svLogic step_valid_i, const svLogicVecVal* step_context_i, svLogic step_clear_i, svLogic step_last_i, svLogic command_last_tile_i, const svLogicVecVal* step_a_i, const svLogicVecVal* step_b_i, svLogic out_ready_i, svLogic completion_ready_i) {
    auto& a=host_startup::ledger();
    try {
        const auto index=a.before_call(handle___05FV,host_startup::Kind::combo_ignore);
        a.no_job(seed_begin_valid_i,seed_beat_valid_i,seed_commit_valid_i,seed_abort_i,cmd_valid_i,step_valid_i);
        __real_qwen2_matrix_command_endpoint_3_protectlib_combo_ignore(handle___05FV, seed_begin_valid_i, seed_context_i, seed_group_tag_i, seed_group_sequence_i, seed_source_generation_i, seed_beat_valid_i, seed_cluster_i, seed_data_i, seed_commit_valid_i, seed_abort_i, seed_ack_ready_i, cmd_valid_i, cmd_i, step_valid_i, step_context_i, step_clear_i, step_last_i, command_last_tile_i, step_a_i, step_b_i, out_ready_i, completion_ready_i);
        a.after_void(index,host_startup::Kind::combo_ignore);
    } catch(...) {a.poison();throw;}
}
long long __wrap_qwen2_matrix_command_endpoint_3_protectlib_combo_update(void* handle___05FV, svLogic seed_begin_valid_i, svLogic* seed_begin_ready_o, const svLogicVecVal* seed_context_i, const svLogicVecVal* seed_group_tag_i, const svLogicVecVal* seed_group_sequence_i, const svLogicVecVal* seed_source_generation_i, svLogic seed_beat_valid_i, svLogic* seed_beat_ready_o, const svLogicVecVal* seed_cluster_i, const svLogicVecVal* seed_data_i, svLogic seed_commit_valid_i, svLogic* seed_commit_ready_o, svLogic seed_abort_i, svLogic* seed_ack_valid_o, svLogic seed_ack_ready_i, svLogicVecVal* seed_ack_context_o, svLogicVecVal* seed_ack_group_tag_o, svLogicVecVal* seed_ack_group_sequence_o, svLogicVecVal* seed_ack_source_generation_o, svLogic* seed_ack_error_o, svLogic* seed_reset_required_o, svLogicVecVal* arithmetic_busy_o, svLogic* arithmetic_out_valid_o, svLogic cmd_valid_i, svLogic* cmd_ready_o, const svLogicVecVal* cmd_i, svLogic step_valid_i, svLogic* step_ready_o, const svLogicVecVal* step_context_i, svLogic step_clear_i, svLogic step_last_i, svLogic command_last_tile_i, const svLogicVecVal* step_a_i, const svLogicVecVal* step_b_i, svLogic* out_valid_o, svLogic out_ready_i, svLogicVecVal* out_context_o, svLogic* out_last_o, svLogicVecVal* out_acc_o, svLogic* completion_valid_o, svLogic completion_ready_i, svLogicVecVal* completion_data_o, svLogic* protocol_error_o) {
    auto& a=host_startup::ledger();
    try {
        const auto index=a.before_call(handle___05FV,host_startup::Kind::combo_update);
        a.no_job(seed_begin_valid_i,seed_beat_valid_i,seed_commit_valid_i,seed_abort_i,cmd_valid_i,step_valid_i);
        const long long actual=__real_qwen2_matrix_command_endpoint_3_protectlib_combo_update(handle___05FV, seed_begin_valid_i, seed_begin_ready_o, seed_context_i, seed_group_tag_i, seed_group_sequence_i, seed_source_generation_i, seed_beat_valid_i, seed_beat_ready_o, seed_cluster_i, seed_data_i, seed_commit_valid_i, seed_commit_ready_o, seed_abort_i, seed_ack_valid_o, seed_ack_ready_i, seed_ack_context_o, seed_ack_group_tag_o, seed_ack_group_sequence_o, seed_ack_source_generation_o, seed_ack_error_o, seed_reset_required_o, arithmetic_busy_o, arithmetic_out_valid_o, cmd_valid_i, cmd_ready_o, cmd_i, step_valid_i, step_ready_o, step_context_i, step_clear_i, step_last_i, command_last_tile_i, step_a_i, step_b_i, out_valid_o, out_ready_i, out_context_o, out_last_o, out_acc_o, completion_valid_o, completion_ready_i, completion_data_o, protocol_error_o);
        a.after_update(index,host_startup::Kind::combo_update,actual,*seed_ack_valid_o,*seed_ack_error_o,*seed_reset_required_o,*arithmetic_out_valid_o,*out_valid_o,*completion_valid_o,*protocol_error_o,arithmetic_busy_o);
        return actual;
    } catch(...) {a.poison();throw;}
}
void* __wrap_qwen2_matrix_command_endpoint_3_protectlib_create(const char* scope___05FV) {
    auto& a=host_startup::ledger();
    try {
        const auto index=a.before_create(scope___05FV);
        void* actual=__real_qwen2_matrix_command_endpoint_3_protectlib_create(scope___05FV);
        a.after_create(index,actual);
        return actual;
    } catch(...) {a.poison();throw;}
}
void __wrap_qwen2_matrix_command_endpoint_3_protectlib_final(void* handle___05FV) {
    auto& a=host_startup::ledger();
    try {
        const auto index=a.before_call(handle___05FV,host_startup::Kind::final);
        __real_qwen2_matrix_command_endpoint_3_protectlib_final(handle___05FV);
        a.after_void(index,host_startup::Kind::final);
    } catch(...) {a.poison();throw;}
}
long long __wrap_qwen2_matrix_command_endpoint_3_protectlib_seq_update(void* handle___05FV, svLogic* seed_begin_ready_o, svLogic* seed_beat_ready_o, svLogic* seed_commit_ready_o, svLogic* seed_ack_valid_o, svLogicVecVal* seed_ack_context_o, svLogicVecVal* seed_ack_group_tag_o, svLogicVecVal* seed_ack_group_sequence_o, svLogicVecVal* seed_ack_source_generation_o, svLogic* seed_ack_error_o, svLogic* seed_reset_required_o, svLogicVecVal* arithmetic_busy_o, svLogic* arithmetic_out_valid_o, svLogic clk_i, svLogic rst_ni, svLogic* cmd_ready_o, svLogic* step_ready_o, svLogic* out_valid_o, svLogicVecVal* out_context_o, svLogic* out_last_o, svLogicVecVal* out_acc_o, svLogic* completion_valid_o, svLogicVecVal* completion_data_o, svLogic* protocol_error_o) {
    auto& a=host_startup::ledger();
    try {
        const auto index=a.before_call(handle___05FV,host_startup::Kind::seq_update);
        a.seq_inputs(index,clk_i,rst_ni);
        const long long actual=__real_qwen2_matrix_command_endpoint_3_protectlib_seq_update(handle___05FV, seed_begin_ready_o, seed_beat_ready_o, seed_commit_ready_o, seed_ack_valid_o, seed_ack_context_o, seed_ack_group_tag_o, seed_ack_group_sequence_o, seed_ack_source_generation_o, seed_ack_error_o, seed_reset_required_o, arithmetic_busy_o, arithmetic_out_valid_o, clk_i, rst_ni, cmd_ready_o, step_ready_o, out_valid_o, out_context_o, out_last_o, out_acc_o, completion_valid_o, completion_data_o, protocol_error_o);
        a.after_update(index,host_startup::Kind::seq_update,actual,*seed_ack_valid_o,*seed_ack_error_o,*seed_reset_required_o,*arithmetic_out_valid_o,*out_valid_o,*completion_valid_o,*protocol_error_o,arithmetic_busy_o);
        return actual;
    } catch(...) {a.poison();throw;}
}
} // extern C

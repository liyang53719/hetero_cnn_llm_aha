// Source-only exact actual Host public-reference schema.
#pragma once
#include "generated_binding.hpp"
#include "host_ports.hpp"
namespace canonical_host::actual_v2 {
struct HostFields {
    static void require_same_root(const VHostBlockTop& d) {
        silu_observation::require(d.rootp!=nullptr,"actual Host root missing");
        silu_observation::require(&d.clock==&d.rootp->clock,"actual Host port alias clock");
        silu_observation::require(&d.reset==&d.rootp->reset,"actual Host port alias reset");
        silu_observation::require(&d.io_axi_w_ready==&d.rootp->io_axi_w_ready,"actual Host port alias io_axi_w_ready");
        silu_observation::require(&d.io_axi_r_valid==&d.rootp->io_axi_r_valid,"actual Host port alias io_axi_r_valid");
        silu_observation::require(&d.io_launch_ready==&d.rootp->io_launch_ready,"actual Host port alias io_launch_ready");
        silu_observation::require(&d.io_launch_valid==&d.rootp->io_launch_valid,"actual Host port alias io_launch_valid");
        silu_observation::require(&d.io_launch_bits_regions_0_read==&d.rootp->io_launch_bits_regions_0_read,"actual Host port alias io_launch_bits_regions_0_read");
        silu_observation::require(&d.io_launch_bits_regions_0_write==&d.rootp->io_launch_bits_regions_0_write,"actual Host port alias io_launch_bits_regions_0_write");
        silu_observation::require(&d.io_launch_bits_regions_1_read==&d.rootp->io_launch_bits_regions_1_read,"actual Host port alias io_launch_bits_regions_1_read");
        silu_observation::require(&d.io_launch_bits_regions_1_write==&d.rootp->io_launch_bits_regions_1_write,"actual Host port alias io_launch_bits_regions_1_write");
        silu_observation::require(&d.io_launch_bits_regions_2_read==&d.rootp->io_launch_bits_regions_2_read,"actual Host port alias io_launch_bits_regions_2_read");
        silu_observation::require(&d.io_launch_bits_regions_2_write==&d.rootp->io_launch_bits_regions_2_write,"actual Host port alias io_launch_bits_regions_2_write");
        silu_observation::require(&d.io_launch_bits_regions_3_read==&d.rootp->io_launch_bits_regions_3_read,"actual Host port alias io_launch_bits_regions_3_read");
        silu_observation::require(&d.io_launch_bits_regions_3_write==&d.rootp->io_launch_bits_regions_3_write,"actual Host port alias io_launch_bits_regions_3_write");
        silu_observation::require(&d.io_result_ready==&d.rootp->io_result_ready,"actual Host port alias io_result_ready");
        silu_observation::require(&d.io_result_valid==&d.rootp->io_result_valid,"actual Host port alias io_result_valid");
        silu_observation::require(&d.io_result_bits_status==&d.rootp->io_result_bits_status,"actual Host port alias io_result_bits_status");
        silu_observation::require(&d.io_completion_ready==&d.rootp->io_completion_ready,"actual Host port alias io_completion_ready");
        silu_observation::require(&d.io_completion_valid==&d.rootp->io_completion_valid,"actual Host port alias io_completion_valid");
        silu_observation::require(&d.io_axi_aw_ready==&d.rootp->io_axi_aw_ready,"actual Host port alias io_axi_aw_ready");
        silu_observation::require(&d.io_axi_aw_valid==&d.rootp->io_axi_aw_valid,"actual Host port alias io_axi_aw_valid");
        silu_observation::require(&d.io_axi_aw_bits_id==&d.rootp->io_axi_aw_bits_id,"actual Host port alias io_axi_aw_bits_id");
        silu_observation::require(&d.io_axi_aw_bits_len==&d.rootp->io_axi_aw_bits_len,"actual Host port alias io_axi_aw_bits_len");
        silu_observation::require(&d.io_axi_aw_bits_size==&d.rootp->io_axi_aw_bits_size,"actual Host port alias io_axi_aw_bits_size");
        silu_observation::require(&d.io_axi_aw_bits_burst==&d.rootp->io_axi_aw_bits_burst,"actual Host port alias io_axi_aw_bits_burst");
        silu_observation::require(&d.io_axi_w_valid==&d.rootp->io_axi_w_valid,"actual Host port alias io_axi_w_valid");
        silu_observation::require(&d.io_axi_w_bits_last==&d.rootp->io_axi_w_bits_last,"actual Host port alias io_axi_w_bits_last");
        silu_observation::require(&d.io_axi_b_ready==&d.rootp->io_axi_b_ready,"actual Host port alias io_axi_b_ready");
        silu_observation::require(&d.io_axi_b_valid==&d.rootp->io_axi_b_valid,"actual Host port alias io_axi_b_valid");
        silu_observation::require(&d.io_axi_b_bits_id==&d.rootp->io_axi_b_bits_id,"actual Host port alias io_axi_b_bits_id");
        silu_observation::require(&d.io_axi_b_bits_resp==&d.rootp->io_axi_b_bits_resp,"actual Host port alias io_axi_b_bits_resp");
        silu_observation::require(&d.io_axi_ar_ready==&d.rootp->io_axi_ar_ready,"actual Host port alias io_axi_ar_ready");
        silu_observation::require(&d.io_axi_ar_valid==&d.rootp->io_axi_ar_valid,"actual Host port alias io_axi_ar_valid");
        silu_observation::require(&d.io_axi_ar_bits_id==&d.rootp->io_axi_ar_bits_id,"actual Host port alias io_axi_ar_bits_id");
        silu_observation::require(&d.io_axi_ar_bits_len==&d.rootp->io_axi_ar_bits_len,"actual Host port alias io_axi_ar_bits_len");
        silu_observation::require(&d.io_axi_ar_bits_size==&d.rootp->io_axi_ar_bits_size,"actual Host port alias io_axi_ar_bits_size");
        silu_observation::require(&d.io_axi_ar_bits_burst==&d.rootp->io_axi_ar_bits_burst,"actual Host port alias io_axi_ar_bits_burst");
        silu_observation::require(&d.io_axi_r_ready==&d.rootp->io_axi_r_ready,"actual Host port alias io_axi_r_ready");
        silu_observation::require(&d.io_axi_r_bits_id==&d.rootp->io_axi_r_bits_id,"actual Host port alias io_axi_r_bits_id");
        silu_observation::require(&d.io_axi_r_bits_resp==&d.rootp->io_axi_r_bits_resp,"actual Host port alias io_axi_r_bits_resp");
        silu_observation::require(&d.io_axi_r_bits_last==&d.rootp->io_axi_r_bits_last,"actual Host port alias io_axi_r_bits_last");
        silu_observation::require(&d.io_resetRequired==&d.rootp->io_resetRequired,"actual Host port alias io_resetRequired");
        silu_observation::require(&d.io_launch_bits_commands==&d.rootp->io_launch_bits_commands,"actual Host port alias io_launch_bits_commands");
        silu_observation::require(&d.io_launch_bits_epoch==&d.rootp->io_launch_bits_epoch,"actual Host port alias io_launch_bits_epoch");
        silu_observation::require(&d.io_result_bits_completed==&d.rootp->io_result_bits_completed,"actual Host port alias io_result_bits_completed");
        silu_observation::require(&d.io_result_bits_failedPc==&d.rootp->io_result_bits_failedPc,"actual Host port alias io_result_bits_failedPc");
        silu_observation::require(&d.io_result_bits_epoch==&d.rootp->io_result_bits_epoch,"actual Host port alias io_result_bits_epoch");
        silu_observation::require(&d.io_pc==&d.rootp->io_pc,"actual Host port alias io_pc");
        silu_observation::require(&d.io_issuedJobs==&d.rootp->io_issuedJobs,"actual Host port alias io_issuedJobs");
        silu_observation::require(&d.io_launch_bits_descriptors==&d.rootp->io_launch_bits_descriptors,"actual Host port alias io_launch_bits_descriptors");
        silu_observation::require(&d.io_axi_w_bits_data==&d.rootp->io_axi_w_bits_data,"actual Host port alias io_axi_w_bits_data");
        silu_observation::require(&d.io_axi_r_bits_data==&d.rootp->io_axi_r_bits_data,"actual Host port alias io_axi_r_bits_data");
        silu_observation::require(&d.io_launch_bits_commandBase==&d.rootp->io_launch_bits_commandBase,"actual Host port alias io_launch_bits_commandBase");
        silu_observation::require(&d.io_launch_bits_commandLimit==&d.rootp->io_launch_bits_commandLimit,"actual Host port alias io_launch_bits_commandLimit");
        silu_observation::require(&d.io_launch_bits_descriptorBase==&d.rootp->io_launch_bits_descriptorBase,"actual Host port alias io_launch_bits_descriptorBase");
        silu_observation::require(&d.io_launch_bits_descriptorLimit==&d.rootp->io_launch_bits_descriptorLimit,"actual Host port alias io_launch_bits_descriptorLimit");
        silu_observation::require(&d.io_launch_bits_regions_0_base==&d.rootp->io_launch_bits_regions_0_base,"actual Host port alias io_launch_bits_regions_0_base");
        silu_observation::require(&d.io_launch_bits_regions_0_limit==&d.rootp->io_launch_bits_regions_0_limit,"actual Host port alias io_launch_bits_regions_0_limit");
        silu_observation::require(&d.io_launch_bits_regions_1_base==&d.rootp->io_launch_bits_regions_1_base,"actual Host port alias io_launch_bits_regions_1_base");
        silu_observation::require(&d.io_launch_bits_regions_1_limit==&d.rootp->io_launch_bits_regions_1_limit,"actual Host port alias io_launch_bits_regions_1_limit");
        silu_observation::require(&d.io_launch_bits_regions_2_base==&d.rootp->io_launch_bits_regions_2_base,"actual Host port alias io_launch_bits_regions_2_base");
        silu_observation::require(&d.io_launch_bits_regions_2_limit==&d.rootp->io_launch_bits_regions_2_limit,"actual Host port alias io_launch_bits_regions_2_limit");
        silu_observation::require(&d.io_launch_bits_regions_3_base==&d.rootp->io_launch_bits_regions_3_base,"actual Host port alias io_launch_bits_regions_3_base");
        silu_observation::require(&d.io_launch_bits_regions_3_limit==&d.rootp->io_launch_bits_regions_3_limit,"actual Host port alias io_launch_bits_regions_3_limit");
        silu_observation::require(&d.io_completion_bits==&d.rootp->io_completion_bits,"actual Host port alias io_completion_bits");
        silu_observation::require(&d.io_axi_aw_bits_addr==&d.rootp->io_axi_aw_bits_addr,"actual Host port alias io_axi_aw_bits_addr");
        silu_observation::require(&d.io_axi_w_bits_strb==&d.rootp->io_axi_w_bits_strb,"actual Host port alias io_axi_w_bits_strb");
        silu_observation::require(&d.io_axi_ar_bits_addr==&d.rootp->io_axi_ar_bits_addr,"actual Host port alias io_axi_ar_bits_addr");
        silu_observation::require(&d.io_idmaTransfers==&d.rootp->io_idmaTransfers,"actual Host port alias io_idmaTransfers");
        silu_observation::require(&d.io_idmaStreamedWriteBeats==&d.rootp->io_idmaStreamedWriteBeats,"actual Host port alias io_idmaStreamedWriteBeats");
        silu_observation::require(&d.io_idmaStreamedBeats==&d.rootp->io_idmaStreamedBeats,"actual Host port alias io_idmaStreamedBeats");
        silu_observation::require(&d.io_pipelineIssues==&d.rootp->io_pipelineIssues,"actual Host port alias io_pipelineIssues");
        silu_observation::require(&d.io_pipelineStalls==&d.rootp->io_pipelineStalls,"actual Host port alias io_pipelineStalls");
        silu_observation::require(&d.io_idmaReadBursts==&d.rootp->io_idmaReadBursts,"actual Host port alias io_idmaReadBursts");
        silu_observation::require(&d.io_idmaReadBeats==&d.rootp->io_idmaReadBeats,"actual Host port alias io_idmaReadBeats");
        silu_observation::require(&d.io_idmaCacheHits==&d.rootp->io_idmaCacheHits,"actual Host port alias io_idmaCacheHits");
        silu_observation::require(&d.io_usefulMacs==&d.rootp->io_usefulMacs,"actual Host port alias io_usefulMacs");
        silu_observation::require(&d.io_executedMacs==&d.rootp->io_executedMacs,"actual Host port alias io_executedMacs");
        silu_observation::require(&d.io_writeBytes==&d.rootp->io_writeBytes,"actual Host port alias io_writeBytes");
        silu_observation::require(&d.io_memoryAccepted_0==&d.rootp->io_memoryAccepted_0,"actual Host port alias io_memoryAccepted_0");
        silu_observation::require(&d.io_memoryAccepted_1==&d.rootp->io_memoryAccepted_1,"actual Host port alias io_memoryAccepted_1");
        silu_observation::require(&d.io_memoryReturned_0==&d.rootp->io_memoryReturned_0,"actual Host port alias io_memoryReturned_0");
        silu_observation::require(&d.io_memoryReturned_1==&d.rootp->io_memoryReturned_1,"actual Host port alias io_memoryReturned_1");
    }
    using InputSnapshot=std::array<uint64_t,54>;
    static InputSnapshot input_snapshot(const VHostBlockTop& d) {
        require_same_root(d);
        return {{d.clock,d.reset,d.io_axi_w_ready,d.io_axi_r_valid,d.io_launch_valid,d.io_launch_bits_regions_0_read,d.io_launch_bits_regions_0_write,d.io_launch_bits_regions_1_read,d.io_launch_bits_regions_1_write,d.io_launch_bits_regions_2_read,d.io_launch_bits_regions_2_write,d.io_launch_bits_regions_3_read,d.io_launch_bits_regions_3_write,d.io_result_ready,d.io_completion_ready,d.io_axi_aw_ready,d.io_axi_b_valid,d.io_axi_b_bits_id,d.io_axi_b_bits_resp,d.io_axi_ar_ready,d.io_axi_r_bits_id,d.io_axi_r_bits_resp,d.io_axi_r_bits_last,d.io_launch_bits_commands,d.io_launch_bits_epoch,d.io_launch_bits_descriptors,d.io_axi_r_bits_data[0],d.io_axi_r_bits_data[1],d.io_axi_r_bits_data[2],d.io_axi_r_bits_data[3],d.io_axi_r_bits_data[4],d.io_axi_r_bits_data[5],d.io_axi_r_bits_data[6],d.io_axi_r_bits_data[7],d.io_axi_r_bits_data[8],d.io_axi_r_bits_data[9],d.io_axi_r_bits_data[10],d.io_axi_r_bits_data[11],d.io_axi_r_bits_data[12],d.io_axi_r_bits_data[13],d.io_axi_r_bits_data[14],d.io_axi_r_bits_data[15],d.io_launch_bits_commandBase,d.io_launch_bits_commandLimit,d.io_launch_bits_descriptorBase,d.io_launch_bits_descriptorLimit,d.io_launch_bits_regions_0_base,d.io_launch_bits_regions_0_limit,d.io_launch_bits_regions_1_base,d.io_launch_bits_regions_1_limit,d.io_launch_bits_regions_2_base,d.io_launch_bits_regions_2_limit,d.io_launch_bits_regions_3_base,d.io_launch_bits_regions_3_limit}};
    }
    static void initialize_inputs(VHostBlockTop& d) {require_same_root(d);HostPins<VHostBlockTop>::initialize_inputs(d);}
    static void launch_payload(VHostBlockTop& d) {require_same_root(d);HostPins<VHostBlockTop>::launch_payload(d);}
    static HostResult result(const VHostBlockTop& d) {require_same_root(d);return HostPins<VHostBlockTop>::result(d);}
    static HubCounts hub(const VHostBlockTop& d) {require_same_root(d);return HostPins<VHostBlockTop>::hub(d);}
    // Exact original AXI sample body, without importing a RAM implementation.
    static Sample axi_sample(const VHostBlockTop& d) {
        require_same_root(d);
        Sample s;
        s.ar_valid = d.io_axi_ar_valid; s.ar_ready = d.io_axi_ar_ready;
        s.aw_valid = d.io_axi_aw_valid; s.aw_ready = d.io_axi_aw_ready;
        s.w_valid = d.io_axi_w_valid; s.w_ready = d.io_axi_w_ready;
        s.r_valid = d.io_axi_r_valid; s.r_ready = d.io_axi_r_ready;
        s.b_valid = d.io_axi_b_valid; s.b_ready = d.io_axi_b_ready;
        s.ar = {d.io_axi_ar_bits_addr, d.io_axi_ar_bits_id, d.io_axi_ar_bits_len,
                d.io_axi_ar_bits_size, d.io_axi_ar_bits_burst};
        s.aw = {d.io_axi_aw_bits_addr, d.io_axi_aw_bits_id, d.io_axi_aw_bits_len,
                d.io_axi_aw_bits_size, d.io_axi_aw_bits_burst};
        s.w.strb = d.io_axi_w_bits_strb; s.w.last = d.io_axi_w_bits_last;
        for (unsigned i = 0; i < 16; ++i) s.w.data[i] = d.io_axi_w_bits_data[i];
        s.r.id = d.io_axi_r_bits_id; s.r.resp = d.io_axi_r_bits_resp; s.r.last = d.io_axi_r_bits_last;
        for (unsigned i = 0; i < 16; ++i) s.r.data[i] = d.io_axi_r_bits_data[i];
        s.b.id = d.io_axi_b_bits_id; s.b.resp = d.io_axi_b_bits_resp;
        return s;
    }
};
// No HostDriver, PhysicalObserver, RAM implementation or comparator is supplied.
} // namespace canonical_host::actual_v2

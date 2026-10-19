// New source-derived implementation, not a byte-recovered missing header.
// Partial public-pin adapter only. No launch_payload, RAM, loader or model admission.
#pragma once
#include <array>
#include <cstdint>

namespace canonical_host {
struct HostResult {
    std::uint8_t status = 0;
    std::uint16_t completed = 0, failedPc = 0, epoch = 0;
};
struct HubCounts {
    std::array<std::uint64_t, 2> accepted{}, returned{};
    bool operator==(const HubCounts& other) const {
        return accepted == other.accepted && returned == other.returned;
    }
};

template<class Model> struct HostPins {
    // Exact 54 published zero assignments. Does not evaluate or sequence reset.
    static void initialize_inputs(Model& d) {
    d.clock=0;
    d.reset=0;
    d.io_axi_w_ready=0;
    d.io_axi_r_valid=0;
    d.io_launch_valid=0;
    d.io_launch_bits_regions_0_read=0;
    d.io_launch_bits_regions_0_write=0;
    d.io_launch_bits_regions_1_read=0;
    d.io_launch_bits_regions_1_write=0;
    d.io_launch_bits_regions_2_read=0;
    d.io_launch_bits_regions_2_write=0;
    d.io_launch_bits_regions_3_read=0;
    d.io_launch_bits_regions_3_write=0;
    d.io_result_ready=0;
    d.io_completion_ready=0;
    d.io_axi_aw_ready=0;
    d.io_axi_b_valid=0;
    d.io_axi_b_bits_id=0;
    d.io_axi_b_bits_resp=0;
    d.io_axi_ar_ready=0;
    d.io_axi_r_bits_id=0;
    d.io_axi_r_bits_resp=0;
    d.io_axi_r_bits_last=0;
    d.io_launch_bits_commands=0;
    d.io_launch_bits_epoch=0;
    d.io_launch_bits_descriptors=0;
    d.io_axi_r_bits_data[0]=0;
    d.io_axi_r_bits_data[1]=0;
    d.io_axi_r_bits_data[2]=0;
    d.io_axi_r_bits_data[3]=0;
    d.io_axi_r_bits_data[4]=0;
    d.io_axi_r_bits_data[5]=0;
    d.io_axi_r_bits_data[6]=0;
    d.io_axi_r_bits_data[7]=0;
    d.io_axi_r_bits_data[8]=0;
    d.io_axi_r_bits_data[9]=0;
    d.io_axi_r_bits_data[10]=0;
    d.io_axi_r_bits_data[11]=0;
    d.io_axi_r_bits_data[12]=0;
    d.io_axi_r_bits_data[13]=0;
    d.io_axi_r_bits_data[14]=0;
    d.io_axi_r_bits_data[15]=0;
    d.io_launch_bits_commandBase=0;
    d.io_launch_bits_commandLimit=0;
    d.io_launch_bits_descriptorBase=0;
    d.io_launch_bits_descriptorLimit=0;
    d.io_launch_bits_regions_0_base=0;
    d.io_launch_bits_regions_0_limit=0;
    d.io_launch_bits_regions_1_base=0;
    d.io_launch_bits_regions_1_limit=0;
    d.io_launch_bits_regions_2_base=0;
    d.io_launch_bits_regions_2_limit=0;
    d.io_launch_bits_regions_3_base=0;
    d.io_launch_bits_regions_3_limit=0;
    }
    static HostResult result(const Model& d) {
        HostResult value{};
        value.status = d.io_result_bits_status;
        value.completed = d.io_result_bits_completed;
        value.failedPc = d.io_result_bits_failedPc;
        value.epoch = d.io_result_bits_epoch;
        return value;
    }
    static HubCounts hub(const Model& d) {
        HubCounts value{};
        value.accepted[0] = d.io_memoryAccepted_0;
        value.accepted[1] = d.io_memoryAccepted_1;
        value.returned[0] = d.io_memoryReturned_0;
        value.returned[1] = d.io_memoryReturned_1;
        return value;
    }
};
} // namespace canonical_host

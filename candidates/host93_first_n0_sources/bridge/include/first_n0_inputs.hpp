#pragma once
#include "VHostBlockTop.h"
#include "host_ports.hpp"
namespace canonical_runtime_v1::first_n0 {
inline std::array<std::uint64_t,54> input_snapshot(const VHostBlockTop& d) {
            return {{d.clock,d.reset,d.io_axi_w_ready,d.io_axi_r_valid,d.io_launch_valid,d.io_launch_bits_regions_0_read,d.io_launch_bits_regions_0_write,d.io_launch_bits_regions_1_read,d.io_launch_bits_regions_1_write,d.io_launch_bits_regions_2_read,d.io_launch_bits_regions_2_write,d.io_launch_bits_regions_3_read,d.io_launch_bits_regions_3_write,d.io_result_ready,d.io_completion_ready,d.io_axi_aw_ready,d.io_axi_b_valid,d.io_axi_b_bits_id,d.io_axi_b_bits_resp,d.io_axi_ar_ready,d.io_axi_r_bits_id,d.io_axi_r_bits_resp,d.io_axi_r_bits_last,d.io_launch_bits_commands,d.io_launch_bits_epoch,d.io_launch_bits_descriptors,d.io_axi_r_bits_data[0],d.io_axi_r_bits_data[1],d.io_axi_r_bits_data[2],d.io_axi_r_bits_data[3],d.io_axi_r_bits_data[4],d.io_axi_r_bits_data[5],d.io_axi_r_bits_data[6],d.io_axi_r_bits_data[7],d.io_axi_r_bits_data[8],d.io_axi_r_bits_data[9],d.io_axi_r_bits_data[10],d.io_axi_r_bits_data[11],d.io_axi_r_bits_data[12],d.io_axi_r_bits_data[13],d.io_axi_r_bits_data[14],d.io_axi_r_bits_data[15],d.io_launch_bits_commandBase,d.io_launch_bits_commandLimit,d.io_launch_bits_descriptorBase,d.io_launch_bits_descriptorLimit,d.io_launch_bits_regions_0_base,d.io_launch_bits_regions_0_limit,d.io_launch_bits_regions_1_base,d.io_launch_bits_regions_1_limit,d.io_launch_bits_regions_2_base,d.io_launch_bits_regions_2_limit,d.io_launch_bits_regions_3_base,d.io_launch_bits_regions_3_limit}};
}
inline void zero_inputs(VHostBlockTop& d) {canonical_host::HostPins<VHostBlockTop>::initialize_inputs(d);}
}

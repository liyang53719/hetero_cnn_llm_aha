// Exact actual public inputs; no metadata provider, no RAM and no launch.
#pragma once
#include "VHostBlockTop.h"
#include "VHostBlockTop___024root.h"
#include <array>
#include <cstdint>
namespace host_startup {
inline void zero_inputs(VHostBlockTop& d) {
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
inline std::array<uint64_t,54> input_snapshot(const VHostBlockTop& d) {
    return {{d.clock,d.reset,d.io_axi_w_ready,d.io_axi_r_valid,d.io_launch_valid,d.io_launch_bits_regions_0_read,d.io_launch_bits_regions_0_write,d.io_launch_bits_regions_1_read,d.io_launch_bits_regions_1_write,d.io_launch_bits_regions_2_read,d.io_launch_bits_regions_2_write,d.io_launch_bits_regions_3_read,d.io_launch_bits_regions_3_write,d.io_result_ready,d.io_completion_ready,d.io_axi_aw_ready,d.io_axi_b_valid,d.io_axi_b_bits_id,d.io_axi_b_bits_resp,d.io_axi_ar_ready,d.io_axi_r_bits_id,d.io_axi_r_bits_resp,d.io_axi_r_bits_last,d.io_launch_bits_commands,d.io_launch_bits_epoch,d.io_launch_bits_descriptors,d.io_axi_r_bits_data[0],d.io_axi_r_bits_data[1],d.io_axi_r_bits_data[2],d.io_axi_r_bits_data[3],d.io_axi_r_bits_data[4],d.io_axi_r_bits_data[5],d.io_axi_r_bits_data[6],d.io_axi_r_bits_data[7],d.io_axi_r_bits_data[8],d.io_axi_r_bits_data[9],d.io_axi_r_bits_data[10],d.io_axi_r_bits_data[11],d.io_axi_r_bits_data[12],d.io_axi_r_bits_data[13],d.io_axi_r_bits_data[14],d.io_axi_r_bits_data[15],d.io_launch_bits_commandBase,d.io_launch_bits_commandLimit,d.io_launch_bits_descriptorBase,d.io_launch_bits_descriptorLimit,d.io_launch_bits_regions_0_base,d.io_launch_bits_regions_0_limit,d.io_launch_bits_regions_1_base,d.io_launch_bits_regions_1_limit,d.io_launch_bits_regions_2_base,d.io_launch_bits_regions_2_limit,d.io_launch_bits_regions_3_base,d.io_launch_bits_regions_3_limit}};
}
inline std::array<uint64_t,8> root_handles(const VHostBlockTop& d) {
    const auto& r=*d.rootp;
    return {{r.HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_0__DOT__handle___05FV,r.HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_1__DOT__handle___05FV,r.HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_2__DOT__handle___05FV,r.HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_3__DOT__handle___05FV,r.HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_4__DOT__handle___05FV,r.HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_5__DOT__handle___05FV,r.HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_6__DOT__handle___05FV,r.HostBlockTop__DOT__owner__DOT__matrix__DOT__leaves_7__DOT__handle___05FV}};
}
inline std::array<unsigned,8> gate_clocks(const VHostBlockTop& d) {
    const auto& r=*d.rootp;
    return {{r.HostBlockTop__DOT__owner__DOT__matrix__DOT___gate_clk_o,r.HostBlockTop__DOT__owner__DOT__matrix__DOT___gate_1_clk_o,r.HostBlockTop__DOT__owner__DOT__matrix__DOT___gate_2_clk_o,r.HostBlockTop__DOT__owner__DOT__matrix__DOT___gate_3_clk_o,r.HostBlockTop__DOT__owner__DOT__matrix__DOT___gate_4_clk_o,r.HostBlockTop__DOT__owner__DOT__matrix__DOT___gate_5_clk_o,r.HostBlockTop__DOT__owner__DOT__matrix__DOT___gate_6_clk_o,r.HostBlockTop__DOT__owner__DOT__matrix__DOT___gate_7_clk_o}};
}
} // namespace host_startup

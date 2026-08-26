// SPDX-License-Identifier: Apache-2.0
// Transaction-locked mux between AHA proc-packet and dedicated INT8 SFU tile.
`timescale 1ns/1ps
module sfu_stream_endpoint_mux(
  input logic clk_i,input logic rst_ni,input logic select_dedicated_i,
  input logic aha_cfg_valid_i,output logic aha_cfg_ready_o,
  input logic[17:0]aha_cfg_input_base_i,aha_cfg_output_base_i,
  input logic[15:0]aha_cfg_input_beats_i,aha_cfg_output_beats_i,aha_cfg_output_tag_i,
  input logic[11:0]aha_cfg_output_tensor_id_i,input logic[3:0]aha_cfg_output_format_i,
  input logic[63:0]aha_cfg_output_last_be_i,input logic aha_run_done_i,
  output logic aha_proc_packet_wr_en_o,output logic[17:0]aha_proc_packet_wr_addr_o,
  output logic[63:0]aha_proc_packet_wr_data_o,output logic[7:0]aha_proc_packet_wr_strb_o,
  output logic aha_proc_packet_rd_en_o,output logic[17:0]aha_proc_packet_rd_addr_o,
  input logic[63:0]aha_proc_packet_rd_data_i,input logic aha_proc_packet_rd_data_valid_i,
  output logic aha_native_eos_o,output logic aha_transfer_done_o,
  output logic[31:0]aha_protocol_error_count_o,
  input logic dedicated_cfg_valid_i,output logic dedicated_cfg_ready_o,
  input logic dedicated_cfg_op_i,input logic[3:0]dedicated_cfg_h_i,dedicated_cfg_w_i,
  input logic[4:0]dedicated_cfg_c_i,input logic[6:0]dedicated_cfg_bytes_i,
  input logic[15:0]dedicated_cfg_tag_i,input logic[11:0]dedicated_cfg_tensor_id_i,
  input logic[3:0]dedicated_cfg_format_i,
  input logic secondary_valid_i,output logic secondary_ready_o,
  input logic[511:0]secondary_data_i,input logic[63:0]secondary_be_i,
  input logic secondary_last_i,input logic[3:0]secondary_format_i,
  output logic dedicated_transfer_done_o,
  output logic[31:0]dedicated_protocol_error_count_o,
  output logic[31:0]mux_protocol_error_count_o,
  input logic primary_valid_i,output logic primary_ready_o,
  input logic[511:0]primary_data_i,input logic[63:0]primary_be_i,
  input logic[15:0]primary_tag_i,input logic[11:0]primary_tensor_id_i,
  input logic primary_last_i,input logic[3:0]primary_format_i,
  output logic out_valid_o,input logic out_ready_i,output logic[511:0]out_data_o,
  output logic[63:0]out_be_o,output logic[15:0]out_tag_o,
  output logic[11:0]out_tensor_id_o,output logic out_last_o,
  output logic[3:0]out_format_o
);
  logic active_q,mode_q;logic aha_cfg_ready_int,dedicated_cfg_ready_int;
  logic aha_in_ready,aha_out_valid,aha_out_ready,aha_out_last;
  logic[511:0]aha_out_data;logic[63:0]aha_out_be;logic[15:0]aha_out_tag;
  logic[11:0]aha_out_tensor;logic[3:0]aha_out_format;
  logic dedicated_primary_ready,dedicated_out_valid,dedicated_out_ready,dedicated_out_last;
  logic[511:0]dedicated_out_data;logic[63:0]dedicated_out_be;logic[15:0]dedicated_out_tag;
  logic[11:0]dedicated_out_tensor;logic[3:0]dedicated_out_format;
  logic aha_cfg_fire,dedicated_cfg_fire;
  assign aha_cfg_ready_o=!active_q&&!select_dedicated_i&&aha_cfg_ready_int;
  assign dedicated_cfg_ready_o=!active_q&&select_dedicated_i&&dedicated_cfg_ready_int;
  assign aha_cfg_fire=aha_cfg_valid_i&&aha_cfg_ready_o;
  assign dedicated_cfg_fire=dedicated_cfg_valid_i&&dedicated_cfg_ready_o;
  assign primary_ready_o=!active_q?1'b0:(mode_q?dedicated_primary_ready:aha_in_ready);
  assign aha_out_ready=active_q&&!mode_q&&out_ready_i;
  assign dedicated_out_ready=active_q&&mode_q&&out_ready_i;
  always_comb begin
    out_valid_o=0;out_data_o=0;out_be_o=0;out_tag_o=0;out_tensor_id_o=0;out_last_o=0;out_format_o=0;
    if(active_q&&mode_q)begin out_valid_o=dedicated_out_valid;out_be_o='1;
      for(int byte_index=0;byte_index<64;byte_index++)
        out_data_o[byte_index*8 +:8]=dedicated_out_be[byte_index]?
          dedicated_out_data[byte_index*8 +:8]:8'd0;
      out_tag_o=dedicated_out_tag;out_tensor_id_o=dedicated_out_tensor;
      out_last_o=dedicated_out_last;out_format_o=dedicated_out_format;end
    else if(active_q)begin out_valid_o=aha_out_valid;out_data_o=aha_out_data;out_be_o=aha_out_be;
      out_tag_o=aha_out_tag;out_tensor_id_o=aha_out_tensor;out_last_o=aha_out_last;out_format_o=aha_out_format;end
  end
  aha_tensor_stream_endpoint u_aha(
    .clk_i,.rst_ni,.cfg_valid_i(aha_cfg_valid_i&&!active_q&&!select_dedicated_i),
    .cfg_ready_o(aha_cfg_ready_int),.cfg_input_base_i(aha_cfg_input_base_i),
    .cfg_output_base_i(aha_cfg_output_base_i),.cfg_input_beats_i(aha_cfg_input_beats_i),
    .cfg_output_beats_i(aha_cfg_output_beats_i),.cfg_output_tag_i(aha_cfg_output_tag_i),
    .cfg_output_tensor_id_i(aha_cfg_output_tensor_id_i),.cfg_output_format_i(aha_cfg_output_format_i),
    .cfg_output_last_be_i(aha_cfg_output_last_be_i),.run_done_i(aha_run_done_i),
    .stream_in_valid_i(primary_valid_i&&active_q&&!mode_q),.stream_in_ready_o(aha_in_ready),
    .stream_in_data_i(primary_data_i),.stream_in_be_i(primary_be_i),.stream_in_tag_i(primary_tag_i),
    .stream_in_tensor_id_i(primary_tensor_id_i),.stream_in_last_i(primary_last_i),
    .stream_in_format_i(primary_format_i),.stream_out_valid_o(aha_out_valid),
    .stream_out_ready_i(aha_out_ready),.stream_out_data_o(aha_out_data),.stream_out_be_o(aha_out_be),
    .stream_out_tag_o(aha_out_tag),.stream_out_tensor_id_o(aha_out_tensor),
    .stream_out_last_o(aha_out_last),.stream_out_format_o(aha_out_format),
    .proc_packet_wr_en_o(aha_proc_packet_wr_en_o),.proc_packet_wr_addr_o(aha_proc_packet_wr_addr_o),
    .proc_packet_wr_data_o(aha_proc_packet_wr_data_o),.proc_packet_wr_strb_o(aha_proc_packet_wr_strb_o),
    .proc_packet_rd_en_o(aha_proc_packet_rd_en_o),.proc_packet_rd_addr_o(aha_proc_packet_rd_addr_o),
    .proc_packet_rd_data_i(aha_proc_packet_rd_data_i),.proc_packet_rd_data_valid_i(aha_proc_packet_rd_data_valid_i),
    .native_eos_o(aha_native_eos_o),.transfer_done_o(aha_transfer_done_o),
    .protocol_error_count_o(aha_protocol_error_count_o));
  int8_pool_residual_sfu u_dedicated(
    .clk_i,.rst_ni,.cfg_valid_i(dedicated_cfg_valid_i&&!active_q&&select_dedicated_i),
    .cfg_ready_o(dedicated_cfg_ready_int),.cfg_op_i(dedicated_cfg_op_i),
    .cfg_h_i(dedicated_cfg_h_i),.cfg_w_i(dedicated_cfg_w_i),.cfg_c_i(dedicated_cfg_c_i),
    .cfg_bytes_i(dedicated_cfg_bytes_i),.cfg_tag_i(dedicated_cfg_tag_i),
    .cfg_tensor_id_i(dedicated_cfg_tensor_id_i),.cfg_format_i(dedicated_cfg_format_i),
    .primary_valid_i(primary_valid_i&&active_q&&mode_q),.primary_ready_o(dedicated_primary_ready),
    .primary_data_i(primary_data_i),.primary_be_i(primary_be_i),.primary_last_i(primary_last_i),
    .primary_format_i(primary_format_i),.secondary_valid_i(secondary_valid_i&&active_q&&mode_q),
    .secondary_ready_o(secondary_ready_o),.secondary_data_i(secondary_data_i),
    .secondary_be_i(secondary_be_i),.secondary_last_i(secondary_last_i),
    .secondary_format_i(secondary_format_i),.out_valid_o(dedicated_out_valid),
    .out_ready_i(dedicated_out_ready),.out_data_o(dedicated_out_data),.out_be_o(dedicated_out_be),
    .out_tag_o(dedicated_out_tag),.out_tensor_id_o(dedicated_out_tensor),
    .out_last_o(dedicated_out_last),.out_format_o(dedicated_out_format),
    .transfer_done_o(dedicated_transfer_done_o),
    .protocol_error_count_o(dedicated_protocol_error_count_o));
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin active_q<=0;mode_q<=0;mux_protocol_error_count_o<=0;end else begin
      if(aha_cfg_fire)begin active_q<=1;mode_q<=0;end
      else if(dedicated_cfg_fire)begin active_q<=1;mode_q<=1;end
      if(active_q&&select_dedicated_i!=mode_q)mux_protocol_error_count_o<=mux_protocol_error_count_o+1'b1;
      if(active_q&&((mode_q&&dedicated_transfer_done_o)||(!mode_q&&aha_transfer_done_o)))active_q<=0;
    end
  end
endmodule

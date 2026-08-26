// SPDX-License-Identifier: Apache-2.0
// Tensor Stream endpoint for the external 512 KiB KV staging store.
`timescale 1ns/1ps
module kv_tensor_stream_endpoint #(
  parameter integer STAGING_BYTES = 512*1024
) (
  input  logic          clk_i,
  input  logic          rst_ni,
  input  logic          cfg_valid_i,
  output logic          cfg_ready_o,
  input  logic          cfg_direction_i,
  input  logic [18:0]   cfg_base_addr_i,
  input  logic [15:0]   cfg_beats_i,
  input  logic [15:0]   cfg_tag_i,
  input  logic [11:0]   cfg_tensor_id_i,
  input  logic [3:0]    cfg_format_i,
  input  logic [63:0]   cfg_last_be_i,

  input  logic          stream_in_valid_i,
  output logic          stream_in_ready_o,
  input  logic [511:0]  stream_in_data_i,
  input  logic [63:0]   stream_in_be_i,
  input  logic [15:0]   stream_in_tag_i,
  input  logic [11:0]   stream_in_tensor_id_i,
  input  logic          stream_in_last_i,
  input  logic [3:0]    stream_in_format_i,
  output logic          stream_out_valid_o,
  input  logic          stream_out_ready_i,
  output logic [511:0]  stream_out_data_o,
  output logic [63:0]   stream_out_be_o,
  output logic [15:0]   stream_out_tag_o,
  output logic [11:0]   stream_out_tensor_id_o,
  output logic          stream_out_last_o,
  output logic [3:0]    stream_out_format_o,

  output logic          mem_write_valid_o,
  input  logic          mem_write_ready_i,
  output logic [18:0]   mem_write_addr_o,
  output logic [511:0]  mem_write_data_o,
  output logic [63:0]   mem_write_be_o,
  output logic          mem_read_req_valid_o,
  input  logic          mem_read_req_ready_i,
  output logic [18:0]   mem_read_req_addr_o,
  input  logic          mem_read_rsp_valid_i,
  output logic          mem_read_rsp_ready_o,
  input  logic [511:0]  mem_read_rsp_data_i,
  input  logic          mem_read_rsp_error_i,
  output logic          transfer_done_o,
  output logic [31:0]   protocol_error_count_o
);
  localparam logic [22:0] STAGING_LIMIT = 23'(STAGING_BYTES);
  logic active_q, direction_q, read_pending_q, output_full_q;
  logic [18:0] base_q;
  logic [15:0] beats_q, count_q;
  logic [15:0] tag_q;
  logic [11:0] tensor_q;
  logic [3:0] format_q;
  logic [63:0] last_be_q;
  logic [511:0] output_data_q;
  logic expected_last, input_fire, output_fire;
  logic [22:0] end_addr;

  assign cfg_ready_o = !active_q && !output_full_q && !read_pending_q;
  assign end_addr = {4'b0, cfg_base_addr_i} + {1'b0, cfg_beats_i, 6'b0};
  assign expected_last = count_q == beats_q - 1'b1;

  assign mem_write_valid_o = active_q && !direction_q && stream_in_valid_i;
  assign mem_write_addr_o = base_q + 19'({count_q, 6'b0});
  assign mem_write_data_o = stream_in_data_i;
  assign mem_write_be_o = stream_in_be_i;
  assign stream_in_ready_o = active_q && !direction_q && mem_write_ready_i;
  assign input_fire = stream_in_valid_i && stream_in_ready_o;

  assign mem_read_req_valid_o = active_q && direction_q && !read_pending_q &&
                                !output_full_q && count_q < beats_q;
  assign mem_read_req_addr_o = base_q + 19'({count_q, 6'b0});
  assign mem_read_rsp_ready_o = active_q && direction_q && read_pending_q && !output_full_q;
  assign stream_out_valid_o = output_full_q;
  assign stream_out_data_o = output_data_q;
  assign stream_out_be_o = expected_last ? last_be_q : 64'hffff_ffff_ffff_ffff;
  assign stream_out_tag_o = tag_q;
  assign stream_out_tensor_id_o = tensor_q;
  assign stream_out_last_o = expected_last;
  assign stream_out_format_o = format_q;
  assign output_fire = stream_out_valid_o && stream_out_ready_i;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      active_q <= 0;
      direction_q <= 0;
      read_pending_q <= 0;
      output_full_q <= 0;
      base_q <= 0;
      beats_q <= 0;
      count_q <= 0;
      tag_q <= 0;
      tensor_q <= 0;
      format_q <= 0;
      last_be_q <= 0;
      output_data_q <= 0;
      transfer_done_o <= 0;
      protocol_error_count_o <= 0;
    end else begin
      transfer_done_o <= 0;
      if (cfg_valid_i && cfg_ready_o) begin
        direction_q <= cfg_direction_i;
        base_q <= cfg_base_addr_i;
        beats_q <= cfg_beats_i;
        count_q <= 0;
        tag_q <= cfg_tag_i;
        tensor_q <= cfg_tensor_id_i;
        format_q <= cfg_format_i;
        last_be_q <= cfg_last_be_i;
        read_pending_q <= 0;
        output_full_q <= 0;
        if (cfg_beats_i == 0 || cfg_base_addr_i[5:0] != 0 ||
            end_addr > STAGING_LIMIT) begin
          protocol_error_count_o <= protocol_error_count_o + 1'b1;
          active_q <= 0;
        end else begin
          active_q <= 1;
        end
      end

      if (input_fire) begin
        if (stream_in_last_i != expected_last)
          protocol_error_count_o <= protocol_error_count_o + 1'b1;
        if (stream_in_tag_i != tag_q || stream_in_tensor_id_i != tensor_q ||
            stream_in_format_i != format_q)
          protocol_error_count_o <= protocol_error_count_o + 1'b1;
        count_q <= count_q + 1'b1;
        if (expected_last) begin
          active_q <= 0;
          transfer_done_o <= 1;
        end
      end

      if (mem_read_req_valid_o && mem_read_req_ready_i)
        read_pending_q <= 1;

      if (mem_read_rsp_valid_i && mem_read_rsp_ready_o) begin
        read_pending_q <= 0;
        if (mem_read_rsp_error_i) begin
          protocol_error_count_o <= protocol_error_count_o + 1'b1;
          active_q <= 0;
          transfer_done_o <= 1;
        end else begin
          output_data_q <= mem_read_rsp_data_i;
          output_full_q <= 1;
        end
      end

      if (output_fire) begin
        output_full_q <= 0;
        count_q <= count_q + 1'b1;
        if (expected_last) begin
          active_q <= 0;
          transfer_done_o <= 1;
        end
      end
    end
  end
endmodule

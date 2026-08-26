// SPDX-License-Identifier: Apache-2.0
// Tensor Stream endpoint for the official Garnet proc_packet boundary.
`timescale 1ns/1ps
module aha_tensor_stream_endpoint (
  input  logic          clk_i,
  input  logic          rst_ni,

  input  logic          cfg_valid_i,
  output logic          cfg_ready_o,
  input  logic [17:0]   cfg_input_base_i,
  input  logic [17:0]   cfg_output_base_i,
  input  logic [15:0]   cfg_input_beats_i,
  input  logic [15:0]   cfg_output_beats_i,
  input  logic [15:0]   cfg_output_tag_i,
  input  logic [11:0]   cfg_output_tensor_id_i,
  input  logic [3:0]    cfg_output_format_i,
  input  logic [63:0]   cfg_output_last_be_i,
  input  logic          run_done_i,

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

  output logic          proc_packet_wr_en_o,
  output logic [17:0]   proc_packet_wr_addr_o,
  output logic [63:0]   proc_packet_wr_data_o,
  output logic [7:0]    proc_packet_wr_strb_o,
  output logic          proc_packet_rd_en_o,
  output logic [17:0]   proc_packet_rd_addr_o,
  input  logic [63:0]   proc_packet_rd_data_i,
  input  logic          proc_packet_rd_data_valid_i,
  output logic          native_eos_o,
  output logic          transfer_done_o,
  output logic [31:0]   protocol_error_count_o
);
  logic active_q, input_done_q, run_done_q, final_packet_pending_q;
  logic [17:0] input_base_q, output_base_q;
  logic [15:0] input_beats_q, output_beats_q;
  logic [15:0] output_tag_q;
  logic [11:0] output_tensor_q;
  logic [3:0] output_format_q;
  logic [63:0] output_last_be_q;
  logic [15:0] input_count_q, output_count_q;
  logic input_meta_valid_q;
  logic [15:0] input_tag_q;
  logic [11:0] input_tensor_q;
  logic [3:0] input_format_q;

  logic packet_valid, packet_ready, packet_done;
  logic read_busy_q, read_issue_done_q, output_full_q;
  logic [2:0] read_issue_count_q, read_response_count_q;
  logic [511:0] output_data_q;
  logic input_fire, output_fire;
  logic expected_input_last;

  assign cfg_ready_o = !active_q && packet_ready && !output_full_q;
  assign expected_input_last = input_count_q == input_beats_q - 1'b1;
  assign packet_valid = active_q && !input_done_q && stream_in_valid_i;
  assign stream_in_ready_o = active_q && !input_done_q && packet_ready;
  assign input_fire = stream_in_valid_i && stream_in_ready_o;

  assign stream_out_valid_o = output_full_q;
  assign stream_out_data_o = output_data_q;
  assign stream_out_tag_o = output_tag_q;
  assign stream_out_tensor_id_o = output_tensor_q;
  assign stream_out_format_o = output_format_q;
  assign stream_out_last_o = output_count_q == output_beats_q - 1'b1;
  assign stream_out_be_o = stream_out_last_o ? output_last_be_q : 64'hffff_ffff_ffff_ffff;
  assign output_fire = stream_out_valid_o && stream_out_ready_i;

  assign proc_packet_rd_en_o = read_busy_q && !read_issue_done_q;
  assign proc_packet_rd_addr_o = output_base_q +
    18'({output_count_q, 6'b0}) + 18'({read_issue_count_q, 3'b0});

  aha_garnet_proc_packet_writer u_writer (
    .clk_i, .rst_ni,
    .packet_valid_i(packet_valid), .packet_ready_o(packet_ready),
    .packet_addr_i(input_base_q + 18'({input_count_q, 6'b0})),
    .packet_data_i(stream_in_data_i), .packet_strb_i(stream_in_be_i),
    .proc_packet_wr_en_o, .proc_packet_wr_addr_o,
    .proc_packet_wr_data_o, .proc_packet_wr_strb_o,
    .packet_done_o(packet_done)
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      active_q <= 0;
      input_done_q <= 0;
      run_done_q <= 0;
      final_packet_pending_q <= 0;
      input_base_q <= 0;
      output_base_q <= 0;
      input_beats_q <= 0;
      output_beats_q <= 0;
      output_tag_q <= 0;
      output_tensor_q <= 0;
      output_format_q <= 0;
      output_last_be_q <= 0;
      input_count_q <= 0;
      output_count_q <= 0;
      input_meta_valid_q <= 0;
      input_tag_q <= 0;
      input_tensor_q <= 0;
      input_format_q <= 0;
      read_busy_q <= 0;
      read_issue_done_q <= 0;
      read_issue_count_q <= 0;
      read_response_count_q <= 0;
      output_full_q <= 0;
      output_data_q <= 0;
      native_eos_o <= 0;
      transfer_done_o <= 0;
      protocol_error_count_o <= 0;
    end else begin
      native_eos_o <= 0;
      transfer_done_o <= 0;

      if (cfg_valid_i && cfg_ready_o) begin
        input_base_q <= cfg_input_base_i;
        output_base_q <= cfg_output_base_i;
        input_beats_q <= cfg_input_beats_i;
        output_beats_q <= cfg_output_beats_i;
        output_tag_q <= cfg_output_tag_i;
        output_tensor_q <= cfg_output_tensor_id_i;
        output_format_q <= cfg_output_format_i;
        output_last_be_q <= cfg_output_last_be_i;
        input_count_q <= 0;
        output_count_q <= 0;
        input_done_q <= 0;
        run_done_q <= 0;
        final_packet_pending_q <= 0;
        input_meta_valid_q <= 0;
        read_busy_q <= 0;
        read_issue_done_q <= 0;
        output_full_q <= 0;
        read_issue_count_q <= 0;
        read_response_count_q <= 0;
        if (cfg_input_beats_i == 0 || cfg_output_beats_i == 0 ||
            cfg_input_base_i[5:0] != 0 || cfg_output_base_i[5:0] != 0) begin
          protocol_error_count_o <= protocol_error_count_o + 1'b1;
          active_q <= 0;
        end else begin
          active_q <= 1;
        end
      end

      if (run_done_i)
        run_done_q <= 1;

      if (input_fire) begin
        if (stream_in_last_i != expected_input_last)
          protocol_error_count_o <= protocol_error_count_o + 1'b1;
        if (!input_meta_valid_q) begin
          input_meta_valid_q <= 1;
          input_tag_q <= stream_in_tag_i;
          input_tensor_q <= stream_in_tensor_id_i;
          input_format_q <= stream_in_format_i;
        end else if (stream_in_tag_i != input_tag_q ||
                     stream_in_tensor_id_i != input_tensor_q ||
                     stream_in_format_i != input_format_q) begin
          protocol_error_count_o <= protocol_error_count_o + 1'b1;
        end
        input_count_q <= input_count_q + 1'b1;
        if (expected_input_last)
          final_packet_pending_q <= 1;
      end

      if (packet_done && final_packet_pending_q) begin
        final_packet_pending_q <= 0;
        input_done_q <= 1;
        native_eos_o <= 1;
      end

      if (active_q && input_done_q && run_done_q && !read_busy_q &&
          !output_full_q && output_count_q < output_beats_q) begin
        read_busy_q <= 1;
        read_issue_done_q <= 0;
        read_issue_count_q <= 0;
        read_response_count_q <= 0;
      end else if (read_busy_q && !read_issue_done_q) begin
        if (read_issue_count_q == 3'd7)
          read_issue_done_q <= 1;
        else
          read_issue_count_q <= read_issue_count_q + 1'b1;
      end

      if (proc_packet_rd_data_valid_i) begin
        if (!read_busy_q || output_full_q) begin
          protocol_error_count_o <= protocol_error_count_o + 1'b1;
        end else begin
          output_data_q[read_response_count_q*64 +: 64] <= proc_packet_rd_data_i;
          if (read_response_count_q == 3'd7) begin
            read_busy_q <= 0;
            read_issue_done_q <= 0;
            output_full_q <= 1;
          end else begin
            read_response_count_q <= read_response_count_q + 1'b1;
          end
        end
      end

      if (output_fire) begin
        output_full_q <= 0;
        output_count_q <= output_count_q + 1'b1;
        if (stream_out_last_o) begin
          active_q <= 0;
          transfer_done_o <= 1;
        end
      end
    end
  end
endmodule

// SPDX-License-Identifier: Apache-2.0
// Source-ready integration of K-tail sequencing, block metadata and GGML group decode.
module ggml_quant_frontend_top #(
  parameter int PAYLOAD_BYTES = 210,
  parameter int K_W = 32,
  parameter int BLOCK_W = 32,
  parameter int TAG_W = 32
) (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic start_i,
  input  logic [1:0] format_i,
  input  logic [K_W-1:0] k_values_i,
  input  logic [TAG_W-1:0] job_tag_i,

  output logic block_req_valid_o,
  input  logic block_req_ready_i,
  output logic [BLOCK_W-1:0] block_req_index_o,
  output logic [TAG_W-1:0] block_req_tag_o,

  input  logic block_rsp_valid_i,
  output logic block_rsp_ready_o,
  input  logic [BLOCK_W-1:0] block_rsp_index_i,
  input  logic [TAG_W-1:0] block_rsp_tag_i,
  input  logic [7:0] block_rsp_fp16_elements_i,
  input  logic [PAYLOAD_BYTES*8-1:0] block_rsp_payload_i,

  output logic beat_valid_o,
  input  logic beat_ready_i,
  output logic [1:0] beat_format_o,
  output logic [TAG_W-1:0] beat_tag_o,
  output logic [BLOCK_W-1:0] beat_block_index_o,
  output logic [3:0] beat_group_index_o,
  output logic [4:0] beat_valid_count_o,
  output logic beat_integer_mode_o,
  output logic signed [7:0] beat_quant_o [0:15],
  output logic [15:0] beat_fp16_o [0:15],
  output logic [15:0] beat_block_scale_fp16_o,
  output logic signed [7:0] beat_subscale_s8_o,
  output logic beat_block_first_o,
  output logic beat_block_last_o,
  output logic beat_last_o,
  output logic done_o,
  output logic protocol_error_o
);
  logic seq_busy, seq_valid, seq_ready, seq_done;
  logic [BLOCK_W-1:0] seq_block;
  logic [3:0] seq_group;
  logic [4:0] seq_valid_count;
  logic seq_block_first, seq_block_last, seq_last;

  logic [1:0] format_q;
  logic [TAG_W-1:0] job_tag_q;
  logic [BLOCK_W-1:0] request_index_q;
  logic [BLOCK_W:0] total_blocks_q;
  logic [2:0] outstanding_q;

  logic [PAYLOAD_BYTES*8-1:0] payload_q [0:1];
  logic [7:0] fp16_count_q [0:1];
  logic [BLOCK_W-1:0] payload_block_q [0:1];
  logic [TAG_W-1:0] payload_tag_q [0:1];
  logic payload_wr_q, payload_rd_q;
  logic [1:0] payload_count_q;

  logic [1:0] out_format_q [0:1];
  logic [TAG_W-1:0] out_tag_q [0:1];
  logic [BLOCK_W-1:0] out_block_q [0:1];
  logic [3:0] out_group_q [0:1];
  logic [4:0] out_valid_count_q [0:1];
  logic out_integer_q [0:1];
  logic signed [7:0] out_quant_q [0:1][0:15];
  logic [15:0] out_fp16_q [0:1][0:15];
  logic [15:0] out_scale_q [0:1];
  logic signed [7:0] out_subscale_q [0:1];
  logic out_first_q [0:1], out_block_last_q [0:1], out_last_q [0:1];
  logic out_wr_q, out_rd_q;
  logic [1:0] out_count_q;

  logic dec_valid, dec_integer, dec_last;
  logic [4:0] dec_valid_count;
  logic signed [7:0] dec_quant [0:15];
  logic [15:0] dec_fp16 [0:15];
  logic [15:0] dec_scale;
  logic signed [7:0] dec_subscale;
  logic req_fire, rsp_fire, seq_fire, out_fire;
  logic [8:0] values_per_block;
  integer lane;

  always_comb begin
    unique case (format_i)
      2'd0: values_per_block = 9'd16;
      2'd1: values_per_block = 9'd32;
      default: values_per_block = 9'd256;
    endcase
  end

  ggml_quant_k_tail_sequencer #(.K_W(K_W), .BLOCK_W(BLOCK_W)) sequencer (
    .clk_i, .rst_ni, .start_i,
    .format_i, .k_values_i,
    .busy_o(seq_busy), .beat_valid_o(seq_valid), .beat_ready_i(seq_ready),
    .block_index_o(seq_block), .group_index_o(seq_group), .valid_count_o(seq_valid_count),
    .block_first_o(seq_block_first), .block_last_o(seq_block_last), .last_o(seq_last), .done_o(seq_done)
  );

  ggml_operand_group_decode #(.PAYLOAD_BYTES(PAYLOAD_BYTES)) decoder (
    .format_i(format_q), .group_index_i(seq_group), .fp16_element_count_i(fp16_count_q[payload_rd_q]),
    .block_payload_i(payload_q[payload_rd_q]), .format_valid_o(dec_valid), .integer_mode_o(dec_integer),
    .valid_count_o(dec_valid_count), .quant_o(dec_quant), .fp16_o(dec_fp16),
    .block_scale_fp16_o(dec_scale), .subscale_s8_o(dec_subscale), .last_o(dec_last)
  );

  assign block_req_valid_o = seq_busy && (request_index_q < total_blocks_q) && ((outstanding_q + payload_count_q) < 2);
  assign block_req_index_o = request_index_q;
  assign block_req_tag_o = job_tag_q ^ TAG_W'(request_index_q);
  assign block_rsp_ready_o = payload_count_q < 2;
  assign req_fire = block_req_valid_o && block_req_ready_i;
  assign rsp_fire = block_rsp_valid_i && block_rsp_ready_o;
  assign seq_ready = seq_valid && payload_count_q != 0 && payload_block_q[payload_rd_q] == seq_block && out_count_q < 2;
  assign seq_fire = seq_valid && seq_ready;
  assign beat_valid_o = out_count_q != 0;
  assign out_fire = beat_valid_o && beat_ready_i;

  assign beat_format_o = out_format_q[out_rd_q];
  assign beat_tag_o = out_tag_q[out_rd_q];
  assign beat_block_index_o = out_block_q[out_rd_q];
  assign beat_group_index_o = out_group_q[out_rd_q];
  assign beat_valid_count_o = out_valid_count_q[out_rd_q];
  assign beat_integer_mode_o = out_integer_q[out_rd_q];
  assign beat_block_scale_fp16_o = out_scale_q[out_rd_q];
  assign beat_subscale_s8_o = out_subscale_q[out_rd_q];
  assign beat_block_first_o = out_first_q[out_rd_q];
  assign beat_block_last_o = out_block_last_q[out_rd_q];
  assign beat_last_o = out_last_q[out_rd_q];
  assign done_o = seq_done && out_count_q == 0;
  always_comb for (lane=0; lane<16; lane++) begin
    beat_quant_o[lane] = out_quant_q[out_rd_q][lane];
    beat_fp16_o[lane] = out_fp16_q[out_rd_q][lane];
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      format_q <= '0; job_tag_q <= '0; request_index_q <= '0; total_blocks_q <= '0; outstanding_q <= '0;
      payload_wr_q <= 0; payload_rd_q <= 0; payload_count_q <= 0;
      out_wr_q <= 0; out_rd_q <= 0; out_count_q <= 0; protocol_error_o <= 0;
    end else begin
      if (start_i && !seq_busy) begin
        format_q <= format_i; job_tag_q <= job_tag_i; request_index_q <= '0; outstanding_q <= '0;
        total_blocks_q <= (k_values_i + K_W'(values_per_block) - 1) / K_W'(values_per_block);
        payload_wr_q <= 0; payload_rd_q <= 0; payload_count_q <= 0;
        out_wr_q <= 0; out_rd_q <= 0; out_count_q <= 0; protocol_error_o <= 0;
      end
      if (req_fire) begin request_index_q <= request_index_q + 1'b1; outstanding_q <= outstanding_q + 1'b1; end
      if (rsp_fire) begin
        payload_q[payload_wr_q] <= block_rsp_payload_i;
        fp16_count_q[payload_wr_q] <= block_rsp_fp16_elements_i;
        payload_block_q[payload_wr_q] <= block_rsp_index_i;
        payload_tag_q[payload_wr_q] <= block_rsp_tag_i;
        payload_wr_q <= ~payload_wr_q;
        payload_count_q <= payload_count_q + 1'b1;
        if (outstanding_q != 0) outstanding_q <= outstanding_q - 1'b1; else protocol_error_o <= 1'b1;
        if (block_rsp_tag_i != (job_tag_q ^ TAG_W'(block_rsp_index_i))) protocol_error_o <= 1'b1;
      end
      if (seq_fire) begin
        out_format_q[out_wr_q] <= format_q;
        out_tag_q[out_wr_q] <= payload_tag_q[payload_rd_q];
        out_block_q[out_wr_q] <= seq_block;
        out_group_q[out_wr_q] <= seq_group;
        out_valid_count_q[out_wr_q] <= seq_valid_count;
        out_integer_q[out_wr_q] <= dec_integer;
        out_scale_q[out_wr_q] <= dec_scale;
        out_subscale_q[out_wr_q] <= dec_subscale;
        out_first_q[out_wr_q] <= seq_block_first;
        out_block_last_q[out_wr_q] <= seq_block_last;
        out_last_q[out_wr_q] <= seq_last;
        for (lane=0; lane<16; lane++) begin
          out_quant_q[out_wr_q][lane] <= lane < seq_valid_count ? dec_quant[lane] : '0;
          out_fp16_q[out_wr_q][lane] <= lane < seq_valid_count ? dec_fp16[lane] : '0;
        end
        out_wr_q <= ~out_wr_q;
        if (!out_fire) out_count_q <= out_count_q + 1'b1;
        if (!dec_valid || dec_valid_count < seq_valid_count || dec_last != seq_block_last) protocol_error_o <= 1'b1;
        if (seq_block_last) begin payload_rd_q <= ~payload_rd_q; payload_count_q <= payload_count_q - 1'b1; end
      end
      if (out_fire) begin out_rd_q <= ~out_rd_q; if (!seq_fire) out_count_q <= out_count_q - 1'b1; end
    end
  end

`ifndef SYNTHESIS
  always_ff @(posedge clk_i) begin
    if (rst_ni && beat_valid_o && !beat_ready_i) begin
      assert($stable(beat_tag_o)); assert($stable(beat_block_scale_fp16_o)); assert($stable(beat_subscale_s8_o));
      assert($stable(beat_valid_count_o)); assert($stable(beat_last_o));
    end
    if (rst_ni && seq_fire) begin
      assert(payload_block_q[payload_rd_q] == seq_block) else $fatal(1,"payload/block mismatch");
      assert(payload_tag_q[payload_rd_q] == (job_tag_q ^ TAG_W'(seq_block))) else $fatal(1,"tag mismatch");
      assert(seq_valid_count >= 1 && seq_valid_count <= 16) else $fatal(1,"valid_count");
    end
    if (rst_ni) begin assert(payload_count_q <= 2); assert(out_count_q <= 2); end
  end
`endif
endmodule

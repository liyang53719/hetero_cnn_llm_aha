// SPDX-License-Identifier: Apache-2.0
// Small synthesizable page-table/KV SRAM contract model.
//
// This model intentionally uses fixed arrays and a first-free allocator so it
// can be simulated and synthesized without a software runtime.  The production
// implementation replaces K/V arrays with SRAM macros and adds refcounts,
// prefix sharing, copy-on-write, wide gather streams and an iDMA backend.
module kv_cache_engine #(
  parameter integer MAX_SEQUENCES    = 4,
  parameter integer MAX_LAYERS       = 4,
  parameter integer MAX_LOGICAL_PAGES= 8,
  parameter integer PHYSICAL_PAGES   = 16,
  parameter integer PAGE_TOKENS      = 4,
  parameter integer WORD_W           = 64,
  parameter integer TOKEN_W          = 16,
  localparam integer SEQ_W  = (MAX_SEQUENCES <= 2) ? 1 : $clog2(MAX_SEQUENCES),
  localparam integer LAYER_W= (MAX_LAYERS <= 2) ? 1 : $clog2(MAX_LAYERS),
  localparam integer PAGE_W = (PHYSICAL_PAGES <= 2) ? 1 : $clog2(PHYSICAL_PAGES),
  localparam integer TABLE_ENTRIES = MAX_SEQUENCES*MAX_LAYERS*MAX_LOGICAL_PAGES,
  localparam integer LEN_ENTRIES   = MAX_SEQUENCES*MAX_LAYERS
) (
  input  logic                    clk_i,
  input  logic                    rst_ni,

  input  logic                    cmd_valid_i,
  output logic                    cmd_ready_o,
  input  logic [1:0]              cmd_op_i,       // 0 append, 1 read, 2 free, 3 length
  input  logic [SEQ_W-1:0]        cmd_sequence_i,
  input  logic [LAYER_W-1:0]      cmd_layer_i,
  input  logic [TOKEN_W-1:0]      cmd_token_i,
  input  logic [WORD_W-1:0]       cmd_k_i,
  input  logic [WORD_W-1:0]       cmd_v_i,

  output logic                    rsp_valid_o,
  input  logic                    rsp_ready_i,
  output logic [2:0]              rsp_status_o,   // 0 OK, 1 OOM, 2 OOB, 3 missing
  output logic [TOKEN_W-1:0]      rsp_length_o,
  output logic [WORD_W-1:0]       rsp_k_o,
  output logic [WORD_W-1:0]       rsp_v_o
);
  localparam logic [1:0] OP_APPEND = 2'd0;
  localparam logic [1:0] OP_READ   = 2'd1;
  localparam logic [1:0] OP_FREE   = 2'd2;
  localparam logic [1:0] OP_LENGTH = 2'd3;

  logic [PAGE_W-1:0] block_page_q [0:TABLE_ENTRIES-1];
  logic              block_valid_q[0:TABLE_ENTRIES-1];
  logic [TOKEN_W-1:0] length_q [0:LEN_ENTRIES-1];
  logic page_used_q [0:PHYSICAL_PAGES-1];
  logic [WORD_W-1:0] k_mem_q [0:PHYSICAL_PAGES-1][0:PAGE_TOKENS-1];
  logic [WORD_W-1:0] v_mem_q [0:PHYSICAL_PAGES-1][0:PAGE_TOKENS-1];

  logic free_found;
  logic [PAGE_W-1:0] free_page;
  integer p, t, idx, lp, offset, table_idx, len_idx;

  always_comb begin
    free_found = 1'b0;
    free_page  = '0;
    for (p = 0; p < PHYSICAL_PAGES; p++) begin
      if (!free_found && !page_used_q[p]) begin
        free_found = 1'b1;
        free_page  = p[PAGE_W-1:0];
      end
    end
  end

  assign cmd_ready_o = !rsp_valid_o || rsp_ready_i;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rsp_valid_o  <= 1'b0;
      rsp_status_o <= '0;
      rsp_length_o <= '0;
      rsp_k_o      <= '0;
      rsp_v_o      <= '0;
      for (idx = 0; idx < TABLE_ENTRIES; idx++) begin
        block_page_q[idx]  <= '0;
        block_valid_q[idx] <= 1'b0;
      end
      for (idx = 0; idx < LEN_ENTRIES; idx++) begin
        length_q[idx] <= '0;
      end
      for (p = 0; p < PHYSICAL_PAGES; p++) begin
        page_used_q[p] <= 1'b0;
        for (t = 0; t < PAGE_TOKENS; t++) begin
          k_mem_q[p][t] <= '0;
          v_mem_q[p][t] <= '0;
        end
      end
    end else if (cmd_ready_o) begin
      rsp_valid_o <= cmd_valid_i;
      if (cmd_valid_i) begin
        rsp_status_o <= 3'd0;
        rsp_k_o      <= '0;
        rsp_v_o      <= '0;
        len_idx = cmd_sequence_i * MAX_LAYERS + cmd_layer_i;
        rsp_length_o <= length_q[len_idx];

        unique case (cmd_op_i)
          OP_APPEND: begin
            lp     = length_q[len_idx] / PAGE_TOKENS;
            offset = length_q[len_idx] % PAGE_TOKENS;
            if (lp >= MAX_LOGICAL_PAGES) begin
              rsp_status_o <= 3'd2;
            end else begin
              table_idx = len_idx * MAX_LOGICAL_PAGES + lp;
              if (!block_valid_q[table_idx]) begin
                if (!free_found) begin
                  rsp_status_o <= 3'd1;
                end else begin
                  block_valid_q[table_idx] <= 1'b1;
                  block_page_q[table_idx]  <= free_page;
                  page_used_q[free_page]   <= 1'b1;
                  k_mem_q[free_page][offset] <= cmd_k_i;
                  v_mem_q[free_page][offset] <= cmd_v_i;
                  length_q[len_idx] <= length_q[len_idx] + 1'b1;
                  rsp_length_o <= length_q[len_idx] + 1'b1;
                end
              end else begin
                k_mem_q[block_page_q[table_idx]][offset] <= cmd_k_i;
                v_mem_q[block_page_q[table_idx]][offset] <= cmd_v_i;
                length_q[len_idx] <= length_q[len_idx] + 1'b1;
                rsp_length_o <= length_q[len_idx] + 1'b1;
              end
            end
          end

          OP_READ: begin
            if (cmd_token_i >= length_q[len_idx]) begin
              rsp_status_o <= 3'd2;
            end else begin
              lp        = cmd_token_i / PAGE_TOKENS;
              offset    = cmd_token_i % PAGE_TOKENS;
              table_idx = len_idx * MAX_LOGICAL_PAGES + lp;
              if (!block_valid_q[table_idx]) begin
                rsp_status_o <= 3'd3;
              end else begin
                rsp_k_o <= k_mem_q[block_page_q[table_idx]][offset];
                rsp_v_o <= v_mem_q[block_page_q[table_idx]][offset];
              end
            end
          end

          OP_FREE: begin
            for (lp = 0; lp < MAX_LOGICAL_PAGES; lp++) begin
              table_idx = len_idx * MAX_LOGICAL_PAGES + lp;
              if (block_valid_q[table_idx]) begin
                page_used_q[block_page_q[table_idx]] <= 1'b0;
                block_valid_q[table_idx] <= 1'b0;
              end
            end
            length_q[len_idx] <= '0;
            rsp_length_o <= '0;
          end

          OP_LENGTH: begin
            rsp_length_o <= length_q[len_idx];
          end

          default: rsp_status_o <= 3'd2;
        endcase
      end
    end
  end
endmodule

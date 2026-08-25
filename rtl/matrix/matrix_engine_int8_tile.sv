// SPDX-License-Identifier: Apache-2.0
// Clean-room, synthesizable contract model for a small INT8 matrix tile.
//
// One accepted operand beat supplies A[0:M-1,k] and B[k,0:N-1].  The tile
// performs M*N signed MACs per accepted beat.  After K beats it emits C in
// row-major order.  This is not Gemmini source code; it is a local interface
// and verification target used before integrating generated Gemmini RTL.
module matrix_engine_int8_tile #(
  parameter integer MAX_M  = 4,
  parameter integer MAX_N  = 4,
  parameter integer DATA_W = 8,
  parameter integer ACC_W  = 32,
  parameter integer K_W    = 16,
  localparam integer M_W   = (MAX_M <= 2) ? 1 : $clog2(MAX_M),
  localparam integer N_W   = (MAX_N <= 2) ? 1 : $clog2(MAX_N)
) (
  input  logic                         clk_i,
  input  logic                         rst_ni,

  input  logic                         start_i,
  output logic                         start_ready_o,
  input  logic [M_W:0]                 cfg_m_i,
  input  logic [N_W:0]                 cfg_n_i,
  input  logic [K_W-1:0]               cfg_k_i,

  input  logic                         a_valid_i,
  output logic                         a_ready_o,
  input  logic [MAX_M*DATA_W-1:0]      a_data_i,
  input  logic                         b_valid_i,
  output logic                         b_ready_o,
  input  logic [MAX_N*DATA_W-1:0]      b_data_i,

  output logic                         c_valid_o,
  input  logic                         c_ready_i,
  output logic [M_W-1:0]               c_row_o,
  output logic [N_W-1:0]               c_col_o,
  output logic signed [ACC_W-1:0]      c_data_o,
  output logic                         done_o,
  output logic                         busy_o
);
  typedef enum logic [1:0] {S_IDLE, S_MAC, S_OUT} state_e;
  state_e state_q;

  logic [M_W:0] cfg_m_q;
  logic [N_W:0] cfg_n_q;
  logic [K_W-1:0] cfg_k_q;
  logic [K_W-1:0] k_count_q;
  logic [M_W-1:0] out_row_q;
  logic [N_W-1:0] out_col_q;
  logic signed [ACC_W-1:0] acc_q [0:MAX_M-1][0:MAX_N-1];

  logic operand_fire;
  assign start_ready_o = (state_q == S_IDLE);
  assign busy_o        = (state_q != S_IDLE);
  assign a_ready_o     = (state_q == S_MAC) && b_valid_i;
  assign b_ready_o     = (state_q == S_MAC) && a_valid_i;
  assign operand_fire  = a_valid_i && a_ready_o && b_valid_i && b_ready_o;

  assign c_valid_o = (state_q == S_OUT);
  assign c_row_o   = out_row_q;
  assign c_col_o   = out_col_q;
  assign c_data_o  = acc_q[out_row_q][out_col_q];

  integer mi, ni;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q   <= S_IDLE;
      cfg_m_q   <= '0;
      cfg_n_q   <= '0;
      cfg_k_q   <= '0;
      k_count_q <= '0;
      out_row_q <= '0;
      out_col_q <= '0;
      done_o    <= 1'b0;
      for (mi = 0; mi < MAX_M; mi++) begin
        for (ni = 0; ni < MAX_N; ni++) begin
          acc_q[mi][ni] <= '0;
        end
      end
    end else begin
      done_o <= 1'b0;
      unique case (state_q)
        S_IDLE: begin
          if (start_i && start_ready_o) begin
            cfg_m_q   <= cfg_m_i;
            cfg_n_q   <= cfg_n_i;
            cfg_k_q   <= cfg_k_i;
            k_count_q <= '0;
            out_row_q <= '0;
            out_col_q <= '0;
            for (mi = 0; mi < MAX_M; mi++) begin
              for (ni = 0; ni < MAX_N; ni++) begin
                acc_q[mi][ni] <= '0;
              end
            end
            state_q <= S_MAC;
          end
        end

        S_MAC: begin
          if (operand_fire) begin
            for (mi = 0; mi < MAX_M; mi++) begin
              for (ni = 0; ni < MAX_N; ni++) begin
                if ((mi < cfg_m_q) && (ni < cfg_n_q)) begin
                  acc_q[mi][ni] <= acc_q[mi][ni]
                    + $signed(a_data_i[mi*DATA_W +: DATA_W])
                    * $signed(b_data_i[ni*DATA_W +: DATA_W]);
                end
              end
            end
            if (k_count_q + 1'b1 >= cfg_k_q) begin
              out_row_q <= '0;
              out_col_q <= '0;
              state_q   <= S_OUT;
            end else begin
              k_count_q <= k_count_q + 1'b1;
            end
          end
        end

        S_OUT: begin
          if (c_valid_o && c_ready_i) begin
            if (out_col_q + 1'b1 >= cfg_n_q) begin
              out_col_q <= '0;
              if (out_row_q + 1'b1 >= cfg_m_q) begin
                state_q <= S_IDLE;
                done_o  <= 1'b1;
              end else begin
                out_row_q <= out_row_q + 1'b1;
              end
            end else begin
              out_col_q <= out_col_q + 1'b1;
            end
          end
        end

        default: state_q <= S_IDLE;
      endcase
    end
  end

`ifndef SYNTHESIS
  always_ff @(posedge clk_i) begin
    if (rst_ni && start_i && start_ready_o) begin
      assert (cfg_m_i > 0 && cfg_m_i <= MAX_M);
      assert (cfg_n_i > 0 && cfg_n_i <= MAX_N);
      assert (cfg_k_i > 0);
    end
  end
`endif
endmodule

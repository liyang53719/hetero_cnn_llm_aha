// SPDX-License-Identifier: Apache-2.0
// Project-side AXI-Lite write sequencer for the generated Garnet top.  Its
// AW -> W -> B ordering follows the pinned AHA test_app axil_driver.sv flow.
// Bitstream storage and proc-packet transfer remain outside this primitive.
module aha_garnet_axi_config_loader (
  input  logic        clk_i,
  input  logic        rst_ni,

  input  logic        cfg_valid_i,
  output logic        cfg_ready_o,
  input  logic [12:0] cfg_addr_i,
  input  logic [31:0] cfg_data_i,

  output logic [12:0] axi_awaddr_o,
  output logic        axi_awvalid_o,
  input  logic        axi_awready_i,
  output logic [31:0] axi_wdata_o,
  output logic        axi_wvalid_o,
  input  logic        axi_wready_i,
  output logic        axi_bready_o,
  input  logic        axi_bvalid_i,
  input  logic [1:0]  axi_bresp_i,

  output logic        write_done_o,
  output logic        write_error_o
);
  // The generated Garnet AXI controller is legal AXI-Lite, but its pinned
  // test_app driver deliberately leaves an idle clock after AW and two clocks
  // after B. Retain those phases so wrapper-side control traffic is cycle
  // compatible with the official application flow, rather than merely
  // handshake compatible.
  typedef enum logic [2:0] {S_IDLE, S_AW, S_AW_TO_W_GAP, S_W, S_B,
                            S_POST_B_1, S_POST_B_2} state_e;
  state_e state_q;
  logic [12:0] addr_q;
  logic [31:0] data_q;
  logic response_error_q;

  assign cfg_ready_o   = (state_q == S_IDLE);
  assign axi_awaddr_o  = addr_q;
  assign axi_wdata_o   = data_q;
  assign axi_awvalid_o = (state_q == S_AW);
  assign axi_wvalid_o  = (state_q == S_W);
  assign axi_bready_o  = (state_q == S_B);

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q       <= S_IDLE;
      addr_q        <= '0;
      data_q        <= '0;
      response_error_q <= 1'b0;
      write_done_o  <= 1'b0;
      write_error_o <= 1'b0;
    end else begin
      write_done_o  <= 1'b0;
      write_error_o <= 1'b0;
      unique case (state_q)
        S_IDLE: if (cfg_valid_i && cfg_ready_o) begin
          addr_q  <= cfg_addr_i;
          data_q  <= cfg_data_i;
          response_error_q <= 1'b0;
          state_q <= S_AW;
        end
        S_AW: if (axi_awvalid_o && axi_awready_i)
          state_q <= S_AW_TO_W_GAP;
        S_AW_TO_W_GAP: state_q <= S_W;
        S_W: if (axi_wvalid_o && axi_wready_i)
          state_q <= S_B;
        S_B: if (axi_bvalid_i && axi_bready_o) begin
          response_error_q <= (axi_bresp_i != 2'b00);
          state_q       <= S_POST_B_1;
        end
        S_POST_B_1: state_q <= S_POST_B_2;
        S_POST_B_2: begin
          write_done_o <= 1'b1;
          write_error_o <= response_error_q;
          state_q <= S_IDLE;
        end
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule

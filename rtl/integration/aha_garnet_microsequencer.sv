// SPDX-License-Identifier: Apache-2.0
// Ordered control-plane sequencer for the official Garnet top. The upstream
// descriptor/metadata lowerer supplies already-resolved micro-operations.
module aha_garnet_microsequencer (
  input  logic          clk_i,
  input  logic          rst_ni,

  input  logic          op_valid_i,
  output logic          op_ready_o,
  input  logic [1:0]    op_kind_i,
  input  logic [12:0]   op_axi_addr_i,
  input  logic [31:0]   op_axi_data_i,
  input  logic [17:0]   op_packet_addr_i,
  input  logic [511:0]  op_packet_data_i,
  input  logic [63:0]   op_packet_strb_i,
  input  logic          garnet_interrupt_i,

  output logic [12:0]   axi_awaddr_o,
  output logic          axi_awvalid_o,
  input  logic          axi_awready_i,
  output logic [31:0]   axi_wdata_o,
  output logic          axi_wvalid_o,
  input  logic          axi_wready_i,
  output logic          axi_bready_o,
  input  logic          axi_bvalid_i,
  input  logic [1:0]    axi_bresp_i,

  output logic          proc_packet_wr_en_o,
  output logic [17:0]   proc_packet_wr_addr_o,
  output logic [63:0]   proc_packet_wr_data_o,
  output logic [7:0]    proc_packet_wr_strb_o,

  output logic          op_done_o,
  output logic          op_error_o
);
  localparam logic [1:0] OP_PACKET = 2'd0;
  localparam logic [1:0] OP_AXI    = 2'd1;
  localparam logic [1:0] OP_WAIT_INTERRUPT = 2'd2;

  typedef enum logic [2:0] {
    S_IDLE, S_PACKET_REQ, S_PACKET_WAIT, S_AXI_REQ, S_AXI_WAIT, S_WAIT_INTERRUPT
  } state_e;
  state_e state_q;
  logic [1:0] kind_q;
  logic [12:0] axi_addr_q;
  logic [31:0] axi_data_q;
  logic [17:0] packet_addr_q;
  logic [511:0] packet_data_q;
  logic [63:0] packet_strb_q;
  logic axi_cfg_valid, axi_cfg_ready, axi_done, axi_error;
  logic packet_valid, packet_ready, packet_done;

  aha_garnet_axi_config_loader u_axi_loader (
    .clk_i, .rst_ni,
    .cfg_valid_i(axi_cfg_valid), .cfg_ready_o(axi_cfg_ready),
    .cfg_addr_i(axi_addr_q), .cfg_data_i(axi_data_q),
    .axi_awaddr_o, .axi_awvalid_o, .axi_awready_i,
    .axi_wdata_o, .axi_wvalid_o, .axi_wready_i,
    .axi_bready_o, .axi_bvalid_i, .axi_bresp_i,
    .write_done_o(axi_done), .write_error_o(axi_error)
  );

  aha_garnet_proc_packet_writer u_packet_writer (
    .clk_i, .rst_ni,
    .packet_valid_i(packet_valid), .packet_ready_o(packet_ready),
    .packet_addr_i(packet_addr_q), .packet_data_i(packet_data_q), .packet_strb_i(packet_strb_q),
    .proc_packet_wr_en_o, .proc_packet_wr_addr_o, .proc_packet_wr_data_o, .proc_packet_wr_strb_o,
    .packet_done_o(packet_done)
  );

  assign op_ready_o = (state_q == S_IDLE);
  assign axi_cfg_valid = (state_q == S_AXI_REQ);
  assign packet_valid = (state_q == S_PACKET_REQ);

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      kind_q <= '0;
      axi_addr_q <= '0;
      axi_data_q <= '0;
      packet_addr_q <= '0;
      packet_data_q <= '0;
      packet_strb_q <= '0;
      op_done_o <= 1'b0;
      op_error_o <= 1'b0;
    end else begin
      op_done_o <= 1'b0;
      op_error_o <= 1'b0;
      unique case (state_q)
        S_IDLE: if (op_valid_i && op_ready_o) begin
          kind_q <= op_kind_i;
          axi_addr_q <= op_axi_addr_i;
          axi_data_q <= op_axi_data_i;
          packet_addr_q <= op_packet_addr_i;
          packet_data_q <= op_packet_data_i;
          packet_strb_q <= op_packet_strb_i;
          unique case (op_kind_i)
            OP_PACKET: state_q <= S_PACKET_REQ;
            OP_AXI: state_q <= S_AXI_REQ;
            OP_WAIT_INTERRUPT: state_q <= S_WAIT_INTERRUPT;
            default: begin
              op_done_o <= 1'b1;
              op_error_o <= 1'b1;
              state_q <= S_IDLE;
            end
          endcase
        end
        S_PACKET_REQ: if (packet_valid && packet_ready)
          state_q <= S_PACKET_WAIT;
        S_PACKET_WAIT: if (packet_done) begin
          op_done_o <= 1'b1;
          state_q <= S_IDLE;
        end
        S_AXI_REQ: if (axi_cfg_valid && axi_cfg_ready)
          state_q <= S_AXI_WAIT;
        S_AXI_WAIT: if (axi_done) begin
          op_done_o <= 1'b1;
          op_error_o <= axi_error;
          state_q <= S_IDLE;
        end
        S_WAIT_INTERRUPT: if (garnet_interrupt_i) begin
          op_done_o <= 1'b1;
          state_q <= S_IDLE;
        end
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule

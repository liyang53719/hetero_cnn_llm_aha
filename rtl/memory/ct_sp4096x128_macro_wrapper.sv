// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module ct_sp4096x128_macro_wrapper (
  input logic clk_i, input logic rst_ni,
  input logic req_valid_i, output logic req_ready_o,
  input logic req_write_i, input logic [12:0] req_addr_i,
  input logic [127:0] req_wdata_i, input logic [15:0] req_wstrb_i,
  output logic rsp_valid_o, input logic rsp_ready_i,
  output logic rsp_error_o, output logic [127:0] rsp_rdata_o
);
  localparam logic [12:0] WORDS=13'd4096;
  typedef enum logic [2:0] {S_IDLE,S_ACCESS,S_CAPTURE,S_RESP} state_e;
  state_e state_q;
  logic write_q,error_q,macro_cen_n;
  logic [12:0] addr_q;
  logic [127:0] wdata_q,rdata_q,macro_q,macro_wen_n;
  logic [15:0] wstrb_q;
  integer byte_index;

  assign req_ready_o=state_q==S_IDLE;
  assign rsp_valid_o=state_q==S_RESP;
  assign rsp_error_o=error_q;
  assign rsp_rdata_o=rdata_q;
  assign macro_cen_n=state_q==S_ACCESS?1'b0:1'b1;
  always_comb begin
    macro_wen_n='1;
    for(byte_index=0;byte_index<16;byte_index++)
      macro_wen_n[byte_index*8 +: 8]={8{~wstrb_q[byte_index]}};
  end

  ctsp4096x128wm u_macro (
    .q(macro_q),.clk(clk_i),.cen(macro_cen_n),.gwen(write_q?1'b0:1'b1),
    .a(addr_q[11:0]),.d(wdata_q),.wen(macro_wen_n),.stov(1'b0),
    .ema(3'b100),.emaw(2'b00),.emas(1'b0),.ret1n(1'b1),
    .rawl(1'b1),.rawlm(2'b01),.wabl(1'b1),.wablm(2'b00));

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      state_q<=S_IDLE;write_q<=0;error_q<=0;addr_q<='0;
      wdata_q<='0;wstrb_q<='0;rdata_q<='0;
    end else begin
      case(state_q)
        S_IDLE: if(req_valid_i&&req_ready_o) begin
          write_q<=req_write_i;error_q<=req_addr_i>=WORDS;addr_q<=req_addr_i;
          wdata_q<=req_wdata_i;wstrb_q<=req_wstrb_i;rdata_q<='0;
          state_q<=req_addr_i>=WORDS?S_RESP:S_ACCESS;
        end
        S_ACCESS: state_q<=write_q?S_RESP:S_CAPTURE;
        S_CAPTURE: begin rdata_q<=macro_q;state_q<=S_RESP;end
        S_RESP: if(rsp_valid_o&&rsp_ready_i) state_q<=S_IDLE;
        default: state_q<=S_IDLE;
      endcase
    end
  end
endmodule

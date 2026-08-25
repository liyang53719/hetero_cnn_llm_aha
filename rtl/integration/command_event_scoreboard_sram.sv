// SPDX-License-Identifier: Apache-2.0
// Full 16-bit persistent event scoreboard backed by one 4096x128 Control SRAM.
`timescale 1ns/1ps
module command_event_scoreboard_sram (
  input logic clk_i,input logic rst_ni,
  input logic host_cmd_valid_i,output logic host_cmd_ready_o,input logic[127:0] host_cmd_data_i,
  output logic runnable_cmd_valid_o,input logic runnable_cmd_ready_i,output logic[127:0] runnable_cmd_data_o,
  input logic completion_valid_i,output logic completion_ready_o,input logic[55:0] completion_data_i,
  output logic init_done_o,output logic[31:0] macro_error_count_o
);
  typedef enum logic[3:0] {S_INIT_REQ,S_INIT_WAIT,S_IDLE,S_READ_REQ,S_READ_WAIT,
    S_WAIT_EVENT,S_WRITE_REQ,S_WRITE_WAIT,S_RELEASE} state_e;
  state_e state_q;
  logic[11:0] init_row_q;
  logic[127:0] command_q;
  logic[15:0] wait_id_q,event_id_q;
  logic event_matches_q,waiting_q;
  logic macro_req_valid,macro_req_ready,macro_req_write;
  logic[12:0] macro_req_addr;
  logic[127:0] macro_req_wdata,macro_rsp_rdata;
  logic[15:0] macro_req_wstrb;
  logic macro_rsp_valid,macro_rsp_ready,macro_rsp_error;
  logic[3:0] event_byte;
  logic[11:0] event_row;
  logic[7:0] completion_status;
  assign completion_status=completion_data_i[39:32];
  assign event_byte=event_id_q[3:0];assign event_row=event_id_q[15:4];

  ct_sp4096x128_macro_wrapper u_event_mem(
    .clk_i(clk_i),.rst_ni(rst_ni),.req_valid_i(macro_req_valid),.req_ready_o(macro_req_ready),
    .req_write_i(macro_req_write),.req_addr_i(macro_req_addr),.req_wdata_i(macro_req_wdata),
    .req_wstrb_i(macro_req_wstrb),.rsp_valid_o(macro_rsp_valid),.rsp_ready_i(macro_rsp_ready),
    .rsp_error_o(macro_rsp_error),.rsp_rdata_o(macro_rsp_rdata));

  always_comb begin
    host_cmd_ready_o=0;runnable_cmd_valid_o=0;runnable_cmd_data_o=command_q;
    completion_ready_o=0;init_done_o=state_q!=S_INIT_REQ&&state_q!=S_INIT_WAIT;
    macro_req_valid=0;macro_req_write=0;macro_req_addr='0;macro_req_wdata='0;
    macro_req_wstrb='0;macro_rsp_ready=0;
    case(state_q)
      S_INIT_REQ: begin
        macro_req_valid=1;macro_req_write=1;macro_req_addr={1'b0,init_row_q};
        macro_req_wstrb=16'hffff;
      end
      S_INIT_WAIT: macro_rsp_ready=1;
      S_IDLE: begin
        if(completion_valid_i) completion_ready_o=1;
        else if(host_cmd_valid_i)begin
          if(host_cmd_data_i[39:24]==0)begin
            host_cmd_ready_o=runnable_cmd_ready_i;runnable_cmd_valid_o=1;
            runnable_cmd_data_o=host_cmd_data_i;
          end
        end
      end
      S_READ_REQ: begin macro_req_valid=1;macro_req_addr={1'b0,wait_id_q[15:4]};end
      S_READ_WAIT: macro_rsp_ready=1;
      S_WAIT_EVENT: completion_ready_o=1;
      S_WRITE_REQ: begin
        macro_req_valid=1;macro_req_write=1;macro_req_addr={1'b0,event_row};
        macro_req_wdata[event_byte*8 +: 8]=8'h1;macro_req_wstrb[event_byte]=1;
      end
      S_WRITE_WAIT: macro_rsp_ready=1;
      S_RELEASE: begin
        host_cmd_ready_o=runnable_cmd_ready_i;runnable_cmd_valid_o=host_cmd_valid_i;
        runnable_cmd_data_o=command_q;
      end
      default: begin end
    endcase
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni)begin
      state_q<=S_INIT_REQ;init_row_q<=0;command_q<='0;wait_id_q<=0;event_id_q<=0;
      event_matches_q<=0;waiting_q<=0;macro_error_count_o<=0;
    end else begin
      case(state_q)
        S_INIT_REQ: if(macro_req_valid&&macro_req_ready)state_q<=S_INIT_WAIT;
        S_INIT_WAIT: if(macro_rsp_valid&&macro_rsp_ready)begin
          if(macro_rsp_error)macro_error_count_o<=macro_error_count_o+1;
          if(init_row_q==12'd4095)state_q<=S_IDLE;
          else begin init_row_q<=init_row_q+1'b1;state_q<=S_INIT_REQ;end
        end
        S_IDLE: begin
          if(completion_valid_i&&completion_ready_o)begin
            if(completion_status==0)begin
              event_id_q<=completion_data_i[55:40];event_matches_q<=0;state_q<=S_WRITE_REQ;
            end
          end else if(host_cmd_valid_i&&host_cmd_data_i[39:24]!=0)begin
            command_q<=host_cmd_data_i;wait_id_q<=host_cmd_data_i[39:24];waiting_q<=1;state_q<=S_READ_REQ;
          end
        end
        S_READ_REQ: if(macro_req_valid&&macro_req_ready)state_q<=S_READ_WAIT;
        S_READ_WAIT: if(macro_rsp_valid&&macro_rsp_ready)begin
          if(macro_rsp_error)begin macro_error_count_o<=macro_error_count_o+1;state_q<=S_WAIT_EVENT;end
          else if(macro_rsp_rdata[wait_id_q[3:0]*8 +: 8]!=0)state_q<=S_RELEASE;
          else state_q<=S_WAIT_EVENT;
        end
        S_WAIT_EVENT: if(completion_valid_i&&completion_ready_o)begin
          if(completion_status==0)begin
            event_id_q<=completion_data_i[55:40];
            event_matches_q<=completion_data_i[55:40]==wait_id_q;state_q<=S_WRITE_REQ;
          end
        end
        S_WRITE_REQ: if(macro_req_valid&&macro_req_ready)state_q<=S_WRITE_WAIT;
        S_WRITE_WAIT: if(macro_rsp_valid&&macro_rsp_ready)begin
          if(macro_rsp_error)macro_error_count_o<=macro_error_count_o+1;
          if(waiting_q)state_q<=event_matches_q?S_RELEASE:S_WAIT_EVENT;
          else state_q<=S_IDLE;
        end
        S_RELEASE: if(host_cmd_valid_i&&host_cmd_ready_o)begin waiting_q<=0;state_q<=S_IDLE;end
        default: state_q<=S_INIT_REQ;
      endcase
    end
  end
endmodule

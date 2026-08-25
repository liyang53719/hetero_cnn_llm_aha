// SPDX-License-Identifier: Apache-2.0
// Production Shared-L2 frontend backed by 4 groups x 4 ARM 6144x128 SP macros.
`timescale 1ns/1ps
module shared_l2_macro_fabric #(
  parameter integer DATA_W=512,
  parameter integer ADDR_W=15
) (
  input logic clk_i,input logic rst_ni,
  input logic[1:0] rd_valid_i,output logic[1:0] rd_ready_o,
  input logic[2*ADDR_W-1:0] rd_addr_i,
  output logic[1:0] rd_resp_valid_o,input logic[1:0] rd_resp_ready_i,
  output logic[2*DATA_W-1:0] rd_data_o,
  input logic wr_valid_i,output logic wr_ready_o,input logic[ADDR_W-1:0] wr_addr_i,
  input logic[DATA_W-1:0] wr_data_i,input logic[DATA_W/8-1:0] wr_be_i,
  output logic[63:0] cycle_count_o,output logic[63:0] read_count_o,
  output logic[63:0] write_count_o,output logic[63:0] bank_conflict_count_o,
  output logic[63:0] read_stall_count_o,output logic[63:0] write_stall_count_o,
  output logic[63:0] macro_error_count_o
);
  localparam integer GROUPS=4,GROUP_W=2,ROW_W=ADDR_W-GROUP_W;
  localparam logic[1:0] TAG_RD0=0,TAG_RD1=1,TAG_WR=2;
  logic[GROUPS-1:0] group_req_valid,group_req_ready,group_req_write;
  logic[GROUPS*13-1:0] group_req_row;
  logic[GROUPS*512-1:0] group_req_wdata,group_rsp_rdata;
  logic[GROUPS*64-1:0] group_req_wstrb;
  logic[GROUPS-1:0] group_rsp_valid,group_rsp_ready,group_rsp_error;
  logic[1:0] group_tag_q[0:GROUPS-1],rr_q[0:GROUPS-1];
  logic[1:0] rd_resp_valid_q,rd_outstanding_q;
  logic[2*DATA_W-1:0] rd_data_q;
  logic eligible0,eligible1;
  logic[GROUP_W-1:0] rd_group0,rd_group1,wr_group;
  logic[ROW_W-1:0] rd_row0,rd_row1,wr_row;
  logic[1:0] selected_tag[0:GROUPS-1];
  logic[GROUPS-1:0] selected_valid;
  logic[2:0] macro_error_fires;
  integer comb_g,seq_g,reset_g;

  assign rd_group0=rd_addr_i[0 +: GROUP_W];
  assign rd_group1=rd_addr_i[ADDR_W +: GROUP_W];
  assign wr_group=wr_addr_i[0 +: GROUP_W];
  assign rd_row0=rd_addr_i[GROUP_W +: ROW_W];
  assign rd_row1=rd_addr_i[ADDR_W+GROUP_W +: ROW_W];
  assign wr_row=wr_addr_i[GROUP_W +: ROW_W];
  assign eligible0=rd_valid_i[0]&&!rd_outstanding_q[0]&&
                   (!rd_resp_valid_q[0]||rd_resp_ready_i[0]);
  assign eligible1=rd_valid_i[1]&&!rd_outstanding_q[1]&&
                   (!rd_resp_valid_q[1]||rd_resp_ready_i[1]);
  assign rd_resp_valid_o=rd_resp_valid_q;
  assign rd_data_o=rd_data_q;

  always_comb begin
    selected_valid='0;rd_ready_o='0;wr_ready_o=0;
    group_req_valid='0;group_req_write='0;group_req_row='0;
    group_req_wdata='0;group_req_wstrb='0;
    for(comb_g=0;comb_g<GROUPS;comb_g++) begin
      selected_tag[comb_g]=TAG_RD0;
      case(rr_q[comb_g])
        TAG_RD0: begin
          if(eligible0&&rd_group0==comb_g[1:0])begin selected_valid[comb_g]=1;selected_tag[comb_g]=TAG_RD0;end
          else if(eligible1&&rd_group1==comb_g[1:0])begin selected_valid[comb_g]=1;selected_tag[comb_g]=TAG_RD1;end
          else if(wr_valid_i&&wr_group==comb_g[1:0])begin selected_valid[comb_g]=1;selected_tag[comb_g]=TAG_WR;end
        end
        TAG_RD1: begin
          if(eligible1&&rd_group1==comb_g[1:0])begin selected_valid[comb_g]=1;selected_tag[comb_g]=TAG_RD1;end
          else if(wr_valid_i&&wr_group==comb_g[1:0])begin selected_valid[comb_g]=1;selected_tag[comb_g]=TAG_WR;end
          else if(eligible0&&rd_group0==comb_g[1:0])begin selected_valid[comb_g]=1;selected_tag[comb_g]=TAG_RD0;end
        end
        default: begin
          if(wr_valid_i&&wr_group==comb_g[1:0])begin selected_valid[comb_g]=1;selected_tag[comb_g]=TAG_WR;end
          else if(eligible0&&rd_group0==comb_g[1:0])begin selected_valid[comb_g]=1;selected_tag[comb_g]=TAG_RD0;end
          else if(eligible1&&rd_group1==comb_g[1:0])begin selected_valid[comb_g]=1;selected_tag[comb_g]=TAG_RD1;end
        end
      endcase
      // Bank-group ready depends only on registered state. Gating valid avoids
      // presenting a changing payload while a group is busy.
      group_req_valid[comb_g]=selected_valid[comb_g]&&group_req_ready[comb_g];
      case(selected_tag[comb_g])
        TAG_RD0: begin
          group_req_row[comb_g*13 +: 13]={{(13-ROW_W){1'b0}},rd_row0};
          rd_ready_o[0]=rd_ready_o[0]||(selected_valid[comb_g]&&group_req_ready[comb_g]);
        end
        TAG_RD1: begin
          group_req_row[comb_g*13 +: 13]={{(13-ROW_W){1'b0}},rd_row1};
          rd_ready_o[1]=rd_ready_o[1]||(selected_valid[comb_g]&&group_req_ready[comb_g]);
        end
        default: begin
          group_req_write[comb_g]=1;
          group_req_row[comb_g*13 +: 13]={{(13-ROW_W){1'b0}},wr_row};
          group_req_wdata[comb_g*512 +: 512]=wr_data_i;
          group_req_wstrb[comb_g*64 +: 64]=wr_be_i;
          wr_ready_o=wr_ready_o||(selected_valid[comb_g]&&group_req_ready[comb_g]);
        end
      endcase
    end
    group_rsp_ready='0;
    macro_error_fires='0;
    for(comb_g=0;comb_g<GROUPS;comb_g++) begin
      case(group_tag_q[comb_g])
        TAG_RD0: group_rsp_ready[comb_g]=!rd_resp_valid_q[0]||rd_resp_ready_i[0];
        TAG_RD1: group_rsp_ready[comb_g]=!rd_resp_valid_q[1]||rd_resp_ready_i[1];
        default: group_rsp_ready[comb_g]=1;
      endcase
      macro_error_fires=macro_error_fires+(group_rsp_valid[comb_g]&&group_rsp_ready[comb_g]&&group_rsp_error[comb_g]);
    end
  end

  genvar group;
  generate for(group=0;group<GROUPS;group++) begin:g_group
    l2_512b_macro_bank_group u_group(
      .clk_i(clk_i),.rst_ni(rst_ni),.req_valid_i(group_req_valid[group]),
      .req_ready_o(group_req_ready[group]),.req_write_i(group_req_write[group]),
      .req_row_i(group_req_row[group*13 +: 13]),
      .req_wdata_i(group_req_wdata[group*512 +: 512]),
      .req_wstrb_i(group_req_wstrb[group*64 +: 64]),
      .rsp_valid_o(group_rsp_valid[group]),.rsp_ready_i(group_rsp_ready[group]),
      .rsp_error_o(group_rsp_error[group]),
      .rsp_rdata_o(group_rsp_rdata[group*512 +: 512]));
  end endgenerate

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      rd_resp_valid_q<='0;rd_outstanding_q<='0;rd_data_q<='0;
      cycle_count_o<='0;read_count_o<='0;write_count_o<='0;
      bank_conflict_count_o<='0;read_stall_count_o<='0;write_stall_count_o<='0;
      macro_error_count_o<='0;
      for(reset_g=0;reset_g<GROUPS;reset_g++)begin rr_q[reset_g]<=TAG_RD0;group_tag_q[reset_g]<=TAG_WR;end
    end else begin
      cycle_count_o<=cycle_count_o+1;
      read_count_o<=read_count_o+(rd_valid_i[0]&&rd_ready_o[0])+(rd_valid_i[1]&&rd_ready_o[1]);
      write_count_o<=write_count_o+(wr_valid_i&&wr_ready_o);
      read_stall_count_o<=read_stall_count_o+(rd_valid_i[0]&&!rd_ready_o[0])+(rd_valid_i[1]&&!rd_ready_o[1]);
      write_stall_count_o<=write_stall_count_o+(wr_valid_i&&!wr_ready_o);
      bank_conflict_count_o<=bank_conflict_count_o+
        (eligible0&&!rd_ready_o[0])+(eligible1&&!rd_ready_o[1])+(wr_valid_i&&!wr_ready_o);
      macro_error_count_o<=macro_error_count_o+macro_error_fires;
      if(rd_resp_valid_q[0]&&rd_resp_ready_i[0])rd_resp_valid_q[0]<=0;
      if(rd_resp_valid_q[1]&&rd_resp_ready_i[1])rd_resp_valid_q[1]<=0;
      for(seq_g=0;seq_g<GROUPS;seq_g++)begin
        if(group_req_valid[seq_g]&&group_req_ready[seq_g])begin
`ifndef SYNTHESIS
          if(!rd_valid_i[0]&&!rd_valid_i[1]&&selected_tag[seq_g]!=TAG_WR)
            $fatal(1,"non-write tag accepted without read request group=%0d tag=%0d",seq_g,selected_tag[seq_g]);
`endif
          group_tag_q[seq_g]<=selected_tag[seq_g];rr_q[seq_g]<=selected_tag[seq_g]==TAG_WR?TAG_RD0:selected_tag[seq_g]+1'b1;
          if(selected_tag[seq_g]==TAG_RD0)rd_outstanding_q[0]<=1;
          if(selected_tag[seq_g]==TAG_RD1)rd_outstanding_q[1]<=1;
        end
        if(group_rsp_valid[seq_g]&&group_rsp_ready[seq_g])begin
`ifndef SYNTHESIS
          if(group_tag_q[seq_g]==TAG_RD0&&!rd_outstanding_q[0])
            $fatal(1,"read0 response without outstanding group=%0d",seq_g);
          if(group_tag_q[seq_g]==TAG_RD1&&!rd_outstanding_q[1])
            $fatal(1,"read1 response without outstanding group=%0d",seq_g);
`endif
          if(group_tag_q[seq_g]==TAG_RD0)begin
            rd_data_q[0 +: DATA_W]<=group_rsp_rdata[seq_g*512 +: 512];rd_resp_valid_q[0]<=1;rd_outstanding_q[0]<=0;
          end
          if(group_tag_q[seq_g]==TAG_RD1)begin
            rd_data_q[DATA_W +: DATA_W]<=group_rsp_rdata[seq_g*512 +: 512];rd_resp_valid_q[1]<=1;rd_outstanding_q[1]<=0;
          end
        end
      end
    end
  end
endmodule

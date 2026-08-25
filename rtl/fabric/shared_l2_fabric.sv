// SPDX-License-Identifier: Apache-2.0
// Shared-L2 contract: 16 logical 128-bit banks. Every 512-bit beat occupies
// four consecutive banks; two reads and one write arbitrate per bank group.
`timescale 1ns/1ps
module shared_l2_fabric #(
  parameter integer DATA_W = 512,
  parameter integer ADDR_W = 15,
  parameter integer BANKS  = 16,
  parameter integer ROWS_PER_BANK = 6144
) (
  input logic clk_i, input logic rst_ni,
  input logic [1:0] rd_valid_i, output logic [1:0] rd_ready_o,
  input logic [2*ADDR_W-1:0] rd_addr_i,
  output logic [1:0] rd_resp_valid_o, input logic [1:0] rd_resp_ready_i,
  output logic [2*DATA_W-1:0] rd_data_o,
  input logic wr_valid_i, output logic wr_ready_o,
  input logic [ADDR_W-1:0] wr_addr_i, input logic [DATA_W-1:0] wr_data_i,
  input logic [DATA_W/8-1:0] wr_be_i,
  output logic [63:0] cycle_count_o, output logic [63:0] read_count_o,
  output logic [63:0] write_count_o, output logic [63:0] bank_conflict_count_o,
  output logic [63:0] read_stall_count_o, output logic [63:0] write_stall_count_o
);
  localparam integer BANK_DATA_W=128, LANES=DATA_W/BANK_DATA_W;
  localparam integer GROUPS=BANKS/LANES, GROUP_W=$clog2(GROUPS);
  localparam integer ROW_W=ADDR_W-GROUP_W;
  logic [BANK_DATA_W-1:0] mem_q [0:BANKS-1][0:ROWS_PER_BANK-1];
  logic [1:0] rd_resp_valid_q, rd_grant;
  logic [2*DATA_W-1:0] rd_data_q;
  logic wr_grant, eligible0, eligible1;
  logic [GROUP_W-1:0] rd_group0, rd_group1, wr_group;
  logic [ROW_W-1:0] rd_row0, rd_row1, wr_row;
  logic [1:0] rr_q [0:GROUPS-1];
  integer comb_group, reset_group, write_lane, write_byte, read_lane;

  initial if (DATA_W!=512 || BANKS!=16 || LANES!=4)
    $error("shared_l2_fabric requires 512-bit beats and 16x128-bit banks");
`ifndef SYNTHESIS
  integer init_bank, init_row;
  initial for(init_bank=0;init_bank<BANKS;init_bank++)
    for(init_row=0;init_row<ROWS_PER_BANK;init_row++) mem_q[init_bank][init_row]='0;
`endif

  assign rd_group0=rd_addr_i[0 +: GROUP_W];
  assign rd_group1=rd_addr_i[ADDR_W +: GROUP_W];
  assign wr_group=wr_addr_i[0 +: GROUP_W];
  assign rd_row0=rd_addr_i[GROUP_W +: ROW_W];
  assign rd_row1=rd_addr_i[ADDR_W+GROUP_W +: ROW_W];
  assign wr_row=wr_addr_i[GROUP_W +: ROW_W];
  assign eligible0=rd_valid_i[0]&&(!rd_resp_valid_q[0]||rd_resp_ready_i[0]);
  assign eligible1=rd_valid_i[1]&&(!rd_resp_valid_q[1]||rd_resp_ready_i[1]);

  always_comb begin
    rd_grant='0; wr_grant=0;
    for(comb_group=0;comb_group<GROUPS;comb_group++) begin
      case(rr_q[comb_group])
        2'd0: begin
          if(eligible0&&rd_group0==comb_group[GROUP_W-1:0]) rd_grant[0]=1;
          else if(eligible1&&rd_group1==comb_group[GROUP_W-1:0]) rd_grant[1]=1;
          else if(wr_valid_i&&wr_group==comb_group[GROUP_W-1:0]) wr_grant=1;
        end
        2'd1: begin
          if(eligible1&&rd_group1==comb_group[GROUP_W-1:0]) rd_grant[1]=1;
          else if(wr_valid_i&&wr_group==comb_group[GROUP_W-1:0]) wr_grant=1;
          else if(eligible0&&rd_group0==comb_group[GROUP_W-1:0]) rd_grant[0]=1;
        end
        default: begin
          if(wr_valid_i&&wr_group==comb_group[GROUP_W-1:0]) wr_grant=1;
          else if(eligible0&&rd_group0==comb_group[GROUP_W-1:0]) rd_grant[0]=1;
          else if(eligible1&&rd_group1==comb_group[GROUP_W-1:0]) rd_grant[1]=1;
        end
      endcase
    end
    rd_ready_o=rd_grant; wr_ready_o=wr_grant;
  end
  assign rd_resp_valid_o=rd_resp_valid_q;
  assign rd_data_o=rd_data_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      rd_resp_valid_q<='0; rd_data_q<='0; cycle_count_o<='0;
      read_count_o<='0; write_count_o<='0; bank_conflict_count_o<='0;
      read_stall_count_o<='0; write_stall_count_o<='0;
      for(reset_group=0;reset_group<GROUPS;reset_group++) rr_q[reset_group]<='0;
    end else begin
      cycle_count_o<=cycle_count_o+1'b1;
      read_count_o<=read_count_o+rd_grant[0]+rd_grant[1];
      write_count_o<=write_count_o+wr_grant;
      read_stall_count_o<=read_stall_count_o+(rd_valid_i[0]&&!rd_ready_o[0])+
                          (rd_valid_i[1]&&!rd_ready_o[1]);
      write_stall_count_o<=write_stall_count_o+(wr_valid_i&&!wr_ready_o);
      bank_conflict_count_o<=bank_conflict_count_o+(eligible0&&!rd_grant[0])+
                             (eligible1&&!rd_grant[1])+(wr_valid_i&&!wr_grant);
      if(wr_grant) begin
        for(write_lane=0;write_lane<LANES;write_lane++)
          for(write_byte=0;write_byte<BANK_DATA_W/8;write_byte++)
            if(wr_be_i[write_lane*(BANK_DATA_W/8)+write_byte])
              mem_q[wr_group*LANES+write_lane][wr_row][write_byte*8 +: 8] <=
                wr_data_i[write_lane*BANK_DATA_W+write_byte*8 +: 8];
        rr_q[wr_group]<=2'd0;
      end
      if(rd_resp_valid_q[0]&&rd_resp_ready_i[0]&&!rd_grant[0]) rd_resp_valid_q[0]<=0;
      if(rd_resp_valid_q[1]&&rd_resp_ready_i[1]&&!rd_grant[1]) rd_resp_valid_q[1]<=0;
      if(rd_grant[0]) begin
        for(read_lane=0;read_lane<LANES;read_lane++)
          rd_data_q[read_lane*BANK_DATA_W +: BANK_DATA_W] <=
            mem_q[rd_group0*LANES+read_lane][rd_row0];
        rd_resp_valid_q[0]<=1; rr_q[rd_group0]<=2'd1;
      end
      if(rd_grant[1]) begin
        for(read_lane=0;read_lane<LANES;read_lane++)
          rd_data_q[DATA_W+read_lane*BANK_DATA_W +: BANK_DATA_W] <=
            mem_q[rd_group1*LANES+read_lane][rd_row1];
        rd_resp_valid_q[1]<=1; rr_q[rd_group1]<=2'd2;
      end
    end
  end
endmodule

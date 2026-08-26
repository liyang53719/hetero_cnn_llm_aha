// SPDX-License-Identifier: Apache-2.0
// Four logical read clients -> two physical reads; two writes -> one write.
`timescale 1ns/1ps
module shared_l2_client_arbiter #(
  parameter integer ADDR_W=15,parameter integer DATA_W=512
)(
  input logic clk_i,input logic rst_ni,
  input logic[3:0]rd_valid_i,output logic[3:0]rd_ready_o,
  input logic[4*ADDR_W-1:0]rd_addr_i,
  output logic[3:0]rd_rsp_valid_o,input logic[3:0]rd_rsp_ready_i,
  output logic[4*DATA_W-1:0]rd_rsp_data_o,output logic[3:0]rd_rsp_error_o,
  input logic[1:0]wr_valid_i,output logic[1:0]wr_ready_o,
  input logic[2*ADDR_W-1:0]wr_addr_i,input logic[2*DATA_W-1:0]wr_data_i,
  input logic[2*(DATA_W/8)-1:0]wr_be_i,
  output logic[1:0]phy_rd_valid_o,input logic[1:0]phy_rd_ready_i,
  output logic[2*ADDR_W-1:0]phy_rd_addr_o,
  input logic[1:0]phy_rsp_valid_i,output logic[1:0]phy_rsp_ready_o,
  input logic[2*DATA_W-1:0]phy_rsp_data_i,input logic[1:0]phy_rsp_error_i,
  output logic phy_wr_valid_o,input logic phy_wr_ready_i,
  output logic[ADDR_W-1:0]phy_wr_addr_o,output logic[DATA_W-1:0]phy_wr_data_o,
  output logic[DATA_W/8-1:0]phy_wr_be_o,
  output logic[31:0]descriptor_promotions_o,output logic[31:0]read_grants_o,
  output logic[31:0]write_grants_o
);
  logic[1:0]read_rr_q;logic write_rr_q;
  logic[3:0]logical_outstanding_q;
  logic[1:0]slot_pending_q,slot_outstanding_q;logic[1:0]slot_owner_q[0:1];
  logic[ADDR_W-1:0]slot_addr_q[0:1];logic[3:0]descriptor_wait_q;
  logic write_pending_q,write_owner_q;logic[ADDR_W-1:0]write_addr_q;
  logic other_write;
  logic[DATA_W-1:0]write_data_q;logic[DATA_W/8-1:0]write_be_q;
  logic[3:0]eligible;logic[1:0]pick0,pick1;logic pick0_valid,pick1_valid;
  logic[1:0]read_accept_count;integer comb_c,comb_s,offset,seq_s;
  function automatic logic[1:0]rr_index(input logic[1:0]start,input logic[1:0]off);
    rr_index=start+off;
  endfunction
  always_comb begin
    eligible='0;
    for(comb_c=0;comb_c<4;comb_c++)eligible[comb_c]=rd_valid_i[comb_c]&&!logical_outstanding_q[comb_c]&&
      !(slot_pending_q[0]&&slot_owner_q[0]==2'(comb_c))&&
      !(slot_pending_q[1]&&slot_owner_q[1]==2'(comb_c));
    pick0=0;pick1=0;pick0_valid=0;pick1_valid=0;
    if(eligible[0]&&descriptor_wait_q>=8)begin pick0=0;pick0_valid=1;end
    else for(offset=0;offset<4;offset++)if(!pick0_valid&&eligible[rr_index(read_rr_q,2'(offset))])begin
      pick0=rr_index(read_rr_q,2'(offset));pick0_valid=1;end
    for(offset=0;offset<4;offset++)if(!pick1_valid&&eligible[rr_index(read_rr_q,2'(offset))]&&
       (!pick0_valid||rr_index(read_rr_q,2'(offset))!=pick0))begin
      pick1=rr_index(read_rr_q,2'(offset));pick1_valid=1;end
  end
  assign phy_rd_valid_o=slot_pending_q;
  assign read_accept_count=(slot_pending_q[0]&&phy_rd_ready_i[0])+
                           (slot_pending_q[1]&&phy_rd_ready_i[1]);
  assign phy_rd_addr_o={slot_addr_q[1],slot_addr_q[0]};
  always_comb begin
    rd_ready_o=0;rd_rsp_valid_o=0;rd_rsp_data_o=0;rd_rsp_error_o=0;phy_rsp_ready_o=0;
    for(comb_s=0;comb_s<2;comb_s++)begin
      if(slot_pending_q[comb_s]&&phy_rd_ready_i[comb_s])rd_ready_o[slot_owner_q[comb_s]]=1;
      if(slot_outstanding_q[comb_s])begin
        rd_rsp_valid_o[slot_owner_q[comb_s]]=phy_rsp_valid_i[comb_s];
        rd_rsp_data_o[slot_owner_q[comb_s]*DATA_W +: DATA_W]=phy_rsp_data_i[comb_s*DATA_W +: DATA_W];
        rd_rsp_error_o[slot_owner_q[comb_s]]=phy_rsp_error_i[comb_s];
        phy_rsp_ready_o[comb_s]=rd_rsp_ready_i[slot_owner_q[comb_s]];
      end
    end
  end
  assign phy_wr_valid_o=write_pending_q;assign phy_wr_addr_o=write_addr_q;
  assign other_write=write_rr_q^1'b1;
  assign phy_wr_data_o=write_data_q;assign phy_wr_be_o=write_be_q;
  always_comb begin wr_ready_o=0;if(write_pending_q&&phy_wr_ready_i)wr_ready_o[write_owner_q]=1;end

  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin read_rr_q<=0;write_rr_q<=0;logical_outstanding_q<=0;
      slot_pending_q<=0;slot_outstanding_q<=0;descriptor_wait_q<=0;write_pending_q<=0;
      write_owner_q<=0;write_addr_q<=0;write_data_q<=0;write_be_q<=0;
      descriptor_promotions_o<=0;read_grants_o<=0;write_grants_o<=0;
      for(seq_s=0;seq_s<2;seq_s++)begin slot_owner_q[seq_s]<=0;slot_addr_q[seq_s]<=0;end
    end else begin
      if(rd_valid_i[0]&&!logical_outstanding_q[0]&&!rd_ready_o[0])begin
        if(descriptor_wait_q<15)descriptor_wait_q<=descriptor_wait_q+1'b1;
      end else descriptor_wait_q<=0;
      if(!slot_pending_q[0]&&!slot_outstanding_q[0]&&pick0_valid)begin
        slot_pending_q[0]<=1;slot_owner_q[0]<=pick0;slot_addr_q[0]<=rd_addr_i[pick0*ADDR_W +: ADDR_W];
        if(pick0==0&&descriptor_wait_q>=8)descriptor_promotions_o<=descriptor_promotions_o+1'b1;
      end
      if(!slot_pending_q[1]&&!slot_outstanding_q[1]&&pick1_valid)begin
        slot_pending_q[1]<=1;slot_owner_q[1]<=pick1;slot_addr_q[1]<=rd_addr_i[pick1*ADDR_W +: ADDR_W];
      end
      for(seq_s=0;seq_s<2;seq_s++)begin
        if(slot_pending_q[seq_s]&&phy_rd_ready_i[seq_s])begin
          slot_pending_q[seq_s]<=0;slot_outstanding_q[seq_s]<=1;logical_outstanding_q[slot_owner_q[seq_s]]<=1;
          read_rr_q<=slot_owner_q[seq_s]+1'b1;
        end
        if(slot_outstanding_q[seq_s]&&phy_rsp_valid_i[seq_s]&&phy_rsp_ready_o[seq_s])begin
          slot_outstanding_q[seq_s]<=0;logical_outstanding_q[slot_owner_q[seq_s]]<=0;
        end
      end
      read_grants_o<=read_grants_o+{30'd0,read_accept_count};
      if(!write_pending_q)begin
        if(wr_valid_i[write_rr_q])begin write_pending_q<=1;write_owner_q<=write_rr_q;
          write_addr_q<=wr_addr_i[write_rr_q*ADDR_W +: ADDR_W];
          write_data_q<=wr_data_i[write_rr_q*DATA_W +: DATA_W];
          write_be_q<=wr_be_i[write_rr_q*(DATA_W/8) +: DATA_W/8];end
        else if(wr_valid_i[other_write])begin write_pending_q<=1;write_owner_q<=other_write;
          write_addr_q<=wr_addr_i[other_write*ADDR_W +: ADDR_W];
          write_data_q<=wr_data_i[other_write*DATA_W +: DATA_W];
          write_be_q<=wr_be_i[other_write*(DATA_W/8) +: DATA_W/8];end
      end else if(phy_wr_ready_i)begin
        write_pending_q<=0;write_rr_q<=write_owner_q+1'b1;write_grants_o<=write_grants_o+1'b1;
      end
    end
  end
endmodule

// SPDX-License-Identifier: Apache-2.0
// Internal row-major BF16 tiling after descriptor validation. No data compute.
// Advance ONLY after the issued tile's memory writeback/completion is checked.
module bf16_projection_tile_iterator(
 input logic clk_i,rst_ni,request_valid_i,output logic request_ready_o,
 input logic[31:0]m_i,n_i,k_i,a_stride_i,b_stride_i,c_stride_i,
 input logic[63:0]a_base_i,b_base_i,c_base_i,
 output logic tile_valid_o,input logic tile_ready_i,
 output logic[31:0]row_o,column_o,
 output logic[15:0]rows_o,columns_o,depth_o,
 output logic[63:0]a_addr_o,b_addr_o,c_addr_o,
 input logic tile_done_valid_i,output logic tile_done_ready_o,input logic[7:0]tile_status_i,
 output logic completion_valid_o,input logic completion_ready_i,output logic[7:0]status_o,
 output logic[63:0]completed_tiles_o,useful_macs_o
);
 typedef enum logic[1:0]{IDLE,ISSUE,WAIT_TILE,COMPLETE}state_t;
 state_t state_q;
 logic[31:0]m_q,n_q,k_q,as_q,bs_q,cs_q,row_q,col_q;
 logic[63:0]a_q,b_q,c_q;
 logic legal;
 logic[64:0]a_end,b_end,c_end;
 // stride and shape products fit 64 bits; retain the carry on base addition.
 assign a_end={1'b0,a_base_i}+65'(m_i-1)*65'(a_stride_i)+65'(k_i)*2;
 assign b_end={1'b0,b_base_i}+65'(k_i-1)*65'(b_stride_i)+65'(n_i)*2;
 assign c_end={1'b0,c_base_i}+65'(m_i-1)*65'(c_stride_i)+65'(n_i)*2;
 assign legal=m_i!=0&&n_i!=0&&k_i!=0&&k_i<=65535&&
   !a_base_i[0]&&!b_base_i[0]&&!c_base_i[0]&&
   !a_stride_i[0]&&!b_stride_i[0]&&!c_stride_i[0]&&
   33'(a_stride_i)>=33'(k_i)*2&&33'(b_stride_i)>=33'(n_i)*2&&33'(c_stride_i)>=33'(n_i)*2&&
   a_end<=65'h10000000000000000&&b_end<=65'h10000000000000000&&c_end<=65'h10000000000000000;
 assign request_ready_o=state_q==IDLE;
 assign tile_valid_o=state_q==ISSUE;assign tile_done_ready_o=state_q==WAIT_TILE;
 assign completion_valid_o=state_q==COMPLETE;
 assign row_o=row_q;assign column_o=col_q;
 assign rows_o=(m_q-row_q>=16)?16:16'(m_q-row_q);
 assign columns_o=(n_q-col_q>=32)?32:16'(n_q-col_q);
 assign depth_o=16'(k_q);
 assign a_addr_o=a_q+64'(row_q)*as_q;
 assign b_addr_o=b_q+64'(col_q)*2;
 assign c_addr_o=c_q+64'(row_q)*cs_q+64'(col_q)*2;
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=IDLE;m_q<=0;n_q<=0;k_q<=0;as_q<=0;bs_q<=0;cs_q<=0;
   row_q<=0;col_q<=0;a_q<=0;b_q<=0;c_q<=0;status_o<=0;completed_tiles_o<=0;useful_macs_o<=0;end
  else case(state_q)
   IDLE:if(request_valid_i)begin
    m_q<=m_i;n_q<=n_i;k_q<=k_i;as_q<=a_stride_i;bs_q<=b_stride_i;cs_q<=c_stride_i;
    a_q<=a_base_i;b_q<=b_base_i;c_q<=c_base_i;row_q<=0;col_q<=0;
    completed_tiles_o<=0;useful_macs_o<=0;status_o<=legal?0:5;state_q<=legal?ISSUE:COMPLETE;
   end
   ISSUE:if(tile_ready_i)state_q<=WAIT_TILE;
   WAIT_TILE:if(tile_done_valid_i)begin
    if(tile_status_i!=0)begin status_o<=tile_status_i;state_q<=COMPLETE;end
    else if(useful_macs_o>64'hffffffffffffffff-64'(rows_o)*columns_o*k_q)begin
      status_o<=5;state_q<=COMPLETE;
    end else begin
     completed_tiles_o<=completed_tiles_o+1;
     useful_macs_o<=useful_macs_o+64'(rows_o)*columns_o*k_q;
     if(n_q-col_q>32)begin col_q<=col_q+32;state_q<=ISSUE;end
     else if(m_q-row_q>16)begin col_q<=0;row_q<=row_q+16;state_q<=ISSUE;end
     else state_q<=COMPLETE;
    end
   end
   COMPLETE:if(completion_ready_i)state_q<=IDLE;
   default:state_q<=IDLE;
  endcase
 end
endmodule

// SPDX-License-Identifier: Apache-2.0
// Source-ready refcount/COW table. Supports one increment, decrement and COW event per cycle.
module state_refcount_cow_table #(
  parameter int PAGES=128,
  parameter int PAGE_W=$clog2(PAGES),
  parameter int REF_W=8
) (
  input logic clk_i,rst_ni,
  input logic inc_valid_i,input logic [PAGE_W-1:0] inc_page_i,
  input logic dec_valid_i,input logic [PAGE_W-1:0] dec_page_i,
  input logic cow_valid_i,input logic [PAGE_W-1:0] cow_old_page_i,input logic [PAGE_W-1:0] cow_new_page_i,
  output logic cow_copy_required_o,output logic protocol_error_o
);
  logic [REF_W-1:0] ref_q[0:PAGES-1]; integer i,p; integer signed delta; logic old_shared;
  always_comb begin old_shared=cow_valid_i&&(ref_q[cow_old_page_i]>1);cow_copy_required_o=old_shared;end
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin protocol_error_o<=0;for(i=0;i<PAGES;i++)ref_q[i]<='0;end
    else begin
      for(p=0;p<PAGES;p++)begin
        delta=0;
        if(inc_valid_i&&inc_page_i==p)delta++;
        if(dec_valid_i&&dec_page_i==p)delta--;
        if(cow_valid_i&&old_shared&&cow_old_page_i==p)delta--;
        if(cow_valid_i&&old_shared&&cow_new_page_i==p)delta++;
        if(delta!=0)begin
          if(($signed({1'b0,ref_q[p]})+delta)<0 || ($signed({1'b0,ref_q[p]})+delta)>((1<<REF_W)-1))protocol_error_o<=1;
          else ref_q[p]<=ref_q[p]+delta;
        end
      end
      if(cow_valid_i&&old_shared&&ref_q[cow_new_page_i]!=0)protocol_error_o<=1;
    end
  end
`ifndef SYNTHESIS
  always_ff@(posedge clk_i)if(rst_ni)begin
    if(dec_valid_i)assert(ref_q[dec_page_i]>0)else$fatal(1,"refcount underflow");
    if(cow_valid_i&&old_shared)assert(cow_new_page_i!=cow_old_page_i);
  end
`endif
endmodule

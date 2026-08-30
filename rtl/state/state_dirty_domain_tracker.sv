module state_dirty_domain_tracker #(
  parameter int SLOTS=8,SLOT_W=$clog2(SLOTS),DOMAINS=10,DOMAIN_W=$clog2(DOMAINS)
)(
  input logic clk_i,rst_ni,clear_valid_i,
  input logic [SLOT_W-1:0] clear_slot_i,
  input logic set_valid_i,
  input logic [SLOT_W-1:0] set_slot_i,
  input logic [DOMAIN_W-1:0] set_domain_i,
  input logic [SLOT_W-1:0] query_slot_i,
  output logic [DOMAINS-1:0] dirty_mask_o
);
  logic[DOMAINS-1:0]dirty_q[0:SLOTS-1];integer index;
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)for(index=0;index<SLOTS;index++)dirty_q[index]<='0;
    else begin if(clear_valid_i)dirty_q[clear_slot_i]<='0;if(set_valid_i&&set_domain_i<DOMAINS)dirty_q[set_slot_i][set_domain_i]<=1'b1;end
  end
  assign dirty_mask_o=dirty_q[query_slot_i];
endmodule

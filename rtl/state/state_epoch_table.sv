module state_epoch_table #(
  parameter int SLOTS=64, SLOT_W=$clog2(SLOTS), SEQUENCE_W=32, GENERATION_W=32
)(
  input logic clk_i,rst_ni,update_valid_i,
  input logic [SLOT_W-1:0] update_slot_i,
  input logic [SEQUENCE_W-1:0] update_sequence_i,
  input logic [GENERATION_W-1:0] update_generation_i,
  input logic update_invalidate_i,
  input logic [SLOT_W-1:0] query_slot_i,
  input logic [SEQUENCE_W-1:0] query_sequence_i,
  input logic [GENERATION_W-1:0] query_generation_i,
  output logic query_hit_o,query_current_o,
  output logic [GENERATION_W-1:0] current_generation_o
);
  logic valid_q[0:SLOTS-1];logic[SEQUENCE_W-1:0]sequence_q[0:SLOTS-1];logic[GENERATION_W-1:0]generation_q[0:SLOTS-1];integer index;
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)for(index=0;index<SLOTS;index++)begin valid_q[index]<=1'b0;sequence_q[index]<='0;generation_q[index]<='0;end
    else if(update_valid_i)begin valid_q[update_slot_i]<=!update_invalidate_i;sequence_q[update_slot_i]<=update_sequence_i;generation_q[update_slot_i]<=update_generation_i;end
  end
  always_comb begin query_hit_o=valid_q[query_slot_i]&&sequence_q[query_slot_i]==query_sequence_i;current_generation_o=generation_q[query_slot_i];query_current_o=query_hit_o&&generation_q[query_slot_i]==query_generation_i;end
endmodule

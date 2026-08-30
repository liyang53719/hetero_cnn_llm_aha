module state_commit_barrier #(
  parameter int SLOTS=8,SLOT_W=$clog2(SLOTS),TXN_W=16,DOMAINS=10,DOMAIN_W=$clog2(DOMAINS)
)(
  input logic clk_i,rst_ni,start_valid_i,
  output logic start_ready_o,
  input logic [SLOT_W-1:0] start_slot_i,
  input logic [TXN_W-1:0] start_txn_i,
  input logic [DOMAINS-1:0] start_expected_mask_i,
  input logic ack_valid_i,
  input logic [SLOT_W-1:0] ack_slot_i,
  input logic [DOMAIN_W-1:0] ack_domain_i,
  input logic fail_valid_i,
  input logic [SLOT_W-1:0] fail_slot_i,
  input logic finish_valid_i,
  output logic finish_ready_o,
  input logic [SLOT_W-1:0] finish_slot_i,
  input logic finish_commit_i,
  output logic done_valid_o,
  input logic done_ready_i,
  output logic [TXN_W-1:0] done_txn_o,
  output logic done_commit_o,protocol_error_o
);
  logic active_q[0:SLOTS-1],failed_q[0:SLOTS-1];logic[TXN_W-1:0]txn_q[0:SLOTS-1];logic[DOMAINS-1:0]expected_q[0:SLOTS-1],ack_q[0:SLOTS-1];logic done_pending_q;logic[TXN_W-1:0]done_txn_q;logic done_commit_q;integer index;logic selected_ready;
  always_comb begin start_ready_o=!active_q[start_slot_i]&&!done_pending_q;selected_ready=active_q[finish_slot_i]&&((ack_q[finish_slot_i]&expected_q[finish_slot_i])==expected_q[finish_slot_i]);finish_ready_o=!done_pending_q&&selected_ready;done_valid_o=done_pending_q;done_txn_o=done_txn_q;done_commit_o=done_commit_q;end
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin done_pending_q<=1'b0;done_txn_q<='0;done_commit_q<=1'b0;protocol_error_o<=1'b0;for(index=0;index<SLOTS;index++)begin active_q[index]<=1'b0;txn_q[index]<='0;expected_q[index]<='0;ack_q[index]<='0;failed_q[index]<=1'b0;end end
    else begin
      protocol_error_o<=1'b0;if(done_pending_q&&done_ready_i)done_pending_q<=1'b0;
      if(start_valid_i)begin if(start_ready_o&&start_expected_mask_i!='0)begin active_q[start_slot_i]<=1'b1;txn_q[start_slot_i]<=start_txn_i;expected_q[start_slot_i]<=start_expected_mask_i;ack_q[start_slot_i]<='0;failed_q[start_slot_i]<=1'b0;end else protocol_error_o<=1'b1;end
      if(ack_valid_i)begin if(active_q[ack_slot_i]&&ack_domain_i<DOMAINS&&expected_q[ack_slot_i][ack_domain_i]&&!ack_q[ack_slot_i][ack_domain_i])ack_q[ack_slot_i][ack_domain_i]<=1'b1;else protocol_error_o<=1'b1;end
      if(fail_valid_i)begin if(active_q[fail_slot_i])failed_q[fail_slot_i]<=1'b1;else protocol_error_o<=1'b1;end
      if(finish_valid_i)begin if(finish_ready_o)begin done_pending_q<=1'b1;done_txn_q<=txn_q[finish_slot_i];done_commit_q<=finish_commit_i&&!failed_q[finish_slot_i];active_q[finish_slot_i]<=1'b0;expected_q[finish_slot_i]<='0;ack_q[finish_slot_i]<='0;failed_q[finish_slot_i]<=1'b0;end else protocol_error_o<=1'b1;end
    end
  end
endmodule

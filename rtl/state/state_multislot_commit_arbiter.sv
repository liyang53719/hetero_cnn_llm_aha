// SPDX-License-Identifier: Apache-2.0
// Eight-slot commit/rollback barrier with dirty page/word-mask merging.
module state_multislot_commit_arbiter #(
  parameter int SLOTS = 8,
  parameter int SLOT_W = $clog2(SLOTS),
  parameter int DOMAINS = 10,
  parameter int PAGE_W = 16,
  parameter int WORDS = 64
) (
  input logic clk_i, rst_ni,
  input logic start_valid_i,
  input logic [SLOT_W-1:0] start_slot_i,
  input logic [31:0] start_txn_id_i,
  input logic [DOMAINS-1:0] start_required_i,
  input logic ack_valid_i,
  input logic [SLOT_W-1:0] ack_slot_i,
  input logic [$clog2(DOMAINS)-1:0] ack_domain_i,
  input logic dirty_valid_i,
  input logic [SLOT_W-1:0] dirty_slot_i,
  input logic [PAGE_W-1:0] dirty_page_i,
  input logic [WORDS-1:0] dirty_word_mask_i,
  input logic decide_valid_i,
  input logic [SLOT_W-1:0] decide_slot_i,
  input logic decide_commit_i,
  output logic resolve_valid_o,
  input logic resolve_ready_i,
  output logic [SLOT_W-1:0] resolve_slot_o,
  output logic [31:0] resolve_txn_id_o,
  output logic resolve_commit_o,
  output logic [PAGE_W-1:0] resolve_dirty_page_o,
  output logic [WORDS-1:0] resolve_dirty_word_mask_o,
  output logic protocol_error_o
);
  logic active_q [0:SLOTS-1], decision_valid_q [0:SLOTS-1], decision_commit_q [0:SLOTS-1];
  logic [31:0] txn_q [0:SLOTS-1];
  logic [DOMAINS-1:0] required_q [0:SLOTS-1], acked_q [0:SLOTS-1];
  logic [PAGE_W-1:0] dirty_page_q [0:SLOTS-1];
  logic [WORDS-1:0] dirty_mask_q [0:SLOTS-1];
  integer i; logic found;
  always_comb begin
    resolve_valid_o=0; resolve_slot_o='0; resolve_txn_id_o='0; resolve_commit_o=0; resolve_dirty_page_o='0; resolve_dirty_word_mask_o='0; found=0;
    for(i=0;i<SLOTS;i++) if(!found && active_q[i] && decision_valid_q[i] && (!decision_commit_q[i] || ((acked_q[i]&required_q[i])==required_q[i]))) begin
      found=1; resolve_valid_o=1; resolve_slot_o=SLOT_W'(i); resolve_txn_id_o=txn_q[i]; resolve_commit_o=decision_commit_q[i]; resolve_dirty_page_o=dirty_page_q[i]; resolve_dirty_word_mask_o=dirty_mask_q[i];
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin protocol_error_o<=0; for(i=0;i<SLOTS;i++) begin active_q[i]<=0;decision_valid_q[i]<=0;decision_commit_q[i]<=0;txn_q[i]<='0;required_q[i]<='0;acked_q[i]<='0;dirty_page_q[i]<='0;dirty_mask_q[i]<='0;end end
    else begin
      if(start_valid_i) begin
        if(active_q[start_slot_i]) protocol_error_o<=1; else begin active_q[start_slot_i]<=1;decision_valid_q[start_slot_i]<=0;txn_q[start_slot_i]<=start_txn_id_i;required_q[start_slot_i]<=start_required_i;acked_q[start_slot_i]<='0;dirty_mask_q[start_slot_i]<='0;dirty_page_q[start_slot_i]<='0;end
      end
      if(ack_valid_i) begin if(!active_q[ack_slot_i]) protocol_error_o<=1; else acked_q[ack_slot_i][ack_domain_i]<=1'b1; end
      if(dirty_valid_i) begin
        if(!active_q[dirty_slot_i]) protocol_error_o<=1;
        else if(dirty_mask_q[dirty_slot_i]=='0 || dirty_page_q[dirty_slot_i]==dirty_page_i) begin dirty_page_q[dirty_slot_i]<=dirty_page_i;dirty_mask_q[dirty_slot_i]<=dirty_mask_q[dirty_slot_i]|dirty_word_mask_i;end
        else protocol_error_o<=1;
      end
      if(decide_valid_i) begin
        if(!active_q[decide_slot_i] || decision_valid_q[decide_slot_i]) protocol_error_o<=1;
        else begin decision_valid_q[decide_slot_i]<=1;decision_commit_q[decide_slot_i]<=decide_commit_i;if(decide_commit_i && ((acked_q[decide_slot_i]&required_q[decide_slot_i])!=required_q[decide_slot_i])) protocol_error_o<=1;end
      end
      if(resolve_valid_o&&resolve_ready_i) begin active_q[resolve_slot_o]<=0;decision_valid_q[resolve_slot_o]<=0;dirty_mask_q[resolve_slot_o]<='0;end
    end
  end
`ifndef SYNTHESIS
  always_ff @(posedge clk_i) if(rst_ni) begin
    if(resolve_valid_o) assert(active_q[resolve_slot_o]);
    if(resolve_valid_o&&resolve_commit_o) assert((acked_q[resolve_slot_o]&required_q[resolve_slot_o])==required_q[resolve_slot_o]);
    if(dirty_valid_i&&active_q[dirty_slot_i]&&dirty_page_q[dirty_slot_i]==dirty_page_i) assert((dirty_mask_q[dirty_slot_i]|dirty_word_mask_i)>=dirty_mask_q[dirty_slot_i]);
  end
`endif
endmodule

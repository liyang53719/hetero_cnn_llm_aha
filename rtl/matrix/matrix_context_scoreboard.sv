// SPDX-License-Identifier: Apache-2.0
module matrix_context_scoreboard #(parameter integer CONTEXTS=4,parameter integer TAG_BITS=$clog2(CONTEXTS))(input logic clk_i,rst_ni,issue_valid_i,output logic issue_ready_o,input logic[TAG_BITS-1:0]issue_context_i,input logic complete_valid_i,input logic[TAG_BITS-1:0]complete_context_i,output logic[CONTEXTS-1:0]busy_o,output logic protocol_error_o);
 logic[CONTEXTS-1:0]busy;assign busy_o=busy;assign issue_ready_o=issue_context_i<CONTEXTS&&!busy[issue_context_i];
 always_ff@(posedge clk_i or negedge rst_ni)if(!rst_ni)begin busy<=0;protocol_error_o<=0;end else begin if(issue_valid_i)begin if(issue_ready_o)busy[issue_context_i]<=1;else protocol_error_o<=1;end if(complete_valid_i)begin if(complete_context_i>=CONTEXTS||!busy[complete_context_i])protocol_error_o<=1;else busy[complete_context_i]<=0;end end
endmodule

module bf16_outer_product_context_array_rev8b_b_candidate(
 input logic clk_i,rst_ni,in_valid_i,output logic in_ready_o,input logic[2:0]context_i,input logic clear_i,last_i,
 input logic[255:0]a_i,input logic[511:0]b_i,output logic out_valid_o,input logic out_ready_i,output logic[2:0]context_o,
 output logic last_o,output logic[16383:0]acc_o,output logic[4:0]exception_flags_o,output logic[4:0]busy_o,accumulator_valid_o,
 output logic[31:0]accepted_steps_o,completed_steps_o,output logic protocol_error_o);
endmodule

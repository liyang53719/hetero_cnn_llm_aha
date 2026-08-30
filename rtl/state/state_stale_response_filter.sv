module state_stale_response_filter #(
  parameter int DATA_W=512, GENERATION_W=32
)(
  input logic in_valid_i,
  output logic in_ready_o,
  input logic [DATA_W-1:0] in_data_i,
  input logic [GENERATION_W-1:0] in_generation_i,current_generation_i,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic [DATA_W-1:0] out_data_o,
  output logic stale_drop_o
);
  logic stale;
  always_comb begin stale=in_generation_i!=current_generation_i;out_valid_o=in_valid_i&&!stale;out_data_o=in_data_i;in_ready_o=stale?1'b1:out_ready_i;stale_drop_o=in_valid_i&&stale;end
endmodule

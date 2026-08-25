// SPDX-License-Identifier: Apache-2.0
// Routes the frozen 128-bit command envelope by engine[10:8].
module command_dispatch (
  input  logic         cmd_valid_i,
  output logic         cmd_ready_o,
  input  logic [127:0] cmd_data_i,

  output logic         control_valid_o,
  input  logic         control_ready_i,
  output logic [127:0] control_data_o,

  output logic         dma_valid_o,
  input  logic         dma_ready_i,
  output logic [127:0] dma_data_o,

  output logic         matrix_valid_o,
  input  logic         matrix_ready_i,
  output logic [127:0] matrix_data_o,

  output logic         sfu_valid_o,
  input  logic         sfu_ready_i,
  output logic [127:0] sfu_data_o,

  output logic         kv_valid_o,
  input  logic         kv_ready_i,
  output logic [127:0] kv_data_o,

  output logic         collective_valid_o,
  input  logic         collective_ready_i,
  output logic [127:0] collective_data_o,

  output logic         illegal_engine_o
);
  logic [2:0] engine;
  assign engine = cmd_data_i[10:8];

  always_comb begin
    control_valid_o    = 1'b0;
    dma_valid_o        = 1'b0;
    matrix_valid_o     = 1'b0;
    sfu_valid_o        = 1'b0;
    kv_valid_o         = 1'b0;
    collective_valid_o = 1'b0;
    control_data_o     = cmd_data_i;
    dma_data_o         = cmd_data_i;
    matrix_data_o      = cmd_data_i;
    sfu_data_o         = cmd_data_i;
    kv_data_o          = cmd_data_i;
    collective_data_o  = cmd_data_i;
    illegal_engine_o   = 1'b0;
    cmd_ready_o        = 1'b0;

    unique case (engine)
      3'd0: begin control_valid_o = cmd_valid_i; cmd_ready_o = control_ready_i; end
      3'd1: begin dma_valid_o = cmd_valid_i; cmd_ready_o = dma_ready_i; end
      3'd2: begin matrix_valid_o = cmd_valid_i; cmd_ready_o = matrix_ready_i; end
      3'd3: begin sfu_valid_o = cmd_valid_i; cmd_ready_o = sfu_ready_i; end
      3'd4: begin kv_valid_o = cmd_valid_i; cmd_ready_o = kv_ready_i; end
      3'd5: begin collective_valid_o = cmd_valid_i; cmd_ready_o = collective_ready_i; end
      default: begin
        illegal_engine_o = cmd_valid_i;
        cmd_ready_o      = 1'b1;
      end
    endcase
  end
endmodule

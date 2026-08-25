// SPDX-License-Identifier: Apache-2.0
// Vector/SFU contract model.  The AHA-generated island will ultimately sit
// behind this ready/valid boundary; this module supplies a small executable
// baseline for arithmetic, activation and reduction behavior.
module cgra_sfu_vector #(
  parameter integer LANES = 8,
  parameter integer IN_W  = 16,
  parameter integer OUT_W = 32,
  parameter integer OP_W  = 4
) (
  input  logic                       clk_i,
  input  logic                       rst_ni,
  input  logic [OP_W-1:0]            op_i,
  input  logic                       in_valid_i,
  output logic                       in_ready_o,
  input  logic [LANES*IN_W-1:0]      in0_data_i,
  input  logic [LANES*IN_W-1:0]      in1_data_i,
  output logic                       out_valid_o,
  input  logic                       out_ready_i,
  output logic [LANES*OUT_W-1:0]     out_data_o
);
  localparam logic [OP_W-1:0] OP_ADD        = 4'h0;
  localparam logic [OP_W-1:0] OP_MUL        = 4'h1;
  localparam logic [OP_W-1:0] OP_MAX        = 4'h2;
  localparam logic [OP_W-1:0] OP_RELU       = 4'h3;
  localparam logic [OP_W-1:0] OP_ABS        = 4'h4;
  localparam logic [OP_W-1:0] OP_REDUCE_SUM = 4'h5;

  logic [LANES*OUT_W-1:0] result_d;
  logic [LANES*OUT_W-1:0] result_q;
  logic out_valid_q;
  logic signed [OUT_W-1:0] in0_ext [0:LANES-1];
  logic signed [OUT_W-1:0] in1_ext [0:LANES-1];
  logic signed [OUT_W-1:0] reduce_sum;
  integer lane;

  always_comb begin
    result_d   = '0;
    reduce_sum = '0;
    for (lane = 0; lane < LANES; lane++) begin
      in0_ext[lane] = {{(OUT_W-IN_W){in0_data_i[lane*IN_W + IN_W-1]}},
                       in0_data_i[lane*IN_W +: IN_W]};
      in1_ext[lane] = {{(OUT_W-IN_W){in1_data_i[lane*IN_W + IN_W-1]}},
                       in1_data_i[lane*IN_W +: IN_W]};
      reduce_sum = reduce_sum + in0_ext[lane];
    end
    for (lane = 0; lane < LANES; lane++) begin
      unique case (op_i)
        OP_ADD: result_d[lane*OUT_W +: OUT_W] = in0_ext[lane] + in1_ext[lane];
        OP_MUL: result_d[lane*OUT_W +: OUT_W] =
          $signed(in0_data_i[lane*IN_W +: IN_W])
          * $signed(in1_data_i[lane*IN_W +: IN_W]);
        OP_MAX: result_d[lane*OUT_W +: OUT_W] =
          (in0_ext[lane] > in1_ext[lane]) ? in0_ext[lane] : in1_ext[lane];
        OP_RELU: result_d[lane*OUT_W +: OUT_W] =
          (in0_ext[lane] < 0) ? '0 : in0_ext[lane];
        OP_ABS: result_d[lane*OUT_W +: OUT_W] =
          (in0_ext[lane] < 0) ? -in0_ext[lane] : in0_ext[lane];
        OP_REDUCE_SUM: result_d[lane*OUT_W +: OUT_W] =
          (lane == 0) ? reduce_sum : '0;
        default: result_d[lane*OUT_W +: OUT_W] = '0;
      endcase
    end
  end

  assign in_ready_o  = !out_valid_q || out_ready_i;
  assign out_valid_o = out_valid_q;
  assign out_data_o  = result_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      out_valid_q <= 1'b0;
      result_q    <= '0;
    end else if (in_ready_o) begin
      out_valid_q <= in_valid_i;
      if (in_valid_i) result_q <= result_d;
    end
  end

`ifndef SYNTHESIS
  initial begin
    assert (OUT_W >= IN_W) else $fatal(1, "OUT_W must be >= IN_W");
    assert (OUT_W >= 2*IN_W) else $warning("multiply result may truncate");
  end
`endif
endmodule

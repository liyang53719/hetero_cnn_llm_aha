`timescale 1ns/1ps
module tb_bf16_front_to_cluster_broadcast32_rev8b_a;
  localparam integer WIDTH = 11;
  localparam integer LEAVES = 32;
  localparam integer TARGET = 100000;
  logic [WIDTH-1:0] control;
  wire [LEAVES*WIDTH-1:0] leaves;
  logic [31:0] lfsr;
  integer operation, leaf;
  integer trace_fd;
  reg [1023:0] trace_path;

  bf16_front_to_cluster_broadcast32_rev8b_a_candidate dut (
    .control_i(control),
    .cluster_control_o(leaves)
  );

  initial begin
    control = '0;
    lfsr = 32'h8b_a0_3201;
    trace_fd = 0;
    if ($value$plusargs("TRACE=%s", trace_path)) begin
      trace_fd = $fopen(trace_path, "w");
      if (!trace_fd) $fatal(1, "cannot open trace");
    end
    for (operation = 0; operation < TARGET; operation = operation + 1) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      control = lfsr[WIDTH-1:0] ^ operation[WIDTH-1:0];
      #1;
      for (leaf = 0; leaf < LEAVES; leaf = leaf + 1) begin
        if (leaves[leaf*WIDTH +: WIDTH] !== control)
          $fatal(1, "broadcast mismatch operation=%0d leaf=%0d expected=%h actual=%h",
                 operation, leaf, control, leaves[leaf*WIDTH +: WIDTH]);
      end
      if (trace_fd) $fwrite(trace_fd, "%03h %088h\n", control, leaves);
    end
    if (trace_fd) $fclose(trace_fd);
    $display("L5_REV8B_A_BROADCAST_E1_PASS operations=%0d leaves=%0d width=%0d",
             TARGET, LEAVES, WIDTH);
    $finish;
  end
endmodule

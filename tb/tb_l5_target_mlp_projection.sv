`timescale 1ns/1ps
module tb_l5_target_mlp_projection;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  logic in_valid, in_ready, out_valid, out_ready;
  logic [255:0] a;
  logic [511:0] b;
  logic [16383:0] accumulator, array_out;
  logic [4:0] flags, flags_or;
  logic [31:0] accepted, completed;
  logic [15:0] weights [0:13762559];
  logic [31:0] input_vector [0:1535], expected [0:8959];
  logic [286719:0] result;
  integer cycles, mode;

  always #5 clk = ~clk;
  always @(posedge clk)
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;

  bf16_outer_product_array #(.ROWS(16), .COLS(32)) matrix(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(in_valid), .in_ready_o(in_ready),
    .a_i(a), .b_i(b), .acc_i(accumulator),
    .out_valid_o(out_valid), .out_ready_i(out_ready),
    .acc_o(array_out), .exception_flags_o(flags),
    .accepted_steps_o(accepted), .completed_steps_o(completed)
  );

  function automatic [15:0] to_bf16(input logic [31:0] value);
    logic [31:0] rounded;
    begin
      rounded = value + 32'h00007fff + value[16];
      to_bf16 = rounded[31:16];
    end
  endfunction

  function automatic [63:0] hash8960(input logic [286719:0] data);
    logic [63:0] value;
    begin
      value = 64'hcbf29ce484222325;
      for (int lane = 0; lane < 8960; lane++)
        value = (value ^ {32'd0, data[lane * 32 +: 32]}) * 64'h100000001b3;
      hash8960 = value;
    end
  endfunction

  task automatic clear512(output logic [16383:0] bus);
    for (int i = 0; i < 512; i++) bus[i * 32 +: 32] = 32'd0;
  endtask

  initial begin
    logic [16383:0] current;
    clk = 0;
    rst_n = 0;
    cycles = 0;
    in_valid = 0;
    out_ready = 1;
    a = '0;
    b = '0;
    clear512(accumulator);
    flags_or = '0;
    if (!$value$plusargs("MODE=%d", mode)) mode = 0;
    if (mode == 0) begin
      $readmemh("work/results/l5_target_gate_up/vectors/gate_weights_bf16.memh", weights);
      $readmemh("work/results/l5_target_gate_up/vectors/gate.memh", expected);
    end else begin
      $readmemh("work/results/l5_target_gate_up/vectors/up_weights_bf16.memh", weights);
      $readmemh("work/results/l5_target_gate_up/vectors/up.memh", expected);
    end
    $readmemh("work/results/l5_target_norm2/vectors/norm2.memh", input_vector);
    repeat (3) @(posedge clk);
    rst_n = 1;
    for (int tile = 0; tile < 280; tile++) begin
      clear512(current);
      for (int k = 0; k < 1536; k++) begin
        a = '0;
        b = '0;
        a[15:0] = to_bf16(input_vector[k]);
        for (int column = 0; column < 32; column++)
          b[column * 16 +: 16] = weights[k * 8960 + tile * 32 + column];
        accumulator = current;
        @(negedge clk);
        in_valid = 1;
        do @(posedge clk); while (!in_ready);
        @(negedge clk);
        in_valid = 0;
        do @(posedge clk); while (!(out_valid && out_ready));
        @(negedge clk);
        current = array_out;
        flags_or |= flags;
      end
      for (int column = 0; column < 32; column++)
        result[(tile * 32 + column) * 32 +: 32] = current[column * 32 +: 32];
    end
    for (int lane = 0; lane < 8960; lane++)
      if (result[lane * 32 +: 32] !== expected[lane])
        $fatal(1, "target MLP projection mismatch mode=%0d lane=%0d", mode, lane);
    if (accepted != 430080 || completed != 430080 || flags_or[4:1] != 0)
      $fatal(1, "target MLP projection accounting mode=%0d accepted=%0d completed=%0d flags=%h",
             mode, accepted, completed, flags_or);
    $display(
      "L5_TARGET_MLP_PROJECTION_PASS mode=%0d shape=1536x8960 array_steps=430080 cycles=%0d output_fnv64=%016h",
      mode, cycles, hash8960(result)
    );
    $finish;
  end

  initial begin
    repeat (2000000) @(posedge clk);
    $fatal(1, "target MLP projection timeout");
  end
endmodule

// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Each memory row is {flags32, bf16_widened_binary32, input_fp32}.
module tb_fp32_to_bf16_candidate;
  parameter integer COUNT = 1;

  logic [31:0] fp32_i;
  logic [15:0] bf16_o;
  logic [4:0] exception_flags_o;
  logic [95:0] vectors [0:COUNT-1];
  integer output_file;
  string vectors_path, outputs_path;

  fp32_to_bf16_rne_candidate dut (
    .fp32_i, .bf16_o, .exception_flags_o
  );

  initial begin
    fp32_i = 0;
    if (COUNT < 1) $fatal(1, "COUNT must be positive");
    if (!$value$plusargs("VECTORS=%s", vectors_path))
      $fatal(1, "missing +VECTORS=<memory file>");
    if (!$value$plusargs("OUTPUTS=%s", outputs_path))
      $fatal(1, "missing +OUTPUTS=<output file>");
    $readmemh(vectors_path, vectors);
    output_file = $fopen(outputs_path, "w");
    if (!output_file) $fatal(1, "cannot open outputs: %s", outputs_path);
    for (integer i = 0; i < COUNT; i = i + 1) begin
      fp32_i = vectors[i][31:0];
      #1;
      if ({bf16_o, 16'd0} !== vectors[i][63:32] ||
          {27'd0, exception_flags_o} !== vectors[i][95:64])
        $fatal(1, "conversion mismatch index=%0d input=%08h got=%08h flags=%08h expected=%08h flags=%08h",
          i, fp32_i, {bf16_o, 16'd0}, {27'd0, exception_flags_o},
          vectors[i][63:32], vectors[i][95:64]);
      $fdisplay(output_file, "%08h %08h", {bf16_o, 16'd0},
        {27'd0, exception_flags_o});
    end
    $fclose(output_file);
    $display("BF16_CONVERTER_PASS vectors=%0d", COUNT);
    $finish;
  end
endmodule

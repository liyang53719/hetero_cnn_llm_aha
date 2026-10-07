// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module tb_rope_hardware_oracle;
  parameter integer COUNT = 1;
  parameter integer PIPE = 0;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;
  logic iv, ir, ov, ready;
  logic [31:0] even_i, odd_i, cos_i, sin_i, even_o, odd_o;
  logic [4:0] flags;
  logic [31:0] accepted, completed;
  logic [199:0] vectors [0:COUNT-1];
  integer cycles = 0, seen = 0, output_file, stalls = 0;
  logic held_valid = 0;
  logic [68:0] held;
  string vectors_path, outputs_path;
  if (PIPE == 0) begin : comb
    fp32_rope_pair dut(.clk_i(clk), .rst_ni(rst_n), .in_valid_i(iv), .in_ready_o(ir),
      .even_i, .odd_i, .cos_i, .sin_i, .out_valid_o(ov), .out_ready_i(ready),
      .even_o, .odd_o, .exception_flags_o(flags), .accepted_pairs_o(accepted), .completed_pairs_o(completed));
  end else begin : pipe
    fp32_rope_pair_pipe dut(.clk_i(clk), .rst_ni(rst_n), .in_valid_i(iv), .in_ready_o(ir),
      .even_i, .odd_i, .cos_i, .sin_i, .out_valid_o(ov), .out_ready_i(ready),
      .even_o, .odd_o, .exception_flags_o(flags));
    assign accepted = 0;
    assign completed = 0;
  end
  // Deterministic multi-cycle output stalls; input gaps use a different period.
  assign ready = (cycles % 13) >= 4;
  always @(posedge clk) begin
    if (rst_n) begin
      cycles <= cycles + 1;
      if (held_valid && (!ov || {flags, odd_o, even_o} !== held))
        $fatal(1, "unstable output under backpressure");
      held_valid <= ov && !ready;
      if (ov && !ready) begin
        held <= {flags, odd_o, even_o};
        stalls <= stalls + 1;
      end
      if (ov && ready) begin
        if (seen >= COUNT) $fatal(1, "extra output");
        if ({3'd0, flags, odd_o, even_o} !== vectors[seen][199:128])
          $fatal(1, "pair mismatch index=%0d got=%08h %08h flags=%02h expected=%018h", seen, even_o, odd_o, flags, vectors[seen][199:128]);
        $fdisplay(output_file, "%08h %08h %02h", even_o, odd_o, flags);
        seen <= seen + 1;
      end
    end
  end
  initial begin
    iv=0; even_i=0; odd_i=0; cos_i=0; sin_i=0;
    if (!$value$plusargs("VECTORS=%s", vectors_path)) $fatal(1,"missing vectors");
    if (!$value$plusargs("OUTPUTS=%s", outputs_path)) $fatal(1,"missing outputs");
    $readmemh(vectors_path, vectors);
    output_file=$fopen(outputs_path,"w");
    if (!output_file) $fatal(1,"cannot open outputs");
    repeat(3) @(negedge clk);
    rst_n=1;
    for(integer i=0;i<COUNT;i=i+1) begin
      @(negedge clk);
      iv=0;
      if (i%17==3) repeat(2) @(negedge clk);
      {sin_i,cos_i,odd_i,even_i}=vectors[i][127:0]; iv=1;
      do @(posedge clk); while(!ir);
    end
    @(negedge clk); iv=0;
    wait(seen==COUNT);
    // Drain for duplicate/late outputs, not only until the last expected beat.
    repeat(20) @(negedge clk);
    if (PIPE==0 && (accepted!=COUNT || completed!=COUNT)) $fatal(1,"counter mismatch");
    if (stalls==0) $fatal(1,"backpressure not exercised");
    $fclose(output_file);
    $display("ROPE_HARDWARE_ORACLE_PASS pipe=%0d pairs=%0d cycles=%0d stalls=%0d",PIPE,COUNT,cycles,stalls);
    $finish;
  end
  initial begin
    repeat(COUNT*40+1000) @(posedge clk);
    $fatal(1,"timeout");
  end
endmodule

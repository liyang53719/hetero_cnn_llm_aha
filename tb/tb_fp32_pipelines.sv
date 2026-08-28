`timescale 1ns/1ps
module tb_fp32_pipelines;
  localparam integer MAX_CASES = 512;
  logic clock, reset;
  logic miv, mir, mov, mor, aiv, air, aov, aor;
  logic [31:0] mx, my, mo, ax, ay, ao;
  logic [11:0] mt, mot, at, aot;
  logic [4:0] mf, af;
  logic [31:0] mxm [0:MAX_CASES-1], mym [0:MAX_CASES-1];
  logic [31:0] mem [0:MAX_CASES-1], axm [0:MAX_CASES-1];
  logic [31:0] aym [0:MAX_CASES-1], aem [0:MAX_CASES-1];
  integer mc, ac, mi, ai, md, ad, fd, rc;
  logic [31:0] lfsr, mhold, ahold;
  logic [11:0] mholdt, aholdt;
  logic mst, ast;

  always #0.5 clock = ~clock;

  HeteroFP32MulPipeTag12 mul_dut(
    .clock, .reset, .io_inValid(miv), .io_inReady(mir),
    .io_x(mx), .io_y(my), .io_userIn(mt),
    .io_outValid(mov), .io_outReady(mor), .io_out(mo),
    .io_exceptionFlags(mf), .io_userOut(mot)
  );
  HeteroFP32AddPipeTag12 add_dut(
    .clock, .reset, .io_inValid(aiv), .io_inReady(air),
    .io_x(ax), .io_y(ay), .io_userIn(at),
    .io_outValid(aov), .io_outReady(aor), .io_out(ao),
    .io_exceptionFlags(af), .io_userOut(aot)
  );

  assign miv = !reset && mi < mc;
  assign mx = mxm[mi];
  assign my = mym[mi];
  assign mt = mi[11:0];
  assign aiv = !reset && ai < ac;
  assign ax = axm[ai];
  assign ay = aym[ai];
  assign at = ai[11:0];
  assign mor = lfsr[0] || lfsr[3];
  assign aor = lfsr[1] || lfsr[4];

  initial begin
    clock = 0;
    reset = 1;
    mc = 0;
    fd = $fopen("tests/vectors/fp32_mul_pipe_vectors.txt", "r");
    if (fd == 0) $fatal(1, "mul vectors");
    while (!$feof(fd) && mc < MAX_CASES) begin
      rc = $fscanf(fd, "%h %h %h\n", mxm[mc], mym[mc], mem[mc]);
      if (rc == 3) mc = mc + 1;
    end
    $fclose(fd);
    ac = 0;
    fd = $fopen("tests/vectors/fp32_add_pipe_vectors.txt", "r");
    if (fd == 0) $fatal(1, "add vectors");
    while (!$feof(fd) && ac < MAX_CASES) begin
      rc = $fscanf(fd, "%h %h %h\n", axm[ac], aym[ac], aem[ac]);
      if (rc == 3) ac = ac + 1;
    end
    $fclose(fd);
    if (mc != MAX_CASES || ac != MAX_CASES) $fatal(1, "vector count");
    repeat (6) @(posedge clock);
    reset <= 0;
  end

  initial begin
    mi = 0; ai = 0; md = 0; ad = 0;
    lfsr = 32'h1ace_b00c;
    mst = 0; ast = 0;
    wait (!reset);
    while (md < mc || ad < ac) begin
      @(posedge clock);
      lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      if (miv && mir) mi <= mi + 1;
      if (aiv && air) ai <= ai + 1;
      if (mov && !mor) begin
        if (mst && (mo !== mhold || mot !== mholdt)) $fatal(1, "mul stall");
        mhold <= mo; mholdt <= mot; mst <= 1;
      end else mst <= 0;
      if (aov && !aor) begin
        if (ast && (ao !== ahold || aot !== aholdt)) $fatal(1, "add stall");
        ahold <= ao; aholdt <= aot; ast <= 1;
      end else ast <= 0;
      if (mov && mor) begin
        if (int'(mot) >= mc || mo !== mem[mot[8:0]]) $fatal(1, "mul mismatch tag=%0d", mot);
        md <= md + 1;
      end
      if (aov && aor) begin
        if (int'(aot) >= ac || ao !== aem[aot[8:0]]) $fatal(1, "add mismatch tag=%0d", aot);
        ad <= ad + 1;
      end
    end
    repeat (4) @(posedge clock);
    $display("FP32_PIPELINE_PASS mul=%0d add=%0d", md, ad);
    $finish;
  end

  initial begin
    repeat (20000) @(posedge clock);
    $fatal(1, "timeout");
  end
endmodule

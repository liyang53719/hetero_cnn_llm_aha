`timescale 1ns/1ps
// Directed/exhaustive smoke for the generated official Gemmini MacUnit.
// The DUT source is taken from the pinned Chipyard collateral, not copied
// into this project.
module tb_official_gemmini_mac_unit;
  logic [7:0] a;
  logic [7:0] b;
  logic [31:0] c;
  wire [19:0] d;
  integer ai, bi, ci;
  integer signed_a, signed_b, signed_c;
  integer expected, got, wrapped;
  integer checks;

  MacUnit dut (
    .io_in_a(a), .io_in_b(b), .io_in_c(c), .io_out_d(d)
  );

  initial begin
    checks = 0;
    for (ci = 0; ci < 5; ci = ci + 1) begin
      case (ci)
        0: c = 32'h00000000;
        1: c = 32'h00000001;
        2: c = 32'hffffffff;
        3: c = 32'h0007ffff;
        default: c = 32'hfff80000;
      endcase
      for (ai = -128; ai < 128; ai = ai + 1) begin
        for (bi = -128; bi < 128; bi = bi + 1) begin
          a = ai[7:0];
          b = bi[7:0];
          #1;
          signed_a = ai;
          signed_b = bi;
          signed_c = $signed(c[19:0]);
          expected = signed_a * signed_b + signed_c;
          wrapped = expected & ((1 << 20) - 1);
          if (wrapped >= (1 << 19)) wrapped = wrapped - (1 << 20);
          got = $signed(d);
          if (got !== wrapped) begin
            $fatal(1, "official MacUnit mismatch a=%0d b=%0d c=%0d got=%0d expected=%0d",
                   signed_a, signed_b, signed_c, got, wrapped);
          end
          checks = checks + 1;
        end
      end
    end
    $display("OFFICIAL_GEMMINI_MACUNIT_PASS checks=%0d", checks);
    $finish;
  end
endmodule

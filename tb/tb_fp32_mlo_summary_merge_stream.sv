`timescale 1ns/1ps
module tb_fp32_mlo_summary_merge_stream;
  logic clk, rst_n;
  logic hv, hr, bv, br, hov, hor, bov, bor, last_i, last_o;
  logic [31:0] ma, la, mb, lb, mo, lo;
  logic [127:0] oa, ob, oo;
  integer fd, rc, count, header_stalls, beat_stalls, stream_beats;
  logic [31:0] a0, a1, a2, a3, b0, b1, b2, b3;
  logic [31:0] em, el, e0, e1, e2, e3;
  logic [31:0] rng;

  always #5 clk = ~clk;

  fp32_mlo_summary_merge_stream #(.LANES(4)) dut(
    .clk_i(clk), .rst_ni(rst_n),
    .header_valid_i(hv), .header_ready_o(hr),
    .ma_i(ma), .la_i(la), .mb_i(mb), .lb_i(lb),
    .beat_valid_i(bv), .beat_ready_o(br),
    .oa_i(oa), .ob_i(ob), .beat_last_i(last_i),
    .header_valid_o(hov), .header_ready_i(hor), .m_o(mo), .l_o(lo),
    .beat_valid_o(bov), .beat_ready_i(bor), .o_o(oo), .beat_last_o(last_o)
  );

  task automatic random_delay(input integer maximum);
    integer delay_cycles;
    begin
      rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
      delay_cycles = rng % (maximum + 1);
      repeat (delay_cycles) @(posedge clk);
    end
  endtask

  initial begin
    logic [63:0] held_header;
    logic [128:0] held_beat;
    clk = 0;
    rst_n = 0;
    hv = 0;
    bv = 0;
    hor = 0;
    bor = 0;
    last_i = 0;
    count = 0;
    header_stalls = 0;
    beat_stalls = 0;
    stream_beats = 0;
    rng = 32'hb128_5eed;
    fd = $fopen("tests/vectors/fp32_mlo_merge_vectors.txt", "r");
    if (fd == 0) $fatal(1, "cannot open merge vectors");
    repeat (4) @(posedge clk);
    rst_n = 1;

    while (!$feof(fd)) begin
      rc = $fscanf(fd,
        "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h\n",
        ma, la, mb, lb, a0, a1, a2, a3, b0, b1, b2, b3,
        em, el, e0, e1, e2, e3);
      if (rc == 18) begin
        oa = {a3, a2, a1, a0};
        ob = {b3, b2, b1, b0};
        random_delay(3);
        @(negedge clk);
        hv = 1;
        do @(posedge clk); while (!hr);
        @(negedge clk);
        hv = 0;
        do @(posedge clk); while (!hov);
        held_header = {mo, lo};
        if (mo !== em || lo !== el)
          $fatal(1,
            "header case=%0d ma=%08x la=%08x mb=%08x lb=%08x mo=%08x em=%08x lo=%08x el=%08x",
            count, ma, la, mb, lb, mo, em, lo, el);
        random_delay(4);
        if (!hov || {mo, lo} !== held_header)
          $fatal(1, "header unstable case=%0d", count);
        header_stalls = header_stalls + 1;
        @(negedge clk);
        hor = 1;
        @(posedge clk);
        @(negedge clk);
        hor = 0;

        random_delay(3);
        @(negedge clk);
        bv = 1;
        last_i = 1;
        do @(posedge clk); while (!br);
        @(negedge clk);
        bv = 0;
        last_i = 0;
        do @(posedge clk); while (!bov);
        held_beat = {last_o, oo};
        if (oo !== {e3, e2, e1, e0} || !last_o)
          $fatal(1,
            "beat case=%0d oo=%032x expected=%032x last=%0d",
            count, oo, {e3, e2, e1, e0}, last_o);
        random_delay(5);
        if (!bov || {last_o, oo} !== held_beat)
          $fatal(1, "beat unstable case=%0d", count);
        beat_stalls = beat_stalls + 1;
        @(negedge clk);
        bor = 1;
        @(posedge clk);
        @(negedge clk);
        bor = 0;
        count = count + 1;
      end
    end
    if (count != 132) $fatal(1, "vector count=%0d", count);

    // One nontrivial coefficient header followed by a complete 128-lane
    // summary represented as 32 independently backpressured 4-lane beats.
    ma = 32'hc06640f5; la = 32'h42281225;
    mb = 32'h401e816d; lb = 32'h435efd06;
    em = 32'h401e816d; el = 32'h435f15c8;
    oa = {32'hc18ef9ce, 32'h41d4aa05, 32'hc173e7c3, 32'hc2739216};
    ob = {32'h42767f70, 32'hc22d4652, 32'hc23f4244, 32'h41277666};
    {e3, e2, e1, e0} = {32'h42765552, 32'hc22d07ac, 32'hc23f6631, 32'h41253860};
    @(negedge clk);
    hv = 1;
    do @(posedge clk); while (!hr);
    @(negedge clk);
    hv = 0;
    do @(posedge clk); while (!hov);
    if (mo !== em || lo !== el) $fatal(1, "stream128 header");
    random_delay(3);
    @(negedge clk);
    hor = 1;
    @(posedge clk);
    @(negedge clk);
    hor = 0;
    for (integer beat = 0; beat < 32; beat = beat + 1) begin
      random_delay(3);
      @(negedge clk);
      bv = 1;
      last_i = beat == 31;
      do @(posedge clk); while (!br);
      @(negedge clk);
      bv = 0;
      last_i = 0;
      do @(posedge clk); while (!bov);
      held_beat = {last_o, oo};
      if (oo !== {e3, e2, e1, e0} || last_o !== (beat == 31))
        $fatal(1, "stream128 beat=%0d", beat);
      random_delay(5);
      if (!bov || {last_o, oo} !== held_beat)
        $fatal(1, "stream128 unstable beat=%0d", beat);
      @(negedge clk);
      bor = 1;
      @(posedge clk);
      @(negedge clk);
      bor = 0;
      stream_beats = stream_beats + 1;
    end
    $display("BLOCK128_MLO_VECTOR_PASS cases=%0d stream_beats=%0d header_stalls=%0d beat_stalls=%0d",
      count, stream_beats, header_stalls, beat_stalls);
    $finish;
  end

  initial begin
    repeat (500000) @(posedge clk);
    $fatal(1, "timeout");
  end
endmodule

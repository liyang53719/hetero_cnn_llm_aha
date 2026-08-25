`timescale 1ns/1ps
module tb_shared_l2_fabric;
  localparam integer ADDR_W = 10;
  localparam integer DATA_W = 512;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;
  logic [1:0] rd_valid, rd_ready;
  logic [2*ADDR_W-1:0] rd_addr;
  logic [1:0] resp_valid, resp_ready;
  logic [2*DATA_W-1:0] resp_data;
  logic wr_valid, wr_ready;
  logic [ADDR_W-1:0] wr_addr;
  logic [DATA_W-1:0] wr_data;
  logic [DATA_W/8-1:0] wr_be;
  logic [DATA_W-1:0] model [0:(1<<ADDR_W)-1];
  logic pending0, pending1;
  logic [DATA_W-1:0] expect0, expect1;
  logic fire0_d, fire1_d, firew_d;
  integer i, seed;
  integer accepted;

  shared_l2_fabric #(.DATA_W(DATA_W), .ADDR_W(ADDR_W), .BANKS(16)) dut (
    .clk_i(clk), .rst_ni(rst_n),
    .rd_valid_i(rd_valid), .rd_ready_o(rd_ready), .rd_addr_i(rd_addr),
    .rd_resp_valid_o(resp_valid), .rd_resp_ready_i(resp_ready),
    .rd_data_o(resp_data), .wr_valid_i(wr_valid), .wr_ready_o(wr_ready),
    .wr_addr_i(wr_addr), .wr_data_i(wr_data), .wr_be_i(wr_be)
  );

  always @(negedge clk) begin
    if (rst_n) begin
      if (pending0) begin
        if (!resp_valid[0] || resp_data[0*DATA_W +: DATA_W] !== expect0) begin
          $display("DEBUG0 got=%h expect=%h rdaddr=%0d rd_ready=%b resp_valid=%b", resp_data[0*DATA_W +: DATA_W], expect0, rd_addr[0 +: ADDR_W], rd_ready, resp_valid);
          $fatal(1, "read0 mismatch transaction=%0d", accepted);
        end
        pending0 = 1'b0;
      end
      if (pending1) begin
        if (!resp_valid[1] || resp_data[1*DATA_W +: DATA_W] !== expect1) begin
          $display("DEBUG1 got=%h expect=%h rdaddr=%0d rd_ready=%b resp_valid=%b", resp_data[1*DATA_W +: DATA_W], expect1, rd_addr[ADDR_W +: ADDR_W], rd_ready, resp_valid);
          $fatal(1, "read1 mismatch transaction=%0d", accepted);
        end
        pending1 = 1'b0;
      end
    end
  end

  initial begin
    rd_valid = 0; rd_addr = 0; resp_ready = 2'b11;
    wr_valid = 0; wr_addr = 0; wr_data = 0; wr_be = '1;
    pending0 = 0; pending1 = 0; accepted = 0; seed = 32'h1234_5678;
    for (i = 0; i < (1<<ADDR_W); i++) model[i] = '0;
    repeat (3) @(posedge clk);
    rst_n = 1'b1;

    for (i = 0; i < 10000; i++) begin
      @(negedge clk);
      rd_valid = 2'b00;
      wr_valid = 1'b0;
      // Do not issue a new read for a client while its registered response is pending.
      if (!pending0 && !pending1 && (($urandom(seed) % 4) == 0)) begin
        wr_valid = 1'b1;
        wr_addr = $urandom(seed) & ((1<<ADDR_W)-1);
        wr_data = {$urandom(seed), $urandom(seed), $urandom(seed), $urandom(seed),
                   $urandom(seed), $urandom(seed), $urandom(seed), $urandom(seed),
                   $urandom(seed), $urandom(seed), $urandom(seed), $urandom(seed),
                   $urandom(seed), $urandom(seed), $urandom(seed), $urandom(seed)};
        wr_be = '1;
      end else begin
        if (!pending0) begin
          rd_valid[0] = 1'b1;
          rd_addr[0 +: ADDR_W] = $urandom(seed) & ((1<<ADDR_W)-1);
        end
        if (!pending1) begin
          rd_valid[1] = 1'b1;
          if (($urandom(seed) % 3) == 0)
            rd_addr[ADDR_W +: ADDR_W] = rd_addr[0 +: ADDR_W];
          else
            rd_addr[ADDR_W +: ADDR_W] = $urandom(seed) & ((1<<ADDR_W)-1);
        end
      end
      #1;
      firew_d = wr_valid && wr_ready;
      fire0_d = rd_valid[0] && rd_ready[0];
      fire1_d = rd_valid[1] && rd_ready[1];
      if (firew_d) begin
        model[wr_addr] = wr_data;
        accepted = accepted + 1;
      end
      if (fire0_d) begin
        expect0 = model[rd_addr[0 +: ADDR_W]];
        pending0 = 1'b1;
        accepted = accepted + 1;
      end
      if (fire1_d) begin
        expect1 = model[rd_addr[ADDR_W +: ADDR_W]];
        pending1 = 1'b1;
        accepted = accepted + 1;
      end
      @(posedge clk);
    end
    wait (!pending0 && !pending1);
    $display("TB_SHARED_L2_PASS transactions=%0d", accepted);
    $finish;
  end

  initial begin
    repeat (30000) @(posedge clk);
    $fatal(1, "shared L2 timeout");
  end
endmodule

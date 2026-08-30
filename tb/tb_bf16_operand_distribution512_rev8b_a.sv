`timescale 1ns/1ps
module tb_bf16_operand_distribution512_rev8b_a;
  localparam integer TARGET=10000;
  logic [255:0] a;
  logic [511:0] b;
  wire [8191:0] lane_a,lane_b;
  logic [31:0] lfsr;
  integer operation,row,col;

  bf16_operand_distribution512_rev8b_a_candidate dut(
    .a_i(a), .b_i(b), .lane_a_o(lane_a), .lane_b_o(lane_b)
  );

  initial begin
    a='0;b='0;lfsr=32'h8ba0_5120;
    for(operation=0;operation<TARGET;operation=operation+1)begin
      lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
      for(integer word=0;word<16;word=word+1)a[word*16+:16]=lfsr[15:0]^(operation+word);
      for(integer word=0;word<32;word=word+1)b[word*16+:16]=lfsr[31:16]^(operation+word*3);
      #1;
      for(row=0;row<16;row=row+1)for(col=0;col<32;col=col+1)begin
        if(lane_a[(row*32+col)*16+:16]!==a[row*16+:16])$fatal(1,"A mismatch op=%0d row=%0d col=%0d",operation,row,col);
        if(lane_b[(row*32+col)*16+:16]!==b[col*16+:16])$fatal(1,"B mismatch op=%0d row=%0d col=%0d",operation,row,col);
      end
    end
    $display("L5_REV8B_A_OPERAND_DISTRIBUTION_E1_PASS operations=%0d lanes=512",TARGET);
    $finish;
  end
endmodule

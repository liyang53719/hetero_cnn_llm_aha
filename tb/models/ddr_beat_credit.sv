// Test-only bandwidth ceiling: 64-byte physical beats, bounded 128-byte burst.
`timescale 1ns/1ps
module ddr_beat_credit #(parameter integer BYTES_PER_CYCLE=50)(
 input logic clk_i,rst_ni,valid_i,fire_i,output logic allow_o,
 output logic[63:0]bytes_o,throttled_cycles_o
);
 integer credit_q,next_credit;
 assign allow_o=credit_q>=64;
 always_comb begin
  next_credit=credit_q+BYTES_PER_CYCLE-(fire_i?64:0);
  if(next_credit>128)next_credit=128;
 end
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin credit_q<=0;bytes_o<=0;throttled_cycles_o<=0;end
  else begin
   assert(!fire_i||allow_o)else $fatal(1,"DDR beat without credit");
   credit_q<=next_credit;
   if(fire_i)bytes_o<=bytes_o+64;
   if(valid_i&&!allow_o)throttled_cycles_o<=throttled_cycles_o+1;
  end
 end
endmodule

// SPDX-License-Identifier: Apache-2.0
// Internal16-element residual stream: A FP32, B BF16 or FP32, output FP32.
// Tags are frontend-assigned transaction/beat correlation tags, not stream-role IDs.
// BF16 B packets contain16 elements in the low256 bits; memory gearbox is external.
module fp32_residual_stream(
 input logic clk_i,rst_ni,
 input logic a_valid_i,output logic a_ready_o,input logic[511:0]a_data_i,
 input logic[15:0]a_tag_i,a_keep_i,input logic a_last_i,
 input logic b_valid_i,output logic b_ready_o,input logic[511:0]b_data_i,
 input logic b_bf16_i,input logic[15:0]b_tag_i,b_keep_i,input logic b_last_i,
 output logic out_valid_o,input logic out_ready_i,output logic[511:0]out_data_o,
 output logic[15:0]out_tag_o,out_keep_o,output logic out_last_o,
 output logic[4:0]out_flags_o,output logic[7:0]out_status_o,output logic fault_o
);
 logic af,bf,ofull,bshort,alast,blast;
 logic[511:0]a,b,va,vb,sum;logic[15:0]at,bt,ak,bk;logic[4:0]flags;
 logic pair_fire,pair_legal;
 assign pair_legal=(at==bt)&&(ak==bk)&&(alast==blast);
 assign pair_fire=af&&bf&&(!ofull||out_ready_i)&&!fault_o;
 assign a_ready_o=!fault_o&&(!af||(pair_fire&&pair_legal));
 assign b_ready_o=!fault_o&&(!bf||(pair_fire&&pair_legal));
 assign out_valid_o=ofull;
 always_comb begin
  va=0;vb=0;
  for(integer i=0;i<16;i++)begin
   if(ak[i])va[i*32+:32]=a[i*32+:32];
   if(bk[i])vb[i*32+:32]=bshort?{b[i*16+:16],16'b0}:b[i*32+:32];
  end
 end
 fp32_vector_alu #(.LANES(16)) alu(.op_i(1'b0),.a_i(va),.b_i(vb),.out_o(sum),.exception_flags_o(flags));
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin
   af<=0;bf<=0;ofull<=0;fault_o<=0;a<=0;b<=0;at<=0;bt<=0;ak<=0;bk<=0;alast<=0;blast<=0;bshort<=0;
   out_data_o<=0;out_tag_o<=0;out_keep_o<=0;out_last_o<=0;out_flags_o<=0;out_status_o<=0;
  end else begin
   if(out_valid_o&&out_ready_i)ofull<=0;
   if(pair_fire)begin
    af<=0;bf<=0;ofull<=1;out_tag_o<=at;out_keep_o<=ak;out_last_o<=alast;
    out_data_o<=pair_legal?sum:512'd0;out_flags_o<=pair_legal?flags:5'd0;
    out_status_o<=pair_legal?8'd0:8'd7;if(!pair_legal)fault_o<=1;
   end
   if(a_valid_i&&a_ready_o)begin af<=1;a<=a_data_i;at<=a_tag_i;ak<=a_keep_i;alast<=a_last_i;end
   if(b_valid_i&&b_ready_o)begin bf<=1;b<=b_data_i;bt<=b_tag_i;bk<=b_keep_i;blast<=b_last_i;bshort<=b_bf16_i;end
  end
 end
endmodule

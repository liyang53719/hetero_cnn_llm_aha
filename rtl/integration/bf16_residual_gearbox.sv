// SPDX-License-Identifier: Apache-2.0
// One512-bit BF16 memory beat -> up to two16-element residual input chunks.
// Fixed64-byte payload storage. Chunk indices are internal32-bit ordinals.
module bf16_residual_gearbox(
 input logic clk_i,rst_ni,
 input logic in_valid_i,output logic in_ready_o,input logic[511:0]in_data_i,
 input logic[31:0]in_keep_i,in_first_chunk_i,input logic in_last_i,
 output logic out_valid_o,input logic out_ready_i,output logic[511:0]out_data_o,
 output logic[15:0]out_keep_o,output logic[31:0]out_chunk_o,output logic out_last_o,
 output logic[7:0]out_status_o,output logic[63:0]accepted_beats_o,emitted_chunks_o
);
 logic full_q,half_q,last_q,last_chunk;logic[511:0]data_q;
 logic[31:0]keep_q,first_q;logic[7:0]status_q;
 assign last_chunk=half_q||keep_q[31:16]==0||status_q!=0;
 assign in_ready_o=rst_ni&&(!full_q||(out_ready_i&&last_chunk));
 assign out_valid_o=full_q;
 assign out_status_o=status_q;
 assign out_data_o=status_q!=0?512'd0:{256'd0,(half_q?data_q[511:256]:data_q[255:0])};
 assign out_keep_o=status_q!=0?16'd0:(half_q?keep_q[31:16]:keep_q[15:0]);
 assign out_chunk_o=first_q+(status_q==0?32'(half_q):32'd0);
 assign out_last_o=last_q&&last_chunk;
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin
   full_q<=0;half_q<=0;last_q<=0;data_q<=0;keep_q<=0;first_q<=0;status_q<=0;accepted_beats_o<=0;emitted_chunks_o<=0;
  end else begin
   if(out_valid_o&&out_ready_i)begin
    emitted_chunks_o<=emitted_chunks_o+1;
    if(last_chunk)full_q<=0;else half_q<=1;
   end
   if(in_valid_i&&in_ready_o)begin
    full_q<=1;data_q<=in_data_i;keep_q<=in_keep_i;first_q<=in_first_chunk_i;last_q<=in_last_i;
    half_q<=in_keep_i[15:0]==0&&in_keep_i[31:16]!=0;
    status_q<=(in_keep_i==0||(in_first_chunk_i==32'hffffffff&&in_keep_i[31:16]!=0))?8'd5:8'd0;
    accepted_beats_o<=accepted_beats_o+1;
   end
  end
 end
endmodule

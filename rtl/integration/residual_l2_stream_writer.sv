// SPDX-License-Identifier: Apache-2.0
`default_nettype none
// FP32 residual chunks -> masked512-bit SRAM writes. Completion follows final grant.
module residual_l2_stream_writer #(
 parameter integer ADDR_W=15,parameter logic[63:0]SRAM_BYTES=64'd1572864
)(
 input logic clk_i,rst_ni,request_valid_i,output logic request_ready_o,
 input logic[63:0]destination_i,input logic[31:0]elements_i,
 input logic in_valid_i,output logic in_ready_o,input logic[511:0]in_data_i,
 input logic[15:0]in_keep_i,input logic[31:0]in_chunk_i,input logic in_last_i,input logic[7:0]in_status_i,
 output logic wr_valid_o,input logic wr_ready_i,output logic[ADDR_W-1:0]wr_addr_o,
 output logic[511:0]wr_data_o,output logic[63:0]wr_be_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[7:0]status_o,
 output logic[63:0]received_chunks_o,written_beats_o,written_payload_bytes_o
);
 typedef enum logic[1:0]{IDLE,INPUT_PACKET,WRITE,DONE}state_t;
 state_t state_q;logic[63:0]address_q;logic[31:0]remaining_q,chunk_q;
 logic[511:0]data_q;logic[15:0]keep_q,expected_keep;
 logic legal;logic[64:0]required_bytes,end_address;
 assign required_bytes=((65'(elements_i)+15)>>4)<<6;
 assign end_address={1'b0,destination_i}+required_bytes;
 assign legal=elements_i!=0&&destination_i[5:0]==0&&end_address<={1'b0,SRAM_BYTES}&&end_address<=(65'd1<<(ADDR_W+6));
 assign request_ready_o=rst_ni&&state_q==IDLE;
 assign in_ready_o=rst_ni&&state_q==INPUT_PACKET;
 assign wr_valid_o=state_q==WRITE;assign wr_addr_o=ADDR_W'(address_q>>6);
 assign completion_valid_o=state_q==DONE;
 always_comb begin
  expected_keep=0;wr_data_o=0;wr_be_o=0;
  for(integer i=0;i<16;i++)begin
   if(i<remaining_q)expected_keep[i]=1;
   if(keep_q[i])begin wr_data_o[i*32+:32]=data_q[i*32+:32];wr_be_o[i*4+:4]=4'hf;end
  end
 end
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=IDLE;address_q<=0;remaining_q<=0;chunk_q<=0;data_q<=0;keep_q<=0;status_o<=0;received_chunks_o<=0;written_beats_o<=0;written_payload_bytes_o<=0;end
  else case(state_q)
   IDLE:if(request_valid_i&&request_ready_o)begin
    address_q<=destination_i;remaining_q<=elements_i;chunk_q<=0;status_o<=legal?0:5;
    received_chunks_o<=0;written_beats_o<=0;written_payload_bytes_o<=0;state_q<=legal?INPUT_PACKET:DONE;
   end
   INPUT_PACKET:if(in_valid_i&&in_ready_o)begin
    received_chunks_o<=received_chunks_o+1;
    if(in_status_i!=0)begin status_o<=in_status_i;state_q<=DONE;end
    else if(in_chunk_i!=chunk_q||in_keep_i!=expected_keep||in_last_i!=(remaining_q<=16))begin status_o<=7;state_q<=DONE;end
    else begin data_q<=in_data_i;keep_q<=in_keep_i;state_q<=WRITE;end
   end
   WRITE:if(wr_ready_i)begin
    written_beats_o<=written_beats_o+1;written_payload_bytes_o<=written_payload_bytes_o+64'(remaining_q>16?16:remaining_q)*4;
    if(remaining_q<=16)begin remaining_q<=0;state_q<=DONE;end
    else begin remaining_q<=remaining_q-16;chunk_q<=chunk_q+1;address_q<=address_q+64;state_q<=INPUT_PACKET;end
   end
   DONE:if(completion_ready_i)state_q<=IDLE;
   default:state_q<=IDLE;
  endcase
 end
endmodule
`default_nettype wire

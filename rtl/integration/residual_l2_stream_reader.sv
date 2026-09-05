// SPDX-License-Identifier: Apache-2.0
`default_nettype none
// Fixed-storage local SRAM reader for one residual operand,16 elements/chunk.
// BF16 memory beats are read once and split through bf16_residual_gearbox.
module residual_l2_stream_reader #(
 parameter integer ADDR_W=15,parameter logic[63:0]SRAM_BYTES=64'd1572864
)(
 input logic clk_i,rst_ni,request_valid_i,output logic request_ready_o,
 input logic[63:0]source_i,input logic[31:0]elements_i,input logic bf16_i,
 output logic rd_valid_o,input logic rd_ready_i,output logic[ADDR_W-1:0]rd_addr_o,
 input logic rsp_valid_i,output logic rsp_ready_o,input logic[511:0]rsp_data_i,input logic rsp_error_i,
 output logic out_valid_o,input logic out_ready_i,output logic[511:0]out_data_o,
 output logic[15:0]out_keep_o,output logic[31:0]out_chunk_o,output logic out_last_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[7:0]status_o,
 output logic[63:0]read_beats_o,output_chunks_o
);
 typedef enum logic[2:0]{IDLE,READ_REQ,READ_RSP,OUTPUT,DONE}state_t;
 state_t state_q;logic bf16_q;logic[63:0]address_q;logic[31:0]remaining_q,chunk_q;
 logic[511:0]fp_data_q,gdata;logic[1:0]packet_chunks_q;
 logic gv,gr,gl,gin_ready,gin_valid;logic[15:0]gkeep;logic[31:0]gchunk,input_keep;
 logic[7:0]gstatus;logic[64:0]required_bytes,end_address;logic legal;
 logic[511:0]raw_data;logic[63:0]gb_reads,gb_chunks;
 assign required_bytes=((65'(elements_i)+(bf16_i?31:15))>>(bf16_i?5:4))<<6;
 assign end_address={1'b0,source_i}+required_bytes;
 assign legal=elements_i!=0&&source_i[5:0]==0&&end_address<={1'b0,SRAM_BYTES}&&end_address<=(65'd1<<(ADDR_W+6));
 assign request_ready_o=rst_ni&&state_q==IDLE;
 assign rd_valid_o=state_q==READ_REQ;assign rd_addr_o=ADDR_W'(address_q>>6);
 assign rsp_ready_o=state_q==READ_RSP&&(!bf16_q||gin_ready);
 always_comb begin input_keep=0;for(integer i=0;i<32;i++)if(i<remaining_q)input_keep[i]=1;end
 assign gin_valid=state_q==READ_RSP&&bf16_q&&rsp_valid_i&&!rsp_error_i;
 bf16_residual_gearbox gearbox(.clk_i,.rst_ni,
  .in_valid_i(gin_valid),.in_ready_o(gin_ready),.in_data_i(rsp_data_i),
  .in_keep_i(input_keep),.in_first_chunk_i(chunk_q),.in_last_i(remaining_q<=32),
  .out_valid_o(gv),.out_ready_i(gr),.out_data_o(gdata),.out_keep_o(gkeep),.out_chunk_o(gchunk),.out_last_o(gl),.out_status_o(gstatus),
  .accepted_beats_o(gb_reads),.emitted_chunks_o(gb_chunks));
 assign out_valid_o=state_q==OUTPUT&&(!bf16_q||gv);
 assign gr=state_q==OUTPUT&&out_ready_i;
 assign raw_data=bf16_q?gdata:fp_data_q;
 assign out_chunk_o=bf16_q?gchunk:chunk_q;
 assign out_last_o=bf16_q?gl:remaining_q<=16;
 always_comb begin
  out_keep_o=0;out_data_o=0;
  for(integer i=0;i<16;i++)begin
   out_keep_o[i]=bf16_q?gkeep[i]:(i<remaining_q);
   if(out_keep_o[i])begin
    if(bf16_q)out_data_o[i*16+:16]=raw_data[i*16+:16];
    else out_data_o[i*32+:32]=raw_data[i*32+:32];
   end
  end
 end
 assign completion_valid_o=state_q==DONE;
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=IDLE;bf16_q<=0;address_q<=0;remaining_q<=0;chunk_q<=0;fp_data_q<=0;packet_chunks_q<=0;status_o<=0;read_beats_o<=0;output_chunks_o<=0;end
  else case(state_q)
   IDLE:if(request_valid_i&&request_ready_o)begin
    bf16_q<=bf16_i;address_q<=source_i;remaining_q<=elements_i;chunk_q<=0;status_o<=legal?0:5;
    read_beats_o<=0;output_chunks_o<=0;state_q<=legal?READ_REQ:DONE;
   end
   READ_REQ:if(rd_ready_i)begin read_beats_o<=read_beats_o+1;state_q<=READ_RSP;end
   READ_RSP:if(rsp_valid_i&&rsp_ready_o)begin
    if(rsp_error_i)begin status_o<=3;state_q<=DONE;end
    else begin fp_data_q<=rsp_data_i;packet_chunks_q<=(bf16_q&&remaining_q>16)?2:1;state_q<=OUTPUT;end
   end
   OUTPUT:if(out_valid_o&&out_ready_i)begin
    output_chunks_o<=output_chunks_o+1;chunk_q<=chunk_q+1;remaining_q<=remaining_q>16?remaining_q-16:0;
    if(bf16_q&&gstatus!=0)begin status_o<=7;state_q<=DONE;end
    else if(out_last_o)state_q<=DONE;
    else if(packet_chunks_q==1)begin address_q<=address_q+64;state_q<=READ_REQ;end
    else packet_chunks_q<=packet_chunks_q-1;
   end
   DONE:if(completion_ready_i)state_q<=IDLE;
   default:state_q<=IDLE;
  endcase
 end
endmodule
`default_nettype wire

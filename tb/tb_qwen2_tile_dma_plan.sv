`timescale 1ns/1ps
module tb_qwen2_tile_dma_plan;
 logic clk=0,rst_n=0,cv,cr,cl,store,rv,rr,sv,sr,se,loads,done;always #0.5 clk=~clk;
 logic[335:0]addresses;logic[1:0]kind;logic[63:0]src,dst,rb,wb,hl,rl,nl,ql,ol;
 logic[31:0]row_bytes,rows,ss,ds;logic[7:0]status;logic[55:0]a[0:5];logic[31:0]lfsr;
 integer requests,responses,delay;logic pending;logic[1:0]ek[0:3];logic[63:0]es[0:3],ed[0:3];logic[31:0]erb[0:3],erows[0:3],ess[0:3],eds[0:3];
 qwen2_tile_dma_plan dut(.clk_i(clk),.rst_ni(rst_n),.context_valid_i(cv),.context_ready_o(cr),
  .context_legal_i(cl),.tensor_address_i(addresses),.q_column_tile_i(6'd0),.full_q_i(1'b0),.reuse_norm_i(1'b0),.start_store_i(store),.dma_req_valid_o(rv),
  .dma_req_ready_i(rr),.dma_req_kind_o(kind),.dma_src_addr_o(src),.dma_dst_addr_o(dst),
  .dma_row_bytes_o(row_bytes),.dma_rows_o(rows),.dma_src_stride_o(ss),.dma_dst_stride_o(ds),
  .dma_rsp_valid_i(sv),.dma_rsp_ready_o(sr),.dma_rsp_error_i(se),.loads_done_o(loads),
  .done_o(done),.status_o(status),.ddr_read_bytes_o(rb),.ddr_write_bytes_o(wb),
  .hidden_local_o(hl),.rms_weight_local_o(rl),.norm_local_o(nl),.q_weight_local_o(ql),.q_output_local_o(ol));
 always_ff@(posedge clk or negedge rst_n)begin if(!rst_n)begin lfsr<=32'h82a1d4f3;pending<=0;sv<=0;requests<=0;responses<=0;delay<=0;end else begin
  lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};sv<=0;
  if(rv&&rr)begin if(kind!==ek[requests]||src!==es[requests]||dst!==ed[requests]||row_bytes!==erb[requests]||rows!==erows[requests]||ss!==ess[requests]||ds!==eds[requests])$fatal(1,"request mismatch %0d",requests);requests<=requests+1;pending<=1;delay<=lfsr[4+:3];end
  if(pending)begin if(delay==0)begin sv<=1;if(sr)begin pending<=0;responses<=responses+1;end end else delay<=delay-1;end
 end end
 assign rr=!pending&&(lfsr[0]||lfsr[3]);assign se=0;
 initial begin cv=0;cl=1;store=0;addresses=0;for(integer i=0;i<6;i++)begin a[i]=56'h100000+i*56'h100000;addresses[i*56+:56]=a[i];end
  ek[0]=0;es[0]={8'd0,a[0]};ed[0]=64'h40000;erb[0]=3072;erows[0]=1;ess[0]=3072;eds[0]=3072;
  ek[1]=0;es[1]={8'd0,a[1]};ed[1]=64'h41000;erb[1]=6144;erows[1]=1;ess[1]=6144;eds[1]=6144;
  ek[2]=1;es[2]={8'd0,a[4]};ed[2]=64'h44000;erb[2]=64;erows[2]=1536;ess[2]=3072;eds[2]=64;
  ek[3]=2;es[3]=64'h5c000;ed[3]={8'd0,a[5]};erb[3]=64;erows[3]=1;ess[3]=64;eds[3]=64;
  repeat(6)@(posedge clk);rst_n=1;@(negedge clk);cv=1;do@(posedge clk);while(!cr);@(negedge clk);cv=0;
  wait(loads);if(rb!=107520||requests!=3||responses!=3)$fatal(1,"load accounting");repeat(4)@(posedge clk);if(!loads)$fatal(1,"loads_done unstable");
  @(negedge clk);store=1;@(posedge clk);@(negedge clk);store=0;wait(done);if(status||rb!=107520||wb!=64||requests!=4||responses!=4)$fatal(1,"final accounting");
  $display("QWEN2_TILE_DMA_PLAN_PASS requests=4 load1d=2 load2d=1 store1d=1 read_bytes=107520 write_bytes=64 q_weight_rows=1536 q_weight_row_bytes=64 src_stride=3072 dst_stride=64 random_backpressure=1");$finish;end
 initial begin repeat(10000)@(posedge clk);$fatal(1,"timeout req=%0d rsp=%0d state=%0d",requests,responses,dut.state_q);end
endmodule

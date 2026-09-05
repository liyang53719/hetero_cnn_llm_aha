`timescale 1ns/1ps
module tb_idma_strided_row_chunks;
 logic clk_i=0;always #1 clk_i=~clk_i;logic rst_ni=0,req_valid_i=0,req_ready_o;
 logic[1:0]req_kind_i;logic[63:0]src_addr_i,dst_addr_i;
 logic[31:0]row_bytes_i,rows_i,src_stride_i,dst_stride_i;
 logic rsp_valid_o,rsp_ready_i=0,rsp_error_o,idma_req_valid_o,idma_req_ready_i=0;
 logic[63:0]idma_src_addr_o,idma_dst_addr_o;logic[31:0]idma_length_o;
 logic idma_rsp_valid_i=0,idma_rsp_ready_o,idma_rsp_error_i=0;
 logic[31:0]flat_requests_o;logic local_source_o;
 integer flat_seen=0;longint unsigned bytes_seen=0;
 qwen2_tile_idma_expand dut(.*);
 task tick;@(posedge clk_i);@(negedge clk_i);endtask
 task run(input integer kind,b,n,ss,ds);
  integer limit,linear,row_count,rb,chunk;logic[63:0]sa,da;
  req_kind_i=2'(kind);row_bytes_i=b;rows_i=n;src_stride_i=ss;dst_stride_i=ds;
  src_addr_i=64'h100000000;dst_addr_i=64'h200000000;req_valid_i=1;tick();req_valid_i=0;
  src_addr_i=0;dst_addr_i=0;row_bytes_i=0;rows_i=0;
  limit=kind>=2?64:1024;linear=((kind==1||kind==3)&&ss==b&&ds==b);
  row_count=linear?1:((kind==1||kind==3)?n:1);rb=linear?b*n:b;
  for(int r=0;r<row_count;r++)for(int off=0;off<rb;off+=limit)begin
   wait(idma_req_valid_o);sa=64'h100000000+64'(r)*ss+off;da=64'h200000000+64'(r)*ds+off;
   chunk=(rb-off>limit)?limit:rb-off;
   repeat(3)begin
    if(idma_src_addr_o!=sa||idma_dst_addr_o!=da||idma_length_o!=chunk||rsp_valid_o)$fatal(1,"chunk kind=%0d row=%0d offset=%0d",kind,r,off);
    tick();
   end
   idma_req_ready_i=1;tick();idma_req_ready_i=0;flat_seen++;bytes_seen+=chunk;
   repeat(2)tick();if(!idma_rsp_ready_o||idma_req_valid_o||rsp_valid_o)$fatal(1,"early done");
   idma_rsp_valid_i=1;tick();idma_rsp_valid_i=0;
  end
  if(!rsp_valid_o||rsp_error_o||flat_requests_o!=flat_seen)$fatal(1,"aggregate");
  repeat(3)tick();rsp_ready_i=1;tick();rsp_ready_i=0;
 endtask
 initial begin
  req_kind_i=0;src_addr_i=0;dst_addr_i=0;row_bytes_i=0;rows_i=0;src_stride_i=0;dst_stride_i=0;
  tick();rst_ni=1;
  run(1,3073,3,4096,8192);run(3,129,3,192,256);
  run(1,3072,16,3072,3072);run(3,3072,16,3072,3072);
  run(0,1025,1,0,0);run(2,65,1,0,0);
  if(bytes_seen!=109000)$fatal(1,"byte sum=%0d",bytes_seen);
  req_kind_i=1;row_bytes_i=64;rows_i=2;src_stride_i=64;dst_stride_i=64;
  src_addr_i=64'hffffffffffffffc0;dst_addr_i=0;req_valid_i=1;tick();req_valid_i=0;
  if(!rsp_valid_o||!rsp_error_o||idma_req_valid_o)$fatal(1,"overflow accepted");
  $display("IDMA_STRIDED_ROW_CHUNKS_PASS cases=6 flat=%0d bytes=%0d overflow_rejected=1",flat_seen,bytes_seen);$finish;
 end
 initial begin repeat(20000)tick();$fatal(1,"watchdog");end
endmodule

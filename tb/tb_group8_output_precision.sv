`timescale 1ns/1ps
// Control/packing regression: actual descriptor, loader, transpose and payload;
// abstract DMA memory service and tagged accumulator fixture, NOT numerical MAC.
module tb_group8_output_precision;
 logic clk=0;always #1 clk=~clk;
 logic rst=0,start=0;logic[127:0]command,records[0:5],dsd;
 logic dqv,dqr,dsv=0,dsr;logic[23:0]dqi;
 logic av,ar,asv=0,asr;logic[1:0]ak;logic[63:0]src,dst;logic[31:0]rb,nr,ss,ds;
 logic rv,rr,rsv=0,rsr,wv,wr,done;logic[14:0]ra,wa;logic[511:0]rd,wd,mem[0:24575];logic[63:0]be;
 logic[7:0]status;logic[31:0]steps,values,loads,norms,batches=1;logic[63:0]read_bytes,write_bytes;
 logic[31:0]rng=32'h12378234;integer columns,ebytes,stores,expected_total,cases=0,checked=0;
 integer expected_col[0:31],expected_batch[0:31];
 qwen2_projection_q1024_group8_controller dut(.clk_i(clk),.rst_ni(rst),.start_i(start),.command_i(command),.trace_only_i(1'b0),.batch_count_i(batches),
 .descriptor_req_valid_o(dqv),.descriptor_req_ready_i(dqr),.descriptor_req_index_o(dqi),.descriptor_rsp_valid_i(dsv),.descriptor_rsp_ready_o(dsr),.descriptor_rsp_data_i(dsd),.descriptor_rsp_error_i(1'b0),
 .dma_req_valid_o(av),.dma_req_ready_i(ar),.dma_req_kind_o(ak),.dma_src_addr_o(src),.dma_dst_addr_o(dst),.dma_row_bytes_o(rb),.dma_rows_o(nr),.dma_src_stride_o(ss),.dma_dst_stride_o(ds),.dma_rsp_valid_i(asv),.dma_rsp_ready_o(asr),.dma_rsp_error_i(1'b0),
 .l2_rd_valid_o(rv),.l2_rd_ready_i(rr),.l2_rd_addr_o(ra),.l2_rsp_valid_i(rsv),.l2_rsp_ready_o(rsr),.l2_rsp_data_i(rd),.l2_wr_valid_o(wv),.l2_wr_ready_i(wr),.l2_wr_addr_o(wa),.l2_wr_data_o(wd),.l2_wr_be_o(be),
 .done_o(done),.status_o(status),.matrix_steps_o(steps),.values_o(values),.weight_tile_loads_o(loads),.norm_batch_loads_o(norms),.ddr_read_bytes_o(read_bytes),.ddr_write_bytes_o(write_bytes));
 assign dqr=!dsv&&rng[0];assign ar=!asv&&rng[2];assign rr=!rsv&&rng[3];assign wr=rng[4]||rng[6];
 function automatic[31:0]word(input integer tile,lane);word=32'h3f800101+32'(tile)*32'h10000+32'(lane)*32'h101;endfunction
 function automatic[15:0]bf(input logic[31:0]x);logic[31:0]t;begin t=x+32'h7fff+x[16];bf=t[31:16];end endfunction
 always @(posedge clk)if(!rst)begin dsv<=0;asv<=0;rsv<=0;stores<=0;rng<=32'h12378234;end else begin
  rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(dqv&&dqr)begin if(dqi>5)$fatal(1,"descriptor index");dsd<=records[dqi];dsv<=1;end
  if(dsv&&dsr)dsv<=0;
  if(rv&&rr)begin rd<=mem[ra];rsv<=1;end
  if(rsv&&rsr)rsv<=0;
  if(wv&&wr)for(int byteidx=0;byteidx<64;byteidx++)if(be[byteidx])mem[wa][byteidx*8+:8]<=wd[byteidx*8+:8];
  if(av&&ar)begin
   asv<=1;
   if(ak==1)begin
    if(dst!=64'h60000&&dst!=64'ha0000)$fatal(1,"load destination");
    for(int row=0;row<nr;row++)for(int beat=0;beat<rb/64;beat++)mem[(dst+row*ds)/64+beat]={32{16'h3f80}};
   end else if(ak==3)begin
    if(stores>=expected_total||src!=64'h160000||rb!=32*ebytes||nr!=16||ss!=rb||ds!=columns*ebytes||
      dst!=64'h300000000+64'(expected_batch[stores])*16*columns*ebytes+64'(expected_col[stores])*32*ebytes)$fatal(1,"store geometry store=%0d src=%h dst=%h rb=%0d stride=%0d",stores,src,dst,rb,ds);
    for(int row=0;row<16;row++)for(int col=0;col<32;col++)begin
     if(ebytes==4)begin
      if(mem[(src+row*ss)/64+col/16][(col%16)*32+:32]!==word(stores,row*32+col))$fatal(1,"FP32 packing");
     end else if(mem[(src+row*ss)/64][col*16+:16]!==bf(word(stores,row*32+col)))$fatal(1,"BF16 packing");
     checked++;
    end
    stores<=stores+1;
   end else $fatal(1,"DMA kind");
  end
  if(asv&&asr)asv<=0;
 end
 task tick;@(posedge clk);@(negedge clk);endtask
 task run_case(input bit fp32,input integer n,nb);
  integer nt,groups,gc;
  begin
   rst=0;repeat(2)tick();columns=n;batches=nb;ebytes=fp32?4:2;nt=n/32;groups=(nt+7)/8;expected_total=0;
   for(int gb=0;gb<nt;gb+=8)begin gc=(nt-gb>8)?8:nt-gb;
    for(int batch=0;batch<nb;batch++)for(int slot=0;slot<gc;slot++)begin expected_col[expected_total]=gb+slot;expected_batch[expected_total]=batch;expected_total++;end
   end
   command=0;command[7:0]=8'h20;command[10:8]=2;command[79:56]=0;command[103:80]=1;command[127:104]=2;
   for(int i=0;i<3;i++)begin
    records[i]=0;records[i][7:0]=1;records[i][55:32]=24'(i+3);records[i][103:56]=48'h100000000*(i+1);records[i][111:108]=(i==2&&fp32)?7:5;
    records[i+3]=0;records[i+3][7:0]=2;records[i+3][55:32]=24'hffffff;records[i+3][56+:18]=(i==1)?1536:1024;
    records[i+3][74+:18]=(i==0)?1536:18'(n);records[i+3][92+:18]=1;records[i+3][110+:18]=1;
   end
   rst=1;tick();start=1;tick();start=0;wait(done);@(negedge clk);
   if(status||stores!=expected_total||steps!=1536*nt*nb||values!=16*n*nb||loads!=nt||norms!=groups*nb||
     read_bytes!=64'(1536)*n*2+64'(groups)*nb*49152||write_bytes!=64'(16)*n*nb*ebytes)$fatal(1,"totals status=%0d stores=%0d write_bytes=%0d",status,stores,write_bytes);
   cases++;$display("GROUP8_PRECISION_CASE mode=%0d n=%0d batches=%0d stores=%0d writes=%0d",fp32,n,nb,stores,write_bytes);tick();
  end
 endtask
 initial begin run_case(0,32,2);run_case(1,32,2);run_case(0,288,1);run_case(1,288,1);
  $display("GROUP8_OUTPUT_PRECISION_CONTROL_PASS cases=%0d checked=%0d numerical_matrix_mocked=1",cases,checked);$finish;end
 initial begin repeat(1000000)tick();$fatal(1,"watchdog");end
endmodule

// Tagged accumulator fixture only; never compile alongside the real Matrix endpoint.
module qwen2_matrix_command_endpoint(
 input logic clk_i,rst_ni,cmd_valid_i,output logic cmd_ready_o,input logic[127:0]cmd_i,
 input logic step_valid_i,output logic step_ready_o,input logic[2:0]step_context_i,input logic step_clear_i,step_last_i,command_last_tile_i,
 input logic[255:0]step_a_i,input logic[511:0]step_b_i,
 output logic out_valid_o,input logic out_ready_i,output logic[2:0]out_context_o,output logic out_last_o,output logic[16383:0]out_acc_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[55:0]completion_data_o,output logic protocol_error_o);
 integer tile;logic final_tile;
 assign cmd_ready_o=1;assign step_ready_o=!out_valid_o||out_ready_i;assign completion_data_o=0;assign protocol_error_o=0;
 always @(posedge clk_i)if(!rst_ni)begin tile<=0;out_valid_o<=0;out_last_o<=0;completion_valid_o<=0;out_acc_o<=0;out_context_o<=0;final_tile<=0;end else begin
  if(out_valid_o&&out_ready_i)begin out_valid_o<=0;if(out_last_o&&final_tile)completion_valid_o<=1;end
  if(completion_valid_o&&completion_ready_i)completion_valid_o<=0;
  if(step_valid_i&&step_ready_o)begin
   out_valid_o<=1;out_last_o<=step_last_i;out_context_o<=step_context_i;final_tile<=command_last_tile_i;
   if(step_last_i)begin for(int i=0;i<512;i++)out_acc_o[i*32+:32]<=32'h3f800101+32'(tile)*32'h10000+32'(i)*32'h101;tile<=tile+1;end
  end
 end
endmodule

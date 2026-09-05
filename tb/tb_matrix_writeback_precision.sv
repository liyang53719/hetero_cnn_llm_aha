`timescale 1ns/1ps
module tb_matrix_writeback_precision;
 logic clk=0;always #1 clk=~clk;
 logic rst=0,start=0,fp32=0;logic[15:0]rows=3,cols=32;logic[63:0]ob=64'h40000;
 logic rv,rr,rsv,rsr,wv,wr,sv,clear,last,ov=0,mor,done,pending=0;
 logic[14:0]ra,wa;logic[511:0]wd,rd={32{16'h3f80}},b;logic[255:0]a;logic[63:0]be;
 logic[2:0]ctx;logic[16383:0]acc;logic[7:0]status;logic[31:0]reads,writes,steps;
 logic[511:0]mem[0:63];logic[31:0]rng=32'hfa324822;
 logic held=0;logic[511:0]held_data;logic[63:0]held_be;logic[14:0]held_addr;
 integer cases=0,checked=0;
 function automatic[31:0] word(input integer i);word=32'h3f800101+32'(i)*32'h101;endfunction
 function automatic[15:0] bf(input logic[31:0] x);logic[31:0]r;begin r=x+32'h7fff+x[16];bf=r[31:16];end endfunction
 qwen2_shared_l2_matrix_tile16_payload dut(
  .clk_i(clk),.rst_ni(rst),.start_i(start),.activation_local_i(64'd0),.weight_local_i(64'h20000),.output_local_i(ob),
  .depth_i(16'd1),.weight_k_stride_i(32'd64),.rows_i(rows),.columns_i(cols),.output_fp32_i(fp32),.status_o(status),
  .l2_rd_valid_o(rv),.l2_rd_ready_i(rr),.l2_rd_addr_o(ra),.l2_rsp_valid_i(rsv),.l2_rsp_ready_o(rsr),.l2_rsp_data_i(rd),
  .l2_wr_valid_o(wv),.l2_wr_ready_i(wr),.l2_wr_addr_o(wa),.l2_wr_data_o(wd),.l2_wr_be_o(be),
  .matrix_step_valid_o(sv),.matrix_step_ready_i(1'b1),.matrix_context_o(ctx),.matrix_clear_o(clear),.matrix_last_o(last),
  .matrix_a_o(a),.matrix_b_o(b),.matrix_out_valid_i(ov),.matrix_out_ready_o(mor),.matrix_out_last_i(ov),.matrix_acc_i(acc),
  .done_o(done),.read_beats_o(reads),.write_beats_o(writes),.matrix_steps_o(steps));
 assign rr=!pending&&rng[0];assign rsv=pending;assign wr=rng[3]&&rng[6];
 always @(posedge clk)if(rst)begin
  rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(rv&&rr)pending<=1;if(rsv&&rsr)pending<=0;
  ov<=sv;
  if(sv&&(!clear||!last||ctx!=0))$fatal(1,"Matrix step semantics");
  if(held&&(!wv||wd!==held_data||be!==held_be||wa!==held_addr))$fatal(1,"write backpressure stability");
  held<=wv&&!wr;held_data<=wd;held_be<=be;held_addr<=wa;
  if(wv&&wr)begin
   if(wa<4096||wa>=4160)$fatal(1,"address");
   for(int byte_lane=0;byte_lane<64;byte_lane++)if(be[byte_lane])mem[wa-4096][byte_lane*8+:8]<=wd[byte_lane*8+:8];
  end
 end
 task tick;@(posedge clk);@(negedge clk);endtask
 task run_case(input logic mode,input integer nr,nc);
  integer pitch,lanes,row,col;logic[31:0]exp32;logic[15:0]exp16;
  begin
   fp32=mode;rows=16'(nr);cols=16'(nc);ob=64'h40000;
   pitch=(mode&&nc>16)?2:1;lanes=mode?16:32;
   for(int i=0;i<64;i++)mem[i]='1;
   start=1;tick();start=0;fp32=!mode;rows=1;cols=1;ob=0;
   wait(done);@(negedge clk);
   if(status||writes!=nr*pitch||reads!=2||steps!=1)$fatal(1,"counts mode=%0d nr=%0d nc=%0d writes=%0d",mode,nr,nc,writes);
   for(int beat=0;beat<64;beat++)for(int lane=0;lane<lanes;lane++)begin
    row=beat/pitch;col=(beat%pitch)*lanes+lane;
    if(mode)begin
     exp32=(row<nr&&col<nc)?word(row*32+col):32'hffffffff;
     if(mem[beat][lane*32+:32]!==exp32)$fatal(1,"FP32 data row=%0d col=%0d",row,col);
    end else begin
     exp16=(row<nr&&col<nc)?bf(word(row*32+col)):16'hffff;
     if(mem[beat][lane*16+:16]!==exp16)$fatal(1,"BF16 data row=%0d col=%0d",row,col);
    end
    checked++;
   end
   cases++;tick();
  end
 endtask
 initial begin
  for(int i=0;i<512;i++)acc[i*32+:32]=word(i);
  repeat(3)tick();rst=1;tick();
  for(int mode=0;mode<2;mode++)begin
   run_case(1'(mode),3,1);run_case(1'(mode),3,16);run_case(1'(mode),3,17);run_case(1'(mode),3,31);run_case(1'(mode),16,32);
  end
  fp32=1;rows=1;cols=32;ob=64'h1fffc0;start=1;tick();start=0;
  if(!done||status!=5||rv||wv||sv||writes||reads||steps)$fatal(1,"FP32 range check");
  tick();
  $display("MATRIX_WRITEBACK_PRECISION_PASS cases=%0d checked=%0d fp32_bits_preserved=1 bf16_rne=1 bounds=1 snapshot=1",cases,checked);$finish;
 end
 initial begin repeat(5000)tick();$fatal(1,"timeout");end
endmodule

`timescale 1ns/1ps
module tb_l5_qwen2_four_layer_cross_replay;
  localparam integer NODES=5,H=1536,SAMPLES=160,STEPS=NODES*H;
  logic clk=0,rst_n=0;integer cycles,rms_seen,matrix_finals,rms_fd,matrix_fd;logic[31:0]lfsr;
  logic riv,rir,rov,ror;logic[49151:0]rx,rw,ry;logic[4:0]rf,rflags;logic[31:0]rac,rcc,rrc,rqc,roc;
  logic miv,mir,mclear,mlast,mov,mor,molast;logic[2:0]mctxi,mctxo;logic[255:0]ma;logic[511:0]mb;logic[16383:0]macc;logic[4:0]mf,mbusy,mvalid,mflags;logic[31:0]maccept,mcomplete;logic merror;
  logic[31:0]xmem[0:STEPS-1],wmem[0:STEPS-1],norm_fp32[0:STEPS-1];logic[15:0]mwmem[0:STEPS*32-1];string rms_path,matrix_path;
  always #0.5 clk=~clk;assign ror=lfsr[0]||lfsr[3];assign mor=lfsr[1]||lfsr[5];
  fp32_rmsnorm1536_chunked #(.REFINE_RSQRT(1'b1)) rms(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(riv),.in_ready_o(rir),.x_i(rx),.weight_i(rw),.epsilon_i(32'h358637bd),.out_valid_o(rov),.out_ready_i(ror),.y_o(ry),.exception_flags_o(rf),.accepted_o(rac),.completed_o(rcc),.reduction_cycles_o(rrc),.rsqrt_cycles_o(rqc),.output_cycles_o(roc));
  bf16_outer_product_context_array_rev8b_b_candidate matrix(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(miv),.in_ready_o(mir),.context_i(mctxi),.clear_i(mclear),.last_i(mlast),.a_i(ma),.b_i(mb),.out_valid_o(mov),.out_ready_i(mor),.context_o(mctxo),.last_o(molast),.acc_o(macc),.exception_flags_o(mf),.busy_o(mbusy),.accumulator_valid_o(mvalid),.accepted_steps_o(maccept),.completed_steps_o(mcomplete),.protocol_error_o(merror));
  function automatic[15:0]to_bf16(input logic[31:0]v);logic[31:0]r;begin r=v+32'h00007fff+v[16];to_bf16=r[31:16];end endfunction
  always_ff@(posedge clk)begin
    if(!rst_n)begin cycles<=0;lfsr<=32'h4c5a91e7;rms_seen<=0;matrix_finals<=0;rflags<=0;mflags<=0;end else begin cycles<=cycles+1;lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
      if(rov&&ror)begin for(integer i=0;i<H;i++)begin norm_fp32[rms_seen*H+i]<=ry[i*32+:32];$fdisplay(rms_fd,"%08x",ry[i*32+:32]);end rms_seen<=rms_seen+1;rflags<=rflags|rf;end
      if(mov&&mor)begin mflags<=mflags|mf;if(molast)begin for(integer c=0;c<32;c++)$fdisplay(matrix_fd,"%08x",macc[c*32+:32]);matrix_finals<=matrix_finals+1;end end
      if(merror)$fatal(1,"matrix protocol error");end
  end
  initial begin
    riv=0;miv=0;mclear=0;mlast=0;mctxi=0;rx='0;rw='0;ma='0;mb='0;if(!$value$plusargs("RMS_OUTPUT=%s",rms_path))rms_path="work/results/l5_qwen2_four_layer_cross_replay/rms_output.memh";if(!$value$plusargs("MATRIX_OUTPUT=%s",matrix_path))matrix_path="work/results/l5_qwen2_four_layer_cross_replay/matrix_output.memh";rms_fd=$fopen(rms_path,"w");matrix_fd=$fopen(matrix_path,"w");if(!rms_fd||!matrix_fd)$fatal(1,"output open");
    $readmemh("work/results/l5_qwen2_four_layer_reference/cross_vectors/rms_x_fp32.memh",xmem);$readmemh("work/results/l5_qwen2_four_layer_reference/cross_vectors/rms_weight_fp32.memh",wmem);$readmemh("work/results/l5_qwen2_four_layer_reference/cross_vectors/matrix_weights_bf16.memh",mwmem);
    repeat(8)@(posedge clk);rst_n=1;
    for(integer node=0;node<NODES;node++)begin @(negedge clk);for(integer i=0;i<H;i++)begin rx[i*32+:32]=xmem[node*H+i];rw[i*32+:32]=wmem[node*H+i];end riv=1;do@(posedge clk);while(!rir);@(negedge clk);riv=0;do@(posedge clk);while(!(rov&&ror));end
    wait(rms_seen==NODES);@(negedge clk);
    for(integer k=0;k<H;k++)for(integer ctx=0;ctx<NODES;ctx++)begin ma='0;ma[15:0]=to_bf16(norm_fp32[ctx*H+k]);for(integer c=0;c<32;c++)mb[c*16+:16]=mwmem[(k*NODES+ctx)*32+c];mctxi=ctx[2:0];mclear=k==0;mlast=k==H-1;miv=1;do@(posedge clk);while(!mir);@(negedge clk);miv=0;end
    while(mcomplete<STEPS&&cycles<30000)@(posedge clk);repeat(8)@(posedge clk);$fclose(rms_fd);$fclose(matrix_fd);
    if(rac!=NODES||rcc!=NODES||rms_seen!=NODES||rflags[4:1])$fatal(1,"rms accounting %0d/%0d/%0d flags=%h",rac,rcc,rms_seen,rflags);
    if(maccept!=STEPS||mcomplete!=STEPS||matrix_finals!=NODES||mbusy||mflags[4:1])$fatal(1,"matrix accounting %0d/%0d/%0d busy=%h flags=%h",maccept,mcomplete,matrix_finals,mbusy,mflags);
    $display("L5_QWEN2_FOUR_LAYER_CROSS_RTL_PASS nodes=5 layers=4 rms_vectors=5 rms_rsqrt_cycles=%0d matrix_samples=160 matrix_steps=7680 cycles=%0d",rqc,cycles);$finish;
  end
  initial begin repeat(40000)@(posedge clk);$fatal(1,"timeout");end
endmodule

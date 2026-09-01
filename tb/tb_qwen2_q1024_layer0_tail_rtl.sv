`timescale 1ns/1ps
module tb_qwen2_q1024_layer0_tail_rtl;
  logic clk,rst_n;always #0.5 clk=~clk;
  logic minv,minr,mclear,mlast,mov,mor,mol;logic[2:0]mctx,moctx;logic[255:0]ma;logic[511:0]mb;logic[16383:0]macc;logic[4:0]mflags,mbusy,mvalid;logic[31:0]maccept,mcomplete;logic merror;
  logic siv,sir,sov,sor,slast_i,slast_o;logic[127:0]sgate,sup,sproduct;logic[11:0]stag_i,stag_o;logic[4:0]sflags;
  logic[255:0]activation[0:8959];logic[511:0]weights[0:26879],expected[0:47];logic[127:0]gate8[0:1023],up8[0:1023],product8[0:1023];
  logic[31:0]lfsr;logic[16383:0]last_matrix_acc;integer layer,matrix_steps,matrix_values,matrix_output_count,silu_output_count;string vector_dir;
  bf16_outer_product_context_array_rev8b_b_candidate matrix(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(minv),.in_ready_o(minr),.context_i(mctx),.clear_i(mclear),.last_i(mlast),.a_i(ma),.b_i(mb),.out_valid_o(mov),.out_ready_i(mor),.context_o(moctx),.last_o(mol),.acc_o(macc),.exception_flags_o(mflags),.busy_o(mbusy),.accumulator_valid_o(mvalid),.accepted_steps_o(maccept),.completed_steps_o(mcomplete),.protocol_error_o(merror));
  bf16_silu_mul_lut_array#(.LANES(8),.TAG_W(12))silu(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(siv),.in_ready_o(sir),.gate_bf16_i(sgate),.up_bf16_i(sup),.tag_i(stag_i),.last_i(slast_i),.out_valid_o(sov),.out_ready_i(sor),.result_bf16_o(sproduct),.tag_o(stag_o),.last_o(slast_o),.exception_flags_o(sflags));
  assign sor=rst_n&&(lfsr[2]||lfsr[7]);
  always_ff@(posedge clk)if(!rst_n)begin lfsr<=32'h1024a55a;matrix_output_count<=0;last_matrix_acc<=0;silu_output_count<=0;end else begin lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};if(mov&&mor)begin matrix_output_count<=matrix_output_count+1;last_matrix_acc<=macc;end if(sov&&sor)begin if(sproduct!==product8[silu_output_count]||stag_o!==silu_output_count[11:0]||slast_o!==(silu_output_count==1023)||sflags[4:1])$fatal(1,"silu beat=%0d",silu_output_count);silu_output_count<=silu_output_count+1;end end
  task automatic run_matrix(input string name,input integer ksteps);logic[16383:0]result;integer mismatches;begin
    $readmemh({vector_dir,"/",name,"_activation.memh"},activation);
    $readmemh({vector_dir,"/",name,"_weights.memh"},weights);
    $readmemh({vector_dir,"/",name,"_expected.memh"},expected);
    mismatches=0;for(integer tile=0;tile<3;tile++)begin integer output_base;output_base=matrix_output_count;for(integer k=0;k<ksteps;k++)begin @(negedge clk);mctx=3'd4;mclear=k==0;mlast=k==ksteps-1;ma=activation[k];mb=weights[tile*ksteps+k];minv=1;mor=1;do@(posedge clk);while(!minr);@(negedge clk);minv=0;matrix_steps++;end wait(matrix_output_count==output_base+ksteps);@(negedge clk);result=last_matrix_acc;if(merror||mflags[4:1])$fatal(1,"matrix protocol");for(integer row=0;row<16;row++)for(integer col=0;col<32;col++)begin logic[31:0]word;logic[15:0]rounded;word=result[(row*32+col)*32+:32];word=word+32'h7fff+word[16];rounded=word[31:16];if(rounded!==expected[tile*16+row][col*16+:16])begin if(mismatches<8)$display("MATRIX_MISMATCH op=%s tile=%0d row=%0d col=%0d fp32=%08h actual=%04h expected=%04h",name,tile,row,col,result[(row*32+col)*32+:32],rounded,expected[tile*16+row][col*16+:16]);mismatches++;end matrix_values++;end end
    if(mismatches)$fatal(1,"%s mismatches=%0d",name,mismatches);$display("QWEN2_LAYER0_MATRIX_SAMPLE_PASS operation=%s tiles=3 k=%0d values=1536 layer=%0d",name,ksteps,layer);
  end endtask
  initial begin logic[11:0]expected_tag;logic expected_last;clk=0;rst_n=0;minv=0;mor=0;mctx=0;mclear=0;mlast=0;ma=0;mb=0;siv=0;sgate=0;sup=0;stag_i=0;slast_i=0;matrix_steps=0;matrix_values=0;if(!$value$plusargs("LAYER=%d",layer))layer=0;if(!$value$plusargs("VECTOR_DIR=%s",vector_dir))vector_dir="work/results/qwen2_q1024_layer0_tail_rtl/vectors";repeat(8)@(posedge clk);rst_n=1;
    run_matrix("oproj",1536);run_matrix("gate",1536);run_matrix("up",1536);run_matrix("down",8960);
    $readmemh({vector_dir,"/silu_gate8.memh"},gate8);$readmemh({vector_dir,"/silu_up8.memh"},up8);$readmemh({vector_dir,"/silu_product8.memh"},product8);
    for(integer beat=0;beat<1024;beat++)begin @(negedge clk);sgate=gate8[beat];sup=up8[beat];stag_i=beat[11:0];slast_i=beat==1023;siv=1;do@(posedge clk);while(!sir);@(negedge clk);siv=0;end wait(silu_output_count==1024);@(negedge clk);
    if(matrix_steps!=40704||matrix_output_count!=40704||matrix_values!=6144||silu_output_count!=1024||maccept!=40704||mcomplete!=40704)$fatal(1,"accounting");
    $display("QWEN2_Q1024_LAYER0_TAIL_RTL_PASS matrix_steps=40704 matrix_values=6144 silu_lanes=8 silu_values=8192 silu_random_backpressure=1 matrix_out_ready=1 same_RTL=1 layer=%0d",layer);$finish;
  end
  initial begin repeat(1000000)@(posedge clk);$fatal(1,"timeout matrix_steps=%0d minr=%0d mov=%0d mor=%0d merror=%0d",matrix_steps,minr,mov,mor,merror);end
endmodule

`timescale 1ns/1ps
module tb_fp32_block32_softmax_tile16_candidate;
 localparam MAX_CASES=32;
 logic clk,rst_n,start,sv,sr,hv,hr,wv,wr,wl,busy,no_stall;logic[511:0]scores,m,l,weights;logic[15:0]mask;logic[4:0]flags;logic[31:0]accepted,issued,completed,reduced,lfsr;
 logic[511:0]score_vec[0:MAX_CASES*32-1],m_vec[0:MAX_CASES-1],l_vec[0:MAX_CASES-1],weight_vec[0:MAX_CASES*32-1];logic[15:0]mask_vec[0:MAX_CASES*32-1];integer cycles,outputs,stalls,cases,max_case_cycles;string vectors;
 always #0.5 clk=~clk;always_ff@(posedge clk)if(!rst_n)begin cycles<=0;lfsr<=32'h51f0016;end else begin cycles<=cycles+1;lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};end
 fp32_block32_softmax_tile16_candidate dut(.clk_i(clk),.rst_ni(rst_n),.start_i(start),.score_valid_i(sv),.score_ready_o(sr),.scores_i(scores),.mask_i(mask),.summary_valid_o(hv),.summary_ready_i(hr),.m_o(m),.l_o(l),.weight_valid_o(wv),.weight_ready_i(wr),.weights_o(weights),.weight_last_o(wl),.busy_o(busy),.exception_flags_o(flags),.accepted_scores_o(accepted),.issued_exp_groups_o(issued),.completed_exp_groups_o(completed),.reduction_ops_o(reduced));
 task automatic run_case(input integer id);integer begin_cycle,mismatches;begin
  begin_cycle=cycles;mismatches=0;@(negedge clk);start=1;@(posedge clk);@(negedge clk);start=0;
  for(integer col=0;col<32;col++)begin scores=score_vec[id*32+col];mask=mask_vec[id*32+col];sv=1;do@(posedge clk);while(!sr);@(negedge clk);sv=0;end
  while(!hv)@(posedge clk);if(m!==m_vec[id]||l!==l_vec[id])$fatal(1,"header case=%0d",id);@(negedge clk);hr=1;@(posedge clk);@(negedge clk);hr=0;outputs=0;
  while(outputs<32)begin wr=no_stall||(lfsr[0]||lfsr[4]);if(wv&&!wr)stalls++;if(wv&&wr)begin if(weights!==weight_vec[id*32+outputs])mismatches++;if(wl!==(outputs==31))$fatal(1,"last");outputs++;end @(posedge clk);@(negedge clk);end
  wr=0;if(mismatches)$fatal(1,"case=%0d mismatches=%0d",id,mismatches);if(flags[4:1]!=0||accepted!=512||issued!=64||completed!=64||reduced!=496)$fatal(1,"accounting case=%0d",id);while(busy)@(posedge clk);if(cycles-begin_cycle>max_case_cycles)max_case_cycles=cycles-begin_cycle;
 end endtask
 initial begin clk=0;rst_n=0;start=0;sv=0;scores=0;mask=0;hr=0;wr=0;stalls=0;max_case_cycles=0;no_stall=$test$plusargs("NOSTALL");if(!$value$plusargs("VECTORS=%s",vectors))vectors="work/results/l5_block32_tile16_candidate_e1/vectors";cases=16;$readmemh({vectors,"/scores.memh"},score_vec);$readmemh({vectors,"/masks.memh"},mask_vec);$readmemh({vectors,"/m.memh"},m_vec);$readmemh({vectors,"/l.memh"},l_vec);$readmemh({vectors,"/weights.memh"},weight_vec);repeat(6)@(posedge clk);rst_n=1;for(integer id=0;id<cases;id++)run_case(id);$display("BLOCK32_TILE16_CANDIDATE_PASS cases=%0d rows_per_case=16 scores_per_case=512 max_case_cycles=%0d output_stalls=%0d nominal=%0d",cases,max_case_cycles,stalls,no_stall);$finish;end
 initial begin repeat(100000)@(posedge clk);$fatal(1,"timeout");end
endmodule

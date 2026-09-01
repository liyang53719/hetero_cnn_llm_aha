`timescale 1ns/1ps
module tb_qwen2_payload_group_controller;
 logic clk=0,rst_n=0,start,inject,busy,done,ov,orr,dv,dr,error;logic[2:0]group,phase;logic[4:0]layer;logic[7:0]tag,done_tag;logic[31:0]commands,completions,stalls,waits,injections,lfsr;logic[63:0]hash;integer total_commands,total_completions,total_stalls,total_waits,countdown;
 always #0.5 clk=~clk;assign orr=lfsr[0]||lfsr[3];
 qwen2_payload_group_controller dut(.clk_i(clk),.rst_ni(rst_n),.start_i(start),.group_i(group),.reference_inject_i(inject),.busy_o(busy),.done_o(done),.op_valid_o(ov),.op_ready_i(orr),.layer_o(layer),.phase_o(phase),.tag_o(tag),.op_done_valid_i(dv),.op_done_ready_o(dr),.op_done_tag_i(done_tag),.commands_o(commands),.completions_o(completions),.command_stalls_o(stalls),.event_wait_cycles_o(waits),.reference_injections_o(injections),.protocol_error_o(error),.trace_hash_o(hash));
 always_ff@(posedge clk)begin if(!rst_n)begin lfsr<=32'h78a5c39d;dv<=0;done_tag<=0;countdown<=-1;end else begin lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};if(dv&&dr)begin dv<=0;countdown<=-1;end if(ov&&orr)begin done_tag<=tag;countdown<=1+(lfsr[6:4]%5);end else if(countdown>0)countdown<=countdown-1;else if(countdown==0&&!dv&&(lfsr[2]||lfsr[7]))dv<=1;end end
 initial begin start=0;inject=0;group=0;total_commands=0;total_completions=0;total_stalls=0;total_waits=0;repeat(8)@(posedge clk);rst_n=1;
  for(integer g=0;g<7;g++)begin @(negedge clk);group=g[2:0];start=1;@(posedge clk);@(negedge clk);start=0;while(!done)@(posedge clk);if(error||commands!=24||completions!=24||injections!=0||hash==64'hcbf29ce484222325)$fatal(1,"group=%0d cmd=%0d cmp=%0d inj=%0d err=%0d",g,commands,completions,injections,error);total_commands+=commands;total_completions+=completions;total_stalls+=stalls;total_waits+=waits;end
  if(total_commands!=168||total_completions!=168||total_stalls==0||total_waits==0)$fatal(1,"totals");$display("QWEN2_PAYLOAD_GROUP_CONTROLLER_PASS groups=7 layers=28 commands=168 completions=168 reference_injections_inside_groups=0 command_stalls=%0d event_wait_cycles=%0d",total_stalls,total_waits);$finish;end
 initial begin repeat(100000)@(posedge clk);$fatal(1,"timeout");end
endmodule

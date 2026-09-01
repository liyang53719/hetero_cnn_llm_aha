`timescale 1ns/1ps
module tb_qwen2_shared_l2_tile_payload;
 localparam integer AW=15;logic clk=0,rst_n=0;always #0.5 clk=~clk;logic start,done;
 logic prv,prr,prsv,prsr,pwv,pwr;logic[AW-1:0]pra,pwa;logic[511:0]prd,pwd;logic[63:0]pbe;logic[31:0]rbeats,wbeats;
 logic[1:0]mrv,mrr,mrsv,mrsr;logic[2*AW-1:0]mra;logic[1023:0]mrd;logic mwv,mwr;logic[AW-1:0]mwa;logic[511:0]mwd;logic[63:0]mbe;
 logic[63:0]cy,reads,writes,conflicts,rstalls,wstalls;logic host_mode,hwv;logic[AW-1:0]hwa;logic[511:0]hwd;
 logic spv,spr,sov,sor,scv;logic[49151:0]sx,sw,sy;logic[55:0]scd;logic[4:0]sflags;
 logic mpv,mpr,mov,mor,mlast,mcv,merr;logic[2:0]mpctx,moctx;logic mpclear,mplast;logic[255:0]mpa;logic[511:0]mpb;logic[16383:0]macc;logic[55:0]mcd;
 logic scmdv,scmdr,mcmdv,mcmdr;logic[127:0]cmd[0:1];logic[511:0]hidden[0:47],rw[0:95],qw[0:1535],enorm[0:47],eq[0:0];logic[31:0]lfsr;
 shared_l2_fabric #(.ADDR_W(AW),.ROWS_PER_BANK(6144))mem(.clk_i(clk),.rst_ni(rst_n),.rd_valid_i(mrv),.rd_ready_o(mrr),.rd_addr_i(mra),.rd_resp_valid_o(mrsv),.rd_resp_ready_i(mrsr),.rd_data_o(mrd),.wr_valid_i(mwv),.wr_ready_o(mwr),.wr_addr_i(mwa),.wr_data_i(mwd),.wr_be_i(mbe),.cycle_count_o(cy),.read_count_o(reads),.write_count_o(writes),.bank_conflict_count_o(conflicts),.read_stall_count_o(rstalls),.write_stall_count_o(wstalls));
 qwen2_shared_l2_tile_payload #(.ADDR_W(AW))payload(.clk_i(clk),.rst_ni(rst_n),.start_i(start),.reuse_norm_i(1'b0),.load_norm_i(1'b0),.hidden_local_i(64'h40000),.rms_weight_local_i(64'h41000),.norm_local_i(64'h43000),.q_weight_local_i(64'h44000),.q_output_local_i(64'h5c000),.l2_rd_valid_o(prv),.l2_rd_ready_i(prr),.l2_rd_addr_o(pra),.l2_rsp_valid_i(prsv),.l2_rsp_ready_o(prsr),.l2_rsp_data_i(prd),.l2_wr_valid_o(pwv),.l2_wr_ready_i(pwr),.l2_wr_addr_o(pwa),.l2_wr_data_o(pwd),.l2_wr_be_o(pbe),.sfu_payload_valid_o(spv),.sfu_payload_ready_i(spr),.sfu_x_o(sx),.sfu_weight_o(sw),.sfu_out_valid_i(sov),.sfu_out_ready_o(sor),.sfu_y_i(sy),.matrix_step_valid_o(mpv),.matrix_step_ready_i(mpr),.matrix_context_o(mpctx),.matrix_clear_o(mpclear),.matrix_last_o(mplast),.matrix_a_o(mpa),.matrix_b_o(mpb),.matrix_out_valid_i(mov),.matrix_out_ready_o(mor),.matrix_out_last_i(mlast),.matrix_acc_i(macc),.done_o(done),.read_beats_o(rbeats),.write_beats_o(wbeats));
 qwen2_sfu_command_endpoint sfu(.clk_i(clk),.rst_ni(rst_n),.cmd_valid_i(scmdv),.cmd_ready_o(scmdr),.cmd_i(cmd[0]),.payload_valid_i(spv),.payload_ready_o(spr),.payload_x_i(sx),.payload_weight_i(sw),.out_valid_o(sov),.out_ready_i(sor),.out_y_o(sy),.completion_valid_o(scv),.completion_ready_i(1'b1),.completion_data_o(scd),.exception_flags_o(sflags));
 qwen2_matrix_command_endpoint matrix(.clk_i(clk),.rst_ni(rst_n),.cmd_valid_i(mcmdv),.cmd_ready_o(mcmdr),.cmd_i(cmd[1]),.step_valid_i(mpv),.step_ready_o(mpr),.step_context_i(mpctx),.step_clear_i(mpclear),.step_last_i(mplast),.command_last_tile_i(1'b1),.step_a_i(mpa),.step_b_i(mpb),.out_valid_o(mov),.out_ready_i(mor),.out_context_o(moctx),.out_last_o(mlast),.out_acc_o(macc),.completion_valid_o(mcv),.completion_ready_i(1'b1),.completion_data_o(mcd),.protocol_error_o(merr));
 always_ff@(posedge clk or negedge rst_n)if(!rst_n)lfsr<=32'h7531ace9;else lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
 assign mrv={1'b0,prv&&(lfsr[0]||lfsr[4])};assign mra={{AW{1'b0}},pra};assign prr=mrr[0]&&(lfsr[0]||lfsr[4]);assign prsv=mrsv[0]&&(lfsr[1]||lfsr[6]);assign prd=mrd[0+:512];assign mrsr={1'b0,prsr&&(lfsr[1]||lfsr[6])};
 assign mwv=host_mode?hwv:(pwv&&(lfsr[2]||lfsr[7]));assign mwa=host_mode?hwa:pwa;assign mwd=host_mode?hwd:pwd;assign mbe=host_mode?'1:pbe;assign pwr=!host_mode&&mwr&&(lfsr[2]||lfsr[7]);
 task automatic hwrite(input[AW-1:0]a,input[511:0]d);begin @(negedge clk);hwa=a;hwd=d;hwv=1;do@(posedge clk);while(!mwr);@(negedge clk);hwv=0;end endtask
 task automatic hread(input[AW-1:0]a,input[511:0]e);begin @(negedge clk);host_mode=0; // use client1 directly
   force mrv[1]=1;force mra[AW+:AW]=a;force mrsr[1]=0;do@(posedge clk);while(!mrr[1]);@(negedge clk);release mrv[1];wait(mrsv[1]);
   if(mrd[512+:512]!==e)$fatal(1,"readback a=%0d",a);@(negedge clk);force mrsr[1]=1;@(posedge clk);@(negedge clk);release mra[AW+:AW];release mrsr[1];end endtask
 initial begin start=0;host_mode=1;hwv=0;hwa=0;hwd=0;scmdv=0;mcmdv=0;
  $readmemh("work/results/qwen2_shared_l2_tile_payload/commands.memh",cmd);$readmemh("work/results/qwen2_shared_l2_tile_payload/hidden_beats.memh",hidden);$readmemh("work/results/qwen2_shared_l2_tile_payload/rms_weight_beats.memh",rw);$readmemh("work/results/qwen2_shared_l2_tile_payload/q_weight_beats.memh",qw);$readmemh("work/results/qwen2_shared_l2_tile_payload/norm_expected_beats.memh",enorm);$readmemh("work/results/qwen2_shared_l2_tile_payload/q_expected_beat.memh",eq);
  repeat(6)@(posedge clk);rst_n=1;repeat(2)@(posedge clk);for(integer i=0;i<48;i++)hwrite(4096+i,hidden[i]);for(integer i=0;i<96;i++)hwrite(4160+i,rw[i]);for(integer i=0;i<1536;i++)hwrite(4352+i,qw[i]);
  @(negedge clk);host_mode=0;scmdv=1;mcmdv=1;do@(posedge clk);while(!(scmdr&&mcmdr));@(negedge clk);scmdv=0;mcmdv=0;start=1;@(posedge clk);@(negedge clk);start=0;
  wait(done);if(rbeats!=1680||wbeats!=49||merr||sflags[4:1])$fatal(1,"payload counters/errors r=%0d w=%0d",rbeats,wbeats);
  for(integer i=0;i<48;i++)hread(4288+i,enorm[i]);hread(5888,eq[0]);
  $display("QWEN2_SHARED_L2_TILE_PAYLOAD_PASS read_beats=1680 write_beats=49 rms_values=1536 matrix_steps=1536 matrix_outputs=32 bf16_bit_exact=1568 random_l2_backpressure=1 q_weight_2d_gather=1");$finish;end
 initial begin repeat(500000)@(posedge clk);$fatal(1,"timeout state=%0d r=%0d w=%0d",payload.state_q,rbeats,wbeats);end
endmodule

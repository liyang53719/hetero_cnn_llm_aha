// SPDX-License-Identifier: Apache-2.0
// Payload-only protocol/rounding guard regression. The Matrix response is a
// directed fixture at the payload interface; this is not a Matrix arithmetic
// or full-chain numerical acceptance bench.
`timescale 1ns/1ps
module matrix_tile16_nonfinite_checker #(parameter bit CANDIDATE=1)(output logic finished=0);
  logic clk=0,rst_n=0,start=0,fp32=0;
  always #5 clk=~clk;
  logic[15:0]rows=1,columns=32;
  logic[7:0]status;
  logic rv,rr,rsv,rsr,wv,wr,mpv,mpr,mc,ml,mov,mor,done;
  logic[11:0]ra,wa;
  logic[511:0]rd,wd,mb;
  logic[255:0]ma;
  logic[63:0]be;
  logic[2:0]mctx;
  logic[16383:0]acc;
  logic[31:0]reads,writes,steps;
  bit read_pending=0,matrix_pending=0,block_writes=0;
  logic[511:0]pending_data;
  integer cycle=0,accepted_reads=0,accepted_writes=0,accepted_steps=0;
  integer final_cycle=-1,first_write_cycle=-1,write_stalls=0;
  integer cases=0,rejections=0,resets=0;
  bit active=0,held_write=0;
  logic[11:0]old_wa;logic[511:0]old_wd;logic[63:0]old_be;
  qwen2_shared_l2_matrix_tile16_payload #(.ADDR_W(12),.L2_BEATS(4096),
    .CANDIDATE_RNE_BF16(CANDIDATE)) dut(
    .clk_i(clk),.rst_ni(rst_n),.start_i(start),
    .activation_local_i(64'd0),.weight_local_i(64'd1024),.output_local_i(64'd4096),
    .depth_i(16'd2),.weight_k_stride_i(32'd64),.rows_i(rows),.columns_i(columns),
    .output_fp32_i(fp32),.status_o(status),
    .l2_rd_valid_o(rv),.l2_rd_ready_i(rr),.l2_rd_addr_o(ra),
    .l2_rsp_valid_i(rsv),.l2_rsp_ready_o(rsr),.l2_rsp_data_i(rd),
    .l2_wr_valid_o(wv),.l2_wr_ready_i(wr),.l2_wr_addr_o(wa),.l2_wr_data_o(wd),.l2_wr_be_o(be),
    .matrix_step_valid_o(mpv),.matrix_step_ready_i(mpr),.matrix_context_o(mctx),
    .matrix_clear_o(mc),.matrix_last_o(ml),.matrix_a_o(ma),.matrix_b_o(mb),
    .matrix_out_valid_i(mov),.matrix_out_ready_o(mor),.matrix_out_last_i(1'b1),.matrix_acc_i(acc),
    .done_o(done),.read_beats_o(reads),.write_beats_o(writes),.matrix_steps_o(steps));
  assign rr=!read_pending&&cycle%4!=1;
  assign rsv=read_pending&&cycle%3!=1;
  assign rd=pending_data;
  assign mpr=cycle%3!=0;
  assign mov=matrix_pending&&cycle%3!=1;
  assign wr=!block_writes&&cycle%5==0;

  function automatic logic[15:0] convert(input logic[31:0] value);
    logic[31:0]rounded;
    if(CANDIDATE&&value[30:23]==8'hff)begin
      if(value[22:0]!=0)return 16'h7fc0;
      return {value[31],8'hff,7'd0};
    end
    rounded=value+32'h7fff+32'(value[16]);
    return rounded[31:16];
  endfunction
  always @(posedge clk)begin : monitor
    integer row,half,lane;
    logic[63:0]mask;
    cycle<=cycle+1;
    if(!rst_n)begin
      read_pending<=0;matrix_pending<=0;held_write=0;
    end else begin
      if(rv&&rr)begin
        if(read_pending)$fatal(1,"duplicate read");
        read_pending<=1;
        for(integer j=0;j<32;j++)pending_data[j*16+:16]<=16'h3f00+16'(j+ra);
        accepted_reads=accepted_reads+1;
      end
      if(rsv&&rsr)read_pending<=0;
      if(mpv&&mpr)begin
        if(mctx!=0||mc!==(accepted_steps==0)||ml!==(accepted_steps==1))$fatal(1,"step metadata");
        for(integer j=0;j<16;j++)
          if(ma[j*16+:16]!==(j<rows?16'h3f00+16'(j+accepted_steps):16'd0))$fatal(1,"activation row mask");
        for(integer j=0;j<32;j++)
          if(mb[j*16+:16]!==(j<columns?16'h3f00+16'(j+16+accepted_steps):16'd0))$fatal(1,"weight column mask");
        if(ml)matrix_pending<=1;
        accepted_steps=accepted_steps+1;
      end
      if(start)begin final_cycle<=-1;first_write_cycle<=-1;end
      if(mov&&mor)begin matrix_pending<=0;final_cycle<=cycle;end
      if(held_write&&(!wv||wa!==old_wa||wd!==old_wd||be!==old_be))$fatal(1,"write changed under backpressure");
      held_write=wv&&!wr;
      if(held_write)begin old_wa=wa;old_wd=wd;old_be=be;write_stalls=write_stalls+1;end
      if(wv&&first_write_cycle<0)first_write_cycle<=cycle;
      if(wv&&wr)begin
        row=accepted_writes/((fp32&&columns>16)?2:1);
        half=accepted_writes%((fp32&&columns>16)?2:1);
        if(wa!==12'(64+accepted_writes)||row>=rows)$fatal(1,"write row/address overflow");
        mask=0;
        if(fp32)begin
          for(lane=0;lane<16;lane++)if(half*16+lane<columns)begin
            mask[lane*4+:4]=4'hf;
            if(wd[lane*32+:32]!==acc[(row*32+half*16+lane)*32+:32])$fatal(1,"FP32 payload changed");
          end
        end else begin
          for(lane=0;lane<32;lane++)if(lane<columns)begin
            mask[lane*2+:2]=2'b11;
            if(wd[lane*16+:16]!==convert(acc[(row*32+lane)*32+:32]))$fatal(1,"BF16 row/rounding mismatch");
          end
        end
        if(be!==mask)$fatal(1,"inactive-column write mask");
        accepted_writes=accepted_writes+1;
      end
      if(!active&&(rv||wv||mpv||done))$fatal(1,"payload activity while idle");
    end
  end
  task automatic prepare(input integer r,c,input bit full,
                         input integer bad_row,bad_col,input logic[31:0]bad_value);
    @(negedge clk);rows=16'(r);columns=16'(c);fp32=full;block_writes=0;
    accepted_reads=0;accepted_writes=0;accepted_steps=0;
    for(integer x=0;x<16;x++)for(integer y=0;y<32;y++)
      acc[(x*32+y)*32+:32]={(16'h3e80+16'(x*32+y)),(y%3==0?16'h8000:16'h0001)};
    if(bad_row>=0)acc[(bad_row*32+bad_col)*32+:32]=bad_value;
    active=1;start=1;
    @(negedge clk);start=0;
  endtask
  task automatic check_case(input integer r,c,input bit full,
                            input integer bad_row,bad_col,input logic[31:0]bad_value,
                            input bit bad);
    integer timeout,expected_writes,expected_latency;
    bit reject;
    prepare(r,c,full,bad_row,bad_col,bad_value);
    timeout=0;
    while(!done)begin @(negedge clk);timeout++;if(timeout>300)$fatal(1,"payload timeout");end
    reject=CANDIDATE&&!full&&bad;
    expected_writes=reject?0:r*((full&&c>16)?2:1);
    if(status!==(reject?8'd7:8'd0)||accepted_writes!=expected_writes||writes!=expected_writes)
      $fatal(1,"candidate=%0d rows=%0d badrow=%0d status=%0d writes=%0d",CANDIDATE,r,bad_row,status,accepted_writes);
    if(reads!=4||steps!=2||accepted_reads!=4||accepted_steps!=2)$fatal(1,"read/step accounting");
    if(reject&&first_write_cycle>=0)$fatal(1,"rejected tile advertised a write");
    if(!reject)begin
      expected_latency=(CANDIDATE&&!full)?r+1:2;
      if(first_write_cycle-final_cycle!=expected_latency)$fatal(1,"conversion scan/default timing drift candidate=%0d rows=%0d fp32=%0d final=%0d first=%0d expected=%0d",CANDIDATE,r,full,final_cycle,first_write_cycle,expected_latency);
    end
    cases++;if(reject)rejections++;
    @(negedge clk);active=0;
    repeat(2)@(negedge clk);
    if(status!==(reject?8'd7:8'd0))$fatal(1,"status did not latch through idle");
  endtask
  task automatic reset_case(input bit during_write);
    integer timeout;
    prepare(16,32,0,-1,0,0);
    block_writes=during_write;
    timeout=0;
    if(during_write)while(!wv)begin @(negedge clk);timeout++;if(timeout>100)$fatal(1,"write reset timeout");end
    else begin
      while(final_cycle<0)begin @(negedge clk);timeout++;if(timeout>100)$fatal(1,"scan reset timeout");end
      repeat(3)@(negedge clk);
    end
    if(accepted_writes!=0)$fatal(1,"reset target already published a write");
    rst_n=0;active=0;start=0;
    repeat(3)@(negedge clk);
    if(rv||wv||mpv||done||status!=0||reads!=0||writes!=0||steps!=0)$fatal(1,"reset did not flush payload");
    rst_n=1;block_writes=0;resets++;
    repeat(2)@(negedge clk);
    check_case(2,32,0,-1,0,0,0);
  endtask
  initial begin
    repeat(3)@(negedge clk);rst_n=1;
    check_case(1,32,0,-1,0,0,0);
    check_case(2,32,0,-1,0,0,0);
    check_case(3,17,0,-1,0,0,0);
    check_case(15,31,0,-1,0,0,0);
    check_case(16,32,0,-1,0,0,0);
    // The late rows must reject before row0 appears on the write interface.
    for(integer r=0;r<16;r++)check_case(16,32,0,r,r%2==0?31:0,
      r%6==0?32'h7f800000:r%6==1?32'hff800000:r%6==2?32'h7fc00000:
      r%6==3?32'h7f800001:r%6==4?32'h7f7fffff:32'hff7fffff,1);
    check_case(1,32,0,0,31,32'h7f800000,1);
    check_case(2,1,0,1,0,32'h7f7fffff,1);
    check_case(2,32,0,2,31,32'h7fc00000,0);
    check_case(16,1,0,15,31,32'h7f800000,0);
    check_case(3,17,0,2,17,32'h7f800001,0);
    check_case(16,32,0,15,31,32'h00000001,0);
    check_case(16,32,0,15,31,32'h7f7f0000,0);
    check_case(16,32,1,15,31,32'h7fc00000,0);
    check_case(2,16,1,1,15,32'h7f800000,0);
    if(CANDIDATE)reset_case(0);
    reset_case(1);
    if(write_stalls==0)$fatal(1,"backpressure coverage missing");
    $display("MATRIX_TILE16_NONFINITE_MODE_PASS candidate=%0d cases=%0d rejections=%0d resets=%0d write_stalls=%0d",CANDIDATE,cases,rejections,resets,write_stalls);
    finished=1;
  end
endmodule
module tb_qwen2_matrix_tile16_nonfinite;
  wire candidate_finished,legacy_finished;
  matrix_tile16_nonfinite_checker #(.CANDIDATE(1)) candidate(candidate_finished);
  matrix_tile16_nonfinite_checker #(.CANDIDATE(0)) legacy(legacy_finished);
  initial begin
    wait(candidate_finished&&legacy_finished);
    $display("MATRIX_TILE16_NONFINITE_PASS actual_payload=1 actual_converter=1 matrix_arithmetic_claimed=0");
    $finish;
  end
  initial begin #1000000;$fatal(1,"bench watchdog");end
endmodule

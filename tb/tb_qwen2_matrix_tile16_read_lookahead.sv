// SPDX-License-Identifier: Apache-2.0
// Direct payload protocol test: the real payload/converter and strict single-
// owner L2/Matrix stubs. Operand order and masked write data are checked, but
// the directed Matrix result is not a Matrix arithmetic/full-chain claim.
`timescale 1ns/1ps
module matrix_tile16_read_lookahead_checker #(
  parameter bit LOOKAHEAD=0
)(output bit finished=0);
  localparam integer ADDR_W=9,L2_BEATS=256;
  logic clk=0,rst_n=0,start=0,fp32=0;
  always #5 clk=~clk;
  logic[63:0]activation=0,weight=4096,output_base=12288;
  logic[15:0]depth=1,rows=1,columns=32;
  logic[31:0]stride=64;
  logic[7:0]status;
  logic rv,rr,rsv,rsr,wv,wr,mpv,mpr,mc,ml,mov,mor,done;
  logic[ADDR_W-1:0]ra,wa;
  logic[511:0]rd,wd,mb;
  logic[255:0]ma;
  logic[63:0]be;
  logic[2:0]mctx;
  logic[16383:0]acc;
  logic[31:0]reads,writes,steps;
  bit active=0,owner=0,matrix_pending=0,held_read=0,held_matrix=0,held_write=0;
  bit hold_requests=0,hold_responses=0,hold_matrix=0,hold_writes=0;
  logic[511:0]owner_data;
  logic[ADDR_W-1:0]saved_ra,saved_wa;
  logic[511:0]saved_a,saved_w,saved_wd;
  logic[255:0]saved_ma;
  logic[511:0]saved_mb;
  logic[63:0]saved_be;
  logic[15:0]saved_k;
  logic saved_clear,saved_last;
  integer mode=0,seed=0,cycle=0,owner_age=0,matrix_wait=0,request_wait=0;
  integer accepted_reads=0,accepted_responses=0,accepted_steps=0,accepted_writes=0;
  integer cases=0,rejections=0,resets=0,request_holds=0,matrix_holds=0,write_holds=0;
  integer prefetched=0,before_fire=0,same_fire=0,after_fire=0,early_held=0,cross_state_hold=0;
  integer case_prefetched=0,case_before=0,case_same=0,case_after=0,case_held=0;
  bit next_request_waiting=0,expect_after_fire=0;
  integer last_matrix_cycle=-1;

  qwen2_shared_l2_matrix_tile16_payload #(.ADDR_W(ADDR_W),.L2_BEATS(L2_BEATS),
    .CANDIDATE_RNE_BF16(1),.CANDIDATE_READ_LOOKAHEAD(LOOKAHEAD)) dut(
    .clk_i(clk),.rst_ni(rst_n),.start_i(start),.activation_local_i(activation),
    .weight_local_i(weight),.output_local_i(output_base),.depth_i(depth),
    .weight_k_stride_i(stride),.rows_i(rows),.columns_i(columns),.output_fp32_i(fp32),
    .status_o(status),.l2_rd_valid_o(rv),.l2_rd_ready_i(rr),.l2_rd_addr_o(ra),
    .l2_rsp_valid_i(rsv),.l2_rsp_ready_o(rsr),.l2_rsp_data_i(rd),
    .l2_wr_valid_o(wv),.l2_wr_ready_i(wr),.l2_wr_addr_o(wa),.l2_wr_data_o(wd),.l2_wr_be_o(be),
    .matrix_step_valid_o(mpv),.matrix_step_ready_i(mpr),.matrix_context_o(mctx),
    .matrix_clear_o(mc),.matrix_last_o(ml),.matrix_a_o(ma),.matrix_b_o(mb),
    .matrix_out_valid_i(mov),.matrix_out_ready_o(mor),.matrix_out_last_i(1'b1),.matrix_acc_i(acc),
    .done_o(done),.read_beats_o(reads),.write_beats_o(writes),.matrix_steps_o(steps));

  // mode0: next request precedes Matrix, with an early held response.
  // mode1: request and Matrix acceptance coincide after three blocked cycles.
  // mode2: request remains blocked across MQ -> ARQ, then is accepted later.
  // mode3: request precedes Matrix, but its response arrives after Matrix fire.
  always_comb begin
    rr=!owner&&!hold_requests;
    if(mode==1&&mpv)rr=rr&&matrix_wait>=3;
    if(mode==2&&accepted_reads>0&&accepted_reads%2==0)
      rr=rr&&!mpv&&request_wait>=4;
    mpr=!hold_matrix;
    case(mode)
      0:mpr=mpr&&matrix_wait>=6;
      1:mpr=mpr&&matrix_wait>=3;
      2:mpr=mpr&&matrix_wait>=1;
      default:mpr=mpr&&matrix_wait>=2;
    endcase
  end
  assign rsv=owner&&!hold_responses&&(mode!=3||owner_age>=7);
  assign rd=owner_data;
  assign mov=matrix_pending;
  assign wr=!hold_writes&&cycle%3==0;

  function automatic logic[15:0] a_value(input integer k,r);
    return 16'h3c00+16'(seed*3+k*17+r);
  endfunction
  function automatic logic[15:0] w_value(input integer k,c);
    return 16'hbe00+16'(seed*5+k*33+c);
  endfunction
  function automatic logic[15:0] rounded(input logic[31:0]v);
    logic[31:0]sum;
    sum=v+32'h7fff+32'(v[16]);return sum[31:16];
  endfunction

  always @(posedge clk)begin : check_protocol
    integer expected_address,k,r,h;
    logic[63:0]mask;
    cycle<=cycle+1;
    if(!rst_n)begin
      owner<=0;matrix_pending<=0;owner_age<=0;matrix_wait<=0;request_wait<=0;
      held_read=0;held_matrix=0;held_write=0;next_request_waiting=0;expect_after_fire=0;
    end else begin
      if(mpv&&!mpr)matrix_wait<=matrix_wait+1;else matrix_wait<=0;
      if(rv&&!rr)request_wait<=request_wait+1;else request_wait<=0;
      if(owner)owner_age<=owner_age+1;
      if(held_read&&(!rv||ra!==saved_ra))$fatal(1,"request changed under backpressure lookahead=%0d",LOOKAHEAD);
      if(held_matrix&&(!mpv||ma!==saved_ma||mb!==saved_mb||mc!==saved_clear||ml!==saved_last||
        dut.a_q!==saved_a||dut.w_q!==saved_w||dut.k_q!==saved_k))
        $fatal(1,"current Matrix operands/control changed while blocked lookahead=%0d",LOOKAHEAD);
      if(held_write&&(!wv||wa!==saved_wa||wd!==saved_wd||be!==saved_be))$fatal(1,"write changed while blocked");
      if(held_read&&!mpv&&next_request_waiting)begin cross_state_hold++;next_request_waiting=0;end
      held_read=rv&&!rr;
      if(held_read)begin saved_ra=ra;request_holds++;end
      held_matrix=mpv&&!mpr;
      if(held_matrix)begin
        saved_ma=ma;saved_mb=mb;saved_clear=mc;saved_last=ml;
        saved_a=dut.a_q;saved_w=dut.w_q;saved_k=dut.k_q;matrix_holds++;
      end
      held_write=wv&&!wr;
      if(held_write)begin saved_wa=wa;saved_wd=wd;saved_be=be;write_holds++;end
      if(mpv&&rsr)$fatal(1,"response ready before Matrix fire");
      if(mpv&&ml&&rv)$fatal(1,"prefetch beyond final K");
      if(!LOOKAHEAD&&mpv&&rv)$fatal(1,"default mode changed request timing");
      if(mpv&&owner&&rsv&&!rsr)begin early_held++;case_held++;end
      if(rv&&rr)begin
        if(owner)$fatal(1,"multiple outstanding reads");
        if(accepted_reads>=2*depth)$fatal(1,"extra read beyond tile boundary");
        k=accepted_reads/2;
        expected_address=accepted_reads%2==0?int'(activation>>6)+k:int'(weight>>6)+k*int'(stride>>6);
        if(ra!==ADDR_W'(expected_address)||expected_address>=L2_BEATS)
          $fatal(1,"read order/address lookahead=%0d ordinal=%0d got=%0d expected=%0d",LOOKAHEAD,accepted_reads,ra,expected_address);
        for(integer lane=0;lane<32;lane++)
          owner_data[lane*16+:16]<=accepted_reads%2==0?a_value(k,lane):w_value(k,lane);
        owner<=1;owner_age<=0;
        if(mpv)begin
          if(!LOOKAHEAD||ml||accepted_reads%2!=0||k!=accepted_steps+1)$fatal(1,"illegal read-ahead owner");
          prefetched++;case_prefetched++;
          if(mpr)begin same_fire++;case_same++;end
          else begin before_fire++;case_before++;end
        end
        if(expect_after_fire)begin
          if(mpv||cycle<=last_matrix_cycle)$fatal(1,"late request coverage invalid");
          after_fire++;case_after++;expect_after_fire=0;
        end
        accepted_reads++;
      end
      if(rsv&&rsr)begin
        if(!owner)$fatal(1,"response without owner");
        owner<=0;accepted_responses++;
      end
      if(mpv&&mpr)begin
        if(mctx!=0||mc!==(accepted_steps==0)||ml!==(accepted_steps==depth-1))$fatal(1,"Matrix metadata/order");
        if(accepted_responses!=2*(accepted_steps+1))$fatal(1,"Matrix used unconsumed/wrong operands");
        for(integer lane=0;lane<16;lane++)
          if(ma[lane*16+:16]!==(lane<rows?a_value(accepted_steps,lane):16'd0))$fatal(1,"activation operand order/mask");
        for(integer lane=0;lane<32;lane++)
          if(mb[lane*16+:16]!==(lane<columns?w_value(accepted_steps,lane):16'd0))$fatal(1,"weight operand order/mask");
        if(rv&&!rr)begin next_request_waiting=1;expect_after_fire=1;end
        if(ml)matrix_pending<=1;
        accepted_steps++;last_matrix_cycle=cycle;
      end
      if(mov&&mor)matrix_pending<=0;
      if(wv||done)begin
        if(owner||rv||rsv||dut.next_a_pending_q)$fatal(1,"outstanding read leaked into write/done");
      end
      if(wv&&wr)begin
        r=accepted_writes/((fp32&&columns>16)?2:1);
        h=accepted_writes%((fp32&&columns>16)?2:1);
        if(wa!==ADDR_W'((output_base>>6)+64'(accepted_writes))||r>=rows)$fatal(1,"write address/row order");
        mask=0;
        if(fp32)begin
          for(integer lane=0;lane<16;lane++)if(h*16+lane<columns)begin
            mask[lane*4+:4]=4'hf;
            if(wd[lane*32+:32]!==acc[(r*32+h*16+lane)*32+:32])$fatal(1,"FP32 write fixture");
          end
        end else begin
          for(integer lane=0;lane<32;lane++)if(lane<columns)begin
            mask[lane*2+:2]=2'b11;
            if(wd[lane*16+:16]!==rounded(acc[(r*32+lane)*32+:32]))$fatal(1,"BF16 write fixture");
          end
        end
        if(be!==mask)$fatal(1,"write lane mask");
        accepted_writes++;
      end
      if(!active&&(rv||wv||mpv||done||owner||dut.next_a_pending_q))$fatal(1,"tile work leaked into idle");
    end
  end

  task automatic prepare(input integer d,r,c,m,input bit full=0);
    @(negedge clk);
    if(owner||matrix_pending)$fatal(1,"previous owner not drained");
    depth=16'(d);rows=16'(r);columns=16'(c);mode=m;fp32=full;seed++;
    activation=m==3?64'(L2_BEATS-d)*64:0;weight=4096;output_base=12288;stride=32'((m+1)*64);
    hold_requests=0;hold_responses=0;hold_matrix=0;hold_writes=0;
    accepted_reads=0;accepted_responses=0;accepted_steps=0;accepted_writes=0;
    case_prefetched=0;case_before=0;case_same=0;case_after=0;case_held=0;
    for(integer row=0;row<16;row++)for(integer col=0;col<32;col++)
      acc[(row*32+col)*32+:32]={(16'h3e00+16'(row*32+col)),(col%2?16'h8000:16'h0001)};
    active=1;
  endtask
  task automatic launch;
    start=1;@(negedge clk);start=0;
  endtask
  task automatic finish_case(input integer expected_status=0);
    integer timeout,expected_writes;
    timeout=0;
    while(!done)begin @(negedge clk);timeout++;if(timeout>2000)$fatal(1,"timeout lookahead=%0d mode=%0d K=%0d",LOOKAHEAD,mode,depth);end
    expected_writes=expected_status?0:int'(rows)*((fp32&&columns>16)?2:1);
    if(status!==8'(expected_status)||accepted_writes!=expected_writes||writes!=32'(expected_writes))$fatal(1,"status/write count");
    if(expected_status!=5)begin
      if(accepted_reads!=2*depth||accepted_responses!=2*depth||reads!=32'(2*depth)||accepted_steps!=depth||steps!=32'(depth))
        $fatal(1,"owner/response/step accounting");
    end else if(accepted_reads||accepted_responses||accepted_steps||reads||steps)$fatal(1,"illegal tile performed work");
    cases++;if(expected_status)rejections++;
    @(negedge clk);active=0;
    repeat(2)@(negedge clk);
    if(status!==8'(expected_status))$fatal(1,"status did not latch through idle");
  endtask
  task automatic good_case(input integer d,r,c,m,input bit full=0);
    prepare(d,r,c,m,full);launch();finish_case();
    if(LOOKAHEAD)begin
      if(m==0&&(case_before!=d-1||case_held<(d-1)))$fatal(1,"early held response coverage");
      if(m==1&&case_same!=d-1)$fatal(1,"simultaneous acceptance coverage");
      if(m==2&&(case_prefetched!=0||case_after!=d-1))$fatal(1,"MQ to ARQ request hold coverage");
      if(m==3&&(case_before!=d-1||case_held!=0))$fatal(1,"late response coverage");
    end else if(case_prefetched||case_held)$fatal(1,"default mode speculated");
  endtask
  task automatic bad_case(input integer kind);
    prepare(2,3,17,0);
    case(kind)
      0:depth=0;1:rows=0;2:rows=17;3:columns=0;4:columns=33;
      5:activation=1;6:weight=4097;7:output_base=12289;
      8:stride=0;9:stride=65;
      10:activation=64'(L2_BEATS-1)*64;
      11:weight=64'(L2_BEATS-1)*64;
      12:output_base=64'(L2_BEATS-2)*64;
    endcase
    launch();finish_case(5);
    good_case(2,3,17,kind%4);
  endtask
  task automatic reset_case(input integer point);
    integer timeout;
    prepare(5,3,17,0);
    if(point==0)hold_requests=1;
    if(point==1)hold_responses=1;
    if(point==2||point==3)hold_matrix=1;
    if(point==4)hold_writes=1;
    launch();timeout=0;
    case(point)
      0:while(!rv)begin @(negedge clk);timeout++;if(timeout>100)$fatal(1,"reset request target");end
      1:while(!owner)begin @(negedge clk);timeout++;if(timeout>100)$fatal(1,"reset response target");end
      2:begin
        while(!mpv)begin @(negedge clk);timeout++;if(timeout>100)$fatal(1,"reset Matrix target");end
        hold_requests=1;
      end
      3:begin
        while(!mpv)begin @(negedge clk);timeout++;if(timeout>100)$fatal(1,"reset prefetch target");end
        if(LOOKAHEAD)begin
          while(!rsv)begin @(negedge clk);timeout++;if(timeout>100)$fatal(1,"reset pending target");end
          if(!dut.next_a_pending_q||rsr)$fatal(1,"reset missed pending lookahead");
        end
      end
      4:while(!wv)begin @(negedge clk);timeout++;if(timeout>300)$fatal(1,"reset write target");end
    endcase
    repeat(2)@(negedge clk);
    rst_n=0;active=0;start=0;
    // The fabric reset accompanies payload reset and flushes the held owner.
    repeat(3)@(negedge clk);
    if(rv||wv||mpv||done||rsr||status||reads||writes||steps||owner||dut.next_a_pending_q)$fatal(1,"reset leakage");
    rst_n=1;resets++;repeat(2)@(negedge clk);
    good_case(2,3,17,point%4);
  endtask

  initial begin
    repeat(3)@(negedge clk);rst_n=1;
    for(integer m=0;m<4;m++)begin
      good_case(1,1,1,m);
      good_case(2,3,17,m);
      good_case(5,15,31,m);
      good_case(31,16,32,m,m==3);
    end
    for(integer kind=0;kind<13;kind++)bad_case(kind);
    // Late active-row nonfinite rejection must occur before any tile write.
    prepare(5,3,17,0);acc[(2*32+16)*32+:32]=32'h7f800000;launch();finish_case(7);
    good_case(5,3,17,0);
    // Same inactive-column value is masked and must not reject the tile.
    prepare(5,3,17,1);acc[(2*32+17)*32+:32]=32'h7fc00000;launch();finish_case();
    for(integer point=0;point<5;point++)reset_case(point);
    if(request_holds==0||matrix_holds==0||write_holds==0)$fatal(1,"missing backpressure");
    if(LOOKAHEAD&&(prefetched==0||before_fire==0||same_fire==0||after_fire==0||early_held==0||cross_state_hold==0))$fatal(1,"missing lookahead corners");
    if(!LOOKAHEAD&&(prefetched||before_fire||same_fire||after_fire||early_held||cross_state_hold))$fatal(1,"legacy protocol drift");
    $display("MATRIX_TILE16_READ_LOOKAHEAD_MODE_PASS lookahead=%0d cases=%0d rejections=%0d resets=%0d prefetched=%0d before=%0d same=%0d after=%0d held=%0d cross=%0d request_stalls=%0d matrix_stalls=%0d write_stalls=%0d",LOOKAHEAD,cases,rejections,resets,prefetched,before_fire,same_fire,after_fire,early_held,cross_state_hold,request_holds,matrix_holds,write_holds);
    finished=1;
  end
endmodule
module tb_qwen2_matrix_tile16_read_lookahead;
  wire baseline_done,candidate_done;
  matrix_tile16_read_lookahead_checker #(.LOOKAHEAD(0)) baseline(baseline_done);
  matrix_tile16_read_lookahead_checker #(.LOOKAHEAD(1)) candidate(candidate_done);
  initial begin
    wait(baseline_done&&candidate_done);
    $display("MATRIX_TILE16_READ_LOOKAHEAD_PASS actual_payload=1 strict_owner=1 operand_sequence=1 matrix_arithmetic_claimed=0");
    $finish;
  end
  initial begin #2000000;$fatal(1,"bench watchdog");end
endmodule

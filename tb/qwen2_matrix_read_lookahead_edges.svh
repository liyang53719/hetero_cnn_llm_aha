// SPDX-License-Identifier: Apache-2.0
// Supplemental hooks inserted into an otherwise unchanged transient copy of
// the real tile16 bench. No arithmetic, transport, or source checks disabled.
  bit edge_active=0,edge_fault=0,edge_requested=0,edge_held=0,edge_error=0;
  logic[772:0] edge_operands;
  integer edge_request_cycle=0,edge_held_cycle=0,edge_error_cycle=0;

  task automatic edge_record(input string phase);
    $fdisplay(trace_fd,"{\"event\":\"lookahead_edge\",\"transaction\":%0d,\"cycle\":%0d,\"phase\":\"%s\",\"inputs\":%0d,\"outputs\":%0d,\"k\":%0d,\"next_a_pending\":%0d,\"read_owner\":%0d,\"response_valid\":%0d,\"response_ready\":%0d,\"matrix_valid\":%0d,\"matrix_ready\":%0d}",transaction,cycle,phase,matrix_inputs,matrix_outputs,`CHAIN.payload.k_q,`CHAIN.payload.next_a_pending_q,rp,rsv,rsr,`CHAIN.mpv,`CHAIN.mpr);
  endtask
  task automatic edge_read_request(input integer address,regid);
    if(edge_active&&address==act_base+128)begin
      if(edge_requested||regid!=5||!`CHAIN.payload.next_a_request||
         `CHAIN.payload.k_q!=1||!`CHAIN.mpv||`CHAIN.mpr||matrix_inputs!=1||matrix_outputs!=0)
        $fatal(1,"A2 was not accepted during blocked Matrix1");
      edge_requested=1;edge_request_cycle=cycle;
      edge_operands={`CHAIN.mctx,`CHAIN.mc,`CHAIN.ml,`CHAIN.ma,`CHAIN.mb};
      edge_record("request");
    end
  endtask
  task automatic edge_read_response;
    if(edge_active&&rse)begin
      if(!edge_fault||!edge_requested||!edge_held||edge_error||pending_read_addr!=act_base+128||
         cycle<=edge_held_cycle||matrix_inputs!=2||matrix_outputs!=1||`CHAIN.payload.k_q!=2)
        $fatal(1,"lookahead error did not follow held response and Matrix1 release");
      edge_error=1;edge_error_cycle=cycle;edge_record("error");
    end
  endtask
  task automatic edge_tick;
    if(edge_active&&edge_error)begin
      if(rv||wv||av||dqv||matrix_accept||matrix_output)
        $fatal(1,"work escaped after fatal lookahead response");
    end
  endtask
  task automatic edge_done;
    if(edge_active)begin
      if(!edge_fault||!edge_error||status!=8||matrix_inputs!=2||matrix_outputs!=1||steps!=2||
         read_requests!=5||read_responses!=5||write_requests||write_acks||rp||wp||ap||dp||
         `CHAIN.payload.next_a_pending_q||`CHAIN.engine_rst_n)
        $fatal(1,"fault terminal failed exact abort/drain accounting");
      edge_record("done");
    end
  endtask
  task automatic edge_wait_held;
    integer timeout;
    timeout=0;
    while(!(edge_requested&&`CHAIN.payload.next_a_pending_q&&rsv&&!rsr))begin
      @(negedge clk);timeout++;
      if(timeout>20000)$fatal(1,"no actual early held A2 response");
    end
    if(!rp||pending_read_addr!=act_base+128||!`CHAIN.mpv||`CHAIN.payload.k_q!=1||
       matrix_inputs!=1||matrix_outputs!=0||done||status!=0||rse!==edge_fault||
       {`CHAIN.mctx,`CHAIN.mc,`CHAIN.ml,`CHAIN.ma,`CHAIN.mb}!==edge_operands)
      $fatal(1,"held A2 response changed current operands or escaped early");
    edge_held=1;edge_held_cycle=cycle;edge_record("held");
  endtask
  task automatic edge_prepare(input bit fault);
    setup_case(1,1);
    edge_active=1;edge_fault=fault;edge_requested=0;edge_held=0;edge_error=0;
    edge_request_cycle=0;edge_held_cycle=0;edge_error_cycle=0;
    if(fault)fault_read_region=5;
    launch(fault?"lookahead_A2_error":"reset_lookahead_A2",1);
  endtask
  task automatic edge_fault_case;
    edge_prepare(1);edge_wait_held();wait_terminal(8);
    if(!fault_injected||!edge_error||!ready||status!=8||`CHAIN.payload.next_a_pending_q)
      $fatal(1,"lookahead fault did not return ready with sticky status");
    repeat(12)@(negedge clk);
    edge_active=0;edge_fault=0;fault_count++;
    $display("MATRIX_LOOKAHEAD_EDGE_FAULT_PASS inputs=2 outputs=1 aborted_inflight=1 reads=5 responses=5 writes=0 status=8 held_before_release=1");
  endtask
  task automatic edge_reset_case;
    edge_prepare(0);edge_wait_held();
    if(metrics_fd)emit_metrics(0);
    // Reset now, before the next Matrix1 handshake edge, including the fabric.
    rst_n=0;start=0;
    repeat(4)@(negedge clk);
    active=0;edge_active=0;rst_n=1;
    repeat(12)@(negedge clk);
    if(!ready||done||rv||wv||av||dqv||dp||ap||rp||wp||matrix_accept||matrix_output||
       completed_heads||completed_tokens||steps||status||`CHAIN.payload.next_a_pending_q)
      $fatal(1,"reset leaked early-response owner or Matrix work");
    if(matrix_inputs!=1||matrix_outputs!=0||read_requests!=5||read_responses!=4||write_requests)
      $fatal(1,"reset did not hit exact early-response target");
    host_mode=1;
    $fdisplay(trace_fd,"{\"event\":\"reset_flush\",\"transaction\":%0d,\"stage\":8}",transaction);
    reset_count++;
    $display("MATRIX_LOOKAHEAD_EDGE_RESET_PASS inputs=1 outputs=0 aborted_inflight=1 reads=5 responses=4 discarded_read=1 writes=0 held_before_release=1");
  endtask

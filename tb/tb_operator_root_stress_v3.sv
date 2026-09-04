`timescale 1ns/1ps
`ifndef ROOT_MODULE
 `define ROOT_MODULE HeteroTokenEmbeddingPrimitiveV3
`endif
`ifndef EXPECTED_PHASES
 `define EXPECTED_PHASES 1
`endif

module tb_operator_root_stress_v3;
  logic clock,reset;
  logic launch_valid,launch_ready,micro_valid,micro_ready;
  logic completion_valid,completion_ready,completion_predicate;
  logic result_valid,result_ready,busy,protocol_error;
  logic [7:0] micro_kind,micro_phase,micro_mode,completion_phase,completion_status,result_status,result_phases;
  logic [15:0] micro_flags,micro_tag,micro_m,micro_n,micro_k,micro_index0,micro_index1,completion_tag,result_tag;
  logic [23:0] micro_src0,micro_src1,micro_src2,micro_dst;
  logic [23:0] descriptors [0:15];
  logic [15:0] dimensions [0:7];
  logic [31:0] random_state;
  integer seed,transaction,phase,stall_cycles;
  logic mtp_rollback;

  initial begin clock=0;reset=1;end
  always #1 clock=~clock;

  `ROOT_MODULE dut(
    .clock,.reset,
    .io_launch_ready(launch_ready),.io_launch_valid(launch_valid),
    .io_launch_bits_descriptors_0(descriptors[0]),.io_launch_bits_descriptors_1(descriptors[1]),
    .io_launch_bits_descriptors_2(descriptors[2]),.io_launch_bits_descriptors_3(descriptors[3]),
    .io_launch_bits_descriptors_4(descriptors[4]),.io_launch_bits_descriptors_5(descriptors[5]),
    .io_launch_bits_descriptors_6(descriptors[6]),.io_launch_bits_descriptors_7(descriptors[7]),
    .io_launch_bits_descriptors_8(descriptors[8]),.io_launch_bits_descriptors_9(descriptors[9]),
    .io_launch_bits_descriptors_10(descriptors[10]),.io_launch_bits_descriptors_11(descriptors[11]),
    .io_launch_bits_descriptors_12(descriptors[12]),.io_launch_bits_descriptors_13(descriptors[13]),
    .io_launch_bits_descriptors_14(descriptors[14]),.io_launch_bits_descriptors_15(descriptors[15]),
    .io_launch_bits_dimensions_0(dimensions[0]),.io_launch_bits_dimensions_1(dimensions[1]),
    .io_launch_bits_dimensions_2(dimensions[2]),.io_launch_bits_dimensions_3(dimensions[3]),
    .io_launch_bits_dimensions_4(dimensions[4]),.io_launch_bits_dimensions_5(dimensions[5]),
    .io_launch_bits_dimensions_6(dimensions[6]),.io_launch_bits_dimensions_7(dimensions[7]),
    .io_launch_bits_tag(transaction[15:0]),.io_launch_bits_mode(seed[7:0]),
    .io_microOp_ready(micro_ready),.io_microOp_valid(micro_valid),
    .io_microOp_bits_kind(micro_kind),.io_microOp_bits_flags(micro_flags),
    .io_microOp_bits_phase(micro_phase),.io_microOp_bits_tag(micro_tag),.io_microOp_bits_mode(micro_mode),
    .io_microOp_bits_src0(micro_src0),.io_microOp_bits_src1(micro_src1),
    .io_microOp_bits_src2(micro_src2),.io_microOp_bits_dst(micro_dst),
    .io_microOp_bits_m(micro_m),.io_microOp_bits_n(micro_n),.io_microOp_bits_k(micro_k),
    .io_microOp_bits_index0(micro_index0),.io_microOp_bits_index1(micro_index1),
    .io_completion_ready(completion_ready),.io_completion_valid(completion_valid),
    .io_completion_bits_tag(completion_tag),.io_completion_bits_phase(completion_phase),
    .io_completion_bits_status(completion_status),.io_completion_bits_predicate(completion_predicate),
    .io_result_ready(result_ready),.io_result_valid(result_valid),.io_result_bits_tag(result_tag),
    .io_result_bits_status(result_status),.io_result_bits_completedPhases(result_phases),
    .io_busy(busy),.io_protocolError(protocol_error));

  function automatic [31:0] advance_random(input [31:0] value);
    reg [31:0] x;
    begin
      x=value;x=x^(x<<13);x=x^(x>>17);x=x^(x<<5);
      advance_random=x;
    end
  endfunction

  task automatic random_stall(input integer maximum);
    begin
      random_state=advance_random(random_state);
      stall_cycles=random_state%(maximum+1);
      repeat(stall_cycles) @(posedge clock);
    end
  endtask

  task automatic check_micro_stable(input integer cycles);
    logic [231:0] snapshot;
    begin
      snapshot={micro_kind,micro_flags,micro_phase,micro_tag,micro_mode,micro_src0,micro_src1,micro_src2,micro_dst,micro_m,micro_n,micro_k,micro_index0,micro_index1};
      repeat(cycles) begin
        @(posedge clock);
        if(!micro_valid||{micro_kind,micro_flags,micro_phase,micro_tag,micro_mode,micro_src0,micro_src1,micro_src2,micro_dst,micro_m,micro_n,micro_k,micro_index0,micro_index1}!==snapshot)
          $fatal(1,"micro-op changed under backpressure tx=%0d phase=%0d",transaction,phase);
      end
    end
  endtask

  initial begin
    if(!$value$plusargs("SEED=%d",seed))seed=1;
    random_state=32'h9e3779b9^seed;launch_valid=0;micro_ready=0;completion_valid=0;
    completion_tag=0;completion_phase=0;completion_status=0;completion_predicate=0;result_ready=0;
    for(integer i=0;i<16;i++)descriptors[i]=24'h100+i;
    for(integer i=0;i<8;i++)dimensions[i]=16'h20+i;
    repeat(4)@(posedge clock);@(negedge clock);reset=0;
    for(transaction=0;transaction<100;transaction++)begin
      random_stall(5);@(negedge clock);launch_valid=1;
      while(!launch_ready)@(posedge clock);
      @(posedge clock);@(negedge clock);launch_valid=0;mtp_rollback=0;
      for(phase=0;phase<`EXPECTED_PHASES;phase++)begin
        while(!micro_valid)@(posedge clock);
        @(negedge clock);
        if(micro_phase!==phase[7:0]||micro_tag!==transaction[15:0])$fatal(1,"micro identity tx=%0d phase=%0d",transaction,phase);
        random_state=advance_random(random_state);stall_cycles=random_state%8;
        check_micro_stable(stall_cycles);@(negedge clock);micro_ready=1;
        @(posedge clock);@(negedge clock);micro_ready=0;
        random_stall(7);@(negedge clock);
        completion_tag=transaction[15:0];completion_phase=phase[7:0];completion_status=0;
        random_state=advance_random(random_state);completion_predicate=random_state[0];
        if(phase==0)mtp_rollback=completion_predicate;
        if(`EXPECTED_PHASES==4&&phase==3)begin
          if(micro_kind!==8'h83||micro_flags[9]===micro_flags[14]||micro_flags[14]!==mtp_rollback)
            $fatal(1,"conditional MTP flags tx=%0d rollback=%0d flags=%h",transaction,mtp_rollback,micro_flags);
        end
        completion_valid=1;while(!completion_ready)@(posedge clock);
        @(posedge clock);@(negedge clock);completion_valid=0;
      end
      while(!result_valid)@(posedge clock);@(negedge clock);
      random_state=advance_random(random_state);stall_cycles=random_state%8;
      repeat(stall_cycles)begin @(posedge clock);if(!result_valid||result_tag!==transaction[15:0]||result_status!==0||result_phases!==`EXPECTED_PHASES)$fatal(1,"result changed under backpressure");end
      @(negedge clock);result_ready=1;@(posedge clock);@(negedge clock);result_ready=0;
      if(protocol_error)$fatal(1,"protocol error tx=%0d",transaction);
    end
    $display("ROOT_STRESS_V3_PASS seed=%0d transactions=100 phases=%0d",seed,`EXPECTED_PHASES);
    $finish;
  end

  initial begin repeat(5000000)@(posedge clock);$fatal(1,"timeout");end
endmodule

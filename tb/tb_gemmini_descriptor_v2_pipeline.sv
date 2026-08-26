`timescale 1ns/1ps
module tb_gemmini_descriptor_v2_pipeline;
  logic clk=0,rst_n=0;always #5 clk=~clk;
  integer cycles,issued,base_issued,expected_count,rejects;logic expect_reject,force_scale_error;
  logic cmd_valid,cmd_ready;logic[127:0]cmd_data,cmd_mem[0:0];
  logic dreq_valid,dreq_ready;logic[23:0]dreq_index;logic[63:0]dreq_addr;
  logic drsp_valid,drsp_ready,drsp_error;logic[127:0]drsp_data;
  logic[127:0]desc_mem[0:63];logic present_mem[0:63];logic desc_pending;logic[23:0]desc_index_q;
  logic snap_valid,snap_ready,snap_legal;logic[7:0]snap_status;logic[127:0]snap_cmd;logic[6:0]snap_count;
  logic rec_valid,rec_ready;logic[1:0]rec_chain;logic[23:0]rec_index;logic[127:0]rec_data;logic rec_first,rec_last;
  logic ctx_valid,ctx_ready,ctx_legal;logic[7:0]ctx_status;logic[127:0]ctx_cmd;
  logic[255:0]ctx_addr;logic[287:0]ctx_shape,ctx_stride;logic[47:0]ctx_meta;
  logic[71:0]ctx_op,ctx_aux,ctx_conv;logic ctx_conv_valid;logic[1:0]ctx_quant_valid;logic[143:0]ctx_quant;
  logic sreq_valid,sreq_ready;logic[47:0]sreq_addr;logic srsp_valid,srsp_ready,srsp_error;logic[31:0]srsp_data;logic scale_pending;
  logic op_valid,op_ready,op_first,op_last,op_legal;logic[7:0]op_status;logic[15:0]op_event;
  logic[6:0]op_funct;logic[63:0]op_rs1,op_rs2;logic[134:0]expected_ops[0:63];

  matrix_descriptor_v2_snapshot u_snapshot(
    .clk_i(clk),.rst_ni(rst_n),.cmd_valid_i(cmd_valid),.cmd_ready_o(cmd_ready),.cmd_data_i(cmd_data),
    .descriptor_base_i(64'h4000),.descriptor_req_valid_o(dreq_valid),.descriptor_req_ready_i(dreq_ready),
    .descriptor_req_index_o(dreq_index),.descriptor_req_byte_addr_o(dreq_addr),
    .descriptor_rsp_valid_i(drsp_valid),.descriptor_rsp_ready_o(drsp_ready),
    .descriptor_rsp_data_i(drsp_data),.descriptor_rsp_error_i(drsp_error),
    .snapshot_valid_o(snap_valid),.snapshot_ready_i(snap_ready),.snapshot_legal_o(snap_legal),
    .snapshot_status_o(snap_status),.snapshot_command_o(snap_cmd),.snapshot_record_count_o(snap_count),
    .record_valid_o(rec_valid),.record_ready_i(rec_ready),.record_chain_o(rec_chain),
    .record_index_o(rec_index),.record_data_o(rec_data),.record_first_o(rec_first),.record_last_o(rec_last));
  matrix_descriptor_v2_decode u_decode(
    .clk_i(clk),.rst_ni(rst_n),.snapshot_valid_i(snap_valid),.snapshot_ready_o(snap_ready),
    .snapshot_legal_i(snap_legal),.snapshot_status_i(snap_status),.snapshot_command_i(snap_cmd),
    .snapshot_record_count_i(snap_count),.record_valid_i(rec_valid),.record_ready_o(rec_ready),
    .record_chain_i(rec_chain),.record_index_i(rec_index),.record_data_i(rec_data),
    .record_first_i(rec_first),.record_last_i(rec_last),.context_valid_o(ctx_valid),
    .context_ready_i(ctx_ready),.context_legal_o(ctx_legal),.context_status_o(ctx_status),
    .context_command_o(ctx_cmd),.tensor_addr_o(ctx_addr),.tensor_shape_o(ctx_shape),
    .tensor_stride_o(ctx_stride),.tensor_meta_o(ctx_meta),.matrix_op_payload_o(ctx_op),
    .matrix_aux_payload_o(ctx_aux),.conv_valid_o(ctx_conv_valid),.conv_payload_o(ctx_conv),
    .quant_valid_o(ctx_quant_valid),.quant_payload_o(ctx_quant));
  gemmini_descriptor_v2_emitter u_emitter(
    .clk_i(clk),.rst_ni(rst_n),.context_valid_i(ctx_valid),.context_ready_o(ctx_ready),
    .context_legal_i(ctx_legal),.context_status_i(ctx_status),.context_command_i(ctx_cmd),
    .tensor_addr_i(ctx_addr),.tensor_shape_i(ctx_shape),.tensor_stride_i(ctx_stride),
    .tensor_meta_i(ctx_meta),.matrix_op_payload_i(ctx_op),.matrix_aux_payload_i(ctx_aux),
    .conv_valid_i(ctx_conv_valid),.conv_payload_i(ctx_conv),.quant_valid_i(ctx_quant_valid),
    .quant_payload_i(ctx_quant),.scale_req_valid_o(sreq_valid),.scale_req_ready_i(sreq_ready),
    .scale_req_addr_o(sreq_addr),.scale_rsp_valid_i(srsp_valid),.scale_rsp_ready_o(srsp_ready),
    .scale_rsp_data_i(srsp_data),.scale_rsp_error_i(srsp_error),.op_valid_o(op_valid),
    .op_ready_i(op_ready),.op_first_o(op_first),.op_last_o(op_last),.op_legal_o(op_legal),
    .op_status_o(op_status),.op_event_id_o(op_event),.op_funct_o(op_funct),.op_rs1_o(op_rs1),.op_rs2_o(op_rs2));

  assign dreq_ready=!desc_pending&&(cycles%3)!=1;assign drsp_valid=desc_pending;
  assign drsp_data=desc_index_q<64?desc_mem[desc_index_q[5:0]]:'0;
  assign drsp_error=desc_index_q>=64||!present_mem[desc_index_q[5:0]];
  assign sreq_ready=!scale_pending;assign srsp_valid=scale_pending;assign srsp_data=32'h3f000000;
  assign srsp_error=force_scale_error;
  assign op_ready=(cycles%4)!=1;

  always @(posedge clk)begin
    if(!rst_n)begin cycles<=0;issued<=0;rejects<=0;desc_pending<=0;scale_pending<=0;end else begin
      cycles<=cycles+1;
      if(dreq_valid&&dreq_ready)begin desc_pending<=1;desc_index_q<=dreq_index;end
      if(drsp_valid&&drsp_ready)desc_pending<=0;
      if(sreq_valid&&sreq_ready)begin
        if(sreq_addr!=48'h9000)$fatal(1,"scale address mismatch");scale_pending<=1;
      end
      if(srsp_valid&&srsp_ready)scale_pending<=0;
      if(op_valid&&op_ready)begin
        if(expect_reject)begin
          if(op_legal||op_status==0||!op_first||!op_last)$fatal(1,"reject envelope mismatch");
          rejects<=rejects+1;
        end else begin
        if(!op_legal||op_status!=0||op_event!=16'h1234)
          $fatal(1,"unexpected illegal op legal=%0b status=%0d event=%h mode=%0d m=%0d n=%0d k=%0d",
                 op_legal,op_status,op_event,u_emitter.mode_q,u_emitter.m,u_emitter.n,u_emitter.k);
        if({op_funct,op_rs1,op_rs2}!==expected_ops[issued-base_issued])
          $fatal(1,"op mismatch case_base=%0d index=%0d got=%h expected=%h",
                 base_issued,issued-base_issued,{op_funct,op_rs1,op_rs2},expected_ops[issued-base_issued]);
        if(op_first!==(issued==base_issued)||op_last!==(issued-base_issued==expected_count-1))
          $fatal(1,"first/last mismatch");
        issued<=issued+1;
        end
      end
    end
  end

  task automatic run_case(input string prefix,input integer count);
    string desc_file,present_file,command_file,ops_file;
    begin
      desc_file={"tests/vectors/gemmini_",prefix,"_desc.memh"};
      present_file={"tests/vectors/gemmini_",prefix,"_present.memh"};
      command_file={"tests/vectors/gemmini_",prefix,"_command.memh"};
      ops_file={"tests/vectors/gemmini_",prefix,".memh"};
      for(int x=0;x<64;x++)begin desc_mem[x]=0;present_mem[x]=0;expected_ops[x]=0;end
      $readmemh(desc_file,desc_mem);$readmemh(present_file,present_mem);
      $readmemh(command_file,cmd_mem,0,0);$readmemh(ops_file,expected_ops,0,count-1);
      wait(cmd_ready);@(negedge clk);base_issued=issued;expected_count=count;cmd_data=cmd_mem[0];cmd_valid=1;
      do @(posedge clk);while(!cmd_ready);@(negedge clk);cmd_valid=0;
      wait(issued==base_issued+count);@(negedge clk);
    end
  endtask
  task automatic run_reject(input string prefix,input integer kind);
    string desc_file,present_file,command_file;integer prior;
    begin
      desc_file={"tests/vectors/gemmini_",prefix,"_desc.memh"};
      present_file={"tests/vectors/gemmini_",prefix,"_present.memh"};
      command_file={"tests/vectors/gemmini_",prefix,"_command.memh"};
      for(int x=0;x<64;x++)begin desc_mem[x]=0;present_mem[x]=0;end
      $readmemh(desc_file,desc_mem);$readmemh(present_file,present_mem);$readmemh(command_file,cmd_mem,0,0);
      if(kind==0)desc_mem[5][125:118]=0;
      if(kind==1)present_mem[30]=0;
      force_scale_error=kind==2;expect_reject=1;prior=rejects;
      wait(cmd_ready);@(negedge clk);cmd_data=cmd_mem[0];cmd_valid=1;
      do @(posedge clk);while(!cmd_ready);@(negedge clk);cmd_valid=0;
      wait(rejects==prior+1);@(negedge clk);expect_reject=0;force_scale_error=0;
    end
  endtask
  initial begin
    cmd_valid=0;cmd_data=0;expect_reject=0;force_scale_error=0;repeat(3)@(posedge clk);rst_n=1;
    run_case("multi_tile_os",36);run_case("loop_ws",11);
    run_case("conv_identity",9);run_case("conv_relu_requant",9);
    run_reject("multi_tile_os",0);run_reject("multi_tile_os",1);run_reject("conv_relu_requant",2);
    $display("GEMMINI_DESCRIPTOR_V2_PIPELINE_PASS cycles=%0d issued=%0d rejects=%0d",cycles,issued,rejects);$finish;
  end
  initial begin repeat(10000)@(posedge clk);$fatal(1,"timeout");end
endmodule

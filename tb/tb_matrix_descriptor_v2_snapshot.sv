`timescale 1ns/1ps
module tb_matrix_descriptor_v2_snapshot;
  logic clk=0,rst_n=0;always #5 clk=~clk;
  integer cycles,headers,replayed,contexts,seed;
  logic cmd_valid,cmd_ready;logic[127:0]cmd_data;
  logic req_valid,req_ready;logic[23:0]req_index;logic[63:0]req_addr;
  logic rsp_valid,rsp_ready,rsp_error;logic[127:0]rsp_data;
  logic snap_valid,snap_ready,snap_legal;logic[7:0]snap_status;logic[127:0]snap_cmd;logic[6:0]snap_count;
  logic rec_valid,rec_ready;logic[1:0]rec_chain;logic[23:0]rec_index;logic[127:0]rec_data;logic rec_first,rec_last;
  logic[127:0]mem[0:63];logic present[0:63],pending;logic[23:0]pending_index;
  logic[127:0]held_data;logic[23:0]held_index;logic held;
  logic d_snap_valid,d_snap_ready,d_rec_valid,d_rec_ready,ctx_valid,ctx_ready,ctx_legal;
  logic[7:0]ctx_status;logic[127:0]ctx_cmd;logic[255:0]ctx_addr;
  logic[287:0]ctx_shape,ctx_stride;logic[47:0]ctx_meta;logic[71:0]ctx_op,ctx_aux,ctx_conv;
  logic ctx_conv_valid;logic[1:0]ctx_quant_valid;logic[143:0]ctx_quant;

  matrix_descriptor_v2_snapshot dut(
    .clk_i(clk),.rst_ni(rst_n),.cmd_valid_i(cmd_valid),.cmd_ready_o(cmd_ready),.cmd_data_i(cmd_data),
    .descriptor_base_i(64'h4000),.descriptor_req_valid_o(req_valid),.descriptor_req_ready_i(req_ready),
    .descriptor_req_index_o(req_index),.descriptor_req_byte_addr_o(req_addr),
    .descriptor_rsp_valid_i(rsp_valid),.descriptor_rsp_ready_o(rsp_ready),
    .descriptor_rsp_data_i(rsp_data),.descriptor_rsp_error_i(rsp_error),
    .snapshot_valid_o(snap_valid),.snapshot_ready_i(snap_ready),.snapshot_legal_o(snap_legal),
    .snapshot_status_o(snap_status),.snapshot_command_o(snap_cmd),.snapshot_record_count_o(snap_count),
    .record_valid_o(rec_valid),.record_ready_i(rec_ready),.record_chain_o(rec_chain),
    .record_index_o(rec_index),.record_data_o(rec_data),.record_first_o(rec_first),.record_last_o(rec_last));

  matrix_descriptor_v2_decode u_decode(
    .clk_i(clk),.rst_ni(rst_n),.snapshot_valid_i(d_snap_valid),.snapshot_ready_o(d_snap_ready),
    .snapshot_legal_i(snap_legal),.snapshot_status_i(snap_status),.snapshot_command_i(snap_cmd),
    .snapshot_record_count_i(snap_count),.record_valid_i(d_rec_valid),.record_ready_o(d_rec_ready),
    .record_chain_i(rec_chain),.record_index_i(rec_index),.record_data_i(rec_data),
    .record_first_i(rec_first),.record_last_i(rec_last),.context_valid_o(ctx_valid),
    .context_ready_i(ctx_ready),.context_legal_o(ctx_legal),.context_status_o(ctx_status),
    .context_command_o(ctx_cmd),.tensor_addr_o(ctx_addr),.tensor_shape_o(ctx_shape),
    .tensor_stride_o(ctx_stride),.tensor_meta_o(ctx_meta),.matrix_op_payload_o(ctx_op),
    .matrix_aux_payload_o(ctx_aux),.conv_valid_o(ctx_conv_valid),.conv_payload_o(ctx_conv),
    .quant_valid_o(ctx_quant_valid),.quant_payload_o(ctx_quant));

  assign req_ready=!pending&&(cycles%4)!=1;assign rsp_valid=pending;
  assign rsp_data=pending_index<64?mem[pending_index[5:0]]:'0;
  assign rsp_error=pending_index>=64||!present[pending_index[5:0]];
  assign d_snap_valid=snap_valid&&(cycles%5)!=2;assign snap_ready=d_snap_ready&&(cycles%5)!=2;
  assign d_rec_valid=rec_valid&&(cycles%3)!=1;assign rec_ready=d_rec_ready&&(cycles%3)!=1;
  assign ctx_ready=(cycles%4)!=1;

  function automatic logic[127:0] common(input logic[7:0]typ,input logic[23:0]next);
    logic[127:0]w;begin w='0;w[7:0]=typ;w[55:32]=next;common=w;end endfunction
  task automatic build_valid;
    logic[127:0]w;
    begin
      for(int n=0;n<64;n++)begin mem[n]='0;present[n]=0;end
      w=common(8'h01,2);w[103:56]=48'h80001000;w[111:108]=1;w[119:116]=2;mem[1]=w;present[1]=1;
      w=common(8'h02,3);w[73:56]=17;w[91:74]=19;mem[2]=w;present[2]=1;
      w=common(8'h03,4);w[79:56]=19;mem[3]=w;present[3]=1;
      w=common(8'h10,5);w[71:56]=17;w[87:72]=18;w[111:88]=19;mem[4]=w;present[4]=1;
      w=common(8'h12,24'hffffff);w[79:56]=30;w[85]=1;w[105:98]=1;w[125:118]=1;mem[5]=w;present[5]=1;
      w=common(8'h01,11);w[103:56]=48'h80002000;w[111:108]=1;w[119:116]=2;mem[10]=w;present[10]=1;
      w=common(8'h02,12);w[73:56]=19;w[91:74]=18;mem[11]=w;present[11]=1;
      w=common(8'h03,24'hffffff);w[79:56]=18;mem[12]=w;present[12]=1;
      w=common(8'h01,21);w[103:56]=48'h80003000;w[111:108]=1;w[119:116]=2;mem[20]=w;present[20]=1;
      w=common(8'h02,22);w[73:56]=17;w[91:74]=18;mem[21]=w;present[21]=1;
      w=common(8'h03,24'hffffff);w[79:56]=18;mem[22]=w;present[22]=1;
      w=common(8'h01,31);w[103:56]=48'h80004000;w[111:108]=4;w[119:116]=2;mem[30]=w;present[30]=1;
      w=common(8'h02,32);w[73:56]=17;w[91:74]=18;mem[31]=w;present[31]=1;
      w=common(8'h03,24'hffffff);w[79:56]=72;mem[32]=w;present[32]=1;
    end
  endtask
  task automatic send(input logic[23:0]a,input logic[23:0]b,input logic[23:0]c);
    begin @(negedge clk);cmd_data='0;cmd_data[7:0]=8'h20;cmd_data[10:8]=2;cmd_data[55:40]=16'h1234;
      cmd_data[79:56]=a;cmd_data[103:80]=b;cmd_data[127:104]=c;cmd_valid=1;
      do @(posedge clk);while(!cmd_ready);@(negedge clk);cmd_valid=0;end
  endtask

  always @(posedge clk)begin
    if(!rst_n)begin cycles<=0;pending<=0;headers<=0;replayed<=0;contexts<=0;held<=0;end else begin
      cycles<=cycles+1;
      if(req_valid&&req_ready)begin
        if(req_addr!==64'h4000+{36'd0,req_index,4'b0})$fatal(1,"address mapping");
        pending<=1;pending_index<=req_index;
      end
      if(rsp_valid&&rsp_ready)pending<=0;
      if(rec_valid&&headers==0)$fatal(1,"record exposed before header");
      if(rec_valid&&!rec_ready)begin
        if(held&&(rec_data!==held_data||rec_index!==held_index))$fatal(1,"replay payload unstable");
        held<=1;held_data<=rec_data;held_index<=rec_index;
      end else held<=0;
      if(snap_valid&&snap_ready)headers<=headers+1;
      if(rec_valid&&rec_ready)replayed<=replayed+1;
      if(ctx_valid&&ctx_ready)contexts<=contexts+1;
    end
  end
  initial begin
    cmd_valid=0;cmd_data=0;pending=0;seed=1;build_valid();repeat(3)@(posedge clk);rst_n=1;
    send(1,10,20);wait(headers==1);if(!snap_legal||snap_status!=0||snap_count!=14)$fatal(1,"valid header");
    wait(contexts==1);if(!ctx_legal||ctx_status!=0||ctx_addr[63:0]!=64'h80001000||
      ctx_addr[64 +: 64]!=64'h80002000||ctx_addr[192 +: 64]!=64'h80004000||ctx_op[15:0]!=17||
      ctx_aux[23:0]!=30)$fatal(1,"decoded context mismatch");@(negedge clk);
    // Cycle in src0 rejects and never replays cached records.
    build_valid();mem[2][55:32]=1;send(1,10,20);wait(headers==2);
    if(snap_legal||snap_status!=2)$fatal(1,"cycle status");
    wait(contexts==2);if(ctx_legal||ctx_status!=2)$fatal(1,"illegal context status");
    repeat(5)@(posedge clk);if(replayed!=14)$fatal(1,"illegal snapshot replayed");
    $display("MATRIX_DESCRIPTOR_V2_PIPELINE_PASS cycles=%0d headers=%0d records=%0d contexts=%0d",cycles,headers,replayed,contexts);$finish;
  end
  initial begin repeat(5000)@(posedge clk);$fatal(1,"timeout");end
endmodule

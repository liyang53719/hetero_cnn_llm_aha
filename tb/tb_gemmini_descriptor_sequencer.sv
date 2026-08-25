`timescale 1ns/1ps
module tb_gemmini_descriptor_sequencer;
  localparam logic [23:0] NULL_INDEX = 24'hff_ffff;
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  integer cycles,requests,legal_ops,reject_ops;
  logic cmd_valid,cmd_ready;
  logic[127:0] cmd_data;
  logic req_valid,req_ready;
  logic[23:0] req_index;
  logic[63:0] req_byte_addr;
  logic rsp_valid,rsp_ready,rsp_error;
  logic[127:0] rsp_data;
  logic op_valid,op_ready,op_first,op_last,op_legal;
  logic[15:0] op_event;
  logic[6:0] op_funct;
  logic[63:0] op_rs1,op_rs2;
  logic[127:0] memory[0:255];
  logic present[0:255];
  logic pending;
  logic[23:0] pending_index;
  logic[6:0] seen_funct[0:31];
  logic[63:0] seen_rs1[0:31],seen_rs2[0:31];

  assign req_ready=(cycles%4)!=1 && !pending;
  assign op_ready=(cycles%5)!=2;
  assign rsp_valid=pending;
  assign rsp_data=(pending_index<256)?memory[pending_index[7:0]]:'0;
  assign rsp_error=(pending_index>=256)||!present[pending_index[7:0]];

  gemmini_descriptor_sequencer dut(
    .clk_i(clk),.rst_ni(rst_n),.cmd_valid_i(cmd_valid),.cmd_ready_o(cmd_ready),
    .cmd_data_i(cmd_data),.descriptor_base_i(64'h0000_0000_0000_4000),
    .descriptor_req_valid_o(req_valid),.descriptor_req_ready_i(req_ready),
    .descriptor_req_index_o(req_index),.descriptor_req_byte_addr_o(req_byte_addr),
    .descriptor_rsp_valid_i(rsp_valid),.descriptor_rsp_ready_o(rsp_ready),
    .descriptor_rsp_data_i(rsp_data),.descriptor_rsp_error_i(rsp_error),
    .op_valid_o(op_valid),.op_ready_i(op_ready),.op_first_o(op_first),
    .op_last_o(op_last),.op_legal_o(op_legal),.op_event_id_o(op_event),
    .op_funct_o(op_funct),.op_rs1_o(op_rs1),.op_rs2_o(op_rs2));

  function automatic logic[127:0] base_record(input logic[23:0] next,
                                                input logic[55:0] address);
    logic[127:0] w;
    begin
      w='0;w[7:0]=8'h01;w[55:32]=next;w[103:56]=address[47:0];
      w[111:108]=4'd1;w[115:112]=4'd0;w[119:116]=4'd2;w[127:120]=address[55:48];
      base_record=w;
    end
  endfunction
  function automatic logic[127:0] shape_record(input logic[23:0] next,
                                                 input integer d0,input integer d1);
    logic[127:0] w;
    begin w='0;w[7:0]=8'h02;w[55:32]=next;w[73:56]=d0[17:0];w[91:74]=d1[17:0];shape_record=w;end
  endfunction
  function automatic logic[127:0] stride_record(input logic[23:0] next,input integer stride);
    logic[127:0] w;
    begin w='0;w[7:0]=8'h03;w[55:32]=next;w[79:56]=stride[23:0];stride_record=w;end
  endfunction
  function automatic logic[127:0] matrix_record(input logic[23:0] next,
                                                  input integer m,input integer n,input integer k);
    logic[127:0] w;
    begin
      w='0;w[7:0]=8'h10;w[55:32]=next;w[71:56]=m[15:0];w[87:72]=n[15:0];w[111:88]=k[23:0];
      matrix_record=w;
    end
  endfunction

  task automatic clear_memory;
    begin for(int i=0;i<256;i++)begin memory[i]='0;present[i]=0;end end
  endtask
  task automatic send_command(input logic[23:0] a,input logic[23:0] b,
                              input logic[23:0] c,input logic[15:0] event_id);
    begin
      @(negedge clk);cmd_data='0;cmd_data[7:0]=8'h20;cmd_data[10:8]=3'd2;
      cmd_data[55:40]=event_id;cmd_data[79:56]=a;cmd_data[103:80]=b;cmd_data[127:104]=c;
      cmd_valid=1;do @(posedge clk);while(!cmd_ready);@(negedge clk);cmd_valid=0;
    end
  endtask
  task automatic wait_account(input integer wanted_legal,input integer wanted_reject);
    begin wait(legal_ops==wanted_legal && reject_ops==wanted_reject);@(negedge clk);end
  endtask

  always @(posedge clk) begin
    if(!rst_n)begin cycles<=0;requests<=0;legal_ops<=0;reject_ops<=0;pending<=0;pending_index<=0;end
    else begin
      cycles<=cycles+1;
      if(req_valid&&req_ready)begin
        if(req_byte_addr!==64'h4000+{36'd0,req_index,4'b0})$fatal(1,"byte mapping mismatch");
        pending<=1;pending_index<=req_index;requests<=requests+1;
      end
      if(rsp_valid&&rsp_ready)pending<=0;
      if(op_valid&&op_ready)begin
        if(op_event==0)$fatal(1,"event id lost");
        if(op_legal)begin
          seen_funct[legal_ops]<=op_funct;seen_rs1[legal_ops]<=op_rs1;seen_rs2[legal_ops]<=op_rs2;
          if((legal_ops%9==0)!==op_first || (legal_ops%9==8)!==op_last)$fatal(1,"first/last mismatch");
          legal_ops<=legal_ops+1;
        end else begin
          if(!op_first||!op_last) $fatal(1,"reject envelope mismatch");
          reject_ops<=reject_ops+1;
        end
      end
    end
  end

  initial begin
    cmd_valid=0;cmd_data=0;pending=0;clear_memory();
    repeat(3)@(posedge clk);rst_n=1;
    // A: base -> shape -> stride -> matrix-op; B/C: base -> shape -> stride.
    memory[1]=base_record(2,56'h00000080001000);present[1]=1;
    memory[2]=shape_record(3,3,7);present[2]=1;
    memory[3]=stride_record(4,7);present[3]=1;
    memory[4]=matrix_record(NULL_INDEX,3,5,7);present[4]=1;
    memory[5]=base_record(6,56'h00000080002000);present[5]=1;
    memory[6]=shape_record(7,7,5);present[6]=1;
    memory[7]=stride_record(NULL_INDEX,5);present[7]=1;
    memory[8]=base_record(9,56'h00000080003000);present[8]=1;
    memory[9]=shape_record(10,3,5);present[9]=1;
    memory[10]=stride_record(NULL_INDEX,5);present[10]=1;
    send_command(1,5,8,16'h1234);wait_account(9,0);
    if(requests!=10)$fatal(1,"expected ten descriptor reads got %0d",requests);
    if(seen_funct[0]!=0||seen_funct[3]!=2||seen_funct[5]!=2||seen_funct[6]!=6||
       seen_funct[7]!=4||seen_funct[8]!=3)$fatal(1,"official op order mismatch");
    if(seen_rs1[3]!=64'h80001000||seen_rs1[5]!=64'h80002000||seen_rs1[8]!=64'h80003000)
      $fatal(1,"tensor address mismatch");
    if(seen_rs2[8]!=64'h0003_0005_0000_0030)$fatal(1,"mvout shape mismatch");

    // Missing/out-of-range response must reject before any additional legal op.
    send_command(24'h0000fe,5,8,16'h2001);wait_account(9,1);

    // Two-record cycle must be detected before a repeated fetch is issued.
    memory[20]=base_record(21,56'h1000);present[20]=1;
    memory[21]=shape_record(20,3,7);present[21]=1;
    send_command(20,5,8,16'h2002);wait_account(9,2);

    // A non-terminating 16-record chain is rejected at the hard bound.
    memory[30]=base_record(31,56'h1000);present[30]=1;
    for(int i=31;i<46;i++)begin memory[i]=shape_record(24'(i+1),3,7);present[i]=1;end
    send_command(30,5,8,16'h2003);wait_account(9,3);
    if(legal_ops!=9)$fatal(1,"illegal chain leaked CUSTOM_3 ops");
    $display("GEMMINI_DESCRIPTOR_SEQUENCER_PASS cycles=%0d requests=%0d legal_ops=%0d rejects=%0d",
             cycles,requests,legal_ops,reject_ops);
    $finish;
  end
  initial begin
    repeat(5000)@(posedge clk);
    $display("TIMEOUT_DEBUG state=%0d chain=%0d count=%0d index=%h pending=%0b req=%0b/%0b rsp=%0b/%0b legal=%0d reject=%0d",
             dut.state_q,dut.chain_q,dut.chain_count_q,dut.current_index_q,pending,
             req_valid,req_ready,rsp_valid,rsp_ready,legal_ops,reject_ops);
    $fatal(1,"timeout");
  end
endmodule

`timescale 1ns/1ps
module tb_kv_idma_basic_core;
  logic clk=0,rst_n=0;always #5 clk=~clk;integer cycles,events,requests;
  logic op_valid,op_ready;logic[7:0]opcode;logic[15:0]event_id;logic[11:0]seq;logic[9:0]layer;
  logic[23:0]start;logic[15:0]count;logic[11:0]head_dim;logic[63:0]kaddr,vaddr,outaddr;
  logic req_valid,req_ready;logic[63:0]src,dst;logic[31:0]length;
  logic rsp_valid,rsp_ready,rsp_error,event_valid,event_ready;logic[55:0]event_data;
  logic rsp_pending;logic[7:0]mem[0:8191];integer expected_events;
  kv_idma_basic_core #(.STAGING_BASE(64'h100),.STAGING_BYTES(512))dut(
    .clk_i(clk),.rst_ni(rst_n),.op_valid_i(op_valid),.op_ready_o(op_ready),.opcode_i(opcode),
    .event_id_i(event_id),.sequence_id_i(seq),.layer_id_i(layer),.token_start_i(start),
    .token_count_i(count),.head_dim_i(head_dim),.k_addr_i(kaddr),.v_addr_i(vaddr),
    .output_addr_i(outaddr),.idma_req_valid_o(req_valid),.idma_req_ready_i(req_ready),
    .idma_src_addr_o(src),.idma_dst_addr_o(dst),.idma_length_o(length),
    .idma_rsp_valid_i(rsp_valid),.idma_rsp_ready_o(rsp_ready),.idma_rsp_error_i(rsp_error),
    .event_valid_o(event_valid),.event_ready_i(event_ready),.event_data_o(event_data));
  assign req_ready=!rsp_pending&&(cycles%4)!=1;assign rsp_valid=rsp_pending;
  assign rsp_error=0;assign event_ready=(cycles%5)!=2;
  always @(posedge clk)begin
    if(!rst_n)begin cycles<=0;events<=0;requests<=0;rsp_pending<=0;end else begin
      cycles<=cycles+1;
      if(req_valid&&req_ready)begin
        for(int i=0;i<length;i++)mem[dst+i]=mem[src+i];
        rsp_pending<=1;requests<=requests+1;
      end
      if(rsp_valid&&rsp_ready)rsp_pending<=0;
      if(event_valid&&event_ready)begin events<=events+1;
        if(event_data[55:40]!=event_id||event_data[31:29]!=3'd4)$fatal(1,"event envelope");
      end
    end
  end
  task automatic send(input logic[7:0]op,input logic[23:0]s,input logic[15:0]c,
                      input logic[11:0]hd,input logic[15:0]eid,input logic[7:0]status,input integer bytes);
    integer prior;
    begin prior=events;@(negedge clk);opcode=op;start=s;count=c;head_dim=hd;event_id=eid;op_valid=1;
      do @(posedge clk);while(!op_ready);@(negedge clk);op_valid=0;
      do @(posedge clk);while(!(event_valid&&event_ready));
      if(event_data[39:32]!=status||event_data[28:0]!=bytes)$fatal(1,"event status/bytes got=%h",event_data);
      @(negedge clk);if(events!=prior+1)$fatal(1,"event accounting");
    end
  endtask
  initial begin
    op_valid=0;opcode=0;event_id=0;seq=0;layer=0;start=0;count=0;head_dim=0;
    kaddr=64'h400;vaddr=64'h500;outaddr=64'h600;for(int i=0;i<8192;i++)mem[i]=0;
    for(int i=0;i<32;i++)begin mem['h400+i]=8'h20+i;mem['h500+i]=8'h80+i;end
    repeat(3)@(posedge clk);rst_n=1;
    send(8'h40,0,0,8,16'h10,0,0);
    send(8'h41,0,2,8,16'h11,0,64);
    send(8'h42,1,1,8,16'h12,0,32);
    for(int i=0;i<16;i++)begin
      if(mem['h600+i]!==mem['h410+i]||mem['h610+i]!==mem['h510+i])$fatal(1,"BF16 byte copy mismatch");
    end
    send(8'h41,4,1,8,16'h13,5,0);
    send(8'h44,0,0,0,16'h14,0,0);
    send(8'h42,0,1,8,16'h15,5,0);
    if(requests!=4)$fatal(1,"expected four iDMA transfers got %0d",requests);
    $display("KV_IDMA_BASIC_CORE_PASS cycles=%0d requests=%0d events=%0d",cycles,requests,events);$finish;
  end
  initial begin repeat(5000)@(posedge clk);$fatal(1,"timeout");end
endmodule

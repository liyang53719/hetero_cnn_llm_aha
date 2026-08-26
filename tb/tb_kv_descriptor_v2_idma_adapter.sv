`timescale 1ns/1ps
module tb_kv_descriptor_v2_idma_adapter;
`ifdef USE_UPSTREAM_IDMA
  import hetero_idma_512_pkg::*;
`endif
  logic clk=0,rst_n=0;always #5 clk=~clk;integer cycles,events,requests;
  logic cmd_valid,cmd_ready;logic[127:0]cmd;
  logic dreq_valid,dreq_ready;logic[23:0]dreq_index;logic[63:0]dreq_addr;
  logic drsp_valid,drsp_ready,drsp_error;logic[127:0]drsp_data,desc[0:63];logic present[0:63],dpending;logic[23:0]dindex;
  logic ireq_valid,ireq_ready;logic[63:0]isrc,idst;logic[31:0]ilen;logic irsp_valid,irsp_ready,irsp_error,ipending;
  logic event_valid,event_ready;logic[55:0]event_data;logic[7:0]mem[0:8191];
`ifdef USE_UPSTREAM_IDMA
  logic[7:0]idma_busy;axi_req_t axi_read_req,axi_write_req,axi_joined_req;
  axi_rsp_t axi_read_rsp,axi_write_rsp,axi_joined_rsp;
  idma_backend_rw_axi_flat_wrap i_idma(.clk_i(clk),.rst_ni(rst_n),.req_valid_i(ireq_valid),
    .req_ready_o(ireq_ready),.src_addr_i(isrc),.dst_addr_i(idst),.length_i(ilen),
    .rsp_valid_o(irsp_valid),.rsp_ready_i(irsp_ready),.rsp_error_o(irsp_error),
    .axi_read_req_o(axi_read_req),.axi_read_rsp_i(axi_read_rsp),
    .axi_write_req_o(axi_write_req),.axi_write_rsp_i(axi_write_rsp),.busy_o(idma_busy));
  axi_rw_join #(.axi_req_t(axi_req_t),.axi_resp_t(axi_rsp_t))i_join(
    .clk_i(clk),.rst_ni(rst_n),.slv_read_req_i(axi_read_req),.slv_read_resp_o(axi_read_rsp),
    .slv_write_req_i(axi_write_req),.slv_write_resp_o(axi_write_rsp),
    .mst_req_o(axi_joined_req),.mst_resp_i(axi_joined_rsp));
  axi_sim_mem #(.AddrWidth(64),.DataWidth(512),.IdWidth(4),.UserWidth(1),
    .axi_req_t(axi_req_t),.axi_rsp_t(axi_rsp_t),.WarnUninitialized(1'b0),
    .ClearErrOnAccess(1'b1),.ApplDelay(1ns),.AcqDelay(9ns))i_mem(
    .clk_i(clk),.rst_ni(rst_n),.axi_req_i(axi_joined_req),.axi_rsp_o(axi_joined_rsp),
    .mon_r_last_o(),.mon_r_beat_count_o(),.mon_r_user_o(),.mon_r_id_o(),
    .mon_r_data_o(),.mon_r_addr_o(),.mon_r_valid_o(),.mon_w_last_o(),
    .mon_w_beat_count_o(),.mon_w_user_o(),.mon_w_id_o(),.mon_w_data_o(),
    .mon_w_addr_o(),.mon_w_valid_o());
`endif
  kv_descriptor_v2_idma_adapter #(.STAGING_BASE(64'h100),.STAGING_BYTES(512))dut(
    .clk_i(clk),.rst_ni(rst_n),.cmd_valid_i(cmd_valid),
    .cmd_ready_o(cmd_ready),.cmd_data_i(cmd),.descriptor_base_i(64'h4000),
    .descriptor_req_valid_o(dreq_valid),.descriptor_req_ready_i(dreq_ready),
    .descriptor_req_index_o(dreq_index),.descriptor_req_byte_addr_o(dreq_addr),
    .descriptor_rsp_valid_i(drsp_valid),.descriptor_rsp_ready_o(drsp_ready),
    .descriptor_rsp_data_i(drsp_data),.descriptor_rsp_error_i(drsp_error),
    .idma_req_valid_o(ireq_valid),.idma_req_ready_i(ireq_ready),.idma_src_addr_o(isrc),
    .idma_dst_addr_o(idst),.idma_length_o(ilen),.idma_rsp_valid_i(irsp_valid),
    .idma_rsp_ready_o(irsp_ready),.idma_rsp_error_i(irsp_error),.event_valid_o(event_valid),
    .event_ready_i(event_ready),.event_data_o(event_data));
  assign dreq_ready=!dpending&&(cycles%4)!=1;assign drsp_valid=dpending;
  assign drsp_data=dindex<64?desc[dindex[5:0]]:'0;assign drsp_error=dindex>=64||!present[dindex[5:0]];
`ifndef USE_UPSTREAM_IDMA
  assign ireq_ready=!ipending&&(cycles%5)!=2;assign irsp_valid=ipending;assign irsp_error=0;
`endif
  assign event_ready=(cycles%3)!=1;
  function automatic logic[127:0]base(input logic[23:0]next,input logic[47:0]addr,input logic[3:0]rank);
    logic[127:0]w;begin w='0;w[7:0]=1;w[55:32]=next;w[103:56]=addr;w[111:108]=2;w[119:116]=rank;base=w;end endfunction
  function automatic logic[127:0]shape(input logic[23:0]next,input integer d0,d1,d2,d3);
    logic[127:0]w;begin w='0;w[7:0]=2;w[55:32]=next;w[73:56]=d0;w[91:74]=d1;w[109:92]=d2;w[127:110]=d3;shape=w;end endfunction
  function automatic logic[127:0]stride(input logic[23:0]next);
    logic[127:0]w;begin w='0;w[7:0]=3;w[55:32]=next;w[79:56]=16;stride=w;end endfunction
  function automatic logic[127:0]kvaddr(input logic[23:0]next,input integer start,count);
    logic[127:0]w;begin w='0;w[7:0]=8'h30;w[55:32]=next;w[111:88]=start;w[127:112]=count;kvaddr=w;end endfunction
  function automatic logic[127:0]kvfmt;
    logic[127:0]w;begin w='0;w[7:0]=8'h31;w[55:32]=24'hffffff;w[83:80]=4;w[95:84]=8;w[105:96]=1;w[115:106]=1;kvfmt=w;end endfunction
  task automatic set_byte(input integer a,input logic[7:0]v);begin
`ifdef USE_UPSTREAM_IDMA
    i_mem.mem[a]=v;
`else
    mem[a]=v;
`endif
  end endtask
  function automatic logic[7:0]get_byte(input integer a);
`ifdef USE_UPSTREAM_IDMA
    get_byte=i_mem.mem.exists(a)?i_mem.mem[a]:8'hxx;
`else
    get_byte=mem[a];
`endif
  endfunction
  task automatic send(input logic[7:0]op,input logic[23:0]s0,s1,d,input logic[15:0]eid,input logic[7:0]status,input integer bytes);
    integer prior;begin prior=events;@(negedge clk);cmd='0;cmd[7:0]=op;cmd[10:8]=4;cmd[55:40]=eid;
      cmd[79:56]=s0;cmd[103:80]=s1;cmd[127:104]=d;cmd_valid=1;
      do @(posedge clk);while(!cmd_ready);@(negedge clk);cmd_valid=0;
      do @(posedge clk);while(!(event_valid&&event_ready));
      if(event_data[39:32]!=status||event_data[28:0]!=bytes)$fatal(1,"event mismatch %h",event_data);
      @(negedge clk);if(events!=prior+1)$fatal(1,"event accounting");end endtask
  always @(posedge clk)begin
    if(!rst_n)begin cycles<=0;events<=0;requests<=0;dpending<=0;ipending<=0;end else begin cycles<=cycles+1;
      if(dreq_valid&&dreq_ready)begin dpending<=1;dindex<=dreq_index;end
      if(drsp_valid&&drsp_ready)dpending<=0;
      if(ireq_valid&&ireq_ready)begin
`ifndef USE_UPSTREAM_IDMA
        for(int i=0;i<ilen;i++)mem[idst+i]=mem[isrc+i];ipending<=1;
`endif
        requests<=requests+1;end
`ifndef USE_UPSTREAM_IDMA
      if(irsp_valid&&irsp_ready)ipending<=0;
`endif
      if(event_valid&&event_ready)events<=events+1;
    end end
  initial begin
    cmd_valid=0;cmd=0;for(int i=0;i<64;i++)begin desc[i]=0;present[i]=0;end
    for(int i=0;i<8192;i++)set_byte(i,0);
    desc[1]=kvaddr(2,0,2);present[1]=1;desc[2]=kvfmt();present[2]=1;
    desc[3]=kvaddr(4,1,1);present[3]=1;desc[4]=kvfmt();present[4]=1;
    desc[10]=base(11,48'h400,3);present[10]=1;desc[11]=shape(12,2,1,8,0);present[11]=1;desc[12]=stride(24'hffffff);present[12]=1;
    desc[20]=base(21,48'h500,3);present[20]=1;desc[21]=shape(22,2,1,8,0);present[21]=1;desc[22]=stride(24'hffffff);present[22]=1;
    desc[30]=base(31,48'h600,4);present[30]=1;desc[31]=shape(32,2,1,1,8);present[31]=1;desc[32]=stride(24'hffffff);present[32]=1;
    for(int i=0;i<32;i++)begin set_byte('h400+i,8'h20+i);set_byte('h500+i,8'h80+i);end
    repeat(3)@(posedge clk);rst_n=1;
    send(8'h40,1,24'hffffff,24'hffffff,16'h10,0,0);
    send(8'h41,10,20,1,16'h11,0,64);
    send(8'h42,3,24'hffffff,30,16'h12,0,32);
    for(int i=0;i<16;i++)if(get_byte('h600+i)!==get_byte('h410+i)||
      get_byte('h610+i)!==get_byte('h510+i))$fatal(1,"gather mismatch");
    send(8'h44,1,24'hffffff,24'hffffff,16'h13,0,0);
    present[1]=0;send(8'h40,1,24'hffffff,24'hffffff,16'h14,3,0);
    if(requests!=4)$fatal(1,"request count");
    $display("KV_DESCRIPTOR_V2_IDMA_ADAPTER_PASS cycles=%0d requests=%0d events=%0d",cycles,requests,events);$finish;
  end
  initial begin repeat(10000)@(posedge clk);$fatal(1,"timeout");end
endmodule

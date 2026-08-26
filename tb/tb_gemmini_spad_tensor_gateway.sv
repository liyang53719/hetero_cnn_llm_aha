`timescale 1ns/1ps
module tb_gemmini_spad_tensor_gateway;
  parameter integer TARGET=100000;logic clk=0,rst_n=0;always #5 clk=~clk;
  integer cycles,seed,completed,tx_seen,rx_seen;
  logic cfg_valid,cfg_ready,cfg_dir,cfg_route;logic[11:0]cfg_last;logic[15:0]cfg_tag;logic[11:0]cfg_tid;logic[3:0]cfg_fmt;
  logic[3:0]wv,wr,rrv,rrr,rrsv,rrsr;logic[47:0]wa,rra;logic[511:0]wd,rrsd;logic[63:0]wm;
  logic txv,txr,txroute,txlast;logic[511:0]txd;logic[63:0]txbe;logic[15:0]txtag;logic[11:0]txtid;logic[3:0]txfmt;
  logic rxv,rxr,rxroute,rxlast;logic[511:0]rxd;logic[63:0]rxbe;logic[15:0]rxtag;logic[11:0]rxtid;logic[3:0]rxfmt;
  logic done;logic[31:0]errors;
  logic[3:0]sin_v,sin_r,sout_v,sout_r,sin_last,sout_last;logic[2047:0]sin_d,sout_d;
  logic[255:0]sin_be,sout_be;logic[63:0]sin_tag,sout_tag;logic[47:0]sin_tid,sout_tid;logic[15:0]sin_fmt,sout_fmt;
  logic[511:0]expected;logic[63:0]expected_be;logic[15:0]expected_tag;logic[11:0]expected_tid;logic expected_route;
  logic[3:0]src_v,src_last;logic[2047:0]src_d;logic[255:0]src_be;
  logic[63:0]src_tag;logic[47:0]src_tid;logic[15:0]src_fmt;
  gemmini_spad_tensor_gateway dut(.clk_i(clk),.rst_ni(rst_n),.cfg_valid_i(cfg_valid),.cfg_ready_o(cfg_ready),
    .cfg_direction_i(cfg_dir),.cfg_route_i(cfg_route),.cfg_last_addr_i(cfg_last),.cfg_tag_i(cfg_tag),
    .cfg_tensor_id_i(cfg_tid),.cfg_format_i(cfg_fmt),.spad_write_valid_i(wv),.spad_write_ready_o(wr),
    .spad_write_addr_i(wa),.spad_write_data_i(wd),.spad_write_mask_i(wm),
    .spad_read_req_valid_i(rrv),.spad_read_req_ready_o(rrr),.spad_read_req_addr_i(rra),
    .spad_read_resp_valid_o(rrsv),.spad_read_resp_ready_i(rrsr),.spad_read_resp_data_o(rrsd),
    .tx_valid_o(txv),.tx_ready_i(txr),.tx_route_o(txroute),.tx_data_o(txd),.tx_be_o(txbe),
    .tx_tag_o(txtag),.tx_tensor_id_o(txtid),.tx_last_o(txlast),.tx_format_o(txfmt),
    .rx_valid_i(rxv),.rx_ready_o(rxr),.rx_route_i(rxroute),.rx_data_i(rxd),.rx_be_i(rxbe),
    .rx_tag_i(rxtag),.rx_tensor_id_i(rxtid),.rx_last_i(rxlast),.rx_format_i(rxfmt),
    .transfer_done_o(done),.protocol_error_count_o(errors));
  matrix_direct_streams streams(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(sin_v),.in_ready_o(sin_r),
    .in_data_i(sin_d),.in_be_i(sin_be),.in_tag_i(sin_tag),.in_tensor_id_i(sin_tid),
    .in_last_i(sin_last),.in_format_i(sin_fmt),.out_valid_o(sout_v),.out_ready_i(sout_r),
    .out_data_o(sout_d),.out_be_o(sout_be),.out_tag_o(sout_tag),.out_tensor_id_o(sout_tid),
    .out_last_o(sout_last),.out_format_o(sout_fmt));
  always_comb begin
    sin_v=src_v;sin_d=src_d;sin_be=src_be;sin_tag=src_tag;sin_tid=src_tid;
    sin_last=src_last;sin_fmt=src_fmt;sout_r=0;
    sin_v[txroute?2:0]=txv;sin_d[(txroute?2:0)*512 +: 512]=txd;
    sin_be[(txroute?2:0)*64 +: 64]=txbe;sin_tag[(txroute?2:0)*16 +: 16]=txtag;
    sin_tid[(txroute?2:0)*12 +: 12]=txtid;sin_last[txroute?2:0]=txlast;
    sin_fmt[(txroute?2:0)*4 +: 4]=txfmt;txr=sin_r[txroute?2:0];
    rxv=sout_v[cfg_route?3:1];rxd=sout_d[(cfg_route?3:1)*512 +: 512];
    rxbe=sout_be[(cfg_route?3:1)*64 +: 64];rxtag=sout_tag[(cfg_route?3:1)*16 +: 16];
    rxtid=sout_tid[(cfg_route?3:1)*12 +: 12];rxlast=sout_last[cfg_route?3:1];
    rxfmt=sout_fmt[(cfg_route?3:1)*4 +: 4];rxroute=cfg_route;sout_r[cfg_route?3:1]=rxr;
    sout_r[0]=(cycles%4)!=1;sout_r[2]=(cycles%5)!=2;
  end
  always @(posedge clk)begin
    if(!rst_n)begin cycles<=0;completed<=0;tx_seen<=0;rx_seen<=0;end else begin cycles<=cycles+1;
      if(done)completed<=completed+1;
      if(sout_v[0]&&sout_r[0]||sout_v[2]&&sout_r[2])begin
        int ch;ch=sout_v[2]?2:0;
        if(ch!=(expected_route?2:0)||sout_d[ch*512 +: 512]!==expected||sout_be[ch*64 +: 64]!==expected_be||
           sout_tag[ch*16 +: 16]!==expected_tag||sout_tid[ch*12 +: 12]!==expected_tid||
           !sout_last[ch])$fatal(1,"TX stream mismatch");tx_seen<=tx_seen+1;end
      rx_seen<=rx_seen+(rrsv[0]&&rrsr[0])+(rrsv[1]&&rrsr[1])+
                       (rrsv[2]&&rrsr[2])+(rrsv[3]&&rrsr[3]);
    end
  end
  task automatic configure(input logic dir,input logic route,input logic[11:0]addr,input integer id);
    begin @(negedge clk);cfg_dir=dir;cfg_route=route;cfg_last=addr;cfg_tag=id;cfg_tid=id;cfg_fmt=1;cfg_valid=1;
      do @(posedge clk);while(!cfg_ready);@(negedge clk);cfg_valid=0;end endtask
  task automatic write_group(input integer id);
    logic[11:0]addr;integer prior,txprior;
    begin addr=id&12'hfff;prior=completed;txprior=tx_seen;configure(0,id&1,addr,id);
      expected_tag=id;expected_tid=id;expected_route=id&1;expected_be='1;
      for(int b=0;b<4;b++)begin wa[b*12 +: 12]=addr;wd[b*128 +: 128]={96'(id),24'(b),8'h5a};wm[b*16 +: 16]='1;end
      expected=wd;@(negedge clk);wv='1;
      wait(&wr);@(posedge clk);@(negedge clk);wv=0;
      wait(completed==prior+1);wait(tx_seen==txprior+1);end endtask
  task automatic read_group(input integer id);
    logic[11:0]addr;integer prior,rxprior;logic[3:0]accepted_resp;
    begin addr=id&12'hfff;prior=completed;rxprior=rx_seen;configure(1,id&1,addr,id);
      for(int b=0;b<4;b++)rra[b*12 +: 12]=addr;@(negedge clk);rrv='1;
      wait(&rrr);@(posedge clk);@(negedge clk);rrv=0;
      expected_tag=id;expected_tid=id;expected_be='1;
      for(int b=0;b<4;b++)expected[b*128 +: 128]={96'(id),24'(b),8'ha5};
      @(negedge clk);src_v[id&1?3:1]=1;src_d[(id&1?3:1)*512 +: 512]=expected;
      src_be[(id&1?3:1)*64 +: 64]='1;src_tag[(id&1?3:1)*16 +: 16]=id;
      src_tid[(id&1?3:1)*12 +: 12]=id;src_last[id&1?3:1]=1;src_fmt[(id&1?3:1)*4 +: 4]=1;
      do @(posedge clk);while(!sin_r[id&1?3:1]);@(negedge clk);src_v[id&1?3:1]=0;
      accepted_resp=0;
      while(accepted_resp!=4'hf)begin rrsr=$urandom(seed);@(posedge clk);
        for(int b=0;b<4;b++)if(rrsv[b]&&rrsr[b])begin
          if(rrsd[b*128 +: 128]!==expected[b*128 +: 128])$fatal(1,"RX response mismatch");accepted_resp[b]=1;end
        @(negedge clk);end
      rrsr=0;wait(completed==prior+1);@(negedge clk);
      if(rx_seen!=rxprior+4)$fatal(1,"RX accounting");end endtask
  initial begin
    cfg_valid=0;cfg_dir=0;cfg_route=0;cfg_last=0;cfg_tag=0;cfg_tid=0;cfg_fmt=0;
    wv=0;wa=0;wd=0;wm=0;rrv=0;rra=0;rrsr=0;src_v=0;src_d=0;src_be=0;
    src_tag=0;src_tid=0;src_last=0;src_fmt=0;seed=32'h2468ace1;
    repeat(3)@(posedge clk);rst_n=1;
    for(int t=0;t<TARGET/2;t++)write_group(t);
    for(int t=0;t<TARGET/2;t++)read_group(t);
    if(completed!=TARGET||errors!=0)$fatal(1,"gateway accounting");
    $display("GEMMINI_SPAD_TENSOR_GATEWAY_100K_PASS transfers=%0d tx=%0d rx_beats=%0d",completed,tx_seen,rx_seen);$finish;
  end
  initial begin repeat(3000000)@(posedge clk);$fatal(1,"timeout");end
endmodule

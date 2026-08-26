`timescale 1ns/1ps
module tb_int8_pool_residual_sfu;
  parameter integer TARGET=100000;
  logic clk;/* verilator lint_off SYNCASYNCNET */logic rst_n;/* verilator lint_on SYNCASYNCNET */
  always #5 clk=~clk;integer cycles,completed,received,rng;
  integer pos_sat,neg_sat,negative_pool;
  logic cfg_valid,cfg_ready,cfg_op;logic[3:0]cfg_h,cfg_w;logic[4:0]cfg_c;
  logic[6:0]cfg_bytes;logic[15:0]cfg_tag;logic[11:0]cfg_tid;logic[3:0]cfg_fmt;
  logic pv,pr,sv,sr;logic[511:0]pd,sd;logic[63:0]pbe,sbe;logic plast,slast;logic[3:0]pfmt,sfmt;
  logic ov,orr;logic[511:0]od;logic[63:0]obe;logic[15:0]otag;logic[11:0]otid;logic olast;logic[3:0]ofmt;
  logic done;logic[31:0]errors;logic[511:0]expected;logic[63:0]expected_be;
  logic[15:0]expected_tag;logic[11:0]expected_tid;logic[3:0]expected_fmt;
  logic stalled;logic[511:0]held_data;logic[63:0]held_be;
  logic[63:0]output_hash;
  int8_pool_residual_sfu dut(.clk_i(clk),.rst_ni(rst_n),.cfg_valid_i(cfg_valid),.cfg_ready_o(cfg_ready),
    .cfg_op_i(cfg_op),.cfg_h_i(cfg_h),.cfg_w_i(cfg_w),.cfg_c_i(cfg_c),.cfg_bytes_i(cfg_bytes),
    .cfg_tag_i(cfg_tag),.cfg_tensor_id_i(cfg_tid),.cfg_format_i(cfg_fmt),
    .primary_valid_i(pv),.primary_ready_o(pr),.primary_data_i(pd),.primary_be_i(pbe),
    .primary_last_i(plast),.primary_format_i(pfmt),.secondary_valid_i(sv),.secondary_ready_o(sr),
    .secondary_data_i(sd),.secondary_be_i(sbe),.secondary_last_i(slast),.secondary_format_i(sfmt),
    .out_valid_o(ov),.out_ready_i(orr),.out_data_o(od),.out_be_o(obe),.out_tag_o(otag),
    .out_tensor_id_o(otid),.out_last_o(olast),.out_format_o(ofmt),
    .transfer_done_o(done),.protocol_error_count_o(errors));
  function automatic[31:0]next_rand(input[31:0]v);reg[31:0]x;begin x=v;x=x^(x<<13);x=x^(x>>17);x=x^(x<<5);next_rand=x;end endfunction
  function automatic[63:0]hash_beat(input[63:0]seed,input[511:0]data,input[63:0]be);
    reg[63:0]h;begin h=seed;for(int i=0;i<64;i++)begin h=(h^{56'd0,data[i*8 +:8]})*64'h00000100000001b3;
      h=(h^{63'd0,be[i]})*64'h00000100000001b3;end hash_beat=h;end endfunction
  always_comb orr=(cycles%5)!=1&&(cycles%7)!=3;
  always @(posedge clk)begin
    if(!rst_n)begin cycles<=0;completed<=0;received<=0;stalled<=0;held_data<=0;held_be<=0;
      output_hash<=64'hcbf29ce484222325;end else begin cycles<=cycles+1;
      if(done)completed<=completed+1;
      if(ov&&orr)begin if(od!==expected||obe!==expected_be||otag!==expected_tag||otid!==expected_tid||ofmt!==expected_fmt||!olast)
        $fatal(1,"SFU output mismatch");received<=received+1;output_hash<=hash_beat(output_hash,od,obe);end
      if(stalled&&(!ov||od!==held_data||obe!==held_be))$fatal(1,"SFU stalled payload changed");
      stalled<=ov&&!orr;if(ov&&!orr)begin held_data<=od;held_be<=obe;end
    end
  end
  task automatic configure(input logic op,input logic[3:0]h,input logic[3:0]w,input logic[4:0]c,
    input logic[6:0]bytes,input logic[15:0]id);
    begin @(negedge clk);cfg_op=op;cfg_h=h;cfg_w=w;cfg_c=c;cfg_bytes=bytes;
      cfg_tag=id;cfg_tid=id[11:0];cfg_fmt=1;expected_tag=id;expected_tid=id[11:0];expected_fmt=1;cfg_valid=1;
      do @(posedge clk);while(!cfg_ready);@(negedge clk);cfg_valid=0;end endtask
  task automatic send_primary;begin @(negedge clk);pv=1;do @(posedge clk);while(!pr);@(negedge clk);pv=0;end endtask
  task automatic send_secondary;begin @(negedge clk);sv=1;do @(posedge clk);while(!sr);@(negedge clk);sv=0;end endtask
  task automatic run_residual(input integer id);
    integer bytes,prior;integer a,b,s;begin bytes=id%64+1;prior=completed;
      configure(0,4'd1,4'd1,5'd1,7'(bytes),16'(id));expected=0;expected_be=0;
      for(int i=0;i<64;i++)begin rng=next_rand(rng);pd[i*8 +:8]=rng[7:0];rng=next_rand(rng);sd[i*8 +:8]=rng[7:0];
        rng=next_rand(rng);pbe[i]=rng[0];rng=next_rand(rng);sbe[i]=rng[0];
        if(i<bytes)begin a=32'($signed(pd[i*8 +:8]));b=32'($signed(sd[i*8 +:8]));s=a+b;
          if(s>127)begin expected[i*8 +:8]=8'h7f;pos_sat=pos_sat+1;end
          else if(s< -128)begin expected[i*8 +:8]=8'h80;neg_sat=neg_sat+1;end
          else expected[i*8 +:8]=8'(s);expected_be[i]=pbe[i]&&sbe[i];end end
      if(id[0])begin fork send_primary();send_secondary();join end else begin send_secondary();send_primary();end
      wait(completed==prior+1);end endtask
  task automatic run_pool(input integer id);
    integer h,w,c,prior;integer i0,i1,i2,i3,oi,v0,v1,v2,v3,m;begin
      case(id%4)0:begin h=4;w=4;c=4;end 1:begin h=2;w=8;c=4;end
        2:begin h=8;w=2;c=4;end default:begin h=2;w=2;c=16;end endcase
      prior=completed;configure(1,4'(h),4'(w),5'(c),7'd64,16'(id));expected=0;expected_be=0;pbe='1;
      for(int i=0;i<64;i++)begin rng=next_rand(rng);pd[i*8 +:8]=rng[7:0];end
      for(int y=0;y<h/2;y++)for(int x=0;x<w/2;x++)for(int ch=0;ch<c;ch++)begin
        i0=((2*y)*w+2*x)*c+ch;i1=i0+c;i2=i0+w*c;i3=i2+c;oi=(y*(w/2)+x)*c+ch;
        v0=32'($signed(pd[i0*8 +:8]));v1=32'($signed(pd[i1*8 +:8]));
        v2=32'($signed(pd[i2*8 +:8]));v3=32'($signed(pd[i3*8 +:8]));
        m=v0;if(v1>m)m=v1;if(v2>m)m=v2;if(v3>m)m=v3;expected[oi*8 +:8]=8'(m);expected_be[oi]=1;
        if(m<0)negative_pool=negative_pool+1;end
      send_primary();wait(completed==prior+1);end endtask
  initial begin clk=0;rst_n=0;cfg_valid=0;cfg_op=0;cfg_h=0;cfg_w=0;cfg_c=0;cfg_bytes=0;cfg_tag=0;cfg_tid=0;cfg_fmt=0;
    pv=0;sv=0;pd=0;sd=0;pbe=0;sbe=0;plast=1;slast=1;pfmt=1;sfmt=1;rng=32'h6d2b79f5;
    pos_sat=0;neg_sat=0;negative_pool=0;repeat(3)@(posedge clk);rst_n=1;
    for(int t=0;t<TARGET;t++)if(t[0])run_pool(t);else run_residual(t);
    if(completed!=TARGET||received!=TARGET||errors!=0||pos_sat==0||neg_sat==0||negative_pool==0)$fatal(1,"SFU accounting");
    $display("INT8_POOL_RESIDUAL_SFU_100K_PASS operations=%0d pos_sat=%0d neg_sat=%0d negative_pool=%0d cycles=%0d output_fnv64=%016h",
      completed,pos_sat,neg_sat,negative_pool,cycles,output_hash);$finish;end
  initial begin repeat(TARGET*20+10000)@(posedge clk);$fatal(1,"SFU timeout");end
endmodule

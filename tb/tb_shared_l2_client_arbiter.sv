`timescale 1ns/1ps
module tb_shared_l2_client_arbiter;
  parameter integer TARGET=100000;localparam integer AW=10,DW=512;
  logic clk=0,rst_n=0;always #5 clk=~clk;integer cycles,accepted,responses,seed,i,b;
  logic[3:0]rv,rr,rsv,rsr;logic[4*AW-1:0]ra;logic[4*DW-1:0]rd;logic[3:0]re;
  logic[1:0]wv,wr;logic[2*AW-1:0]wa;logic[2*DW-1:0]wd;logic[127:0]wb;
  logic[1:0]prv,prr,psv,psr;logic[2*AW-1:0]pra;logic[2*DW-1:0]prd;logic[1:0]pse;
  logic pwv,pwr;logic[AW-1:0]pwa;logic[DW-1:0]pwd;logic[63:0]pwb;
  logic[31:0]promotions,rgrants,wgrants;logic[63:0]pc,prc,pwc,pconf,prstall,pwstall;
  logic[DW-1:0]model[0:(1<<AW)-1],expected[0:3],merged;logic[3:0]pending;
  logic[3:0]rfire;logic[1:0]wfire;integer client_reads[0:3],client_writes[0:1];
  logic[1:0]held_pr;logic[AW-1:0]held_addr[0:1];logic held_pw;
  logic[AW-1:0]held_waddr;logic[DW-1:0]held_wdata;logic[63:0]held_wbe;
  shared_l2_client_arbiter #(.ADDR_W(AW))arb(.clk_i(clk),.rst_ni(rst_n),
    .rd_valid_i(rv),.rd_ready_o(rr),.rd_addr_i(ra),.rd_rsp_valid_o(rsv),
    .rd_rsp_ready_i(rsr),.rd_rsp_data_o(rd),.rd_rsp_error_o(re),.wr_valid_i(wv),
    .wr_ready_o(wr),.wr_addr_i(wa),.wr_data_i(wd),.wr_be_i(wb),
    .phy_rd_valid_o(prv),.phy_rd_ready_i(prr),.phy_rd_addr_o(pra),
    .phy_rsp_valid_i(psv),.phy_rsp_ready_o(psr),.phy_rsp_data_i(prd),.phy_rsp_error_i(pse),
    .phy_wr_valid_o(pwv),.phy_wr_ready_i(pwr),.phy_wr_addr_o(pwa),.phy_wr_data_o(pwd),
    .phy_wr_be_o(pwb),.descriptor_promotions_o(promotions),.read_grants_o(rgrants),
    .write_grants_o(wgrants));
  shared_l2_fabric #(.ADDR_W(AW),.ROWS_PER_BANK(256))mem(.clk_i(clk),.rst_ni(rst_n),
    .rd_valid_i(prv),.rd_ready_o(prr),.rd_addr_i(pra),.rd_resp_valid_o(psv),
    .rd_resp_ready_i(psr),.rd_data_o(prd),.wr_valid_i(pwv),.wr_ready_o(pwr),
    .wr_addr_i(pwa),.wr_data_i(pwd),.wr_be_i(pwb),.cycle_count_o(pc),
    .read_count_o(prc),.write_count_o(pwc),.bank_conflict_count_o(pconf),
    .read_stall_count_o(prstall),.write_stall_count_o(pwstall));
  assign pse=0;
  always @(posedge clk)if(rst_n)for(int c=0;c<4;c++)if(rsv[c]&&rsr[c])begin
    if(!pending[c]||re[c]||rd[c*DW +: DW]!==expected[c])$fatal(1,"read mismatch client=%0d",c);
    pending[c]=0;responses=responses+1;end
  always @(posedge clk)if(rst_n)begin
    for(int h=0;h<2;h++)begin
      if(held_pr[h]&&!prv[h])$fatal(1,"physical read valid dropped under stall");
      if(held_pr[h]&&pra[h*AW +: AW]!==held_addr[h])$fatal(1,"physical read payload changed");
      held_pr[h]<=prv[h]&&!prr[h];if(prv[h]&&!prr[h])held_addr[h]<=pra[h*AW +: AW];
    end
    if(held_pw&&!pwv)$fatal(1,"physical write valid dropped under stall");
    if(held_pw&&(pwa!==held_waddr||pwd!==held_wdata||pwb!==held_wbe))$fatal(1,"physical write payload changed");
    held_pw<=pwv&&!pwr;if(pwv&&!pwr)begin held_waddr<=pwa;held_wdata<=pwd;held_wbe<=pwb;end
  end
  initial begin
    rv=0;ra=0;rsr='1;wv=0;wa=0;wd=0;wb=0;pending=0;rfire=0;wfire=0;
    cycles=0;accepted=0;responses=0;seed=32'h13579bdf;held_pr=0;held_pw=0;
    for(i=0;i<(1<<AW);i++)model[i]=0;for(i=0;i<4;i++)client_reads[i]=0;
    for(i=0;i<2;i++)client_writes[i]=0;repeat(3)@(posedge clk);rst_n=1;
    while(accepted<TARGET||rv!=0||wv!=0||pending!=0)begin
      @(negedge clk);for(i=0;i<4;i++)if(rfire[i])rv[i]=0;for(i=0;i<2;i++)if(wfire[i])wv[i]=0;
      for(i=0;i<4;i++)rsr[i]=($urandom(seed)%5)!=0;
      for(i=0;i<4;i++)if(accepted<TARGET&&!pending[i]&&!rv[i]&&($urandom(seed)%3)!=0)begin
        rv[i]=1;ra[i*AW +: AW]=$urandom(seed)&10'h3ff;end
      for(i=0;i<2;i++)if(accepted<TARGET&&!wv[i]&&($urandom(seed)%3)!=0)begin
        wv[i]=1;wa[i*AW +: AW]=$urandom(seed)&10'h3ff;
        for(b=0;b<16;b++)wd[i*DW+b*32 +: 32]=$urandom(seed);
        for(b=0;b<64;b++)wb[i*64+b]=($urandom(seed)%4)!=0;end
      #1;rfire=rv&rr;wfire=wv&wr;
      for(i=0;i<4;i++)if(rfire[i])begin expected[i]=model[ra[i*AW +: AW]];pending[i]=1;
        accepted=accepted+1;client_reads[i]=client_reads[i]+1;end
      for(i=0;i<2;i++)if(wfire[i])begin merged=model[wa[i*AW +: AW]];
        for(b=0;b<64;b++)if(wb[i*64+b])merged[b*8 +: 8]=wd[i*DW+b*8 +: 8];
        model[wa[i*AW +: AW]]=merged;accepted=accepted+1;client_writes[i]=client_writes[i]+1;end
      @(posedge clk);cycles=cycles+1;
    end
    repeat(3)@(posedge clk);
    if(responses!=rgrants||accepted!=rgrants+wgrants||prc!=rgrants||pwc!=wgrants)$fatal(1,"counter mismatch");
    for(i=0;i<4;i++)if(client_reads[i]==0)$fatal(1,"read client starved %0d",i);
    for(i=0;i<2;i++)if(client_writes[i]==0)$fatal(1,"write client starved %0d",i);
    if(promotions==0)$fatal(1,"descriptor promotion coverage missing");
    $display("SHARED_L2_CLIENT_ARBITER_100K_PASS transactions=%0d reads=%0d writes=%0d responses=%0d promotions=%0d",
      accepted,rgrants,wgrants,responses,promotions);$finish;
  end
  initial begin repeat(1000000)@(posedge clk);
    $display("TIMEOUT accepted=%0d rv=%b wv=%b wa=%h pending=%b slot_pending=%b slot_out=%b owners=%0d,%0d wp=%b wo=%b wrr=%b pwr=%b pwv=%b pwa=%h prv=%b mem_resp=%b",
      accepted,rv,wv,wa,pending,arb.slot_pending_q,arb.slot_outstanding_q,arb.slot_owner_q[0],arb.slot_owner_q[1],
      arb.write_pending_q,arb.write_owner_q,arb.write_rr_q,pwr,pwv,pwa,prv,mem.rd_resp_valid_q);
    $fatal(1,"timeout");end
endmodule

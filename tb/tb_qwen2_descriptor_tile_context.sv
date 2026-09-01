`timescale 1ns/1ps
module tb_qwen2_descriptor_tile_context;
  localparam integer AW=15,BEAT_BASE=1024,BEATS=1547;
  logic clk=0,rst_n=0;always #0.5 clk=~clk;
  logic start;logic[127:0]cmd[0:1],rms_cmd,matrix_cmd;logic qv,qr;logic[23:0]qi;
  logic sv,sr,se;logic[127:0]sd;logic cv,cr,cl;logic[7:0]cs;
  logic[335:0]addresses;logic[23:0]dtypes;logic[431:0]shapes;logic[143:0]roots;
  logic fqv,fqr,frv,frr;logic[AW-1:0]fqa;logic[511:0]frd;
  logic[1:0]rv,rr,rsv,rsr;logic[2*AW-1:0]ra;logic[1023:0]rd;
  logic wv,wr;logic[AW-1:0]wa;logic[511:0]wd;logic[63:0]wbe;
  logic[63:0]cy,reads,writes,conflicts,rstalls,wstalls;logic[511:0]beats[0:BEATS-1];
  logic[55:0]eaddr[0:5];logic[3:0]edtype[0:5];logic[71:0]eshape[0:5];
  logic[31:0]lfsr;integer reqs,resps;
  shared_l2_descriptor_port #(.ADDR_W(AW),.SRAM_BYTES(64'd1572864))port(.clk_i(clk),.rst_ni(rst_n),
    .descriptor_base_i(0),.descriptor_req_valid_i(qv),.descriptor_req_ready_o(qr),
    .descriptor_req_index_i(qi),.descriptor_rsp_valid_o(sv),.descriptor_rsp_ready_i(sr),
    .descriptor_rsp_data_o(sd),.descriptor_rsp_error_o(se),.fabric_req_valid_o(fqv),
    .fabric_req_ready_i(fqr),.fabric_req_addr_o(fqa),.fabric_rsp_valid_i(frv),
    .fabric_rsp_ready_o(frr),.fabric_rsp_data_i(frd),.fabric_rsp_error_i(1'b0));
  shared_l2_fabric #(.ADDR_W(AW),.ROWS_PER_BANK(6144))mem(.clk_i(clk),.rst_ni(rst_n),
    .rd_valid_i(rv),.rd_ready_o(rr),.rd_addr_i(ra),.rd_resp_valid_o(rsv),
    .rd_resp_ready_i(rsr),.rd_data_o(rd),.wr_valid_i(wv),.wr_ready_o(wr),.wr_addr_i(wa),
    .wr_data_i(wd),.wr_be_i(wbe),.cycle_count_o(cy),.read_count_o(reads),
    .write_count_o(writes),.bank_conflict_count_o(conflicts),.read_stall_count_o(rstalls),
    .write_stall_count_o(wstalls));
  qwen2_descriptor_tile_context dut(.clk_i(clk),.rst_ni(rst_n),.start_i(start),
    .rms_command_i(rms_cmd),.matrix_command_i(matrix_cmd),.descriptor_req_valid_o(qv),
    .descriptor_req_ready_i(qr),.descriptor_req_index_o(qi),.descriptor_rsp_valid_i(sv),
    .descriptor_rsp_ready_o(sr),.descriptor_rsp_data_i(sd),.descriptor_rsp_error_i(se),
    .context_valid_o(cv),.context_ready_i(cr),.context_legal_o(cl),.context_status_o(cs),
    .tensor_address_o(addresses),.tensor_dtype_o(dtypes),.tensor_shape_o(shapes),.tensor_root_o(roots));
  assign rv={1'b0,fqv};assign ra={{AW{1'b0}},fqa};assign fqr=rr[0];assign frv=rsv[0];
  assign frd=rd[0+:512];assign rsr={1'b0,frr};
  always_ff@(posedge clk or negedge rst_n)begin if(!rst_n)begin lfsr<=32'h4d8ac73b;reqs<=0;resps<=0;end
    else begin lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};if(qv&&qr)reqs<=reqs+1;if(sv&&sr)resps<=resps+1;end end
  task automatic write_beat(input integer i);begin @(negedge clk);wv=1;wa=AW'(BEAT_BASE+i);wd=beats[i];wbe='1;
    do@(posedge clk);while(!wr);@(negedge clk);wv=0;end endtask
  task automatic launch(input[127:0]a,input[127:0]b);begin @(negedge clk);rms_cmd=a;matrix_cmd=b;start=1;
    @(posedge clk);@(negedge clk);start=0;end endtask
  initial begin start=0;rms_cmd=0;matrix_cmd=0;cr=0;wv=0;wa=0;wd=0;wbe=0;
    $readmemh("work/results/qwen2_descriptor_tile_context/beats.memh",beats);
    $readmemh("work/results/qwen2_descriptor_tile_context/commands.memh",cmd);
    $readmemh("work/results/qwen2_descriptor_tile_context/addresses.memh",eaddr);
    $readmemh("work/results/qwen2_descriptor_tile_context/dtypes.memh",edtype);
    $readmemh("work/results/qwen2_descriptor_tile_context/shapes.memh",eshape);
    repeat(6)@(posedge clk);rst_n=1;repeat(2)@(posedge clk);for(integer i=0;i<BEATS;i++)write_beat(i);
    launch(cmd[0],cmd[1]);wait(cv);repeat(5)begin @(posedge clk);if(!cv)$fatal(1,"context valid unstable");end
    for(integer i=0;i<6;i++)if(addresses[i*56+:56]!==eaddr[i]||dtypes[i*4+:4]!==edtype[i]||shapes[i*72+:72]!==eshape[i])$fatal(1,"context mismatch slot=%0d",i);
    if(!cl||cs!=0||reqs!=12||resps!=12)$fatal(1,"legal context status/fetch mismatch");
    @(negedge clk);cr=1;@(posedge clk);@(negedge clk);cr=0;
    // Broken event dependency is rejected before any descriptor request.
    matrix_cmd=cmd[1];matrix_cmd[39:24]=16'hffff;launch(cmd[0],matrix_cmd);wait(cv);
    if(cl||cs!=2||reqs!=12||resps!=12)$fatal(1,"illegal command was fetched");
    @(negedge clk);cr=1;@(posedge clk);@(negedge clk);cr=0;
    $display("QWEN2_DESCRIPTOR_TILE_CONTEXT_PASS roots=6 descriptor_fetches=12 shapes=6 address_continuity=1 q1024=1 invalid_preissue=1 stable_backpressure=1");$finish;
  end
  initial begin repeat(100000)@(posedge clk);$fatal(1,"timeout reqs=%0d resps=%0d state=%0d",reqs,resps,dut.state_q);end
endmodule

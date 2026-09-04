`timescale 1ns/1ps
module tb_operator_dma_pinned_idma_v3;
  import hetero_idma_512_pkg::*;
  logic clk_i=0,rst_ni=1;always #5 clk_i=~clk_i;
  logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i;logic[15:0]req_tag_i;
  logic[7:0]req_parent_phase_i,req_terminal_phase_i;logic[23:0]req_src0_i,req_dst_i;logic[15:0]req_rows_i;
  logic descriptor_req_valid_o,descriptor_req_ready_i,descriptor_req_destination_o;
  logic[23:0]descriptor_req_index_o;logic descriptor_rsp_valid_i,descriptor_rsp_ready_o;
  logic[7:0]descriptor_rsp_status_i;logic[63:0]descriptor_rsp_address_i;
  logic[31:0]descriptor_rsp_row_bytes_i,descriptor_rsp_rows_i,descriptor_rsp_stride_i;
  logic idma_req_valid,idma_req_ready,idma_rsp_valid,idma_rsp_ready,idma_rsp_error;
  logic[63:0]idma_src,idma_dst;logic[31:0]idma_length;logic[7:0]idma_busy;
  logic completion_valid_o,completion_ready_i;logic[15:0]completion_tag_o;
  logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;logic[31:0]flat_requests_o;
  axi_req_t read_req,write_req,joined_req;axi_rsp_t read_rsp,write_rsp,joined_rsp;
  logic desc_pending,desc_role_q;integer desc_delay;

  operator_dma_endpoint_v3 endpoint(
    .*,.idma_req_valid_o(idma_req_valid),.idma_req_ready_i(idma_req_ready),
    .idma_src_addr_o(idma_src),.idma_dst_addr_o(idma_dst),.idma_length_o(idma_length),
    .idma_rsp_valid_i(idma_rsp_valid),.idma_rsp_ready_o(idma_rsp_ready),.idma_rsp_error_i(idma_rsp_error));
  idma_backend_rw_axi_flat_wrap backend(.clk_i,.rst_ni,.req_valid_i(idma_req_valid),.req_ready_o(idma_req_ready),
    .src_addr_i(idma_src),.dst_addr_i(idma_dst),.length_i(idma_length),.rsp_valid_o(idma_rsp_valid),
    .rsp_ready_i(idma_rsp_ready),.rsp_error_o(idma_rsp_error),.axi_read_req_o(read_req),
    .axi_read_rsp_i(read_rsp),.axi_write_req_o(write_req),.axi_write_rsp_i(write_rsp),.busy_o(idma_busy));
  axi_rw_join #(.axi_req_t(axi_req_t),.axi_resp_t(axi_rsp_t))joiner(.clk_i,.rst_ni,
    .slv_read_req_i(read_req),.slv_read_resp_o(read_rsp),.slv_write_req_i(write_req),
    .slv_write_resp_o(write_rsp),.mst_req_o(joined_req),.mst_resp_i(joined_rsp));
  axi_sim_mem #(.AddrWidth(64),.DataWidth(512),.IdWidth(4),.UserWidth(1),.axi_req_t(axi_req_t),
    .axi_rsp_t(axi_rsp_t),.WarnUninitialized(1'b0),.ClearErrOnAccess(1'b1),
    .ApplDelay(1ns),.AcqDelay(9ns))mem(.clk_i,.rst_ni,.axi_req_i(joined_req),.axi_rsp_o(joined_rsp),
    .mon_r_last_o(),.mon_r_beat_count_o(),.mon_r_user_o(),.mon_r_id_o(),.mon_r_data_o(),
    .mon_r_addr_o(),.mon_r_valid_o(),.mon_w_last_o(),.mon_w_beat_count_o(),.mon_w_user_o(),
    .mon_w_id_o(),.mon_w_data_o(),.mon_w_addr_o(),.mon_w_valid_o());

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni)begin desc_pending<=0;descriptor_rsp_valid_i<=0;desc_delay<=0;desc_role_q<=0;
      descriptor_rsp_status_i<=0;descriptor_rsp_address_i<=0;descriptor_rsp_row_bytes_i<=0;
      descriptor_rsp_rows_i<=0;descriptor_rsp_stride_i<=0;end
    else begin
      if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)descriptor_rsp_valid_i<=0;
      if(descriptor_req_valid_o&&descriptor_req_ready_i)begin desc_pending<=1;desc_delay<=1;desc_role_q<=descriptor_req_destination_o;end
      if(desc_pending)begin if(desc_delay==0)begin desc_pending<=0;descriptor_rsp_valid_i<=1;
        descriptor_rsp_status_i<=0;descriptor_rsp_address_i<=desc_role_q?64'h8000:64'h1000;
        descriptor_rsp_row_bytes_i<=64;descriptor_rsp_rows_i<=3;
        descriptor_rsp_stride_i<=desc_role_q?256:128;end else desc_delay<=desc_delay-1;end
    end
  end
  task automatic run_op(input logic[7:0]op,input logic[15:0]tag,input logic[15:0]rows);
    begin @(negedge clk_i);req_opcode_i=op;req_tag_i=tag;req_rows_i=rows;req_valid_i=1;
      do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;
      wait(completion_valid_o);if(completion_status_o!=0||completion_tag_o!=tag)$fatal(1,"bad completion");
      @(negedge clk_i);completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;end
  endtask
  initial begin repeat(20000)@(posedge clk_i);$fatal(1,"timeout");end
  initial begin
    #1 rst_ni=0;req_valid_i=0;req_opcode_i=0;req_tag_i=0;req_parent_phase_i=8'h12;
    req_terminal_phase_i=8'h34;req_src0_i=24'h10;req_dst_i=24'h20;req_rows_i=0;
    descriptor_req_ready_i=1;
    completion_ready_i=0;
    repeat(3)@(posedge clk_i);@(negedge clk_i);rst_ni=1;
    for(int r=0;r<3;r++)for(int i=0;i<64;i++)mem.mem[64'h1000+r*128+i]=(r*64+i)^8'h5a;
    run_op(8'h10,16'h1001,1);run_op(8'h11,16'h1002,1);
    run_op(8'h12,16'h1003,3);run_op(8'h13,16'h1004,3);
    for(int r=0;r<3;r++)for(int i=0;i<64;i++)if(mem.mem[64'h8000+r*256+i]!==((r*64+i)^8'h5a))$fatal(1,"copy mismatch row=%0d byte=%0d",r,i);
    if(flat_requests_o!=8||idma_busy!=0)$fatal(1,"bad request count or busy");
    $display("OPERATOR_DMA_PINNED_IDMA_V3_PASS opcodes=4 requests=8 bytes=512");$finish;
  end
endmodule

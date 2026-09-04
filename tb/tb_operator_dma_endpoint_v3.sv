`timescale 1ns/1ps
module tb_operator_dma_endpoint_v3;
  logic clk_i=0,rst_ni=1;always #1 clk_i=~clk_i;
  logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i;logic[15:0]req_tag_i;
  logic[7:0]req_parent_phase_i,req_terminal_phase_i;logic[23:0]req_src0_i,req_dst_i;logic[15:0]req_rows_i;
  logic descriptor_req_valid_o,descriptor_req_ready_i,descriptor_req_destination_o;
  logic[23:0]descriptor_req_index_o;logic descriptor_rsp_valid_i,descriptor_rsp_ready_o;
  logic[7:0]descriptor_rsp_status_i;logic[63:0]descriptor_rsp_address_i;
  logic[31:0]descriptor_rsp_row_bytes_i,descriptor_rsp_rows_i,descriptor_rsp_stride_i;
  logic idma_req_valid_o,idma_req_ready_i,idma_rsp_valid_i,idma_rsp_ready_o,idma_rsp_error_i;
  logic[63:0]idma_src_addr_o,idma_dst_addr_o;logic[31:0]idma_length_o;
  logic completion_valid_o,completion_ready_i;logic[15:0]completion_tag_o;
  logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;logic[31:0]flat_requests_o;
  logic desc_pending,idma_pending;logic desc_role_q;integer desc_delay,idma_delay,total_idma;
  operator_dma_endpoint_v3 dut(.*);

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni)begin desc_pending<=0;descriptor_rsp_valid_i<=0;desc_delay<=0;desc_role_q<=0;end
    else begin
      if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)descriptor_rsp_valid_i<=0;
      if(descriptor_req_valid_o&&descriptor_req_ready_i)begin desc_pending<=1;desc_delay<=1;desc_role_q<=descriptor_req_destination_o;end
      if(desc_pending)begin if(desc_delay==0)begin desc_pending<=0;descriptor_rsp_valid_i<=1;
        descriptor_rsp_status_i<=0;descriptor_rsp_address_i<=desc_role_q?64'h8000:64'h1000;
        descriptor_rsp_row_bytes_i<=64;descriptor_rsp_rows_i<=3;
        descriptor_rsp_stride_i<=desc_role_q?256:128;end else desc_delay<=desc_delay-1;end
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni)begin idma_pending<=0;idma_rsp_valid_i<=0;idma_delay<=0;total_idma<=0;end
    else begin
      if(idma_rsp_valid_i&&idma_rsp_ready_o)idma_rsp_valid_i<=0;
      if(idma_req_valid_o&&idma_req_ready_i)begin idma_pending<=1;idma_delay<=2;total_idma<=total_idma+1;end
      if(idma_pending)begin if(idma_delay==0)begin idma_pending<=0;idma_rsp_valid_i<=1;idma_rsp_error_i<=0;end else idma_delay<=idma_delay-1;end
    end
  end

  task automatic run_op(input logic[7:0]op,input logic[15:0]tag,input logic[15:0]rows);
    begin
      @(negedge clk_i);req_opcode_i=op;req_tag_i=tag;req_rows_i=rows;req_valid_i=1;
      do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;
      wait(completion_valid_o);
      if(completion_status_o!=0||completion_tag_o!=tag||completion_parent_phase_o!=8'h12||completion_terminal_phase_o!=8'h34)$fatal(1,"bad dma completion");
      @(negedge clk_i);completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;
    end
  endtask
  initial begin repeat(2000)@(posedge clk_i);$fatal(1,"watchdog");end
  initial begin
    #0.1 rst_ni=0;req_valid_i=0;req_opcode_i=0;req_tag_i=0;req_parent_phase_i=8'h12;
    req_terminal_phase_i=8'h34;req_src0_i=24'h10;req_dst_i=24'h20;req_rows_i=0;
    descriptor_req_ready_i=1;descriptor_rsp_valid_i=0;descriptor_rsp_status_i=0;
    descriptor_rsp_address_i=0;descriptor_rsp_row_bytes_i=0;descriptor_rsp_rows_i=0;descriptor_rsp_stride_i=0;
    idma_req_ready_i=1;idma_rsp_valid_i=0;idma_rsp_error_i=0;completion_ready_i=0;
    repeat(3)@(posedge clk_i);@(negedge clk_i);rst_ni=1;
    run_op(8'h10,16'h1001,1);run_op(8'h11,16'h1002,1);
    run_op(8'h12,16'h1003,3);run_op(8'h13,16'h1004,3);
    if(total_idma!=8||flat_requests_o!=8)$fatal(1,"unexpected idma request count %0d %0d",total_idma,flat_requests_o);
    @(negedge clk_i);req_opcode_i=8'hff;req_tag_i=16'h2001;req_valid_i=1;
    @(posedge clk_i);@(negedge clk_i);req_valid_i=0;wait(completion_valid_o);
    if(completion_status_o!=4)$fatal(1,"illegal dma opcode accepted");
    $display("OPERATOR_DMA_ENDPOINT_V3_PASS opcodes=4 idma_requests=8 illegal=1");$finish;
  end
endmodule

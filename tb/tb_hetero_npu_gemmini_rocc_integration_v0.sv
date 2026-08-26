`timescale 1ns/1ps
module tb_hetero_npu_gemmini_rocc_integration_v0;
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  integer cycles, event_count, rocc_count, busy_countdown;
  logic host_valid, host_ready;
  logic [127:0] host_data;
  logic host_event_valid, host_event_ready;
  logic [55:0] host_event_data;
  logic illegal_engine, illegal_rocc;
  logic rocc_valid, rocc_ready;
  logic [6:0] funct, opcode;
  logic [4:0] rs1_idx, rs2_idx, rd;
  logic xd, xs1, xs2;
  logic [63:0] rs1, rs2;
  logic resp_valid, resp_ready, rocc_busy;
  logic [4:0] resp_rd;
  logic [63:0] resp_data;
  logic seen_matrix, seen_sfu;
  logic descriptor_req_valid,descriptor_req_ready,descriptor_rsp_valid,descriptor_rsp_ready;
  logic[23:0] descriptor_req_index,pending_descriptor_index;
  logic[63:0] descriptor_req_byte_addr;
  logic[127:0] descriptor_rsp_data;
  logic descriptor_rsp_error,descriptor_pending;
  logic[127:0] descriptor_mem[0:63],matrix_command_mem[0:0];logic descriptor_present[0:63];
  logic scale_req_valid,scale_req_ready,scale_rsp_valid,scale_rsp_ready,scale_rsp_error;
  logic[47:0]scale_req_addr;logic[31:0]scale_rsp_data;
  assign rocc_ready = (cycles % 3) != 0;
  assign host_event_ready = (cycles % 4) != 1;

  hetero_npu_gemmini_rocc_integration_v0 dut (
    .clk_i(clk), .rst_ni(rst_n), .host_cmd_valid_i(host_valid), .host_cmd_ready_o(host_ready),
    .host_cmd_data_i(host_data), .host_event_valid_o(host_event_valid), .host_event_ready_i(host_event_ready),
    .host_event_data_o(host_event_data), .illegal_engine_o(illegal_engine), .illegal_rocc_command_o(illegal_rocc),
    .descriptor_base_i(64'h4000),.descriptor_req_valid_o(descriptor_req_valid),
    .descriptor_req_ready_i(descriptor_req_ready),.descriptor_req_index_o(descriptor_req_index),
    .descriptor_req_byte_addr_o(descriptor_req_byte_addr),.descriptor_rsp_valid_i(descriptor_rsp_valid),
    .descriptor_rsp_ready_o(descriptor_rsp_ready),.descriptor_rsp_data_i(descriptor_rsp_data),
    .descriptor_rsp_error_i(descriptor_rsp_error),
    .scale_req_valid_o(scale_req_valid),.scale_req_ready_i(scale_req_ready),.scale_req_addr_o(scale_req_addr),
    .scale_rsp_valid_i(scale_rsp_valid),.scale_rsp_ready_o(scale_rsp_ready),
    .scale_rsp_data_i(scale_rsp_data),.scale_rsp_error_i(scale_rsp_error),
    .rocc_cmd_valid_o(rocc_valid), .rocc_cmd_ready_i(rocc_ready), .rocc_inst_funct_o(funct),
    .rocc_inst_rs2_o(rs2_idx), .rocc_inst_rs1_o(rs1_idx), .rocc_inst_xd_o(xd), .rocc_inst_xs1_o(xs1),
    .rocc_inst_xs2_o(xs2), .rocc_inst_rd_o(rd), .rocc_inst_opcode_o(opcode), .rocc_rs1_o(rs1), .rocc_rs2_o(rs2),
    .rocc_resp_valid_i(resp_valid), .rocc_resp_ready_o(resp_ready), .rocc_resp_rd_i(resp_rd),
    .rocc_resp_data_i(resp_data), .rocc_busy_i(rocc_busy)
  );

  assign descriptor_req_ready=(cycles%5)!=1&&!descriptor_pending;
  assign descriptor_rsp_valid=descriptor_pending;
  assign descriptor_rsp_data=pending_descriptor_index<64?descriptor_mem[pending_descriptor_index[5:0]]:'0;
  assign descriptor_rsp_error=pending_descriptor_index>=64||!descriptor_present[pending_descriptor_index[5:0]];
  assign scale_req_ready=1;assign scale_rsp_valid=0;assign scale_rsp_data=0;assign scale_rsp_error=0;

  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;rocc_count<=0;busy_countdown<=0;descriptor_pending<=0;
      pending_descriptor_index<=0;rocc_busy<=0;
    end
    else cycles <= cycles + 1;
    if(rst_n)begin
      if(descriptor_req_valid&&descriptor_req_ready)begin
        if(descriptor_req_byte_addr!==64'h4000+{36'd0,descriptor_req_index,4'b0})$fatal(1,"descriptor address mismatch");
        descriptor_pending<=1;pending_descriptor_index<=descriptor_req_index;
      end
      if(descriptor_rsp_valid&&descriptor_rsp_ready)descriptor_pending<=0;
      if(rocc_valid&&rocc_ready)begin
        rocc_count<=rocc_count+1;
        if(opcode!=7'h7b||xd||!xs1||!xs2)$fatal(1,"not CUSTOM_3 envelope");
        if(rocc_count==10)busy_countdown<=5;
      end
      if(busy_countdown>0)begin
        busy_countdown<=busy_countdown-1;rocc_busy<=busy_countdown>1;
      end
    end
    if (rst_n && host_event_valid && host_event_ready) begin
      event_count <= event_count + 1;
      if (host_event_data[55:40] == 16'h1234) seen_matrix <= 1'b1;
      if (host_event_data[55:40] == 16'd2) seen_sfu <= 1'b1;
    end
  end

  task automatic send_command(input logic [7:0] op, input logic [2:0] engine,
                              input logic [15:0] signal_id);
    begin
      @(negedge clk);
      host_data = '0; host_data[7:0] = op; host_data[10:8] = engine;
      host_data[55:40] = signal_id;
      if(engine==3'd2)host_data=matrix_command_mem[0];
      else begin host_data[79:56]=24'h123456;host_data[103:80]=24'h654321;host_data[127:104]=3;end
      host_valid = 1'b1;
      do @(posedge clk); while (!host_ready);
      @(negedge clk); host_valid = 1'b0;
    end
  endtask

  initial begin
    host_valid = 0; host_data = 0; resp_valid = 0; resp_rd = 0; resp_data = 0;
    cycles = 0; event_count = 0; seen_matrix = 0; seen_sfu = 0;
    $readmemh("tests/vectors/gemmini_loop_ws_desc.memh",descriptor_mem);
    $readmemh("tests/vectors/gemmini_loop_ws_present.memh",descriptor_present);
    $readmemh("tests/vectors/gemmini_loop_ws_command.memh",matrix_command_mem,0,0);
    repeat (3) @(posedge clk); rst_n = 1;
    send_command(8'h20, 3'd2, 16'd1);
    wait (seen_matrix);
    send_command(8'h30, 3'd3, 16'd2);
    wait (seen_sfu);
    if (event_count != 2 || rocc_count != 11 || illegal_engine || illegal_rocc || resp_ready||scale_req_valid)
      $fatal(1, "integrated event/illegal result mismatch");
    $display("GEMMINI_ROCC_INTEGRATION_PASS cycles=%0d", cycles);
    $finish;
  end
  initial begin
    repeat (1000) @(posedge clk);
    $fatal(1, "integrated RoCC timeout");
  end
endmodule

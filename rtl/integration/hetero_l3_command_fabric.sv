// SPDX-License-Identifier: Apache-2.0
// Production L3 command/event frontend, completion merge, watchdog and L2 arbiter.
`timescale 1ns/1ps
module hetero_l3_command_fabric #(
  parameter integer ADDR_W = 15,
  parameter integer DATA_W = 512,
  parameter bit WATCHDOG_ENABLE = 1'b1,
  parameter integer WATCHDOG_CYCLES = 4096
) (
  input  logic                    clk_i,
  input  logic                    rst_ni,
  input  logic                    host_cmd_valid_i,
  output logic                    host_cmd_ready_o,
  input  logic [127:0]            host_cmd_data_i,

  output logic [5:0]              engine_cmd_valid_o,
  input  logic [5:0]              engine_cmd_ready_i,
  output logic [6*128-1:0]        engine_cmd_data_o,
  input  logic [5:0]              engine_completion_valid_i,
  output logic [5:0]              engine_completion_ready_o,
  input  logic [6*56-1:0]         engine_completion_data_i,

  output logic                    init_done_o,
  output logic [4:0]              command_level_o,
  output logic [4:0]              completion_level_o,
  output logic [31:0]             event_macro_error_count_o,
  output logic                    illegal_engine_o,
  output logic                    watchdog_lock_o,
  output logic [31:0]             completion_grants_o,
  output logic [31:0]             completion_protocol_error_count_o,

  input  logic [3:0]              l2_rd_valid_i,
  output logic [3:0]              l2_rd_ready_o,
  input  logic [4*ADDR_W-1:0]     l2_rd_addr_i,
  output logic [3:0]              l2_rd_rsp_valid_o,
  input  logic [3:0]              l2_rd_rsp_ready_i,
  output logic [4*DATA_W-1:0]     l2_rd_rsp_data_o,
  output logic [3:0]              l2_rd_rsp_error_o,
  input  logic [1:0]              l2_wr_valid_i,
  output logic [1:0]              l2_wr_ready_o,
  input  logic [2*ADDR_W-1:0]     l2_wr_addr_i,
  input  logic [2*DATA_W-1:0]     l2_wr_data_i,
  input  logic [2*(DATA_W/8)-1:0] l2_wr_be_i,

  output logic [1:0]              phy_rd_valid_o,
  input  logic [1:0]              phy_rd_ready_i,
  output logic [2*ADDR_W-1:0]     phy_rd_addr_o,
  input  logic [1:0]              phy_rsp_valid_i,
  output logic [1:0]              phy_rsp_ready_o,
  input  logic [2*DATA_W-1:0]     phy_rsp_data_i,
  input  logic [1:0]              phy_rsp_error_i,
  output logic                    phy_wr_valid_o,
  input  logic                    phy_wr_ready_i,
  output logic [ADDR_W-1:0]       phy_wr_addr_o,
  output logic [DATA_W-1:0]       phy_wr_data_o,
  output logic [DATA_W/8-1:0]     phy_wr_be_o,
  output logic [31:0]             descriptor_promotions_o,
  output logic [31:0]             l2_read_grants_o,
  output logic [31:0]             l2_write_grants_o
);
  localparam logic [7:0] STATUS_ILLEGAL = 8'd1;
  localparam logic [7:0] STATUS_WATCHDOG = 8'd6;
  localparam logic [31:0] WATCHDOG_LIMIT = 32'(WATCHDOG_CYCLES);

  logic frontend_host_ready;
  logic runnable_valid, runnable_ready;
  logic [127:0] runnable_data;
  logic completion_valid, completion_ready;
  logic [55:0] completion_data;

  logic dispatch_valid, dispatch_ready, dispatch_illegal;
  logic [5:0] dispatch_engine_valid, dispatch_engine_ready;
  logic [6*128-1:0] dispatch_engine_data;
  logic [5:0] inflight_q;
  logic [15:0] inflight_event_q [0:5];
  logic [31:0] watchdog_count_q [0:5];
  logic [5:0] command_fire, external_completion_fire;

  logic synthetic_pending_q;
  logic [55:0] synthetic_data_q;
  logic [6:0] completion_inputs_valid, completion_inputs_ready;
  logic [7*56-1:0] completion_inputs_data;
  logic illegal_accept;
  logic timeout_select_valid;
  logic [2:0] timeout_select_engine;
  integer timeout_scan;

  command_event_frontend_sram u_event_frontend (
    .clk_i, .rst_ni,
    .host_cmd_valid_i(host_cmd_valid_i && !watchdog_lock_o),
    .host_cmd_ready_o(frontend_host_ready), .host_cmd_data_i,
    .runnable_cmd_valid_o(runnable_valid), .runnable_cmd_ready_i(runnable_ready),
    .runnable_cmd_data_o(runnable_data), .completion_valid_i(completion_valid),
    .completion_ready_o(completion_ready), .completion_data_i(completion_data),
    .init_done_o, .command_level_o, .completion_level_o,
    .macro_error_count_o(event_macro_error_count_o)
  );
  assign host_cmd_ready_o = frontend_host_ready && !watchdog_lock_o;

  assign dispatch_valid = runnable_valid && !watchdog_lock_o;
  assign runnable_ready = !watchdog_lock_o &&
    (dispatch_illegal ? !synthetic_pending_q : dispatch_ready);

  command_dispatch u_dispatch (
    .cmd_valid_i(dispatch_valid), .cmd_ready_o(dispatch_ready),
    .cmd_data_i(runnable_data),
    .control_valid_o(dispatch_engine_valid[0]),
    .control_ready_i(dispatch_engine_ready[0]),
    .control_data_o(dispatch_engine_data[0*128 +: 128]),
    .dma_valid_o(dispatch_engine_valid[1]),
    .dma_ready_i(dispatch_engine_ready[1]),
    .dma_data_o(dispatch_engine_data[1*128 +: 128]),
    .matrix_valid_o(dispatch_engine_valid[2]),
    .matrix_ready_i(dispatch_engine_ready[2]),
    .matrix_data_o(dispatch_engine_data[2*128 +: 128]),
    .sfu_valid_o(dispatch_engine_valid[3]),
    .sfu_ready_i(dispatch_engine_ready[3]),
    .sfu_data_o(dispatch_engine_data[3*128 +: 128]),
    .kv_valid_o(dispatch_engine_valid[4]),
    .kv_ready_i(dispatch_engine_ready[4]),
    .kv_data_o(dispatch_engine_data[4*128 +: 128]),
    .collective_valid_o(dispatch_engine_valid[5]),
    .collective_ready_i(dispatch_engine_ready[5]),
    .collective_data_o(dispatch_engine_data[5*128 +: 128]),
    .illegal_engine_o(dispatch_illegal)
  );

  always_comb begin
    for (int unsigned cmd_engine = 0; cmd_engine < 6; cmd_engine++) begin
      dispatch_engine_ready[cmd_engine] = engine_cmd_ready_i[cmd_engine] &&
                                            !inflight_q[cmd_engine] &&
                                            !watchdog_lock_o;
      engine_cmd_valid_o[cmd_engine] = dispatch_engine_valid[cmd_engine] &&
                                         !inflight_q[cmd_engine] &&
                                         !watchdog_lock_o;
      engine_cmd_data_o[cmd_engine*128 +: 128] =
        dispatch_engine_data[cmd_engine*128 +: 128];
    end
  end
  assign command_fire = engine_cmd_valid_o & engine_cmd_ready_i;
  assign illegal_accept = dispatch_valid && dispatch_illegal && runnable_ready;
  assign illegal_engine_o = illegal_accept;

  assign completion_inputs_valid[5:0] = engine_completion_valid_i;
  assign completion_inputs_valid[6] = synthetic_pending_q;
  assign completion_inputs_data[6*56-1:0] = engine_completion_data_i;
  assign completion_inputs_data[6*56 +: 56] = synthetic_data_q;
  assign engine_completion_ready_o = completion_inputs_ready[5:0];
  assign external_completion_fire = engine_completion_valid_i &
                                    engine_completion_ready_o;

  engine_completion_rr_arbiter u_completion_arbiter (
    .clk_i, .rst_ni, .in_valid_i(completion_inputs_valid),
    .in_ready_o(completion_inputs_ready), .in_data_i(completion_inputs_data),
    .out_valid_o(completion_valid), .out_ready_i(completion_ready),
    .out_data_o(completion_data), .grants_o(completion_grants_o)
  );

  always_comb begin
    timeout_select_valid = 0;
    timeout_select_engine = 0;
    for (timeout_scan = 0; timeout_scan < 6; timeout_scan++) begin
      if (!timeout_select_valid && inflight_q[timeout_scan] &&
          !external_completion_fire[timeout_scan] && WATCHDOG_ENABLE &&
          watchdog_count_q[timeout_scan] >= WATCHDOG_LIMIT - 1'b1) begin
        timeout_select_valid = 1;
        timeout_select_engine = 3'(timeout_scan);
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      inflight_q <= 0;
      synthetic_pending_q <= 0;
      synthetic_data_q <= 0;
      watchdog_lock_o <= 0;
      completion_protocol_error_count_o <= 0;
      for (int unsigned reset_engine = 0; reset_engine < 6; reset_engine++) begin
        inflight_event_q[reset_engine] <= 0;
        watchdog_count_q[reset_engine] <= 0;
      end
    end else begin
      if (synthetic_pending_q && completion_inputs_ready[6])
        synthetic_pending_q <= 0;

      for (int unsigned state_engine = 0; state_engine < 6; state_engine++) begin
        if (command_fire[state_engine]) begin
          inflight_q[state_engine] <= 1;
          inflight_event_q[state_engine] <=
            engine_cmd_data_o[state_engine*128 + 40 +: 16];
          watchdog_count_q[state_engine] <= 0;
        end else if (external_completion_fire[state_engine]) begin
          inflight_q[state_engine] <= 0;
          watchdog_count_q[state_engine] <= 0;
          if (!inflight_q[state_engine] ||
              engine_completion_data_i[state_engine*56 + 29 +: 3] !=
                3'(state_engine))
            completion_protocol_error_count_o <=
              completion_protocol_error_count_o + 1'b1;
        end else if (inflight_q[state_engine] &&
                     watchdog_count_q[state_engine] < WATCHDOG_LIMIT) begin
          watchdog_count_q[state_engine] <= watchdog_count_q[state_engine] + 1'b1;
        end
      end

      if (illegal_accept && !synthetic_pending_q) begin
        synthetic_pending_q <= 1;
        synthetic_data_q <= {runnable_data[55:40], STATUS_ILLEGAL,
                             runnable_data[10:8], 29'd0};
      end else if (timeout_select_valid && !synthetic_pending_q &&
                   !watchdog_lock_o) begin
        synthetic_pending_q <= 1;
        synthetic_data_q <= {inflight_event_q[timeout_select_engine],
                             STATUS_WATCHDOG, timeout_select_engine,
                             watchdog_count_q[timeout_select_engine][28:0]};
        watchdog_lock_o <= 1;
      end
    end
  end

  shared_l2_client_arbiter #(.ADDR_W(ADDR_W), .DATA_W(DATA_W)) u_l2_arbiter (
    .clk_i, .rst_ni, .rd_valid_i(l2_rd_valid_i), .rd_ready_o(l2_rd_ready_o),
    .rd_addr_i(l2_rd_addr_i), .rd_rsp_valid_o(l2_rd_rsp_valid_o),
    .rd_rsp_ready_i(l2_rd_rsp_ready_i), .rd_rsp_data_o(l2_rd_rsp_data_o),
    .rd_rsp_error_o(l2_rd_rsp_error_o), .wr_valid_i(l2_wr_valid_i),
    .wr_ready_o(l2_wr_ready_o), .wr_addr_i(l2_wr_addr_i),
    .wr_data_i(l2_wr_data_i), .wr_be_i(l2_wr_be_i),
    .phy_rd_valid_o, .phy_rd_ready_i, .phy_rd_addr_o,
    .phy_rsp_valid_i, .phy_rsp_ready_o, .phy_rsp_data_i, .phy_rsp_error_i,
    .phy_wr_valid_o, .phy_wr_ready_i, .phy_wr_addr_o, .phy_wr_data_o,
    .phy_wr_be_o, .descriptor_promotions_o,
    .read_grants_o(l2_read_grants_o), .write_grants_o(l2_write_grants_o)
  );
endmodule

// SPDX-License-Identifier: Apache-2.0
// Small executable L6 shared-L2 contract: 2 read clients, 1 write client,
// bank-aware arbitration and one-cycle registered read responses.
module shared_l2_fabric #(
  parameter integer DATA_W = 512,
  parameter integer ADDR_W = 10,
  parameter integer BANKS  = 16
) (
  input  logic                   clk_i,
  input  logic                   rst_ni,
  input  logic [1:0]             rd_valid_i,
  output logic [1:0]             rd_ready_o,
  input  logic [2*ADDR_W-1:0]    rd_addr_i,
  output logic [1:0]             rd_resp_valid_o,
  input  logic [1:0]             rd_resp_ready_i,
  output logic [2*DATA_W-1:0]    rd_data_o,
  input  logic                   wr_valid_i,
  output logic                   wr_ready_o,
  input  logic [ADDR_W-1:0]      wr_addr_i,
  input  logic [DATA_W-1:0]      wr_data_i,
  input  logic [DATA_W/8-1:0]    wr_be_i
);
  localparam integer BANK_W = (BANKS <= 2) ? 1 : $clog2(BANKS);
  localparam integer DEPTH  = (1 << ADDR_W);
  logic [DATA_W-1:0] mem_q [0:DEPTH-1];
  logic [1:0] rd_resp_valid_q;
  logic [2*DATA_W-1:0] rd_data_q;
  logic [1:0] rd_grant;
  logic wr_grant;
  logic [BANK_W-1:0] rd_bank0, rd_bank1, wr_bank;
  integer byte_index;

`ifndef SYNTHESIS
  integer init_index;
  initial begin
    for (init_index = 0; init_index < DEPTH; init_index++)
      mem_q[init_index] = '0;
  end
`endif

  assign rd_bank0 = rd_addr_i[0 +: BANK_W];
  assign rd_bank1 = rd_addr_i[ADDR_W +: BANK_W];
  assign wr_bank  = wr_addr_i[0 +: BANK_W];

  always_comb begin
    rd_grant = '0;
    wr_grant = wr_valid_i;
    if (rd_valid_i[0] && !rd_resp_valid_q[0] &&
        (!wr_valid_i || rd_bank0 != wr_bank))
      rd_grant[0] = 1'b1;
    if (rd_valid_i[1] && !rd_resp_valid_q[1] &&
        (!wr_valid_i || rd_bank1 != wr_bank) &&
        (!rd_grant[0] || rd_bank1 != rd_bank0))
      rd_grant[1] = 1'b1;
    rd_ready_o = rd_grant;
    wr_ready_o = wr_grant;
  end

  assign rd_resp_valid_o = rd_resp_valid_q;
  assign rd_data_o       = rd_data_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rd_resp_valid_q <= '0;
      rd_data_q       <= '0;
    end else begin
      if (wr_valid_i && wr_ready_o) begin
        for (byte_index = 0; byte_index < DATA_W/8; byte_index++) begin
          if (wr_be_i[byte_index])
            mem_q[wr_addr_i][byte_index*8 +: 8] <= wr_data_i[byte_index*8 +: 8];
        end
      end
      for (byte_index = 0; byte_index < 2; byte_index++) begin
        if (rd_resp_valid_q[byte_index] && rd_resp_ready_i[byte_index])
          rd_resp_valid_q[byte_index] <= 1'b0;
      end
      if (rd_grant[0]) begin
        rd_data_q[0*DATA_W +: DATA_W] <= mem_q[rd_addr_i[0 +: ADDR_W]];
        rd_resp_valid_q[0] <= 1'b1;
      end
      if (rd_grant[1]) begin
        rd_data_q[1*DATA_W +: DATA_W] <= mem_q[rd_addr_i[ADDR_W +: ADDR_W]];
        rd_resp_valid_q[1] <= 1'b1;
      end
    end
  end
endmodule

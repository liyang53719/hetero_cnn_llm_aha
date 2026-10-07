// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Bounded experimental SharedL2 consumer for the all-products-BF16 RoPE policy.
// This is not a Command128 endpoint or a full Q8 tensor implementation.
// Tensor: one or two contiguous 256-element BF16 heads; rotary_dim is 64.
// Trig: two aligned 512-bit beats, cos[0:31] followed by sin[0:31], shared by
// both heads. All reads finish before any output is written, including when
// the output range overlaps the input or coefficient range.
// Reset must also reset the fabric, and stay low for at least two rising
// clocks for the registered HardFloat primitives. Reset discards unfinished
// work; it cannot roll back writes that the fabric already accepted.
module rope_bf16_l2_candidate #(
    parameter integer ADDR_W = 15,
    // Match the attached fabric's implemented beat capacity. Its default
    // four bank groups x 6144 rows expose 24576 beats, not all 15 address bits.
    parameter longint unsigned L2_BEATS =
        ADDR_W < 15 ? (64'd1 << ADDR_W) : 64'd24576
) (
    input logic clk_i,
    input logic rst_ni,
    input logic start_i,
    input logic [5:0] data_beats_i,
    input logic [9:0] heads_i,
    input logic [9:0] head_dim_i,
    input logic [3:0] position_lane_i,
    input logic [63:0] data_local_i,
    input logic [63:0] position_local_i,
    input logic [63:0] out_local_i,
    input logic [63:0] candidate_trig_local_i,
    input logic [9:0] candidate_rotary_dim_i,
    input logic [7:0] candidate_policy_i,
    output logic ready_o,
    output logic l2_rd_valid_o,
    input logic l2_rd_ready_i,
    output logic [ADDR_W-1:0] l2_rd_addr_o,
    input logic l2_rsp_valid_i,
    output logic l2_rsp_ready_o,
    input logic [511:0] l2_rsp_data_i,
    output logic l2_wr_valid_o,
    input logic l2_wr_ready_i,
    output logic [ADDR_W-1:0] l2_wr_addr_o,
    output logic [511:0] l2_wr_data_o,
    output logic [63:0] l2_wr_be_o,
    output logic done_o,
    output logic unsupported_position_o,
    output logic [31:0] read_beats_o,
    output logic [31:0] write_beats_o,
    output logic [31:0] pairs_o,
    output logic [31:0] position_o,
    output logic [31:0] coefficient_steps_o,
    output logic [4:0] exception_flags_o
);
    typedef enum logic [3:0] {
        IDLE, CHECK, DATA_REQ, DATA_RSP, TRIG_REQ, TRIG_RSP,
        PAIR_REQ, PAIR_RSP, PACK, WRITE, DONE
    } state_t;
    state_t state_q;

    // One carry bit is essential: truncating a 64-bit end address before
    // validation could turn an overflowing descriptor into a legal request.
    localparam logic [64:0] BYTE_LIMIT = 65'(L2_BEATS) << 6;
    logic [63:0] data_local_q, trig_local_q, out_local_q;
    // Position is captured with the descriptor but not interpreted by this
    // explicit-coefficient candidate. The legacy branch retains its policy.
    logic [63:0] position_local_q;
    logic [3:0] position_lane_q;
    logic [5:0] data_beats_q;
    logic [9:0] heads_q, head_dim_q, rotary_dim_q;
    logic [7:0] policy_q;
    logic [4:0] read_index_q, write_index_q, write_count_q;
    logic trig_index_q;
    logic [5:0] pair_index_q;
    logic [6:0] pair_count_q;
    logic [511:0] tensor_q [0:15];
    logic [511:0] cos_q, sin_q;
    logic [ADDR_W-1:0] write_addr_q;
    logic [511:0] write_data_q;
    logic [63:0] write_be_q;
    logic [511:0] packed_data;
    logic [63:0] packed_be;
    logic [64:0] tensor_bytes;
    logic descriptor_supported;
    logic pair_in_valid, pair_in_ready, pair_out_valid, pair_out_ready;
    logic [31:0] pair_even, pair_odd, pair_cos, pair_sin;
    logic [15:0] result_even, result_odd;
    logic [4:0] result_flags;
    integer even_element, odd_element;
    integer source_word;

    initial begin
        if (ADDR_W < 1 || ADDR_W > 58)
            $error("rope_bf16_l2_candidate requires 1 <= ADDR_W <= 58");
        if (L2_BEATS == 0 || 65'(L2_BEATS) > (65'd1 << ADDR_W))
            $error("rope_bf16_l2_candidate requires 0 < L2_BEATS <= 2**ADDR_W");
    end

    function automatic logic range_fits(
        input logic [63:0] base,
        input logic [64:0] length
    );
        range_fits = ({1'b0, base} < BYTE_LIMIT) && (length != 0) &&
                     ({1'b0, base} + length <= BYTE_LIMIT);
    endfunction

    assign tensor_bytes = {59'd0, data_beats_q} << 6;
    assign descriptor_supported =
        policy_q == 8'hb1 && head_dim_q == 10'd256 && rotary_dim_q == 10'd64 &&
        ((heads_q == 10'd1 && data_beats_q == 6'd8) ||
         (heads_q == 10'd2 && data_beats_q == 6'd16)) &&
        data_local_q[5:0] == 6'd0 && trig_local_q[5:0] == 6'd0 &&
        out_local_q[0] == 1'b0 &&
        range_fits(data_local_q, tensor_bytes) &&
        range_fits(trig_local_q, 65'd128) &&
        range_fits(out_local_q, tensor_bytes);

    // Each head uses split-half rotary pairs (i, i+32), i in [0,31].
    // Neither BF16 promotion nor the raw tail copy performs conversion.
    always_comb begin
        even_element = (int'(pair_index_q) / 32) * 256 +
                       (int'(pair_index_q) % 32);
        odd_element = even_element + 32;
        pair_even = {tensor_q[even_element / 32][(even_element % 32)*16 +: 16], 16'd0};
        pair_odd = {tensor_q[odd_element / 32][(odd_element % 32)*16 +: 16], 16'd0};
        pair_cos = {cos_q[pair_index_q[4:0]*16 +: 16], 16'd0};
        pair_sin = {sin_q[pair_index_q[4:0]*16 +: 16], 16'd0};
    end
    assign pair_in_valid = state_q == PAIR_REQ;
    assign pair_out_ready = state_q == PAIR_RSP;
    fp32_rope_pair_bf16_pipe_candidate pair (
        .clk_i, .rst_ni,
        .in_valid_i(pair_in_valid), .in_ready_o(pair_in_ready),
        .even_i(pair_even), .odd_i(pair_odd), .cos_i(pair_cos), .sin_i(pair_sin),
        .out_valid_o(pair_out_valid), .out_ready_i(pair_out_ready),
        .even_o(result_even), .odd_o(result_odd), .exception_flags_o(result_flags),
        .accepted_pairs_o(), .completed_pairs_o(),
        .product_fp32_o(), .product_bf16_o(), .sum_fp32_o(),
        .mul_flags_o(), .product_conversion_flags_o(),
        .add_flags_o(), .terminal_conversion_flags_o()
    );

    // Assemble one beat before exposing it to the bus. The registered packet
    // below, including its mask and address, is immutable while WRITE stalls.
    always_comb begin
        packed_data = '0;
        packed_be = '0;
        for (int lane = 0; lane < 32; lane++) begin
            source_word = int'(write_index_q)*32 + lane - int'(out_local_q[5:1]);
            if (source_word >= 0 && source_word < int'(data_beats_q)*32) begin
                packed_data[lane*16 +: 16] =
                    tensor_q[source_word / 32][(source_word % 32)*16 +: 16];
                packed_be[lane*2 +: 2] = 2'b11;
            end
        end
    end

    assign ready_o = state_q == IDLE;
    assign done_o = state_q == DONE;
    assign position_o = 32'd0;
    assign coefficient_steps_o = 32'd0;
    assign l2_rd_valid_o = state_q == DATA_REQ || state_q == TRIG_REQ;
    assign l2_rd_addr_o = state_q == DATA_REQ ?
        ADDR_W'(data_local_q[ADDR_W+5:6] + ADDR_W'(read_index_q)) :
        ADDR_W'(trig_local_q[ADDR_W+5:6] + ADDR_W'(trig_index_q));
    assign l2_rsp_ready_o = state_q == DATA_RSP || state_q == TRIG_RSP;
    assign l2_wr_valid_o = state_q == WRITE;
    assign l2_wr_addr_o = write_addr_q;
    assign l2_wr_data_o = write_data_q;
    assign l2_wr_be_o = write_be_q;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state_q <= IDLE;
            data_local_q <= '0; trig_local_q <= '0; out_local_q <= '0;
            position_local_q <= '0; position_lane_q <= '0;
            data_beats_q <= '0; heads_q <= '0; head_dim_q <= '0;
            rotary_dim_q <= '0; policy_q <= '0;
            read_index_q <= '0; write_index_q <= '0; write_count_q <= '0;
            trig_index_q <= '0; pair_index_q <= '0; pair_count_q <= '0;
            cos_q <= '0; sin_q <= '0;
            write_addr_q <= '0; write_data_q <= '0; write_be_q <= '0;
            unsupported_position_o <= 1'b0;
            read_beats_o <= '0; write_beats_o <= '0; pairs_o <= '0;
            exception_flags_o <= '0;
            // tensor_q has no valid contents until the complete read phase.
            // Resetting the control and write packet prevents stale stores.
        end else begin
            if (l2_rd_valid_o && l2_rd_ready_i)
                read_beats_o <= read_beats_o + 1'b1;
            if (l2_wr_valid_o && l2_wr_ready_i)
                write_beats_o <= write_beats_o + 1'b1;
            if (pair_out_valid && pair_out_ready) begin
                pairs_o <= pairs_o + 1'b1;
                exception_flags_o <= exception_flags_o | result_flags;
            end
            case (state_q)
                IDLE: if (start_i) begin
                    data_local_q <= data_local_i;
                    trig_local_q <= candidate_trig_local_i;
                    out_local_q <= out_local_i;
                    position_local_q <= position_local_i;
                    position_lane_q <= position_lane_i;
                    data_beats_q <= data_beats_i;
                    heads_q <= heads_i;
                    head_dim_q <= head_dim_i;
                    rotary_dim_q <= candidate_rotary_dim_i;
                    policy_q <= candidate_policy_i;
                    read_index_q <= '0; write_index_q <= '0;
                    trig_index_q <= '0; pair_index_q <= '0;
                    write_count_q <= '0; pair_count_q <= '0;
                    write_addr_q <= '0; write_data_q <= '0; write_be_q <= '0;
                    unsupported_position_o <= 1'b0;
                    read_beats_o <= '0; write_beats_o <= '0; pairs_o <= '0;
                    exception_flags_o <= '0;
                    state_q <= CHECK;
                end
                CHECK: begin
                    if (descriptor_supported) begin
                        pair_count_q <= heads_q == 10'd1 ? 7'd32 : 7'd64;
                        write_count_q <= data_beats_q[4:0] +
                                         {4'd0, out_local_q[5:0] != 6'd0};
                        state_q <= DATA_REQ;
                    end else begin
                        unsupported_position_o <= 1'b1;
                        state_q <= DONE;
                    end
                end
                DATA_REQ: if (l2_rd_valid_o && l2_rd_ready_i)
                    state_q <= DATA_RSP;
                DATA_RSP: if (l2_rsp_valid_i && l2_rsp_ready_o) begin
                    tensor_q[read_index_q[3:0]] <= l2_rsp_data_i;
                    if ({1'b0, read_index_q} + 6'd1 == data_beats_q) begin
                        trig_index_q <= 1'b0;
                        state_q <= TRIG_REQ;
                    end else begin
                        read_index_q <= read_index_q + 1'b1;
                        state_q <= DATA_REQ;
                    end
                end
                TRIG_REQ: if (l2_rd_valid_o && l2_rd_ready_i)
                    state_q <= TRIG_RSP;
                TRIG_RSP: if (l2_rsp_valid_i && l2_rsp_ready_o) begin
                    if (!trig_index_q) begin
                        cos_q <= l2_rsp_data_i;
                        trig_index_q <= 1'b1;
                        state_q <= TRIG_REQ;
                    end else begin
                        sin_q <= l2_rsp_data_i;
                        state_q <= PAIR_REQ;
                    end
                end
                PAIR_REQ: if (pair_in_valid && pair_in_ready)
                    state_q <= PAIR_RSP;
                PAIR_RSP: if (pair_out_valid && pair_out_ready) begin
                    // Actual 16-bit candidate outputs, with no second round.
                    tensor_q[even_element / 32][(even_element % 32)*16 +: 16] <= result_even;
                    tensor_q[odd_element / 32][(odd_element % 32)*16 +: 16] <= result_odd;
                    if ({1'b0, pair_index_q} + 7'd1 == pair_count_q) begin
                        write_index_q <= '0;
                        state_q <= PACK;
                    end else begin
                        pair_index_q <= pair_index_q + 1'b1;
                        state_q <= PAIR_REQ;
                    end
                end
                PACK: begin
                    write_addr_q <= ADDR_W'(out_local_q[ADDR_W+5:6] +
                                              ADDR_W'(write_index_q));
                    // Output is BF16-aligned, so byte enables always occur
                    // in pairs. Out-of-range lanes are masked and zeroed.
                    write_data_q <= packed_data;
                    write_be_q <= packed_be;
                    state_q <= WRITE;
                end
                WRITE: if (l2_wr_valid_o && l2_wr_ready_i) begin
                    if (write_index_q + 5'd1 == write_count_q) begin
                        state_q <= DONE;
                    end else begin
                        write_index_q <= write_index_q + 1'b1;
                        state_q <= PACK;
                    end
                end
                DONE: state_q <= IDLE;
                default: state_q <= IDLE;
            endcase
        end
    end
endmodule

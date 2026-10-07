// SPDX-License-Identifier: Apache-2.0
// Experimental one-head Q/K normalization producer. No tensor owner, memory,
// projection, or architecture-top integration is implied by this module.
//
// Policy 0xc1, exactly 256 lanes:
//   BF16 x/weight widen exactly to FP32.
//   square = RN32(x*x); balanced reduce16, then serial16 partial sums from +0.
//   mean_eps = RN32(RN32(sum * 1/256) + 0x358637bd).
//   inv = existing fp32_rsqrt_nr LUT plus one Newton iteration.
//   gamma = RN32(1 + weight), without an intervening BF16 conversion.
//   y = BF16_RNE(RN32(RN32(x*inv) * gamma)).
// All FP32 operations are separate RN32 nodes; there is no FMA or reassociation.
//
// Supported arithmetic inputs: either signed zero or BF16 normal encodings with
// exponent 95..158 inclusive (2^-32 <= abs(value) < 2^32). Both signs are valid.
// This deliberately bounded domain keeps square/reduction, rsqrt input, and
// nonzero output intermediates normal and finite in FP32. Nonfinite arithmetic
// operands, finite values outside this domain, and invalid descriptors reject.
// Q gates are opaque BF16 bits: never validated, converted, or used for flags.
// K ignores the high half of packed_i and always returns an all-zero gate.
//
// Every accepted request gives one terminal result unless reset flushes it.
// Status: 0 OK, 1 bad descriptor, 2 nonfinite operand, 3 unsupported finite
// operand range, 4 arithmetic/domain failure. Descriptor errors take priority,
// then nonfinite operands, then finite range errors. Errors zero norm and gate.
// Flags use {invalid, divide_by_zero, overflow, underflow, inexact}; preflight
// errors have zero flags. Runtime errors retain the observed arithmetic flags.
// tag, status, payload, flags and debug results are held throughout backpressure.
`timescale 1ns/1ps
module qk_norm256_bf16_candidate #(
    parameter integer TAG_WIDTH = 32
) (
    input  logic clk_i,
    input  logic rst_ni,
    input  logic in_valid_i,
    output logic in_ready_o,
    input  logic [8191:0] packed_i,
    input  logic [4095:0] weight_i,
    input  logic [1:0] role_i,          // 0: Q plus gate, 1: K only
    input  logic [15:0] head_dim_i,
    input  logic [7:0] policy_i,
    input  logic [31:0] epsilon_i,
    input  logic [TAG_WIDTH-1:0] tag_i,
    output logic out_valid_o,
    input  logic out_ready_i,
    output logic [4095:0] norm_o,
    output logic [4095:0] gate_o,
    output logic [3:0] status_o,
    output logic [TAG_WIDTH-1:0] tag_o,
    output logic [4:0] exception_flags_o,
    output logic [31:0] mean_eps_o,
    output logic [31:0] inv_o,
    output logic [31:0] accepted_o,
    output logic [31:0] completed_o
);
    localparam logic [1:0] ROLE_Q = 2'd0, ROLE_K = 2'd1;
    localparam logic [3:0] STATUS_OK = 4'd0, STATUS_DESCRIPTOR = 4'd1,
        STATUS_NONFINITE = 4'd2, STATUS_RANGE = 4'd3,
        STATUS_ARITHMETIC = 4'd4;
    typedef enum logic [1:0] {IDLE, ISSUE, WAIT_RESULT, OUT} state_e;
    state_e state_q;
    logic [8191:0] x_q, weight_q;
    logic [4095:0] gate_q;
    logic role_q;
    logic descriptor_bad, operand_nonfinite, operand_range_bad;
    logic core_ready, core_valid, core_domain_error;
    logic [8191:0] core_y;
    logic [4:0] core_flags;
    logic [31:0] core_mean_eps, core_inv;
    logic [4095:0] converted_y;
    logic [1279:0] conversion_flags;
    logic [4:0] conversion_flags_or;
    logic output_nonfinite, arithmetic_bad;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] core_accepted, core_completed;
    logic [31:0] core_reduction_cycles, core_rsqrt_cycles, core_output_cycles;
    /* verilator lint_on UNUSEDSIGNAL */

    function automatic logic supported_bf16(input logic [15:0] value);
        supported_bf16 = (value[14:0] == 15'b0) ||
                         ((value[14:7] >= 8'd95) &&
                          (value[14:7] <= 8'd158));
    endfunction

    always_comb begin
        descriptor_bad = ((role_i != ROLE_Q) && (role_i != ROLE_K)) ||
                         (head_dim_i != 16'd256) || (policy_i != 8'hc1) ||
                         (epsilon_i != 32'h358637bd);
        operand_nonfinite = 1'b0;
        operand_range_bad = 1'b0;
        for (int lane = 0; lane < 256; lane++) begin
            operand_nonfinite |= (packed_i[lane*16+7 +: 8] == 8'hff) ||
                                 (weight_i[lane*16+7 +: 8] == 8'hff);
            operand_range_bad |= !supported_bf16(packed_i[lane*16 +: 16]) ||
                                 !supported_bf16(weight_i[lane*16 +: 16]);
        end
    end

    fp32_rmsnorm256_chunked #(.QK_CANDIDATE(1'b1)) norm_core (
        .clk_i(clk_i), .rst_ni(rst_ni),
        .in_valid_i(state_q == ISSUE), .in_ready_o(core_ready),
        .x_i(x_q), .weight_i(weight_q), .epsilon_i(32'h358637bd),
        .out_valid_o(core_valid), .out_ready_i(state_q == WAIT_RESULT),
        .y_o(core_y), .exception_flags_o(core_flags),
        .accepted_o(core_accepted), .completed_o(core_completed),
        .reduction_cycles_o(core_reduction_cycles),
        .rsqrt_cycles_o(core_rsqrt_cycles), .output_cycles_o(core_output_cycles),
        .domain_error_o(core_domain_error),
        .mean_eps_o(core_mean_eps), .inv_o(core_inv)
    );
    for (genvar lane = 0; lane < 256; lane++) begin : g_output_conversion
        fp32_to_bf16_rne_candidate convert (
            .fp32_i(core_y[lane*32 +: 32]),
            .bf16_o(converted_y[lane*16 +: 16]),
            .exception_flags_o(conversion_flags[lane*5 +: 5])
        );
    end
    always_comb begin
        conversion_flags_or = 5'b0;
        output_nonfinite = 1'b0;
        for (int lane = 0; lane < 256; lane++) begin
            conversion_flags_or |= conversion_flags[lane*5 +: 5];
            output_nonfinite |= (core_y[lane*32+23 +: 8] == 8'hff) ||
                                (converted_y[lane*16+7 +: 8] == 8'hff);
        end
        // NX is expected and is reported, rather than treated as an error.
        arithmetic_bad = core_domain_error || output_nonfinite ||
                         (|core_flags[4:1]) || (|conversion_flags_or[4:1]) ||
                         core_mean_eps[31] ||
                         (core_mean_eps[30:23] < 8'd2) ||
                         (core_mean_eps[30:23] > 8'd253) ||
                         core_inv[31] || (core_inv[30:23] == 8'd0) ||
                         (core_inv[30:23] == 8'hff);
    end

    assign in_ready_o = rst_ni && (state_q == IDLE);
    assign out_valid_o = rst_ni && (state_q == OUT);

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state_q <= IDLE;
            x_q <= '0;
            weight_q <= '0;
            gate_q <= '0;
            role_q <= 1'b0;
            norm_o <= '0;
            gate_o <= '0;
            status_o <= STATUS_OK;
            tag_o <= '0;
            exception_flags_o <= '0;
            mean_eps_o <= '0;
            inv_o <= '0;
            accepted_o <= '0;
            completed_o <= '0;
        end else begin
            case (state_q)
                IDLE: if (in_valid_i && in_ready_o) begin
                    tag_o <= tag_i;
                    role_q <= role_i == ROLE_Q;
                    gate_q <= packed_i[8191:4096];
                    for (int lane = 0; lane < 256; lane++) begin
                        x_q[lane*32 +: 32] <= {packed_i[lane*16 +: 16],16'b0};
                        weight_q[lane*32 +: 32] <= {weight_i[lane*16 +: 16],16'b0};
                    end
                    norm_o <= '0;
                    gate_o <= '0;
                    status_o <= STATUS_OK;
                    exception_flags_o <= '0;
                    mean_eps_o <= '0;
                    inv_o <= '0;
                    accepted_o <= accepted_o + 1'b1;
                    if (descriptor_bad) begin
                        status_o <= STATUS_DESCRIPTOR;
                        state_q <= OUT;
                    end else if (operand_nonfinite) begin
                        status_o <= STATUS_NONFINITE;
                        state_q <= OUT;
                    end else if (operand_range_bad) begin
                        status_o <= STATUS_RANGE;
                        state_q <= OUT;
                    end else begin
                        state_q <= ISSUE;
                    end
                end
                ISSUE: if (core_ready) state_q <= WAIT_RESULT;
                WAIT_RESULT: if (core_valid) begin
                    exception_flags_o <= core_flags | conversion_flags_or;
                    mean_eps_o <= core_mean_eps;
                    inv_o <= core_inv;
                    if (arithmetic_bad) begin
                        status_o <= STATUS_ARITHMETIC;
                        norm_o <= '0;
                        gate_o <= '0;
                    end else begin
                        status_o <= STATUS_OK;
                        norm_o <= converted_y;
                        gate_o <= role_q ? gate_q : 4096'b0;
                    end
                    state_q <= OUT;
                end
                OUT: if (out_ready_i) begin
                    completed_o <= completed_o + 1'b1;
                    state_q <= IDLE;
                end
                default: state_q <= IDLE;
            endcase
        end
    end
endmodule

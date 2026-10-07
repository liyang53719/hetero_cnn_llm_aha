// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Experimental all-products-BF16 RoPE pair. The existing two-slot elastic
// control is retained; conversion does not introduce an extra register stage.
// Lane order, least significant first: products ec, os, es, oc; sums even, odd.
// Trace ports are observational and travel with the output handshake.
module fp32_rope_pair_bf16_candidate (
    input logic clk_i, rst_ni,
    input logic in_valid_i,
    output logic in_ready_o,
    input logic [31:0] even_i, odd_i, cos_i, sin_i,
    output logic out_valid_o,
    input logic out_ready_i,
    output logic [15:0] even_o, odd_o,
    output logic [4:0] exception_flags_o,
    output logic [31:0] accepted_pairs_o, completed_pairs_o,
    output logic [127:0] product_fp32_o,
    output logic [63:0] product_bf16_o,
    output logic [63:0] sum_fp32_o,
    output logic [19:0] mul_flags_o,
    output logic [19:0] product_conversion_flags_o,
    output logic [9:0] add_flags_o,
    output logic [9:0] terminal_conversion_flags_o
);
    logic input_valid_q, output_valid_q, output_ready;
    logic [31:0] e_q, o_q, c_q, s_q;
    logic [127:0] product_fp32;
    logic [63:0] product_bf16, sum_fp32;
    logic [31:0] terminal_bf16;
    logic [19:0] mul_flags, product_conversion_flags;
    logic [9:0] add_flags, terminal_conversion_flags;
    logic [4:0] flags_comb;

    HeteroFP32Alu m0 (.io_op(1'b1), .io_x(e_q), .io_y(c_q),
        .io_out(product_fp32[31:0]), .io_exceptionFlags(mul_flags[4:0]));
    HeteroFP32Alu m1 (.io_op(1'b1), .io_x(o_q), .io_y(s_q),
        .io_out(product_fp32[63:32]), .io_exceptionFlags(mul_flags[9:5]));
    HeteroFP32Alu m2 (.io_op(1'b1), .io_x(e_q), .io_y(s_q),
        .io_out(product_fp32[95:64]), .io_exceptionFlags(mul_flags[14:10]));
    HeteroFP32Alu m3 (.io_op(1'b1), .io_x(o_q), .io_y(c_q),
        .io_out(product_fp32[127:96]), .io_exceptionFlags(mul_flags[19:15]));
    for (genvar lane = 0; lane < 4; lane++) begin : g_product_conversion
        fp32_to_bf16_rne_candidate convert (
            .fp32_i(product_fp32[lane*32 +: 32]),
            .bf16_o(product_bf16[lane*16 +: 16]),
            .exception_flags_o(product_conversion_flags[lane*5 +: 5]));
    end
    HeteroFP32Alu a0 (.io_op(1'b0),
        .io_x({product_bf16[15:0], 16'b0}),
        .io_y({~product_bf16[31], product_bf16[30:16], 16'b0}),
        .io_out(sum_fp32[31:0]), .io_exceptionFlags(add_flags[4:0]));
    HeteroFP32Alu a1 (.io_op(1'b0),
        .io_x({product_bf16[47:32], 16'b0}),
        .io_y({product_bf16[63:48], 16'b0}),
        .io_out(sum_fp32[63:32]), .io_exceptionFlags(add_flags[9:5]));
    for (genvar lane = 0; lane < 2; lane++) begin : g_terminal_conversion
        fp32_to_bf16_rne_candidate convert (
            .fp32_i(sum_fp32[lane*32 +: 32]),
            .bf16_o(terminal_bf16[lane*16 +: 16]),
            .exception_flags_o(terminal_conversion_flags[lane*5 +: 5]));
    end
    always_comb begin
        flags_comb = 5'b0;
        for (int lane = 0; lane < 4; lane++)
            flags_comb |= mul_flags[lane*5 +: 5] |
                          product_conversion_flags[lane*5 +: 5];
        for (int lane = 0; lane < 2; lane++)
            flags_comb |= add_flags[lane*5 +: 5] |
                          terminal_conversion_flags[lane*5 +: 5];
    end
    assign output_ready = !output_valid_q || out_ready_i;
    assign in_ready_o = !input_valid_q || output_ready;
    assign out_valid_o = output_valid_q;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            input_valid_q <= 1'b0;
            output_valid_q <= 1'b0;
            e_q <= '0; o_q <= '0; c_q <= '0; s_q <= '0;
            even_o <= '0; odd_o <= '0; exception_flags_o <= '0;
            product_fp32_o <= '0; product_bf16_o <= '0; sum_fp32_o <= '0;
            mul_flags_o <= '0; product_conversion_flags_o <= '0;
            add_flags_o <= '0; terminal_conversion_flags_o <= '0;
            accepted_pairs_o <= '0; completed_pairs_o <= '0;
        end else begin
            if (output_valid_q && out_ready_i)
                completed_pairs_o <= completed_pairs_o + 1'b1;
            if (output_ready) begin
                output_valid_q <= input_valid_q;
                if (input_valid_q) begin
                    even_o <= terminal_bf16[15:0];
                    odd_o <= terminal_bf16[31:16];
                    exception_flags_o <= flags_comb;
                    product_fp32_o <= product_fp32;
                    product_bf16_o <= product_bf16;
                    sum_fp32_o <= sum_fp32;
                    mul_flags_o <= mul_flags;
                    product_conversion_flags_o <= product_conversion_flags;
                    add_flags_o <= add_flags;
                    terminal_conversion_flags_o <= terminal_conversion_flags;
                end
            end
            if (in_ready_o) begin
                input_valid_q <= in_valid_i;
                if (in_valid_i) begin
                    e_q <= even_i; o_q <= odd_i; c_q <= cos_i; s_q <= sin_i;
                    accepted_pairs_o <= accepted_pairs_o + 1'b1;
                end
            end
        end
    end
endmodule

// SPDX-License-Identifier: Apache-2.0
// Experimental all-products-BF16 RoPE pair with the existing six-state control.
// The actual registered HardFloat mul/add primitives are retained unchanged.
// Product conversion is captured at MWAIT and terminal conversion at AWAIT;
// no additional stage is introduced. Trace lanes are ec, os, es, oc / even, odd.
module fp32_rope_pair_bf16_pipe_candidate (
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
    localparam logic [2:0] IDLE=0, MISSUE=1, MWAIT=2, AISSUE=3, AWAIT=4, OUT=5;
    logic [2:0] st;
    logic [31:0] eq, oq, cq, sq;
    logic [3:0] mir, mov;
    logic [127:0] mo;
    logic [19:0] mf, product_conversion_flags;
    logic [63:0] product_bf16;
    logic [47:0] mu;
    logic mallin, mallout, mconsume;
    logic [1:0] air, aov;
    logic [63:0] ao;
    logic [9:0] af, terminal_conversion_flags;
    logic [31:0] terminal_bf16;
    logic [23:0] au;
    logic aallin, aallout, aconsume;
    logic [4:0] product_flags, sum_flags;

    assign mallin = &mir;
    assign mallout = &mov;
    assign aallin = &air;
    assign aallout = &aov;
    assign mconsume = st == MWAIT && mallout;
    assign aconsume = st == AWAIT && aallout;

    HeteroFP32MulPipeTag12 m0 (.clock(clk_i), .reset(!rst_ni),
        .io_inValid(st==MISSUE && mallin), .io_inReady(mir[0]),
        .io_x(eq), .io_y(cq), .io_userIn(12'd0),
        .io_outValid(mov[0]), .io_outReady(mconsume), .io_out(mo[31:0]),
        .io_exceptionFlags(mf[4:0]), .io_userOut(mu[11:0]));
    HeteroFP32MulPipeTag12 m1 (.clock(clk_i), .reset(!rst_ni),
        .io_inValid(st==MISSUE && mallin), .io_inReady(mir[1]),
        .io_x(oq), .io_y(sq), .io_userIn(12'd1),
        .io_outValid(mov[1]), .io_outReady(mconsume), .io_out(mo[63:32]),
        .io_exceptionFlags(mf[9:5]), .io_userOut(mu[23:12]));
    HeteroFP32MulPipeTag12 m2 (.clock(clk_i), .reset(!rst_ni),
        .io_inValid(st==MISSUE && mallin), .io_inReady(mir[2]),
        .io_x(eq), .io_y(sq), .io_userIn(12'd2),
        .io_outValid(mov[2]), .io_outReady(mconsume), .io_out(mo[95:64]),
        .io_exceptionFlags(mf[14:10]), .io_userOut(mu[35:24]));
    HeteroFP32MulPipeTag12 m3 (.clock(clk_i), .reset(!rst_ni),
        .io_inValid(st==MISSUE && mallin), .io_inReady(mir[3]),
        .io_x(oq), .io_y(cq), .io_userIn(12'd3),
        .io_outValid(mov[3]), .io_outReady(mconsume), .io_out(mo[127:96]),
        .io_exceptionFlags(mf[19:15]), .io_userOut(mu[47:36]));
    for (genvar lane = 0; lane < 4; lane++) begin : g_product_conversion
        fp32_to_bf16_rne_candidate convert (
            .fp32_i(mo[lane*32 +: 32]), .bf16_o(product_bf16[lane*16 +: 16]),
            .exception_flags_o(product_conversion_flags[lane*5 +: 5]));
    end
    HeteroFP32AddPipeTag12 a0 (.clock(clk_i), .reset(!rst_ni),
        .io_inValid(st==AISSUE && aallin), .io_inReady(air[0]),
        .io_x({product_bf16_o[15:0], 16'b0}),
        .io_y({~product_bf16_o[31], product_bf16_o[30:16], 16'b0}),
        .io_userIn(12'd0), .io_outValid(aov[0]), .io_outReady(aconsume),
        .io_out(ao[31:0]), .io_exceptionFlags(af[4:0]), .io_userOut(au[11:0]));
    HeteroFP32AddPipeTag12 a1 (.clock(clk_i), .reset(!rst_ni),
        .io_inValid(st==AISSUE && aallin), .io_inReady(air[1]),
        .io_x({product_bf16_o[47:32], 16'b0}),
        .io_y({product_bf16_o[63:48], 16'b0}),
        .io_userIn(12'd1), .io_outValid(aov[1]), .io_outReady(aconsume),
        .io_out(ao[63:32]), .io_exceptionFlags(af[9:5]), .io_userOut(au[23:12]));
    for (genvar lane = 0; lane < 2; lane++) begin : g_terminal_conversion
        fp32_to_bf16_rne_candidate convert (
            .fp32_i(ao[lane*32 +: 32]), .bf16_o(terminal_bf16[lane*16 +: 16]),
            .exception_flags_o(terminal_conversion_flags[lane*5 +: 5]));
    end
    always_comb begin
        product_flags = 5'b0;
        sum_flags = 5'b0;
        for (int lane = 0; lane < 4; lane++)
            product_flags |= mf[lane*5 +: 5] |
                             product_conversion_flags[lane*5 +: 5];
        for (int lane = 0; lane < 2; lane++)
            sum_flags |= af[lane*5 +: 5] |
                         terminal_conversion_flags[lane*5 +: 5];
    end
    assign in_ready_o = st == IDLE;
    assign out_valid_o = st == OUT;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            st <= IDLE;
            eq <= '0; oq <= '0; cq <= '0; sq <= '0;
            even_o <= '0; odd_o <= '0; exception_flags_o <= '0;
            product_fp32_o <= '0; product_bf16_o <= '0; sum_fp32_o <= '0;
            mul_flags_o <= '0; product_conversion_flags_o <= '0;
            add_flags_o <= '0; terminal_conversion_flags_o <= '0;
            accepted_pairs_o <= '0; completed_pairs_o <= '0;
        end else begin
            case (st)
                IDLE: if (in_valid_i) begin
                    eq <= even_i; oq <= odd_i; cq <= cos_i; sq <= sin_i;
                    exception_flags_o <= '0;
                    accepted_pairs_o <= accepted_pairs_o + 1'b1;
                    st <= MISSUE;
                end
                MISSUE: if (mallin) st <= MWAIT;
                MWAIT: if (mallout) begin
                    product_fp32_o <= mo;
                    product_bf16_o <= product_bf16;
                    mul_flags_o <= mf;
                    product_conversion_flags_o <= product_conversion_flags;
                    exception_flags_o <= product_flags;
                    st <= AISSUE;
                end
                AISSUE: if (aallin) st <= AWAIT;
                AWAIT: if (aallout) begin
                    sum_fp32_o <= ao;
                    add_flags_o <= af;
                    even_o <= terminal_bf16[15:0];
                    odd_o <= terminal_bf16[31:16];
                    terminal_conversion_flags_o <= terminal_conversion_flags;
                    exception_flags_o <= exception_flags_o | sum_flags;
                    st <= OUT;
                end
                OUT: if (out_ready_i) begin
                    completed_pairs_o <= completed_pairs_o + 1'b1;
                    st <= IDLE;
                end
                default: st <= IDLE;
            endcase
        end
    end
endmodule

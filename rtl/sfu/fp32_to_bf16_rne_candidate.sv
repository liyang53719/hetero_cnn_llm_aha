// SPDX-License-Identifier: Apache-2.0
// Experimental, all-encoding binary32 -> BF16 conversion. Not production wiring.
// Flags are {invalid, divide_by_zero, overflow, underflow, inexact}.
// Underflow uses destination-encoding tininess AFTER rounding: UF iff NX and
// the rounded BF16 exponent is zero. This is intentionally not HardFloat's
// tininess predicate at the subnormal/normal crossover.
module fp32_to_bf16_rne_candidate (
    input  logic [31:0] fp32_i,
    output logic [15:0] bf16_o,
    output logic [4:0]  exception_flags_o
);
    logic discarded, increment;
    logic [15:0] rounded;

    always_comb begin
        discarded = |fp32_i[15:0];
        increment = fp32_i[15] && ((|fp32_i[14:0]) || fp32_i[16]);
        rounded = fp32_i[31:16] + {15'b0, increment};
        bf16_o = rounded;
        exception_flags_o = 5'b00000;
        if (fp32_i[30:23] == 8'hff) begin
            if (|fp32_i[22:0]) begin
                // Canonical positive quiet NaN. Only signaling NaNs raise NV.
                bf16_o = 16'h7fc0;
                exception_flags_o[4] = !fp32_i[22];
            end else begin
                bf16_o = {fp32_i[31], 8'hff, 7'b0};
            end
        end else begin
            exception_flags_o[0] = discarded;
            // Finite input rounded to infinity always implies OF and NX.
            if (rounded[14:7] == 8'hff)
                exception_flags_o = 5'b00101;
            else if (discarded && rounded[14:7] == 8'h00)
                exception_flags_o[1] = 1'b1;
        end
    end
endmodule

// Copyright 2024 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51

// Local four-state combinational/stepped-state differential fixture.
// SOURCE ONLY: native elaboration and simulation have NOT_EXECUTED.
// The source bodies between PINNED markers are byte-for-byte extracted regions.
// Test-only shells expose state; common_cells register/assertion macros are not modeled.
`timescale 1ns/1ps

module fifo_original_comb #(
    parameter integer Depth = 2,
    parameter bit SameCycleRW = 1'b1
) (
    input logic flush_i, valid_i, ready_i,
    input logic [7:0] data_i,
    input logic [$clog2(Depth):0] read_ptr_q, write_ptr_q,
    input logic [Depth-1:0][7:0] data_q,
    output logic valid_o, ready_o, load_data,
    output logic [7:0] data_o,
    output logic [$clog2(Depth):0] read_ptr_d, write_ptr_d,
    output logic [Depth-1:0][7:0] data_d
);
    localparam integer PointerWidth = $clog2(Depth) + 1;
    assign data_o = data_q[read_ptr_q[PointerWidth-2:0]];
// BEGIN PINNED ORIGINAL COMBINATIONAL REGION
    // Logic
    always_comb begin
        // Default
        load_data   = 1'b0;
        read_ptr_d  = read_ptr_q;
        write_ptr_d = write_ptr_q;
        data_d      = data_q;

        if (flush_i) begin // Flush
            read_ptr_d  = '0;
            write_ptr_d = '0;
            valid_o     = 1'b0;
            ready_o     = 1'b0;
        end else begin
            // Read
            valid_o = read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]
                ? read_ptr_q[PointerWidth-2:0] != write_ptr_q[PointerWidth-2:0] : 1'b1;
            if (ready_i && valid_o) begin
                if (read_ptr_q[PointerWidth-2:0] == (Depth-1)) begin
                    // On overflow reset pointer to zero and flip imaginary bit
                    read_ptr_d[PointerWidth-2:0] = '0;
                    read_ptr_d[PointerWidth-1]   = !read_ptr_q[PointerWidth-1];
                end else begin
                    // Increment counter
                    read_ptr_d = read_ptr_q + 'd1;
                end
            end

            // Write -> Also able to write if we read in the same cycle
            ready_o     = (read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]
                ? 1'b1 : write_ptr_q[PointerWidth-2:0] != read_ptr_q[PointerWidth-2:0])
                || (SameCycleRW && ready_i && valid_o);

            if (valid_i && ready_o) begin
                load_data = 1'b1;
                data_d[write_ptr_q[PointerWidth-2:0]] = data_i;

                if (write_ptr_q[PointerWidth-2:0] == (Depth-1)) begin
                    // On overflow reset pointer to zero and flip imaginary bit
                    write_ptr_d[PointerWidth-2:0] = '0;
                    write_ptr_d[PointerWidth-1]   = !write_ptr_q[PointerWidth-1];
                end else begin
                    // Increment pointer
                    write_ptr_d = write_ptr_q + 'd1;
                end
            end
        end
    end

// END PINNED ORIGINAL COMBINATIONAL REGION
endmodule

module fifo_derived_comb #(
    parameter integer Depth = 2,
    parameter bit SameCycleRW = 1'b1
) (
    input logic flush_i, valid_i, ready_i,
    input logic [7:0] data_i,
    input logic [$clog2(Depth):0] read_ptr_q, write_ptr_q,
    input logic [Depth-1:0][7:0] data_q,
    output logic valid_o, ready_o, load_data,
    output logic [7:0] data_o,
    output logic [$clog2(Depth):0] read_ptr_d, write_ptr_d,
    output logic [Depth-1:0][7:0] data_d
);
    localparam integer PointerWidth = $clog2(Depth) + 1;
    assign data_o = data_q[read_ptr_q[PointerWidth-2:0]];
// BEGIN PINNED DERIVED COMBINATIONAL REGION
    // Output validity
    always_comb begin
        if (flush_i) begin // Flush
            valid_o     = 1'b0;
        end else begin
            valid_o = read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]
                ? read_ptr_q[PointerWidth-2:0] != write_ptr_q[PointerWidth-2:0] : 1'b1;
        end
    end

    // Logic
    always_comb begin
        // Default
        load_data   = 1'b0;
        read_ptr_d  = read_ptr_q;
        write_ptr_d = write_ptr_q;
        data_d      = data_q;

        if (flush_i) begin // Flush
            read_ptr_d  = '0;
            write_ptr_d = '0;
            ready_o     = 1'b0;
        end else begin
            // Read
            if (ready_i && valid_o) begin
                if (read_ptr_q[PointerWidth-2:0] == (Depth-1)) begin
                    // On overflow reset pointer to zero and flip imaginary bit
                    read_ptr_d[PointerWidth-2:0] = '0;
                    read_ptr_d[PointerWidth-1]   = !read_ptr_q[PointerWidth-1];
                end else begin
                    // Increment counter
                    read_ptr_d = read_ptr_q + 'd1;
                end
            end

            // Write -> Also able to write if we read in the same cycle
            ready_o     = (read_ptr_q[PointerWidth-1] == write_ptr_q[PointerWidth-1]
                ? 1'b1 : write_ptr_q[PointerWidth-2:0] != read_ptr_q[PointerWidth-2:0])
                || (SameCycleRW && ready_i && valid_o);

            if (valid_i && ready_o) begin
                load_data = 1'b1;
                data_d[write_ptr_q[PointerWidth-2:0]] = data_i;

                if (write_ptr_q[PointerWidth-2:0] == (Depth-1)) begin
                    // On overflow reset pointer to zero and flip imaginary bit
                    write_ptr_d[PointerWidth-2:0] = '0;
                    write_ptr_d[PointerWidth-1]   = !write_ptr_q[PointerWidth-1];
                end else begin
                    // Increment pointer
                    write_ptr_d = write_ptr_q + 'd1;
                end
            end
        end
    end

// END PINNED DERIVED COMBINATIONAL REGION
endmodule


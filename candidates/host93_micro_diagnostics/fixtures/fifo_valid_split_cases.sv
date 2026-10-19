// SOURCE ONLY: this fixture has not been elaborated or simulated.
// Compile with fifo_valid_split_miter.sv in a true four-state SV simulator.
`timescale 1ns/1ps

module fifo_valid_split_case #(
    parameter integer Depth = 2,
    parameter bit SameCycleRW = 1'b1
) (output logic done);
    localparam integer PointerWidth = $clog2(Depth) + 1;
    logic flush_i, valid_i, ready_i;
    logic [7:0] data_i;
    logic [PointerWidth-1:0] read_ptr_q, write_ptr_q;
    logic [Depth-1:0][7:0] data_q;
    logic valid_ref, ready_ref, load_ref, valid_new, ready_new, load_new;
    logic [7:0] data_ref, data_new;
    logic [PointerWidth-1:0] read_ref, write_ref, read_new, write_new;
    logic [Depth-1:0][7:0] mem_ref, mem_new;
    integer checks;
    logic expected_valid, expected_ready;
    logic [7:0] expected_data;

    fifo_original_comb #(.Depth(Depth), .SameCycleRW(SameCycleRW)) original (
        .flush_i(flush_i), .valid_i(valid_i), .ready_i(ready_i), .data_i(data_i),
        .read_ptr_q(read_ptr_q), .write_ptr_q(write_ptr_q), .data_q(data_q),
        .valid_o(valid_ref), .ready_o(ready_ref), .load_data(load_ref),
        .data_o(data_ref), .read_ptr_d(read_ref), .write_ptr_d(write_ref), .data_d(mem_ref)
    );
    fifo_derived_comb #(.Depth(Depth), .SameCycleRW(SameCycleRW)) candidate (
        .flush_i(flush_i), .valid_i(valid_i), .ready_i(ready_i), .data_i(data_i),
        .read_ptr_q(read_ptr_q), .write_ptr_q(write_ptr_q), .data_q(data_q),
        .valid_o(valid_new), .ready_o(ready_new), .load_data(load_new),
        .data_o(data_new), .read_ptr_d(read_new), .write_ptr_d(write_new), .data_d(mem_new)
    );

    function automatic logic symbol4(input integer code);
        case (code)
            0: symbol4 = 1'b0;
            1: symbol4 = 1'b1;
            2: symbol4 = 1'bx;
            default: symbol4 = 1'bz;
        endcase
    endfunction

    task automatic compare_settled(input string label);
        #1;
        checks = checks + 1;
        if ({valid_ref, ready_ref, load_ref, data_ref, read_ref, write_ref, mem_ref}
            !== {valid_new, ready_new, load_new, data_new, read_new, write_new, mem_new})
            $fatal(1, "MISMATCH Depth=%0d SameCycleRW=%0b check=%0d %s flush=%b vi=%b ri=%b r=%b w=%b",
                Depth, SameCycleRW, checks, label, flush_i, valid_i, ready_i,
                read_ptr_q, write_ptr_q);
    endtask

    // A clockless state step after comparing every next-state signal. This is not
    // a model or test of the source file's FFARNC/FFLARNC macros, reset, or clr_i.
    task automatic commit_compared_state;
        logic [PointerWidth-1:0] next_read, next_write;
        logic [Depth-1:0][7:0] next_mem;
        next_read = read_ref;
        next_write = write_ref;
        next_mem = mem_ref;
        read_ptr_q = next_read;
        write_ptr_q = next_write;
        data_q = next_mem;
        #1;
    endtask

    task automatic require_stalled;
        if (valid_ref !== 1'b1 || ready_ref !== 1'b0 || load_ref !== 1'b0
            || read_ref !== read_ptr_q || write_ref !== write_ptr_q || mem_ref !== data_q)
            $fatal(1, "STALL contract Depth=%0d SameCycleRW=%0b", Depth, SameCycleRW);
    endtask

    initial begin
        done = 1'b0;
        checks = 0;
        flush_i = 1'b0;
        valid_i = 1'b0;
        ready_i = 1'b0;
        data_i = '0;
        read_ptr_q = '0;
        write_ptr_q = '0;
        data_q = '0;

        // 10 pointer states x 4 flush x 4 ready x 4 valid x 2 data patterns.
        // Occupancy states are directed; this is not exhaustive pointer-space proof.
        for (integer pc = 0; pc < 10; pc = pc + 1) begin
            read_ptr_q = '0;
            write_ptr_q = '0;
            case (pc)
                0: begin end // empty at zero
                1: write_ptr_q = 1; // one entry
                2: write_ptr_q[PointerWidth-1] = 1'b1; // full
                3: begin read_ptr_q = 1; write_ptr_q = 1; end // empty elsewhere
                4: begin // one entry crossing the low-pointer wrap
                    read_ptr_q[PointerWidth-2:0] = Depth - 1;
                    write_ptr_q[PointerWidth-1] = 1'b1;
                end
                5: read_ptr_q[PointerWidth-1] = 1'bx;
                6: write_ptr_q[0] = 1'bx;
                7: read_ptr_q[0] = 1'bz;
                8: begin // uncertain wrap bit, definitely distinct low pointers
                    read_ptr_q[PointerWidth-1] = 1'bx;
                    write_ptr_q[0] = 1'b1;
                end
                9: write_ptr_q[PointerWidth-1] = 1'bz;
            endcase
            for (integer f = 0; f < 4; f = f + 1)
            for (integer r = 0; r < 4; r = r + 1)
            for (integer v = 0; v < 4; v = v + 1)
            for (integer d = 0; d < 2; d = d + 1) begin
                flush_i = symbol4(f);
                ready_i = symbol4(r);
                valid_i = symbol4(v);
                data_i = d == 0 ? 8'ha5 : 8'hx3;
                for (integer i = 0; i < Depth; i = i + 1) data_q[i] = 8'h40 + i;
                if (d != 0) data_q[0] = 8'hz7;
                compare_settled($sformatf("matrix pc=%0d f=%0d r=%0d v=%0d d=%0d", pc, f, r, v, d));
                case (pc)
                    0, 3: expected_valid = 1'b0;
                    1, 2, 4, 8: expected_valid = 1'b1;
                    default: expected_valid = 1'bx;
                endcase
                // Procedural flush X/Z must take the else branch, not mask valid.
                if (f == 1) expected_valid = 1'b0;
                if (valid_ref !== expected_valid)
                    $fatal(1, "VALID oracle Depth=%0d SameCycleRW=%0b pc=%0d f=%0d got=%b expected=%b",
                        Depth, SameCycleRW, pc, f, valid_ref, expected_valid);
                if (f == 1) begin
                    if (ready_ref !== 1'b0 || load_ref !== 1'b0 || read_ref !== '0
                        || write_ref !== '0 || mem_ref !== data_q)
                        $fatal(1, "FLUSH oracle Depth=%0d SameCycleRW=%0b", Depth, SameCycleRW);
                end else if (pc == 2) begin
                    if (!SameCycleRW || r == 0) expected_ready = 1'b0;
                    else if (r == 1) expected_ready = 1'b1;
                    else expected_ready = 1'bx;
                    if (ready_ref !== expected_ready)
                        $fatal(1, "FULL readiness oracle Depth=%0d SameCycleRW=%0b r=%0d", Depth, SameCycleRW, r);
                end else if ((pc == 0 || pc == 3) && ready_ref !== 1'b1)
                    $fatal(1, "EMPTY readiness oracle Depth=%0d SameCycleRW=%0b", Depth, SameCycleRW);
            end
        end
        if (checks != 1280) $fatal(1, "Matrix count=%0d expected=1280", checks);

        // Directed stepped-state trace: fill, full stall, pop+push, refill under
        // backpressure, drain in order, empty simultaneous request, and flush.
        read_ptr_q = '0; write_ptr_q = '0; data_q = '0;
        flush_i = 1'b0; valid_i = 1'b0; ready_i = 1'b0; data_i = '0;
        compare_settled("initial empty");
        if (valid_ref !== 1'b0 || ready_ref !== 1'b1) $fatal(1, "Initial empty");
        for (integer i = 0; i < Depth; i = i + 1) begin
            valid_i = 1'b1; ready_i = 1'b0; data_i = 8'h10 + i;
            compare_settled("fill");
            if (ready_ref !== 1'b1 || load_ref !== 1'b1 || read_ref !== read_ptr_q)
                $fatal(1, "Fill acceptance");
            commit_compared_state();
        end
        valid_i = 1'b1; ready_i = 1'b0; data_i = 8'hff;
        compare_settled("full stall"); require_stalled(); commit_compared_state();

        ready_i = 1'b1; data_i = 8'he1;
        compare_settled("full simultaneous pop/push");
        if (valid_ref !== 1'b1 || data_ref !== 8'h10 || ready_ref !== SameCycleRW
            || load_ref !== SameCycleRW || read_ref === read_ptr_q)
            $fatal(1, "Full simultaneous branch");
        if (!SameCycleRW && write_ref !== write_ptr_q) $fatal(1, "No same-cycle write");
        commit_compared_state();

        ready_i = 1'b0; data_i = 8'he2;
        compare_settled("refill while downstream stalled");
        if (valid_ref !== 1'b1 || data_ref !== 8'h11 || ready_ref !== !SameCycleRW
            || load_ref !== !SameCycleRW || read_ref !== read_ptr_q)
            $fatal(1, "Backpressure refill branch");
        commit_compared_state();
        for (integer i = 0; i < 2; i = i + 1) begin
            data_i = 8'hfe - i;
            compare_settled("full backpressure stability"); require_stalled();
            if (data_ref !== 8'h11) $fatal(1, "Stalled head changed");
            commit_compared_state();
        end
        valid_i = 1'b0; ready_i = 1'b1;
        for (integer i = 0; i < Depth; i = i + 1) begin
            expected_data = i < Depth - 1 ? 8'h11 + i : (SameCycleRW ? 8'he1 : 8'he2);
            compare_settled("drain order");
            if (valid_ref !== 1'b1 || data_ref !== expected_data || load_ref !== 1'b0)
                $fatal(1, "Drain order Depth=%0d SameCycleRW=%0b index=%0d", Depth, SameCycleRW, i);
            commit_compared_state();
        end
        valid_i = 1'b1; ready_i = 1'b1; data_i = 8'h5a;
        compare_settled("empty simultaneous request");
        if (valid_ref !== 1'b0 || ready_ref !== 1'b1 || load_ref !== 1'b1 || read_ref !== read_ptr_q)
            $fatal(1, "Empty request must push only");
        commit_compared_state();
        valid_i = 1'b0; ready_i = 1'b0;
        compare_settled("new head held");
        if (valid_ref !== 1'b1 || data_ref !== 8'h5a) $fatal(1, "New head data");
        flush_i = 1'b1; valid_i = 1'b1; ready_i = 1'b1;
        compare_settled("flush dominates traffic");
        if (valid_ref !== 1'b0 || ready_ref !== 1'b0 || load_ref !== 1'b0
            || read_ref !== '0 || write_ref !== '0 || mem_ref !== data_q)
            $fatal(1, "Flush dominance");
        commit_compared_state();
        flush_i = 1'b0; valid_i = 1'b0; ready_i = 1'b0;
        compare_settled("post flush empty");
        if (valid_ref !== 1'b0 || ready_ref !== 1'b1) $fatal(1, "Post flush empty");
        $display("CASE_PASS Depth=%0d SameCycleRW=%0b checks=%0d", Depth, SameCycleRW, checks);
        done = 1'b1;
    end
endmodule

module fifo_valid_split_tb;
    wire [3:0] done;
    logic four_state_probe;
    fifo_valid_split_case #(.Depth(2), .SameCycleRW(1'b0)) d2_rw0 (.done(done[0]));
    fifo_valid_split_case #(.Depth(2), .SameCycleRW(1'b1)) d2_rw1 (.done(done[1]));
    fifo_valid_split_case #(.Depth(3), .SameCycleRW(1'b0)) d3_rw0 (.done(done[2]));
    fifo_valid_split_case #(.Depth(3), .SameCycleRW(1'b1)) d3_rw1 (.done(done[3]));
    initial begin
        four_state_probe = 1'bx;
        #0;
        if ($isunknown(four_state_probe) !== 1'b1 || (four_state_probe === 1'b0) !== 1'b0)
            $fatal(1, "A true four-state simulator is required (X canary)");
        four_state_probe = 1'bz;
        #0;
        if ($isunknown(four_state_probe) !== 1'b1 || (four_state_probe === 1'b1) !== 1'b0)
            $fatal(1, "A true four-state simulator is required (Z canary)");
        wait (&done);
        $display("PASS fifo_valid_split local four-state matrix and stepped backpressure traces");
        $finish;
    end
    initial begin
        #10000;
        $fatal(1, "TIMEOUT waiting for four fixture cases");
    end
endmodule

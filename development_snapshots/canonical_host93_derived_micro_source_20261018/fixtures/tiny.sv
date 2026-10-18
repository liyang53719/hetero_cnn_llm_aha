module micro_leaf #(
    parameter int unsigned STEP = 1
) (
    input logic clk,
    input logic reset,
    input int unsigned delta,
    output int unsigned count
);
    /* verilator hier_block */
    always_ff @(posedge clk) begin
        if (reset) count <= 7;
        else count <= count + delta + STEP;
    end
endmodule

module micro_top (
    input logic clk,
    input logic reset,
    output int unsigned count
);
    int unsigned delta = 0;
    micro_leaf #(.STEP(3)) u_leaf (
        .clk(clk), .reset(reset), .delta(delta), .count(count)
    );
    export "DPI-C" function hm_read_count;
    function int unsigned hm_read_count();
        return count;
    endfunction
    export "DPI-C" function hm_read_delta;
    function int unsigned hm_read_delta();
        return delta;
    endfunction
    export "DPI-C" task hm_set_delta;
    task hm_set_delta(input int unsigned value);
        delta = value;
    endtask
endmodule

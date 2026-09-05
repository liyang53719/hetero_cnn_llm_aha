// SPDX-License-Identifier: Apache-2.0
// One endpoint request describes one <=16x32 tile with exactly depth K steps.
// A malformed stream requires reset; no stale pipeline output may complete a
// subsequent request. This is not a full matrix tiler or a performance counter.
module matrix_tile_step_guard (
 input logic clk_i, rst_ni, start_i,
 input logic [15:0] depth_i,
 input logic step_valid_i, step_ready_i,
 input logic [2:0] context_i,
 input logic clear_i, last_i,
 input logic result_fire_i, result_last_i,
 input logic [2:0] result_context_i,
 output logic allow_step_o, done_o, fault_o
);
 logic active_q, context_valid_q;
 logic [15:0] depth_q;
 logic [16:0] issued_q, returned_q;
 logic [2:0] context_q;
 logic step_legal, fire;
 assign step_legal = issued_q < {1'b0,depth_q} && context_i < 5 &&
   (!context_valid_q || context_i == context_q) &&
   clear_i == (issued_q == 0) && last_i == (issued_q + 1 == {1'b0,depth_q});
 assign allow_step_o = active_q && !fault_o && step_legal;
 assign fire = step_valid_i && step_ready_i && allow_step_o;
 always_ff @(posedge clk_i or negedge rst_ni) begin
   if (!rst_ni) begin
     active_q<=0; context_valid_q<=0; depth_q<=0; issued_q<=0;
     returned_q<=0; context_q<=0; done_o<=0; fault_o<=0;
   end else begin
     done_o<=0;
     if (start_i && !fault_o) begin
       if (active_q || depth_i==0) fault_o<=1;
       else begin active_q<=1;depth_q<=depth_i;issued_q<=0;
         returned_q<=0;context_valid_q<=0;end
     end
     if (active_q && !fault_o) begin
       if (step_valid_i && !step_legal) fault_o<=1;
       if (fire) begin
         issued_q<=issued_q+1;context_valid_q<=1;context_q<=context_i;
       end
       if (result_fire_i) begin
         if (!context_valid_q || result_context_i!=context_q ||
             returned_q>=issued_q ||
             result_last_i!=(returned_q+1=={1'b0,depth_q})) fault_o<=1;
         else begin
           returned_q<=returned_q+1;
           if (result_last_i && !(step_valid_i && !step_legal)) begin
             done_o<=1;active_q<=0;
           end
         end
       end
     end
   end
 end
endmodule

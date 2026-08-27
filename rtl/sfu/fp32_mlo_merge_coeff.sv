// SPDX-License-Identifier: Apache-2.0
// Pipelined stable M/L coefficient merge.  Exp2, L multiplies and L add are
// separated by registers so no cycle contains multiple FP arithmetic stages.
module fp32_mlo_merge_coeff(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic in_valid_i,
  output logic in_ready_o,
  input  logic [31:0] ma_i,
  input  logic [31:0] la_i,
  input  logic [31:0] mb_i,
  input  logic [31:0] lb_i,
  output logic out_valid_o,
  input  logic out_ready_i,
  output logic [31:0] m_o,
  output logic [31:0] l_o,
  output logic [31:0] alpha_o,
  output logic [31:0] beta_o,
  output logic [4:0] flags_o
);
  typedef enum logic [2:0] {IDLE, SUBTRACT, SCALE, EXP_ISSUE, EXP_WAIT, L_ADD, OUT} state_t;
  state_t state_q;
  logic [31:0] ma_q, la_q, mb_q, lb_q, m_new_q;
  logic [31:0] delta_a, delta_b, delta2_a, delta2_b;
  logic [31:0] delta_a_q, delta_b_q, delta2_a_q, delta2_b_q;
  logic [31:0] exp_a, exp_b, product_a, product_b;
  logic [31:0] product_a_q, product_b_q, l_sum;
  logic [4:0] f_sub_a, f_sub_b, f_delta_a, f_delta_b;
  logic [4:0] f_mul_a, f_mul_b, f_l_add;
  logic [12:0] f_exp_a, f_exp_b;
  logic exp_a_in_valid, exp_a_in_ready, exp_a_out_valid, exp_a_out_ready;
  logic exp_b_in_valid, exp_b_in_ready, exp_b_out_valid, exp_b_out_ready;
  logic [31:0] exp_a_accepted, exp_a_completed, exp_b_accepted, exp_b_completed;
  logic [4:0] flags_q;

  function automatic logic fp32_gt(input logic [31:0] a, input logic [31:0] b);
    if (a[31] != b[31]) fp32_gt = !a[31];
    else if (!a[31]) fp32_gt = a[30:0] > b[30:0];
    else fp32_gt = a[30:0] < b[30:0];
  endfunction

  HeteroFP32Alu sub_a(
    .io_op(1'b0), .io_x(ma_q), .io_y({~m_new_q[31], m_new_q[30:0]}),
    .io_out(delta_a), .io_exceptionFlags(f_sub_a)
  );
  HeteroFP32Alu sub_b(
    .io_op(1'b0), .io_x(mb_q), .io_y({~m_new_q[31], m_new_q[30:0]}),
    .io_out(delta_b), .io_exceptionFlags(f_sub_b)
  );
  HeteroFP32Alu scale_a(
    .io_op(1'b1), .io_x(delta_a_q), .io_y(32'h3fb8aa3b),
    .io_out(delta2_a), .io_exceptionFlags(f_delta_a)
  );
  HeteroFP32Alu scale_b(
    .io_op(1'b1), .io_x(delta_b_q), .io_y(32'h3fb8aa3b),
    .io_out(delta2_b), .io_exceptionFlags(f_delta_b)
  );

  assign exp_a_in_valid = state_q == EXP_ISSUE;
  assign exp_b_in_valid = state_q == EXP_ISSUE;
  assign exp_a_out_ready = state_q == EXP_WAIT && exp_a_out_valid && exp_b_out_valid;
  assign exp_b_out_ready = exp_a_out_ready;
  fp32_exp2_pwl exp_a_unit(
    .clk_i, .rst_ni, .in_valid_i(exp_a_in_valid), .in_ready_o(exp_a_in_ready),
    .x_i(delta2_a_q), .out_valid_o(exp_a_out_valid), .out_ready_i(exp_a_out_ready),
    .y_o(exp_a), .exception_flags_o(f_exp_a),
    .accepted_o(exp_a_accepted), .completed_o(exp_a_completed)
  );
  fp32_exp2_pwl exp_b_unit(
    .clk_i, .rst_ni, .in_valid_i(exp_b_in_valid), .in_ready_o(exp_b_in_ready),
    .x_i(delta2_b_q), .out_valid_o(exp_b_out_valid), .out_ready_i(exp_b_out_ready),
    .y_o(exp_b), .exception_flags_o(f_exp_b),
    .accepted_o(exp_b_accepted), .completed_o(exp_b_completed)
  );

  HeteroFP32Alu mul_l_a(
    .io_op(1'b1), .io_x(la_q), .io_y(exp_a),
    .io_out(product_a), .io_exceptionFlags(f_mul_a)
  );
  HeteroFP32Alu mul_l_b(
    .io_op(1'b1), .io_x(lb_q), .io_y(exp_b),
    .io_out(product_b), .io_exceptionFlags(f_mul_b)
  );
  HeteroFP32Alu add_l(
    .io_op(1'b0), .io_x(product_a_q), .io_y(product_b_q),
    .io_out(l_sum), .io_exceptionFlags(f_l_add)
  );

  assign in_ready_o = state_q == IDLE;
  assign out_valid_o = state_q == OUT;
  assign flags_o = flags_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= IDLE;
      ma_q <= '0; la_q <= '0; mb_q <= '0; lb_q <= '0; m_new_q <= '0;
      product_a_q <= '0; product_b_q <= '0;
      delta_a_q <= '0; delta_b_q <= '0; delta2_a_q <= '0; delta2_b_q <= '0;
      m_o <= '0; l_o <= '0; alpha_o <= '0; beta_o <= '0; flags_q <= '0;
    end else begin
      case (state_q)
        IDLE: if (in_valid_i) begin
          if (la_i[30:0] == 0) begin
            m_o <= mb_i; l_o <= lb_i; alpha_o <= 32'd0; beta_o <= 32'h3f800000;
            flags_q <= '0; state_q <= OUT;
          end else if (lb_i[30:0] == 0) begin
            m_o <= ma_i; l_o <= la_i; alpha_o <= 32'h3f800000; beta_o <= 32'd0;
            flags_q <= '0; state_q <= OUT;
          end else begin
            ma_q <= ma_i; la_q <= la_i; mb_q <= mb_i; lb_q <= lb_i;
            m_new_q <= fp32_gt(mb_i, ma_i) ? mb_i : ma_i;
            flags_q <= '0;
            state_q <= SUBTRACT;
          end
        end
        SUBTRACT: begin
          delta_a_q <= delta_a;
          delta_b_q <= delta_b;
          flags_q <= f_sub_a | f_sub_b;
          state_q <= SCALE;
        end
        SCALE: begin
          delta2_a_q <= delta2_a;
          delta2_b_q <= delta2_b;
          flags_q <= flags_q | f_delta_a | f_delta_b;
          state_q <= EXP_ISSUE;
        end
        EXP_ISSUE: if (exp_a_in_ready && exp_b_in_ready) state_q <= EXP_WAIT;
        EXP_WAIT: if (exp_a_out_valid && exp_b_out_valid) begin
          m_o <= m_new_q;
          alpha_o <= exp_a;
          beta_o <= exp_b;
          product_a_q <= product_a;
          product_b_q <= product_b;
          flags_q <= flags_q | f_exp_a[4:0] | f_exp_b[4:0] | f_mul_a | f_mul_b;
          state_q <= L_ADD;
        end
        L_ADD: begin
          l_o <= l_sum;
          flags_q <= flags_q | f_l_add;
          state_q <= OUT;
        end
        OUT: if (out_ready_i) state_q <= IDLE;
        default: state_q <= IDLE;
      endcase
    end
  end
endmodule

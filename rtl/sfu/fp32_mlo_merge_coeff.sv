// SPDX-License-Identifier: Apache-2.0
// Depends on pinned HeteroFP32Alu and fp32_exp2_pwl generated locally.
module fp32_mlo_merge_coeff(
 input logic clk_i,rst_ni,in_valid_i,output logic in_ready_o,
 input logic[31:0]ma_i,la_i,mb_i,lb_i,
 output logic out_valid_o,input logic out_ready_i,
 output logic[31:0]m_o,l_o,alpha_o,beta_o,output logic[4:0]flags_o);
 typedef enum logic[1:0]{IDLE,ISSUE,WAIT,OUT}st_t;st_t st;
 logic[31:0]ma,la,mb,lb,mn,da,db,ea,eb,pa,pb,ls;logic[4:0]f0,f1,f2,f3,f4;logic eai,ear,eao,eae,ebi,ebr,ebo,ebe;
 function automatic logic gt(input logic[31:0]a,b);if(a[31]!=b[31])gt=!a[31];else if(!a[31])gt=a[30:0]>b[30:0];else gt=a[30:0]<b[30:0];endfunction
 HeteroFP32Alu s0(.io_op(1'b0),.io_x(ma),.io_y({~mn[31],mn[30:0]}),.io_out(da),.io_exceptionFlags(f0));
 HeteroFP32Alu s1(.io_op(1'b0),.io_x(mb),.io_y({~mn[31],mn[30:0]}),.io_out(db),.io_exceptionFlags(f1));
 logic[31:0]d2a,d2b;HeteroFP32Alu m0(.io_op(1'b1),.io_x(da),.io_y(32'h3fb8aa3b),.io_out(d2a),.io_exceptionFlags(f2));HeteroFP32Alu m1(.io_op(1'b1),.io_x(db),.io_y(32'h3fb8aa3b),.io_out(d2b),.io_exceptionFlags(f3));
 assign eai=st==ISSUE;assign ebi=st==ISSUE;assign eae=st==WAIT&&eao&&ebo;assign ebe=eae;
 fp32_exp2_pwl xa(.clk_i,.rst_ni,.in_valid_i(eai),.in_ready_o(ear),.x_i(d2a),.out_valid_o(eao),.out_ready_i(eae),.y_o(ea),.exception_flags_o());
 fp32_exp2_pwl xb(.clk_i,.rst_ni,.in_valid_i(ebi),.in_ready_o(ebr),.x_i(d2b),.out_valid_o(ebo),.out_ready_i(ebe),.y_o(eb),.exception_flags_o());
 HeteroFP32Alu ml0(.io_op(1'b1),.io_x(la),.io_y(ea),.io_out(pa),.io_exceptionFlags());HeteroFP32Alu ml1(.io_op(1'b1),.io_x(lb),.io_y(eb),.io_out(pb),.io_exceptionFlags());HeteroFP32Alu al(.io_op(1'b0),.io_x(pa),.io_y(pb),.io_out(ls),.io_exceptionFlags(f4));
 assign in_ready_o=st==IDLE;assign out_valid_o=st==OUT;
 always_ff@(posedge clk_i or negedge rst_ni)if(!rst_ni)begin st<=IDLE;m_o<=0;l_o<=0;alpha_o<=0;beta_o<=0;flags_o<=0;end else case(st)
 IDLE:if(in_valid_i)begin if(la_i[30:0]==0)begin m_o<=mb_i;l_o<=lb_i;alpha_o<=0;beta_o<=32'h3f800000;st<=OUT;end else if(lb_i[30:0]==0)begin m_o<=ma_i;l_o<=la_i;alpha_o<=32'h3f800000;beta_o<=0;st<=OUT;end else begin ma<=ma_i;la<=la_i;mb<=mb_i;lb<=lb_i;mn<=gt(mb_i,ma_i)?mb_i:ma_i;st<=ISSUE;end end
 ISSUE:if(ear&&ebr)st<=WAIT;
 WAIT:if(eao&&ebo)begin m_o<=mn;l_o<=ls;alpha_o<=ea;beta_o<=eb;flags_o<=f0|f1|f2|f3|f4;st<=OUT;end
 OUT:if(out_ready_i)st<=IDLE;default:st<=IDLE;endcase
endmodule

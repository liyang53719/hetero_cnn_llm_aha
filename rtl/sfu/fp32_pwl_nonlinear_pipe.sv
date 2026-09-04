// SPDX-License-Identifier: Apache-2.0
module fp32_pwl_nonlinear_pipe(
 input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[7:0]variant_i,input logic[31:0]x_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]y_o,output logic[4:0]exception_flags_o);
 `include "fp32_pwl_nonlinear_coeffs.svh"
 localparam logic[2:0]IDLE=0,LOOKUP=1,MISSUE=2,MWAIT=3,AISSUE=4,AWAIT=5,OUT=6;
 logic[2:0]st;logic[7:0]variant_q;logic[31:0]xq,mq,bq,pq,yq;logic[4:0]flags_q;
 logic[15:0]scaled_floor;logic[7:0]scale_flags;logic signed[16:0]bucket;logic[6:0]index;logic[63:0]coeff;
 logic nan,positive_tail,negative_tail,special;logic[31:0]special_result;
 logic miv,mir,mov,mor,mu,aiv,air,aov,aor,au;logic[31:0]mo,ao;logic[4:0]mf,af;
 function automatic logic fp_ge(input logic[31:0]a,input logic[31:0]b);begin if(a[30:0]==0&&b[30:0]==0)fp_ge=1;else if(a[31]!=b[31])fp_ge=!a[31];else if(!a[31])fp_ge=a[30:0]>=b[30:0];else fp_ge=a[30:0]<=b[30:0];end endfunction
 HeteroFP32Scale16Floor floor16(.io_x(xq),.io_out(scaled_floor),.io_exceptionFlags(scale_flags));
 always_comb begin
  bucket=variant_q==1?($signed(scaled_floor)>>>2):($signed(scaled_floor)>>>1);index=7'(bucket+17'sd64);coeff=fp32_pwl_coeff(variant_q==2,index);
  nan=&xq[30:23]&&|xq[22:0];positive_tail=fp_ge(xq,variant_q==1?32'h41800000:32'h41000000);negative_tail=fp_ge(variant_q==1?32'hc1800000:32'hc1000000,xq);special=nan||positive_tail||negative_tail;
  if(nan)special_result=xq|32'h00400000;else if(negative_tail)special_result=0;else special_result=xq;
 end
 assign miv=st==MISSUE;assign mor=st==MWAIT;assign aiv=st==AISSUE;assign aor=st==AWAIT;
 HeteroFP32MulPipeBit1 mul(.clock(clk_i),.reset(!rst_ni),.io_inValid(miv),.io_inReady(mir),.io_x(mq),.io_y(xq),.io_userIn(1'b0),.io_outValid(mov),.io_outReady(mor),.io_out(mo),.io_exceptionFlags(mf),.io_userOut(mu));
 HeteroFP32AddPipeBit1 add(.clock(clk_i),.reset(!rst_ni),.io_inValid(aiv),.io_inReady(air),.io_x(pq),.io_y(bq),.io_userIn(1'b0),.io_outValid(aov),.io_outReady(aor),.io_out(ao),.io_exceptionFlags(af),.io_userOut(au));
 assign in_ready_o=st==IDLE;assign out_valid_o=st==OUT;assign y_o=yq;assign exception_flags_o=flags_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;variant_q<=0;xq<=0;mq<=0;bq<=0;pq<=0;yq<=0;flags_q<=0;end else case(st)
  IDLE:if(in_valid_i)begin variant_q<=variant_i;xq<=x_i;flags_q<=0;st<=LOOKUP;end
  LOOKUP:if(special)begin yq<=special_result;st<=OUT;end else begin mq<=coeff[63:32];bq<=coeff[31:0];st<=MISSUE;end
  MISSUE:if(mir)st<=MWAIT;MWAIT:if(mov)begin pq<=mo;flags_q<=mf;st<=AISSUE;end
  AISSUE:if(air)st<=AWAIT;AWAIT:if(aov)begin yq<=ao;flags_q<=flags_q|af;st<=OUT;end
  OUT:if(out_ready_i)st<=IDLE;default:st<=IDLE;endcase end
endmodule

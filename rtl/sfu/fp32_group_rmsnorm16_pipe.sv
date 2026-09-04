// SPDX-License-Identifier: Apache-2.0
module fp32_norm16_shared_pipe(input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,input logic mode_group_i,mode_rms_i,mode_layer_i,input logic[511:0]x_i,weight_i,bias_i,input logic[31:0]epsilon_i,output logic out_valid_o,input logic out_ready_i,output logic[511:0]y_o,output logic[4:0]exception_flags_o);
 localparam logic[1:0]IDLE=0,ISSUE=1,WAIT=2,OUT=3;logic[1:0]st;logic[1:0]group_q;logic group_mode_q,rms_mode_q,layer_mode_q;logic[511:0]xq,wq,bq,yq,gx,gw,gb;logic[31:0]epsq;logic cv,cr,cov,cor;logic[511:0]cy;logic[4:0]cf,flags_q;
 always_comb begin gx=xq;gw=wq;gb=bq;if(group_mode_q)begin gx=0;gw=0;gb=0;for(int k=0;k<4;k++)begin gx[k*32+:32]=xq[(group_q*4+k)*32+:32];gw[k*32+:32]=wq[(group_q*4+k)*32+:32];end end end
 assign cv=st==ISSUE;assign cor=st==WAIT;fp32_norm16_rms_l2_pipe core(.clk_i,.rst_ni,.in_valid_i(cv),.in_ready_o(cr),.mode_rms_i(rms_mode_q),.mode_layer_i(layer_mode_q),.x_i(gx),.weight_i(gw),.bias_i(gb),.epsilon_i(epsq),.mean_scale_i(group_mode_q?32'h3e800000:32'h3d800000),.out_valid_o(cov),.out_ready_i(cor),.y_o(cy),.exception_flags_o(cf));
 assign in_ready_o=st==IDLE;assign out_valid_o=st==OUT;assign y_o=yq;assign exception_flags_o=flags_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;group_q<=0;group_mode_q<=0;rms_mode_q<=0;layer_mode_q<=0;xq<=0;wq<=0;bq<=0;yq<=0;epsq<=0;flags_q<=0;end else case(st)
  IDLE:if(in_valid_i)begin xq<=x_i;wq<=weight_i;bq<=bias_i;epsq<=epsilon_i;group_q<=0;group_mode_q<=mode_group_i;rms_mode_q<=mode_rms_i;layer_mode_q<=mode_layer_i;flags_q<=0;st<=ISSUE;end
  ISSUE:if(cr)st<=WAIT;WAIT:if(cov)begin flags_q<=flags_q|cf;if(group_mode_q)begin for(int k=0;k<4;k++)yq[(group_q*4+k)*32+:32]<=cy[k*32+:32];if(group_q==3)st<=OUT;else begin group_q<=group_q+1'b1;st<=ISSUE;end end else begin yq<=cy;st<=OUT;end end
  OUT:if(out_ready_i)st<=IDLE;default:st<=IDLE;endcase end
endmodule

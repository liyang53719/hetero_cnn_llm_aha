// SPDX-License-Identifier: Apache-2.0
module fp32_rope_pair_pipe(
 input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,
 input logic[31:0]even_i,odd_i,cos_i,sin_i,output logic out_valid_o,input logic out_ready_i,
 output logic[31:0]even_o,odd_o,output logic[4:0]exception_flags_o);
 localparam logic[2:0]IDLE=0,MISSUE=1,MWAIT=2,AISSUE=3,AWAIT=4,OUT=5;
 logic[2:0]st;logic[31:0]eq,oq,cq,sq,ecq,osq,esq,ocq,erq,orq;logic[4:0]flags_q;
 logic[3:0]mir,mov;logic[127:0]mo;logic[19:0]mf;logic[47:0]mu;logic mallin,mallout,mconsume;
 logic[1:0]air,aov;logic[63:0]ao;logic[9:0]af;logic[23:0]au;logic aallin,aallout,aconsume;
 always_comb begin mallin=&mir;mallout=&mov;aallin=&air;aallout=&aov;end
 assign mconsume=st==MWAIT&&mallout;assign aconsume=st==AWAIT&&aallout;
 HeteroFP32MulPipeTag12 m0(.clock(clk_i),.reset(!rst_ni),.io_inValid(st==MISSUE&&mallin),.io_inReady(mir[0]),.io_x(eq),.io_y(cq),.io_userIn(12'd0),.io_outValid(mov[0]),.io_outReady(mconsume),.io_out(mo[31:0]),.io_exceptionFlags(mf[4:0]),.io_userOut(mu[11:0]));
 HeteroFP32MulPipeTag12 m1(.clock(clk_i),.reset(!rst_ni),.io_inValid(st==MISSUE&&mallin),.io_inReady(mir[1]),.io_x(oq),.io_y(sq),.io_userIn(12'd1),.io_outValid(mov[1]),.io_outReady(mconsume),.io_out(mo[63:32]),.io_exceptionFlags(mf[9:5]),.io_userOut(mu[23:12]));
 HeteroFP32MulPipeTag12 m2(.clock(clk_i),.reset(!rst_ni),.io_inValid(st==MISSUE&&mallin),.io_inReady(mir[2]),.io_x(eq),.io_y(sq),.io_userIn(12'd2),.io_outValid(mov[2]),.io_outReady(mconsume),.io_out(mo[95:64]),.io_exceptionFlags(mf[14:10]),.io_userOut(mu[35:24]));
 HeteroFP32MulPipeTag12 m3(.clock(clk_i),.reset(!rst_ni),.io_inValid(st==MISSUE&&mallin),.io_inReady(mir[3]),.io_x(oq),.io_y(cq),.io_userIn(12'd3),.io_outValid(mov[3]),.io_outReady(mconsume),.io_out(mo[127:96]),.io_exceptionFlags(mf[19:15]),.io_userOut(mu[47:36]));
 HeteroFP32AddPipeTag12 a0(.clock(clk_i),.reset(!rst_ni),.io_inValid(st==AISSUE&&aallin),.io_inReady(air[0]),.io_x(ecq),.io_y({~osq[31],osq[30:0]}),.io_userIn(12'd0),.io_outValid(aov[0]),.io_outReady(aconsume),.io_out(ao[31:0]),.io_exceptionFlags(af[4:0]),.io_userOut(au[11:0]));
 HeteroFP32AddPipeTag12 a1(.clock(clk_i),.reset(!rst_ni),.io_inValid(st==AISSUE&&aallin),.io_inReady(air[1]),.io_x(esq),.io_y(ocq),.io_userIn(12'd1),.io_outValid(aov[1]),.io_outReady(aconsume),.io_out(ao[63:32]),.io_exceptionFlags(af[9:5]),.io_userOut(au[23:12]));
 assign in_ready_o=st==IDLE;assign out_valid_o=st==OUT;assign even_o=erq;assign odd_o=orq;assign exception_flags_o=flags_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;eq<=0;oq<=0;cq<=0;sq<=0;ecq<=0;osq<=0;esq<=0;ocq<=0;erq<=0;orq<=0;flags_q<=0;end else case(st)
  IDLE:if(in_valid_i)begin eq<=even_i;oq<=odd_i;cq<=cos_i;sq<=sin_i;flags_q<=0;st<=MISSUE;end
  MISSUE:if(mallin)st<=MWAIT;
  MWAIT:if(mallout)begin ecq<=mo[31:0];osq<=mo[63:32];esq<=mo[95:64];ocq<=mo[127:96];flags_q<=mf[4:0]|mf[9:5]|mf[14:10]|mf[19:15];st<=AISSUE;end
  AISSUE:if(aallin)st<=AWAIT;
  AWAIT:if(aallout)begin erq<=ao[31:0];orq<=ao[63:32];flags_q<=flags_q|af[4:0]|af[9:5];st<=OUT;end
  OUT:if(out_ready_i)st<=IDLE;default:st<=IDLE;endcase end
endmodule

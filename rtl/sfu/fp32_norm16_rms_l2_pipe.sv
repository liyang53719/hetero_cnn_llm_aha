// SPDX-License-Identifier: Apache-2.0
module fp32_norm16_rms_l2_pipe(
 input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,input logic mode_rms_i,
 input logic[511:0]x_i,weight_i,input logic[31:0]epsilon_i,mean_scale_i,output logic out_valid_o,input logic out_ready_i,
 output logic[511:0]y_o,output logic[4:0]exception_flags_o);
 localparam logic[3:0]IDLE=0,VISSUE=1,VWAIT=2,RISSUE=3,RWAIT=4,SISSUE=5,SWAIT=6,QISSUE=7,QWAIT=8,OUT=9;
 logic[3:0]st;logic mode_q;logic[1:0]vphase;logic scalar_add;logic[511:0]xq,wq,tmpq,yq;logic[31:0]epsq,mean_scale_q,scalar_q,norm_q,invq;
 logic[15:0]vir,vov;logic[511:0]vo;logic[79:0]vf;logic[191:0]vu;logic vallin,vallout,vconsume;logic[4:0]flags_q,vflags;integer f,j;
 logic riv,rir,rov,ror;logic[31:0]rsum,ra,rc;logic[4:0]rf;
 logic siv,sir,sov,sor,su,aiv,air,aov,aor,au;logic[31:0]so,ao;logic[4:0]sf,af;
 logic qiv,qir,qov,qor,qu;logic[31:0]qo,qa,qc;logic[4:0]qf;logic qde;
 always_comb begin vallin=1;vallout=1;vflags=0;for(f=0;f<16;f++)begin vallin&=vir[f];vallout&=vov[f];vflags|=vf[f*5+:5];end end
 assign vconsume=st==VWAIT&&vallout;genvar i;generate for(i=0;i<16;i++)begin:g
  logic[31:0]vx,vy;assign vx=vphase==0?xq[i*32+:32]:vphase==1?xq[i*32+:32]:tmpq[i*32+:32];
  assign vy=vphase==0?xq[i*32+:32]:vphase==1?invq:wq[i*32+:32];
  HeteroFP32MulPipeTag12 m(.clock(clk_i),.reset(!rst_ni),.io_inValid(st==VISSUE&&vallin),.io_inReady(vir[i]),.io_x(vx),.io_y(vy),.io_userIn(i),.io_outValid(vov[i]),.io_outReady(vconsume),.io_out(vo[i*32+:32]),.io_exceptionFlags(vf[i*5+:5]),.io_userOut(vu[i*12+:12]));end endgenerate
 fp32_reduce16 red(.clk_i,.rst_ni,.in_valid_i(riv),.in_ready_o(rir),.data_i(tmpq),.out_valid_o(rov),.out_ready_i(ror),.sum_o(rsum),.exception_flags_o(rf),.accepted_vectors_o(ra),.completed_vectors_o(rc));
 assign siv=st==SISSUE&&!scalar_add;assign sor=st==SWAIT&&!scalar_add;assign aiv=st==SISSUE&&scalar_add;assign aor=st==SWAIT&&scalar_add;
 HeteroFP32MulPipeBit1 sm(.clock(clk_i),.reset(!rst_ni),.io_inValid(siv),.io_inReady(sir),.io_x(scalar_q),.io_y(mean_scale_q),.io_userIn(0),.io_outValid(sov),.io_outReady(sor),.io_out(so),.io_exceptionFlags(sf),.io_userOut(su));
 HeteroFP32AddPipeBit1 sa(.clock(clk_i),.reset(!rst_ni),.io_inValid(aiv),.io_inReady(air),.io_x(scalar_q),.io_y(epsq),.io_userIn(0),.io_outValid(aov),.io_outReady(aor),.io_out(ao),.io_exceptionFlags(af),.io_userOut(au));
 assign qiv=st==QISSUE;assign qor=st==QWAIT;fp32_rsqrt_nr2 rs(.clk_i,.rst_ni,.in_valid_i(qiv),.in_ready_o(qir),.x_i(norm_q),.out_valid_o(qov),.out_ready_i(qor),.y_o(qo),.exception_flags_o(qf),.domain_error_o(qde),.accepted_o(qa),.completed_o(qc));
 assign riv=st==RISSUE;assign ror=st==RWAIT;assign in_ready_o=st==IDLE;assign out_valid_o=st==OUT;assign y_o=yq;assign exception_flags_o=flags_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;mode_q<=0;vphase<=0;xq<=0;wq<=0;tmpq<=0;yq<=0;epsq<=0;mean_scale_q<=0;scalar_q<=0;norm_q<=0;invq<=0;flags_q<=0;scalar_add<=0;end else case(st)
  IDLE:if(in_valid_i)begin mode_q<=mode_rms_i;xq<=x_i;wq<=weight_i;epsq<=epsilon_i;mean_scale_q<=mean_scale_i;flags_q<=0;vphase<=0;st<=VISSUE;end
  VISSUE:if(vallin)st<=VWAIT;VWAIT:if(vallout)begin flags_q<=flags_q|vflags;for(j=0;j<16;j++)tmpq[j*32+:32]<=vo[j*32+:32];
   if(vphase==0)st<=RISSUE;else if(vphase==1)begin if(mode_q)begin vphase<=2;st<=VISSUE;end else begin for(j=0;j<16;j++)yq[j*32+:32]<=vo[j*32+:32];st<=OUT;end end
   else begin for(j=0;j<16;j++)yq[j*32+:32]<=vo[j*32+:32];st<=OUT;end end
  RISSUE:if(rir)st<=RWAIT;RWAIT:if(rov)begin flags_q<=flags_q|rf;scalar_q<=rsum;scalar_add<=!mode_q;st<=SISSUE;end
  SISSUE:if((scalar_add&&air)||(!scalar_add&&sir))st<=SWAIT;SWAIT:if((scalar_add&&aov)||(!scalar_add&&sov))begin flags_q<=flags_q|(scalar_add?af:sf);
   if(scalar_add)begin norm_q<=ao;st<=QISSUE;end else begin scalar_q<=so;scalar_add<=1;st<=SISSUE;end end
  QISSUE:if(qir)st<=QWAIT;QWAIT:if(qov)begin flags_q<=flags_q|qf;invq<=qo;vphase<=1;st<=VISSUE;end
  OUT:if(out_ready_i)st<=IDLE;default:st<=IDLE;endcase end
endmodule

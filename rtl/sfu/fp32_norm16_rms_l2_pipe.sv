// SPDX-License-Identifier: Apache-2.0
module fp32_norm16_rms_l2_pipe(
 input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,
 input logic mode_rms_i,mode_layer_i,input logic[511:0]x_i,weight_i,bias_i,
 input logic[31:0]epsilon_i,mean_scale_i,output logic out_valid_o,input logic out_ready_i,
 output logic[511:0]y_o,output logic[4:0]exception_flags_o);
 localparam logic[3:0] IDLE=0,MISSUE=1,MWAIT=2,RISSUE=3,RWAIT=4,SISSUE=5,SWAIT=6,QISSUE=7,QWAIT=8,AISSUE=9,AWAIT=10,OUT=11;
 localparam logic[2:0] M_SQUARE_X=0,M_SQUARE_CENTER=1,M_NORMALIZE=2,M_WEIGHT=3;
 localparam logic[1:0] S_MEAN_SCALE=0,S_NORM_SCALE=1,S_EPS=2;
 localparam logic A_CENTER=0,A_BIAS=1;
 logic[3:0]st;logic mode_rms_q,mode_layer_q;logic[2:0]mphase;logic[1:0]sphase;logic aphase,rphase;
 logic[511:0]xq,wq,bq,centerq,tmpq,yq;logic[31:0]epsq,mean_scale_q,scalar_q,norm_q,invq,mean_q;
 logic[15:0]mir,mov,airv,aov;logic[511:0]mo,addo;logic[79:0]mf,addf;logic[191:0]mu,addu;
 logic mallin,mallout,mconsume,aallin,aallout,aconsume;logic[4:0]flags_q,mflags,aflags;integer f,j;
 logic riv,rir,rov,ror;logic[511:0]reduce_data;logic[31:0]rsum,ra,rc;logic[4:0]rf;
 logic siv,sir,sov,sor,su,saiv,sair,saov,saor,sau;logic[31:0]so,sao;logic[4:0]sf,saf;
 logic qiv,qir,qov,qor,qu;logic[31:0]qo,qa,qc;logic[4:0]qf;logic qde;
 always_comb begin mallin=1;mallout=1;mflags=0;aallin=1;aallout=1;aflags=0;for(f=0;f<16;f++)begin mallin&=mir[f];mallout&=mov[f];mflags|=mf[f*5+:5];aallin&=airv[f];aallout&=aov[f];aflags|=addf[f*5+:5];end end
 assign mconsume=st==MWAIT&&mallout;assign aconsume=st==AWAIT&&aallout;
 genvar i;generate for(i=0;i<16;i++)begin:g
 logic[31:0]mx,my,ax,ay;
  localparam logic[11:0] LANE_TAG=i;
  always_comb begin mx=xq[i*32+:32];my=xq[i*32+:32];case(mphase)
   M_SQUARE_CENTER:begin mx=centerq[i*32+:32];my=centerq[i*32+:32];end
   M_NORMALIZE:begin mx=mode_layer_q?centerq[i*32+:32]:xq[i*32+:32];my=invq;end
   M_WEIGHT:begin mx=tmpq[i*32+:32];my=wq[i*32+:32];end
   default:begin mx=xq[i*32+:32];my=xq[i*32+:32];end endcase
   ax=aphase?tmpq[i*32+:32]:xq[i*32+:32];ay=aphase?bq[i*32+:32]:{~mean_q[31],mean_q[30:0]};end
  HeteroFP32MulPipeTag12 m(.clock(clk_i),.reset(!rst_ni),.io_inValid(st==MISSUE&&mallin),.io_inReady(mir[i]),.io_x(mx),.io_y(my),.io_userIn(LANE_TAG),.io_outValid(mov[i]),.io_outReady(mconsume),.io_out(mo[i*32+:32]),.io_exceptionFlags(mf[i*5+:5]),.io_userOut(mu[i*12+:12]));
  HeteroFP32AddPipeTag12 a(.clock(clk_i),.reset(!rst_ni),.io_inValid(st==AISSUE&&aallin),.io_inReady(airv[i]),.io_x(ax),.io_y(ay),.io_userIn(LANE_TAG),.io_outValid(aov[i]),.io_outReady(aconsume),.io_out(addo[i*32+:32]),.io_exceptionFlags(addf[i*5+:5]),.io_userOut(addu[i*12+:12]));
 end endgenerate
 assign reduce_data=(mode_layer_q&&!rphase)?xq:tmpq;
 fp32_reduce16 red(.clk_i,.rst_ni,.in_valid_i(riv),.in_ready_o(rir),.data_i(reduce_data),.out_valid_o(rov),.out_ready_i(ror),.sum_o(rsum),.exception_flags_o(rf),.accepted_vectors_o(ra),.completed_vectors_o(rc));
 assign siv=st==SISSUE&&sphase!=S_EPS;assign sor=st==SWAIT&&sphase!=S_EPS;assign saiv=st==SISSUE&&sphase==S_EPS;assign saor=st==SWAIT&&sphase==S_EPS;
 HeteroFP32MulPipeBit1 sm(.clock(clk_i),.reset(!rst_ni),.io_inValid(siv),.io_inReady(sir),.io_x(scalar_q),.io_y(mean_scale_q),.io_userIn(0),.io_outValid(sov),.io_outReady(sor),.io_out(so),.io_exceptionFlags(sf),.io_userOut(su));
 HeteroFP32AddPipeBit1 sa(.clock(clk_i),.reset(!rst_ni),.io_inValid(saiv),.io_inReady(sair),.io_x(scalar_q),.io_y(epsq),.io_userIn(0),.io_outValid(saov),.io_outReady(saor),.io_out(sao),.io_exceptionFlags(saf),.io_userOut(sau));
 assign qiv=st==QISSUE;assign qor=st==QWAIT;fp32_rsqrt_nr2 rs(.clk_i,.rst_ni,.in_valid_i(qiv),.in_ready_o(qir),.x_i(norm_q),.out_valid_o(qov),.out_ready_i(qor),.y_o(qo),.exception_flags_o(qf),.domain_error_o(qde),.accepted_o(qa),.completed_o(qc));
 assign riv=st==RISSUE;assign ror=st==RWAIT;assign in_ready_o=st==IDLE;assign out_valid_o=st==OUT;assign y_o=yq;assign exception_flags_o=flags_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin st<=IDLE;mode_rms_q<=0;mode_layer_q<=0;mphase<=0;sphase<=0;aphase<=0;rphase<=0;xq<=0;wq<=0;bq<=0;centerq<=0;tmpq<=0;yq<=0;epsq<=0;mean_scale_q<=0;scalar_q<=0;norm_q<=0;invq<=0;mean_q<=0;flags_q<=0;end else case(st)
   IDLE:if(in_valid_i)begin mode_rms_q<=mode_rms_i;mode_layer_q<=mode_layer_i;xq<=x_i;wq<=weight_i;bq<=bias_i;epsq<=epsilon_i;mean_scale_q<=mean_scale_i;flags_q<=0;rphase<=0;if(mode_layer_i)st<=RISSUE;else begin mphase<=M_SQUARE_X;st<=MISSUE;end end
   MISSUE:if(mallin)st<=MWAIT;
   MWAIT:if(mallout)begin flags_q<=flags_q|mflags;for(j=0;j<16;j++)tmpq[j*32+:32]<=mo[j*32+:32];if(mphase==M_SQUARE_X||mphase==M_SQUARE_CENTER)begin rphase<=1;st<=RISSUE;end else if(mphase==M_NORMALIZE)begin if(mode_rms_q||mode_layer_q)begin mphase<=M_WEIGHT;st<=MISSUE;end else begin for(j=0;j<16;j++)yq[j*32+:32]<=mo[j*32+:32];st<=OUT;end end else if(mode_layer_q)begin aphase<=A_BIAS;st<=AISSUE;end else begin for(j=0;j<16;j++)yq[j*32+:32]<=mo[j*32+:32];st<=OUT;end end
   RISSUE:if(rir)st<=RWAIT;
   RWAIT:if(rov)begin flags_q<=flags_q|rf;scalar_q<=rsum;if(mode_layer_q&&!rphase)sphase<=S_MEAN_SCALE;else if(mode_rms_q||mode_layer_q)sphase<=S_NORM_SCALE;else sphase<=S_EPS;st<=SISSUE;end
   SISSUE:if((sphase==S_EPS&&sair)||(sphase!=S_EPS&&sir))st<=SWAIT;
   SWAIT:if((sphase==S_EPS&&saov)||(sphase!=S_EPS&&sov))begin flags_q<=flags_q|(sphase==S_EPS?saf:sf);if(sphase==S_MEAN_SCALE)begin mean_q<=so;aphase<=A_CENTER;st<=AISSUE;end else if(sphase==S_NORM_SCALE)begin scalar_q<=so;sphase<=S_EPS;st<=SISSUE;end else begin norm_q<=sao;st<=QISSUE;end end
   AISSUE:if(aallin)st<=AWAIT;
   AWAIT:if(aallout)begin flags_q<=flags_q|aflags;if(aphase==A_CENTER)begin for(j=0;j<16;j++)centerq[j*32+:32]<=addo[j*32+:32];mphase<=M_SQUARE_CENTER;st<=MISSUE;end else begin for(j=0;j<16;j++)yq[j*32+:32]<=addo[j*32+:32];st<=OUT;end end
   QISSUE:if(qir)st<=QWAIT;
   QWAIT:if(qov)begin flags_q<=flags_q|qf;invq<=qo;mphase<=M_NORMALIZE;st<=MISSUE;end
   OUT:if(out_ready_i)st<=IDLE;default:st<=IDLE;endcase
 end
endmodule

// SPDX-License-Identifier: Apache-2.0
module fp32_mlo_merge_beat_rawpipe#(parameter integer LANES=4)(input logic clk_i,rst_ni,in_valid_i,output logic in_ready_o,input logic[31:0]alpha_i,beta_i,input logic[LANES*32-1:0]oa_i,ob_i,input logic last_i,output logic out_valid_o,input logic out_ready_i,output logic[LANES*32-1:0]o_o,output logic last_o);
 logic[LANES-1:0]mar,mbr,mav,mbv,ar,av,mal,mbl,al;logic[LANES*32-1:0]mao,mbo,ao;logic input_fire,pair_fire,output_fire;assign in_ready_o=&mar&&&mbr;assign input_fire=in_valid_i&&in_ready_o;assign pair_fire=&mav&&&mbv&&&ar;assign out_valid_o=&av;assign output_fire=out_valid_o&&out_ready_i;assign o_o=ao;assign last_o=al[0];
 genvar lane;generate for(lane=0;lane<LANES;lane++)begin:g
 HeteroFP32MulPipeBit1 ma(.clock(clk_i),.reset(!rst_ni),.io_inValid(input_fire),.io_inReady(mar[lane]),.io_x(oa_i[lane*32+:32]),.io_y(alpha_i),.io_userIn(last_i),.io_outValid(mav[lane]),.io_outReady(pair_fire),.io_out(mao[lane*32+:32]),.io_exceptionFlags(),.io_userOut(mal[lane]));
 HeteroFP32MulPipeBit1 mb(.clock(clk_i),.reset(!rst_ni),.io_inValid(input_fire),.io_inReady(mbr[lane]),.io_x(ob_i[lane*32+:32]),.io_y(beta_i),.io_userIn(last_i),.io_outValid(mbv[lane]),.io_outReady(pair_fire),.io_out(mbo[lane*32+:32]),.io_exceptionFlags(),.io_userOut(mbl[lane]));
 HeteroFP32AddPipeBit1 add(.clock(clk_i),.reset(!rst_ni),.io_inValid(pair_fire),.io_inReady(ar[lane]),.io_x(mao[lane*32+:32]),.io_y(mbo[lane*32+:32]),.io_userIn(mal[lane]),.io_outValid(av[lane]),.io_outReady(output_fire),.io_out(ao[lane*32+:32]),.io_exceptionFlags(),.io_userOut(al[lane]));end endgenerate
`ifndef SYNTHESIS
 always_ff@(posedge clk_i)if(rst_ni)begin if((|mav)&&!(&mav))$fatal(1,"mulA desync");if((|mbv)&&!(&mbv))$fatal(1,"mulB desync");if((|av)&&!(&av))$fatal(1,"add desync");if(pair_fire&&mal!==mbl)$fatal(1,"last mismatch");if(out_valid_o&&al!=={LANES{al[0]}})$fatal(1,"last mismatch");end
`endif
endmodule

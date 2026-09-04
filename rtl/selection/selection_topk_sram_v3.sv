// SPDX-License-Identifier: Apache-2.0
module selection_topk_sram_v3(
 input logic clk_i,rst_ni,input logic start_i,output logic start_ready_o,input logic[19:0]item_count_i,input logic[8:0]k_i,
 input logic in_valid_i,output logic in_ready_o,input logic[31:0]score_i,index_i,
 output logic sram_req_valid_o,input logic sram_req_ready_i,output logic sram_req_write_o,output logic[8:0]sram_req_addr_o,output logic[64:0]sram_req_wdata_o,
 input logic sram_rsp_valid_i,output logic sram_rsp_ready_o,input logic[64:0]sram_rsp_rdata_i,input logic sram_rsp_error_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]out_score_o,out_index_o,output logic[8:0]out_rank_o,output logic out_last_o,
 output logic done_o,output logic[7:0]status_o);
 localparam logic[3:0]IDLE=0,CLEAR=1,INPUT=2,SCAN_REQ=3,SCAN_RSP=4,SHIFT_REQ=5,SHIFT_RSP=6,SHIFT_WRITE=7,INSERT=8,EMIT_REQ=9,EMIT_RSP=10,EMIT_OUT=11,DONE=12;
 logic[3:0]st;logic[19:0]count_q,accepted_q;logic[8:0]k_q,clear_q,scan_q,insert_q,shift_q,rank_q;logic[31:0]cand_score_q,cand_index_q;logic cand_last_q;logic[64:0]shift_data_q,out_entry_q;
 function automatic logic is_nan(input logic[31:0]x);return &x[30:23]&&|x[22:0];endfunction
 function automatic logic[31:0]key(input logic[31:0]x);logic[31:0]c;begin c=x[30:0]==0?0:x;key=c[31]?~c:(c^32'h80000000);end endfunction
 function automatic logic better(input logic[31:0]as,ai,bs,bi);begin better=(!is_nan(as)&&is_nan(bs))||((!is_nan(as)&&!is_nan(bs))&&((key(as)>key(bs))||((key(as)==key(bs))&&(ai<bi))))||(is_nan(as)&&is_nan(bs)&&ai<bi);end endfunction
 wire entry_valid=sram_rsp_rdata_i[64];wire[31:0]entry_score=sram_rsp_rdata_i[63:32];wire[31:0]entry_index=sram_rsp_rdata_i[31:0];
 assign start_ready_o=st==IDLE;assign in_ready_o=st==INPUT;assign out_valid_o=st==EMIT_OUT;assign out_score_o=out_entry_q[63:32];assign out_index_o=out_entry_q[31:0];assign out_rank_o=rank_q;assign out_last_o=rank_q+1>=k_q;assign done_o=st==DONE;
 assign sram_req_valid_o=st inside{CLEAR,SCAN_REQ,SHIFT_REQ,SHIFT_WRITE,INSERT,EMIT_REQ};assign sram_req_write_o=st inside{CLEAR,SHIFT_WRITE,INSERT};assign sram_req_addr_o=st==CLEAR?clear_q:st==SCAN_REQ?scan_q:st==SHIFT_REQ?shift_q-1'b1:st==SHIFT_WRITE?shift_q:st==INSERT?insert_q:rank_q;assign sram_req_wdata_o=st==CLEAR?0:st==SHIFT_WRITE?shift_data_q:{1'b1,cand_score_q,cand_index_q};assign sram_rsp_ready_o=st inside{SCAN_RSP,SHIFT_RSP,EMIT_RSP};
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;count_q<=0;accepted_q<=0;k_q<=0;clear_q<=0;scan_q<=0;insert_q<=0;shift_q<=0;rank_q<=0;cand_score_q<=0;cand_index_q<=0;cand_last_q<=0;shift_data_q<=0;out_entry_q<=0;status_o<=0;end else case(st)
  IDLE:if(start_i)begin status_o<=0;accepted_q<=0;if(item_count_i==0||k_i==0||k_i>item_count_i||k_i>512)begin status_o<=5;st<=DONE;end else begin count_q<=item_count_i;k_q<=k_i;clear_q<=0;st<=CLEAR;end end
  CLEAR:if(sram_req_ready_i)begin if(clear_q+1>=k_q)st<=INPUT;else clear_q<=clear_q+1'b1;end
  INPUT:if(in_valid_i)begin cand_score_q<=score_i;cand_index_q<=index_i;cand_last_q<=accepted_q+1>=count_q;accepted_q<=accepted_q+1'b1;scan_q<=0;st<=SCAN_REQ;end
  SCAN_REQ:if(sram_req_ready_i)st<=SCAN_RSP;
  SCAN_RSP:if(sram_rsp_valid_i)begin if(sram_rsp_error_i)begin status_o<=7;st<=DONE;end else if(!entry_valid||better(cand_score_q,cand_index_q,entry_score,entry_index))begin insert_q<=scan_q;shift_q<=k_q-1'b1;if(k_q-1>scan_q)st<=SHIFT_REQ;else st<=INSERT;end else if(scan_q+1<k_q)begin scan_q<=scan_q+1'b1;st<=SCAN_REQ;end else if(cand_last_q)begin rank_q<=0;st<=EMIT_REQ;end else st<=INPUT;end
  SHIFT_REQ:if(sram_req_ready_i)st<=SHIFT_RSP;
  SHIFT_RSP:if(sram_rsp_valid_i)begin if(sram_rsp_error_i)begin status_o<=7;st<=DONE;end else begin shift_data_q<=sram_rsp_rdata_i;st<=SHIFT_WRITE;end end
  SHIFT_WRITE:if(sram_req_ready_i)begin if(shift_q-1>insert_q)begin shift_q<=shift_q-1'b1;st<=SHIFT_REQ;end else st<=INSERT;end
  INSERT:if(sram_req_ready_i)begin if(cand_last_q)begin rank_q<=0;st<=EMIT_REQ;end else st<=INPUT;end
  EMIT_REQ:if(sram_req_ready_i)st<=EMIT_RSP;
  EMIT_RSP:if(sram_rsp_valid_i)begin if(sram_rsp_error_i)begin status_o<=7;st<=DONE;end else begin out_entry_q<=sram_rsp_rdata_i;st<=EMIT_OUT;end end
  EMIT_OUT:if(out_ready_i)begin if(out_last_o)st<=DONE;else begin rank_q<=rank_q+1'b1;st<=EMIT_REQ;end end
  DONE:st<=IDLE;default:st<=IDLE;endcase end
endmodule

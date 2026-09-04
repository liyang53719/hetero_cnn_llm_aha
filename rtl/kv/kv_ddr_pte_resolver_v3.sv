// SPDX-License-Identifier: Apache-2.0
module kv_ddr_pte_resolver_v3(
 input logic clk_i,rst_ni,input logic start_i,output logic ready_o,input logic allocate_on_miss_i,free_i,
 input logic[63:0]table_base_i,input logic[9:0]root_index_i,leaf_index_i,input logic[31:0]generation_i,physical_page_limit_i,input logic[7:0]format_i,
 output logic ddr_req_valid_o,input logic ddr_req_ready_i,output logic ddr_req_write_o,output logic[63:0]ddr_req_addr_o,output logic[127:0]ddr_req_wdata_o,output logic[15:0]ddr_req_wstrb_o,
 input logic ddr_rsp_valid_i,output logic ddr_rsp_ready_o,input logic[127:0]ddr_rsp_rdata_i,input logic ddr_rsp_error_i,
 output logic page_req_valid_o,input logic page_req_ready_i,output logic page_req_free_o,output logic[31:0]page_req_id_o,
 input logic page_rsp_valid_i,output logic page_rsp_ready_o,input logic[31:0]page_rsp_id_i,input logic page_rsp_error_i,
 output logic done_o,output logic[7:0]status_o,output logic[31:0]data_page_o);
 localparam logic[7:0]OK=0,PROTOCOL=7,OOM=8,STALE=9,INVARIANT=10;
 localparam logic[3:0]IDLE=0,ROOT_REQ=1,ROOT_RSP=2,ALLOC_LEAF_REQ=3,ALLOC_LEAF_RSP=4,ROOT_WRITE_REQ=5,ROOT_WRITE_RSP=6,LEAF_REQ=7,LEAF_RSP=8,ALLOC_DATA_REQ=9,ALLOC_DATA_RSP=10,LEAF_WRITE_REQ=11,LEAF_WRITE_RSP=12,FREE_REQ=13,FREE_RSP=14,DONE=15;
 logic[3:0]st;logic alloc_q,free_q;logic[63:0]table_q;logic[9:0]root_q,leaf_q;logic[31:0]gen_q,limit_q,leaf_page_q,data_page_q,refcount_q;logic[7:0]format_q;logic write_root_q;
 logic root_valid,leaf_valid;logic[31:0]pte_page,pte_generation,pte_refcount;logic[15:0]pte_flags;logic[7:0]pte_format;
 assign pte_page=ddr_rsp_rdata_i[31:0];assign pte_generation=ddr_rsp_rdata_i[63:32];assign pte_refcount=ddr_rsp_rdata_i[95:64];assign pte_flags=ddr_rsp_rdata_i[111:96];assign pte_format=ddr_rsp_rdata_i[119:112];assign root_valid=pte_flags[0];assign leaf_valid=pte_flags[0];
 assign ready_o=st==IDLE;assign done_o=st==DONE;assign data_page_o=data_page_q;
 assign ddr_req_valid_o=st inside{ROOT_REQ,ROOT_WRITE_REQ,LEAF_REQ,LEAF_WRITE_REQ};assign ddr_req_write_o=st inside{ROOT_WRITE_REQ,LEAF_WRITE_REQ};
 assign ddr_req_addr_o=(st inside{ROOT_REQ,ROOT_WRITE_REQ})?table_q+{50'd0,root_q,4'b0}:table_q+64'd16384+{28'd0,leaf_page_q,14'b0}+{50'd0,leaf_q,4'b0};
 assign ddr_req_wdata_o=write_root_q?{8'd0,8'd0,16'h0001,32'd1,gen_q,leaf_page_q}:{8'd0,format_q,(free_q?16'd0:16'h0001),(free_q?32'd0:32'd1),(free_q?32'd0:gen_q),(free_q?32'd0:data_page_q)};
 assign ddr_req_wstrb_o=16'hffff;assign ddr_rsp_ready_o=st inside{ROOT_RSP,ROOT_WRITE_RSP,LEAF_RSP,LEAF_WRITE_RSP};
 assign page_req_valid_o=st inside{ALLOC_LEAF_REQ,ALLOC_DATA_REQ,FREE_REQ};assign page_req_free_o=st==FREE_REQ;assign page_req_id_o=data_page_q;assign page_rsp_ready_o=st inside{ALLOC_LEAF_RSP,ALLOC_DATA_RSP,FREE_RSP};
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;alloc_q<=0;free_q<=0;table_q<=0;root_q<=0;leaf_q<=0;gen_q<=0;limit_q<=0;format_q<=0;leaf_page_q<=0;data_page_q<=0;refcount_q<=0;write_root_q<=0;status_o<=0;end else case(st)
  IDLE:if(start_i)begin alloc_q<=allocate_on_miss_i;free_q<=free_i;table_q<=table_base_i;root_q<=root_index_i;leaf_q<=leaf_index_i;gen_q<=generation_i;limit_q<=physical_page_limit_i;format_q<=format_i;status_o<=OK;write_root_q<=0;st<=ROOT_REQ;end
  ROOT_REQ:if(ddr_req_ready_i)st<=ROOT_RSP;
  ROOT_RSP:if(ddr_rsp_valid_i)begin if(ddr_rsp_error_i)begin status_o<=PROTOCOL;st<=DONE;end else if(root_valid)begin if(pte_generation!=gen_q)begin status_o<=STALE;st<=DONE;end else begin leaf_page_q<=pte_page;st<=LEAF_REQ;end end else if(alloc_q)st<=ALLOC_LEAF_REQ;else begin status_o<=STALE;st<=DONE;end end
  ALLOC_LEAF_REQ:if(page_req_ready_i)st<=ALLOC_LEAF_RSP;
  ALLOC_LEAF_RSP:if(page_rsp_valid_i)begin if(page_rsp_error_i||page_rsp_id_i>=limit_q)begin status_o<=OOM;st<=DONE;end else begin leaf_page_q<=page_rsp_id_i;write_root_q<=1;st<=ROOT_WRITE_REQ;end end
  ROOT_WRITE_REQ:if(ddr_req_ready_i)st<=ROOT_WRITE_RSP;
  ROOT_WRITE_RSP:if(ddr_rsp_valid_i)begin if(ddr_rsp_error_i)begin status_o<=PROTOCOL;st<=DONE;end else begin write_root_q<=0;st<=LEAF_REQ;end end
  LEAF_REQ:if(ddr_req_ready_i)st<=LEAF_RSP;
  LEAF_RSP:if(ddr_rsp_valid_i)begin if(ddr_rsp_error_i)begin status_o<=PROTOCOL;st<=DONE;end else if(leaf_valid)begin data_page_q<=pte_page;refcount_q<=pte_refcount;if(pte_generation!=gen_q)begin status_o<=STALE;st<=DONE;end else if(free_q)begin if(pte_refcount!=1)begin status_o<=INVARIANT;st<=DONE;end else st<=FREE_REQ;end else st<=DONE;end else if(alloc_q)st<=ALLOC_DATA_REQ;else begin status_o<=STALE;st<=DONE;end end
  ALLOC_DATA_REQ:if(page_req_ready_i)st<=ALLOC_DATA_RSP;
  ALLOC_DATA_RSP:if(page_rsp_valid_i)begin if(page_rsp_error_i||page_rsp_id_i>=limit_q)begin status_o<=OOM;st<=DONE;end else begin data_page_q<=page_rsp_id_i;write_root_q<=0;st<=LEAF_WRITE_REQ;end end
  LEAF_WRITE_REQ:if(ddr_req_ready_i)st<=LEAF_WRITE_RSP;
  LEAF_WRITE_RSP:if(ddr_rsp_valid_i)begin if(ddr_rsp_error_i)status_o<=PROTOCOL;st<=DONE;end
  FREE_REQ:if(page_req_ready_i)st<=FREE_RSP;
  FREE_RSP:if(page_rsp_valid_i)begin if(page_rsp_error_i)begin status_o<=INVARIANT;st<=DONE;end else begin free_q<=1;write_root_q<=0;st<=LEAF_WRITE_REQ;end end
  DONE:st<=IDLE;default:st<=IDLE;endcase end
endmodule

// SPDX-License-Identifier: Apache-2.0
// Algorithmic schema-v2 context to pinned Gemmini CUSTOM_3 micro-op emitter.
`timescale 1ns/1ps
module gemmini_descriptor_v2_emitter(
  input logic clk_i,input logic rst_ni,
  input logic context_valid_i,output logic context_ready_o,
  input logic context_legal_i,input logic[7:0] context_status_i,
  input logic[127:0] context_command_i,
  input logic[4*64-1:0] tensor_addr_i,input logic[4*4*18-1:0] tensor_shape_i,
  input logic[4*3*24-1:0] tensor_stride_i,input logic[4*12-1:0] tensor_meta_i,
  input logic[71:0] matrix_op_payload_i,input logic[71:0] matrix_aux_payload_i,
  input logic conv_valid_i,input logic[71:0] conv_payload_i,
  input logic[1:0] quant_valid_i,input logic[2*72-1:0] quant_payload_i,
  output logic scale_req_valid_o,input logic scale_req_ready_i,
  output logic[47:0] scale_req_addr_o,input logic scale_rsp_valid_i,
  output logic scale_rsp_ready_o,input logic[31:0] scale_rsp_data_i,input logic scale_rsp_error_i,
  output logic op_valid_o,input logic op_ready_i,output logic op_first_o,output logic op_last_o,
  output logic op_legal_o,output logic[7:0] op_status_o,output logic[15:0] op_event_id_o,
  output logic[6:0] op_funct_o,output logic[63:0] op_rs1_o,output logic[63:0] op_rs2_o
);
  localparam logic[7:0] ST_OK=0,ST_MALFORMED=2,ST_FETCH=3,ST_UNSUPPORTED=4,ST_RANGE=5;
  localparam logic[2:0] MODE_SINGLE_OS=0,MODE_MULTI_OS=1,MODE_WS=2,MODE_CONV=3;
  typedef enum logic[2:0]{S_IDLE,S_VALIDATE,S_SCALE_REQ,S_SCALE_RSP,S_EMIT,S_REJECT}state_e;
  state_e state_q;
  /* verilator lint_off UNUSEDSIGNAL */
  logic[127:0] command_q;logic[255:0] addr_q;logic[287:0] shape_q,stride_q;
  logic[47:0] meta_q;logic[71:0] mop_q,aux_q,conv_q;logic[143:0] quant_q;
  logic[1:0] quant_valid_q;logic conv_valid_q;logic[2:0] mode_q;
  /* verilator lint_on UNUSEDSIGNAL */
  logic[7:0] status_q;logic[7:0] op_index_q,op_count_q;
  logic[31:0] scale_bits_q;
  logic context_semantic_legal,has_bias;
  logic[15:0] m,n;logic[23:0] k;
  logic[15:0] itiles,jtiles,ktiles;logic[15:0] pad_i,pad_j,pad_k;
  logic[31:0] os_count_wide;
  logic[134:0] selected_op;

  function automatic logic[63:0] pack_shape(input logic[31:0]local_addr,
                                             input logic[15:0]cols,input logic[15:0]rows);
    pack_shape={rows,cols,local_addr};
  endfunction
  function automatic logic[63:0] ld_rs1(input logic[1:0]channel);
    ld_rs1=64'h3f80_0000_0010_0101|({62'd0,channel}<<3);
  endfunction
  /* verilator lint_off WIDTHEXPAND */
  /* verilator lint_off WIDTHTRUNC */
  function automatic logic[134:0] os_program(input logic[7:0]which);
    integer cursor,ii,jj,kk;logic[6:0]f;logic[63:0]r1,r2;
    logic[31:0]local_a,local_b,local_c,local_d,b_start;
    logic[15:0]rows,cols,a_cols,b_cols,b_rows;
    begin
      cursor=0;f=0;r1=0;r2=0;b_start=32'd16384-ktiles*jtiles*16;
      if(which==cursor)begin f=0;r1=64'h3f80_0000_0001_0000;r2=64'h0001_0000_0000_0000;end cursor++;
      if(which==cursor)begin f=0;r1=2;r2={32'h3f80_0000,8'd0,stride_q[144 +: 24]};end cursor++;
      if(which==cursor)begin f=0;r1=ld_rs1(0);r2={40'd0,stride_q[0 +: 24]};end cursor++;
      if(which==cursor)begin f=0;r1=ld_rs1(1);r2={40'd0,stride_q[72 +: 24]};end cursor++;
      if(which==cursor)begin f=0;r1=ld_rs1(2);r2={40'd0,stride_q[216 +: 24]};end cursor++;
      if(which==cursor)begin f=0;r1=ld_rs1(0);r2={40'd0,stride_q[216 +: 24]};end cursor++;
      for(ii=0;ii<4;ii++)for(jj=0;jj<4;jj++)if(ii<itiles&&jj<jtiles)begin
        rows=16-((ii==itiles-1)?pad_i:0);cols=16-((jj==jtiles-1)?pad_j:0);
        local_d=32'h80000000+(ii*jtiles+jj)*16;
        if(which==cursor)begin f=2;r1=addr_q[192 +: 64]+(ii*(stride_q[216 +: 24]>>2)+jj)*64;
          r2=pack_shape(local_d,cols,rows);end cursor++;
      end
      if(which==cursor)begin f=0;r1=ld_rs1(0);r2={40'd0,stride_q[72 +: 24]};end cursor++;
      for(kk=0;kk<4;kk++)if(kk<ktiles)begin
        rows=16-((kk==ktiles-1)?pad_k:0);cols=jtiles*16-pad_j;local_b=b_start+kk*jtiles*16;
        if(which==cursor)begin f=2;r1=addr_q[64 +: 64]+kk*16*stride_q[72 +: 24];r2=pack_shape(local_b,cols,rows);end cursor++;
      end
      if(which==cursor)begin f=0;r1=ld_rs1(0);r2={40'd0,stride_q[0 +: 24]};end cursor++;
      for(ii=0;ii<4;ii++)if(ii<itiles)begin
        rows=16-((ii==itiles-1)?pad_i:0);cols=ktiles*16-pad_k;local_a=ii*ktiles*16;
        if(which==cursor)begin f=2;r1=addr_q[0 +: 64]+ii*16*stride_q[0 +: 24];r2=pack_shape(local_a,cols,rows);end cursor++;
      end
      for(ii=0;ii<4;ii++)for(jj=0;jj<4;jj++)for(kk=0;kk<4;kk++)
        if(ii<itiles&&jj<jtiles&&kk<ktiles)begin
          rows=16-((ii==itiles-1)?pad_i:0);b_cols=16-((jj==jtiles-1)?pad_j:0);
          a_cols=16-((kk==ktiles-1)?pad_k:0);b_rows=a_cols;
          local_a=(ii*ktiles+kk)*16;local_b=b_start+(kk*jtiles+jj)*16;
          local_c=kk==ktiles-1?32'hc0000000+(ii*jtiles+jj)*16:32'hffffffff;
          if(which==cursor)begin f=6;r1=pack_shape(32'hffffffff,16,16);r2=pack_shape(local_c,b_cols,rows);end cursor++;
          if(which==cursor)begin f=kk==0?4:5;r1=pack_shape(local_a,a_cols,rows);r2=pack_shape(local_b,b_cols,b_rows);end cursor++;
        end
      for(ii=0;ii<4;ii++)for(jj=0;jj<4;jj++)if(ii<itiles&&jj<jtiles)begin
        rows=16-((ii==itiles-1)?pad_i:0);cols=16-((jj==jtiles-1)?pad_j:0);
        local_c=32'hc0000000+(ii*jtiles+jj)*16;
        if(which==cursor)begin f=3;r1=addr_q[128 +: 64]+(ii*stride_q[144 +: 24]+jj)*16;
          r2=pack_shape(local_c,cols,rows);end cursor++;
      end
      os_program={f,r1,r2};
    end
  endfunction
  /* verilator lint_on WIDTHEXPAND */
  /* verilator lint_on WIDTHTRUNC */

  assign m=mop_q[15:0];assign n=mop_q[31:16];assign k=mop_q[55:32];
  assign itiles=(m+16'd15)>>4;assign jtiles=(n+16'd15)>>4;
  assign ktiles=(k[15:0]+16'd15)>>4;
  assign pad_i=itiles*16'd16-m;assign pad_j=jtiles*16'd16-n;
  assign pad_k=ktiles*16'd16-k[15:0];
  assign os_count_wide=32'd8+{16'd0,itiles}*{16'd0,jtiles}+{16'd0,ktiles}+
    {16'd0,itiles}+32'd2*{16'd0,itiles}*{16'd0,jtiles}*{16'd0,ktiles}+
    {16'd0,itiles}*{16'd0,jtiles};
  assign has_bias=aux_q[23:0]!=24'hffffff;
  assign context_semantic_legal=m!=0&&n!=0&&k!=0&&itiles<=4&&jtiles<=4&&ktiles<=4&&
    os_count_wide<=32'd255&&
    meta_q[3:0]==1&&meta_q[15:12]==1&&meta_q[27:24]==1&&
    meta_q[7:4]==0&&meta_q[19:16]==0&&meta_q[31:28]==0&&
    stride_q[23:0]!=0&&stride_q[95:72]!=0&&stride_q[167:144]!=0;
  assign context_ready_o=state_q==S_IDLE;
  assign scale_req_valid_o=state_q==S_SCALE_REQ;assign scale_req_addr_o=quant_q[72 +: 48];
  assign scale_rsp_ready_o=state_q==S_SCALE_RSP;
  assign op_valid_o=state_q==S_EMIT||state_q==S_REJECT;
  assign op_first_o=state_q==S_REJECT||op_index_q==0;
  assign op_last_o=state_q==S_REJECT||op_index_q+1'b1==op_count_q;
  assign op_legal_o=state_q==S_EMIT;assign op_status_o=status_q;
  assign op_event_id_o=command_q[55:40];

  always_comb begin
    selected_op='0;
    if(mode_q==MODE_MULTI_OS)selected_op=os_program(op_index_q);
    else if(mode_q==MODE_WS)case(op_index_q)
      0:selected_op={7'd0,64'h3f80_0000_0001_0004,64'h0001_0000_0000_0000};
      1:selected_op={7'd0,64'd2,{32'h3f80_0000,8'd0,stride_q[144 +: 24]}};
      2:selected_op={7'd0,ld_rs1(0),{40'd0,stride_q[0 +: 24]}};
      3:selected_op={7'd0,ld_rs1(1),{40'd0,stride_q[72 +: 24]}};
      4:selected_op={7'd0,ld_rs1(2),has_bias?{40'd0,stride_q[216 +: 24]}:64'd0};
      5:selected_op={7'd9,{16'd0,pad_k,pad_j,pad_i},{16'd0,ktiles,jtiles,itiles}};
      6:selected_op={7'd10,addr_q[0 +: 64],addr_q[64 +: 64]};
      7:selected_op={7'd11,has_bias?addr_q[192 +: 64]:64'd0,addr_q[128 +: 64]};
      8:selected_op={7'd12,{40'd0,stride_q[0 +: 24]},{40'd0,stride_q[72 +: 24]}};
      9:selected_op={7'd13,has_bias?{40'd0,(stride_q[216 +: 24]>>2)}:64'd0,{40'd0,stride_q[144 +: 24]}};
      default:selected_op={7'd8,
        ({62'd0,aux_q[39:38]}<<18)|({62'd0,aux_q[41:40]}<<16)|
        ({62'd0,aux_q[25:24]}<<8)|({63'd0,aux_q[27]}<<2)|
        ({63'd0,aux_q[26]}<<1)|{63'd0,mop_q[60]},
        ({63'd0,mop_q[59]}<<1)|{63'd0,mop_q[58]}};
    endcase
    else if(mode_q==MODE_CONV)case(op_index_q)
      0:selected_op={7'd0,({62'd0,aux_q[25:24]}<<2)|64'd2,
                     {scale_bits_q,{14'd0,shape_q[198 +: 18]}}};
      1:selected_op={7'd0,64'h0000_0000_0001_0004,64'h0001_0000_0000_0000};
      2:selected_op={7'd16,
        ({46'd0,shape_q[198 +: 18]}<<48)|({46'd0,shape_q[54 +: 18]}<<32)|
        ({46'd0,shape_q[18 +: 18]}<<16)|{46'd0,shape_q[0 +: 18]},
        ({58'd0,conv_q[53:48]}<<56)|({56'd0,conv_q[23:16]}<<48)|
        ({46'd0,shape_q[180 +: 18]}<<32)|({46'd0,shape_q[162 +: 18]}<<16)|
        {46'd0,shape_q[162 +: 18]}};
      3:selected_op={7'd17,
        ({56'd0,conv_q[15:8]}<<48)|({46'd0,shape_q[180 +: 18]}<<32)|
        (64'd1<<16)|(64'd1<<8),
        ({46'd0,shape_q[0 +: 18]}<<48)|({46'd0,shape_q[162 +: 18]}<<32)|
        ({46'd0,shape_q[180 +: 18]}<<16)|{46'd0,shape_q[198 +: 18]}};
      4:selected_op={7'd18,
        ({56'd0,conv_q[7:0]}<<48)|({56'd0,conv_q[15:8]}<<32)|
        ({46'd0,shape_q[54 +: 18]}<<16)|{58'd0,conv_q[59:54]},
        ({58'd0,aux_q[61:56]}<<48)|({58'd0,conv_q[53:48]}<<32)|
        ({58'd0,aux_q[55:50]}<<24)|{46'd0,shape_q[36 +: 18]}};
      5:selected_op={7'd19,
        ({46'd0,shape_q[162 +: 18]}<<48)|{56'd0,conv_q[39:32]},
        ({46'd0,shape_q[54 +: 18]}<<48)|({46'd0,shape_q[198 +: 18]}<<32)|
        ({46'd0,shape_q[198 +: 18]}<<16)|{46'd0,shape_q[180 +: 18]}};
      6:selected_op={7'd20,addr_q[64 +: 64],addr_q[128 +: 64]};
      7:selected_op={7'd21,addr_q[192 +: 64],addr_q[0 +: 64]};
      default:selected_op={7'd15,
        ({62'd0,aux_q[39:38]}<<18)|({62'd0,aux_q[41:40]}<<16)|
        ({56'd0,aux_q[49:42]}<<8)|({63'd0,aux_q[37]}<<6)|
        ({63'd0,aux_q[36]}<<5)|({63'd0,aux_q[35]}<<4)|
        ({63'd0,aux_q[34]}<<3)|({63'd0,aux_q[33]}<<2)|({63'd0,aux_q[32]}<<1),
        ({62'd0,aux_q[25:24]}<<3)|({63'd0,aux_q[31]}<<2)|
        ({63'd0,aux_q[30]}<<1)|{63'd0,aux_q[29]}};
    endcase
    else case(op_index_q)
      0:selected_op={7'd0,64'h3f80_0000_0001_0000,64'h0001_0000_0000_0000};
      1:selected_op={7'd0,64'd2,{32'h3f80_0000,8'd0,stride_q[144 +: 24]}};
      2:selected_op={7'd0,ld_rs1(0),{40'd0,stride_q[0 +: 24]}};
      3:selected_op={7'd2,addr_q[0 +: 64],pack_shape(0,k[15:0],m)};
      4:selected_op={7'd0,ld_rs1(0),{40'd0,stride_q[72 +: 24]}};
      5:selected_op={7'd2,addr_q[64 +: 64],pack_shape(16,n,k[15:0])};
      6:selected_op={7'd6,pack_shape(32'hffffffff,16,16),pack_shape(48,n,m)};
      7:selected_op={7'd4,pack_shape(0,k[15:0],m),pack_shape(16,n,k[15:0])};
      default:selected_op={7'd3,addr_q[128 +: 64],pack_shape(48,n,m)};
    endcase
  end
  assign {op_funct_o,op_rs1_o,op_rs2_o}=selected_op;

  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin state_q<=S_IDLE;command_q<=0;addr_q<=0;shape_q<=0;stride_q<=0;
      meta_q<=0;mop_q<=0;aux_q<=0;conv_q<=0;quant_q<=0;quant_valid_q<=0;
      conv_valid_q<=0;mode_q<=0;status_q<=ST_OK;op_index_q<=0;op_count_q<=0;
      scale_bits_q<=32'h3f800000;
    end else case(state_q)
      S_IDLE:if(context_valid_i&&context_ready_o)begin
        command_q<=context_command_i;addr_q<=tensor_addr_i;shape_q<=tensor_shape_i;
        stride_q<=tensor_stride_i;meta_q<=tensor_meta_i;mop_q<=matrix_op_payload_i;
        aux_q<=matrix_aux_payload_i;conv_q<=conv_payload_i;quant_q<=quant_payload_i;
        quant_valid_q<=quant_valid_i;conv_valid_q<=conv_valid_i;op_index_q<=0;
        scale_bits_q<=32'h3f800000;status_q<=context_status_i;
        if(!context_legal_i)state_q<=S_REJECT;else state_q<=S_VALIDATE;
      end
      S_VALIDATE:begin
        if(!context_semantic_legal)begin status_q<=ST_RANGE;state_q<=S_REJECT;end
        else if(aux_q[25:24]>1)begin status_q<=ST_UNSUPPORTED;state_q<=S_REJECT;end
        else if(command_q[7:0]==8'h22)begin
          mode_q<=MODE_CONV;op_count_q<=9;
          if(!conv_valid_q||mop_q[57:56]!=1||aux_q[29]!=1||
             !has_bias)begin status_q<=ST_UNSUPPORTED;state_q<=S_REJECT;end
          else if(mop_q[63:61]!=0)begin
            if(!quant_valid_q[1])begin status_q<=ST_MALFORMED;state_q<=S_REJECT;end
            else state_q<=S_SCALE_REQ;
          end else state_q<=S_EMIT;
        end else if(mop_q[57:56]==1)begin
          mode_q<=MODE_WS;op_count_q<=11;state_q<=S_EMIT;
        end else if(has_bias)begin
          mode_q<=MODE_MULTI_OS;
          op_count_q<=os_count_wide[7:0];
          state_q<=S_EMIT;
        end else if(itiles==1&&jtiles==1&&ktiles==1)begin
          mode_q<=MODE_SINGLE_OS;op_count_q<=9;state_q<=S_EMIT;
        end else begin status_q<=ST_UNSUPPORTED;state_q<=S_REJECT;end
      end
      S_SCALE_REQ:if(scale_req_valid_o&&scale_req_ready_i)state_q<=S_SCALE_RSP;
      S_SCALE_RSP:if(scale_rsp_valid_i&&scale_rsp_ready_o)begin
        if(scale_rsp_error_i)begin status_q<=ST_FETCH;state_q<=S_REJECT;end
        else begin scale_bits_q<=scale_rsp_data_i;state_q<=S_EMIT;end
      end
      S_EMIT:if(op_valid_o&&op_ready_i)begin
        if(op_index_q+1'b1==op_count_q)state_q<=S_IDLE;else op_index_q<=op_index_q+1'b1;
      end
      S_REJECT:if(op_valid_o&&op_ready_i)state_q<=S_IDLE;
      default:state_q<=S_IDLE;
    endcase
  end
endmodule

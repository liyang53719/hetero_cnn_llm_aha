// SPDX-License-Identifier: Apache-2.0
// One-tile INT8 max-pool and saturating residual-add production SFU.
`timescale 1ns/1ps
module int8_pool_residual_sfu (
  input logic clk_i,input logic rst_ni,
  input logic cfg_valid_i,output logic cfg_ready_o,input logic cfg_op_i,
  input logic[3:0]cfg_h_i,input logic[3:0]cfg_w_i,input logic[4:0]cfg_c_i,
  input logic[6:0]cfg_bytes_i,input logic[15:0]cfg_tag_i,
  input logic[11:0]cfg_tensor_id_i,input logic[3:0]cfg_format_i,
  input logic primary_valid_i,output logic primary_ready_o,
  input logic[511:0]primary_data_i,input logic[63:0]primary_be_i,
  input logic primary_last_i,input logic[3:0]primary_format_i,
  input logic secondary_valid_i,output logic secondary_ready_o,
  input logic[511:0]secondary_data_i,input logic[63:0]secondary_be_i,
  input logic secondary_last_i,input logic[3:0]secondary_format_i,
  output logic out_valid_o,input logic out_ready_i,output logic[511:0]out_data_o,
  output logic[63:0]out_be_o,output logic[15:0]out_tag_o,
  output logic[11:0]out_tensor_id_o,output logic out_last_o,
  output logic[3:0]out_format_o,output logic transfer_done_o,
  output logic[31:0]protocol_error_count_o
);
  localparam logic OP_RESIDUAL=1'b0,OP_MAXPOOL=1'b1;
  logic active_q,op_q,have_primary_q,have_secondary_q,out_valid_q;
  logic[3:0]h_q,w_q;logic[4:0]c_q;logic[6:0]bytes_q;
  logic[15:0]tag_q;logic[11:0]tensor_q;logic[3:0]format_q;
  logic[511:0]primary_q,secondary_q,result_d,result_q;logic[63:0]primary_be_q,secondary_be_q,result_be_d,result_be_q;
  logic operands_ready;integer byte_index,oh,ow,ch;integer input_index0,input_index1,input_index2,input_index3,output_index;
  logic signed[8:0]sum_value;logic signed[7:0]pool_value,pool_candidate;
  assign cfg_ready_o=!active_q&&!out_valid_q;
  assign primary_ready_o=active_q&&!have_primary_q&&!out_valid_q;
  assign secondary_ready_o=active_q&&op_q==OP_RESIDUAL&&!have_secondary_q&&!out_valid_q;
  assign operands_ready=have_primary_q&&(op_q==OP_MAXPOOL||have_secondary_q);
  assign out_valid_o=out_valid_q;assign out_data_o=result_q;assign out_be_o=result_be_q;
  assign out_tag_o=tag_q;assign out_tensor_id_o=tensor_q;assign out_last_o=1'b1;assign out_format_o=format_q;
  always_comb begin
    result_d='0;result_be_d='0;sum_value='0;pool_value='0;pool_candidate='0;
    input_index0=0;input_index1=0;input_index2=0;input_index3=0;output_index=0;
    if(op_q==OP_RESIDUAL)begin
      for(byte_index=0;byte_index<64;byte_index++)if(byte_index<bytes_q)begin
        sum_value=$signed(primary_q[byte_index*8 +:8])+$signed(secondary_q[byte_index*8 +:8]);
        if(sum_value>9'sd127)result_d[byte_index*8 +:8]=8'h7f;
        else if(sum_value< -9'sd128)result_d[byte_index*8 +:8]=8'h80;
        else result_d[byte_index*8 +:8]=sum_value[7:0];
        result_be_d[byte_index]=primary_be_q[byte_index]&&secondary_be_q[byte_index];
      end
    end else begin
      for(oh=0;oh<4;oh++)for(ow=0;ow<4;ow++)for(ch=0;ch<16;ch++)
        if(oh<32'(h_q)/2&&ow<32'(w_q)/2&&ch<32'(c_q))begin
          input_index0=((2*oh)*w_q+2*ow)*c_q+ch;
          input_index1=input_index0+32'(c_q);input_index2=input_index0+32'(w_q)*32'(c_q);
          input_index3=input_index2+32'(c_q);
          pool_value=$signed(primary_q[input_index0*8 +:8]);
          pool_candidate=$signed(primary_q[input_index1*8 +:8]);if(pool_candidate>pool_value)pool_value=pool_candidate;
          pool_candidate=$signed(primary_q[input_index2*8 +:8]);if(pool_candidate>pool_value)pool_value=pool_candidate;
          pool_candidate=$signed(primary_q[input_index3*8 +:8]);if(pool_candidate>pool_value)pool_value=pool_candidate;
          output_index=(oh*(32'(w_q)/2)+ow)*32'(c_q)+ch;result_d[output_index*8 +:8]=pool_value;
          result_be_d[output_index]=primary_be_q[input_index0]&&primary_be_q[input_index1]&&
            primary_be_q[input_index2]&&primary_be_q[input_index3];
        end
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin active_q<=0;op_q<=0;have_primary_q<=0;have_secondary_q<=0;out_valid_q<=0;
      h_q<=0;w_q<=0;c_q<=0;bytes_q<=0;tag_q<=0;tensor_q<=0;format_q<=0;
      primary_q<=0;secondary_q<=0;primary_be_q<=0;secondary_be_q<=0;result_q<=0;result_be_q<=0;
      transfer_done_o<=0;protocol_error_count_o<=0;
    end else begin transfer_done_o<=0;
      if(cfg_valid_i&&cfg_ready_o)begin
        op_q<=cfg_op_i;h_q<=cfg_h_i;w_q<=cfg_w_i;c_q<=cfg_c_i;bytes_q<=cfg_bytes_i;
        tag_q<=cfg_tag_i;tensor_q<=cfg_tensor_id_i;format_q<=cfg_format_i;
        have_primary_q<=0;have_secondary_q<=0;
        if(cfg_format_i!=1||cfg_bytes_i==0||cfg_bytes_i>64||
          (cfg_op_i==OP_MAXPOOL&&(cfg_h_i==0||cfg_w_i==0||cfg_c_i==0||cfg_c_i>16||
           cfg_h_i[0]||cfg_w_i[0]||cfg_h_i>8||cfg_w_i>8||cfg_h_i*cfg_w_i*cfg_c_i>64)))begin
          protocol_error_count_o<=protocol_error_count_o+1'b1;active_q<=0;
        end else active_q<=1;
      end
      if(primary_valid_i&&primary_ready_o)begin primary_q<=primary_data_i;primary_be_q<=primary_be_i;have_primary_q<=1;
        if(!primary_last_i||primary_format_i!=1)protocol_error_count_o<=protocol_error_count_o+1'b1;end
      if(secondary_valid_i&&secondary_ready_o)begin secondary_q<=secondary_data_i;secondary_be_q<=secondary_be_i;have_secondary_q<=1;
        if(!secondary_last_i||secondary_format_i!=1)protocol_error_count_o<=protocol_error_count_o+1'b1;end
      if(active_q&&!out_valid_q&&operands_ready)begin result_q<=result_d;result_be_q<=result_be_d;out_valid_q<=1;end
      if(out_valid_q&&out_ready_i)begin out_valid_q<=0;active_q<=0;have_primary_q<=0;have_secondary_q<=0;transfer_done_o<=1;end
    end
  end
endmodule

module ggml_operand_group_decode #(
  parameter int PAYLOAD_BYTES = 210
) (
  input  logic [1:0] format_i,
  input  logic [3:0] group_index_i,
  input  logic [7:0] fp16_element_count_i,
  input  logic [PAYLOAD_BYTES*8-1:0] block_payload_i,
  output logic format_valid_o,
  output logic integer_mode_o,
  output logic [4:0] valid_count_o,
  output logic signed [7:0] quant_o [0:15],
  output logic [15:0] fp16_o [0:15],
  output logic [15:0] block_scale_fp16_o,
  output logic signed [7:0] subscale_s8_o,
  output logic last_o
);
  localparam logic [1:0] FORMAT_FP16=2'd0, FORMAT_Q8_0=2'd1, FORMAT_Q6_K=2'd2, FORMAT_Q3_K=2'd3;
  function automatic logic [7:0] byte_at(input int unsigned index); byte_at=block_payload_i[index*8 +: 8]; endfunction
  function automatic logic signed [7:0] q3_scale_at(input int unsigned index);
    int unsigned j; logic [3:0] low; logic [1:0] high; logic [5:0] raw; logic [7:0] base_byte,temp_byte;
    begin
      j=0;low='0;high='0;base_byte='0;temp_byte='0;
      if(index<4) begin j=index;base_byte=byte_at(96+j);temp_byte=byte_at(104+j);low=base_byte[3:0];high=temp_byte[5:4]; end
      else if(index<8) begin j=index-4;base_byte=byte_at(100+j);temp_byte=byte_at(104+j);low=base_byte[3:0];high=temp_byte[7:6]; end
      else if(index<12) begin j=index-8;base_byte=byte_at(96+j);temp_byte=byte_at(104+j);low=base_byte[7:4];high=temp_byte[1:0]; end
      else begin j=index-12;base_byte=byte_at(100+j);temp_byte=byte_at(104+j);low=base_byte[7:4];high=temp_byte[3:2]; end
      raw={high,low}; q3_scale_at=$signed({2'b00,raw})-8'sd32;
    end
  endfunction
  function automatic logic signed [7:0] q6_quant_at(input int unsigned index);
    int unsigned half,rem,group32,lane,ql_base,qh_base;logic [7:0] high_bits,low_byte;logic [5:0] raw;
    begin
      half=index/128;rem=index%128;group32=rem/32;lane=rem%32;ql_base=half*64;qh_base=128+half*32;high_bits=byte_at(qh_base+lane);low_byte=(group32==0||group32==2)?byte_at(ql_base+lane):byte_at(ql_base+lane+32);
      case(group32) 0:raw={high_bits[1:0],low_byte[3:0]};1:raw={high_bits[3:2],low_byte[3:0]};2:raw={high_bits[5:4],low_byte[7:4]};default:raw={high_bits[7:6],low_byte[7:4]};endcase
      q6_quant_at=$signed({2'b00,raw})-8'sd32;
    end
  endfunction
  function automatic logic signed [7:0] q6_subscale_at(input int unsigned index);
    int unsigned half,rem,group32,lane,scale_index;
    begin half=index/128;rem=index%128;group32=rem/32;lane=rem%32;scale_index=half*8+lane/16+2*group32;q6_subscale_at=$signed(byte_at(192+scale_index));end
  endfunction
  function automatic logic signed [7:0] q3_quant_at(input int unsigned index);
    int unsigned half,rem,group32,lane;logic [1:0] low;logic high;
    begin half=index/128;rem=index%128;group32=rem/32;lane=rem%32;low=(byte_at(32+half*32+lane)>>(2*group32))&2'b11;high=byte_at(lane)[half*4+group32];q3_quant_at=high?$signed({6'b0,low}):($signed({6'b0,low})-8'sd4);end
  endfunction
  integer lane;int unsigned element_index;int signed remaining;
  always_comb begin
    format_valid_o=1'b1;integer_mode_o=1'b1;valid_count_o=5'd16;block_scale_fp16_o=16'h3c00;subscale_s8_o=8'sd1;last_o=1'b0;
    for(lane=0;lane<16;lane++) begin quant_o[lane]=8'sd0;fp16_o[lane]=16'd0;end
    case(format_i)
      FORMAT_FP16: begin
        integer_mode_o=1'b0;remaining=$signed({1'b0,fp16_element_count_i})-$signed({1'b0,group_index_i,4'b0});
        if((fp16_element_count_i==0)||(remaining<=0)||((group_index_i*16)>=PAYLOAD_BYTES/2)) begin format_valid_o=1'b0;valid_count_o=5'd0;end
        else begin valid_count_o=remaining>=16?5'd16:remaining[4:0];for(lane=0;lane<16;lane++) begin element_index=group_index_i*16+lane;if(lane<valid_count_o)fp16_o[lane]={byte_at(element_index*2+1),byte_at(element_index*2)};end last_o=remaining<=16;end
      end
      FORMAT_Q8_0: begin if(group_index_i>=2) begin format_valid_o=1'b0;valid_count_o=5'd0;end else begin block_scale_fp16_o={byte_at(1),byte_at(0)};for(lane=0;lane<16;lane++)quant_o[lane]=$signed(byte_at(2+group_index_i*16+lane));last_o=group_index_i==1;end end
      FORMAT_Q6_K: begin if(group_index_i>=16) begin format_valid_o=1'b0;valid_count_o=5'd0;end else begin block_scale_fp16_o={byte_at(209),byte_at(208)};subscale_s8_o=q6_subscale_at(group_index_i*16);for(lane=0;lane<16;lane++)quant_o[lane]=q6_quant_at(group_index_i*16+lane);last_o=group_index_i==15;end end
      FORMAT_Q3_K: begin if(group_index_i>=16) begin format_valid_o=1'b0;valid_count_o=5'd0;end else begin block_scale_fp16_o={byte_at(109),byte_at(108)};subscale_s8_o=q3_scale_at(group_index_i);for(lane=0;lane<16;lane++)quant_o[lane]=q3_quant_at(group_index_i*16+lane);last_o=group_index_i==15;end end
      default: begin format_valid_o=1'b0;valid_count_o=5'd0;end
    endcase
  end
endmodule

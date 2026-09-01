// SPDX-License-Identifier: Apache-2.0
// Approved public tensor_base and SFU_PROGRAM record field decoder.
`timescale 1ns/1ps
module descriptor_public_record_decode(
  input  logic [127:0] record_i,
  output logic         recognized_o,
  output logic         legal_o,
  output logic [7:0]   status_o,
  output logic [55:0]  tensor_address_o,
  output logic [3:0]   tensor_dtype_o,
  output logic [3:0]   tensor_memory_space_o,
  output logic [3:0]   tensor_layout_o,
  output logic [3:0]   tensor_rank_o,
  output logic [15:0]  sfu_program_id_o,
  output logic [7:0]   sfu_input_count_o,
  output logic [7:0]   sfu_output_count_o,
  output logic [3:0]   sfu_input_dtype_o,
  output logic [3:0]   sfu_output_dtype_o,
  output logic [7:0]   sfu_lane_width_bits_o,
  output logic [7:0]   sfu_vector_lanes_o
);
  localparam logic [7:0] STATUS_OK=8'd0,STATUS_MALFORMED=8'd2,
                         STATUS_UNSUPPORTED=8'd4;
  logic common_legal,tensor_dtype_legal,sfu_input_dtype_legal,sfu_output_dtype_legal;

  function automatic logic dtype_legal(input logic[3:0] value);
    return value==4'd1||value==4'd4||value==4'd5||value==4'd6||value==4'd7;
  endfunction

  always_comb begin
    recognized_o=1'b1;legal_o=1'b0;status_o=STATUS_UNSUPPORTED;
    tensor_address_o={record_i[127:120],record_i[103:56]};
    tensor_memory_space_o=record_i[107:104];tensor_dtype_o=record_i[111:108];
    tensor_layout_o=record_i[115:112];tensor_rank_o=record_i[119:116];
    sfu_program_id_o=record_i[71:56];sfu_input_count_o=record_i[79:72];
    sfu_output_count_o=record_i[87:80];sfu_input_dtype_o=record_i[91:88];
    sfu_output_dtype_o=record_i[95:92];sfu_lane_width_bits_o=record_i[103:96];
    sfu_vector_lanes_o=record_i[111:104];
    common_legal=record_i[31:8]==24'd0;
    tensor_dtype_legal=dtype_legal(tensor_dtype_o);
    sfu_input_dtype_legal=dtype_legal(sfu_input_dtype_o);
    sfu_output_dtype_legal=dtype_legal(sfu_output_dtype_o);
    if(!common_legal)status_o=STATUS_MALFORMED;
    else case(record_i[7:0])
      8'h01:begin
        legal_o=tensor_memory_space_o==0&&tensor_layout_o==0&&
                tensor_rank_o>=4'd1&&tensor_rank_o<=4'd4&&tensor_dtype_legal;
        status_o=legal_o?STATUS_OK:STATUS_UNSUPPORTED;
      end
      8'h20:begin
        legal_o=(sfu_input_count_o==8'd1||sfu_input_count_o==8'd2)&&sfu_output_count_o==8'd1&&
                sfu_input_dtype_legal&&sfu_output_dtype_legal&&
                sfu_lane_width_bits_o==8'd16&&record_i[119:112]==0&&
                record_i[127:120]==0;
        status_o=legal_o?STATUS_OK:STATUS_UNSUPPORTED;
      end
      default:begin recognized_o=1'b0;status_o=STATUS_UNSUPPORTED;end
    endcase
  end
endmodule

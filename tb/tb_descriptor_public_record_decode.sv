`timescale 1ns/1ps
module tb_descriptor_public_record_decode;
  logic[127:0]r;logic recognized,legal;logic[7:0]status;logic[55:0]address;
  logic[3:0]dtype,space,layout,rank,idt,odt;logic[15:0]pid;logic[7:0]ic,oc,lane,vl;
  integer cases;
  descriptor_public_record_decode dut(.record_i(r),.recognized_o(recognized),.legal_o(legal),
    .status_o(status),.tensor_address_o(address),.tensor_dtype_o(dtype),
    .tensor_memory_space_o(space),.tensor_layout_o(layout),.tensor_rank_o(rank),
    .sfu_program_id_o(pid),.sfu_input_count_o(ic),.sfu_output_count_o(oc),
    .sfu_input_dtype_o(idt),.sfu_output_dtype_o(odt),.sfu_lane_width_bits_o(lane),
    .sfu_vector_lanes_o(vl));
  task automatic check(input logic exp_rec,input logic exp_legal,input logic[7:0]exp_status);
    #1;cases++;if(recognized!==exp_rec||legal!==exp_legal||status!==exp_status)
      $fatal(1,"case=%0d rec=%0d legal=%0d status=%0d",cases,recognized,legal,status);
  endtask
  function automatic[127:0]tensor(input[55:0]a,input[3:0]dt,input[3:0]rk);
    logic[127:0]w;begin w=0;w[7:0]=8'h01;w[103:56]=a[47:0];w[107:104]=0;
      w[111:108]=dt;w[115:112]=0;w[119:116]=rk;w[127:120]=a[55:48];return w;end
  endfunction
  function automatic[127:0]sfu(input[15:0]p,input[7:0]inputs,input[3:0]di,input[3:0]do_);
    logic[127:0]w;begin w=0;w[7:0]=8'h20;w[71:56]=p;w[79:72]=inputs;
      w[87:80]=1;w[91:88]=di;w[95:92]=do_;w[103:96]=16;return w;end
  endfunction
  initial begin cases=0;
    r=tensor(56'h123456789abcde,4'd5,4'd2);check(1,1,0);
    if(address!==56'h123456789abcde||dtype!=5||rank!=2)$fatal(1,"tensor decode");
    r=tensor(56'h1000,4'd7,4'd4);check(1,1,0);
    r=tensor(56'h1000,4'd0,4'd2);check(1,0,4);
    r=tensor(56'h1000,4'd2,4'd2);check(1,0,4);
    r=tensor(56'h1000,4'd5,4'd0);check(1,0,4);
    r=tensor(56'h1000,4'd5,4'd2);r[107:104]=1;check(1,0,4);
    r=tensor(56'h1000,4'd5,4'd2);r[8]=1;check(1,0,2);
    r=sfu(16'h32,2,5,5);check(1,1,0);
    if(pid!=16'h32||ic!=2||oc!=1||idt!=5||odt!=5||lane!=16||vl!=0)$fatal(1,"sfu decode");
    r=sfu(16'h35,3,5,5);check(1,0,4);
    r=sfu(16'h33,1,5,5);r[120]=1;check(1,0,4);
    r=sfu(16'h33,1,0,5);check(1,0,4);
    r=0;r[7:0]=8'haa;check(0,0,4);
    $display("DESCRIPTOR_PUBLIC_RECORD_DECODE_PASS cases=%0d",cases);$finish;
  end
endmodule

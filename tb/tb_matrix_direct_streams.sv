`timescale 1ns/1ps
module tb_matrix_direct_streams;
  localparam integer PER_CHANNEL=25000;
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  logic[3:0] in_valid,in_ready,out_valid,out_ready,prev_in_fire,stalling;
  logic[4*512-1:0] in_data,out_data,held_data;
  logic[4*64-1:0] in_be,out_be,held_be;
  logic[4*16-1:0] in_tag,out_tag,held_tag;
  logic[4*12-1:0] in_tensor,out_tensor,held_tensor;
  logic[3:0] in_last,out_last,held_last;
  logic[4*4-1:0] in_format,out_format,held_format;
  integer sent[0:3],received[0:3];
  integer ch,w,seed,cycles,total_received;

  matrix_direct_streams dut(.clk_i(clk),.rst_ni(rst_n),
    .in_valid_i(in_valid),.in_ready_o(in_ready),.in_data_i(in_data),.in_be_i(in_be),
    .in_tag_i(in_tag),.in_tensor_id_i(in_tensor),.in_last_i(in_last),.in_format_i(in_format),
    .out_valid_o(out_valid),.out_ready_i(out_ready),.out_data_o(out_data),.out_be_o(out_be),
    .out_tag_o(out_tag),.out_tensor_id_o(out_tensor),.out_last_o(out_last),.out_format_o(out_format));

  function automatic[511:0] make_data(input integer channel,input integer sequence_number);
    integer word_index;
    begin
      for(word_index=0;word_index<16;word_index++)
        make_data[word_index*32 +: 32]=sequence_number*32'h1021+channel*32'h100000+word_index;
    end
  endfunction
  function automatic[63:0] make_be(input integer channel,input integer sequence_number);
    begin make_be=(sequence_number%2?64'ha55aa55aa55aa55a:64'h5aa55aa55aa55aa5)^
      (channel*64'h0101010101010101);end
  endfunction
  function automatic[15:0] make_tag(input integer channel,input integer sequence_number);
    begin make_tag=sequence_number^(channel<<12);end
  endfunction
  function automatic[11:0] make_tensor(input integer channel,input integer sequence_number);
    begin make_tensor=(sequence_number+channel*17)&12'hfff;end
  endfunction

  initial begin
    in_valid=0;in_data=0;in_be=0;in_tag=0;in_tensor=0;in_last=0;in_format=0;
    out_ready=0;prev_in_fire=0;stalling=0;held_data=0;held_be=0;held_tag=0;
    held_tensor=0;held_last=0;held_format=0;seed=32'h2468ace1;cycles=0;total_received=0;
    for(ch=0;ch<4;ch++)begin sent[ch]=0;received[ch]=0;end
    repeat(4)@(posedge clk);rst_n=1;
    while(total_received<4*PER_CHANNEL)begin
      @(negedge clk);cycles=cycles+1;
      for(ch=0;ch<4;ch++)begin
        if(prev_in_fire[ch])in_valid[ch]=0;
        out_ready[ch]=($urandom(seed)%(3+ch))!=0;
        if(sent[ch]<PER_CHANNEL&&!in_valid[ch]&&($urandom(seed)%4)!=0)begin
          in_valid[ch]=1;
          in_data[ch*512 +: 512]=make_data(ch,sent[ch]);
          in_be[ch*64 +: 64]=make_be(ch,sent[ch]);
          in_tag[ch*16 +: 16]=make_tag(ch,sent[ch]);
          in_tensor[ch*12 +: 12]=make_tensor(ch,sent[ch]);
          in_last[ch]=(sent[ch]%31)==30;
          in_format[ch*4 +: 4]=ch+1;
        end
      end
      #1;
      for(ch=0;ch<4;ch++)begin
        if(stalling[ch])begin
          if(!out_valid[ch]||out_data[ch*512 +: 512]!==held_data[ch*512 +: 512]||
             out_be[ch*64 +: 64]!==held_be[ch*64 +: 64]||out_tag[ch*16 +: 16]!==held_tag[ch*16 +: 16]||
             out_tensor[ch*12 +: 12]!==held_tensor[ch*12 +: 12]||out_last[ch]!==held_last[ch]||
             out_format[ch*4 +: 4]!==held_format[ch*4 +: 4])$fatal(1,"payload changed under stall ch=%0d",ch);
        end
        prev_in_fire[ch]=in_valid[ch]&&in_ready[ch];
        if(prev_in_fire[ch])sent[ch]=sent[ch]+1;
        if(out_valid[ch]&&out_ready[ch])begin
          if(out_data[ch*512 +: 512]!==make_data(ch,received[ch])||
             out_be[ch*64 +: 64]!==make_be(ch,received[ch])||
             out_tag[ch*16 +: 16]!==make_tag(ch,received[ch])||
             out_tensor[ch*12 +: 12]!==make_tensor(ch,received[ch])||
             out_last[ch]!==((received[ch]%31)==30)||out_format[ch*4 +: 4]!==ch+1)
            $fatal(1,"stream mismatch ch=%0d sequence=%0d",ch,received[ch]);
          received[ch]=received[ch]+1;total_received=total_received+1;
        end
        stalling[ch]=out_valid[ch]&&!out_ready[ch];
        if(stalling[ch])begin
          held_data[ch*512 +: 512]=out_data[ch*512 +: 512];held_be[ch*64 +: 64]=out_be[ch*64 +: 64];
          held_tag[ch*16 +: 16]=out_tag[ch*16 +: 16];held_tensor[ch*12 +: 12]=out_tensor[ch*12 +: 12];
          held_last[ch]=out_last[ch];held_format[ch*4 +: 4]=out_format[ch*4 +: 4];
        end
      end
      @(posedge clk);
    end
    for(ch=0;ch<4;ch++)if(sent[ch]!=PER_CHANNEL||received[ch]!=PER_CHANNEL)$fatal(1,"count mismatch ch=%0d",ch);
    $display("MATRIX_DIRECT_STREAMS_100K_PASS cycles=%0d per_channel=%0d",cycles,PER_CHANNEL);$finish;
  end
  initial begin repeat(300000)@(posedge clk);$fatal(1,"timeout");end
endmodule

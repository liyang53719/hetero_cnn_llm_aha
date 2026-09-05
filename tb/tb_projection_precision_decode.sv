`timescale 1ns/1ps
module tb_projection_precision_decode;
 parameter bit ENABLE=1;
 logic clk=0;always #1 clk=~clk;
 logic rst=0,start=0,qv,qr,sv=0,sr,se=0,cv,cr=0,legal,fp32;
 logic[127:0]command=128'h00000200000100000000000000000220,data,records[0:5];
 logic[23:0]index;logic[7:0]status;logic[167:0]addresses;logic[215:0]shapes;
 logic[17:0]cols;logic[31:0]stride;logic[5:0]tiles;logic[31:0]rng=32'habcd7891;
 integer errors=0,checked=0;logic inject_error=0;
 qwen2_projection_descriptor_context #(.ALLOW_FP32_OUTPUT(ENABLE))dut(
 .clk_i(clk),.rst_ni(rst),.start_i(start),.command_i(command),.descriptor_req_valid_o(qv),.descriptor_req_ready_i(qr),
 .descriptor_req_index_o(index),.descriptor_rsp_valid_i(sv),.descriptor_rsp_ready_o(sr),.descriptor_rsp_data_i(data),.descriptor_rsp_error_i(se),
 .context_valid_o(cv),.context_ready_i(cr),.context_legal_o(legal),.context_status_o(status),.tensor_address_o(addresses),.tensor_shape_o(shapes),
 .output_columns_o(cols),.weight_row_bytes_o(stride),.column_tiles_o(tiles),.output_fp32_o(fp32));
 assign qr=!sv&&rng[0];
 always @(posedge clk)if(rst)begin
  rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(qv&&qr)begin if(index>5)$fatal(1,"fetch index");data<=records[index];sv<=1;se<=inject_error;end
  if(sv&&sr)sv<=0;
 end
 task tick;@(posedge clk);@(negedge clk);endtask
 task init_records;
  begin
   for(int i=0;i<3;i++)begin
    records[i]=0;records[i][7:0]=1;records[i][55:32]=24'(i+3);records[i][103:56]=48'(i*65536);records[i][111:108]=5;
    records[i+3]=0;records[i+3][7:0]=2;records[i+3][55:32]=24'hffffff;
    records[i+3][56+:18]=i==1?1536:1024;records[i+3][74+:18]=i==0?1536:32;
    records[i+3][92+:18]=1;records[i+3][110+:18]=1;
   end
  end
 endtask
 task run_case(input integer expected_status,input bit expected_fp32);
  begin
   start=1;tick();start=0;wait(cv);@(negedge clk);
   if(status!=expected_status||legal!=(expected_status==0))$fatal(1,"status %0d expected %0d",status,expected_status);
   if(expected_status==0&&(fp32!=expected_fp32||cols!=32||stride!=64||tiles!=1))$fatal(1,"output geometry");
   repeat(3)begin tick();if(!cv||status!=expected_status)$fatal(1,"completion hold");end
   cr=1;tick();cr=0;checked++;
  end
 endtask
 initial begin
  command=0;command[7:0]=8'h20;command[10:8]=2;command[79:56]=0;command[103:80]=1;command[127:104]=2;
  repeat(3)tick();rst=1;tick();
  init_records();run_case(0,0);
  records[2][111:108]=7;run_case(ENABLE?0:4,ENABLE);
  for(int role=0;role<2;role++)begin init_records();records[role][111:108]=7;run_case(4,0);end
  init_records();records[2][111:108]=6;run_case(4,0);
  init_records();records[0][8]=1;run_case(2,0);
  init_records();inject_error=1;run_case(3,0);inject_error=0;
  init_records();run_case(0,0);
  $display("PROJECTION_PRECISION_DECODE_PASS enable=%0d cases=%0d fp32_matrix_inputs_rejected=1",ENABLE,checked);$finish;
 end
 initial begin repeat(5000)tick();$fatal(1,"timeout");end
endmodule

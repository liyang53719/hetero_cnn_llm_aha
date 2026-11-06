#include "passive_native_mapping.h"
// Independent direct generated-port execution. No C ABI/JNA/Scala callbacks.
#include "Vqwen2_matrix_command_endpoint.h"
#include "verilated.h"
#include "trace_io.h"
int main(int argc,char** argv){try{
 require_argc(argc,2);auto rows=read_rows(argv[1],64,4096);VerilatedContext context;
 context.threads(1);Vqwen2_matrix_command_endpoint dut(&context,"matrix_direct");passive_native_mapping::capture("matrix_direct");dut.clk_i=0;
 uint32_t previous=0;uint64_t rises=0,falls=0;bool low=false;
 for(size_t row=0;row<rows.size();++row){const auto& r=rows[row];const auto* words=r.data()+1;
  if(r[0]>1||(!low&&r[0]!=0))throw std::runtime_error("first actual clock must be low");
    dut.rst_ni=words[0];
    dut.cmd_valid_i=words[1];
    for(unsigned j=0;j<4;++j)dut.cmd_i[j]=words[2+j];
    dut.step_valid_i=words[6];
    dut.step_context_i=words[7];
    dut.step_clear_i=words[8];
    dut.step_last_i=words[9];
    dut.command_last_tile_i=words[10];
    for(unsigned j=0;j<8;++j)dut.step_a_i[j]=words[11+j];
    for(unsigned j=0;j<16;++j)dut.step_b_i[j]=words[19+j];
    dut.out_ready_i=words[35];
    dut.completion_ready_i=words[36];
    dut.seed_begin_valid_i=words[37];
    dut.seed_context_i=words[38];
    dut.seed_group_tag_i=words[39];
    dut.seed_group_sequence_i=words[40];
    dut.seed_source_generation_i=words[41];
    dut.seed_beat_valid_i=words[42];
    dut.seed_cluster_i=words[43];
    for(unsigned j=0;j<16;++j)dut.seed_data_i[j]=words[44+j];
    dut.seed_commit_valid_i=words[60];
    dut.seed_abort_i=words[61];
    dut.seed_ack_ready_i=words[62];
  dut.eval();if(context.gotFinish())throw std::runtime_error("RTL finish");
  if(r[0]!=previous){context.timeInc(1);if(r[0])++rises;else ++falls;}
  dut.clk_i=r[0];dut.eval();if(context.gotFinish())throw std::runtime_error("RTL finish");
  if(r[0]==0)low=true;previous=r[0];std::vector<uint32_t> result(533);
    result[0]=dut.cmd_ready_o;
    result[1]=dut.step_ready_o;
    result[2]=dut.out_valid_o;
    result[3]=dut.out_context_o;
    result[4]=dut.out_last_o;
    for(unsigned j=0;j<512;++j)result[5+j]=dut.out_acc_o[j];
    result[517]=dut.completion_valid_o;
    result[518]=uint32_t(dut.completion_data_o);
    result[519]=uint32_t(dut.completion_data_o>>32);
    result[520]=dut.protocol_error_o;
    result[521]=dut.seed_begin_ready_o;
    result[522]=dut.seed_beat_ready_o;
    result[523]=dut.seed_commit_ready_o;
    result[524]=dut.seed_ack_valid_o;
    result[525]=dut.seed_ack_context_o;
    result[526]=dut.seed_ack_group_tag_o;
    result[527]=dut.seed_ack_group_sequence_o;
    result[528]=dut.seed_ack_source_generation_o;
    result[529]=dut.seed_ack_error_o;
    result[530]=dut.seed_reset_required_o;
    result[531]=dut.arithmetic_busy_o;
    result[532]=dut.arithmetic_out_valid_o;
  print_row(row,r[0],result,rises,falls);
 }
 dut.final();return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 2;}}

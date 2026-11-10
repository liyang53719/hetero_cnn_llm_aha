#include "unseeded_matrix_v2.h"
#include "Vqwen2_matrix_command_endpoint.h"
#include "verilated.h"
#include <cstdint>
#include <memory>
namespace {
struct Leaf {
  std::unique_ptr<VerilatedContext> context;
  std::unique_ptr<Vqwen2_matrix_command_endpoint> dut;
  bool driven=false,evaluated=false,low_observed=false;
  uint32_t level=0;
  uint64_t positive=0,negative=0;
  Leaf():context(new VerilatedContext){context->threads(1);dut.reset(new Vqwen2_matrix_command_endpoint(context.get(),"retained_matrix"));dut->clk_i=0;}
};
static_assert(sizeof(uint32_t)==4 && sizeof(uint64_t)==8, "fixed-width ABI");
static_assert(sizeof(((Vqwen2_matrix_command_endpoint*)nullptr)->cmd_i)==16, "cmd_i generated header width");
static_assert(sizeof(((Vqwen2_matrix_command_endpoint*)nullptr)->step_a_i)==32, "step_a_i generated header width");
static_assert(sizeof(((Vqwen2_matrix_command_endpoint*)nullptr)->step_b_i)==64, "step_b_i generated header width");
static_assert(sizeof(((Vqwen2_matrix_command_endpoint*)nullptr)->out_acc_o)==2048, "out_acc_o generated header width");
}
extern "C" uint32_t retained_matrix_unseeded_v2_abi_version(){return RETAINED_MATRIX_ABI_VERSION;}
extern "C" const char* retained_matrix_unseeded_v2_contract_sha256(){return RETAINED_MATRIX_CONTRACT_SHA256;}
extern "C" void* retained_matrix_unseeded_v2_create(){try{return new Leaf;}catch(...){return nullptr;}}
extern "C" int retained_matrix_unseeded_v2_destroy(void* h){if(!h)return 0;auto* s=static_cast<Leaf*>(h);int status=0;try{s->dut->final();}catch(...){status=-5;}delete s;return status;}
extern "C" int retained_matrix_unseeded_v2_drive(void* h,const uint32_t* words,uint32_t count){
  if(!h||!words||count!=RETAINED_MATRIX_INPUT_WORDS)return -1;
  if (words[0] & ~uint32_t(0x00000001u)) return -1;
  if (words[1] & ~uint32_t(0x00000001u)) return -1;
  if (words[6] & ~uint32_t(0x00000001u)) return -1;
  if (words[7] & ~uint32_t(0x00000007u)) return -1;
  if (words[8] & ~uint32_t(0x00000001u)) return -1;
  if (words[9] & ~uint32_t(0x00000001u)) return -1;
  if (words[10] & ~uint32_t(0x00000001u)) return -1;
  if (words[35] & ~uint32_t(0x00000001u)) return -1;
  if (words[36] & ~uint32_t(0x00000001u)) return -1;
  Leaf& s=*static_cast<Leaf*>(h);
  s.dut->rst_ni=words[0];
  s.dut->cmd_valid_i=words[1];
  for (unsigned i=0;i<4;++i) s.dut->cmd_i[i]=words[2+i];
  s.dut->step_valid_i=words[6];
  s.dut->step_context_i=words[7];
  s.dut->step_clear_i=words[8];
  s.dut->step_last_i=words[9];
  s.dut->command_last_tile_i=words[10];
  for (unsigned i=0;i<8;++i) s.dut->step_a_i[i]=words[11+i];
  for (unsigned i=0;i<16;++i) s.dut->step_b_i[i]=words[19+i];
  s.dut->out_ready_i=words[35];
  s.dut->completion_ready_i=words[36];
  s.driven=true;s.evaluated=false;return 0;
}
extern "C" int retained_matrix_unseeded_v2_eval(void* h){
  if(!h)return -1;Leaf& s=*static_cast<Leaf*>(h);
  if(!s.driven)return -2;
  try{s.dut->eval();}catch(...){s.evaluated=false;return -5;}s.evaluated=true;
  return s.context->gotFinish()?-3:0;
}
extern "C" int retained_matrix_unseeded_v2_clock(void* h,uint32_t level){
  if(!h||level>1)return -1;Leaf& s=*static_cast<Leaf*>(h);
  if(!s.evaluated||(level==1&&!s.low_observed))return -2;
  if(level!=s.level){s.context->timeInc(1);if(level)++s.positive;else ++s.negative;}
  s.level=level;s.dut->clk_i=level;s.evaluated=false;
  const int result=retained_matrix_unseeded_v2_eval(h);
  if(result==0&&level==0)s.low_observed=true;
  return result;
}
extern "C" int retained_matrix_unseeded_v2_read(void* h,uint32_t* words,uint32_t count){
  if(!h||!words||count!=RETAINED_MATRIX_OUTPUT_WORDS)return -1;
  Leaf& s=*static_cast<Leaf*>(h);if(!s.evaluated)return -2;
  words[0]=s.dut->cmd_ready_o;
  words[1]=s.dut->step_ready_o;
  words[2]=s.dut->out_valid_o;
  words[3]=s.dut->out_context_o;
  words[4]=s.dut->out_last_o;
  for (unsigned i=0;i<512;++i) words[5+i]=s.dut->out_acc_o[i];
  words[517]=s.dut->completion_valid_o;
  words[518]=uint32_t(s.dut->completion_data_o);
  words[519]=uint32_t(s.dut->completion_data_o>>32);
  words[520]=s.dut->protocol_error_o;
  if (words[0] & ~uint32_t(0x00000001u)) return -4;
  if (words[1] & ~uint32_t(0x00000001u)) return -4;
  if (words[2] & ~uint32_t(0x00000001u)) return -4;
  if (words[3] & ~uint32_t(0x00000007u)) return -4;
  if (words[4] & ~uint32_t(0x00000001u)) return -4;
  if (words[517] & ~uint32_t(0x00000001u)) return -4;
  if (words[519] & ~uint32_t(0x00ffffffu)) return -4;
  if (words[520] & ~uint32_t(0x00000001u)) return -4;
  return 0;
}
extern "C" int retained_matrix_unseeded_v2_edge_counts(void* h,uint64_t* positive,uint64_t* negative){
  if(!h||!positive||!negative)return -1;const Leaf& s=*static_cast<Leaf*>(h);
  *positive=s.positive;*negative=s.negative;return 0;
}
extern "C" int retained_matrix_unseeded_v2_seed_request(void*,const uint32_t*,uint32_t){return -7;} // unsupported, even zero request

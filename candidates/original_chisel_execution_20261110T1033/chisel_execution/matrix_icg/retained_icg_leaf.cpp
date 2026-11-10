#include "retained_icg_leaf.h"
#include "Vtc_clk_gating.h"
#include "verilated.h"
#include <memory>
namespace {
struct Leaf {
 std::unique_ptr<VerilatedContext> context;
 std::unique_ptr<Vtc_clk_gating> dut;
 bool driven=false,evaluated=false,low_observed=false,output_observed=false;
 uint32_t level=0,previous_output=0;
 uint64_t positive=0,negative=0,gated_positive=0,gated_negative=0;
 Leaf():context(new VerilatedContext){context->threads(1);dut.reset(new Vtc_clk_gating(context.get(),"retained_icg"));dut->clk_i=0;}
};
static_assert(sizeof(uint32_t)==4 && sizeof(uint64_t)==8,"fixed-width ABI");
}
extern "C" uint32_t retained_icg_abi_version(){return RETAINED_ICG_ABI_VERSION;}
extern "C" void* retained_icg_create(){try{return new Leaf;}catch(...){return nullptr;}}
extern "C" int retained_icg_destroy(void* h){if(!h)return 0;auto* s=static_cast<Leaf*>(h);int status=0;try{s->dut->final();}catch(...){status=-5;}delete s;return status;}
extern "C" int retained_icg_drive(void* h,uint32_t en,uint32_t scan){
 if(!h||en>1||scan>1)return -1;Leaf& s=*static_cast<Leaf*>(h);
 s.dut->en_i=en;s.dut->test_en_i=scan;s.driven=true;s.evaluated=false;return 0;
}
extern "C" int retained_icg_eval(void* h){
 if(!h)return -1;Leaf& s=*static_cast<Leaf*>(h);if(!s.driven)return -2;
 try{s.dut->eval();}catch(...){s.evaluated=false;return -5;}s.evaluated=true;if(s.context->gotFinish())return -3;
 if(s.dut->clk_o>1)return -4;
 if(s.output_observed&&s.dut->clk_o!=s.previous_output){if(s.dut->clk_o)++s.gated_positive;else ++s.gated_negative;}
 s.previous_output=s.dut->clk_o;s.output_observed=true;return 0;
}
extern "C" int retained_icg_clock(void* h,uint32_t level){
 if(!h||level>1)return -1;Leaf& s=*static_cast<Leaf*>(h);
 if(!s.evaluated||(level==1&&!s.low_observed))return -2;
 if(level!=s.level){s.context->timeInc(1);if(level)++s.positive;else ++s.negative;}
 s.level=level;s.dut->clk_i=level;s.evaluated=false;
 const int result=retained_icg_eval(h);if(result==0&&level==0)s.low_observed=true;return result;
}
extern "C" int retained_icg_read(void* h,uint32_t* gated_clock){
 if(!h||!gated_clock)return -1;const Leaf& s=*static_cast<Leaf*>(h);if(!s.evaluated)return -2;
 *gated_clock=s.dut->clk_o;return *gated_clock<=1?0:-4;
}
extern "C" int retained_icg_edge_counts(void* h,uint64_t* p,uint64_t* n,uint64_t* gp,uint64_t* gn){
 if(!h||!p||!n||!gp||!gn)return -1;const Leaf& s=*static_cast<Leaf*>(h);
 *p=s.positive;*n=s.negative;*gp=s.gated_positive;*gn=s.gated_negative;return 0;
}

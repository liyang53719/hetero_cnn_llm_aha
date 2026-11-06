#include "passive_native_mapping.h"
#include "Vtc_clk_gating.h"
#include "verilated.h"
#include "trace_io.h"
int main(int argc,char** argv){try{
 require_argc(argc,2);auto rows=read_rows(argv[1],3,4096);VerilatedContext context;context.threads(1);Vtc_clk_gating dut(&context,"icg_direct");passive_native_mapping::capture("icg_direct");dut.clk_i=0;
 uint32_t old=0,out=0;bool seen=false,low=false;uint64_t p=0,n=0,gp=0,gn=0;
 auto eval=[&](){dut.eval();if(context.gotFinish())throw std::runtime_error("RTL finish");if(seen&&out!=dut.clk_o){if(dut.clk_o)++gp;else ++gn;}out=dut.clk_o;seen=true;};
 for(size_t i=0;i<rows.size();++i){auto r=rows[i];for(auto v:r)if(v>1)throw std::runtime_error("one-bit ICG input");if(!low&&r[0])throw std::runtime_error("actual low first");
  dut.en_i=r[1];dut.test_en_i=r[2];eval();if(old!=r[0]){context.timeInc(1);if(r[0])++p;else ++n;}dut.clk_i=r[0];eval();if(!r[0])low=true;old=r[0];
  std::cout<<i<<" "<<r[0]<<" "<<unsigned(dut.clk_o)<<" "<<p<<" "<<n<<" "<<gp<<" "<<gn<<"\n";
 }
 dut.final();return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 2;}}

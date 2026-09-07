// SPDX-License-Identifier: Apache-2.0
// Diagnostic on unchanged Chisel-generated, eight-slice arithmetic.
// No DDR, SFU, Host program or external request gap is modeled here.
#define main preserved_matrix_arithmetic_main
#include "matrix4096_arithmetic.cpp"
#undef main
#include <vector>
#include <algorithm>

int main(int argc,char**argv){try {
 std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
 check(argc==2,"NEW_OUTPUT_DIRECTORY");const std::filesystem::path out(argv[1]);
 check(!std::filesystem::exists(out),"preserve old diagnostic evidence");std::filesystem::create_directories(out);
 Probe p(out);uint64_t steps=0;
 for(unsigned mask:{255u,1u}){
  const unsigned depth=128;std::vector<uint64_t> periods;const uint64_t begin=p.cycles;
  for(unsigned k=0;k<depth;k++){
   const uint64_t start=p.cycles;p.send(mask,k,depth);
   for(unsigned r=0;r<16;r++)for(unsigned c=0;c<256;c++){
    const bool selected=mask&(1u<<(c/32));
    const int numerator=(int(c)-128)*int((k+1)*(r+1)+k*(k+1)/2);
    const uint32_t expected=bits(selected?float(numerator)/4096.0f:0.0f),actual=p.word(r*256+c);
    check(actual==expected,"ordered arithmetic differs in service test");
    p.actual.write(reinterpret_cast<const char*>(&actual),4);p.reference.write(reinterpret_cast<const char*>(&expected),4);
    p.csv<<p.request<<','<<mask<<','<<r<<','<<c<<','<<std::hex<<std::setfill('0')<<std::setw(8)<<actual<<','<<std::setw(8)<<expected<<std::dec<<'\n';p.checked++;
   }
   steps+=__builtin_popcount(mask);check(p.dut.io_acceptedSteps==steps,"slice counter mismatch");
   p.consume();if(k>0 && k+1<depth)periods.push_back(p.cycles-start);
  }
  check(periods.size()==126,"missing steady-state samples");
  auto mm=std::minmax_element(periods.begin(),periods.end());
  check(*mm.first>0 && *mm.first==*mm.second,"unexpected variable no-stall service period");
  std::cout<<"MATRIX_SERVICE_CASE mask="<<mask<<" depth="<<depth<<" checked_fp32="<<depth*4096
   <<" cycles="<<p.cycles-begin<<" steady_samples="<<periods.size()<<" steady_period_min="<<*mm.first
   <<" steady_period_max="<<*mm.second<<" active_macs_per_step="<<__builtin_popcount(mask)*512
   <<" explicit_result_hold_cycles=0 explicit_inter_request_delay=0"<<std::endl;
 }
 p.csv.flush();p.actual.flush();p.reference.flush();check(p.csv.good()&&p.actual.good()&&p.reference.good(),"output write failed");
 check(p.checked==1048576 && steps==1152 && !p.dut.io_resetRequired,"incomplete diagnostic");
 std::cout<<"MATRIX_SERVICE_PASS checked_fp32="<<p.checked<<" bit_differences=0 actual_slice_steps="<<steps
  <<" physical_slices=8 host_idma=0 full_model=0"<<std::endl;return 0;
}catch(const std::exception& e){std::cerr<<"MATRIX_SERVICE_FAIL: "<<e.what()<<std::endl;return 1;}}

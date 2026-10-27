// SPDX-License-Identifier: Apache-2.0
// The original0337 two-group service stimulus translated to the compiled-model
// port API. Expectations live ONLY in this test executable, never in the DPI.
#include "VMatrixPipelineService.h"
#include "verilated.h"
#include "finite_fp32_gmp.hpp"
#include "endpoint_fma_fixture.hpp"
#include "endpoint_state_crosscheck.hpp"
#include <unordered_map>
#include <string>
#include <type_traits>
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <memory>
#include <cstdint>
extern "C" void retained_endpoint_require_complete();
struct PortRef {
  void* address;unsigned width;bool input;
  uint64_t(*get)(const void*);void(*set)(void*,uint64_t);
};
using PortMap=std::unordered_map<std::string,PortRef>;
template<class T> void addPort(PortMap& p,const char* name,T& field,unsigned width,bool input) {
  static_assert(std::is_integral<T>::value&&std::is_unsigned<T>::value,"unsigned Verilator scalar port");
  retained_model::require(width>0&&width<=64&&sizeof(T)*8>=width,"actual port width");
  auto get=[](const void* q)->uint64_t{return *static_cast<const T*>(q);};
  auto set=[](void* q,uint64_t v){*static_cast<T*>(q)=T(v);};
  retained_model::require(p.emplace(name,PortRef{&field,width,input,get,set}).second,"duplicate compiled port");
}
#include "actual_port_bindings.hpp"
static uint32_t fp(unsigned n) {
  if(!n)return 0;unsigned e=0;for(unsigned v=n;v>>=1;)++e;
  retained_model::require(e<=23,"integer expected-value fixture domain");
  return ((e+127)<<23)|((n<<(23-e))&0x7fffff);
}
static uint16_t bf(unsigned n){const uint32_t v=fp(n);retained_model::require((v&65535)==0,"fixture integer exactly BF16");return v>>16;}
int main(int argc,char** argv) {
  std::unique_ptr<VerilatedContext> context;
  std::unique_ptr<VMatrixPipelineService> dut;
  bool finished=false;
  try {
    retained_model::require(argc==1,"fixed no-argument service test only");
    unsigned checked=0;
    for(const auto& v:EndpointFmaFixture){const auto f=retained_model::fma(v.a<<16,v.b<<16,v.c);
      retained_model::require(f.value==v.value&&f.flags==v.flags,"C++ FMA fixture value/flags mismatch");++checked;}
    retained_model::require(checked==74,"exact74 inherited finite-input literals");
    std::cout<<"COMPILED_MODEL arithmetic_literals74 PASS (not fresh HardFloat execution)\n"<<std::flush;
    unsigned rejected=0;
    for(uint32_t bad:{0x7f800000u,0xff800000u,0x7fc00001u,0x7f800001u})for(unsigned where=0;where<3;++where){
      bool threw=false;try{(void)retained_model::fma(where==0?bad:0x3f800000u,where==1?bad:0x3f800000u,where==2?bad:0u);}catch(const std::runtime_error&){threw=true;}
      retained_model::require(threw,"unsupported nonfinite input must reject");++rejected;
    }
    retained_model::require(rejected==12,"exact12 inherited nonfinite rejection checks");
    endpoint_state_test::run();
    std::cout<<"COMPILED_MODEL finite_state_contract PASS (not Chisel seed protocol)\n"<<std::flush;
    context=std::make_unique<VerilatedContext>();context->threads(1);context->randReset(0);
    dut=std::make_unique<VMatrixPipelineService>(context.get());PortMap ports;bindPorts(*dut,ports);
    uint64_t steps=0,expects=0,groups=0,wide=0;
    auto port=[&](const std::string& name)->PortRef&{auto i=ports.find(name);retained_model::require(i!=ports.end(),"unknown actual top port");return i->second;};
    auto rawPoke=[&](const std::string& name,uint64_t value){auto& p=port(name);retained_model::require(p.input,"poke output forbidden");retained_model::require(p.width==64||(value>>p.width)==0,"poke word width");p.set(p.address,value);dut->eval();};
    auto poke=[&](const std::string& name,uint64_t value){rawPoke("io_"+name,value);};
    auto peek=[&](const std::string& name)->uint64_t{dut->eval();const auto& p=port("io_"+name);return p.get(p.address);};
    auto expect=[&](const std::string& name,uint64_t wanted){const uint64_t got=peek(name);++expects;
      if(got!=wanted){std::cerr<<"EXPECT_FAIL "<<name<<" got="<<std::hex<<got<<" wanted="<<wanted<<std::dec<<"\n";throw std::runtime_error("service expectation");}};
    auto advance=[&](unsigned n=1){for(unsigned i=0;i<n;++i){rawPoke("clock",0);context->timeInc(1);rawPoke("clock",1);context->timeInc(1);rawPoke("clock",0);++steps;}};
    auto waitFor=[&](const std::string& name){unsigned n=0;while(peek(name)==0&&n<128){advance();++n;}expect(name,1);};
    auto progress=[&](const char* phase){std::cout<<"SERVICE_PHASE "<<phase<<" steps="<<steps<<" expects="<<expects<<" groups="<<groups<<" wide="<<wide<<"\n"<<std::flush;};
    // Explicit no-clock reset-establishment preamble. Set all handshake inputs
    // inactive and clock low; settle real reset deassertion at time zero, then
    // assert the real top reset so every gated endpoint observes rst_ni falling.
    // No model reset call, clock edge, timeInc, or advance is added here. The
    // following original two reset clocks and all48 clocked cycles are unchanged.
    {auto& c=port("clock");c.set(c.address,0);
      for(const char* name:{"port_group_valid","port_step_valid","port_abort","port_result_ready","port_done_ready"}) {
        auto& p=port(std::string("io_")+name);p.set(p.address,0);
      }
      auto& r=port("reset");r.set(r.address,0);dut->eval();
      r.set(r.address,1);dut->eval();}
    retained_endpoint_require_complete();progress("fixture.begin");
    poke("port_group_valid",0);poke("port_step_valid",0);poke("port_abort",0);
    poke("port_result_ready",0);poke("port_done_ready",0);
    poke("port_group_bits_opcode",0x20);poke("port_group_bits_sliceMask",255);
    poke("port_group_bits_tag",1);poke("port_group_bits_transposedDense",0);
    poke("port_step_bits_context",0);poke("port_step_bits_clear",1);poke("port_step_bits_last",0);
    poke("port_step_bits_finish",0);poke("port_step_bits_emit",0);poke("port_step_bits_returnTag",0);
    for(unsigned r=0;r<16;++r)poke("port_step_bits_a_"+std::to_string(r),bf(r+1));
    for(unsigned c=0;c<256;++c)poke("port_step_bits_b_"+std::to_string(c),bf(c+1));
    rawPoke("reset",1);advance(2);rawPoke("reset",0);advance(3);
    expect("acceptedSteps",0);expect("resetRequired",0);
    auto group=[&](unsigned tag,bool transposed){poke("port_group_bits_tag",tag);poke("port_group_bits_transposedDense",transposed);
      poke("port_group_valid",1);waitFor("port_group_ready");advance();poke("port_group_valid",0);++groups;};
    auto step=[&](unsigned ctx,bool clear,bool last,bool finish,bool emit,unsigned tag){
      poke("port_step_bits_context",ctx);poke("port_step_bits_clear",clear);poke("port_step_bits_last",last);
      poke("port_step_bits_finish",finish);poke("port_step_bits_emit",emit);poke("port_step_bits_returnTag",tag);
      poke("port_step_valid",1);waitFor("port_step_ready");advance();poke("port_step_valid",0);++wide;};
    progress("transaction.1.begin");group(1,false);
    for(unsigned ctx=0;ctx<5;++ctx)step(ctx,true,true,ctx==4,true,100+ctx);
    waitFor("port_result_valid");const uint64_t held=peek("port_result_bits_value_0_0");
    advance(4);expect("port_result_valid",1);expect("port_result_bits_value_0_0",held);expect("port_done_valid",0);
    for(unsigned ctx=0;ctx<5;++ctx){
      waitFor("port_result_valid");expect("port_result_bits_context",ctx);expect("port_result_bits_returnTag",100+ctx);expect("port_result_bits_error",0);
      for(unsigned r=0;r<16;++r)for(unsigned c=0;c<256;++c)expect("port_result_bits_value_"+std::to_string(r)+"_"+std::to_string(c),fp((r+1)*(c+1)));
      poke("port_result_ready",1);advance();poke("port_result_ready",0);
    }
    waitFor("port_done_valid");expect("port_done_bits_tag",1);expect("port_done_bits_error",0);
    poke("port_done_ready",1);advance();poke("port_done_ready",0);progress("transaction.1.end");
    for(unsigned c=0;c<256;++c)poke("port_step_bits_b_"+std::to_string(c),bf(c<128?c+1:(c<144?c-111:1)));
    progress("transaction.2.begin");group(2,true);step(0,true,false,false,false,200);step(0,false,true,true,true,201);
    waitFor("port_result_valid");expect("port_result_bits_returnTag",201);
    for(unsigned r=0;r<16;++r)for(unsigned c=0;c<256;++c){const unsigned slice=c/32,lane=c%32;
      expect("port_result_bits_value_"+std::to_string(r)+"_"+std::to_string(c),fp(2*(r+1+16*(slice/4))*(32*(slice%4)+lane+1)));}
    poke("port_result_ready",1);advance();poke("port_result_ready",0);
    waitFor("port_done_valid");expect("port_done_bits_tag",2);expect("port_done_bits_error",0);
    poke("port_done_ready",1);advance();poke("port_done_ready",0);
    expect("wideSteps",7);expect("acceptedSteps",56);expect("resetRequired",0);progress("transaction.2.end");
    advance(8);expect("wideSteps",7);expect("acceptedSteps",56);
    rawPoke("reset",1);advance(2);rawPoke("reset",0);
    expect("acceptedSteps",0);expect("port_result_valid",0);expect("resetRequired",0);
    retained_endpoint_require_complete();progress("fixture.end");
    // Counts are the prior actual0337 two-state test's exact cycle/expectation
    // observation, not an allowance to change latency until outputs match.
    retained_model::require(steps==48&&expects==24627&&groups==2&&wide==7,"same original fixture cycle/observation counts");
    dut->final();finished=true;
    std::cout<<"PASS_COMPILED_FUNCTIONAL_MODEL_ORIGINAL_UNSEEDED_8X512_2GROUPS_48CYCLES_NOT_PROVIDER_RTL\n"<<std::flush;
    return 0;
  }catch(const std::exception& e){
    if(dut&&!finished){try{dut->final();}catch(...){}}
    std::cerr<<"COMPILED_MODEL_FAIL "<<e.what()<<"\n"<<std::flush;return 1;
  }
}

// SPDX-License-Identifier: Apache-2.0
#include "VMatrixPipelineProbe.h"
#include "verilated.h"
#include <array>
#include <cmath>
#include <cfenv>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
static void ck(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
static uint32_t bits(float x){uint32_t u;memcpy(&u,&x,4);return u;}
static float av(unsigned k,unsigned ctx,unsigned r){return float(int((k+ctx*3+r)%31)-15)/32;}
static float bv(unsigned k,unsigned ctx,unsigned c){return float(int((k*7+ctx*13+c)%61)-30)/64;}
struct Test{
 VMatrixPipelineProbe d;uint64_t cycle=0,checked=0;std::ofstream actual,reference;
 Test(const std::filesystem::path& o):actual(o/"actual.f32le",std::ios::binary),reference(o/"reference.f32le",std::ios::binary){
  d.clock=0;d.reset=1;d.io_group_valid=0;d.io_step_valid=0;d.io_result_ready=0;d.io_done_ready=0;d.io_abort=0;
  tick(6);d.reset=0;tick();
 }
 uint32_t word(unsigned n)const{
  const uint32_t* rows[16]={&d.io_result_bits_data_0[0],&d.io_result_bits_data_1[0],&d.io_result_bits_data_2[0],&d.io_result_bits_data_3[0],&d.io_result_bits_data_4[0],&d.io_result_bits_data_5[0],&d.io_result_bits_data_6[0],&d.io_result_bits_data_7[0],&d.io_result_bits_data_8[0],&d.io_result_bits_data_9[0],&d.io_result_bits_data_10[0],&d.io_result_bits_data_11[0],&d.io_result_bits_data_12[0],&d.io_result_bits_data_13[0],&d.io_result_bits_data_14[0],&d.io_result_bits_data_15[0]};
  return rows[n/256][n%256];
 }
 void eval(){d.clock=0;d.eval();}
 void tick(unsigned n=1){while(n--){eval();d.clock=1;d.eval();cycle++;eval();}}
 void group(unsigned mask,unsigned tag){d.io_group_valid=1;d.io_group_bits_opcode=0x20;d.io_group_bits_sliceMask=mask;d.io_group_bits_tag=tag;
  eval();unsigned w=0;while(!d.io_group_ready&&w++<100)tick();ck(d.io_group_ready,"group timeout");tick();d.io_group_valid=0;eval();}
 void run(unsigned mask,unsigned contexts,unsigned depth,bool stall){
  const unsigned total=contexts*depth;std::array<std::array<float,4096>,5> accum{};
  group(mask,mask);unsigned sent=0,got=0;uint64_t first=0,last=0;unsigned wait=0;
  std::array<uint32_t,4096> held{};bool hold=false;
  while(got<total && wait++<100000){
   if(sent<total){unsigned ctx=sent%contexts,k=sent/contexts;
    for(unsigned i=0;i<8;i++)d.io_step_bits_a[i]=0;
    for(unsigned i=0;i<128;i++)d.io_step_bits_b[i]=0;
    for(unsigned r=0;r<16;r++)d.io_step_bits_a[r/2]|=(bits(av(k,ctx,r))>>16)<<(16*(r%2));
    for(unsigned c=0;c<256;c++)d.io_step_bits_b[c/2]|=(bits(bv(k,ctx,c))>>16)<<(16*(c%2));
    d.io_step_valid=1;d.io_step_bits_context=ctx;d.io_step_bits_clear=k==0;
    d.io_step_bits_last=k+1==depth;d.io_step_bits_finish=sent+1==total;d.io_step_bits_emit=1;
   }else d.io_step_valid=0;
   d.io_result_ready=!stall || (cycle%11<7);eval();
   if(hold){ck(d.io_result_valid,"dropped stalled result");for(unsigned n=0;n<4096;n++)ck(held[n]==word(n),"unstable stalled result");}
   const bool issue=d.io_step_valid&&d.io_step_ready;
   if(issue){if(sent==0)first=cycle;last=cycle;sent++;}
   if(d.io_result_valid&&d.io_result_ready){
    unsigned ctx=got%contexts,k=got/contexts;ck(d.io_result_bits_context==ctx,"context order");ck(d.io_result_bits_last==(k+1==depth),"last mismatch");ck(!d.io_result_bits_error,"result error");
    for(unsigned r=0;r<16;r++)for(unsigned c=0;c<256;c++){
     unsigned n=r*256+c;if((mask>>(c/32))&1)accum[ctx][n]=std::fma(av(k,ctx,r),bv(k,ctx,c),accum[ctx][n]);
     const auto want=bits(accum[ctx][n]),v=word(n);
     if(v!=want){std::cerr<<"mismatch k="<<k<<" ctx="<<ctx<<" r="<<r<<" c="<<c<<std::hex<<" got="<<v<<" expected="<<want<<std::dec<<"\n";throw std::runtime_error("numeric");}
     actual.write(reinterpret_cast<const char*>(&v),4);reference.write(reinterpret_cast<const char*>(&want),4);checked++;
    }got++;
   }
   hold=d.io_result_valid&&!d.io_result_ready;if(hold)for(unsigned n=0;n<4096;n++)held[n]=word(n);tick();
  }
  ck(sent==total&&got==total,"incomplete stream");
  d.io_step_valid=0;d.io_result_ready=1;d.io_done_ready=0;eval();wait=0;while(!d.io_done_valid&&wait++<1000)tick();
  ck(d.io_done_valid&&!d.io_done_bits_error&&d.io_done_bits_tag==mask,"done contract");
  tick(5);ck(d.io_done_valid&&!d.io_done_bits_error,"done backpressure");d.io_done_ready=1;tick();d.io_done_ready=0;
  ck(!d.io_resetRequired,"unexpected poison");
  if(!stall&&contexts==5)ck(last-first+1==total,"five contexts failed II=1");
  std::cout<<"PIPELINE_CASE_PASS mask="<<mask<<" contexts="<<contexts<<" depth="<<depth<<" requests="<<total<<" issue_span="<<last-first+1<<" checked="<<uint64_t(total)*4096<<std::endl;
 }
};
int main(int argc,char**argv){try{
 std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);ck(argc==2,"new output path");std::filesystem::path out(argv[1]);ck(!std::filesystem::exists(out),"preserve evidence");std::filesystem::create_directories(out);
 auto t=std::make_unique<Test>(out);t->run(255,5,64,false);t->run(85,5,17,true);t->run(1,1,16,true);
 ck(t->d.io_wideSteps==421,"wide accepted steps");ck(t->d.io_acceptedSteps==320*8+85*4+16,"physical slice issue count");
 t->actual.flush();t->reference.flush();ck(t->actual.good()&&t->reference.good(),"file write");
 std::cout<<"MATRIX_PIPELINE_NUMERIC_PASS checked_fp32="<<t->checked<<" bit_differences=0 physical_slices=8 wide_steps="<<t->d.io_wideSteps<<" original_arithmetic=1 ii_one_5contexts=1\n";return 0;
}catch(const std::exception& e){std::cerr<<"MATRIX_PIPELINE_FAIL: "<<e.what()<<std::endl;return 1;}}

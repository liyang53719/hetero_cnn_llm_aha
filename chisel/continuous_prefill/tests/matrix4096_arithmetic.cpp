// SPDX-License-Identifier: Apache-2.0
// Actual retained arithmetic only; no leaf response injection or behavioral MAC.
#include "VMatrix4096ArithmeticProbe.h"
#include "verilated.h"
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

static void check(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
static uint32_t bits(float x){uint32_t u;std::memcpy(&u,&x,4);return u;}
struct Probe {
 VMatrix4096ArithmeticProbe dut;uint64_t cycles=0,checked=0;unsigned request=0;
 std::ofstream csv,actual,reference;
 explicit Probe(const std::filesystem::path& out):csv(out/"all_elements.csv"),actual(out/"actual.f32le",std::ios::binary),reference(out/"reference.f32le",std::ios::binary){
  csv<<"request,mask,row,column,actual_hex,reference_hex\n";
  dut.clock=0;dut.reset=1;dut.io_request_valid=0;dut.io_result_ready=0;
  tick(6);dut.reset=0;tick();
 }
 void tick(unsigned count=1){while(count--){dut.clock=0;dut.eval();dut.clock=1;dut.eval();cycles++;dut.clock=0;dut.eval();}}
 void send(unsigned mask,unsigned k,unsigned depth,bool invalid=false){
  for(unsigned i=0;i<8;i++)dut.io_request_bits_a[i]=0;
  for(unsigned i=0;i<128;i++)dut.io_request_bits_b[i]=0;
  for(unsigned row=0;row<16;row++){
   const float a=float(row+1+k)/16.0f;check((bits(a)&65535)==0,"operand A must be exactly BF16");
   dut.io_request_bits_a[row/2]|=(bits(a)>>16)<<(16*(row%2));
  }
  for(unsigned col=0;col<256;col++){
   const float b=float(int(col)-128)/256.0f;check((bits(b)&65535)==0,"operand B must be exactly BF16");
   dut.io_request_bits_b[col/2]|=(bits(b)>>16)<<(16*(col%2));
  }
  dut.io_request_bits_mask=mask;dut.io_request_bits_opcode=0x20;
  dut.io_request_bits_clear=(k==0);dut.io_request_bits_last=(k+1==depth);
  dut.io_request_valid=1;dut.eval();unsigned watchdog=0;
  while(!dut.io_request_ready&&watchdog++<2000)tick();check(dut.io_request_ready,"request timeout");
  tick();dut.io_request_valid=0;dut.eval();watchdog=0;
  while(!dut.io_result_valid&&watchdog++<2000)tick();check(dut.io_result_valid,"result timeout");
  check(bool(dut.io_result_bits_error)==invalid,"unexpected result status");
 }
 uint32_t word(unsigned n) const {
  const uint32_t* rows[16]={&dut.io_result_bits_data_0[0],&dut.io_result_bits_data_1[0],&dut.io_result_bits_data_2[0],&dut.io_result_bits_data_3[0],&dut.io_result_bits_data_4[0],&dut.io_result_bits_data_5[0],&dut.io_result_bits_data_6[0],&dut.io_result_bits_data_7[0],&dut.io_result_bits_data_8[0],&dut.io_result_bits_data_9[0],&dut.io_result_bits_data_10[0],&dut.io_result_bits_data_11[0],&dut.io_result_bits_data_12[0],&dut.io_result_bits_data_13[0],&dut.io_result_bits_data_14[0],&dut.io_result_bits_data_15[0]};
  return rows[n/256][n%256];
 }
 void consume(){dut.io_result_ready=1;tick();dut.io_result_ready=0;dut.eval();request++;}
 void dot(unsigned mask,unsigned depth,uint64_t& expectedSteps){
  std::array<float,4096> acc{};
  for(unsigned k=0;k<depth;k++){
   send(mask,k,depth);
   std::array<uint32_t,4096> frozen{};
   for(unsigned row=0;row<16;row++)for(unsigned col=0;col<256;col++){
    const unsigned n=row*256+col;const bool selected=(mask>>(col/32))&1;
    if(selected)acc[n]=std::fma(float(row+1+k)/16.0f,float(int(col)-128)/256.0f,acc[n]);
    const uint32_t got=word(n),want=bits(acc[n]);
    check(got==want,"slice/row/column numerical mismatch");frozen[n]=got;
    actual.write(reinterpret_cast<const char*>(&got),4);reference.write(reinterpret_cast<const char*>(&want),4);
    csv<<request<<','<<mask<<','<<row<<','<<col<<','<<std::hex<<std::setfill('0')<<std::setw(8)<<got<<','<<std::setw(8)<<want<<std::dec<<'\n';checked++;
   }
   for(unsigned hold=0;hold<7;hold++){
    tick();check(dut.io_result_valid&&!dut.io_result_bits_error,"result withdrawn under backpressure");
    for(unsigned n=0;n<4096;n++)check(word(n)==frozen[n],"unstable result");
   }
   expectedSteps+=__builtin_popcount(mask);check(dut.io_acceptedSteps==expectedSteps,"actual slice-issue counter");consume();
  }
 }
};
int main(int argc,char**argv){try{
 std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
 check(argc==2,"NEW_OUTPUT_DIRECTORY");std::filesystem::path out(argv[1]);check(!std::filesystem::exists(out),"preserve old outputs");std::filesystem::create_directories(out);
 Probe p(out);uint64_t first=0;
 for(unsigned mask:{255u,1u,128u,85u,170u,15u}){p.dot(mask,4,first);std::cout<<"ARITHMETIC_DOT_PASS mask="<<mask<<" depth=4 checked="<<p.checked<<std::endl;}
 check(first==88,"first epoch steps");p.send(0,0,1,true);check(p.dut.io_resetRequired,"invalid request did not poison");p.consume();
 p.dut.io_request_valid=1;for(unsigned i=0;i<10;i++){p.tick();check(!p.dut.io_request_ready,"lockout failed");}p.dut.io_request_valid=0;
 p.dut.reset=1;p.tick(6);p.dut.reset=0;p.tick();check(!p.dut.io_resetRequired&&p.dut.io_acceptedSteps==0,"reset failed");
 uint64_t second=0;p.dot(255,1,second);check(second==8&&p.checked==102400,"full lane coverage");
 p.csv.flush();p.actual.flush();p.reference.flush();check(p.csv.good()&&p.actual.good()&&p.reference.good(),"output write failed");
 std::cout<<"MATRIX4096_ARITHMETIC_PASS checked_fp32="<<p.checked<<" bit_differences=0 physical_slices=8 all_columns=256 noncontiguous_masks=1 actual_slice_steps="<<first+second<<" same_dut_reset_recovery=1 cycles="<<p.cycles<<std::endl;return 0;
 }catch(const std::exception& e){std::cerr<<"MATRIX4096_ARITHMETIC_FAIL: "<<e.what()<<std::endl;return 1;}}

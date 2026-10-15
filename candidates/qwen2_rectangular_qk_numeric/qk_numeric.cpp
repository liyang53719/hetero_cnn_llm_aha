// SPDX-License-Identifier: Apache-2.0
// ACTUAL_MATRIX_RTL. C++ supplies operands and bounded SRAM ACKs, never results.
#include "VQkNumericProbe.h"
#include "verilated.h"
#include "expected_tail.hpp"
#include <array>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

static void need(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
static bool nan32(uint32_t x){return (x&0x7f800000u)==0x7f800000u && (x&0x007fffffu);}
struct Test {
 VQkNumericProbe d;
 std::array<uint32_t,81920/4> b{}; // exactly the original B allocation, testbench SRAM model
 struct Packet {unsigned tag,epoch,context,bank,word;std::array<uint32_t,8> data;} pending{},held{};
 bool debt=false,holding=false;uint64_t due=0,cycles=0,checked=0,nans=0;
 unsigned kind=0,contexts=5,returned=0,writes=0,acks=0;uint64_t allSteps=0,allAcks=0;
 void eval(){d.clock=0;d.eval();}
 uint32_t tapWord(unsigned r,unsigned c) const {
  const uint32_t* rows[16]={&d.io_tap_bits_data_0[0],&d.io_tap_bits_data_1[0],&d.io_tap_bits_data_2[0],&d.io_tap_bits_data_3[0],
   &d.io_tap_bits_data_4[0],&d.io_tap_bits_data_5[0],&d.io_tap_bits_data_6[0],&d.io_tap_bits_data_7[0],
   &d.io_tap_bits_data_8[0],&d.io_tap_bits_data_9[0],&d.io_tap_bits_data_10[0],&d.io_tap_bits_data_11[0],
   &d.io_tap_bits_data_12[0],&d.io_tap_bits_data_13[0],&d.io_tap_bits_data_14[0],&d.io_tap_bits_data_15[0]};
  return rows[r][c];
 }
 uint32_t expected(unsigned sequence,unsigned r,unsigned c) const {
  if(kind==0)return r==0&&c==0?0x80000000u:0u;
  if(kind==1)return r==0&&c<17?tailExpected[sequence][c]:0u;
  return 0u; // the deliberately nonfinite key16 is checked by classification below
 }
 void checkWord(uint32_t actual,unsigned sequence,unsigned r,unsigned c){
  if(kind>=2 && c==16){need(nan32(actual),"future/selected key16 must contain actual NaN");++nans;}
  else{need(actual==expected(sequence,r,c),"actual Matrix finite FP32 bits differ from frozen expectation");++checked;}
 }
 Packet offered()const {
  Packet p{unsigned(d.io_write_bits_id_tag),unsigned(d.io_write_bits_id_epoch),unsigned(d.io_write_bits_id_context),
   unsigned(d.io_write_bits_id_bank),unsigned(d.io_write_bits_id_word),{}};
  for(unsigned i=0;i<8;++i)p.data[i]=d.io_write_bits_data[i];
  return p;
 }
 static bool same(const Packet&a,const Packet&b){return a.tag==b.tag&&a.epoch==b.epoch&&a.context==b.context&&a.bank==b.bank&&a.word==b.word&&a.data==b.data;}
 void tick(){
  need(cycles<20000,"global 20000-cycle bounded test timeout");
  d.io_write_ready=!debt && cycles%5!=0;
  d.io_ack_valid=debt && cycles>=due;
  if(debt){d.io_ack_bits_id_tag=pending.tag;d.io_ack_bits_id_epoch=pending.epoch;d.io_ack_bits_id_context=pending.context;
   d.io_ack_bits_id_bank=pending.bank;d.io_ack_bits_id_word=pending.word;d.io_ack_bits_error=0;}
  eval();
  if(!d.reset){
   if(d.io_tap_valid){
    need(returned<(kind==3?1:contexts*8),"too many actual Matrix returns");
    need(d.io_tap_bits_context==returned%contexts && bool(d.io_tap_bits_last)==(returned/contexts==7),"actual return context/last order");
    need(!d.io_tap_bits_error,"unexpected service result protocol error");
    for(unsigned r=0;r<16;++r)for(unsigned c=0;c<256;++c)checkWord(tapWord(r,c),returned,r,c);
    ++returned;++allSteps;
   }
   if(holding)need(d.io_write_valid && same(held,offered()),"B request changed under backpressure");
   holding=d.io_write_valid&&!d.io_write_ready;if(holding)held=offered();
   const bool commit=d.io_ack_valid&&d.io_ack_ready;
   const bool accept=d.io_write_valid&&d.io_write_ready;
   if(commit){
    need(debt,"ACK without a real accepted B write");
    for(unsigned i=0;i<8;++i)b[(pending.bank*160+pending.word)*8+i]=pending.data[i];
    debt=false;++acks;++allAcks;
   }
   if(accept){
    need(!debt && kind!=3,"B credit overflow or publication after selected fault");
    Packet p=offered();const unsigned ctx=writes/64,bank=(writes%64)/4,chunk=writes%4;
    need(p.tag==1&&p.epoch==7&&p.context==ctx&&p.bank==bank&&p.word==ctx*32+chunk,"B write identity/address order");
    for(unsigned i=0;i<8;++i)checkWord(p.data[i],35+ctx,p.bank,chunk*8+i);
    pending=p;debt=true;due=cycles+((writes%64==63)?13:3);++writes;
   }
  }
  d.clock=1;d.eval();++cycles;eval();
 }
 void reset(unsigned which){
  kind=which;contexts=which<2?5:1;returned=writes=acks=0;debt=holding=false;b.fill(0x5a5a5a5au);
  d.io_start_valid=0;d.io_operand_valid=0;d.io_done_ready=0;d.io_release_valid=0;d.io_abort=0;d.io_ack_valid=0;
  d.reset=1;for(unsigned i=0;i<6;++i)tick();d.reset=0;tick();
 }
 template<class Predicate>void until(Predicate ready,const char* why){
  unsigned count=0;eval();while(!ready() && count++<4000)tick();need(ready(),why);
 }
 void operands(unsigned ctx,unsigned step){
  const unsigned stripe=(kind<2?0:15)+ctx,j=stripe+16*step;
  d.io_operand_bits_tag=1;d.io_operand_bits_epoch=7;d.io_operand_bits_stripe=stripe;d.io_operand_bits_step=step;
  for(unsigned i=0;i<8;++i)d.io_operand_bits_a[i]=0;
  for(unsigned i=0;i<128;++i)d.io_operand_bits_b[i]=0;
  unsigned a=0;
  if(kind==0)a=j<16?0x0001:0x8000;
  if(kind==1)a=0x3f00+j%7;
  for(unsigned r=0;r<16;++r)d.io_operand_bits_a[r/2]|=a<<(16*(r%2)); // adapter masks padded rows
  for(unsigned c=0;c<256;++c){
   unsigned x=0;
   if(kind==0)x=j<16?0x8001:0x3f80;
   if(kind==1)x=0x3e80+(c+j)%9;
   if(kind>=2 && c==16)x=0x7f80;
   d.io_operand_bits_b[c/2]|=x<<(16*(c%2)); // adapter masks nonexistent keys
  }
 }
 void checkB(){
  for(unsigned bank=0;bank<16;++bank)for(unsigned word=0;word<160;++word)for(unsigned lane=0;lane<8;++lane){
   const bool written=word/32<contexts && word%32<4;
   const auto x=b[(bank*160+word)*8+lane];
   if(written)checkWord(x,35+word/32,bank,(word%32)*8+lane);
   else need(x==0x5a5a5a5au,"write escaped its exact B slot words");
  }
 }
 void run(unsigned which){
  reset(which);const bool error=kind==3;const unsigned count=error?1:contexts*8,wordCount=error?0:contexts*64;
  d.io_start_bits_tag=1;d.io_start_bits_epoch=7;d.io_start_bits_qbase=(kind==1||kind==3)?16:0;
  d.io_start_bits_tokens=kind==0?1:17;d.io_start_bits_stripeBase=kind<2?0:15;
  d.io_start_valid=1;until([&]{return d.io_start_ready;},"start timeout");tick();d.io_start_valid=0;
  for(unsigned n=0;n<count;++n){
   operands(n%contexts,n/contexts);d.io_operand_valid=1;
   until([&]{return d.io_operand_ready;},"operand timeout");tick();d.io_operand_valid=0;
   until([&]{return returned==n+1;},"actual Matrix return timeout");
  }
  until([&]{return d.io_done_valid;},"actual group/store drain timeout");
  need(!debt&&writes==wordCount&&acks==wordCount,"done preceded accepted B write drain");
  need(d.io_done_bits_tag==1&&d.io_done_bits_epoch==7&&bool(d.io_done_bits_error)==error,"owner terminal identity/error");
  need(d.io_returned==count&&d.io_committed==wordCount&&d.io_wideSteps==count&&d.io_sliceSteps==count,"actual step/return/commit counters");
  need(bool(d.io_poisoned)==error,"poison status");
  for(unsigned i=0;i<7;++i){tick();need(d.io_done_valid&&bool(d.io_done_bits_error)==error,"unstable owner terminal");}
  d.io_done_ready=1;tick();d.io_done_ready=0;
  if(!error){
   checkB();d.io_release_bits_tag=1;d.io_release_bits_epoch=7;d.io_release_bits_slots=(1u<<contexts)-1;d.io_release_bits_error=0;
   d.io_release_valid=1;until([&]{return d.io_release_ready;},"slot release timeout");tick();d.io_release_valid=0;
   need(d.io_start_ready&&d.io_slots==0,"verified B consumer release did not free slots");
  }else need(!d.io_start_ready&&d.io_slots==0,"selected nonfinite permitted reuse/publication");
  std::cout<<"QK_NUMERIC_SUBCASE_PASS case="<<kind<<" actual_steps="<<count<<" b_write_acks="<<acks<<"\n";
 }
};
int main(int argc,char**argv){try{
 Verilated::commandArgs(argc,argv);need(argc==1,"no external payloads or run-size options");
 auto t=std::make_unique<Test>();
 t->run(0);t->run(1);t->run(2);t->run(3); // three tests, last test has legal/selected-fault halves
 need(t->allSteps==89&&t->allAcks==704,"fixed total Matrix work/ACKs");
 need(t->checked==375632&&t->nans==176,"fixed full finite/padding and nonfinite comparison coverage");
 std::cout<<"QK_ACTUAL_MATRIX_NUMERIC_PASS tests=3 subcases=4 actual_steps=89 b_write_acks=704 finite_bit_checks="<<t->checked
  <<" nan_class_checks="<<t->nans<<" diagnostic_cycles="<<t->cycles<<" fold_softmax_rtl=0\n";
 return 0;
}catch(const std::exception&e){std::cerr<<"QK_ACTUAL_MATRIX_NUMERIC_FAIL "<<e.what()<<"\n";return 1;}}

// SPDX-License-Identifier: Apache-2.0
#include "VIdmaCommitTailProbe.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
static void ck(bool p,const char*s){if(!p)throw std::runtime_error(s);}
using Words=std::array<uint32_t,16>;
static constexpr uint64_t BASE=0x900008000ULL;
struct Test{
 VIdmaCommitTailProbe d;bool active=false,held=false;uint64_t address=0,id=0,cycles=0,acks=0;
 unsigned left=0,delay=0,count=0;int fault=0;uint32_t rng=100841;
 bool accepted=false,acceptedLast=false,acceptedError=false,acceptedActive=false;Words acceptedData{};uint64_t acceptedTag=0,acceptedCompleted=0,acceptedAcks=0;
 Words previous{};uint64_t oldtag=0;bool oldlast=false,olderr=false;
 uint32_t random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
 Words data(uint64_t a){Words w;for(unsigned i=0;i<16;i++)w[i]=uint32_t((a-BASE)/4+i)^0x47a18931U;return w;}
 Test(){d.reset=1;d.clock=0;d.io_request_valid=0;d.io_result_ready=0;d.io_legacyRequest_valid=0;d.io_legacyResult_ready=0;for(int i=0;i<6;i++)step();d.reset=0;step();}
 void step(){
  d.clock=0;d.io_axi_ar_ready=!active&&random()%3!=0;d.io_axi_aw_ready=1;d.io_axi_w_ready=1;d.io_axi_b_valid=0;d.io_axi_b_bits_id=0;d.io_axi_b_bits_resp=0;
  d.io_axi_r_valid=active&&!delay;d.io_axi_r_bits_id=id+(fault==2&&left==1?1:0);d.io_axi_r_bits_resp=fault==1&&left==1?2:0;d.io_axi_r_bits_last=(left==1)^(fault==3&&left==count&&count>1);
  auto w=data(address);for(unsigned i=0;i<16;i++)d.io_axi_r_bits_data[i]=w[i];d.eval();
  ck(!d.io_axi_aw_valid&&!d.io_axi_w_valid,"read leaked external writes");
  if(held){ck(d.io_result_valid&&d.io_result_bits_tag==oldtag&&d.io_result_bits_last==oldlast&&d.io_result_bits_error==olderr,"stalled response control changed");for(unsigned i=0;i<16;i++)ck(d.io_result_bits_data[i]==previous[i],"stalled response data changed");}
  held=d.io_result_valid&&!d.io_result_ready;
  if(held){oldtag=d.io_result_bits_tag;oldlast=d.io_result_bits_last;olderr=d.io_result_bits_error;for(unsigned i=0;i<16;i++)previous[i]=d.io_result_bits_data[i];}
  accepted=d.io_result_valid&&d.io_result_ready;acceptedLast=d.io_result_bits_last;acceptedError=d.io_result_bits_error;
  acceptedTag=d.io_result_bits_tag;acceptedCompleted=d.io_completed;acceptedAcks=acks;acceptedActive=active;
  for(unsigned i=0;i<16;i++)acceptedData[i]=d.io_result_bits_data[i];
  bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready,ack=d.io_axi_r_valid&&d.io_axi_r_ready;
  if(ar){ck(d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1,"read geometry");address=d.io_axi_ar_bits_addr;id=d.io_axi_ar_bits_id;left=count=d.io_axi_ar_bits_len+1;ck(left<=16&&(address&1023)+left*64<=1024,"read bounds");active=true;delay=4;}
  d.clock=1;d.eval();cycles++;
  if(ack){acks++;if(--left==0)active=false;else{address+=64;delay=2+random()%4;}}
  else if(active&&delay)delay--;
  d.clock=0;d.eval();
 }
 void reset(){ck(!active,"reset before external drain");held=false;d.io_result_ready=0;d.reset=1;for(int i=0;i<6;i++)step();d.reset=0;step();fault=0;}
 void stream(unsigned beats,unsigned offset,unsigned seed,int f=0){
  fault=f;uint64_t tx=d.io_transfers,done=d.io_completed,rd=acks,start=cycles;unsigned got=0;bool forwarded=false;
  d.io_request_bits_address=BASE+offset;d.io_request_bits_beats=beats;d.io_request_bits_tag=seed;d.io_request_valid=1;d.io_result_ready=0;
  ck(d.io_request_ready,"request not ready");step();d.io_request_valid=0;
  while(got<beats&&cycles-start<4000){
   d.io_result_ready=random()%4!=0;step();
   if(accepted){
    ck(acceptedTag==seed&&acceptedLast==(got+1==beats),"stream identity");
    if(got+1==beats){if(!(acceptedCompleted==done+1&&acceptedAcks==rd+beats&&!acceptedActive))std::cerr<<"TAIL_DEBUG beats="<<beats<<" completed="<<acceptedCompleted<<" expected="<<done+1<<" acks="<<acceptedAcks<<" expectedacks="<<rd+beats<<" active="<<acceptedActive<<" error="<<acceptedError<<" cycles="<<cycles<<std::endl;ck(acceptedCompleted==done+1&&acceptedAcks==rd+beats&&!acceptedActive,"last released before real backend commit");ck(acceptedError==bool(f),"late fault was hidden");}
    else{if(acceptedCompleted==done)forwarded=true;ck(!acceptedError,"prefix status changed by later beat");}
    if(!(f&&got+1==beats)){auto x=data(BASE+offset+64*got);for(unsigned i=0;i<16;i++)ck(acceptedData[i]==x[i],"stream payload corruption");}
    got++;
   }
  }
  ck(got==beats&&d.io_transfers==tx+1,"incomplete stream");if(beats>1)ck(forwarded,"no prefix forwarding observed");
  d.io_result_ready=0;
  if(f){ck(d.io_resetRequired&&!d.io_request_ready,"late fault did not quarantine");reset();}else ck(!d.io_resetRequired&&d.io_request_ready,"healthy stream not reusable");
  std::cout<<"COMMIT_TAIL_CASE_PASS beats="<<beats<<" mode="<<f<<" cycles="<<cycles-start<<" checked_words="<<beats*16<<" prefix_forwarded="<<forwarded<<" last_after_backend_commit=1"<<std::endl;
 }
 void legacy(){auto done=d.io_completed;d.io_legacyRequest_bits_address=BASE+2048;d.io_legacyRequest_bits_write=0;d.io_legacyRequest_bits_mask=0;d.io_legacyRequest_bits_tag=99;d.io_legacyRequest_valid=1;d.io_legacyResult_ready=0;
  ck(d.io_legacyRequest_ready,"legacy not ready");step();d.io_legacyRequest_valid=0;unsigned n=0;while(!d.io_legacyResult_valid&&n++<300)step();ck(d.io_legacyResult_valid&&d.io_completed==done+1&&!active&&!d.io_legacyResult_bits_error,"legacy read speculated");auto x=data(BASE+2048);for(unsigned i=0;i<16;i++)ck(d.io_legacyResult_bits_data[i]==x[i],"legacy payload");d.io_legacyResult_ready=1;step();d.io_legacyResult_ready=0;}
};
int main(int argc,char**argv){try{Verilated::commandArgs(argc,argv);auto t=std::make_unique<Test>();unsigned seed=1;
 for(unsigned n:{1,2,4,8,16})t->stream(n,1024-n*64,seed++);
 for(int f:{1,2,3}){t->stream(16,1024,seed++,f);t->stream(16,1024,seed++);}
 t->legacy();std::cout<<"COMMIT_TAIL_READ_PASS stream_cases=11 late_fault_resets=3 legacy_case=1 real_idma=1 same_dut=1 last_is_commit_barrier=1"<<std::endl;return 0;
}catch(const std::exception&e){std::cerr<<"COMMIT_TAIL_READ_FAIL: "<<e.what()<<std::endl;return 1;}}

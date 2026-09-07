// SPDX-License-Identifier: Apache-2.0
// Test service: AXI memory only, all transfers run through the real pinned iDMA.
#include "VIdmaWeightBurstProbe.h"
#include "verilated.h"
#include <array>
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
static void check(bool yes,const std::string& m){if(!yes)throw std::runtime_error(m);}
using Data=std::array<uint32_t,16>;
struct Address{bool valid=false;uint64_t addr=0;unsigned id=0,len=0;};
struct Read{bool valid=false;uint64_t addr=0;unsigned id=0,left=0,total=0,delay=0,index=0;Data data{};};
class Bench{
 public:
 VIdmaWeightBurstProbe d;std::map<uint64_t,Data> memory;
 uint64_t cycles=0,ar=0,r=0,aw=0,w=0,b=0,tag=100;uint32_t rng=12345;
 bool stalls=true;Address awq;Data wq{};bool wvalid=false;uint64_t wmask=0;
 Read rq;bool bvalid=false;unsigned bid=0,bdelay=0;
 std::string fault;unsigned faultBeat=0;bool injected=false;
 uint32_t random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
 Data get(uint64_t a){auto i=memory.find(a);if(i!=memory.end())return i->second;Data x;for(unsigned j=0;j<16;j++){uint64_t q=a/4+j;x[j]=uint32_t((q*0x9e3779b9ULL)^(q>>9));}return x;}
 void reset(){
  d.io_request_valid=0;d.io_response_ready=0;d.io_window_enable=0;d.io_window_base=0;d.io_window_limit=0;d.io_flush=0;
  d.reset=1;for(int i=0;i<5;i++)step();d.reset=0;for(int i=0;i<3;i++)step();
  check(!d.io_resetRequired&&d.io_request_ready,"reset did not recover");
 }
 Bench(){reset();}
 void step(){
  d.clock=0;
  d.io_axi_ar_ready=!rq.valid&&!awq.valid&&!wvalid&&!bvalid&&(!stalls||random()%3!=0);
  d.io_axi_aw_ready=!rq.valid&&!awq.valid&&!bvalid&&(!stalls||random()%3!=0);
  d.io_axi_w_ready=!rq.valid&&!wvalid&&!bvalid&&(!stalls||random()%4!=0);
  d.io_axi_r_valid=rq.valid&&rq.delay==0;d.io_axi_r_bits_id=rq.id;
  d.io_axi_r_bits_resp=0;d.io_axi_r_bits_last=rq.left==1;
  if(rq.valid && rq.index==faultBeat && !fault.empty()){
   if(fault=="rresp")d.io_axi_r_bits_resp=2;
   if(fault=="rid")d.io_axi_r_bits_id=rq.id^1;
   if(fault=="rlast")d.io_axi_r_bits_last=!(rq.left==1);
  }
  for(unsigned i=0;i<16;i++)d.io_axi_r_bits_data[i]=rq.data[i];
  d.io_axi_b_valid=bvalid&&bdelay==0;d.io_axi_b_bits_id=bid;d.io_axi_b_bits_resp=fault=="bresp"?2:0;
  d.eval();
  bool arF=d.io_axi_ar_valid&&d.io_axi_ar_ready,awF=d.io_axi_aw_valid&&d.io_axi_aw_ready;
  bool wF=d.io_axi_w_valid&&d.io_axi_w_ready,rF=d.io_axi_r_valid&&d.io_axi_r_ready,bF=d.io_axi_b_valid&&d.io_axi_b_ready;
  Address na;
  if(arF){
   check(d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1,"AR format");
   auto a=uint64_t(d.io_axi_ar_bits_addr);unsigned n=d.io_axi_ar_bits_len+1;
   check((a&63)==0&&n<=16&&((a&4095)+n*64)<=4096,"AR bounds/4KiB");
   if(n>1)check(d.io_window_enable&&a>=d.io_window_base&&a+n*64<=d.io_window_limit,"prefetch escaped validated tensor");
   na={true,a,unsigned(d.io_axi_ar_bits_id),n};++ar;if(std::getenv("IDMA_TRACE"))std::cout<<"AR "<<std::hex<<a<<std::dec<<" beats="<<n<<" cycles="<<cycles<<std::endl;
  }
  if(awF){check(d.io_axi_aw_bits_len==0&&d.io_axi_aw_bits_size<=6,"write changed to unsupported burst");awq={true,d.io_axi_aw_bits_addr,unsigned(d.io_axi_aw_bits_id),1};++aw;}
  if(wF){check(d.io_axi_w_bits_last,"WLAST");for(unsigned i=0;i<16;i++)wq[i]=d.io_axi_w_bits_data[i];wmask=d.io_axi_w_bits_strb;wvalid=true;++w;}
  d.clock=1;d.eval();++cycles;
  if(rF){
   ++r;if(rq.index==faultBeat&&!fault.empty())injected=true;
   if(--rq.left==0)rq={};else{rq.addr+=64;++rq.index;rq.data=get(rq.addr);rq.delay=stalls?random()%4:0;}
  }else if(rq.valid&&rq.delay)--rq.delay;
  if(bF){++b;bvalid=false;if(fault=="bresp")injected=true;}
  else if(bvalid&&bdelay)--bdelay;
  if(na.valid){check(!rq.valid,"more than one source burst outstanding");rq={true,na.addr,na.id,na.len,na.len,stalls?1+random()%4:0,0,get(na.addr)};}
  if(awq.valid&&wvalid&&!bvalid){
   auto old=get(awq.addr);auto dst=reinterpret_cast<unsigned char*>(old.data());auto src=reinterpret_cast<const unsigned char*>(wq.data());
   for(unsigned i=0;i<64;i++)if((wmask>>i)&1)dst[i]=src[i];
   if(fault!="bresp")memory[awq.addr]=old;
   bid=awq.id;bvalid=true;bdelay=stalls?1+random()%4:0;awq={};wvalid=false;
  }
  d.clock=0;d.eval();
 }
 void window(uint64_t a,uint64_t end,bool enable=true){
  d.io_flush=1;step();d.io_flush=0;d.io_window_enable=enable;d.io_window_base=a;d.io_window_limit=end;step();
 }
 Data transfer(uint64_t address,bool write=false,uint64_t mask=~0ULL,bool expectError=false){
  d.io_request_valid=1;d.io_request_bits_address=address;d.io_request_bits_write=write;d.io_request_bits_mask=mask;d.io_request_bits_tag=++tag;
  Data x;for(unsigned i=0;i<16;i++){x[i]=uint32_t(tag*257+i);d.io_request_bits_data[i]=x[i];}
  unsigned watchdog=0;while(!d.io_request_ready){step();check(++watchdog<30000,"request timeout");}
  step();d.io_request_valid=0;
  while(!d.io_response_valid){step();check(++watchdog<30000,"response timeout");}
  Data y;for(unsigned i=0;i<16;i++)y[i]=d.io_response_bits_data[i];
  check(d.io_response_bits_tag==tag&&bool(d.io_response_bits_error)==expectError,"response identity/error addr="+std::to_string(address)+" tag="+std::to_string(tag)+" observed="+std::to_string(d.io_response_bits_tag)+" error="+std::to_string(d.io_response_bits_error)+" expected="+std::to_string(expectError));
  for(unsigned k=0;k<4;k++){step();check(d.io_response_valid&&d.io_response_bits_tag==tag,"response not held");for(unsigned i=0;i<16;i++)check(d.io_response_bits_data[i]==y[i],"response data changed");}
  if(expectError){check(d.io_resetRequired,"fault not quarantined");for(auto v:y)check(v==0,"failed burst leaked payload");}
  else if(!write)check(y==get(address),"numerical payload mismatch");
  d.io_response_ready=1;step();d.io_response_ready=0;step();
  if(expectError)check(!d.io_request_ready,"fault escaped after response");
  check(!rq.valid&&!bvalid&&!awq.valid&&!wvalid,"response before AXI drained");return y;
 }
};
int main(int argc,char**argv){try{
 Verilated::commandArgs(argc,argv);unsigned cases=0;
 uint64_t one=0,burst=0;
 for(bool enable:{false,true}){
  auto t=std::make_unique<Bench>();t->stalls=false;t->window(0x100000400ULL,0x100004400ULL,enable);
  auto start=t->cycles;for(unsigned i=0;i<256;i++)t->transfer(0x100000400ULL+64*i);
  auto elapsed=t->cycles-start;if(enable)burst=elapsed;else one=elapsed;
  check(t->d.io_readBeats==256&&t->d.io_transfers==(enable?16:256)&&t->d.io_cacheHits==(enable?240:0),"burst accounting");
  std::cout<<"BURST_BENCH enabled="<<enable<<" cycles="<<elapsed<<" beats="<<t->r<<" transfers="<<t->d.io_transfers<<" hits="<<t->d.io_cacheHits<<std::endl;++cases;
 }
 check(burst<one,"read burst did not improve measured supply");
 for(unsigned tail:{1u,2u,7u,15u,16u,17u,31u,33u}){
  std::cout<<"TAIL_CASE "<<tail<<std::endl;auto t=std::make_unique<Bench>();const uint64_t a=0x100000fc0ULL;t->window(a,a+tail*64);
  for(unsigned i=0;i<tail;i++)t->transfer(a+i*64);check(t->r==tail,"tail overfetch");
  ++cases;
 }
 {auto t=std::make_unique<Bench>();uint64_t a=0x100001000ULL;t->window(a,a+1024);t->transfer(a);auto x=t->get(a);x[3]^=17;t->memory[a]=x;t->window(a,a+1024);t->transfer(a);check(t->d.io_transfers==2,"flush did not invalidate old data");++cases;}
 {auto t=std::make_unique<Bench>();uint64_t a=0x100002000ULL;t->window(a,a+1024);t->transfer(a);t->transfer(a,true);t->transfer(a);check(t->d.io_transfers==3,"store did not invalidate cached line");++cases;}
 for(auto mode:{"rresp","rid","rlast"})for(unsigned position:{0u,7u,15u}){
  auto t=std::make_unique<Bench>();uint64_t a=0x100001000ULL;t->window(a,a+1024);t->fault=mode;t->faultBeat=position;t->transfer(a,false,~0ULL,true);
  check(t->injected&&t->r==16&&t->d.io_cacheHits==0,"bad burst was not fully drained");
  t->fault.clear();t->reset();t->window(a,a+1024);for(unsigned i=0;i<16;i++)t->transfer(a+64*i);++cases;
 }
 {auto t=std::make_unique<Bench>();t->fault="bresp";t->transfer(0x100001000ULL,true,~0ULL,true);check(t->injected,"write fault absent");t->fault.clear();t->reset();t->transfer(0x100001000ULL,true);++cases;}
 for(uint64_t a:{uint64_t(0x100001001ULL),uint64_t(1ULL<<56)}){auto t=std::make_unique<Bench>();t->transfer(a,false,~0ULL,true);check(t->ar==0&&t->aw==0,"illegal request reached AXI");++cases;}
 std::cout<<"IDMA_WEIGHT_BURST_PASS cases="<<cases<<" real_pinned_idma=1 max_beats=16 mailbox_bytes=1024 supply_cycles_single="<<one<<" supply_cycles_burst="<<burst<<" data_mismatches=0"<<std::endl;
 return 0;
 }catch(const std::exception&e){std::cerr<<"IDMA_WEIGHT_BURST_FAIL: "<<e.what()<<std::endl;return 1;}}

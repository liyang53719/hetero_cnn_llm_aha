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
 unsigned forcedBDelay=0;uint64_t heldBCycles=0,writeBStart=0,lastWriteAddress=0,lastWriteMask=0;
 bool checkWriteFence=false,writeInFlight=false;
 std::string fault;unsigned faultBeat=0;bool injected=false;
 uint32_t random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
 Data get(uint64_t a){auto i=memory.find(a);if(i!=memory.end())return i->second;Data x;for(unsigned j=0;j<16;j++){uint64_t q=a/4+j;x[j]=uint32_t((q*0x9e3779b9ULL)^(q>>9));}return x;}
 void reset(){
  d.io_request_valid=0;d.io_response_ready=0;d.io_window_enable=0;d.io_window_base=0;d.io_window_limit=0;d.io_flush=0;
#ifdef IDMA_STREAMING_PROBE
  d.io_streamRequest_valid=0;d.io_streamResponse_ready=1;
#endif
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
  if(writeInFlight&&b==writeBStart&&!bF)check(!d.io_response_valid,"store ACK before final B handshake");
  if(bvalid&&bdelay)++heldBCycles;
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
   lastWriteAddress=awq.addr;lastWriteMask=wmask;
   auto old=get(awq.addr);auto dst=reinterpret_cast<unsigned char*>(old.data());auto src=reinterpret_cast<const unsigned char*>(wq.data());
   for(unsigned i=0;i<64;i++)if((wmask>>i)&1)dst[i]=src[i];
   if(fault!="bresp")memory[awq.addr]=old;
   bid=awq.id;bvalid=true;bdelay=forcedBDelay?forcedBDelay:(stalls?1+random()%4:0);awq={};wvalid=false;
  }
  d.clock=0;d.eval();
 }
 void window(uint64_t a,uint64_t end,bool enable=true){
  d.io_flush=1;step();d.io_flush=0;d.io_window_enable=enable;d.io_window_base=a;d.io_window_limit=end;step();
 }
 Data transfer(uint64_t address,bool write=false,uint64_t mask=~0ULL,bool expectError=false,const Data* writeData=nullptr){
  d.io_request_valid=1;d.io_request_bits_address=address;d.io_request_bits_write=write;d.io_request_bits_mask=mask;d.io_request_bits_tag=++tag;
  Data x;for(unsigned i=0;i<16;i++){x[i]=writeData?(*writeData)[i]:uint32_t(tag*257+i);d.io_request_bits_data[i]=x[i];}
  unsigned watchdog=0;while(!d.io_request_ready){step();check(++watchdog<30000,"request timeout");}
  writeInFlight=write&&checkWriteFence;writeBStart=b;
  step();d.io_request_valid=0;
  while(!d.io_response_valid){step();check(++watchdog<30000,"response timeout");}
  if(writeInFlight)check(b==writeBStart+1,"store completed without final B");
  Data y;for(unsigned i=0;i<16;i++)y[i]=d.io_response_bits_data[i];
  check(d.io_response_bits_tag==tag&&bool(d.io_response_bits_error)==expectError,"response identity/error addr="+std::to_string(address)+" tag="+std::to_string(tag)+" observed="+std::to_string(d.io_response_bits_tag)+" error="+std::to_string(d.io_response_bits_error)+" expected="+std::to_string(expectError));
  for(unsigned k=0;k<4;k++){step();check(d.io_response_valid&&d.io_response_bits_tag==tag&&bool(d.io_response_bits_error)==expectError,"response not held");for(unsigned i=0;i<16;i++)check(d.io_response_bits_data[i]==y[i],"response data changed");}
  if(expectError){check(d.io_resetRequired,"fault not quarantined");for(auto v:y)check(v==0,"failed burst leaked payload");}
  else if(!write)check(y==get(address),"numerical payload mismatch");
  d.io_response_ready=1;step();d.io_response_ready=0;step();
  writeInFlight=false;
  if(expectError)check(!d.io_request_ready,"fault escaped after response");
  check(!rq.valid&&!bvalid&&!awq.valid&&!wvalid,"response before AXI drained");return y;
 }
};
// Pack two distinct 16-column BF16 tiles in the exact little-endian full-beat
// format used by recurrent output stores. Every lane has a different payload.
static Data bf16Pair(unsigned pair){
 Data x{};for(unsigned lane=0;lane<32;++lane){
  const uint16_t value=uint16_t((lane<16?0x3e00:0xbe80)+pair*3+lane);
  x[lane/2]|=uint32_t(value)<<((lane%2)*16);
 }return x;
}
static void seedOutputWithGuards(Bench& t,uint64_t base){
 // Full production-sized 16-head x 128-column BF16 output and two guard beats.
 for(unsigned beat=0;beat<66;++beat){const auto a=base-64+beat*64;t.memory[a]=t.get(a);}
}
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
 check(cases==24,"original burst probe coverage changed");
 const uint64_t outputBase=0x100040000ULL,tailAddress=outputBase+63*64;
 {auto t=std::make_unique<Bench>();seedOutputWithGuards(*t,outputBase);const auto before=t->memory;const auto data=bf16Pair(63);
  t->transfer(tailAddress,true,0xffffffff00000000ULL,true,&data);
  check(!t->ar&&!t->r&&!t->aw&&!t->w&&!t->b&&!t->d.io_transfers,"old recurrent high-half mask reached AXI");
  check(t->memory==before,"rejected high-half mask mutated output/guards");
  check(t->d.io_resetRequired&&!t->d.io_request_ready,"high-half mask did not remain quarantined");
  std::cout<<"RECURRENT_MASK_CASE high32_rejected=1 zero_axi=1 memory_unchanged=1 reset_required=1"<<std::endl;++cases;
 }
 {auto t=std::make_unique<Bench>();seedOutputWithGuards(*t,outputBase);auto expected=t->memory;const auto data=bf16Pair(63);
  for(unsigned i=0;i<8;++i)expected[tailAddress][i]=data[i];
  t->transfer(tailAddress,true,0x00000000ffffffffULL,false,&data);
  check(t->memory==expected,"low-prefix32 store changed high half, another pair, or guards");
  check(t->ar==0&&t->aw==1&&t->w==1&&t->b==1&&t->lastWriteAddress==tailAddress&&t->lastWriteMask==0xffffffffULL,"low-prefix32 AXI shape");
  std::cout<<"RECURRENT_MASK_CASE low32_accepted=1 high32_preserved=1 guards_preserved=1"<<std::endl;++cases;
 }
 for(unsigned pair:{0u,31u,63u}){
  auto t=std::make_unique<Bench>();seedOutputWithGuards(*t,outputBase);auto expected=t->memory;
  const uint64_t a=outputBase+pair*64;const auto data=bf16Pair(pair);expected[a]=data;
  t->transfer(a,true,~0ULL,false,&data);
  check(t->memory==expected,"paired BF16 full64 store payload/address/guards");
  check(t->ar==0&&t->aw==1&&t->w==1&&t->b==1&&t->lastWriteAddress==a&&t->lastWriteMask==~0ULL,"paired BF16 full64 AXI shape");
  std::cout<<"RECURRENT_PAIR_CASE pair="<<pair<<" bf16_lanes=32 bytes=64 guards_preserved=1"<<std::endl;++cases;
 }
 for(bool error:{false,true}){
  auto t=std::make_unique<Bench>();seedOutputWithGuards(*t,outputBase);const auto before=t->memory;const auto data=bf16Pair(63);
  t->stalls=false;t->forcedBDelay=40;t->checkWriteFence=true;if(error)t->fault="bresp";
  t->transfer(tailAddress,true,~0ULL,error,&data);
  check(t->heldBCycles>=40&&t->b==1&&t->aw==1&&t->w==1,"final B delay was not exercised");
  check(t->memory.at(outputBase-64)==before.at(outputBase-64)&&t->memory.at(outputBase+4096)==before.at(outputBase+4096),"delayed B changed guards");
  if(error)check(t->injected&&t->d.io_resetRequired&&!t->d.io_request_ready,"final B error escaped quarantine");
  else{auto expected=before;expected[tailAddress]=data;check(t->memory==expected&&!t->d.io_resetRequired,"delayed B successful store");}
  std::cout<<"RECURRENT_B_FENCE_CASE error="<<error<<" held_cycles="<<t->heldBCycles<<" early_ack=0 response_backpressure_cycles=4"<<std::endl;++cases;
 }
 check(cases==31,"recurrent mask/fence coverage");
#ifdef IDMA_STREAMING_PROBE
 const unsigned streaming=1;
#else
 const unsigned streaming=0;
#endif
 std::cout<<"IDMA_WEIGHT_BURST_PASS cases="<<cases<<" real_pinned_idma=1 max_beats=16 mailbox_bytes=1024 streaming="<<streaming<<" high32_reject_cases=1 low32_prefix_cases=1 paired_bf16_cases=3 final_b_fence_cases=2 supply_cycles_single="<<one<<" supply_cycles_burst="<<burst<<" data_mismatches=0"<<std::endl;
 return 0;
 }catch(const std::exception&e){std::cerr<<"IDMA_WEIGHT_BURST_FAIL: "<<e.what()<<std::endl;return 1;}}

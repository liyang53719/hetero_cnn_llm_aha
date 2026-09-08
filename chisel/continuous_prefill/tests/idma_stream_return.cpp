// SPDX-License-Identifier: Apache-2.0
// Transport verification only. The DUT contains the actual pinned iDMA. The
// test supplies AXI memory; it never computes an NPU operator or inserts data
// into the internal mailbox. Identical timing for replay and cut-through.
#include "VIdmaStreamReturnProbe.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
using Data=std::array<uint32_t,16>;
static void check(bool x,const std::string& s){if(!x)throw std::runtime_error(s);}
static Data payload(uint64_t a){Data x{};for(unsigned i=0;i<16;i++)x[i]=uint32_t((a/4+i)*0x9e3779b9ULL) ^ uint32_t(a>>32);return x;}
struct Bench {
 VIdmaStreamReturnProbe d;bool ct,randomTiming=false,rx=false,injected=false;
 uint64_t cycles=0,readCount=0,bursts=0,tag=100,addr=0;unsigned left=0,index=0,delay=0,faultAt=0,id=0;
 uint32_t rng=20260908;std::string fault;
 explicit Bench(bool cut):ct(cut){reset();}
 uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
 void reset(){check(!rx,"reset before external drain");d.io_request_valid=0;d.io_response_ready=0;d.io_streamRequest_valid=0;d.io_streamResponse_ready=0;d.io_flush=0;d.io_window_enable=0;d.io_window_base=0;d.io_window_limit=0;d.reset=1;for(unsigned i=0;i<6;i++)step();d.reset=0;step();check(d.io_streamRequest_ready&&!d.io_resetRequired,"reset did not recover");}
 void step(){
  d.clock=0;d.io_axi_ar_ready=!rx&&(!randomTiming||next()%4!=0);
  d.io_axi_aw_ready=0;d.io_axi_w_ready=0;d.io_axi_b_valid=0;
  d.io_axi_r_valid=rx&&delay==0;d.io_axi_r_bits_id=id;d.io_axi_r_bits_last=left==1;d.io_axi_r_bits_resp=0;
  if(rx&&index==faultAt){if(fault=="resp")d.io_axi_r_bits_resp=2;if(fault=="id")d.io_axi_r_bits_id=id^1;if(fault=="last")d.io_axi_r_bits_last=left!=1;}
  auto data=payload(addr);for(unsigned i=0;i<16;i++)d.io_axi_r_bits_data[i]=data[i];d.eval();
  const bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready,rf=d.io_axi_r_valid&&d.io_axi_r_ready;
  const uint64_t a=d.io_axi_ar_bits_addr;const unsigned n=d.io_axi_ar_bits_len+1,aid=d.io_axi_ar_bits_id;
  if(ar){check(!rx,"multiple outstanding read bursts");check(d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1&&n<=16&&((a&1023)+n*64)<=1024,"bad burst");}
  check(!d.io_axi_aw_valid&&!d.io_axi_w_valid,"read escaped onto external write port");
  d.clock=1;d.eval();++cycles;
  if(rf){++readCount;if(!fault.empty()&&index==faultAt)injected=true;if(--left==0)rx=false;else{addr+=64;++index;delay=randomTiming?next()%4:0;}}
  else if(rx&&delay)--delay;
  if(ar){addr=a;left=n;index=0;id=aid;rx=true;delay=randomTiming?1+next()%4:0;++bursts;}
  d.clock=0;d.eval();
 }
 Data result(){Data x;for(unsigned i=0;i<16;i++)x[i]=d.io_streamResponse_bits_data[i];return x;}
 uint64_t transfer(uint64_t a,unsigned n,bool hold=false,const std::string& error="",unsigned at=0,bool invalid=false){
  check(!rx&&!d.io_resetRequired,"not idle");fault=error;faultAt=at;injected=false;uint64_t oldReads=readCount,oldBursts=bursts,start=cycles;
  d.io_streamRequest_valid=1;d.io_streamRequest_bits_address=a;d.io_streamRequest_bits_beats=n;d.io_streamRequest_bits_tag=++tag;d.io_streamResponse_ready=0;
  unsigned watchdog=0;while(!d.io_streamRequest_ready){step();check(++watchdog<10000,"request timeout");}
  step();d.io_streamRequest_valid=0;unsigned received=0;uint64_t first=0;const unsigned expected=invalid?1:n;
  while(received<expected){
   d.io_streamResponse_ready=0;while(!d.io_streamResponse_valid){step();check(++watchdog<10000,"response timeout");}
   const auto bits=result();const bool last=d.io_streamResponse_bits_last,err=d.io_streamResponse_bits_error;
   check(d.io_streamResponse_bits_tag==tag&&last==(received+1==expected),"tag/last mismatch");
   if(received==0){first=cycles-start;if(ct&&n==16&&!randomTiming&&!invalid&&!hold)check(readCount-oldReads<n,"cut-through prefix waited for entire burst");}
   if(hold&&received==0){for(unsigned j=0;j<40;j++){step();check(d.io_streamResponse_valid&&d.io_streamResponse_bits_tag==tag&&bool(d.io_streamResponse_bits_last)==last&&bool(d.io_streamResponse_bits_error)==err&&result()==bits,"response changed under backpressure/late failure");}}
   if(!invalid&&error.empty())check(!err&&bits==payload(a+received*64),"data mismatch");
   if(last){check(!rx,"LAST before external drain");check(err==(!error.empty()||invalid),"transaction commit/error mismatch");}
   // A failed prefix need not be rolled back. Consumers cannot publish it:
   // successful LAST alone commits the complete staged burst.
   d.io_streamResponse_ready=1;step();++received;
  }
  d.io_streamResponse_ready=0;step();
  check(readCount-oldReads==(invalid?0:n)&&bursts-oldBursts==(invalid?0:1),"physical read count");
  if(!error.empty()||invalid){check(d.io_resetRequired&&!d.io_streamRequest_ready,"failure not quarantined");check(invalid||injected,"fault not reached");}
  else check(!d.io_resetRequired&&d.io_streamRequest_ready,"healthy stream not reusable");
  auto elapsed=cycles-start;
  std::cout<<"IDMA_STREAM_CASE cut="<<ct<<" beats="<<n<<" first="<<first<<" cycles="<<elapsed<<" fault="<<(error.empty()?"none":error)<<" position="<<at<<" invalid="<<invalid<<" hold="<<hold<<" random="<<randomTiming<<"\n";
  return elapsed;
 }
};
int main(int argc,char**argv){try{
 Verilated::commandArgs(argc,argv);check(argc==2,"cut-through flag required");bool ct=std::string(argv[1])=="1";Bench t(ct);unsigned cases=0;uint64_t bench=0;
 for(unsigned n:{1u,2u,3u,8u,15u,16u}){bench+=t.transfer(0x100000400ULL,n);++cases;}
 t.randomTiming=true;
 for(unsigned i=0;i<50;i++){unsigned n=1+(i*7)%16;auto a=0x10000000000400ULL+1024*(i%7);t.transfer(a,n,i%3==0);++cases;}
 for(auto mode:{"resp","id","last"})for(unsigned at:{0u,7u,15u}){t.transfer(0x100008000ULL,16,true,mode,at);++cases;t.fault.clear();t.reset();t.transfer(0x100008000ULL,16);++cases;}
 for(auto item:{std::pair<uint64_t,unsigned>(0x100004001ULL,8),{0x1000043c0ULL,2},{1ULL<<56,1},{0x100004000ULL,0},{0x100004000ULL,17}}){t.transfer(item.first,item.second,false,"",0,true);++cases;t.reset();}
 check(cases==79,"missing cases");std::cout<<"IDMA_STREAM_RETURN_PASS cut="<<ct<<" cases="<<cases<<" numerical_mismatches=0 late_errors=9 protocol_rejections=5 physical_idma=1 sequential_supply_cycles="<<bench<<"\n";return 0;
 }catch(const std::exception&e){std::cerr<<"IDMA_STREAM_RETURN_FAIL "<<e.what()<<"\n";return 1;}}

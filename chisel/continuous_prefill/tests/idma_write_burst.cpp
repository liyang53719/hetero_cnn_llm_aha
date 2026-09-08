// SPDX-License-Identifier: Apache-2.0
// Only AXI memory transport is modeled here. All DMA data crosses real RTL.
#include "VIdmaBurstWriteProbe.h"
#include "verilated.h"
#include <array>
#include <vector>
#include <memory>
#include <stdexcept>
#include <iostream>
#include <cstdint>
static void check(bool p,const char*s){if(!p)throw std::runtime_error(s);}
using Words=std::array<uint32_t,16>;
static constexpr uint64_t BASE=0x200004000ULL;
struct Test {
 VIdmaBurstWriteProbe d;
 std::vector<uint32_t> mem=std::vector<uint32_t>(4096/4,0xa5a5a5a5);
 std::vector<Words> wdata;std::vector<bool> wlast;
 bool aw=false,bvalid=false,rvalid=false;unsigned awbeats=0,bdelay=0,rd=0;
 uint64_t awaddr=0,bid=0,rid=0,cycles=0,awCount=0,arCount=0,acks=0;
 uint32_t rng=90851;int fault=0;Words rdata{};
 uint32_t random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
 Test(){d.clock=0;d.reset=1;d.io_request_valid=0;d.io_data_valid=0;d.io_response_ready=0;d.io_legacyRequest_valid=0;d.io_legacyResponse_ready=0;for(int i=0;i<6;i++)step();d.reset=0;step();}
 size_t pos(uint64_t a){check(a>=BASE && a+64<=BASE+4096 && !(a&63),"AXI address outside arena");return (a-BASE)/4;}
 void step(){
  d.clock=0;
  d.io_axi_aw_ready=!aw&&!bvalid&&!rvalid&&random()%4!=0;
  d.io_axi_w_ready=!bvalid&&!rvalid&&wdata.size()<16&&random()%3!=0;
  d.io_axi_ar_ready=!aw&&wdata.empty()&&!bvalid&&!rvalid&&random()%4!=0;
  d.io_axi_b_valid=bvalid&&bdelay==0;d.io_axi_b_bits_id=bid+(fault==2?1:0);d.io_axi_b_bits_resp=fault==1?2:0;
  d.io_axi_r_valid=rvalid&&rd==0;d.io_axi_r_bits_id=rid;d.io_axi_r_bits_resp=0;d.io_axi_r_bits_last=1;
  for(int i=0;i<16;i++)d.io_axi_r_bits_data[i]=rdata[i];d.eval();
  bool af=d.io_axi_aw_valid&&d.io_axi_aw_ready,wf=d.io_axi_w_valid&&d.io_axi_w_ready,ar=d.io_axi_ar_valid&&d.io_axi_ar_ready;
  bool bf=d.io_axi_b_valid&&d.io_axi_b_ready,rf=d.io_axi_r_valid&&d.io_axi_r_ready;
  if(af){aw=true;awaddr=d.io_axi_aw_bits_addr;bid=d.io_axi_aw_bits_id;awbeats=d.io_axi_aw_bits_len+1;awCount++;
   check(awbeats>=1&&awbeats<=16&&d.io_axi_aw_bits_size==6&&d.io_axi_aw_bits_burst==1,"write geometry");
   check((awaddr&1023)+64*awbeats<=1024,"write crossed 1KiB");pos(awaddr+64*(awbeats-1));}
  if(wf){Words x;for(int i=0;i<16;i++)x[i]=d.io_axi_w_bits_data[i];wdata.push_back(x);wlast.push_back(d.io_axi_w_bits_last);check(d.io_axi_w_bits_strb==~uint64_t(0),"wrong write mask");}
  if(ar){arCount++;check(d.io_axi_ar_bits_len==0&&d.io_axi_ar_bits_size==6,"legacy read geometry");rid=d.io_axi_ar_bits_id;for(int i=0;i<16;i++)rdata[i]=mem[pos(d.io_axi_ar_bits_addr)+i];rvalid=true;rd=2+random()%5;}
  if(d.io_response_valid)check(!aw&&!bvalid&&wdata.empty(),"early successful or error response before B drain");
  d.clock=1;d.eval();cycles++;
  if(bf){
   if(fault==0){for(unsigned b=0;b<awbeats;b++)for(unsigned j=0;j<16;j++)mem[pos(awaddr+64*b)+j]=wdata[b][j];}
   acks++;bvalid=false;aw=false;wdata.clear();wlast.clear();
  }
  if(rf)rvalid=false;
  if(aw&&wdata.size()==awbeats&&!bvalid){for(unsigned i=0;i<awbeats;i++)check(wlast[i]==(i+1==awbeats),"WLAST misplaced");bvalid=true;bdelay=3+random()%6;}
  else if(bvalid&&bdelay)bdelay--;
  if(rvalid&&rd)rd--;
  d.clock=0;d.eval();
 }
 Words pattern(unsigned beat,unsigned seed){Words a;for(unsigned j=0;j<16;j++)a[j]=0x34000000U+(seed<<16)+(beat<<8)+j;return a;}
 void reset(){check(!aw&&!bvalid&&!rvalid&&wdata.empty(),"reset before bus drain");d.reset=1;for(int i=0;i<6;i++)step();d.reset=0;step();fault=0;}
 void readback(uint64_t address,Words expected,uint64_t tag){
  d.io_legacyRequest_bits_write=0;d.io_legacyRequest_bits_address=address;d.io_legacyRequest_bits_tag=tag;d.io_legacyRequest_bits_mask=0;
  d.io_legacyRequest_valid=1;d.io_legacyResponse_ready=0;while(!d.io_legacyRequest_ready)step();step();d.io_legacyRequest_valid=0;
  unsigned limit=0;while(!d.io_legacyResponse_valid&&limit++<300)step();check(d.io_legacyResponse_valid&&!d.io_legacyResponse_bits_error&&d.io_legacyResponse_bits_tag==tag,"readback response");
  for(int j=0;j<16;j++)check(d.io_legacyResponse_bits_data[j]==expected[j],"readback byte mismatch");
  d.io_legacyResponse_ready=1;step();d.io_legacyResponse_ready=0;
 }
 void run(unsigned count,unsigned offset,unsigned seed,int mode=0){
  fault=mode==1||mode==2?mode:0;auto starts=cycles,aw0=awCount,tx0=d.io_transfers,ack0=acks;
  uint64_t addr=BASE+offset;bool invalid=mode==4;
  d.io_request_bits_address=addr;d.io_request_bits_beats=count;d.io_request_bits_tag=seed;d.io_request_valid=1;d.io_response_ready=0;
  check(d.io_request_ready,"not ready for write request");step();d.io_request_valid=0;
  if(!invalid)for(unsigned i=0;i<count;i++){
   auto p=pattern(i,seed);for(int j=0;j<16;j++)d.io_data_bits_data[j]=p[j];d.io_data_bits_last=(i+1==count)^(mode==3&&i==0);d.io_data_valid=1;
   unsigned spins=0;while(!d.io_data_ready&&spins++<300)step();check(d.io_data_ready,"write data deadlock");step();d.io_data_valid=0;
   if(i+1<count){step();step();check(d.io_transfers==tx0,"iDMA began before complete source batch");}
  }
  unsigned limit=0;while(!d.io_response_valid&&limit++<1000)step();check(d.io_response_valid&&d.io_response_bits_tag==seed,"write completion missing");
  check(bool(d.io_response_bits_error)==bool(mode),"error classification");
  if(mode>=3){check(awCount==aw0&&d.io_transfers==tx0,"malformed write issued external work");}
  else{check(awCount==aw0+1&&acks==ack0+1&&d.io_transfers==tx0+1,"not exactly one real DMA/write burst");}
  for(int i=0;i<9;i++){step();check(d.io_response_valid&&d.io_response_bits_tag==seed&&bool(d.io_response_bits_error)==bool(mode),"unstable completion under backpressure");}
  d.io_response_ready=1;step();d.io_response_ready=0;const auto elapsed=cycles-starts;
  if(mode){check(d.io_resetRequired&&!d.io_request_ready,"error did not quarantine adapter");reset();}
  else{for(unsigned i=0;i<count;i++)readback(addr+64*i,pattern(i,seed),1000+seed*16+i);}
  std::cout<<"IDMA_WRITE_BURST_CASE_PASS beats="<<count<<" offset="<<offset<<" mode="<<mode<<" cycles="<<elapsed<<" checked_words="<<(mode?0:16*count)<<std::endl;
 }
};
int main(int argc,char**argv){try{Verilated::commandArgs(argc,argv);auto t=std::make_unique<Test>();
 for(unsigned b:{1,2,4,8,16}){t->run(b,0,b);t->run(b,1024-b*64,20+b);}
 t->run(16,1024,51,1);t->run(8,1024,52,2);t->run(8,1024,53,3);t->run(2,960,54,4);
 t->run(16,2048,55);
 std::cout<<"IDMA_WRITE_BURST_PASS cases=15 same_dut=1 fault_resets=4 real_idma=1 checked_words=1248 early_completion=0"<<std::endl;return 0;
}catch(const std::exception&e){std::cerr<<"IDMA_WRITE_BURST_FAIL: "<<e.what()<<std::endl;return 1;}}

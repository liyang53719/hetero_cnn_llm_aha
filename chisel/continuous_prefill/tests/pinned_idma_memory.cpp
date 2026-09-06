// SPDX-License-Identifier: Apache-2.0
// Exercise the actual, unchanged pinned iDMA backend. The environment only
// services AXI memory and injects bus faults; it never computes a model operator.
#include "VRetainedIdmaMemoryAdapter.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void check(bool ok,const std::string& s){if(!ok)throw std::runtime_error(s);}
struct Beat {bool valid=false,write=false;uint64_t address=0,mask=0;uint8_t id=0;std::array<uint32_t,16> data{};int delay=0;};
class Test {
public:
  VRetainedIdmaMemoryAdapter d;
  const uint64_t base=0x100001000ULL;
  std::array<uint8_t,4096> mem{};
  Beat aw,w,pending,heldAw,heldW,heldAr;
  bool awHeld=false,wHeld=false,arHeld=false;
  uint64_t cycle=0,readAcks=0,writeAcks=0,reqStalls=0,responseWait=0;
  uint32_t rng=20260906;std::string fault;
  Test(){for(size_t i=0;i<mem.size();i++)mem[i]=uint8_t(i*37+19);reset();}
  unsigned random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
  void reset(){
    d.clock=0;d.reset=1;d.io_request_valid=0;d.io_response_ready=0;
    aw={};w={};pending={};awHeld=wHeld=arHeld=false;
    for(int i=0;i<5;i++)step();d.reset=0;step();
  }
  static bool equal(const Beat&a,const Beat&b){return a.address==b.address&&a.id==b.id&&a.mask==b.mask&&a.data==b.data;}
  bool bus()const{return d.io_axi_ar_valid||d.io_axi_aw_valid||d.io_axi_w_valid;}
  void step(){
    d.clock=0;
    d.io_axi_ar_ready=!pending.valid&&!aw.valid&&!w.valid&&(random()%4!=0);
    d.io_axi_aw_ready=!pending.valid&&!aw.valid&&(random()%3!=0);
    d.io_axi_w_ready=!pending.valid&&!w.valid&&(random()%4!=0);
    d.io_axi_b_valid=pending.valid&&pending.write&&pending.delay==0;
    d.io_axi_r_valid=pending.valid&&!pending.write&&pending.delay==0;
    d.io_axi_b_bits_resp=fault=="b-error"?2:0;d.io_axi_b_bits_id=pending.id^(fault=="b-id"?1:0);
    d.io_axi_r_bits_resp=fault=="r-error"?3:0;d.io_axi_r_bits_id=pending.id^(fault=="r-id"?1:0);
    d.io_axi_r_bits_last=fault!="r-last";
    for(int i=0;i<16;i++)d.io_axi_r_bits_data[i]=pending.data[i];d.eval();
    bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready;
    bool af=d.io_axi_aw_valid&&d.io_axi_aw_ready,wf=d.io_axi_w_valid&&d.io_axi_w_ready;
    bool ack=(d.io_axi_b_valid&&d.io_axi_b_ready)||(d.io_axi_r_valid&&d.io_axi_r_ready);
    Beat a,b,c;
    if(d.io_axi_aw_valid){a.valid=true;a.address=d.io_axi_aw_bits_addr;a.id=d.io_axi_aw_bits_id;
      check(d.io_axi_aw_bits_len==0&&d.io_axi_aw_bits_size<=6&&d.io_axi_aw_bits_burst==1,"bad AW descriptor");
      if(awHeld)check(equal(a,heldAw),"unstable AW");heldAw=a;awHeld=!af;}else check(!awHeld,"withdrawn AW");
    if(d.io_axi_w_valid){b.valid=true;b.write=true;b.mask=d.io_axi_w_bits_strb;
      for(int i=0;i<16;i++)b.data[i]=d.io_axi_w_bits_data[i];check(d.io_axi_w_bits_last,"missing WLAST");
      if(wHeld)check(equal(b,heldW),"unstable W");heldW=b;wHeld=!wf;}else check(!wHeld,"withdrawn W");
    if(d.io_axi_ar_valid){c.valid=true;c.address=d.io_axi_ar_bits_addr;c.id=d.io_axi_ar_bits_id;
      check(d.io_axi_ar_bits_len==0&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1,"bad AR descriptor");
      if(arHeld)check(equal(c,heldAr),"unstable AR");heldAr=c;arHeld=!ar;}else check(!arHeld,"withdrawn AR");
    reqStalls+=(d.io_axi_ar_valid&&!ar)+(d.io_axi_aw_valid&&!af)+(d.io_axi_w_valid&&!wf);
    if(pending.valid&&pending.delay)responseWait++;
    if(af)aw=a;if(wf)w=b;Beat next;
    if(aw.valid&&w.valid){check(!pending.valid&&!ar,"AXI overlap");next=w;next.address=aw.address;next.id=aw.id;aw={};w={};}
    else if(ar){check(!pending.valid,"multiple outstanding reads");next=c;}
    if(next.valid){check(next.address>=base&&next.address-base+64<=mem.size()&&(next.address&63)==0,"AXI out of range");next.delay=1+random()%7;
      if(!next.write)for(int i=0;i<64;i++)next.data[i/4]|=uint32_t(mem[next.address-base+i])<<(8*(i%4));}
    d.clock=1;d.eval();cycle++;
    if(ack){if(pending.write){writeAcks++;if(fault.empty())for(int i=0;i<64;i++)if((pending.mask>>i)&1)mem[pending.address-base+i]=(pending.data[i/4]>>(8*(i%4)))&255;}
      else readAcks++;pending={};}
    if(next.valid)pending=next;else if(pending.valid&&pending.delay)pending.delay--;
    d.clock=0;d.eval();
  }
  void transact(bool write,uint64_t addr,uint64_t mask,bool expectError,bool expectDma){
    const auto before=d.io_transfers;const auto ra=readAcks,wa=writeAcks;
    std::array<uint8_t,4096> expected=mem;
    if(!expectError&&write)for(int i=0;i<64;i++)if((mask>>i)&1)expected[addr-base+i]=uint8_t(0x63+i*11);
    check(d.io_request_ready,"not ready");d.io_request_bits_write=write;d.io_request_bits_address=addr;d.io_request_bits_mask=mask;
    const uint64_t tag=0x1fedcba987650000ULL+cycle;d.io_request_bits_tag=tag;
    for(int i=0;i<16;i++)d.io_request_bits_data[i]=0;
    for(int i=0;i<64;i++)d.io_request_bits_data[i/4]|=uint32_t(uint8_t(0x63+i*11))<<(8*(i%4));
    d.io_request_valid=1;step();d.io_request_valid=0;
    auto bound=cycle+2000;
    while(!d.io_response_valid&&cycle<bound)step();check(d.io_response_valid,"response timeout");
    check(d.io_response_bits_tag==tag,"lost request tag");check(bool(d.io_response_bits_error)==expectError,"wrong error status");
    check(d.io_transfers-before==unsigned(expectDma),"wrong backend transfer count");
    if(expectDma)check((write?writeAcks-wa:readAcks-ra)==1,"response precedes actual AXI completion");
    else check(readAcks==ra&&writeAcks==wa&&!bus(),"rejected request reached backend");
    if(!expectError){check(mem==expected,"write payload/mask/guard mismatch");if(!write)for(int i=0;i<64;i++)
      check(((d.io_response_bits_data[i/4]>>(8*(i%4)))&255)==mem[addr-base+i],"read mailbox payload mismatch");}
    std::array<uint32_t,16> old;for(int i=0;i<16;i++)old[i]=d.io_response_bits_data[i];
    for(int stall=0;stall<9;stall++){check(d.io_response_valid&&d.io_response_bits_tag==tag&&bool(d.io_response_bits_error)==expectError,"unstable completion");
      for(int i=0;i<16;i++)check(old[i]==d.io_response_bits_data[i],"unstable completion data");check(!d.io_request_ready,"request overlapped completion");step();}
    d.io_response_ready=1;step();d.io_response_ready=0;
    if(expectError){check(d.io_resetRequired,"missing error quarantine");d.io_request_valid=1;for(int i=0;i<5;i++){check(!d.io_request_ready&&!bus(),"request escaped quarantine");step();}d.io_request_valid=0;}
    else check(!d.io_resetRequired&&d.io_request_ready,"healthy transfer poisoned adapter");
  }
};
int main(int argc,char**argv){try{Verilated::commandArgs(argc,argv);unsigned cases=0;Test t;
  for(unsigned n=1;n<=64;n++){uint64_t mask=n==64?~0ULL:(1ULL<<n)-1;t.transact(true,t.base+128,mask,false,true);cases++;t.transact(false,t.base+128,0,false,true);cases++;}
  for(auto fault:{"b-error","b-id","r-error","r-id","r-last"}){t.fault=fault;bool w=fault[0]=='b';t.transact(w,t.base+256,~0ULL,true,true);cases++;t.fault="";t.reset();t.transact(false,t.base+128,0,false,true);cases++;}
  for(uint64_t addr:std::array<uint64_t,3>{t.base+1,(1ULL<<56),~0ULL-63}){t.transact(false,addr,0,true,false);cases++;t.reset();}
  for(uint64_t mask:{0ULL,2ULL,5ULL,0x8000000000000000ULL}){t.transact(true,t.base,mask,true,false);cases++;t.reset();}
  check(t.reqStalls>0&&t.responseWait>0,"no random backpressure");
  std::cout<<"PINNED_IDMA_TRANSPORT_PASS cases="<<cases<<" request_stalls="<<t.reqStalls<<" response_delay_cycles="<<t.responseWait<<" original_backend=1 response_after_axi_ack=1"<<std::endl;return 0;
}catch(const std::exception&e){std::cerr<<"PINNED_IDMA_TRANSPORT_FAIL "<<e.what()<<std::endl;return 1;}}

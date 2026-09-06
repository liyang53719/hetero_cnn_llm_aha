// SPDX-License-Identifier: Apache-2.0
// The environment only serves DDR reads. It cannot synthesize a descriptor result.
#include "VRecord128IdmaTop.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
static void check(bool v,const std::string& s){if(!v)throw std::runtime_error(s);}
class Test {
public:
  VRecord128IdmaTop d;
  static constexpr uint64_t BASE=0x12345678000ULL;
  std::array<uint32_t,32> memory{};
  bool pending=false,held=false;uint64_t addr=0,heldAddr=0,cycles=0,acks=0,stalls=0,delays=0;
  unsigned delay=0,id=0,heldId=0,rng=20260906;std::string fault;
  std::array<uint32_t,16> data{};
  unsigned random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
  void step(){
    d.clock=0;d.io_axi_aw_ready=0;d.io_axi_w_ready=0;d.io_axi_b_valid=0;
    d.io_axi_b_bits_resp=0;d.io_axi_b_bits_id=0;
    d.io_axi_ar_ready=!pending&&(random()%4!=0);
    d.io_axi_r_valid=pending&&delay==0;
    d.io_axi_r_bits_id=id^(fault=="id"?1:0);
    d.io_axi_r_bits_resp=fault=="resp"?2:0;d.io_axi_r_bits_last=fault!="last";
    for(int j=0;j<16;j++)d.io_axi_r_bits_data[j]=data[j];d.eval();
    check(!d.io_axi_aw_valid&&!d.io_axi_w_valid,"read-only table request escaped as write");
    const bool af=d.io_axi_ar_valid&&d.io_axi_ar_ready,rf=d.io_axi_r_valid&&d.io_axi_r_ready;
    if(d.io_axi_ar_valid){
      check(d.io_axi_ar_bits_len==0&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1,"invalid burst");
      if(held)check(heldAddr==d.io_axi_ar_bits_addr&&heldId==d.io_axi_ar_bits_id,"unstable AR");
      heldAddr=d.io_axi_ar_bits_addr;heldId=d.io_axi_ar_bits_id;held=!af;
    }else check(!held,"withdrawn AR");
    if(d.io_axi_ar_valid&&!d.io_axi_ar_ready)stalls++;if(pending&&delay)delays++;
    uint64_t newAddr=d.io_axi_ar_bits_addr;unsigned newId=d.io_axi_ar_bits_id;
    d.clock=1;d.eval();cycles++;
    if(rf){pending=false;acks++;}
    if(af){check(!pending&&newAddr>=BASE&&newAddr-BASE+64<=128&&(newAddr&63)==0,"out-of-table read");
      pending=true;addr=newAddr;id=newId;delay=1+random()%6;
      for(unsigned j=0;j<16;j++)data[j]=memory[(addr-BASE)/4+j];
    }else if(pending&&delay)delay--;
    d.clock=0;d.eval();
  }
  void reset(){d.reset=1;d.io_request_valid=0;d.io_result_ready=0;pending=held=false;
    for(int j=0;j<4;j++)step();d.reset=0;step();}
  void transact(unsigned index,unsigned count,uint64_t base,uint64_t limit,unsigned expectedStatus,bool bus){
    const auto startAcks=acks,startDma=d.io_idmaTransfers;
    const uint64_t tag=0xfedcba9800000000ULL+cycles;
    check(d.io_request_ready,"reader not ready");
    d.io_request_bits_index=index;d.io_request_bits_entryCount=count;
    d.io_request_bits_tableBase=base;d.io_request_bits_tableLimit=limit;d.io_request_bits_requestTag=tag;
    d.io_request_valid=1;step();d.io_request_valid=0;
    const uint64_t end=cycles+2000;while(!d.io_result_valid&&cycles<end)step();
    check(d.io_result_valid,"result timeout");check(d.io_result_bits_status==expectedStatus,"wrong status");
    check(d.io_result_bits_requestTag==tag,"request identity lost");
    check(acks-startAcks==unsigned(bus)&&d.io_idmaTransfers-startDma==unsigned(bus),"result bypassed actual iDMA/AXI");
    for(int j=0;j<4;j++)check(d.io_result_bits_data[j]==(expectedStatus?0:memory[index*4+j]),"128-bit data/slot mismatch");
    for(int n=0;n<7;n++){check(d.io_result_valid&&!d.io_request_ready&&d.io_result_bits_requestTag==tag,"result unstable under backpressure");step();}
    d.io_result_ready=1;step();d.io_result_ready=0;
    check(!pending,"result preceded external ACK");
    if(expectedStatus==3){check(d.io_resetRequired,"missing quarantine");d.io_request_valid=1;
      for(int n=0;n<5;n++){check(!d.io_request_ready&&!d.io_axi_ar_valid,"request escaped quarantine");step();}d.io_request_valid=0;}
    else check(d.io_request_ready&&!d.io_resetRequired,"healthy/admission-error request poisoned reader");
  }
};
int main(int argc,char**argv){try{
  Verilated::commandArgs(argc,argv);Test t;t.reset();unsigned cases=0;
  for(unsigned round=0;round<2;round++){
    for(unsigned j=0;j<32;j++)t.memory[j]=0xdead0000u+j*7919u+round*0x123456u;
    for(unsigned index=0;index<7;index++){t.transact(index,7,t.BASE,t.BASE+128,0,true);cases++;}
  }
  t.transact(7,7,t.BASE,t.BASE+128,5,false);cases++;
  t.transact(0,0,t.BASE,t.BASE+128,5,false);cases++;
  t.transact(0,7,t.BASE,t.BASE+112,5,false);cases++;
  t.transact(0,7,t.BASE+16,t.BASE+256,5,false);cases++;
  t.transact(0,1,~0ULL-63,~0ULL,5,false);cases++;
  for(const auto& fault:{"id","resp","last"}){
    t.fault=fault;t.transact(3,7,t.BASE,t.BASE+128,3,true);cases++;t.fault="";t.reset();
  }
  t.transact(6,7,t.BASE,t.BASE+128,0,true);cases++;
  check(t.stalls>0&&t.delays>0,"backpressure absent");
  std::cout<<"RECORD128_IDMA_PASS cases="<<cases<<" external_read_acks="<<t.acks
    <<" request_stalls="<<t.stalls<<" response_delay_cycles="<<t.delays
    <<" original_idma=1 descriptor_execution=0"<<std::endl;return 0;
}catch(const std::exception&e){std::cerr<<"RECORD128_IDMA_FAIL "<<e.what()<<std::endl;return 1;}}

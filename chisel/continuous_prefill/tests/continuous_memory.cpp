// SPDX-License-Identifier: Apache-2.0
// Numerical memory-system test, not a decoder/network simulator.
#include "VContinuousElementwiseTop.h"
#include "verilated.h"
#include <array>
#include <cfenv>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include <algorithm>
static void need(bool ok,const std::string& s){if(!ok)throw std::runtime_error(s);}
static uint32_t bits(float x){uint32_t r;std::memcpy(&r,&x,4);return r;}
static float real32(uint32_t x){float r;std::memcpy(&r,&x,4);return r;}
static uint16_t bf(float x){uint32_t w=bits(x);return uint16_t((uint64_t(w)+0x7fff+((w>>16)&1))>>16);}
struct Segment {uint64_t base;std::vector<uint8_t> bytes;bool ro;};
struct Pending {bool valid=false,write=false,error=false;uint64_t addr=0,tag=0,mask=0;std::array<uint32_t,16> data{};unsigned delay=0;};
class Test {
 public:
  VContinuousElementwiseTop d;
  std::vector<Segment> memory;
  Pending pending;
  uint32_t rng=0x19060531;uint64_t cycles=0,reads=0,writes=0,acks=0,reqStalls=0,rspDelay=0;
  uint32_t elements;bool inject;bool injected=false;unsigned commits=0;
  std::array<bool,6> published{};
  explicit Test(uint32_t n,bool fail):elements(n),inject(fail){
    for(int i=0;i<6;i++)memory.push_back({uint64_t(i<3?0x100000000ULL:0x200000000ULL)+uint64_t(i%3)*0x4000000ULL,
      std::vector<uint8_t>(((size_t(n)*(i==1||i==2||i==5?2:4)+63)/64)*64+64,0xcc),i<3});
    for(uint32_t i=0;i<n;i++){
      uint32_t h=(i*1664525u+1013904223u)^(i>>3);
      float x=float(int(h%8191)-4095)*0.03125f;
      float b=float(int((h>>12)%255)-127)*0.015625f;
      float s=float((h>>20)%31+1)*0.0625f;
      put(0,i,bits(x),4);put(1,i,bf(b),2);put(2,i,bf(s),2);
    }
    d.clock=0;d.reset=1;d.io_regionWrite_valid=0;d.io_tensorWrite_valid=0;d.io_programWrite_valid=0;
    d.io_launch_valid=0;d.io_result_ready=0;d.io_memory_ready=0;d.io_response_valid=0;
    for(int i=0;i<5;i++)step();d.reset=0;step();
  }
  uint32_t random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
  void put(int seg,uint32_t i,uint32_t w,int size){for(int j=0;j<size;j++)memory[seg].bytes[size_t(i)*size+j]=uint8_t(w>>(8*j));}
  uint32_t get(int seg,uint32_t i,int size){uint32_t w=0;for(int j=0;j<size;j++)w|=uint32_t(memory[seg].bytes[size_t(i)*size+j])<<(8*j);return w;}
  Segment& locate(uint64_t addr){for(auto& s:memory)if(addr>=s.base&&addr+64>=addr&&addr+64<=s.base+s.bytes.size()-64)return s;throw std::runtime_error("DDR address outside allocation");}
  void step(){
    d.clock=0;
    d.io_memory_ready=!pending.valid && (random()%5!=0);
    d.io_response_valid=pending.valid && pending.delay==0;
    d.io_response_bits_tag=pending.tag;d.io_response_bits_error=pending.error;
    for(int i=0;i<16;i++)d.io_response_bits_data[i]=pending.data[i];
    d.eval();
    bool rf=d.io_memory_valid&&d.io_memory_ready,af=d.io_response_valid&&d.io_response_ready;
    if(d.io_memory_valid&&!d.io_memory_ready)reqStalls++;
    if(pending.valid&&pending.delay)rspDelay++;
    if(d.io_committed){need(!pending.valid,"publish before final DDR ack");published[d.io_committedTensor]=true;commits++;}
    Pending next;
    if(rf){
      need(!pending.valid,"two outstanding transactions");next.valid=true;next.write=d.io_memory_bits_write;
      next.addr=d.io_memory_bits_address;next.tag=d.io_memory_bits_tag;next.mask=d.io_memory_bits_mask;next.delay=random()%4;
      need((next.addr&63)==0,"unaligned beat");auto& s=locate(next.addr);size_t off=next.addr-s.base;
      if(next.write){need(!s.ro,"write to immutable input/weight region");writes++;for(int i=0;i<16;i++)next.data[i]=d.io_memory_bits_data[i];
        if(inject&&!injected&&writes==4){next.error=true;injected=true;}
      }else{
        reads++;if(s.base==memory[3].base)need(published[3],"consumer read uncommitted first producer");
        if(s.base==memory[4].base)need(published[4],"consumer read uncommitted second producer");
        for(int i=0;i<16;i++){uint32_t w=0;for(int j=0;j<4;j++)w|=uint32_t(s.bytes[off+4*i+j])<<(8*j);next.data[i]=w;}
      }
    }
    d.clock=1;d.eval();cycles++;
    if(af){
      if(pending.write&&!pending.error){auto& s=locate(pending.addr);size_t off=pending.addr-s.base;
        for(int j=0;j<64;j++)if((pending.mask>>j)&1)s.bytes[off+j]=uint8_t(pending.data[j/4]>>(8*(j%4)));
      }acks++;pending.valid=false;
    }
    if(rf)pending=next;else if(pending.valid&&pending.delay)pending.delay--;
    d.clock=0;d.eval();
  }
  void configure(){
    for(int i=0;i<2;i++){
      d.io_regionWrite_bits_index=i;d.io_regionWrite_bits_value_base=i?0x200000000ULL:0x100000000ULL;
      d.io_regionWrite_bits_value_limit=i?0x20c000000ULL:0x10c000000ULL;
      d.io_regionWrite_bits_value_read=1;d.io_regionWrite_bits_value_write=i;
      d.io_regionWrite_valid=1;step();need(d.io_regionWrite_ready,"config blocked");
    }d.io_regionWrite_valid=0;
    for(int i=0;i<6;i++){
      d.io_tensorWrite_bits_index=i;d.io_tensorWrite_bits_value_base=memory[i].base;d.io_tensorWrite_bits_value_elementCount=elements;
      d.io_tensorWrite_bits_value_bf16=i==1||i==2||i==5;d.io_tensorWrite_bits_value_region=i>=3;d.io_tensorWrite_bits_value_external=i<3;
      d.io_tensorWrite_valid=1;step();
    }d.io_tensorWrite_valid=0;
    for(int p=0;p<3;p++){
      d.io_programWrite_bits_index=p;d.io_programWrite_bits_value_op=p==0?1:p==1?2:0;
      d.io_programWrite_bits_value_a=p==0?0:p==1?3:4;d.io_programWrite_bits_value_b=p==0?1:2;d.io_programWrite_bits_value_dst=3+p;
      d.io_programWrite_bits_value_aVersion=p?1:0;d.io_programWrite_bits_value_bVersion=0;d.io_programWrite_bits_value_dstVersion=1;
      d.io_programWrite_valid=1;step();
    }d.io_programWrite_valid=0;
  }
  void run(){
    configure();d.io_launch_bits_commands=3;d.io_launch_bits_epoch=1;d.io_launch_valid=1;step();d.io_launch_valid=0;
    // No host input, expected output or stage-specific intervention from here.
    while(!d.io_result_valid&&cycles<100000000ULL){need(!d.io_tensorWrite_ready&&!d.io_programWrite_ready,"configuration mutable during run");step();}
    need(d.io_result_valid,"watchdog");need(!pending.valid,"undrained memory transaction");
    if(inject){need(injected&&d.io_result_bits_status==3&&commits==0&&d.io_resetRequired,"fault did not poison entire tensor");
      std::cout<<"MEMORY_FAILURE_NO_PUBLICATION_PASS elements="<<elements<<" writes="<<writes<<"\n";return;}
    need(d.io_result_bits_status==0&&d.io_result_bits_completed==3&&commits==3,"chain completion");
    uint64_t hash=0xcbf29ce484222325ULL;
    for(uint32_t i=0;i<elements;i++){
      volatile float a=real32(get(0,i,4));volatile float b=real32(get(1,i,2)<<16);volatile float s=real32(get(2,i,2)<<16);
      volatile float u=a+b;volatile float v=u*s;
      need(get(3,i,4)==bits(u),"first FP32 producer mismatch at "+std::to_string(i));
      need(get(4,i,4)==bits(v),"second FP32 producer mismatch at "+std::to_string(i));
      uint16_t e=bf(v);need(get(5,i,2)==e,"BF16 output mismatch at "+std::to_string(i));hash=(hash^e)*0x100000001b3ULL;
    }
    for(int i=3;i<6;i++){size_t valid=size_t(elements)*(i==5?2:4);for(size_t j=valid;j<memory[i].bytes.size();j++)need(memory[i].bytes[j]==0xcc,"tail or guard clobbered");}
    need(reqStalls>0&&rspDelay>0,"no memory backpressure exercised");
    std::cout<<"CONTINUOUS_ELEMENTWISE_NUMERIC_PASS elements="<<elements<<" stages=3 commits="<<commits<<" cycles="<<cycles
      <<" reads="<<reads<<" writes="<<writes<<" ack="<<acks<<" request_stalls="<<reqStalls<<" response_delay_cycles="<<rspDelay
      <<" bf16_hash="<<std::hex<<hash<<std::dec<<" host_intermediate_writes=0 full_model=0\n";
  }
};
int main(int argc,char** argv){try{
  Verilated::commandArgs(argc,argv);std::fesetround(FE_TONEAREST);
  uint32_t n=argc>1?uint32_t(std::stoul(argv[1])):32768;
  need(n>0&&n<=1024*2560,"test size outside bounded gate");bool fail=argc>2&&std::string(argv[2])=="fail";
  auto test=std::make_unique<Test>(n,fail);test->run();return 0;
}catch(const std::exception& e){std::cerr<<"TEST_FAILURE "<<e.what()<<"\n";return 1;}}

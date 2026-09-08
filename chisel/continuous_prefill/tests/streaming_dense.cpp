// SPDX-License-Identifier: Apache-2.0
// AXI memory service only: no arithmetic results are returned to the DUT.
#include "VStreamingDenseProbe.h"
#include "verilated.h"
#include <array>
#include <vector>
#include <memory>
#include <cstring>
#include <cmath>
#include <cfenv>
#include <iostream>
#include <fstream>
#include <filesystem>
#include <stdexcept>
static void ck(bool c,const char*s){if(!c)throw std::runtime_error(s);}
static uint32_t bits(float x){uint32_t u;memcpy(&u,&x,4);return u;}
static float fl(uint32_t u){float x;memcpy(&x,&u,4);return x;}
static float bf(float x){auto u=bits(x);return fl((u+0x7fff+((u>>16)&1))&0xffff0000U);}
static constexpr uint64_t BASE=0x102000000ULL,A=BASE+0x40,B=BASE+0x10040,C=BASE+0x100000;
struct Beat{bool valid=false,write=false,error=false;uint64_t address=0,id=0,mask=0;unsigned delay=0,left=1;std::array<uint32_t,16> words{};};
struct Test{
 VStreamingDenseProbe d;std::vector<uint32_t> memory;Beat pending,aw,w;uint32_t rng=9082026;uint64_t cycles=0,reads=0,writes=0,readBursts=0;unsigned m=0,n=0,k=0;bool running=false,injected=false;int fault=0;std::ofstream actual,reference;
 Test(const std::filesystem::path&o):memory(2*1024*1024/4,0x7fc00001),actual(o/"actual.f32le",std::ios::binary),reference(o/"reference.f32le",std::ios::binary){d.clock=0;d.reset=1;d.io_job_valid=0;d.io_done_ready=0;for(int i=0;i<6;i++)tick();d.reset=0;tick();}
 uint32_t random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
 size_t pos(uint64_t a){ck(a>=BASE&&a<BASE+memory.size()*4,"address out of range");return (a-BASE)/4;}
 bool validRead(uint64_t a){return (a>=A&&a+64<=A+uint64_t(m)*k*4)||(a>=B&&a+64<=B+uint64_t(k)*n*4);}
 void tick(){
  d.clock=0;d.io_axi_ar_ready=!pending.valid&&!aw.valid&&!w.valid&&random()%4!=0;
  d.io_axi_aw_ready=!pending.valid&&!aw.valid&&random()%3!=0;d.io_axi_w_ready=!pending.valid&&!w.valid&&random()%4!=0;
  d.io_axi_r_valid=pending.valid&&!pending.write&&!pending.delay;d.io_axi_b_valid=pending.valid&&pending.write&&!pending.delay;
  d.io_axi_r_bits_id=pending.id;d.io_axi_r_bits_resp=pending.error?2:0;d.io_axi_r_bits_last=pending.left==1;
  d.io_axi_b_bits_id=pending.id;d.io_axi_b_bits_resp=pending.error?2:0;
  for(unsigned i=0;i<16;i++)d.io_axi_r_bits_data[i]=pending.words[i];d.eval();
  bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready,af=d.io_axi_aw_valid&&d.io_axi_aw_ready,wf=d.io_axi_w_valid&&d.io_axi_w_ready;
  bool ack=(d.io_axi_r_valid&&d.io_axi_r_ready)||(d.io_axi_b_valid&&d.io_axi_b_ready);Beat next;
  if(ar){ck(running,"read without job");next.valid=true;next.address=d.io_axi_ar_bits_addr;next.id=d.io_axi_ar_bits_id;next.left=d.io_axi_ar_bits_len+1;
   ck(next.left<=16&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1&&((next.address&1023)+next.left*64)<=1024,"read burst geometry");readBursts++;}
  if(af){aw.valid=true;aw.address=d.io_axi_aw_bits_addr;aw.id=d.io_axi_aw_bits_id;ck(d.io_axi_aw_bits_len==0&&d.io_axi_aw_bits_size==6,"write burst geometry");}
  if(wf){w.valid=true;w.write=true;w.mask=d.io_axi_w_bits_strb;for(unsigned i=0;i<16;i++)w.words[i]=d.io_axi_w_bits_data[i];ck(d.io_axi_w_bits_last,"write last");}
  if(aw.valid&&w.valid){ck(!next.valid&&!pending.valid,"overlapping AXI operations");next=w;next.address=aw.address;next.id=aw.id;aw={};w={};}
  auto prepare=[&](Beat& b){b.delay=1+random()%4;ck(!(b.address&63),"unaligned request");
   if(b.write){ck(b.address>=C&&b.address+64<=C+uint64_t(m)*n*4&&b.mask==~uint64_t(0),"write extent/mask");
    if(fault==2&&!injected&&b.address+64==C+uint64_t(m)*n*4){b.error=true;injected=true;}}
   else{ck(validRead(b.address),"read exceeded tensor extent");for(unsigned i=0;i<16;i++)b.words[i]=memory[pos(b.address)+i];
    if(fault==1&&!injected&&b.address>=B+uint64_t(16)*n*4){b.error=true;injected=true;}}
  };
  if(next.valid){ck(!pending.valid,"more than one burst in flight");prepare(next);}
  d.clock=1;d.eval();cycles++;
  if(ack){if(pending.write){if(!pending.error){for(unsigned i=0;i<16;i++)memory[pos(pending.address)+i]=pending.words[i];writes++;}}
   else reads++;
   if(!pending.write&&pending.left>1){pending.address+=64;pending.left--;pending.error=false;prepare(pending);}else pending={};}
  if(next.valid)pending=next;else if(pending.valid&&pending.delay)pending.delay--;d.clock=0;d.eval();
 }
 uint64_t run(unsigned mm,unsigned nn,unsigned kk,unsigned seed,int fail=0){
  ck(!running&&!pending.valid&&!aw.valid&&!w.valid,"undrained previous request");m=mm;n=nn;k=kk;fault=fail;injected=false;cycles=reads=writes=readBursts=0;
  for(unsigned i=0;i<m*k;i++)memory[pos(A)+i]=bits(float(int((i*13+seed)%127)-63)*0.03131f);
  for(unsigned i=0;i<k*n;i++)memory[pos(B)+i]=bits(float(int((i*17+seed*7)%61)-30)*0.007821f);
  for(unsigned i=0;i<m*n+16;i++)memory[pos(C)+i]=0x7fc00001;
  std::vector<float> gold(m*n,0);if(!fail)for(unsigned r=0;r<m;r++)for(unsigned col=0;col<n;col++)for(unsigned z=0;z<k;z++)gold[r*n+col]=std::fma(bf(fl(memory[pos(A)+r*k+z])),bf(fl(memory[pos(B)+z*n+col])),gold[r*n+col]);
  d.io_job_bits_kind=1;d.io_job_bits_m=m;d.io_job_bits_n=n;d.io_job_bits_k=k;d.io_job_bits_a=A;d.io_job_bits_b=B;d.io_job_bits_c=0;d.io_job_bits_dst=C;d.io_job_bits_writeBytes=uint64_t(m)*n*4;d.io_job_bits_tag=seed;
  d.io_job_valid=1;d.io_done_ready=0;d.eval();ck(d.io_job_ready,"job not admitted");running=true;tick();d.io_job_valid=0;
  while(!d.io_done_valid&&cycles<3000000)tick();ck(d.io_done_valid,"job timeout");ck(!pending.valid&&!aw.valid&&!w.valid,"completion before external drain");
  ck(d.io_done_bits_tag==seed,"result tag");uint64_t checked=0;
  if(fail){ck(injected&&d.io_done_bits_status==3&&d.io_resetRequired,"error propagation");}
  else{
   ck(!d.io_done_bits_status&&!d.io_resetRequired,"unexpected owner failure");ck(d.io_done_bits_writeBytes==uint64_t(m)*n*4&&writes*64==uint64_t(m)*n*4,"incomplete acknowledged writeback");
   ck(d.io_done_bits_usefulMacs==uint64_t(m)*n*k,"useful MAC count");
   ck(d.io_done_bits_executedMacs==uint64_t((m+15)/16)*((n+31)/32)*k*512,"physical MAC count");
   for(unsigned i=0;i<m*n;i++){uint32_t a=memory[pos(C)+i],b=bits(gold[i]);if(a!=b){std::cerr<<"mismatch i="<<i<<" got="<<std::hex<<a<<" want="<<b<<std::dec<<"\n";throw std::runtime_error("arithmetic mismatch");}actual.write((const char*)&a,4);reference.write((const char*)&b,4);checked++;}
   for(unsigned i=0;i<16;i++)ck(memory[pos(C)+m*n+i]==0x7fc00001,"output guard modified");
  }
  auto status=d.io_done_bits_status;auto count=d.io_done_bits_writeBytes;for(unsigned i=0;i<7;i++){tick();ck(d.io_done_valid&&d.io_done_bits_status==status&&d.io_done_bits_writeBytes==count,"unstable completion");}
  d.io_done_ready=1;tick();d.io_done_ready=0;running=false;
  if(fail){ck(!d.io_job_ready,"failed owner accepted new work");d.reset=1;for(unsigned i=0;i<6;i++)tick();d.reset=0;tick();}
  else ck(d.io_job_ready,"owner not ready for next request");
  std::cout<<"STREAM_DENSE_CASE_PASS m="<<m<<" n="<<n<<" k="<<k<<" fault="<<fail<<" checked_fp32="<<checked<<" cycles="<<cycles<<" read_beats="<<reads<<" read_bursts="<<readBursts<<" write_acks="<<writes<<std::endl;return checked;
 }
};
int main(int argc,char**argv){try{
 std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);ck(argc==2,"NEW_OUTPUT");std::filesystem::path p(argv[1]);ck(!std::filesystem::exists(p),"preserve existing outputs");std::filesystem::create_directories(p);auto t=std::make_unique<Test>(p);uint64_t count=0;
 count+=t->run(16,1536,64,1);count+=t->run(17,528,128,2);count+=t->run(1,16,16,3);count+=t->run(16,1280,32,4);
 t->run(16,1536,64,5,1);count+=t->run(16,1536,64,6);
 t->run(16,528,32,7,2);count+=t->run(16,528,32,8);
 t->actual.flush();t->reference.flush();ck(t->actual.good()&&t->reference.good(),"output write failed");
 std::cout<<"STREAM_DENSE_NUMERIC_PASS cases=8 numeric_cases=6 fault_resets=2 checked_fp32="<<count<<" bit_differences=0 real_idma=1 physical_mac=4096 same_dut=1\n";return 0;
}catch(const std::exception&e){std::cerr<<"STREAM_DENSE_FAIL: "<<e.what()<<std::endl;return 1;}}

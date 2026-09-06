// SPDX-License-Identifier: Apache-2.0
// DDR service only: the device performs every operator and every intermediate write.
// The independent CPU reference is comparison-only and never services DUT reads.
#ifdef BLOCK_IDMA
#include "VQwen2IdmaBlockTop.h"
using BlockDut=VQwen2IdmaBlockTop;
#elif defined(BLOCK_AXI)
#include "VQwen2AxiBlockTop.h"
using BlockDut=VQwen2AxiBlockTop;
#else
#include "VQwen2ContinuousBlock.h"
using BlockDut=VQwen2ContinuousBlock;
#endif
#include "verilated.h"
#include "block_layout.h"
#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
static constexpr int KV=KVHEADS*HD;
static void need(bool b,const std::string& msg){if(!b)throw std::runtime_error(msg);}
static uint32_t bits(float x){uint32_t r;std::memcpy(&r,&x,4);return r;}
static float fp(uint32_t x){float r;std::memcpy(&r,&x,4);return r;}
static float bf(float x){uint32_t u=bits(x);if((u&0x7f800000)==0x7f800000)return x;return fp((u+0x7fff+((u>>16)&1))&0xffff0000);}
static float add(float a,float b){return a+b;}
static float mul(float a,float b){return a*b;}
static float expneg(float x){
  x=std::abs(x);if(x>=80)return 0;float z=mul(x,float(1.0/std::log(2.0)));unsigned k=unsigned(z);float f=add(z,-float(k));
  float c[8];double fact=1;for(int i=0;i<8;i++){if(i)fact*=i;c[i]=float(std::pow(-std::log(2.0),i)/fact);}float y=c[7];
  for(int i=6;i>=0;i--)y=add(mul(y,f),c[i]);return mul(y,fp((127-k)<<23));
}
struct Stage {const char* name;uint64_t off;int width;};
static const std::array<Stage,15> STAGES{{{"n0",OFF_N0,H},{"qr",OFF_QR,H},{"kr",OFF_KR,KV},{"v",OFF_V,KV},{"q",OFF_Q,H},{"k",OFF_K,KV},{"att",OFF_ATT,H},{"o",OFF_O,H},{"r",OFF_R,H},{"n1",OFF_N1,H},{"gate",OFF_GATE,F},{"up",OFF_UP,F},{"act",OFF_ACT,F},{"down",OFF_DOWN,H},{"y",OFF_Y,H}}};
struct Pending {bool valid=false,write=false,error=false;uint64_t address=0,tag=0,mask=0;std::array<uint32_t,16> data{};unsigned delay=0;};
class BlockTest {
public:
  BlockDut d;std::vector<uint32_t> memory;std::vector<float> reference;std::vector<uint8_t> initialized;
  unsigned tokens;uint32_t rng;uint64_t BASE=0x100000000ULL,cycles=0,reads=0,writes=0,acks=0,requestStalls=0,responseStalls=0,checked=0,bitDifferences=0;
  unsigned commits=0;Pending pending,held;bool heldValid=false,inject=false,corruptTag=false,injected=false;float globalMaxError=0;
  std::array<bool,15> published{};
  explicit BlockTest(unsigned t,uint32_t seed):memory(ARENA_BYTES/4,0x7fc00001u),reference(ARENA_BYTES/4,0.0f),initialized(ARENA_BYTES/4,0),tokens(t),rng(seed){
    d.clock=0;d.reset=1;d.io_launch_valid=0;d.io_result_ready=0;
#ifdef BLOCK_AXI
    d.io_axi_aw_ready=0;d.io_axi_w_ready=0;d.io_axi_ar_ready=0;d.io_axi_b_valid=0;d.io_axi_r_valid=0;
#else
    d.io_memory_ready=0;d.io_response_valid=0;
#endif
    for(int i=0;i<5;i++)step();d.reset=0;step();
  }
  uint32_t random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
  void set(uint64_t offset,size_t i,float x){memory[offset/4+i]=bits(x);reference[offset/4+i]=x;initialized[offset/4+i]=1;}
  float get(uint64_t offset,size_t i)const{return reference[offset/4+i];}
  void put(uint64_t offset,size_t i,float x){reference[offset/4+i]=x;}
  void weight(uint64_t offset,int k,int n,unsigned salt){for(int i=0;i<k;i++)for(int j=0;j<n;j++){
    uint32_t x=(uint32_t(i)*1664525u+uint32_t(j)*1013904223u+salt*2654435761u);x^=x>>13;x*=2246822519u;
    set(offset,size_t(i)*n+j,bf(float(int(x%31)-15)*(H>64?0.00390625f:0.015625f)));
  }}
  void initialize(unsigned epoch=1){
    weight(OFF_WQ,H,H,1);weight(OFF_WK,H,KV,2);weight(OFF_WV,H,KV,3);weight(OFF_WO,H,H,4);weight(OFF_WG,H,F,5);weight(OFF_WU,H,F,6);weight(OFF_WD,F,H,7);
    for(int i=0;i<H;i++){set(OFF_GAMMA0,i,bf(0.9f+(i%11)*0.015625f));set(OFF_GAMMA1,i,bf(1.0f+(i%7)*0.015625f));set(OFF_BQ,i,float(i%13-6)*0.00390625f);}
    for(int i=0;i<KV;i++){set(OFF_BK,i,float(i%7-3)*0.0078125f);set(OFF_BV,i,float(i%9-4)*0.00390625f);}
    for(unsigned t=0;t<tokens;t++)for(int i=0;i<HD/2;i++){
      double angle=t/std::pow(1000000.0,2.0*i/HD);set(OFF_COS,size_t(t)*HD/2+i,float(std::cos(angle)));set(OFF_SIN,size_t(t)*HD/2+i,float(std::sin(angle)));
    }
    for(unsigned t=0;t<tokens;t++)for(int i=0;i<H;i++)set(OFF_X,size_t(t)*H+i,float(int((i*37u+t*101u+epoch*73u)%1021)-510)*0.00390625f);
    computeReference();
  }
  void loadArena(const std::string& path){
    std::ifstream f(path,std::ios::binary);need(bool(f),"cannot open external arena");f.seekg(0,std::ios::end);need(uint64_t(f.tellg())==WRITABLE_START,"external arena must contain only exact readonly prefix");f.seekg(0);
    f.read(reinterpret_cast<char*>(memory.data()),WRITABLE_START);need(bool(f),"short arena read");
    for(size_t i=0;i<WRITABLE_START/4;i++){reference[i]=fp(memory[i]);initialized[i]=1;}
    computeReference();
  }
  void norm(uint64_t in,uint64_t gamma,uint64_t out){for(unsigned t=0;t<tokens;t++){
    float sum=0;for(int i=0;i<H;i++){float x=get(in,size_t(t)*H+i);sum=add(sum,mul(x,x));}
    float inv=1.0f/std::sqrt(add(mul(sum,float(1.0/H)),1e-6f));for(int i=0;i<H;i++)put(out,size_t(t)*H+i,bf(mul(mul(get(in,size_t(t)*H+i),inv),get(gamma,i))));
  }}
  void dense(uint64_t in,uint64_t w,uint64_t out,int K,int N,int64_t bias=-1){
    std::vector<float> a(K);for(unsigned t=0;t<tokens;t++){for(int k=0;k<K;k++)a[k]=bf(get(in,size_t(t)*K+k));
      for(int col=0;col<N;col+=16){float sums[16]={};for(int k=0;k<K;k++){const float* weights=reference.data()+w/4+size_t(k)*N+col;for(int j=0;j<16;j++)sums[j]=std::fma(a[k],bf(weights[j]),sums[j]);}
        for(int j=0;j<16;j++)put(out,size_t(t)*N+col+j,bias>=0?add(sums[j],get(bias,col+j)):sums[j]);
      }
    }
  }
  void rope(uint64_t in,uint64_t out,int heads){int width=heads*HD;for(unsigned t=0;t<tokens;t++)for(int h=0;h<heads;h++)for(int j=0;j<HD/2;j++){
    auto ix=size_t(t)*width+h*HD+j;float x=get(in,ix),y=get(in,ix+HD/2),c=get(OFF_COS,size_t(t)*HD/2+j),s=get(OFF_SIN,size_t(t)*HD/2+j);
    put(out,ix,add(mul(x,c),-mul(y,s)));put(out,ix+HD/2,add(mul(x,s),mul(y,c)));
  }}
  void attention(){std::vector<float> p(tokens);for(unsigned t=0;t<tokens;t++)for(int h=0;h<HEADS;h++){
    int kh=h/(HEADS/KVHEADS);float max=-INFINITY;
    for(unsigned k=0;k<=t;k++){float parts[16]={};for(int j=0;j<HD;j++)parts[j%16]=std::fma(bf(get(OFF_Q,size_t(t)*H+h*HD+j)),bf(get(OFF_K,size_t(k)*KV+kh*HD+j)),parts[j%16]);
      float sum=0;for(float x:parts)sum=add(sum,x);p[k]=mul(sum,float(1.0/std::sqrt(double(HD))));max=std::max(max,p[k]);}
    float sum=0;for(unsigned k=0;k<=t;k++){p[k]=expneg(add(p[k],-max));sum=add(sum,p[k]);}float inv=1.0f/sum;
    for(int j=0;j<HD;j++){float sum=0;for(unsigned k=0;k<=t;k++)sum=std::fma(bf(mul(p[k],inv)),bf(get(OFF_V,size_t(k)*KV+kh*HD+j)),sum);put(OFF_ATT,size_t(t)*H+h*HD+j,sum);}
  }}
  void computeReference(){
    norm(OFF_X,OFF_GAMMA0,OFF_N0);dense(OFF_N0,OFF_WQ,OFF_QR,H,H,OFF_BQ);dense(OFF_N0,OFF_WK,OFF_KR,H,KV,OFF_BK);dense(OFF_N0,OFF_WV,OFF_V,H,KV,OFF_BV);
    rope(OFF_QR,OFF_Q,HEADS);rope(OFF_KR,OFF_K,KVHEADS);attention();dense(OFF_ATT,OFF_WO,OFF_O,H,H);
    for(size_t i=0;i<size_t(tokens)*H;i++)put(OFF_R,i,add(get(OFF_X,i),get(OFF_O,i)));
    norm(OFF_R,OFF_GAMMA1,OFF_N1);dense(OFF_N1,OFF_WG,OFF_GATE,H,F);dense(OFF_N1,OFF_WU,OFF_UP,H,F);
    for(size_t i=0;i<size_t(tokens)*F;i++){float g=get(OFF_GATE,i),e=expneg(g),sig=1.0f/add(1.0f,e);sig=mul(sig,std::signbit(g)?e:1.0f);put(OFF_ACT,i,mul(mul(sig,g),get(OFF_UP,i)));}
    dense(OFF_ACT,OFF_WD,OFF_DOWN,F,H);for(size_t i=0;i<size_t(tokens)*H;i++)put(OFF_Y,i,add(get(OFF_R,i),get(OFF_DOWN,i)));
  }
  void compareStage(unsigned stage){
    need(stage==commits&&stage<15,"stage missing/reordered/duplicated");need(!pending.valid,"stage commit precedes write ACK");
    const auto& s=STAGES[stage];size_t count=size_t(tokens)*s.width;double err2=0,ref2=0;float maxError=0,maxRef=0;uint64_t mismatch=0;
    for(size_t i=0;i<count;i++){need(initialized[s.off/4+i],"unwritten stage output");float a=fp(memory[s.off/4+i]),b=get(s.off,i);need(std::isfinite(a)&&std::isfinite(b),"nonfinite stage output");float e=std::abs(a-b);maxError=std::max(maxError,e);maxRef=std::max(maxRef,std::abs(b));err2+=double(e)*e;ref2+=double(b)*b;mismatch+=bits(a)!=bits(b);}
    double rel=std::sqrt(err2/std::max(ref2,1e-30));
    std::cout<<"STAGE_CHECK phase="<<stage<<" name="<<s.name<<" values="<<count<<" max_abs="<<maxError<<" rel_l2="<<rel<<" bit_diffs="<<mismatch<<" cycle="<<cycles<<std::endl;
    need(maxError<=1e-5f+1e-5f*maxRef&&rel<=1e-5,"stage numerical mismatch "+std::string(s.name));
    checked+=count;bitDifferences+=mismatch;globalMaxError=std::max(globalMaxError,maxError);published[stage]=true;commits++;
  }
  void checkRead(uint64_t offset){for(int i=0;i<16;i++)need(initialized[offset/4+i],"read from poison/uninitialized DDR at "+std::to_string(offset));
    if(offset>=WRITABLE_START)for(unsigned p=0;p<15;p++){auto& s=STAGES[p];if(offset>=s.off&&offset<s.off+size_t(tokens)*s.width*4)need(published[p],"consumer read unpublished producer phase="+std::to_string(p));}}
  bool equal(const Pending& a,const Pending& b){return a.write==b.write&&a.address==b.address&&a.tag==b.tag&&a.mask==b.mask&&a.data==b.data;}
#ifndef BLOCK_AXI
  Pending offered(){Pending p;p.valid=true;p.write=d.io_memory_bits_write;p.address=d.io_memory_bits_address;p.tag=d.io_memory_bits_tag;p.mask=d.io_memory_bits_mask;for(int i=0;i<16;i++)p.data[i]=d.io_memory_bits_data[i];return p;}
#endif
  bool busOffered()const{
#ifdef BLOCK_AXI
    return d.io_axi_aw_valid||d.io_axi_w_valid||d.io_axi_ar_valid;
#else
    return d.io_memory_valid;
#endif
  }
#ifndef BLOCK_AXI
  void step(){
    d.clock=0;d.io_memory_ready=!pending.valid&&(random()%5!=0);d.io_response_valid=pending.valid&&pending.delay==0;
    d.io_response_bits_tag=pending.tag;d.io_response_bits_error=pending.error;for(int i=0;i<16;i++)d.io_response_bits_data[i]=pending.data[i];d.eval();
    bool rf=d.io_memory_valid&&d.io_memory_ready,af=d.io_response_valid&&d.io_response_ready;
    if(d.io_memory_valid){auto p=offered();if(heldValid)need(equal(p,held),"request changed under backpressure");held=p;heldValid=!d.io_memory_ready;}else need(!heldValid,"withdrawn memory request");
    if(d.io_memory_valid&&!d.io_memory_ready)requestStalls++;if(pending.valid&&pending.delay)responseStalls++;
    if(d.io_stageCommit)compareStage(d.io_committedPhase);
    Pending next;
    if(rf){need(!pending.valid,"more than one request in flight");next=offered();next.delay=random()%4;
      need((next.address&63)==0&&next.address>=BASE&&next.address-BASE+64<=ARENA_BYTES,"unaligned/out-of-arena address");uint64_t off=next.address-BASE;
      if(next.write){need(off>=WRITABLE_START,"write into readonly region");writes++;if(inject&&!injected&&writes==4){next.error=!corruptTag;if(corruptTag)next.tag^=1;injected=true;}}
      else{reads++;checkRead(off);for(int i=0;i<16;i++)next.data[i]=memory[off/4+i];}
    }
    d.clock=1;d.eval();cycles++;
    if(af){if(pending.write&&!pending.error&&!(corruptTag&&injected)){
        auto off=pending.address-BASE;for(int j=0;j<64;j++)if((pending.mask>>j)&1){auto i=(off+j)/4;unsigned sh=((off+j)%4)*8;memory[i]=(memory[i]&~(255u<<sh))|(((pending.data[j/4]>>(8*(j%4)))&255)<<sh);initialized[i]=1;}
      }acks++;pending.valid=false;}
    if(rf)pending=next;else if(pending.valid&&pending.delay)pending.delay--;d.clock=0;d.eval();
  }
#else
  Pending awBuffer,wBuffer,awHeld,wHeld,arHeld;bool awHeldValid=false,wHeldValid=false,arHeldValid=false;
  void step(){
    d.clock=0;
    d.io_axi_aw_ready=!pending.valid&&!awBuffer.valid&&(random()%3!=0);
    d.io_axi_w_ready=!pending.valid&&!wBuffer.valid&&(random()%4!=0);
    d.io_axi_ar_ready=!pending.valid&&!awBuffer.valid&&!wBuffer.valid&&(random()%5!=0);
    d.io_axi_b_valid=pending.valid&&pending.write&&pending.delay==0;
    d.io_axi_r_valid=pending.valid&&!pending.write&&pending.delay==0;
    d.io_axi_b_bits_id=pending.tag;d.io_axi_b_bits_resp=pending.error?2:0;
    d.io_axi_r_bits_id=pending.tag;d.io_axi_r_bits_resp=pending.error?2:0;d.io_axi_r_bits_last=1;
    for(int i=0;i<16;i++)d.io_axi_r_bits_data[i]=pending.data[i];d.eval();
    bool aw=d.io_axi_aw_valid&&d.io_axi_aw_ready,w=d.io_axi_w_valid&&d.io_axi_w_ready,ar=d.io_axi_ar_valid&&d.io_axi_ar_ready;
    bool ack=(d.io_axi_b_valid&&d.io_axi_b_ready)||(d.io_axi_r_valid&&d.io_axi_r_ready);
    if(d.io_stageCommit){need(!awBuffer.valid&&!wBuffer.valid,"stage published partial AXI write");compareStage(d.io_committedPhase);}
    Pending a,b,c;
    if(d.io_axi_aw_valid){a.valid=true;a.address=d.io_axi_aw_bits_addr;a.tag=d.io_axi_aw_bits_id;need(d.io_axi_aw_bits_len==0&&d.io_axi_aw_bits_size==6&&d.io_axi_aw_bits_burst==1,"AXI AW burst contract");if(awHeldValid)need(equal(a,awHeld),"AW changed under stall");awHeld=a;awHeldValid=!aw;}
    else need(!awHeldValid,"AW withdrawn");
    if(d.io_axi_w_valid){b.valid=true;b.write=true;b.mask=d.io_axi_w_bits_strb;for(int i=0;i<16;i++)b.data[i]=d.io_axi_w_bits_data[i];need(d.io_axi_w_bits_last,"W missing LAST");if(wHeldValid)need(equal(b,wHeld),"W changed under stall");wHeld=b;wHeldValid=!w;}
    else need(!wHeldValid,"W withdrawn");
    if(d.io_axi_ar_valid){c.valid=true;c.address=d.io_axi_ar_bits_addr;c.tag=d.io_axi_ar_bits_id;need(d.io_axi_ar_bits_len==0&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1,"AXI AR burst contract");if(arHeldValid)need(equal(c,arHeld),"AR changed under stall");arHeld=c;arHeldValid=!ar;}
    else need(!arHeldValid,"AR withdrawn");
    requestStalls+=(d.io_axi_aw_valid&&!aw)+(d.io_axi_w_valid&&!w)+(d.io_axi_ar_valid&&!ar);
    if(pending.valid&&pending.delay)responseStalls++;
    if(aw)awBuffer=a;if(w)wBuffer=b;Pending next;
    if(awBuffer.valid&&wBuffer.valid){need(!ar&&!pending.valid,"AXI overlap");next=wBuffer;next.address=awBuffer.address;next.tag=awBuffer.tag;awBuffer.valid=wBuffer.valid=false;writes++;
      if(inject&&!injected&&writes==4){next.error=!corruptTag;if(corruptTag)next.tag^=1;injected=true;}
    }else if(ar){need(!pending.valid,"AXI read overlap");next=c;reads++;}
    if(next.valid){need((next.address&63)==0&&next.address>=BASE&&next.address-BASE+64<=ARENA_BYTES,"AXI out-of-arena address");next.delay=random()%4;auto off=next.address-BASE;
      if(next.write)need(off>=WRITABLE_START,"AXI write into readonly");else{checkRead(off);for(int i=0;i<16;i++)next.data[i]=memory[off/4+i];}}
    d.clock=1;d.eval();cycles++;
    if(ack){if(pending.write&&!pending.error&&!(corruptTag&&injected)){auto off=pending.address-BASE;for(int j=0;j<64;j++)if((pending.mask>>j)&1){auto i=(off+j)/4;unsigned sh=((off+j)%4)*8;memory[i]=(memory[i]&~(255u<<sh))|(((pending.data[j/4]>>(8*(j%4)))&255)<<sh);initialized[i]=1;}}
      acks++;pending.valid=false;}
    if(next.valid)pending=next;else if(pending.valid&&pending.delay)pending.delay--;d.clock=0;d.eval();
  }
#endif
  void nextRequest(unsigned epoch,bool reset){
    need(!pending.valid&&!heldValid,"request boundary has in-flight traffic");
    if(reset){d.reset=1;for(int i=0;i<5;i++)step();d.reset=0;step();}
    need(d.io_launch_ready,"new request not accepted after completion/reset");
    std::fill(memory.begin()+WRITABLE_START/4,memory.end(),0x7fc00001u);
    std::fill(initialized.begin()+WRITABLE_START/4,initialized.end(),0);
    published.fill(false);commits=0;checked=0;bitDifferences=0;globalMaxError=0;
    reads=writes=acks=requestStalls=responseStalls=cycles=0;inject=false;corruptTag=false;injected=false;
    for(unsigned t=0;t<tokens;t++)for(int i=0;i<H;i++)set(OFF_X,size_t(t)*H+i,float(int((i*37u+t*101u+epoch*73u)%1021)-510)*0.00390625f);
    computeReference();run(epoch);
  }
  void rejectLaunch(bool badBase){
    d.io_launch_bits_base=BASE+(badBase?1:0);d.io_launch_bits_limit=BASE+ARENA_BYTES;
    d.io_launch_bits_tokens=badBase?tokens:0;d.io_launch_bits_epoch=1;d.io_launch_valid=1;step();d.io_launch_valid=0;
    for(int i=0;!d.io_result_valid&&i<20;i++)step();
    need(d.io_result_valid&&d.io_result_bits_status==5&&reads==0&&writes==0&&commits==0,"malformed launch reached memory");
    std::cout<<"BLOCK_BAD_LAUNCH_PASS kind="<<(badBase?"alignment":"tokens_zero")<<std::endl;
  }
  void run(unsigned epoch=1){
#ifdef BLOCK_IDMA
    const uint64_t dmaBase=d.io_idmaTransfers;
#endif
    d.io_launch_bits_base=BASE;d.io_launch_bits_limit=BASE+ARENA_BYTES;d.io_launch_bits_tokens=tokens;d.io_launch_bits_epoch=epoch;d.io_launch_valid=1;
    for(int i=0;!d.io_launch_ready&&i<100;i++)step();need(d.io_launch_ready,"launch timeout");step();d.io_launch_valid=0;
    uint64_t bound=2000000ULL+uint64_t(tokens)*(uint64_t(H)*H*2+uint64_t(H)*KV*2+uint64_t(H)*F*3)*2+uint64_t(tokens)*tokens*H*30;
    while(!d.io_result_valid&&cycles<bound)step();need(d.io_result_valid,"block watchdog timeout phase="+std::to_string(d.io_phase));
    if(inject){need(injected&&d.io_result_bits_status!=0&&commits==0&&d.io_resetRequired,"failed write published output");std::cout<<"BLOCK_FAULT_PASS kind="<<(corruptTag?"tag":"write_error")<<" status="<<unsigned(d.io_result_bits_status)<<std::endl;}
    else{
      need(d.io_result_bits_status==0&&commits==15,"block result failure status="+std::to_string(d.io_result_bits_status));
      uint64_t expectedMac=uint64_t(tokens)*(uint64_t(H)*H*2+uint64_t(H)*KV*2+uint64_t(H)*F*3)+uint64_t(tokens)*(tokens+1)*H;
      // Count padded full-array issues separately from useful model MACs.
      const uint64_t denseSteps=((uint64_t(tokens)+15)/16)*
        (uint64_t(H)*((H+31)/32)*2+uint64_t(H)*((KV+31)/32)*2+
         uint64_t(H)*((F+31)/32)*2+uint64_t(F)*((H+31)/32));
      const uint64_t attentionSteps=uint64_t(tokens)*(tokens+1)*H/16;
      const uint64_t expectedExecuted=PHYSICAL_MAC_LANES==512?(denseSteps+attentionSteps)*512:expectedMac;
      need(d.io_result_bits_executedMacs==expectedExecuted,"physical MAC accounting mismatch");need(d.io_result_bits_macs==expectedMac,"MAC accounting differs from independent shape equation");need(reads*64==d.io_readBytes&&writes*64==d.io_writeBytes,"DDR counters mismatch");
      #ifdef BLOCK_IDMA
      need(d.io_idmaTransfers-dmaBase==reads+writes,"not every transaction passed the actual pinned iDMA");
      std::cout<<"PINNED_IDMA_BLOCK transfers="<<(d.io_idmaTransfers-dmaBase)<<" external_read_beats="<<reads<<" external_write_beats="<<writes<<" full_backend=1"<<std::endl;
#endif
      uint64_t hash=1469598103934665603ULL;for(size_t i=0;i<size_t(tokens)*H;i++)hash=(hash^memory[OFF_Y/4+i])*1099511628211ULL;
      std::cout<<"CONTINUOUS_QWEN2_BLOCK_PASS tokens="<<tokens<<" hidden="<<H<<" ffn="<<F<<" heads="<<HEADS<<" kv_heads="<<KVHEADS<<" phases="<<commits<<" checked_fp32="<<checked<<" bit_diffs="<<bitDifferences<<" max_abs="<<globalMaxError<<" cycles="<<d.io_result_bits_cycles<<" macs="<<expectedMac<<" read_bytes="<<reads*64<<" write_bytes="<<writes*64<<" request_stalls="<<requestStalls<<" response_delay_cycles="<<responseStalls<<" hash="<<std::hex<<hash<<std::dec<<" host_intermediate_writes=0 full_model=0 canonical_512_array="<<(PHYSICAL_MAC_LANES==512)<<" executed_macs="<<d.io_result_bits_executedMacs<<std::endl;
    }
    auto resultStatus=d.io_result_bits_status;step();step();need(d.io_result_valid&&d.io_result_bits_status==resultStatus,"completion not held");d.io_result_ready=1;step();d.io_result_ready=0;
    if(inject){d.io_launch_valid=1;for(int i=0;i<8;i++){need(!d.io_launch_ready&&!busOffered()&&!d.io_result_valid,"poisoned request escaped reset lockout");step();}d.io_launch_valid=0;}
  }
};
int main(int argc,char**argv){try{
  std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);need(argc>=2,"usage: TOKENS [write-error|tag-error|ARENA] [seed]");
  unsigned n=std::stoul(argv[1]);need(n>0&&n<=MAX_TOKENS,"invalid tokens");unsigned seed=argc>3?std::stoul(argv[3]):20260906;
  auto t=std::make_unique<BlockTest>(n,seed);std::string mode=argc>2?argv[2]:"synthetic";
  if(mode=="bad-count"||mode=="bad-base"){t->rejectLaunch(mode=="bad-base");return 0;}
  bool recover=mode=="recover-write"||mode=="recover-tag";
  if(mode=="write-error"||mode=="tag-error"||recover){t->inject=true;t->corruptTag=mode=="tag-error"||mode=="recover-tag";t->initialize();}
  else if(mode=="synthetic"||mode=="repeat")t->initialize();else t->loadArena(mode);
  t->run();if(mode=="repeat"||recover){t->nextRequest(2,recover);std::cout<<"BLOCK_SECOND_REQUEST_PASS reset="<<recover<<" epoch=2"<<std::endl;}return 0;
}catch(const std::exception&e){std::cerr<<"BLOCK_FAIL: "<<e.what()<<std::endl;return 1;}}

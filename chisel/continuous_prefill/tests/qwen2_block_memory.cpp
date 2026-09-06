// SPDX-License-Identifier: Apache-2.0
// External memory service and independent CPU oracle. Never supplies an operator
// result to the DUT: only reads input/weight bytes and acknowledges DUT writes.
#ifdef USE_AXI
#include "VQwen2BlockAxiTop.h"
using Device=VQwen2BlockAxiTop;
#else
#include "VQwen2ContinuousBlock.h"
using Device=VQwen2ContinuousBlock;
#endif
#include "verilated.h"
#include "block_layout.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <filesystem>

using Words=std::vector<uint32_t>;
static uint32_t bits(float x){uint32_t u;std::memcpy(&u,&x,4);return u;}
static float fl(uint32_t u){float x;std::memcpy(&x,&u,4);return x;}
static float add(float x,float y){volatile float z=x+y;return z;}
static float mul(float x,float y){volatile float z=x*y;return z;}
static float divf(float x,float y){volatile float z=x/y;return z;}
static float bf(float x){uint32_t u=bits(x);if((u&0x7f800000)==0x7f800000)return x;u+=0x7fff+((u>>16)&1);return fl(u&0xffff0000);}
static float expneg(float x){
  x=std::fabs(x);if(x>=80)return 0;
  float z=mul(x,float(1.0/std::log(2.0)));unsigned k=unsigned(z);float f=add(z,-float(k));
  float c[8];double fact=1;for(int i=0;i<=7;i++){if(i)fact*=i;c[i]=float(std::pow(-std::log(2.0),i)/fact);}
  float p=c[7];for(int i=6;i>=0;i--)p=add(mul(p,f),c[i]);return mul(p,fl((127-k)<<23));
}
static uint64_t mix(uint64_t x){x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}
struct Tensor{const char* name;uint64_t offset;uint64_t count;bool external;};
static std::vector<Tensor> tensors(int t){return {
 {"wq",OFF_WQ,uint64_t(H)*H,true},{"wk",OFF_WK,uint64_t(H)*KVHEADS*HD,true},{"wv",OFF_WV,uint64_t(H)*KVHEADS*HD,true},
 {"wo",OFF_WO,uint64_t(H)*H,true},{"wg",OFF_WG,uint64_t(H)*F,true},{"wu",OFF_WU,uint64_t(H)*F,true},{"wd",OFF_WD,uint64_t(F)*H,true},
 {"gamma0",OFF_GAMMA0,H,true},{"gamma1",OFF_GAMMA1,H,true},{"bq",OFF_BQ,H,true},{"bk",OFF_BK,KVHEADS*HD,true},{"bv",OFF_BV,KVHEADS*HD,true},
 {"cos",OFF_COS,uint64_t(t)*HD/2,true},{"sin",OFF_SIN,uint64_t(t)*HD/2,true},{"x",OFF_X,uint64_t(t)*H,true},
 {"n0",OFF_N0,uint64_t(t)*H,false},{"qr",OFF_QR,uint64_t(t)*H,false},{"kr",OFF_KR,uint64_t(t)*KVHEADS*HD,false},{"v",OFF_V,uint64_t(t)*KVHEADS*HD,false},
 {"q",OFF_Q,uint64_t(t)*H,false},{"k",OFF_K,uint64_t(t)*KVHEADS*HD,false},{"att",OFF_ATT,uint64_t(t)*H,false},{"o",OFF_O,uint64_t(t)*H,false},
 {"r",OFF_R,uint64_t(t)*H,false},{"n1",OFF_N1,uint64_t(t)*H,false},{"gate",OFF_GATE,uint64_t(t)*F,false},{"up",OFF_UP,uint64_t(t)*F,false},
 {"act",OFF_ACT,uint64_t(t)*F,false},{"down",OFF_DOWN,uint64_t(t)*H,false},{"y",OFF_Y,uint64_t(t)*H,false}};}
static void require(bool p,const std::string& msg){if(!p)throw std::runtime_error(msg);}
struct Oracle {
  const Words& memory;int t;
  std::vector<Words> expected;
  Oracle(const Words& m,int n):memory(m),t(n){}
  float weight(uint64_t o,uint64_t i)const{return fl(memory.at(o/4+i));}
  Words norm(const Words& x,uint64_t gamma){Words y(x.size());for(int r=0;r<t;r++){
    float sum=0;for(int i=0;i<H;i++)sum=add(sum,mul(fl(x[r*H+i]),fl(x[r*H+i])));
    float inv=divf(1.0f,std::sqrt(add(mul(sum,float(1.0/H)),1e-6f)));
    for(int i=0;i<H;i++)y[r*H+i]=bits(bf(mul(mul(fl(x[r*H+i]),inv),weight(gamma,i))));
  }return y;}
  Words dense(const Words& x,uint64_t w,int k,int n,int64_t bias=-1){Words y(uint64_t(t)*n);
    for(int r=0;r<t;r++)for(int c=0;c<n;c+=16){float acc[16]={};
      for(int j=0;j<k;j++){float a=bf(fl(x[r*k+j]));for(int i=0;i<16;i++)acc[i]=std::fma(a,bf(weight(w,uint64_t(j)*n+c+i)),acc[i]);}
      for(int i=0;i<16;i++)y[r*n+c+i]=bits(bias<0?acc[i]:add(acc[i],weight(uint64_t(bias),c+i)));
    }return y;}
  Words rope(const Words& x,int heads){Words y(x.size());for(int r=0;r<t;r++)for(int h=0;h<heads;h++)for(int i=0;i<HD/2;i++){
    int j=r*heads*HD+h*HD+i;float a=fl(x[j]),b=fl(x[j+HD/2]);float c=weight(OFF_COS,r*HD/2+i),s=weight(OFF_SIN,r*HD/2+i);
    y[j]=bits(add(mul(a,c),-mul(b,s)));y[j+HD/2]=bits(add(mul(a,s),mul(b,c)));
  }return y;}
  Words attention(const Words& q,const Words& k,const Words& v){Words y(uint64_t(t)*H);
    for(int r=0;r<t;r++)for(int h=0;h<HEADS;h++){
      std::vector<float> score(r+1),p(r+1);float max=-INFINITY,sum=0;
      for(int j=0;j<=r;j++){float acc[16]={};int kh=h/(HEADS/KVHEADS);
        for(int d=0;d<HD;d+=16)for(int i=0;i<16;i++)acc[i]=std::fma(bf(fl(q[r*H+h*HD+d+i])),bf(fl(k[j*KVHEADS*HD+kh*HD+d+i])),acc[i]);
        float dot=0;for(float a:acc)dot=add(dot,a);score[j]=mul(dot,float(1.0/std::sqrt(double(HD))));max=std::max(max,score[j]);}
      for(int j=0;j<=r;j++){p[j]=expneg(add(score[j],-max));sum=add(sum,p[j]);}
      float inv=divf(1.0f,sum);for(int i=0;i<HD;i++){float acc=0;for(int j=0;j<=r;j++)acc=std::fma(bf(mul(p[j],inv)),bf(fl(v[j*KVHEADS*HD+(h/(HEADS/KVHEADS))*HD+i])),acc);y[r*H+h*HD+i]=bits(acc);}
    }return y;
  }
  static Words plus(const Words& a,const Words& b){Words y(a.size());for(size_t i=0;i<a.size();i++)y[i]=bits(add(fl(a[i]),fl(b[i])));return y;}
  void execute(){Words x(memory.begin()+OFF_X/4,memory.begin()+OFF_X/4+uint64_t(t)*H);
    expected.push_back(norm(x,OFF_GAMMA0));
    expected.push_back(dense(expected[0],OFF_WQ,H,H,OFF_BQ));
    expected.push_back(dense(expected[0],OFF_WK,H,KVHEADS*HD,OFF_BK));
    expected.push_back(dense(expected[0],OFF_WV,H,KVHEADS*HD,OFF_BV));
    expected.push_back(rope(expected[1],HEADS));expected.push_back(rope(expected[2],KVHEADS));
    expected.push_back(attention(expected[4],expected[5],expected[3]));
    expected.push_back(dense(expected[6],OFF_WO,H,H));expected.push_back(plus(x,expected[7]));
    expected.push_back(norm(expected[8],OFF_GAMMA1));expected.push_back(dense(expected[9],OFF_WG,H,F));expected.push_back(dense(expected[9],OFF_WU,H,F));
    Words act(uint64_t(t)*F);for(size_t i=0;i<act.size();i++){float g=fl(expected[10][i]),e=expneg(g);float sig=divf(1.0f,add(1.0f,e));sig=mul(sig,std::signbit(g)?e:1.0f);act[i]=bits(mul(mul(sig,g),fl(expected[11][i])));}
    expected.push_back(std::move(act));expected.push_back(dense(expected[12],OFF_WD,F,H));expected.push_back(plus(expected[8],expected[13]));
  }
};
struct Harness {
  Device d;
  Words mem;std::vector<uint8_t> valid;
  uint64_t base=0x100000000ULL,cycle=0,reads=0,writes=0,stalls=0,compared=0,hash=0xcbf29ce484222325ULL,seed=807;
  int tokens,commits=0,faultPhase=-1;std::string faultKind;bool injected=false;
  struct Pending{bool active=false,write=false;uint64_t off=0,tag=0,mask=0;std::array<uint32_t,16> data{};int delay=0;} pending;
  Oracle* oracle=nullptr;
  const std::array<uint64_t,15> output={OFF_N0,OFF_QR,OFF_KR,OFF_V,OFF_Q,OFF_K,OFF_ATT,OFF_O,OFF_R,OFF_N1,OFF_GATE,OFF_UP,OFF_ACT,OFF_DOWN,OFF_Y};
  Harness(int t):mem(ARENA_BYTES/4,0x7fc0babe),valid(ARENA_BYTES/4,0),tokens(t){d.io_launch_valid=0;d.io_result_ready=0;
#ifdef USE_AXI
    d.io_axi_ar_ready=0;d.io_axi_aw_ready=0;d.io_axi_w_ready=0;d.io_axi_r_valid=0;d.io_axi_b_valid=0;
#else
    d.io_memory_ready=0;d.io_response_valid=0;
#endif
    d.reset=1;for(int i=0;i<5;i++){d.clock=0;d.eval();d.clock=1;d.eval();}d.reset=0;}
  void inputs(int epoch,const std::string& directory){
    for(const auto& a:tensors(tokens)){
      if(!a.external){std::fill(mem.begin()+a.offset/4,mem.begin()+a.offset/4+a.count,0x7fc0babe);std::fill(valid.begin()+a.offset/4,valid.begin()+a.offset/4+a.count,0);continue;}
      if(!directory.empty()){
        std::ifstream f(directory+"/"+a.name+".bin",std::ios::binary);require(bool(f),"missing external input "+std::string(a.name));
        f.read(reinterpret_cast<char*>(mem.data()+a.offset/4),a.count*4);require(uint64_t(f.gcount())==a.count*4 && f.peek()==std::char_traits<char>::eof(),"wrong byte count "+std::string(a.name));
      }else for(uint64_t i=0;i<a.count;i++){
        uint64_t v=mix(i+a.offset*17+(std::string(a.name)=="x"?epoch*1234567:0));float value;
        std::string n=a.name;
        if(n=="gamma0"||n=="gamma1")value=bf(1.0f+float(int(v%9)-4)/128);
        else if(n=="cos"||n=="sin"){uint64_t p=i/(HD/2),j=i%(HD/2);double angle=double(p)/std::pow(1000000.0,double(2*j)/HD);value=float(n=="cos"?std::cos(angle):std::sin(angle));}
        else if(n=="x")value=float(int(v%127)-63)/64;
        else if(n[0]=='b')value=bf(float(int(v%17)-8)/1024);
        else value=bf(float(int(v%31)-15)/512);
        mem[a.offset/4+i]=bits(value);
      }
      for(uint64_t i=0;i<a.count;i++)require(std::isfinite(fl(mem[a.offset/4+i])),"nonfinite external input "+std::string(a.name));
      std::fill(valid.begin()+a.offset/4,valid.begin()+a.offset/4+a.count,1);
    }
  }
  void checkStage(){
    if(d.io_stageCommit){require(!pending.active,"stage published with outstanding DDR/AXI transaction");int p=d.io_committedPhase;require(p==commits,"missing/duplicate/OOO stage commit");require(oracle!=nullptr,"missing oracle");
      const auto& ref=oracle->expected.at(p);double maxError=0;uint64_t different=0;
      for(size_t i=0;i<ref.size();i++){
        uint64_t a=output[p]/4+i;require(valid[a],"stage committed before output byte initialized");float actual=fl(mem[a]),expected=fl(ref[i]);
        require(std::isfinite(actual)&&std::isfinite(expected),"nonfinite output");double e=std::fabs(double(actual)-expected);maxError=std::max(maxError,e);different+=mem[a]!=ref[i];
        if(e>1e-5+1e-5*std::fabs(expected))throw std::runtime_error("numeric mismatch stage="+std::to_string(p)+" i="+std::to_string(i)+" actual="+std::to_string(actual)+" expected="+std::to_string(expected)+" bits="+std::to_string(mem[a])+" ref="+std::to_string(ref[i]));
        hash=(hash^mem[a])*1099511628211ULL;compared++;
      }
      std::cout<<"BLOCK_STAGE_PASS phase="<<p<<" elements="<<ref.size()<<" bit_differences="<<different<<" max_abs="<<maxError<<" cycle="<<cycle<<std::endl;commits++;
    }
  }
  void checkWrite(const Pending& p){
    require(p.off>=WRITABLE_START,"write to immutable input or weight");
    auto ts=tensors(tokens);int phase=int(d.io_phase);require(phase>=0&&phase<15,"write outside block phase");
    const auto& tensor=ts.at(15+phase);
    require(p.off>=tensor.offset && p.off+64<=tensor.offset+tensor.count*4,"write outside current producer tensor");
  }
  void applyWrite(const Pending& p){
    for(int i=0;i<16;i++){uint32_t u=mem[p.off/4+i];for(int b=0;b<4;b++)if((p.mask>>(4*i+b))&1)u=(u&~(255u<<(8*b)))|(p.data[i]&(255u<<(8*b)));mem[p.off/4+i]=u;if(((p.mask>>(4*i))&15)==15)valid[p.off/4+i]=1;}
  }
#ifdef USE_AXI
  bool awHeld=false,wHeld=false;uint64_t awOff=0,axiMask=0;std::array<uint32_t,16> axiData{};
  void tick(){
    d.clock=0;
    d.io_axi_ar_ready=!pending.active&&!awHeld&&!wHeld&&(mix(cycle+3)%5!=0);
    d.io_axi_aw_ready=!pending.active&&!awHeld&&(mix(cycle+7)%4!=0);
    d.io_axi_w_ready=!pending.active&&!wHeld&&(mix(cycle+17)%3!=0);
    d.io_axi_r_valid=pending.active&&!pending.write&&pending.delay==0;
    d.io_axi_b_valid=pending.active&&pending.write&&pending.delay==0;
    d.io_axi_r_bits_id=0;d.io_axi_r_bits_response=0;d.io_axi_r_bits_last=1;
    d.io_axi_b_bits_id=0;d.io_axi_b_bits_response=0;
    for(int i=0;i<16;i++)d.io_axi_r_bits_data[i]=pending.data[i];
    bool hasReply=d.io_axi_r_valid||d.io_axi_b_valid;
    if(hasReply&&!injected&&int(d.io_phase)==faultPhase&&(faultKind=="tag"||(faultKind=="write"&&pending.write)||(faultKind=="read"&&!pending.write))){
      if(faultKind=="tag"){if(pending.write)d.io_axi_b_bits_id=1;else d.io_axi_r_bits_id=1;}
      else{if(pending.write)d.io_axi_b_bits_response=2;else d.io_axi_r_bits_response=2;}injected=true;
    }
    d.eval();
    bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready,aw=d.io_axi_aw_valid&&d.io_axi_aw_ready,w=d.io_axi_w_valid&&d.io_axi_w_ready;
    bool answered=(d.io_axi_r_valid&&d.io_axi_r_ready)||(d.io_axi_b_valid&&d.io_axi_b_ready);
    bool bad=pending.write?(d.io_axi_b_bits_response||d.io_axi_b_bits_id):(d.io_axi_r_bits_response||d.io_axi_r_bits_id);
    if((d.io_axi_ar_valid&&!d.io_axi_ar_ready)||(d.io_axi_aw_valid&&!d.io_axi_aw_ready)||(d.io_axi_w_valid&&!d.io_axi_w_ready))stalls++;
    auto offset=[&](uint64_t address){require(address>=base&&address-base+64<=ARENA_BYTES&&(address&63)==0,"AXI address");return address-base;};
    Pending next;
    if(ar){require(!aw&&!w&&!awHeld&&!wHeld,"mixed AXI transaction");require(d.io_axi_ar_bits_id==0&&d.io_axi_ar_bits_len==0&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1,"AR attributes");
      next.active=true;next.off=offset(d.io_axi_ar_bits_address);next.delay=int(mix(cycle+11)%4);
      for(int i=0;i<16;i++){require(valid.at(next.off/4+i]),"AXI read before producer B ACK");next.data[i]=mem.at(next.off/4+i);}reads++;
    }
    if(aw){require(d.io_axi_aw_bits_id==0&&d.io_axi_aw_bits_len==0&&d.io_axi_aw_bits_size==6&&d.io_axi_aw_bits_burst==1,"AW attributes");awOff=offset(d.io_axi_aw_bits_address);awHeld=true;}
    if(w){require(d.io_axi_w_bits_last,"W last");for(int i=0;i<16;i++)axiData[i]=d.io_axi_w_bits_data[i];axiMask=d.io_axi_w_bits_strobe;wHeld=true;}
    if(awHeld&&wHeld){require(!pending.active&&!ar,"multiple outstanding AXI requests");next.active=true;next.write=true;next.off=awOff;next.mask=axiMask;next.data=axiData;next.delay=int(mix(cycle+19)%5);checkWrite(next);awHeld=false;wHeld=false;writes++;}
    checkStage();d.clock=1;d.eval();d.clock=0;d.eval();
    if(answered){if(pending.write&&!bad)applyWrite(pending);pending.active=false;}
    else if(pending.active&&pending.delay>0)pending.delay--;
    if(next.active)pending=next;cycle++;
  }
#else
  void tick(){
    d.clock=0;d.io_memory_ready=!pending.active&&(mix(cycle+seed)%5!=0);
    if(!pending.active&&!d.io_memory_ready)stalls++;
    d.io_response_valid=pending.active&&pending.delay==0;
    d.io_response_bits_tag=pending.tag;d.io_response_bits_error=0;
    for(int i=0;i<16;i++)d.io_response_bits_data[i]=pending.data[i];
    if(d.io_response_valid && !injected && int(d.io_phase)==faultPhase &&
       (faultKind=="tag" || (faultKind=="write"&&pending.write)||(faultKind=="read"&&!pending.write))){
      if(faultKind=="tag")d.io_response_bits_tag^=1;else d.io_response_bits_error=1;injected=true;
    }
    d.eval();bool accept=d.io_memory_valid&&d.io_memory_ready;bool answer=d.io_response_valid&&d.io_response_ready;
    Pending next;
    if(accept){next.active=true;next.write=d.io_memory_bits_write;next.tag=d.io_memory_bits_tag;next.mask=d.io_memory_bits_mask;next.delay=int(mix(cycle+seed+101)%4);
      require(d.io_memory_bits_address>=base,"address below arena");next.off=d.io_memory_bits_address-base;
      require(next.off%64==0&&next.off+64<=ARENA_BYTES,"unaligned/out-of-arena memory request");
      if(next.write){checkWrite(next);for(int i=0;i<16;i++)next.data[i]=d.io_memory_bits_data[i];writes++;}
      else{for(int i=0;i<16;i++){require(valid.at(next.off/4+i)),"read before producer write ACK phase="+std::to_string(d.io_phase)+" offset="+std::to_string(next.off+4*i));next.data[i]=mem.at(next.off/4+i);}reads++;}
    }
    checkStage();
    d.clock=1;d.eval();d.clock=0;d.eval();
    if(answer){if(pending.write && !d.io_response_bits_error && (d.io_response_bits_tag==pending.tag)){
      for(int i=0;i<16;i++){uint32_t u=mem[pending.off/4+i];for(int b=0;b<4;b++)if((pending.mask>>(4*i+b))&1)u=(u&~(255u<<(8*b)))|(pending.data[i]&(255u<<(8*b)));mem[pending.off/4+i]=u;if(((pending.mask>>(4*i))&15)==15)valid[pending.off/4+i]=1;}
    }pending.active=false;}
    else if(pending.active&&pending.delay>0)pending.delay--;
    if(accept)pending=next;cycle++;
  }
#endif
  void dump(const std::string& path){
    require(!std::filesystem::exists(path),"refuse to overwrite captured outputs");std::filesystem::create_directories(path);
    for(const auto& a:tensors(tokens))if(!a.external){std::ofstream f(path+"/"+a.name+".bin",std::ios::binary);f.write(reinterpret_cast<const char*>(mem.data()+a.offset/4),a.count*4);require(bool(f),"capture write failure");}
  }
  void run(int epoch,uint64_t limit){
    commits=0;Oracle ref(mem,tokens);ref.execute();oracle=&ref;
    d.io_launch_bits_base=base;d.io_launch_bits_limit=base+ARENA_BYTES;d.io_launch_bits_tokens=tokens;d.io_launch_bits_epoch=epoch;d.io_launch_valid=1;
    tick();require(d.io_phase==0,"launch phase");d.io_launch_valid=0;
    uint64_t start=cycle;while(!d.io_result_valid && cycle-start<limit)tick();
    require(d.io_result_valid,"cycle watchdog phase="+std::to_string(d.io_phase));
    if(faultPhase>=0){require(injected,"fault was not injected");require(d.io_result_bits_status!=0&&d.io_resetRequired,"fault silently accepted");require(commits<=faultPhase,"consumer committed after failure");
      std::cout<<"BLOCK_FAULT_PASS phase="<<faultPhase<<" kind="<<faultKind<<" status="<<unsigned(d.io_result_bits_status)<<" commits="<<commits<<std::endl;
    }else{
      require(d.io_result_bits_status==0&&commits==15&&!pending.active,"bad final completion");
      uint64_t mac=uint64_t(tokens)*(2ULL*H*H+2ULL*H*KVHEADS*HD+3ULL*H*F)+uint64_t(tokens)*(tokens+1)*H;
      require(d.io_result_bits_macs==mac,"incorrect useful MAC counter");require(d.io_result_bits_executedMacs==mac*(PHYSICAL_MAC_LANES/16),"incorrect padded MAC counter");
      std::cout<<"QWEN2_BLOCK_CONTINUOUS_PASS tokens="<<tokens<<" hidden="<<H<<" ffn="<<F<<" epoch="<<epoch<<" stages="<<commits<<" compared="<<compared<<" cycles="<<d.io_result_bits_cycles<<" useful_macs="<<mac<<" useful_lanes_per_issue=16 physical_mac_lanes="<<PHYSICAL_MAC_LANES<<" executed_macs="<<d.io_result_bits_executedMacs<<" reads="<<reads<<" writes="<<writes<<" request_stalls="<<stalls<<" hash="<<std::hex<<hash<<std::dec<<" host_intermediate_writes=0 full_model=0 weights_profile=canonical_fp32_bf16_mac"<<std::endl;
    }
    const auto status=d.io_result_bits_status;const auto reportedCycles=d.io_result_bits_cycles;
    for(int i=0;i<4;i++){tick();require(d.io_result_valid&&d.io_result_bits_status==status&&d.io_result_bits_cycles==reportedCycles,"result changed under backpressure");}
    if(faultPhase>=0){d.io_result_ready=1;tick();d.io_result_ready=0;d.io_launch_valid=1;
      for(int i=0;i<4;i++){tick();require(!d.io_launch_ready&&!d.io_result_valid,"failed request accepted restart without reset");}d.io_launch_valid=0;
    }else{d.io_result_ready=1;tick();d.io_result_ready=0;}
    oracle=nullptr;
  }
};
int main(int argc,char**argv){try{
  Verilated::commandArgs(argc,argv);int t=argc>1?std::stoi(argv[1]):3;require(t>0&&t<=MAX_TOKENS,"tokens out of range");
  std::string dir,dump;int repeats=1,fault=-1;std::string kind;uint64_t cycles=90000000000ULL;
  for(int i=2;i<argc;i++){std::string a=argv[i];if(a=="--inputs"&&i+1<argc)dir=argv[++i];else if(a=="--dump"&&i+1<argc)dump=argv[++i];else if(a=="--repeat"&&i+1<argc)repeats=std::stoi(argv[++i]);else if(a=="--fault"&&i+2<argc){fault=std::stoi(argv[++i]);kind=argv[++i];}else if(a=="--cycles"&&i+1<argc)cycles=std::stoull(argv[++i]);else throw std::runtime_error("unknown argument "+a);}
  require(repeats>0&&repeats<=100,"repeat count");require(fault<15 && (fault<0||kind=="read"||kind=="write"||kind=="tag"),"fault specification");
  std::cout<<"BLOCK_INPUT mode="<<(dir.empty()?"synthetic":"external_directory")<<" tokens="<<t<<" hidden="<<H<<" ffn="<<F<<std::endl;
  Harness h(t);h.faultPhase=fault;h.faultKind=kind;for(int e=1;e<=repeats;e++){h.inputs(e,dir);h.run(e,cycles);if(fault>=0)break;if(!dump.empty())h.dump(dump+"/epoch"+std::to_string(e));}return 0;
}catch(const std::exception&e){std::cerr<<"BLOCK_FAIL "<<e.what()<<std::endl;return 1;}}

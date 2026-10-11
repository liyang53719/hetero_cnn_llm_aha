// WORK-ONLY CANDIDATE. Not the frozen canonical recipe or implemented hardware.
// Ordinary C++ software numerical model; not a hardware simulator.
#include "block_layout.h"
#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <filesystem>
#include <cstdlib>
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

#if defined(__x86_64__) || defined(__i386__)
#include <xmmintrin.h>
#endif
static void verifyFloatEnvironment(){
  need(std::fesetround(FE_TONEAREST)==0 && std::fegetround()==FE_TONEAREST,"FE_TONEAREST unavailable");
#if defined(__x86_64__) || defined(__i386__)
  unsigned before=_mm_getcsr();_mm_setcsr(before & ~((1u<<15)|(1u<<6)));
  unsigned after=_mm_getcsr();need((after&((1u<<15)|(1u<<6)))==0,"cannot clear FTZ/DAZ");
#endif
  // Volatile operands keep these execution probes out of constant folding.
  volatile float tiny=fp(0x00000001u),one=1.0f,half=0.5f,normal=fp(0x00800000u);
  volatile float pzero=fp(0u),nzero=fp(0x80000000u),minusone=-1.0f;
  volatile float a=fp(0x3f800001u),b=fp(0x3f7ffffeu);
  need(bits(add(tiny,tiny))==2u,"subnormal add probe failed");
  need(bits(mul(tiny,one))==1u,"subnormal multiply probe failed");
  need(bits(mul(normal,half))==0x00400000u,"gradual underflow probe failed");
  need(bits(std::fma(tiny,one,pzero))==1u,"subnormal FMA probe failed");
  need(bits(mul(nzero,one))==0x80000000u && bits(mul(pzero,one))==0u,"signed-zero multiply probe failed");
  need(bits(add(nzero,nzero))==0x80000000u && bits(add(nzero,pzero))==0u,"signed-zero add probe failed");
  need(bits(std::fma(a,b,minusone))==0xa8800000u,"single-round FMA probe failed");
  need(bits(add(mul(a,b),minusone))==0u,"uncontracted multiply-add probe failed");
  std::cout<<"SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10";
#if defined(__x86_64__) || defined(__i386__)
  std::cout<<" arch=x86 mxcsr_before="<<before<<" mxcsr_after="<<after<<" ftz=0 daz=0";
#else
  std::cout<<" arch=other mxcsr_before=unavailable mxcsr_after=unavailable ftz=probe_verified daz=probe_verified";
#endif
  std::cout<<std::endl;
}

class SoftwareRecipe {
public:
  std::vector<float> reference; unsigned tokens;
  std::vector<float> candidateScores,candidateLogits,candidateSoftmax,candidateProb,candidateSilu;
  SoftwareRecipe(unsigned t):reference(ARENA_BYTES/4,fp(0x7fc00001u)),tokens(t){}
  float get(uint64_t offset,size_t i)const{return reference.at(offset/4+i);}
  void put(uint64_t offset,size_t i,float x){reference.at(offset/4+i)=x;}
  void norm(uint64_t in,uint64_t gamma,uint64_t out){for(unsigned t=0;t<tokens;t++){
    float sum=0;for(int i=0;i<H;i++){float x=get(in,size_t(t)*H+i);sum=add(sum,mul(x,x));}
    float inv=1.0f/std::sqrt(add(mul(sum,float(1.0/H)),1e-6f));for(int i=0;i<H;i++)put(out,size_t(t)*H+i,bf(mul(bf(mul(get(in,size_t(t)*H+i),inv)),get(gamma,i))));
  }}
  void dense(uint64_t in,uint64_t w,uint64_t out,int K,int N,int64_t bias=-1){
    std::vector<float> a(K);for(unsigned t=0;t<tokens;t++){for(int k=0;k<K;k++)a[k]=bf(get(in,size_t(t)*K+k));
      for(int col=0;col<N;col+=16){float sums[16]={};for(int k=0;k<K;k++){const float* weights=reference.data()+w/4+size_t(k)*N+col;for(int j=0;j<16;j++)sums[j]=std::fma(a[k],bf(weights[j]),sums[j]);}
        for(int j=0;j<16;j++)put(out,size_t(t)*N+col+j,bf(bias>=0?add(sums[j],get(bias,col+j)):sums[j]));
      }
    }
  }
  void rope(uint64_t in,uint64_t out,int heads){int width=heads*HD;for(unsigned t=0;t<tokens;t++)for(int h=0;h<heads;h++)for(int j=0;j<HD/2;j++){
    auto ix=size_t(t)*width+h*HD+j;float x=get(in,ix),y=get(in,ix+HD/2),c=bf(get(OFF_COS,size_t(t)*HD/2+j)),s=bf(get(OFF_SIN,size_t(t)*HD/2+j));
    put(out,ix,bf(add(bf(mul(x,c)),-bf(mul(y,s)))));put(out,ix+HD/2,bf(add(bf(mul(x,s)),bf(mul(y,c)))));
  }}
  void attention(){candidateScores.resize(size_t(HEADS)*tokens*tokens);candidateLogits.resize(candidateScores.size());candidateSoftmax.assign(candidateScores.size(),0);candidateProb.assign(candidateScores.size(),0);std::vector<float> p(tokens);for(unsigned t=0;t<tokens;t++)for(int h=0;h<HEADS;h++){
    int kh=h/(HEADS/KVHEADS);float max=-INFINITY;
    for(unsigned k=0;k<tokens;k++){float parts[16]={};for(int j=0;j<HD;j++)parts[j%16]=std::fma(bf(get(OFF_Q,size_t(t)*H+h*HD+j)),bf(get(OFF_K,size_t(k)*KV+kh*HD+j)),parts[j%16]);
      float sum=0;for(float x:parts)sum=add(sum,x);p[k]=bf(mul(bf(sum),float(1.0/std::sqrt(double(HD)))));candidateScores[(size_t(h)*tokens+t)*tokens+k]=p[k];candidateLogits[(size_t(h)*tokens+t)*tokens+k]=k<=t?p[k]:fp(0xff7f0000u);if(k<=t)max=std::max(max,p[k]);}
    float sum=0;for(unsigned k=0;k<=t;k++){p[k]=expneg(add(p[k],-max));sum=add(sum,p[k]);}float inv=1.0f/sum;
    for(unsigned k=0;k<=t;k++){candidateSoftmax[(size_t(h)*tokens+t)*tokens+k]=mul(p[k],inv);candidateProb[(size_t(h)*tokens+t)*tokens+k]=bf(mul(p[k],inv));}
    for(int j=0;j<HD;j++){float sum=0;for(unsigned k=0;k<=t;k++)sum=std::fma(bf(mul(p[k],inv)),bf(get(OFF_V,size_t(k)*KV+kh*HD+j)),sum);put(OFF_ATT,size_t(t)*H+h*HD+j,bf(sum));}
  }}
  void computeReference(){candidateSilu.resize(size_t(tokens)*F);
    norm(OFF_X,OFF_GAMMA0,OFF_N0);dense(OFF_N0,OFF_WQ,OFF_QR,H,H,OFF_BQ);dense(OFF_N0,OFF_WK,OFF_KR,H,KV,OFF_BK);dense(OFF_N0,OFF_WV,OFF_V,H,KV,OFF_BV);
    rope(OFF_QR,OFF_Q,HEADS);rope(OFF_KR,OFF_K,KVHEADS);attention();dense(OFF_ATT,OFF_WO,OFF_O,H,H);
    for(size_t i=0;i<size_t(tokens)*H;i++)put(OFF_R,i,bf(add(get(OFF_X,i),get(OFF_O,i))));
    norm(OFF_R,OFF_GAMMA1,OFF_N1);dense(OFF_N1,OFF_WG,OFF_GATE,H,F);dense(OFF_N1,OFF_WU,OFF_UP,H,F);
    for(size_t i=0;i<size_t(tokens)*F;i++){float g=get(OFF_GATE,i),e=expneg(g),sig=1.0f/add(1.0f,e);sig=mul(sig,std::signbit(g)?e:1.0f);candidateSilu[i]=bf(mul(sig,g));put(OFF_ACT,i,bf(mul(candidateSilu[i],get(OFF_UP,i))));}
    dense(OFF_ACT,OFF_WD,OFF_DOWN,F,H);for(size_t i=0;i<size_t(tokens)*H;i++)put(OFF_Y,i,bf(add(get(OFF_R,i),get(OFF_DOWN,i))));
  }

};
int main(int argc,char** argv){try{
  need(argc==4,"usage: software_recipe readonly_arena tokens output_directory");
  verifyFloatEnvironment();
  need(sizeof(float)==4,"FP32 host required");
  uint32_t endian=1;need(*reinterpret_cast<uint8_t*>(&endian)==1,"little-endian host required");
  unsigned t=std::stoul(argv[2]);need(t>0&&t<=MAX_TOKENS,"token capacity exceeded");
  SoftwareRecipe model(t);
  std::ifstream input(argv[1],std::ios::binary|std::ios::ate);
  need(bool(input)&&uint64_t(input.tellg())==WRITABLE_START,"readonly arena length mismatch");
  input.seekg(0);input.read(reinterpret_cast<char*>(model.reference.data()),WRITABLE_START);
  need(bool(input),"short readonly arena read");
  model.computeReference();
  auto dump=[&](const char* name,const std::vector<float>& values){std::ofstream f(std::filesystem::path(argv[3])/(std::string(name)+".f32le"),std::ios::binary);f.write(reinterpret_cast<const char*>(values.data()),values.size()*4);need(bool(f),"candidate diagnostic write failed");};
  dump("scores",model.candidateScores);dump("logits",model.candidateLogits);dump("softmax_fp32",model.candidateSoftmax);dump("prob",model.candidateProb);dump("silu",model.candidateSilu);
  for(unsigned phase=0;phase<STAGES.size();phase++){
    const auto& s=STAGES[phase];size_t count=size_t(t)*s.width;
    for(size_t i=0;i<count;i++)need(std::isfinite(model.get(s.off,i)),"nonfinite stage output");
    auto path=std::filesystem::path(argv[3])/("phase_"+std::to_string(phase)+"_"+s.name+"_recipe.f32le");
    need(!std::filesystem::exists(path),"refuse output overwrite");
    std::ofstream output(path,std::ios::binary);
    output.write(reinterpret_cast<const char*>(model.reference.data()+s.off/4),count*4);
    need(bool(output),"short stage output write");
    std::cout<<"SOFTWARE_RECIPE_STAGE phase="<<phase<<" name="<<s.name<<" values="<<count<<std::endl;
  }
  std::cout<<"SOFTWARE_RECIPE_COMPLETE tokens="<<t<<" stages=15"<<std::endl;
  return 0;
}catch(const std::exception& e){std::cerr<<"SOFTWARE_RECIPE_FAIL "<<e.what()<<std::endl;return 1;}}

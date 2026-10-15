// Tiny numerical payload candidate only. No RTL or production ABI.
// Physical normal mode: a[16] broadcast against b[256], five shared contexts.
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <xmmintrin.h>
static float fp(uint32_t u){float x;std::memcpy(&x,&u,4);return x;}
static uint32_t bits(float x){uint32_t u;std::memcpy(&u,&x,4);return u;}
static float (*volatile fused)(float,float,float)=::fmaf;
static float accum[5][16][256];
static unsigned progress[5], contexts=0;
static bool poisoned=false;
static uint32_t bf(uint32_t u){
  if((u&0x7f800000)==0x7f800000)return u;
  return (u+0x7fff+((u>>16)&1))&0xffff0000;
}
extern "C" int environment_ok(){
  return std::fegetround()==FE_TONEAREST && !(_mm_getcsr()&0xe040);
}
extern "C" int reset(){
  if(!environment_ok())return -1;
  contexts=0;poisoned=false;std::memset(progress,0,sizeof(progress));return 0;
}
extern "C" int begin(unsigned count){
  if(poisoned||count==0||count>5)return -1;
  for(unsigned c=0;c<contexts;c++)if(progress[c]!=8)return -1;
  contexts=count;std::memset(progress,0,sizeof(progress));
  for(auto& c:accum)for(auto& row:c)for(auto& x:row)x=fp(0x7fc00001);
  return 0;
}
extern "C" int step(unsigned context,unsigned index,unsigned columns,
                    const uint16_t* a,const uint16_t* b,const unsigned* valid,uint32_t* out){
  if(!environment_ok()||poisoned||context>=contexts||index>=8||progress[context]!=index||
     !columns||columns>128||columns%32)return -1;
  for(unsigned r=0;r<16;r++)if(valid[r]>columns)return -1;
  for(unsigned r=0;r<16;r++)for(unsigned c=0;c<columns;c++){
    float& x=accum[context][r][c];if(index==0)x=0.0f;
    x=fused(fp(uint32_t(a[r])<<16),fp(uint32_t(b[c])<<16),x);
    // Exactly the source owner's selected-lane finite gate on EVERY step.
    // Noncausal / padded cells are not a numerical error for this operation.
    if(c<valid[r]&&!std::isfinite(x)){poisoned=true;return -2;}
  }
  ++progress[context];
  if(index==7)std::memcpy(out,accum[context],sizeof(accum[context]));
  return index==7?1:0;
}
static int checked(float a,float b,bool multiply,uint32_t* out){
  if(!environment_ok()||!std::isfinite(a)||!std::isfinite(b))return -2;
  std::feclearexcept(FE_ALL_EXCEPT);
  volatile float value=multiply?a*b:a+b;
  *out=bits(value);
  return !std::isfinite(value)||std::fetestexcept(FE_INVALID|FE_DIVBYZERO|FE_OVERFLOW|FE_UNDERFLOW)?-2:0;
}
extern "C" int scalar_add(uint32_t a,uint32_t b,uint32_t* out){return checked(fp(a),fp(b),false,out);}
extern "C" int post_dot(uint32_t total,uint32_t* out){
  out[0]=bf(total); // first, completed-dot BF16 materialization
  if(checked(fp(out[0]),fp(0x3db504f3),true,out+1))return -2;
  out[2]=bf(out[1]); // second, post-scale BF16 materialization
  return std::isfinite(fp(out[2]))?0:-2;
}
extern "C" unsigned accumulator_bytes(){return sizeof(accum);}

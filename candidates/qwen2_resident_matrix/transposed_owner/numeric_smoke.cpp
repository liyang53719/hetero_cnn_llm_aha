// SPDX-License-Identifier: Apache-2.0
// HOST MODEL ONLY. No RTL endpoint or production FPU replacement.
// Tiny ABI for one M128/K1536/N160 derived Dense group. Every accumulator
// update is driven by an accepted bank-model MatrixStreamStep payload.
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>

// Exact helper bodies from the frozen qwen2_block.cpp recipe.
static uint32_t bits(float x){uint32_t r;std::memcpy(&r,&x,4);return r;}
static float fp(uint32_t x){float r;std::memcpy(&r,&x,4);return r;}
static float bf(float x){uint32_t u=bits(x);if((u&0x7f800000)==0x7f800000)return x;return fp((u+0x7fff+((u>>16)&1))&0xffff0000);}
static float add(float a,float b){return a+b;}

static float accum[5][16][256];
static unsigned nextK[5];
extern "C" int td_reset(){
  if(std::fesetround(FE_TONEAREST))return -1;
  std::memset(accum,0,sizeof(accum));std::memset(nextK,0,sizeof(nextK));return 0;
}
extern "C" int td_step(unsigned k,unsigned context,unsigned clear,unsigned last,
                       unsigned finish,unsigned emit,const uint16_t* a,const uint16_t* b,uint32_t* terminal){
  if(context>=5 || k>=1536 || k!=nextK[context] || clear!=(k==0) || last!=(k==1535) ||
     finish!=(last && context==4) || emit!=last)return -1;
  for(unsigned i=0;i<16;i++)if((a[i]&0x7f80)==0x7f80)return -2;
  for(unsigned i=0;i<144;i++)if((b[i]&0x7f80)==0x7f80)return -2;
  for(unsigned r=0;r<16;r++)for(unsigned col=0;col<256;col++){
    const unsigned slice=col/32;
    const float weight=fp(uint32_t(slice<4?a[r]:b[128+r])<<16);
    const float activation=fp(uint32_t(b[(slice%4)*32+col%32])<<16);
    float& x=accum[context][r][col];if(clear)x=0.0f;
    x=std::fma(weight,activation,x);
    if(last){if(!std::isfinite(x))return -3;terminal[r*256+col]=bits(x);}
  }
  nextK[context]++;return last?1:0;
}
extern "C" int td_reference(const uint32_t* a,const uint16_t* rawOutputMajorWeight,uint32_t* output){
  // Independent direct row-major dot reference. It does not inspect bank
  // coordinates, accepted-step payloads or the physical accumulator array.
  for(unsigned m=0;m<128;m++)for(unsigned n=0;n<160;n++){
    float sum=0.0f;
    for(unsigned k=0;k<1536;k++)
      sum=std::fma(bf(fp(a[m*1536+k])),fp(uint32_t(rawOutputMajorWeight[n*1536+k])<<16),sum);
    if(!std::isfinite(sum))return -1;output[m*160+n]=bits(sum);
  }
  return 0;
}
extern "C" int td_add_bias(const uint32_t* output,const uint16_t* bias,uint32_t* biased){
  for(unsigned m=0;m<128;m++)for(unsigned n=0;n<160;n++){
    const float value=add(fp(output[m*160+n]),fp(uint32_t(bias[n])<<16));
    if(!std::isfinite(value))return -1;biased[m*160+n]=bits(value);
  }
  return 0;
}

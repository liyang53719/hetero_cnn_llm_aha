// SPDX-License-Identifier: Apache-2.0
// HOST MODEL ONLY. No RTL endpoint or production FPU replacement.
// Five existing 16x256 banks, erased at EVERY N-group/K-chunk boundary.
// Arithmetic is driven only by accepted MatrixStreamStep payloads.
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>

// Exact helper bodies from the frozen qwen2_block.cpp recipe.
static uint32_t bits(float x){uint32_t r;std::memcpy(&r,&x,4);return r;}
static float fp(uint32_t x){float r;std::memcpy(&r,&x,4);return r;}
static float bf(float x){uint32_t u=bits(x);if((u&0x7f800000)==0x7f800000)return x;return fp((u+0x7fff+((u>>16)&1))&0xffff0000);}

static float accum[5][16][256];
static unsigned nextK[5], seedNext[5];
static unsigned chunkStart=0, chunkEnd=0, contexts=0;
static bool bankValid[5], seedOpen[5];

extern "C" int td_reset(){
  if(std::fesetround(FE_TONEAREST))return -1;
  std::memset(accum,0,sizeof(accum));std::memset(nextK,0,sizeof(nextK));
  std::memset(seedNext,0,sizeof(seedNext));std::memset(bankValid,0,sizeof(bankValid));
  std::memset(seedOpen,0,sizeof(seedOpen));chunkStart=chunkEnd=contexts=0;return 0;
}

extern "C" int td_group(unsigned start,unsigned end,unsigned count){
  if(start>=end || end>8960 || end-start>2560 || start%16 || end%16 || !count || count>5)return -1;
  chunkStart=start;chunkEnd=end;contexts=count;
  // NaNs make it impossible to pass by retaining an old chunk or N-group.
  // A continuing chunk must restore all 4096 physical FP32 cells per bank.
  for(unsigned c=0;c<5;c++){
    nextK[c]=start;bankValid[c]=seedOpen[c]=false;seedNext[c]=0;
    for(unsigned r=0;r<16;r++)for(unsigned col=0;col<256;col++)accum[c][r][col]=fp(0x7fc00001);
  }
  return 0;
}

extern "C" int td_seed_begin(unsigned context){
  if(context>=contexts || !chunkStart || bankValid[context] || seedOpen[context] || seedNext[context])return -1;
  seedOpen[context]=true;return 0;
}

extern "C" int td_seed_beat(unsigned context,unsigned index,const uint32_t* words){
  if(context>=contexts || !seedOpen[context] || index>=256 || seedNext[context]!=index || bankValid[context])return -1;
  unsigned slice=index/32,cluster=index%32,row=cluster/2,col=slice*32+(cluster%2)*16;
  for(unsigned i=0;i<16;i++){
    if((words[i]&0x7f800000)==0x7f800000)return -2;
    accum[context][row][col+i]=fp(words[i]);
  }
  seedNext[context]++;return 0;
}

extern "C" int td_seed_commit(unsigned context){
  if(context>=contexts || !seedOpen[context] || seedNext[context]!=256 || bankValid[context])return -1;
  bankValid[context]=true;seedOpen[context]=false;return 0;
}

extern "C" int td_step(unsigned k,unsigned context,unsigned clear,unsigned last,
                       unsigned finish,unsigned emit,const uint16_t* a,const uint16_t* b,uint32_t* terminal){
  if(context>=contexts || k<chunkStart || k>=chunkEnd || k!=nextK[context] || clear!=(k==0) ||
     last!=(k+1==chunkEnd) || finish!=(last && context+1==contexts) || emit!=last ||
     seedOpen[context] || (!clear&&!bankValid[context]))return -1;
  for(unsigned i=0;i<16;i++)if((a[i]&0x7f80)==0x7f80)return -2;
  for(unsigned i=0;i<144;i++)if((b[i]&0x7f80)==0x7f80)return -2;
  for(unsigned i=144;i<256;i++)if(b[i])return -2;
  for(unsigned r=0;r<16;r++)for(unsigned col=0;col<256;col++){
    const unsigned slice=col/32;
    const float weight=fp(uint32_t(slice<4?a[r]:b[128+r])<<16);
    const float activation=fp(uint32_t(b[(slice%4)*32+col%32])<<16);
    float& x=accum[context][r][col];if(clear)x=0.0f;
    x=std::fma(weight,activation,x);
    if(last){if(!std::isfinite(x))return -3;terminal[r*256+col]=bits(x);}
  }
  bankValid[context]=true;nextK[context]++;return last?1:0;
}

extern "C" int td_reference(const uint32_t* a,const uint16_t* rawOutputMajorWeight,uint32_t* output,unsigned columns){
  // Called only AFTER owner completion. Independent direct row-major dot
  // reference: no bank coordinates, accepted payloads or accumulator access.
  // Both full input/weight rows have stride K8960; output stride is columns.
  // Actual Qwen2 Down has no bias, so none is manufactured or added here.
  if(!columns || columns>1536)return -1;
  for(unsigned m=0;m<128;m++)for(unsigned n=0;n<columns;n++){
    float sum=0.0f;
    for(unsigned k=0;k<8960;k++)
      sum=std::fma(bf(fp(a[m*8960+k])),fp(uint32_t(rawOutputMajorWeight[n*8960+k])<<16),sum);
    if(!std::isfinite(sum))return -1;output[m*columns+n]=bits(sum);
  }
  return 0;
}

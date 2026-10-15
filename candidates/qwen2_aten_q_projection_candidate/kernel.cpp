// Source-corresponding SOFTWARE candidate. No RTL or hardware timing claim.
// Fixed PyTorch 449b176... AVX2 BF16 transa dot, K=1536 only.
#include <cmath>
#include <cfenv>
#include <cstdint>
#include <cstring>
#include <xmmintrin.h>
static float from(uint32_t u) { float x; std::memcpy(&x,&u,4); return x; }
static uint32_t bits(float x) { uint32_t u; std::memcpy(&u,&x,4); return u; }
static float bf(float x) { auto u=bits(x); return from((u+0x7fff+((u>>16)&1))&0xffff0000); }
static bool environment() { return std::fegetround()==FE_TONEAREST && !(_mm_getcsr()&0x8040); }
extern "C" int candidate_rms(const float* x,const float* gamma,float* y,int rows) {
  if(!environment() || rows<1 || rows>128) return -1;
  for(int m=0;m<rows;m++) {
    float total=0;
    for(int lane=0;lane<8;lane++) {
      float lane_sum=0;
      for(int residue=0;residue<4;residue++) {
        float residue_sum=0;
        for(int block=0;block<3;block++) {
          float partial=0;
          for(int term=0;term<16;term++) {
            float a=x[m*1536+block*512+term*32+residue*8+lane];
            if(!std::isfinite(a)) return -2;
            partial=partial+a*a;
          }
          residue_sum=residue_sum+partial;
        }
        lane_sum=lane_sum+residue_sum;
      }
      total=total+lane_sum;
    }
    float mean=total/1536.0f;
    float scale=1.0f/std::sqrt(mean+1.0e-6f);
    for(int k=0;k<1536;k++) {
      if(!std::isfinite(gamma[k])) return -2;
      y[m*1536+k]=bf(bf(x[m*1536+k]*scale)*gamma[k]);
      if(!std::isfinite(y[m*1536+k])) return -2;
    }
  }
  return 0;
}
extern "C" int candidate_q(const float* x,const uint16_t* weight_input_major,
    const float* bias,const int* columns,int count,int rows,float* raw,float* out) {
  if(!environment() || rows<1 || rows>128 || count<1 || count>1536) return -1;
  for(int c=0;c<count;c++) if(columns[c]<0 || columns[c]>=1536) return -1;
  for(int m=0;m<rows;m++) for(int c=0;c<count;c++) {
    // One logical output, exactly 64 persistent F32 accumulators; no K split.
    float s[8][8]={};
    for(int t=0;t<24;t++) for(int r=0;r<8;r++) for(int l=0;l<8;l++) {
      int k=64*t+8*r+l;
      float a=x[m*1536+k], b=from(uint32_t(weight_input_major[k*1536+columns[c]])<<16);
      if(!std::isfinite(a) || (bits(a)&0xffff) || !std::isfinite(b)) return -2;
      s[r][l]=std::fma(a,b,s[r][l]);
    }
    for(int offset=4;offset;offset/=2)
      for(int r=0;r<offset;r++) for(int l=0;l<8;l++) s[r][l]=s[r][l]+s[r+offset][l];
    for(int offset=4;offset;offset/=2)
      for(int l=0;l<offset;l++) s[0][l]=s[0][l]+s[0][l+offset];
    // Fixed source adds the zero tail reduction even for divisible K.
    float dot=s[0][0]+0.0f, b=bias[columns[c]];
    if(!std::isfinite(dot) || !std::isfinite(b) || (bits(b)&0xffff)) return -2;
    raw[m*count+c]=dot;
    out[m*count+c]=bf(b+dot);
    if(!std::isfinite(out[m*count+c])) return -2;
  }
  return 0;
}

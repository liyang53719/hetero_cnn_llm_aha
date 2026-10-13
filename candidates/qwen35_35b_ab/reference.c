/* Independent logical-coordinate diagnostic, never an execution resource.
 * Strict libm fmaf, full K2048 ascending or two K1024 pair-high-first partials.
 * No owner, Matrix packet, banking coordinate, torch or saved native output.
 */
#include <fenv.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <xmmintrin.h>

#pragma STDC FENV_ACCESS ON
static float (*volatile ordered_fmaf)(float,float,float) = fmaf;
static float fp(uint32_t u) { float f; memcpy(&f,&u,4); return f; }
static uint32_t bits(float f) { uint32_t u; memcpy(&u,&f,4); return u; }
static uint16_t bf16(float f) {
  uint32_t u=bits(f); return (uint16_t)((u+0x7fffu+((u>>16)&1u))>>16);
}
unsigned reference_mxcsr(void) { return _mm_getcsr(); }
int reference_environment(void) {
  if (fegetround()!=FE_TONEAREST || (_mm_getcsr()&0x8040u)) return -1;
  volatile float tiny=fp(1), one=1.0f;
  return bits(ordered_fmaf(tiny,one,0.0f))==1 ? 0 : -2;
}
int reference_self_test(void) {
  if(reference_environment()) return -1;
  if(bits(ordered_fmaf(fp(0x3f800001),fp(0x3f7ffffe),-1.0f))!=0xa8800000u) return -2;
  if(bf16(fp(0x3f808000))!=0x3f80 || bf16(fp(0x3f818000))!=0x3f82) return -3;
  if(bf16(fp(0x00010000))!=1 || bf16(fp(0x00008000))!=0 || bf16(fp(0x00018000))!=2) return -4;
  if(bits(ordered_fmaf(fp(0x00010000),1.0f,0.0f))!=0x00010000u) return -5;
  unsigned old=_mm_getcsr(); _mm_setcsr(old|0x8040u);
  int refused=reference_environment(); _mm_setcsr(old);
  if(refused!=-1 || reference_environment()) return -6;
  return 0;
}
/* Call counters below are diagnostic observations, not hardware counters. */
int reference_run(unsigned m,unsigned mode,const uint16_t *a,const uint16_t *w,
                  uint16_t *out,float *pre_bf16,uint64_t *counts) {
  if ((m!=16&&m!=128)||mode>1||!a||!w||!out||!pre_bf16||!counts||reference_environment()) return -1;
  const unsigned k=2048,n=32;
  float *af=malloc((size_t)m*k*4),*wf=malloc((size_t)n*k*4);
  if(!af||!wf) {free(af);free(wf);return -2;}
  for(size_t i=0;i<(size_t)m*k;++i) {af[i]=fp((uint32_t)a[i]<<16);if(!isfinite(af[i])){free(af);free(wf);return -3;}}
  for(size_t i=0;i<(size_t)n*k;++i) {wf[i]=fp((uint32_t)w[i]<<16);if(!isfinite(wf[i])){free(af);free(wf);return -3;}}
  memset(counts,0,3*sizeof(*counts));
  for(unsigned row=0;row<m;++row) for(unsigned col=0;col<n;++col) {
    const float *x=af+(size_t)row*k,*v=wf+(size_t)col*k;
    float sum=0.0f;
    if(mode==0) {
      for(unsigned d=0;d<k;++d) {sum=ordered_fmaf(x[d],v[d],sum); uint32_t u=bits(sum)&0x7fffffffu;counts[1]+=(u>0&&u<0x00800000u);}
    } else {
      float low=0.0f,high=0.0f;
      for(unsigned ordinal=0;ordinal<1024;++ordinal) {
        unsigned d=ordinal^1u;
        low=ordered_fmaf(x[d],v[d],low);
        high=ordered_fmaf(x[1024+d],v[1024+d],high);
        uint32_t l=bits(low)&0x7fffffffu,h=bits(high)&0x7fffffffu;
        counts[1]+=(l>0&&l<0x00800000u)+(h>0&&h<0x00800000u);
      }
      sum=low+high; ++counts[2];
    }
    counts[0]+=k;
    if(!isfinite(sum)||(bf16(sum)&0x7f80)==0x7f80) {free(af);free(wf);return -4;}
    pre_bf16[(size_t)row*n+col]=sum;out[(size_t)row*n+col]=bf16(sum);
  }
  free(af);free(wf);return reference_environment();
}

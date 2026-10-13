/* Independent original O: BF16[M,4096] x BF16[2048,4096].
 * No owner output, Matrix bank/packet arithmetic, or expected result is input.
 * Every accumulation is external libm fmaf under verified RNE/gradual FP32.
 * Modes: 0 sequential; 1 full pair-high; 2 two independent pair-high K2048
 * partials; 3 four independent pair-high K1024 partials/left fold;
 * 4 the same four partials/balanced merge. One final BF16 RNE conversion.
 */
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <xmmintrin.h>

#pragma STDC FENV_ACCESS ON
_Static_assert(sizeof(float)==4 && FLT_RADIX==2 && FLT_MANT_DIG==24 &&
               FLT_MAX_EXP==128 && FLT_EVAL_METHOD==0, "strict IEEE FP32 required");
enum { O_K=4096, O_N=2048, O_MODES=5 };
static float (*volatile ordered_fmaf)(float,float,float) = fmaf;
static float fp(uint32_t u) { float f; memcpy(&f,&u,4); return f; }
static uint32_t bits(float f) { uint32_t u; memcpy(&u,&f,4); return u; }
static uint16_t bf16(float f) {
  uint32_t u=bits(f); return (uint16_t)((u+0x7fffu+((u>>16)&1u))>>16);
}
static float partialAdd(float low,float high) {
  volatile float result=low+high; return result;
}
unsigned o_reference_mxcsr(void) { return _mm_getcsr(); }
unsigned o_reference_n(void) { return O_N; }
unsigned o_reference_k(void) { return O_K; }
unsigned o_reference_modes(void) { return O_MODES; }
int o_reference_environment(void) {
  if(fegetround()!=FE_TONEAREST || (_mm_getcsr()&0xe040u)) return -1;
  volatile float tiny=fp(1),one=1.0f;
  return bits(ordered_fmaf(tiny,one,0.0f))==1 ? 0 : -2;
}
static float accumulate(const float *x,const float *w,unsigned start,unsigned length,
                        unsigned pair_high,float seed,uint64_t *counts) {
  float sum=seed;
  for(unsigned ordinal=0;ordinal<length;++ordinal) {
    unsigned d=start+(pair_high ? (ordinal^1u) : ordinal);
    sum=ordered_fmaf(x[d],w[d],sum);
    uint32_t u=bits(sum)&0x7fffffffu;
    ++counts[0]; counts[1]+=(u>0&&u<0x00800000u);
  }
  return sum;
}
/* k is fixed to O_K in production; the small selftests exercise this same
 * function at k=8. Each independent partial starts at positive FP32 zero. */
static float recipe(const float *x,const float *w,unsigned k,unsigned mode,uint64_t *counts) {
  if(mode<2) return accumulate(x,w,0,k,mode,0.0f,counts);
  unsigned parts=mode==2 ? 2u : 4u, span=k/parts;
  float p[4];
  for(unsigned i=0;i<parts;++i) p[i]=accumulate(x,w,i*span,span,1,0.0f,counts);
  if(mode==2) { ++counts[2]; return partialAdd(p[0],p[1]); }
  counts[2]+=3;
  if(mode==3) {
    float s01=partialAdd(p[0],p[1]);
    float s012=partialAdd(s01,p[2]);
    return partialAdd(s012,p[3]);
  }
  float s01=partialAdd(p[0],p[1]);
  float s23=partialAdd(p[2],p[3]);
  return partialAdd(s01,s23);
}
int o_reference_self_test(void) {
  if(o_reference_environment()) return -1;
  if(bits(ordered_fmaf(fp(0x3f800001),fp(0x3f7ffffe),-1.0f))!=0xa8800000u) return -2;
  if(bf16(fp(0x3f808000))!=0x3f80 || bf16(fp(0x3f818000))!=0x3f82 ||
     bf16(fp(0xbf808000))!=0xbf80 || bf16(fp(0xbf818000))!=0xbf82) return -3;
  if(bf16(fp(0x00010000))!=1 || bf16(fp(0x00008000))!=0 || bf16(fp(0x00018000))!=2) return -4;
  if(bits(ordered_fmaf(fp(0x00010000),1.0f,0.0f))!=0x00010000u) return -5;
  if(bits(partialAdd(fp(0x3f800000),fp(0x33800000)))!=0x3f800000u ||
     bits(partialAdd(fp(0x3f800001),fp(0x33800000)))!=0x3f800002u) return -6;
  unsigned old=_mm_getcsr(); _mm_setcsr(old|0x8040u);
  int refused=o_reference_environment(); _mm_setcsr(old);
  if(refused!=-1 || o_reference_environment()) return -7;
  _mm_setcsr(old|0x2000u);
  refused=o_reference_environment(); _mm_setcsr(old);
  if(refused!=-1 || o_reference_environment()) return -8;
  int previous=fegetround();
  if(fesetround(FE_DOWNWARD)) return -9;
  refused=o_reference_environment();
  if(fesetround(previous) || refused!=-1 || o_reference_environment()) return -10;
  /* BF16-representable witness: both independent merge modes differ from
   * seeded continuation, and the four-part merge association matters. */
  float x[8]={0,33554432.0f,0,1.0f,0,-33554432.0f,0,1.0f};
  float w[8]={1,1,1,1,1,1,1,1};
  const uint32_t expected[5]={0x3f800000u,0x3f800000u,0,0x3f800000u,0};
  const uint64_t adds[5]={0,0,1,3,3};
  for(unsigned mode=0;mode<O_MODES;++mode) {
    uint64_t counts[3]={0,0,0};
    if(bits(recipe(x,w,8,mode,counts))!=expected[mode] || counts[0]!=8 ||
       counts[1]!=0 || counts[2]!=adds[mode]) return -11-(int)mode;
  }
  for(unsigned pair=0;pair<2;++pair) {
    uint64_t counts[3]={0,0,0};
    float first=accumulate(x,w,0,4,pair,0.0f,counts);
    float seeded=accumulate(x,w,4,4,pair,first,counts);
    if(bits(seeded)!=expected[pair] || counts[0]!=8 || counts[2]!=0) return -16;
  }
  /* Ascending [A,1,-A,1] yields 1; pair-high [1,A,1,-A] yields 0. */
  uint64_t c0[3]={0,0,0},c1[3]={0,0,0};
  float ordered[8]={33554432.0f,1.0f,-33554432.0f,1.0f,0,0,0,0};
  memset(c0,0,sizeof(c0)); memset(c1,0,sizeof(c1));
  if(bits(recipe(ordered,w,8,0,c0))!=0x3f800000u ||
     bits(recipe(ordered,w,8,1,c1))!=0) return -17;
  return o_reference_environment();
}
/* Counts are host diagnostics [fmaf calls, subnormal fmaf results, FP32 adds].
 * Caller supplies complete buffers; no physical-resource/cycle claim. */
int o_reference_run(unsigned m,unsigned mode,const uint16_t *a,const uint16_t *w,
                    uint16_t *out,float *pre_bf16,uint64_t *counts) {
  if((m!=16&&m!=128)||mode>=O_MODES||!a||!w||!out||!pre_bf16||!counts||
     o_reference_environment()) return -1;
  float *af=malloc((size_t)m*O_K*sizeof(float));
  float *wf=malloc((size_t)O_N*O_K*sizeof(float));
  if(!af||!wf) { free(af); free(wf); return -2; }
  for(size_t i=0;i<(size_t)m*O_K;++i) {
    af[i]=fp((uint32_t)a[i]<<16);
    if(!isfinite(af[i])) { free(af); free(wf); return -3; }
  }
  for(size_t i=0;i<(size_t)O_N*O_K;++i) {
    wf[i]=fp((uint32_t)w[i]<<16);
    if(!isfinite(wf[i])) { free(af); free(wf); return -3; }
  }
  memset(counts,0,3*sizeof(*counts));
  for(unsigned row=0;row<m;++row) for(unsigned col=0;col<O_N;++col) {
    float sum=recipe(af+(size_t)row*O_K,wf+(size_t)col*O_K,O_K,mode,counts);
    if(!isfinite(sum)||(bf16(sum)&0x7f80)==0x7f80) { free(af); free(wf); return -4; }
    pre_bf16[(size_t)row*O_N+col]=sum;
    out[(size_t)row*O_N+col]=bf16(sum);
  }
  free(af); free(wf); return o_reference_environment();
}

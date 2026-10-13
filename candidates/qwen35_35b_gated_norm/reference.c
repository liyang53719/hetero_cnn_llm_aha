/* Independent Z K2048/N4096 logical-coordinate diagnostics. Never an owner.
 * Explicit external libm fmaf; no Matrix packets/banks or expected outputs.
 * mode 0: K0..2047 sequential FP32 fmaf.
 * mode 1: two K1024 FP32 partials, pair high first (1,0,3,2,...),
 *         then exactly one FP32 partialAdd, then BF16 round-to-nearest-even.
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
enum { Z_K=2048, Z_N=4096 };
static float (*volatile ordered_fmaf)(float,float,float) = fmaf;
static float fp(uint32_t u) { float f; memcpy(&f,&u,4); return f; }
static uint32_t bits(float f) { uint32_t u; memcpy(&u,&f,4); return u; }
static uint16_t bf16(float f) {
  uint32_t u=bits(f); return (uint16_t)((u+0x7fffu+((u>>16)&1u))>>16);
}
static float partialAdd(float low,float high) {
  volatile float result=low+high; return result;
}
unsigned z_reference_mxcsr(void) { return _mm_getcsr(); }
unsigned z_reference_n(void) { return Z_N; }
unsigned z_reference_k(void) { return Z_K; }
int z_reference_environment(void) {
  /* Include SIMD rounding-control bits: fegetround alone can miss a caller
   * that changed only MXCSR, leaving the x87 rounding mode at FE_TONEAREST. */
  if(fegetround()!=FE_TONEAREST || (_mm_getcsr()&0xe040u)) return -1;
  volatile float tiny=fp(1),one=1.0f;
  return bits(ordered_fmaf(tiny,one,0.0f))==1 ? 0 : -2;
}
int z_reference_self_test(void) {
  if(z_reference_environment()) return -1;
  if(bits(ordered_fmaf(fp(0x3f800001),fp(0x3f7ffffe),-1.0f))!=0xa8800000u) return -2;
  if(bf16(fp(0x3f808000))!=0x3f80 || bf16(fp(0x3f818000))!=0x3f82 ||
     bf16(fp(0xbf808000))!=0xbf80 || bf16(fp(0xbf818000))!=0xbf82) return -3;
  if(bf16(fp(0x00010000))!=1 || bf16(fp(0x00008000))!=0 || bf16(fp(0x00018000))!=2) return -4;
  if(bits(ordered_fmaf(fp(0x00010000),1.0f,0.0f))!=0x00010000u) return -5;
  if(bits(partialAdd(fp(0x3f800000),fp(0x33800000)))!=0x3f800000u ||
     bits(partialAdd(fp(0x3f800001),fp(0x33800000)))!=0x3f800002u) return -6;
  unsigned old=_mm_getcsr(); _mm_setcsr(old|0x8040u);
  int refused=z_reference_environment(); _mm_setcsr(old);
  if(refused!=-1 || z_reference_environment()) return -7;
  _mm_setcsr(old|0x2000u);
  refused=z_reference_environment(); _mm_setcsr(old);
  if(refused!=-1 || z_reference_environment()) return -8;
  int previous=fegetround();
  if(fesetround(FE_DOWNWARD)) return -9;
  refused=z_reference_environment();
  if(fesetround(previous) || refused!=-1 || z_reference_environment()) return -10;
  return 0;
}
/* Caller provides complete uint16 BF16[M,2048] and BF16[4096,2048].
 * Outputs are uint16 BF16[M,4096], float pre_bf16[M,4096], uint64 counts[3].
 * Counts are host observations [fmaf calls, subnormal fmaf results, partialAdds].
 * They are NOT hardware counters, resources, cycles or owner storage.
 */
int z_reference_run(unsigned m,unsigned mode,const uint16_t *a,const uint16_t *w,
                    uint16_t *out,float *pre_bf16,uint64_t *counts) {
  if((m!=16&&m!=128)||mode>1||!a||!w||!out||!pre_bf16||!counts||
     z_reference_environment()) return -1;
  float *af=malloc((size_t)m*Z_K*sizeof(float));
  float *wf=malloc((size_t)Z_N*Z_K*sizeof(float));
  if(!af||!wf) { free(af); free(wf); return -2; }
  for(size_t i=0;i<(size_t)m*Z_K;++i) {
    af[i]=fp((uint32_t)a[i]<<16);
    if(!isfinite(af[i])) { free(af); free(wf); return -3; }
  }
  for(size_t i=0;i<(size_t)Z_N*Z_K;++i) {
    wf[i]=fp((uint32_t)w[i]<<16);
    if(!isfinite(wf[i])) { free(af); free(wf); return -3; }
  }
  memset(counts,0,3*sizeof(*counts));
  for(unsigned row=0;row<m;++row) for(unsigned col=0;col<Z_N;++col) {
    const float *x=af+(size_t)row*Z_K,*v=wf+(size_t)col*Z_K;
    float sum=0.0f;
    if(mode==0) {
      for(unsigned d=0;d<Z_K;++d) {
        sum=ordered_fmaf(x[d],v[d],sum);
        uint32_t u=bits(sum)&0x7fffffffu;
        counts[1]+=(u>0&&u<0x00800000u);
      }
    } else {
      float low=0.0f,high=0.0f;
      for(unsigned ordinal=0;ordinal<1024;++ordinal) {
        unsigned d=ordinal^1u;
        low=ordered_fmaf(x[d],v[d],low);
        high=ordered_fmaf(x[1024+d],v[1024+d],high);
        uint32_t l=bits(low)&0x7fffffffu,h=bits(high)&0x7fffffffu;
        counts[1]+=(l>0&&l<0x00800000u)+(h>0&&h<0x00800000u);
      }
      sum=partialAdd(low,high); ++counts[2];
    }
    counts[0]+=Z_K;
    if(!isfinite(sum)||(bf16(sum)&0x7f80)==0x7f80) { free(af); free(wf); return -4; }
    pre_bf16[(size_t)row*Z_N+col]=sum;
    out[(size_t)row*Z_N+col]=bf16(sum);
  }
  free(af); free(wf); return z_reference_environment();
}

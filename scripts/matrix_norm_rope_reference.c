/* Independent host fmaf Matrix reference. No Python-produced arithmetic input.
 * cc -std=c11 -O2 -fno-fast-math -ffp-contract=off -frounding-math this.c -lm
 * reference input.bin output.bin: input uint32 header[K=1024,columns=256/512],
 * activation[1024] and K-major weight[1024*columns], BF16 widened to uint32.
 * Output final FP32[columns], BF16 widened[columns], aggregate fma flags[cols],
 * followed by every accumulator step in K-major order [1024,columns].
 * reference --fma input.bin output.bin: uint32 triplets -> [result,flags].
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <fenv.h>
#include <float.h>
#if defined(__SSE__)
#include <xmmintrin.h>
#endif
#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || FLT_EVAL_METHOD != 0
#error "Native IEEE binary32 evaluation required"
#endif
#if defined(__FAST_MATH__)
#error "Fast math unsupported"
#endif
static float value(uint32_t x) { float y; memcpy(&y,&x,4); return y; }
static uint32_t bits(float x) { uint32_t y; memcpy(&y,&x,4); return y; }
static uint32_t fused(uint32_t a,uint32_t b,uint32_t c,uint32_t *flag) {
  volatile float x=value(a),y=value(b),z=value(c);
  feclearexcept(FE_ALL_EXCEPT);
  volatile float result=fmaf(x,y,z);
  int f=fetestexcept(FE_ALL_EXCEPT);
  *flag=((f&FE_INVALID)?16u:0u)|((f&FE_DIVBYZERO)?8u:0u)|((f&FE_OVERFLOW)?4u:0u)|((f&FE_UNDERFLOW)?2u:0u)|((f&FE_INEXACT)?1u:0u);
  uint32_t word=bits(result);
  return (word&0x7fffffffu)>0x7f800000u ? 0x7fc00000u : word;
}
static uint32_t convert(uint32_t x) {
  unsigned retained=x>>16,discarded=x&65535u;
  if(discarded>32768u || (discarded==32768u && (retained&1u))) ++retained;
  return retained<<16;
}
static int admitted(uint32_t x) {
  unsigned exponent=(x>>23)&255u;
  return !(x&65535u) && exponent!=255u && (exponent || !(x&0x7fffffffu));
}
int main(int argc,char **argv) {
  int probe=argc==4 && !strcmp(argv[1],"--fma");
  if((!probe && argc!=3) || sizeof(float)!=4 || sizeof(uint32_t)!=4) return 2;
  uint32_t endian=1; if(*(unsigned char *)&endian!=1) return 2;
  if(fesetround(FE_TONEAREST) || fegetround()!=FE_TONEAREST) return 2;
#if defined(__SSE__)
  if(_mm_getcsr() & ((1u<<15)|(1u<<6))) return 2;
#endif
  uint32_t f;
  /* Product rounds up separately, but exact fused cancellation is 2^-46. */
  if(fused(0x3f800001u,0x3f800001u,0xbf800002u,&f)!=0x28800000u || f) return 2;
  if(fused(1u,0x3f000000u,0u,&f)!=0u || f!=3u) return 2;
  FILE *in=fopen(argv[1+probe],"rb"),*out=fopen(argv[2+probe],"wb");
  if(!in || !out) return 2;
  if(probe) {
    uint32_t x[3],y[2]; size_t n;
    while((n=fread(x,1,sizeof x,in))) {
      if(n!=sizeof x) return 3;
      y[0]=fused(x[0],x[1],x[2],&y[1]);
      if(fwrite(y,4,2,out)!=2) return 3;
    }
  } else {
    uint32_t h[2],a[1024],w[512],acc[512]={0},flags[512]={0},rounded[512];
    if(fread(h,4,2,in)!=2 || h[0]!=1024 || (h[1]!=256 && h[1]!=512)) return 3;
    uint32_t *steps=malloc(1024u*h[1]*sizeof(uint32_t));
    if(!steps) return 3;
    if(fread(a,4,1024,in)!=1024) return 3;
    for(unsigned k=0;k<1024;k++) if(!admitted(a[k])) return 3;
    for(unsigned k=0;k<1024;k++) {
      if(fread(w,4,h[1],in)!=h[1]) return 3;
      for(unsigned j=0;j<h[1];j++) {
        if(!admitted(w[j])) return 3;
        acc[j]=fused(a[k],w[j],acc[j],&f); flags[j]|=f;
        steps[k*h[1]+j]=acc[j];
      }
    }
    if(fgetc(in)!=EOF) return 3;
    for(unsigned j=0;j<h[1];j++) {
      if((acc[j]&0x7f800000u)==0x7f800000u) return 3;
      rounded[j]=convert(acc[j]);
      if((rounded[j]&0x7f800000u)==0x7f800000u) return 3;
    }
    if(fwrite(acc,4,h[1],out)!=h[1] || fwrite(rounded,4,h[1],out)!=h[1] || fwrite(flags,4,h[1],out)!=h[1] || fwrite(steps,4,1024u*h[1],out)!=1024u*h[1]) return 3;
    free(steps);
  }
  if(ferror(in) || fclose(in) || fclose(out)) return 3;
  return 0;
}

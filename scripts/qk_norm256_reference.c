/* Independent host-binary32 oracle for admitted Q/K Norm256 candidate heads.
 * Build: cc -std=c11 -O2 -fno-fast-math -ffp-contract=off -frounding-math
 *          scripts/qk_norm256_reference.c -lm -o reference
 * Usage: reference inputs.bin trace.bin
 * Input is consecutive 512-word LE uint32 records: x[256], BF16 weight[256].
 * Output is consecutive 3132-word uint32 records (TRACE_FIELDS Python ABI).
 * No generated Python outputs, libraries, or oracle imports are consumed.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fenv.h>
#include <float.h>
#pragma STDC FENV_ACCESS ON
#pragma STDC FP_CONTRACT OFF
#if defined(__SSE__)
#include <xmmintrin.h>
#endif

static const uint64_t coeff[32] = {
  UINT64_C(0xbef497b73fbd25ee), UINT64_C(0xbedfea6b3fb7a7e6), UINT64_C(0xbecdff353fb29dbe), UINT64_C(0xbebe58e33fadf85e),
  UINT64_C(0xbeb0956f3fa9ab4a), UINT64_C(0xbea4671b3fa5ac16), UINT64_C(0xbe998f8e3fa1f1fe), UINT64_C(0xbe8fdc3f3f9e758d),
  UINT64_C(0xbe8723d63f9b3066), UINT64_C(0xbe7e88713f981d0c), UINT64_C(0xbe7042093f9536bf), UINT64_C(0xbe6344ec3f92795b),
  UINT64_C(0xbe5769013f8fe140), UINT64_C(0xbe4c8c3f3f8d6b3c), UINT64_C(0xbe42919b3f8b147d), UINT64_C(0xbe3960253f88da83),
  UINT64_C(0xbe2cf3ff3f85bf79), UINT64_C(0xbe1e55123f81dd42), UINT64_C(0xbe11a96c3f7c99f7), UINT64_C(0xbe0698873f7607ef),
  UINT64_C(0xbdf9ba233f6ff2c6), UINT64_C(0xbde880283f6a4bc0), UINT64_C(0xbdd92aee3f650674), UINT64_C(0xbdcb73013f60185b),
  UINT64_C(0xbdbf1de73f5b7871), UINT64_C(0xbdb3fb643f571ef6), UINT64_C(0xbda9e3563f530530), UINT64_C(0xbda0b4203f4f2545),
  UINT64_C(0xbd9851683f4b7a15), UINT64_C(0xbd90a31d3f47ff1b), UINT64_C(0xbd8994b63f44b05a), UINT64_C(0xbd8314903f418a48)
};
static uint32_t bits(float x) { uint32_t y; memcpy(&y, &x, 4); return y; }
static float value(uint32_t x) { float y; memcpy(&y, &x, 4); return y; }
static uint32_t flags(void) {
  int f=fetestexcept(FE_ALL_EXCEPT);
  return ((f&FE_INVALID)?16u:0u)|((f&FE_DIVBYZERO)?8u:0u)|((f&FE_OVERFLOW)?4u:0u)|((f&FE_UNDERFLOW)?2u:0u)|((f&FE_INEXACT)?1u:0u);
}
static uint32_t op(uint32_t a,uint32_t b,int multiply,uint32_t *flag) {
  volatile float x=value(a),y=value(b),z;
  feclearexcept(FE_ALL_EXCEPT);
  if(multiply) z=x*y; else z=x+y;
  uint32_t out=bits(z); *flag=flags(); return out;
}
static uint32_t convert(uint32_t x,uint32_t *flag) {
  uint32_t e=x&0x7f800000u, f=x&0x007fffffu;
  if(e==0x7f800000u) {
    *flag=(f && !(f&0x00400000u))?16u:0u;
    return f?0x7fc00000u:x;
  }
  /* Decide the rounding direction from discarded bits rather than the
   * Python oracle's bias-add conversion implementation. */
  uint32_t retained=x>>16, discarded=x&65535u;
  if(discarded>32768u || (discarded==32768u && (retained&1u))) ++retained;
  uint32_t y=retained<<16;
  if((y&0x7f800000u)==0x7f800000u) *flag=5;
  else *flag=(x&65535u)?(1u|((y&0x7f800000u)?0u:2u)):0u;
  return y;
}
static int selftest(void) {
  uint32_t f,y;
  if(fegetround()!=FE_TONEAREST)return 0;
  y=op(0x3f800000u,0x33800000u,0,&f); if(y!=0x3f800000u || f!=1u)return 0;
  y=op(0x3f800001u,0x33800000u,0,&f); if(y!=0x3f800002u || f!=1u)return 0;
  y=op(0x7f7fffffu,0x40000000u,1,&f); if(y!=0x7f800000u || f!=5u)return 0;
  y=op(1u,0x3f000000u,1,&f); if(y!=0u || f!=3u)return 0;
  y=op(0x80000000u,0x3f800000u,1,&f); if(y!=0x80000000u || f!=0u)return 0;
  y=op(0u,0x7f800000u,1,&f); if((y&0x7fffffffu)<=0x7f800000u || f!=16u)return 0;
  return 1;
}
static int admitted(const uint32_t *x) {
  for(int i=0;i<512;i++) {
    unsigned e=(x[i]>>23)&255u;
    if((x[i]&65535u) || ((x[i]&0x7fffffffu) && (e<95u || e>158u))) return 0;
  }
  return 1;
}
static int emit(FILE *out,const uint32_t *x,size_t n) { return fwrite(x,4,n,out)==n; }
#define EMIT(a,n) do { if(!emit(out,(a),(n))) return 0; } while(0)
static int head(FILE *out,const uint32_t *in) {
  uint32_t square[256],sf[256],tree[240],tf[240],part[16],pf[16],running[16],rf[16];
  uint32_t gamma[256],gf[256],scaled[256],xf[256],full[256],ff[256],bf[256],bff[256];
  uint32_t mean,mf,eps,ef,normal,scale,index,rv[8],rvf[8],inverse,domain=0,arithmetic=0,conversion=0,aggregate;
  unsigned t=0;
  for(int i=0;i<256;i++){ square[i]=op(in[i],in[i],1,&sf[i]); arithmetic|=sf[i]; }
  for(int c=0;c<16;c++) {
    uint32_t level[16]; memcpy(level,square+c*16,sizeof(level));
    for(int n=16;n>1;n/=2) {
      for(int j=0;j<n/2;j++) {
        level[j]=op(level[j*2],level[j*2+1],0,&tf[t]);
        tree[t]=level[j]; arithmetic|=tf[t]; ++t;
      }
    }
    part[c]=level[0]; pf[c]=tf[t-1];
  }
  uint32_t acc=0;
  for(int i=0;i<16;i++){ acc=op(acc,part[i],0,&rf[i]); running[i]=acc; arithmetic|=rf[i]; }
  mean=op(acc,0x3b800000u,1,&mf); eps=op(mean,0x358637bdu,0,&ef); arithmetic|=mf|ef;
  int e=(int)((eps>>23)&255u)-127,odd=e&1,half_e=(e-odd)/2;
  normal=((uint32_t)(odd?128:127)<<23)|(eps&0x007fffffu);
  scale=((uint32_t)(127-half_e)&255u)<<23; index=((uint32_t)odd<<4)|((eps>>19)&15u);
  uint32_t m=(uint32_t)(coeff[index]>>32),b=(uint32_t)coeff[index];
  rv[0]=op(m,normal,1,&rvf[0]);
  rv[1]=op(rv[0],b,0,&rvf[1]);
  rv[2]=op(rv[1],rv[1],1,&rvf[2]);
  rv[3]=op(normal,rv[2],1,&rvf[3]);
  rv[4]=op(0x3f000000u,rv[3],1,&rvf[4]);
  rv[5]=op(0x3fc00000u,rv[4]^0x80000000u,0,&rvf[5]);
  rv[6]=op(rv[1],rv[5],1,&rvf[6]);
  rv[7]=op(rv[6],scale,1,&rvf[7]);
  inverse=rv[7];
  for(int i=0;i<8;i++)arithmetic|=rvf[i];
  for(int i=0;i<256;i++) {
    gamma[i]=op(0x3f800000u,in[256+i],0,&gf[i]);
    scaled[i]=op(in[i],inverse,1,&xf[i]);
    full[i]=op(scaled[i],gamma[i],1,&ff[i]);
    bf[i]=convert(full[i],&bff[i]);
    arithmetic|=gf[i]|xf[i]|ff[i]; conversion|=bff[i];
  }
  aggregate=arithmetic|conversion;
  EMIT(square,256);EMIT(sf,256);EMIT(tree,240);EMIT(tf,240);EMIT(part,16);EMIT(pf,16);EMIT(running,16);EMIT(rf,16);
  EMIT(&mean,1);EMIT(&mf,1);EMIT(&eps,1);EMIT(&ef,1);EMIT(&normal,1);EMIT(&scale,1);EMIT(&index,1);
  EMIT(rv,8);EMIT(rvf,8);EMIT(&inverse,1);EMIT(&domain,1);
  EMIT(gamma,256);EMIT(gf,256);EMIT(scaled,256);EMIT(xf,256);EMIT(full,256);EMIT(ff,256);EMIT(bf,256);EMIT(bff,256);
  EMIT(&arithmetic,1);EMIT(&conversion,1);EMIT(&aggregate,1);
  return 1;
}
int main(int argc,char **argv) {
  const uint32_t endian=1;
  if(argc!=3 || sizeof(float)!=4 || FLT_RADIX!=2 || FLT_MANT_DIG!=24 || *(const unsigned char*)&endian!=1) {
    fprintf(stderr,"usage: qk_norm256_reference inputs.bin trace.bin; requires little-endian IEEE binary32\n");return 2;
  }
#if defined(__SSE__)
  _mm_setcsr(_mm_getcsr() & ~(0x8040u)); /* disable flush-to-zero and denormals-are-zero */
#endif
  if(fesetround(FE_TONEAREST) || !selftest()){fprintf(stderr,"binary32 rounding/flags platform selftest failed\n");return 2;}
  FILE *in=fopen(argv[1],"rb"),*out=fopen(argv[2],"wb");
  if(!in || !out){perror("reference file");return 2;}
  unsigned long records=0; uint32_t input[512]; size_t n;
  while((n=fread(input,1,sizeof(input),in))!=0) {
    if(n!=sizeof(input) || !admitted(input)){fprintf(stderr,"invalid candidate input at record %lu\n",records);return 3;}
    if(!head(out,input)){perror("reference write");return 4;}
    ++records;
  }
  if(ferror(in) || fclose(in) || fclose(out))return 4;
  fprintf(stderr,"independent C binary32 reference: %lu heads; RNE, no FMA\n",records);
  return records?0:3;
}

/* Long-K adapter for the production GDN O/down projections. Arithmetic,
 * flags, BF16 rounding and admitted operands are the unchanged shared oracle.
 * The historical K1024 executable and source entry remain unchanged. */
#define main qkv_reference_main
#include "../../../scripts/matrix_norm_rope_reference.c"
#undef main

int main(int argc,char **argv) {
  if(argc!=3 || sizeof(float)!=4 || sizeof(uint32_t)!=4) return 2;
  uint32_t endian=1; if(*(unsigned char *)&endian!=1) return 2;
  if(fesetround(FE_TONEAREST) || fegetround()!=FE_TONEAREST) return 2;
#if defined(__SSE__)
  if(_mm_getcsr() & ((1u<<15)|(1u<<6))) return 2;
#endif
  uint32_t f;
  if(fused(0x3f800001u,0x3f800001u,0xbf800002u,&f)!=0x28800000u || f) return 2;
  if(fused(1u,0x3f000000u,0u,&f)!=0u || f!=3u) return 2;
  FILE *in=fopen(argv[1],"rb"),*out=fopen(argv[2],"wb");
  if(!in || !out) return 2;
  uint32_t h[2],a[3584],w[512],acc[512]={0},flags[512]={0},rounded[512];
  if(fread(h,4,2,in)!=2 || (h[0]!=1024 && h[0]!=2048 && h[0]!=3584) || (h[1]!=256 && h[1]!=512)) return 3;
  uint32_t *steps=malloc((size_t)h[0]*h[1]*sizeof(uint32_t));
  if(!steps || fread(a,4,h[0],in)!=h[0]) return 3;
  for(unsigned k=0;k<h[0];k++) if(!admitted(a[k])) return 3;
  for(unsigned k=0;k<h[0];k++) {
    if(fread(w,4,h[1],in)!=h[1]) return 3;
    for(unsigned j=0;j<h[1];j++) {
      if(!admitted(w[j])) return 3;
      acc[j]=fused(a[k],w[j],acc[j],&f);flags[j]|=f;steps[k*h[1]+j]=acc[j];
    }
  }
  if(fgetc(in)!=EOF) return 3;
  for(unsigned j=0;j<h[1];j++) {
    if((acc[j]&0x7f800000u)==0x7f800000u) return 3;
    rounded[j]=convert(acc[j]);
    if((rounded[j]&0x7f800000u)==0x7f800000u) return 3;
  }
  if(fwrite(acc,4,h[1],out)!=h[1] || fwrite(rounded,4,h[1],out)!=h[1] ||
     fwrite(flags,4,h[1],out)!=h[1] || fwrite(steps,4,(size_t)h[0]*h[1],out)!=(size_t)h[0]*h[1]) return 3;
  free(steps);
  if(ferror(in) || fclose(in) || fclose(out)) return 3;
  return 0;
}

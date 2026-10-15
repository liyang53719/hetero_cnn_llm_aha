// Independent SOFTWARE arithmetic candidate. No Chisel/RTL/resource mapping.
// Reuse the already reviewed raw-input RMS implementation without alteration.
#include "../qwen2_aten_q_projection_candidate/kernel.cpp"
static float (*volatile exact_fma)(float,float,float)=::fmaf;
extern "C" int candidate_project_raw(const float* x,const uint16_t* w,int width,
    int rows,float* raw,uint64_t* fmas,uint64_t* adds,unsigned* peak){
  if(!environment()||!x||!w||!raw||!fmas||!adds||!peak||rows<1||rows>128||(width!=256&&width!=1536))return -1;
  for(int i=0;i<rows*1536;i++)if(!std::isfinite(x[i])||(bits(x[i])&0xffff))return -2;
  for(int i=0;i<1536*width;i++)if((w[i]&0x7f80)==0x7f80)return -2;
  *fmas=*adds=0;*peak=0;
  // At most 64 outputs x 64 FP32 partials. This is a 16KiB software
  // workspace, NOT evidence of current hardware port/route feasibility.
  float partial[64][8][8];
  for(int m=0;m<rows;m++)for(int base=0;base<width;base+=64){
    std::memset(partial,0,sizeof(partial));*peak=4096;
    for(int t=0;t<24;t++)for(int r=0;r<8;r++)for(int l=0;l<8;l++){
      int k=64*t+8*r+l;float a=x[m*1536+k];
      for(int c=0;c<64;c++){
        partial[c][r][l]=exact_fma(a,from(uint32_t(w[k*width+base+c])<<16),partial[c][r][l]);++*fmas;
      }
    }
    for(int c=0;c<64;c++){
      for(int offset=4;offset;offset/=2)for(int r=0;r<offset;r++)for(int l=0;l<8;l++){
        partial[c][r][l]=partial[c][r][l]+partial[c][r+offset][l];++*adds;
      }
      for(int offset=4;offset;offset/=2)for(int l=0;l<offset;l++){
        partial[c][0][l]=partial[c][0][l]+partial[c][0][l+offset];++*adds;
      }
      float dot=partial[c][0][0]+0.0f;++*adds;
      if(!std::isfinite(dot))return -2;raw[m*width+base+c]=dot;
    }
  }
  return 0;
}

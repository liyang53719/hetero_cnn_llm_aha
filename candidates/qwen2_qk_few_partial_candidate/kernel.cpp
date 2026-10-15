// SOFTWARE arithmetic screen for fixed P2/P4 graphs. No new hardware claim.
#include "../qwen2_qk_aten_reduction_candidate/kernel.cpp"
extern "C" int few_project_raw(const float* x,const uint16_t* w,int width,int rows,
    int P,float* out,uint64_t* fmas,uint64_t* adds,unsigned* peak){
  if(!environment()||!x||!w||!out||!fmas||!adds||!peak||rows<1||rows>128||(width!=256&&width!=1536)||(P!=2&&P!=4))return -1;
  for(int i=0;i<rows*1536;i++)if(!std::isfinite(x[i])||(bits(x[i])&0xffff))return -2;
  for(int i=0;i<1536*width;i++)if((w[i]&0x7f80)==0x7f80)return -2;
  *fmas=*adds=0;*peak=128;const int columns=128/P;
  float partial[128];
  for(int m=0;m<rows;m++)for(int base=0;base<width;base+=columns){
    std::memset(partial,0,sizeof(partial));
    for(int t=0;t<1536/P;t++)for(int p=0;p<P;p++){
      int k=P*t+p;float a=x[m*1536+k];
      for(int c=0;c<columns;c++){
        partial[c*P+p]=exact_fma(from(uint32_t(w[k*width+base+c])<<16),a,partial[c*P+p]);++*fmas;
      }
    }
    for(int c=0;c<columns;c++){
      for(int offset=P/2;offset;offset/=2)for(int p=0;p<offset;p++){
        partial[c*P+p]=partial[c*P+p]+partial[c*P+p+offset];++*adds;
      }
      float dot=partial[c*P]+0.0f;++*adds;
      if(!std::isfinite(dot))return -2;out[m*width+base+c]=dot;
    }
  }
  return 0;
}

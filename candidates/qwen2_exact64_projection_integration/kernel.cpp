// DIAGNOSTIC SOFTWARE OWNER. Same frozen exact64 arithmetic, streamed inputs.
// Existing complete kernel remains included as an after-terminal test control.
#include "../qwen2_qk_aten_reduction_candidate/kernel.cpp"
extern "C" int exact64_clear(float* partial){
  if(!environment()||!partial)return -1;
  std::memset(partial,0,4096*sizeof(float));return 0;
}
extern "C" int exact64_push(float* partial,unsigned k,uint32_t activation,
    const uint16_t* weight,uint64_t* fmas){
  if(!environment()||!partial||!weight||!fmas||k>=1536)return -1;
  float a=from(activation);
  if(!std::isfinite(a)||(activation&0xffff))return -2;
  for(unsigned c=0;c<64;c++)if((weight[c]&0x7f80)==0x7f80)return -2;
  const unsigned r=(k%64)/8,l=k%8;
  for(unsigned c=0;c<64;c++){
    float& value=partial[c*64+r*8+l];
    value=exact_fma(a,from(uint32_t(weight[c])<<16),value);++*fmas;
  }
  return 0;
}
extern "C" int exact64_finish(float* partial,uint32_t* output,uint64_t* adds){
  if(!environment()||!partial||!output||!adds)return -1;
  for(unsigned c=0;c<64;c++){
    float (*s)[8]=reinterpret_cast<float (*)[8]>(partial+c*64);
    for(int offset=4;offset;offset/=2)for(int r=0;r<offset;r++)for(int l=0;l<8;l++){
      s[r][l]=s[r][l]+s[r+offset][l];++*adds;
    }
    for(int offset=4;offset;offset/=2)for(int l=0;l<offset;l++){
      s[0][l]=s[0][l]+s[0][l+offset];++*adds;
    }
    float dot=s[0][0]+0.0f;++*adds;
    if(!std::isfinite(dot))return -2;output[c]=bits(dot);
  }
  return 0;
}

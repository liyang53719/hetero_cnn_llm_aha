// SPDX-License-Identifier: Apache-2.0
// Host-only versioned tensor materialization. No second hardware SFU is added.
// The unmodified original entrypoints/helpers are compiled in this same TU.
#include "../ffn_tiles/silu_recipe.cpp"

namespace {
uint64_t bf16Calls=0,bf16Failures=0;
static float tensor_bf16(float x) {
  const uint32_t u=bits(x);
  if((u&0x7f800000u)==0x7f800000u)return x;
  return fp((u+0x7fffu+((u>>16)&1u))&0xffff0000u);
}
}

extern "C" int sf_reset_bf16_v1() {
  const int rc=sf_reset();
  if(!rc)bf16Calls=bf16Failures=0;
  return rc;
}
extern "C" uint64_t sf_bf16_v1_calls(){return bf16Calls;}
extern "C" uint64_t sf_bf16_v1_failures(){return bf16Failures;}

// Same six phases and scalar helpers as the original sf_vector. Phases 0..3
// stay FP32; only sigmoid*gate and then previous*up materialize as BF16 values
// held in FP32 words. Phase5 consumes the rounded phase4, not its FP32 source.
// Phase flags still describe host FP32 primitives. Integer BF16 narrowing does
// not manufacture host/HardFloat exception flags; nonfinite rounded results
// are rejected explicitly. Exact BF16 subnormals and signed zero are retained.
extern "C" int sf_vector_bf16_v1(const uint32_t* gate,const uint32_t* up,uint32_t* out,
                                uint32_t* phase_values,uint32_t* phase_flags,uint32_t* lane_errors) {
  ++bf16Calls;
  float value[16]={},probability[16]={};
  std::memset(phase_values,0,96*sizeof(uint32_t));
  std::memset(phase_flags,0,96*sizeof(uint32_t));
  std::memset(lane_errors,0,16*sizeof(uint32_t));
  bool invalid=false;
  for(unsigned i=0;i<16;i++) {
    if(!std::isfinite(fp(gate[i]))||!std::isfinite(fp(up[i]))) {lane_errors[i]=64;invalid=true;}
    out[i]=0;
  }
  if(invalid){++bf16Failures;return -1;}
  for(unsigned phase=0;phase<6;phase++) {
    bool bad=false;
    for(unsigned i=0;i<16;i++) {
      std::feclearexcept(FE_ALL_EXCEPT);
      float r;
      if(phase==0) {r=expneg(fp(gate[i]));probability[i]=r;}
      else if(phase==1) r=primitive(phase,1.0f,value[i]);
      else if(phase==2) r=primitive(phase,1.0f,value[i]);
      else if(phase==3) r=primitive(phase,value[i],(gate[i]>>31)?probability[i]:1.0f);
      else if(phase==4) r=primitive(phase,value[i],fp(gate[i]));
      else r=primitive(phase,value[i],fp(up[i]));
      const unsigned f=flags();
      if(phase>=4)r=tensor_bf16(r);
      value[i]=r;out[i]=bits(r);phase_values[phase*16+i]=bits(r);
      phase_flags[phase*16+i]=f;
      if((phase!=0&&(f&30))||!std::isfinite(r)) {lane_errors[i]|=1u<<phase;bad=true;}
    }
    if(bad){++bf16Failures;return int(phase+1);}
  }
  return 0;
}

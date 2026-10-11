// SPDX-License-Identifier: Apache-2.0
// Host-only, strict-FP reference bound to the frozen v0 source recipe.
// This does not execute HardFloat, Chisel, RTL, or the physical SiLU unit.
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#if defined(__SSE__)
#include <xmmintrin.h>
#endif
#pragma STDC FENV_ACCESS ON

// Verbatim helpers from chisel/continuous_prefill/tests/qwen2_block.cpp.
static uint32_t bits(float x){uint32_t r;std::memcpy(&r,&x,4);return r;}
static float fp(uint32_t x){float r;std::memcpy(&r,&x,4);return r;}
static float add(float a,float b){return a+b;}
static float mul(float a,float b){return a*b;}
static float expneg(float x){
  x=std::abs(x);if(x>=80)return 0;float z=mul(x,float(1.0/std::log(2.0)));unsigned k=unsigned(z);float f=add(z,-float(k));
  float c[8];double fact=1;for(int i=0;i<8;i++){if(i)fact*=i;c[i]=float(std::pow(-std::log(2.0),i)/fact);}float y=c[7];
  for(int i=6;i>=0;i--)y=add(mul(y,f),c[i]);return mul(y,fp((127-k)<<23));
}

static unsigned flags() {
  const int f=std::fetestexcept(FE_ALL_EXCEPT);
  return ((f&FE_INVALID)?16u:0u)|((f&FE_DIVBYZERO)?8u:0u)|
         ((f&FE_OVERFLOW)?4u:0u)|((f&FE_UNDERFLOW)?2u:0u)|((f&FE_INEXACT)?1u:0u);
}

// Volatile operand/result boundaries preserve the separate FP32 phases and
// make their host exception observations explicit at -O2. No fused operations.
static float primitive(unsigned phase,float a,float b) {
  volatile float x=a,y=b;
  volatile float result=phase==1?x+y:phase==2?x/y:x*y;
  return result;
}

extern "C" int sf_reset() {
  if(sizeof(float)!=4 || !std::numeric_limits<float>::is_iec559) return 1;
  if(std::fesetround(FE_TONEAREST)!=0) return 2;
#if defined(__SSE__)
  // Fail visibly rather than silently accept FTZ/DAZ host execution.
  if(_mm_getcsr()&((1u<<15)|(1u<<6))) return 3;
#endif
  return 0;
}

// phase_values/phase_flags are phase-major [6][16]. lane_errors contains one
// bit per failed phase, or bit6 for an unsupported nonfinite input. Host flags
// use HardFloat bit positions for reporting only: they are NOT HardFloat flags.
// Existing ExpNegative ignores internal arithmetic exception flags; Add/Div/
// legacy Mul reject invalid/divzero/overflow/underflow and nonfinite results.
// A vector fails as a whole after the first failing phase, like SiluVectorUnit.
extern "C" int sf_vector(const uint32_t* gate,const uint32_t* up,uint32_t* out,
                         uint32_t* phase_values,uint32_t* phase_flags,uint32_t* lane_errors) {
  float value[16]={},probability[16]={};
  std::memset(phase_values,0,96*sizeof(uint32_t));
  std::memset(phase_flags,0,96*sizeof(uint32_t));
  std::memset(lane_errors,0,16*sizeof(uint32_t));
  bool invalid=false;
  for(unsigned i=0;i<16;i++) {
    if(!std::isfinite(fp(gate[i]))||!std::isfinite(fp(up[i]))) {lane_errors[i]=64;invalid=true;}
    out[i]=0;
  }
  if(invalid) return -1;
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
      value[i]=r;out[i]=bits(r);phase_values[phase*16+i]=bits(r);
      const unsigned f=flags();phase_flags[phase*16+i]=f;
      if((phase!=0&&(f&30))||!std::isfinite(r)) {lane_errors[i]|=1u<<phase;bad=true;}
    }
    if(bad) return int(phase+1);
  }
  return 0;
}

// Independent flat indexing and exact original source expression; called only
// after all output bank read responses have been accepted, never as model input.
extern "C" int sf_reference(const uint32_t* gate,const uint32_t* up,uint32_t* out,unsigned count) {
  for(unsigned i=0;i<count;i++) {
    float g=fp(gate[i]),u=fp(up[i]);
    if(!std::isfinite(g)||!std::isfinite(u)) return 1;
    float e=expneg(g),sig=1.0f/add(1.0f,e);sig=mul(sig,std::signbit(g)?e:1.0f);
    const float result=mul(mul(sig,g),u);
    if(!std::isfinite(result)) return 2;
    out[i]=bits(result);
  }
  return 0;
}

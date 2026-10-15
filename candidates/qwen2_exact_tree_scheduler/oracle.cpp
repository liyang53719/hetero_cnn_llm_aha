// Tiny independent host FP32 test oracle; never hardware evidence.
// Original loops: qwen2_aten_q_projection_candidate/kernel.cpp:49-63.
#include <cmath>
#include <cfenv>
#include <cstdint>
#include <cstring>
#include <xmmintrin.h>
static float from(uint32_t u) { float x; std::memcpy(&x,&u,4); return x; }
static uint32_t bits(float x) { uint32_t u; std::memcpy(&u,&x,4); return u; }
static float (*volatile exact_fma)(float,float,float)=::fmaf;
extern "C" int supported_environment() {
  return std::fegetround()==FE_TONEAREST && !(_mm_getcsr() & 0xe040);
}
extern "C" uint32_t oracle_get_mxcsr() { return _mm_getcsr(); }
extern "C" void oracle_set_mxcsr(uint32_t value) { _mm_setcsr(value); }
extern "C" uint32_t oracle_add(uint32_t a, uint32_t b) { return bits(from(a)+from(b)); }
extern "C" uint32_t oracle_fma(uint32_t a,uint32_t b,uint32_t c) {
  return bits(exact_fma(from(a),from(b),from(c)));
}
extern "C" uint32_t oracle_reduce(const uint32_t *p) {
  float s[8][8];
  for(int r=0;r<8;r++) for(int l=0;l<8;l++) s[r][l]=from(p[8*r+l]);
  for(int offset=4;offset;offset/=2)
    for(int r=0;r<offset;r++) for(int l=0;l<8;l++) s[r][l]=s[r][l]+s[r+offset][l];
  for(int offset=4;offset;offset/=2)
    for(int l=0;l<offset;l++) s[0][l]=s[0][l]+s[0][l+offset];
  return bits(s[0][0]+0.0f);
}
extern "C" uint32_t oracle_dot(const uint32_t *a,const uint32_t *b) {
  float s[8][8]={}; uint32_t p[64];
  for(int t=0;t<24;t++) for(int r=0;r<8;r++) for(int l=0;l<8;l++) {
    int k=64*t+8*r+l;
    s[r][l]=exact_fma(from(a[k]),from(b[k]),s[r][l]);
  }
  for(int r=0;r<8;r++) for(int l=0;l<8;l++) p[8*r+l]=bits(s[r][l]);
  return oracle_reduce(p);
}

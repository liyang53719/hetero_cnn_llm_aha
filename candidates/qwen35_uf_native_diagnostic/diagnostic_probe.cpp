// Separate software probe. This is NOT instrumentation of vector16.cpp.
#include <cfenv>
#include <cstdint>
#include <cstring>
#include <xmmintrin.h>
#pragma STDC FENV_ACCESS ON

static unsigned x87_control() {
  unsigned short value;
  asm volatile("fnstcw %0" : "=m"(value));
  return value;
}
extern "C" void uf_diagnostic_snapshot(uint32_t* out) {
  out[0] = static_cast<uint32_t>(std::fegetround());
  out[1] = static_cast<uint32_t>(std::fetestexcept(FE_ALL_EXCEPT));
  out[2] = _mm_getcsr();
  out[3] = x87_control();
}
extern "C" int uf_diagnostic_environment() {
  const unsigned mxcsr = _mm_getcsr();
  const unsigned cw = x87_control();
  if (std::fegetround() != FE_TONEAREST || (mxcsr & (3u << 13)) || (cw & (3u << 10))) return -1;
  if (mxcsr & (1u << 15)) return -2;
  if (mxcsr & (1u << 6)) return -3;
  // Additional diagnostic admission, NOT a claim about the legacy API.
  if ((mxcsr & (63u << 7)) != (63u << 7) || (cw & 63u) != 63u) return -6;
  return 0;
}
extern "C" int uf_diagnostic_raw(unsigned op, uint32_t a, uint32_t b, uint32_t* out) {
  if (op > 1) return -5;
  const int environment = uf_diagnostic_environment();
  if (environment) return environment;
  std::fexcept_t saved;
  if (std::fegetexceptflag(&saved, FE_ALL_EXCEPT) != 0) return -7;
  float x, y;
  std::memcpy(&x, &a, 4);
  std::memcpy(&y, &b, 4);
  if (std::feclearexcept(FE_ALL_EXCEPT) != 0) return -8;
  volatile float z = op ? x * y : x + y;
  float r = z;
  const int f = std::fetestexcept(FE_ALL_EXCEPT);
  unsigned flags = (f & FE_INVALID) ? 16 : 0;
  flags |= (f & FE_DIVBYZERO) ? 8 : 0;
  flags |= (f & FE_OVERFLOW) ? 4 : 0;
  flags |= (f & FE_UNDERFLOW) ? 2 : 0;
  flags |= (f & FE_INEXACT) ? 1 : 0;
  std::memcpy(out, &r, 4);
  if (std::fesetexceptflag(&saved, FE_ALL_EXCEPT) != 0) return -9;
  return flags;
}

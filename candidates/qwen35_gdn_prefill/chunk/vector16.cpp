// Software adapter for ONE existing 16-lane HeteroFP32Alu Add/Mul resource.
// No matmul, reduction, SFU, FMA, or native tensor operation is hidden here.
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#if defined(__SSE__)
#include <xmmintrin.h>
#endif
#pragma STDC FENV_ACCESS ON

// Read only. Never clear FTZ/DAZ or change rounding to make a request succeed.
extern "C" int gdn_vector16_environment() {
  if (std::fegetround() != FE_TONEAREST) return -1;
#if defined(__SSE__)
  const unsigned controls = _mm_getcsr();
  if (controls & (3u << 13)) return -1; // SSE rounding also must be nearest.
  if (controls & (1u << 15)) return -2; // flush to zero
  if (controls & (1u << 6)) return -3;  // denormals are zero
  return 0;
#else
  return -4; // No verified FTZ/DAZ inspection route on this host architecture.
#endif
}

static int compute(unsigned op, const uint32_t* a, const uint32_t* b,
                   uint32_t* out, unsigned lanes, uint32_t* lane_flags) {
  if (op > 1 || lanes == 0 || lanes > 16)
    return -1;
  const int environment = gdn_vector16_environment();
  if (environment) return environment;
  // Keep caller sticky exception status as well as all control modes unchanged.
  std::fexcept_t original_flags;
  std::fegetexceptflag(&original_flags, FE_ALL_EXCEPT);
  unsigned flags = 0;
  for (unsigned i = 0; i < lanes; ++i) {
    float x, y;
    std::memcpy(&x, a + i, 4);
    std::memcpy(&y, b + i, 4);
    std::feclearexcept(FE_ALL_EXCEPT);
    volatile float z = op ? x * y : x + y;
    float r = z;
    const int f = std::fetestexcept(FE_ALL_EXCEPT);
    unsigned lane = (f & FE_INVALID) ? 16 : 0;
    lane |= (f & FE_DIVBYZERO) ? 8 : 0;
    lane |= (f & FE_OVERFLOW) ? 4 : 0;
    // Match HardFloat tininess_afterRounding, even on hosts detecting before.
    lane |= ((f & FE_INEXACT) && std::fabs(r) < 0x1p-126f) ? 2 : 0;
    lane |= (f & FE_INEXACT) ? 1 : 0;
    flags |= lane;
    if (lane_flags) lane_flags[i] = lane;
    std::memcpy(out + i, &r, 4);
  }
  std::fesetexceptflag(&original_flags, FE_ALL_EXCEPT);
  return flags;
}

extern "C" int gdn_vector16(unsigned op, const uint32_t* a,
                            const uint32_t* b, uint32_t* out, unsigned lanes) {
  return compute(op, a, b, out, lanes, nullptr);
}

extern "C" int gdn_vector16_trace(unsigned op, const uint32_t* a,
    const uint32_t* b, uint32_t* out, unsigned lanes, uint32_t* lane_flags) {
  return compute(op, a, b, out, lanes, lane_flags);
}

// Host-call batching only: TWO logical issues on the same 16 lanes. Complete
// Mul for every active lane before Add, using the very same rounded primitive.
// b is reused for the rounded product; Python retains the original operands.
// Return the last attempted issue (1=Mul, 2=Add), including environment faults.
extern "C" unsigned gdn_vector16_mul_add_policy_trace(const uint32_t* a, uint32_t* b,
    const uint32_t* total, uint32_t* out, unsigned lanes,
    uint32_t* lane_flags, int* issue_flags, unsigned fatal_mask) {
  if (fatal_mask != 30 && fatal_mask != 28) {
    issue_flags[0] = -5; issue_flags[1] = 0; return 1;
  }
  issue_flags[0] = compute(1, a, b, b, lanes, lane_flags);
  issue_flags[1] = 0;
  if (issue_flags[0] < 0 || (issue_flags[0] & fatal_mask)) return 1;
  for (unsigned i = 0; i < lanes; ++i)
    if ((b[i] & 0x7f800000u) == 0x7f800000u) return 1;
  issue_flags[1] = compute(0, total, b, out, lanes, lane_flags);
  return 2;
}

// Preserve the original ABI and legacy default for previously bound clients.
extern "C" unsigned gdn_vector16_mul_add_trace(const uint32_t* a, uint32_t* b,
    const uint32_t* total, uint32_t* out, unsigned lanes,
    uint32_t* lane_flags, int* issue_flags) {
  return gdn_vector16_mul_add_policy_trace(a, b, total, out, lanes,
                                         lane_flags, issue_flags, 30);
}

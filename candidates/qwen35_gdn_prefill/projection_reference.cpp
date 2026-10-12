// Independent post-execution logical-row reference. Not an execution resource.
// No Matrix packet, bank coordinate, owner state or saved output is accessed.
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>

static float fp(uint32_t u) { float f; std::memcpy(&f, &u, 4); return f; }
static uint32_t bits(float f) { uint32_t u; std::memcpy(&u, &f, 4); return u; }

extern "C" int gdn_projection_reference(unsigned m, unsigned k, unsigned n,
    const uint16_t* a, const uint16_t* outputMajorWeight, uint16_t* output) {
  if (!m || m > 128 || !k || k > 3584 || !n || n > 65535 ||
      !a || !outputMajorWeight || !output || std::fesetround(FE_TONEAREST)) return -1;
  volatile float tiny = fp(1), one = 1.0f;
  if (bits(tiny * one) != 1) return -2; // reject host FTZ/DAZ
  for (unsigned row = 0; row < m; ++row) {
    for (unsigned col = 0; col < n; ++col) {
      float sum = 0.0f;
      for (unsigned depth = 0; depth < k; ++depth) {
        const float x = fp(uint32_t(a[row*k+depth]) << 16);
        const float w = fp(uint32_t(outputMajorWeight[col*k+depth]) << 16);
        if (!std::isfinite(x) || !std::isfinite(w)) return -3;
        sum = std::fma(x, w, sum);
      }
      if (!std::isfinite(sum)) return -4;
      const uint32_t u = bits(sum);
      const uint16_t b = uint16_t((u + 0x7fff + ((u >> 16) & 1)) >> 16);
      if ((b & 0x7f80) == 0x7f80) return -5;
      output[row*n+col] = b;
    }
  }
  return 0;
}

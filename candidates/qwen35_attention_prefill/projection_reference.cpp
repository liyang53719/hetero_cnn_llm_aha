// Software diagnostic only. Logical row/column coordinates and original
// output-major weights. No Matrix bank, owner, driver, or hardware execution.
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <xmmintrin.h>
#include <chrono>

static float fp(uint32_t u) { float f; std::memcpy(&f, &u, 4); return f; }
static uint32_t bits(float f) { uint32_t u; std::memcpy(&u, &f, 4); return u; }
static std::vector<float> load(const std::string& path, size_t count) {
  std::ifstream f(path, std::ios::binary | std::ios::ate);
  if (!f || f.tellg() != std::streamoff(count * 2)) throw std::runtime_error("input size");
  f.seekg(0);
  std::vector<uint16_t> raw(count);
  if (!f.read(reinterpret_cast<char*>(raw.data()), count * 2)) throw std::runtime_error("input read");
  std::vector<float> out(count);
  for (size_t i = 0; i < count; ++i) {
    out[i] = fp(uint32_t(raw[i]) << 16);
    if (!std::isfinite(out[i])) throw std::runtime_error("nonfinite input");
  }
  return out;
}
int main(int argc, char** argv) try {
  if (argc != 2) throw std::runtime_error("usage: independent_pair_reference jobs.tsv");
  uint16_t endian = 1;
  if (*reinterpret_cast<uint8_t*>(&endian) != 1) throw std::runtime_error("little endian required");
  if (std::fesetround(FE_TONEAREST)) throw std::runtime_error("rounding");
  const unsigned mxcsr = _mm_getcsr();
  if (mxcsr & ((1u << 15) | (1u << 6))) throw std::runtime_error("FTZ/DAZ refused");
  volatile float tiny = fp(1), one = 1.0f;
  if (bits(tiny * one) != 1) throw std::runtime_error("subnormal behavior refused");
  std::cout << "{\"mxcsr\":" << mxcsr << ",\"FTZ\":false,\"DAZ\":false,\"rounding\":\"FE_TONEAREST\"}" << std::endl;
  std::ifstream jobs(argv[1]);
  std::string label, ap, wp, op;
  unsigned m, n;
  while (jobs >> label >> m >> n >> ap >> wp >> op) {
    if ((m != 16 && m != 128) || (n != 4096 && n != 512)) throw std::runtime_error("shape refused");
    auto start = std::chrono::steady_clock::now();
    const auto a = load(ap, m * 1024), w = load(wp, n * 1024);
    std::vector<uint16_t> out(m * n);
    for (unsigned row = 0; row < m; ++row) {
      for (unsigned col = 0; col < n; ++col) {
        float low = 0.0f, high = 0.0f;
        for (unsigned ordinal = 0; ordinal < 512; ++ordinal) {
          const unsigned depth = ordinal ^ 1u;
          low = std::fma(a[row * 1024 + depth], w[col * 1024 + depth], low);
          high = std::fma(a[row * 1024 + 512 + depth], w[col * 1024 + 512 + depth], high);
        }
        const float sum = low + high;
        if (!std::isfinite(sum)) throw std::runtime_error("nonfinite sum");
        const uint32_t u = bits(sum);
        const uint16_t b = uint16_t((u + 0x7fffu + ((u >> 16) & 1u)) >> 16);
        if ((b & 0x7f80) == 0x7f80) throw std::runtime_error("nonfinite output");
        out[row * n + col] = b;
      }
    }
    std::ofstream f(op, std::ios::binary);
    if (!f.write(reinterpret_cast<const char*>(out.data()), out.size() * 2)) throw std::runtime_error("output write");
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    std::cout << "{\"label\":\"" << label << "\",\"seconds\":" << seconds << "}" << std::endl;
  }
  if (!jobs.eof()) throw std::runtime_error("job parse");
  if (_mm_getcsr() & ((1u << 15) | (1u << 6))) throw std::runtime_error("FTZ/DAZ changed");
  return 0;
} catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }

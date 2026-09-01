#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
#include <omp.h>

static uint32_t bits(float value) { uint32_t word; __builtin_memcpy(&word, &value, 4); return word; }
static float from_bits(uint32_t word) { float value; __builtin_memcpy(&value, &word, 4); return value; }
static float bf(uint16_t value) { return from_bits(uint32_t(value) << 16); }
static uint16_t tobf(float value) {
  uint32_t word = bits(value);
  if (((word >> 23) & 255u) == 255u && (word & 0x7fffffu)) {
    uint16_t result = uint16_t(word >> 16) | 0x40u;
    if ((result & 0x7fu) == 0) result |= 1u;
    return result;
  }
  word += 0x7fffu + ((word >> 16) & 1u);
  return uint16_t(word >> 16);
}
static float add32(float a, float b) { volatile float result = a + b; return result; }
static float mul32(float a, float b) { volatile float result = a * b; return result; }

template <class T> static std::vector<T> load(const std::string &path, size_t count) {
  std::vector<T> values(count); std::ifstream stream(path, std::ios::binary);
  stream.read(reinterpret_cast<char *>(values.data()), count * sizeof(T));
  if (!stream || size_t(stream.gcount()) != count * sizeof(T)) {
    std::fprintf(stderr, "load fail %s\n", path.c_str()); std::exit(2);
  }
  return values;
}
template <class T> static void save(const std::string &path, const std::vector<T> &values) {
  std::ofstream stream(path, std::ios::binary);
  stream.write(reinterpret_cast<const char *>(values.data()), values.size() * sizeof(T));
  if (!stream) std::exit(3);
}
static uint64_t fnv32(const std::vector<float> &values) {
  uint64_t hash = 1469598103934665603ull;
  for (float value : values) { uint32_t word = bits(value); for (int byte = 0; byte < 4; ++byte) hash = (hash ^ ((word >> (8 * byte)) & 255u)) * 1099511628211ull; }
  return hash;
}
static uint64_t fnv16(const std::vector<uint16_t> &values) {
  uint64_t hash = 1469598103934665603ull;
  for (uint16_t value : values) { hash = (hash ^ (value & 255u)) * 1099511628211ull; hash = (hash ^ (value >> 8)) * 1099511628211ull; }
  return hash;
}

static void validate_commands(const std::string &input) {
  const auto commands = load<uint8_t>(input + "/first21_commands.bin", 21 * 16);
  const uint8_t opcodes[21] = {0x32,0x20,0x30,0x34,0x20,0x30,0x34,0x20,0x30,0x41,0x23,0x33,0x24,0x20,0x30,0x32,0x20,0x20,0x35,0x20,0x30};
  const uint8_t engines[21] = {3,2,3,3,2,3,3,2,3,4,2,3,2,2,3,3,2,2,3,2,3};
  for (int index = 0; index < 21; ++index)
    if (commands[index * 16] != opcodes[index] || (commands[index * 16 + 1] & 7u) != engines[index]) {
      std::fprintf(stderr, "command mismatch %d\n", index); std::exit(4);
    }
}

static std::vector<float> gemm(const std::vector<uint16_t> &input, int rows, int inner, int columns, const std::string &weight_path, const char *name) {
  const auto weights = load<uint16_t>(weight_path, size_t(columns) * inner);
  std::vector<float> output(size_t(rows) * columns);
  const double start = omp_get_wtime();
#pragma omp parallel for collapse(2) schedule(static)
  for (int row = 0; row < rows; ++row) for (int column = 0; column < columns; ++column) {
    float accumulator = 0.0f;
    for (int k = 0; k < inner; ++k)
      accumulator = std::fma(bf(input[size_t(row) * inner + k]), bf(weights[size_t(column) * inner + k]), accumulator);
    output[size_t(row) * columns + column] = accumulator;
  }
  std::printf("%s_seconds=%.6f\n", name, omp_get_wtime() - start);
  return output;
}

static float reduce16(float *values) {
  for (int width = 16; width > 1; width >>= 1)
    for (int index = 0; index < width / 2; ++index) values[index] = add32(values[index * 2], values[index * 2 + 1]);
  return values[0];
}
static float rsqrt_nr2(float value) {
  const uint32_t word = bits(value); const int exponent = int((word >> 23) & 255u); const uint32_t fraction = word & 0x7fffffu;
  const int unbiased = exponent - 127; const int odd = unbiased & 1; const int even_exponent = odd ? unbiased - 1 : unbiased;
  const float normalized = from_bits((uint32_t(odd ? 128 : 127) << 23) | fraction);
  const int index = (odd << 4) | int(fraction >> 19); const double low = odd ? 2.0 : 1.0; const double step = odd ? 1.0 / 8.0 : 1.0 / 16.0;
  const double x0 = low + (index & 15) * step, x1 = x0 + step;
  const float slope = float(((1.0 / std::sqrt(x1)) - (1.0 / std::sqrt(x0))) / step);
  const float intercept = float(1.0 / std::sqrt(x0) - double(slope) * x0);
  float estimate = add32(mul32(slope, normalized), intercept);
  float term = add32(1.5f, -mul32(0.5f, mul32(normalized, mul32(estimate, estimate))));
  float scaled = mul32(mul32(estimate, term), from_bits(uint32_t(127 - even_exponent / 2) << 23));
  term = add32(1.5f, -mul32(0.5f, mul32(value, mul32(scaled, scaled))));
  return mul32(scaled, term);
}
static std::vector<float> rmsnorm(const std::vector<float> &input, const std::vector<uint16_t> &weight) {
  constexpr int hidden = 1536; const int rows = int(input.size() / hidden); std::vector<float> output(input.size());
#pragma omp parallel for schedule(static)
  for (int row = 0; row < rows; ++row) {
    float total = 0.0f;
    for (int chunk = 0; chunk < 96; ++chunk) { float partial[16]; for (int lane = 0; lane < 16; ++lane) { const float value = input[size_t(row) * hidden + chunk * 16 + lane]; partial[lane] = mul32(value, value); } total = add32(total, reduce16(partial)); }
    const float mean = add32(mul32(total, 1.0f / 1536.0f), 1.0e-6f); const float inverse = rsqrt_nr2(mean);
    for (int column = 0; column < hidden; ++column) output[size_t(row) * hidden + column] = mul32(mul32(input[size_t(row) * hidden + column], inverse), bf(weight[column]));
  }
  return output;
}
static float fp16_to_fp32(uint16_t value) {
  const uint32_t sign = uint32_t(value >> 15) << 31; const uint32_t exponent = (value >> 10) & 31u; uint32_t fraction = value & 1023u;
  if (exponent == 0) { if (!fraction) return from_bits(sign); int msb = 9; while (((fraction >> msb) & 1u) == 0u) --msb; const uint32_t fp_fraction = (fraction << (23 - msb)) & 0x7fffffu; return from_bits(sign | (uint32_t(103 + msb) << 23) | fp_fraction); }
  if (exponent == 31) return from_bits(sign | 0x7f800000u | (fraction << 13));
  return from_bits(sign | ((exponent + 112u) << 23) | (fraction << 13));
}
static int bf16_to_q12(uint16_t value) {
  const int exponent = (value >> 7) & 255, significand = 128 + (value & 127); int magnitude;
  if (exponent == 255) magnitude = 32768; else if (exponent == 0) magnitude = 0; else { const int shift = exponent - 122; if (shift >= 0) magnitude = significand << shift; else { const int right = -shift; magnitude = right >= 16 ? 0 : (significand + (1 << (right - 1))) >> right; } magnitude = std::min(32768, magnitude); }
  return (value & 0x8000u) ? -magnitude : magnitude;
}
static uint16_t fused_silu(uint16_t gate_bits, uint16_t up_bits, const std::vector<uint16_t> &rom) {
  const float gate = bf(gate_bits), up = bf(up_bits); const int exponent = (gate_bits >> 7) & 255, fraction_bits = gate_bits & 127; float y0, y1, fraction;
  const int q12 = bf16_to_q12(gate_bits);
  if (exponent == 255 && fraction_bits) y0 = y1 = gate;
  else if ((gate_bits & 0x7fffu) == 0 || q12 <= -32768) y0 = y1 = 0.0f;
  else if (q12 == 0) y0 = y1 = mul32(gate, 0.5f);
  else if (q12 >= 32768) y0 = y1 = gate;
  else { const uint32_t position = (uint32_t(q12 + 32768) * 127u) >> 4; const int index = std::min(126, int(position >> 12)); y0 = fp16_to_fp32(rom[index]); y1 = fp16_to_fp32(rom[index + 1]); fraction = float(position & 4095u) / 4096.0f; y1 = add32(y0, mul32(add32(y1, -y0), fraction)); }
  return tobf(mul32(y1, up));
}

int main(int argc, char **argv) {
  if (argc != 5) { std::fprintf(stderr, "usage: stage input_dir attention_dir output_dir\n"); return 2; }
  const std::string stage = argv[1], input = argv[2], attention = argv[3], output = argv[4]; validate_commands(input);
  constexpr int tokens = 1024, hidden = 1536, intermediate = 8960;
  if (stage == "oproj") {
    const auto probabilities = load<float>(attention + "/attention_fp32.bin", size_t(tokens) * hidden); std::vector<uint16_t> matrix_input(probabilities.size());
#pragma omp parallel for schedule(static)
    for (size_t index = 0; index < probabilities.size(); ++index) matrix_input[index] = tobf(probabilities[index]);
    const auto projected = gemm(matrix_input, tokens, hidden, hidden, input + "/oproj_weight_bf16.bin", "oproj"); const auto original = load<uint16_t>(input + "/hidden_bf16.bin", projected.size()); std::vector<float> residual(projected.size());
#pragma omp parallel for schedule(static)
    for (size_t index = 0; index < residual.size(); ++index) residual[index] = add32(projected[index], bf(original[index]));
    const auto norm_weight = load<uint16_t>(input + "/post_norm_weight_bf16.bin", hidden); const auto normalized = rmsnorm(residual, norm_weight);
    save(output + "/oproj_fp32.bin", projected); save(output + "/residual1_fp32.bin", residual); save(output + "/postnorm_fp32.bin", normalized);
    std::printf("QWEN2_LAYER0_OPROJ_PASS commands=21 rows=1024 values=%zu oproj_fnv=%016llx residual_fnv=%016llx postnorm_fnv=%016llx\n", projected.size(), (unsigned long long)fnv32(projected), (unsigned long long)fnv32(residual), (unsigned long long)fnv32(normalized));
  } else if (stage == "gate") {
    const auto normalized = load<float>(output + "/postnorm_fp32.bin", size_t(tokens) * hidden); std::vector<uint16_t> matrix_input(normalized.size());
#pragma omp parallel for schedule(static)
    for (size_t index = 0; index < normalized.size(); ++index) matrix_input[index] = tobf(normalized[index]);
    const auto gate = gemm(matrix_input, tokens, hidden, intermediate, input + "/gate_weight_bf16.bin", "gate"); save(output + "/gate_fp32.bin", gate);
    std::printf("QWEN2_LAYER0_GATE_PASS commands=21 rows=1024 values=%zu gate_fnv=%016llx\n", gate.size(), (unsigned long long)fnv32(gate));
  } else if (stage == "up") {
    const auto normalized = load<float>(output + "/postnorm_fp32.bin", size_t(tokens) * hidden); std::vector<uint16_t> matrix_input(normalized.size());
#pragma omp parallel for schedule(static)
    for (size_t index = 0; index < normalized.size(); ++index) matrix_input[index] = tobf(normalized[index]);
    const auto up = gemm(matrix_input, tokens, hidden, intermediate, input + "/up_weight_bf16.bin", "up"); const auto gate = load<float>(output + "/gate_fp32.bin", up.size()); const auto rom = load<uint16_t>(input + "/silu_lut_fp16.bin", 128); std::vector<uint16_t> product(up.size());
#pragma omp parallel for schedule(static)
    for (size_t index = 0; index < up.size(); ++index) product[index] = fused_silu(tobf(gate[index]), tobf(up[index]), rom);
    save(output + "/up_fp32.bin", up); save(output + "/silu_product_bf16.bin", product);
    std::printf("QWEN2_LAYER0_UP_SILU_PASS commands=21 rows=1024 values=%zu up_fnv=%016llx product_fnv=%016llx lanes=8\n", up.size(), (unsigned long long)fnv32(up), (unsigned long long)fnv16(product));
  } else if (stage == "down") {
    const auto product = load<uint16_t>(output + "/silu_product_bf16.bin", size_t(tokens) * intermediate); const auto down = gemm(product, tokens, intermediate, hidden, input + "/down_weight_bf16.bin", "down"); const auto residual1 = load<float>(output + "/residual1_fp32.bin", down.size()); std::vector<float> final(down.size());
#pragma omp parallel for schedule(static)
    for (size_t index = 0; index < final.size(); ++index) final[index] = add32(down[index], residual1[index]);
    save(output + "/down_fp32.bin", down); save(output + "/final_fp32.bin", final);
    std::printf("QWEN2_LAYER0_DOWN_FINAL_PASS commands=21 rows=1024 values=%zu down_fnv=%016llx final_fnv=%016llx\n", down.size(), (unsigned long long)fnv32(down), (unsigned long long)fnv32(final));
  } else { std::fprintf(stderr, "unknown stage\n"); return 2; }
  return 0;
}

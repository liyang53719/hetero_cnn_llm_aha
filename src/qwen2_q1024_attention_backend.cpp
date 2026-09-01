#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <limits>
#include <string>
#include <vector>
#include <omp.h>

static float bf(uint16_t value) {
  uint32_t word = uint32_t(value) << 16;
  float result;
  __builtin_memcpy(&result, &word, sizeof(result));
  return result;
}

static uint16_t tobf(float value) {
  uint32_t word;
  __builtin_memcpy(&word, &value, sizeof(word));
  if (((word >> 23) & 255u) == 255u && (word & 0x7fffffu)) {
    uint16_t result = uint16_t(word >> 16) | 0x40u;
    if ((result & 0x7fu) == 0) result |= 1u;
    return result;
  }
  word += 0x7fffu + ((word >> 16) & 1u);
  return uint16_t(word >> 16);
}

template <class T>
static std::vector<T> load(const std::string &path, size_t count) {
  std::vector<T> values(count);
  std::ifstream stream(path, std::ios::binary);
  stream.read(reinterpret_cast<char *>(values.data()), count * sizeof(T));
  if (!stream || size_t(stream.gcount()) != count * sizeof(T)) {
    std::fprintf(stderr, "load fail %s\n", path.c_str());
    std::exit(2);
  }
  return values;
}

template <class T>
static void save(const std::string &path, const std::vector<T> &values) {
  std::ofstream stream(path, std::ios::binary);
  stream.write(reinterpret_cast<const char *>(values.data()), values.size() * sizeof(T));
  if (!stream) std::exit(3);
}

static uint64_t fnv(const std::vector<uint16_t> &values) {
  uint64_t hash = 1469598103934665603ull;
  for (const uint16_t value : values) {
    hash = (hash ^ (value & 255u)) * 1099511628211ull;
    hash = (hash ^ (value >> 8)) * 1099511628211ull;
  }
  return hash;
}

static float add32(float a, float b) {
  volatile float result = a + b;
  return result;
}

static float mul32(float a, float b) {
  volatile float result = a * b;
  return result;
}

static float from_bits(uint32_t bits) {
  float value;
  __builtin_memcpy(&value, &bits, sizeof(value));
  return value;
}

static float exp2_pwl256(float x) {
  if (x < -16.0f) return 0.0f;
  if (x >= 0.0f) return 1.0f;
  const int index = std::max(0, std::min(255, int(std::floor(double(x) * 16.0)) + 256));
  const float x0 = float(index) / 16.0f - 16.0f;
  const float x1 = x0 + 1.0f / 16.0f;
  const float y0 = std::exp2(x0);
  const float y1 = std::exp2(x1);
  const float slope = float((double(y1) - double(y0)) / (1.0 / 16.0));
  const float intercept = float(double(y0) - double(slope) * double(x0));
  return add32(mul32(slope, x), intercept);
}

static float reciprocal_pwl_nr(float x) {
  uint32_t word;
  __builtin_memcpy(&word, &x, sizeof(word));
  const int exponent = int((word >> 23) & 255u);
  const uint32_t fraction = word & 0x7fffffu;
  const float normalized = from_bits((127u << 23) | fraction);
  const int index = int(fraction >> 19);
  const double x0 = 1.0 + double(index) / 16.0;
  const double x1 = x0 + 1.0 / 16.0;
  const float slope = float(((1.0 / x1) - (1.0 / x0)) / (1.0 / 16.0));
  const float intercept = float(1.0 / x0 - double(slope) * x0);
  float estimate = add32(mul32(slope, normalized), intercept);
  estimate = mul32(estimate, add32(2.0f, -mul32(normalized, estimate)));
  return mul32(estimate, from_bits(uint32_t(254 - exponent) << 23));
}

int main(int argc, char **argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: input_dir output_dir\n");
    return 2;
  }
  const std::string input = argv[1];
  const std::string output = argv[2];
  const auto commands = load<uint8_t>(input + "/first13_commands.bin", 13 * 16);
  const uint8_t opcodes[13] = {0x32,0x20,0x30,0x34,0x20,0x30,0x34,0x20,0x30,0x41,0x23,0x33,0x24};
  const uint8_t engines[13] = {3,2,3,3,2,3,3,2,3,4,2,3,2};
  for (int index = 0; index < 13; ++index) {
    if (commands[index * 16] != opcodes[index] ||
        (commands[index * 16 + 1] & 7u) != engines[index]) {
      std::fprintf(stderr, "command mismatch %d\n", index);
      return 4;
    }
  }

  constexpr int tokens = 1024;
  constexpr int query_heads = 12;
  constexpr int kv_heads = 2;
  constexpr int head_dim = 128;
  constexpr int hidden = query_heads * head_dim;
  constexpr int kv_hidden = kv_heads * head_dim;
  constexpr int block_tokens = 128;
  const float scale = from_bits(0x3db504f3u);
  const float log2e = from_bits(0x3fb8aa3bu);
  const auto q = load<uint16_t>(output + "/q_rope.bin", size_t(tokens) * hidden);
  const auto k = load<uint16_t>(output + "/k_rope.bin", size_t(tokens) * kv_hidden);
  const auto v = load<uint16_t>(output + "/v_bias.bin", size_t(tokens) * kv_hidden);
  std::vector<uint16_t> attention_bf16(size_t(tokens) * hidden);
  std::vector<float> attention_fp32(size_t(tokens) * hidden);
  std::vector<float> m_values(size_t(tokens) * query_heads);
  std::vector<float> l_values(size_t(tokens) * query_heads);
  double max_fp32_error = 0.0;
  double max_bf16_error = 0.0;
  const double start = omp_get_wtime();

#pragma omp parallel for collapse(2) schedule(dynamic, 1) reduction(max:max_fp32_error,max_bf16_error)
  for (int query_token = 0; query_token < tokens; ++query_token) {
    for (int query_head = 0; query_head < query_heads; ++query_head) {
      const int kv_head = query_head / (query_heads / kv_heads);
      const size_t q_base = size_t(query_token) * hidden + query_head * head_dim;
      float merged_m = -std::numeric_limits<float>::infinity();
      float merged_l = 0.0f;
      float merged_o[head_dim] = {};
      double truth_m = -std::numeric_limits<double>::infinity();
      double truth_l = 0.0;
      double truth_o[head_dim] = {};

      for (int block_start = 0; block_start <= query_token; block_start += block_tokens) {
        const int block_end = std::min(query_token + 1, block_start + block_tokens);
        float block_m = -std::numeric_limits<float>::infinity();
        float block_l = 0.0f;
        float block_o[head_dim] = {};
        for (int key_token = block_start; key_token < block_end; ++key_token) {
          const size_t kv_base = size_t(key_token) * kv_hidden + kv_head * head_dim;
          float dot = 0.0f;
          for (int dim = 0; dim < head_dim; ++dim)
            dot = std::fma(bf(q[q_base + dim]), bf(k[kv_base + dim]), dot);
          const float score = mul32(dot, scale);
          if (key_token == block_start) {
            block_m = score;
            block_l = 1.0f;
            for (int dim = 0; dim < head_dim; ++dim) block_o[dim] = bf(v[kv_base + dim]);
          } else {
            const float next_m = std::max(block_m, score);
            const float alpha = exp2_pwl256(mul32(add32(block_m, -next_m), log2e));
            const float beta = exp2_pwl256(mul32(add32(score, -next_m), log2e));
            block_l = add32(mul32(block_l, alpha), beta);
            for (int dim = 0; dim < head_dim; ++dim)
              block_o[dim] = add32(mul32(block_o[dim], alpha), mul32(bf(v[kv_base + dim]), beta));
            block_m = next_m;
          }

          const double score64 = double(score);
          const double next_truth_m = std::max(truth_m, score64);
          const double truth_alpha = std::isinf(truth_m) ? 0.0 : std::exp(truth_m - next_truth_m);
          const double truth_beta = std::exp(score64 - next_truth_m);
          truth_l = truth_l * truth_alpha + truth_beta;
          for (int dim = 0; dim < head_dim; ++dim)
            truth_o[dim] = truth_o[dim] * truth_alpha + double(bf(v[kv_base + dim])) * truth_beta;
          truth_m = next_truth_m;
        }

        if (block_start == 0) {
          merged_m = block_m;
          merged_l = block_l;
          std::copy(block_o, block_o + head_dim, merged_o);
        } else {
          const float next_m = std::max(merged_m, block_m);
          const float alpha = exp2_pwl256(mul32(add32(merged_m, -next_m), log2e));
          const float beta = exp2_pwl256(mul32(add32(block_m, -next_m), log2e));
          merged_l = add32(mul32(merged_l, alpha), mul32(block_l, beta));
          for (int dim = 0; dim < head_dim; ++dim)
            merged_o[dim] = add32(mul32(merged_o[dim], alpha), mul32(block_o[dim], beta));
          merged_m = next_m;
        }
      }

      const float inverse = reciprocal_pwl_nr(merged_l);
      const size_t summary_index = size_t(query_token) * query_heads + query_head;
      m_values[summary_index] = merged_m;
      l_values[summary_index] = merged_l;
      for (int dim = 0; dim < head_dim; ++dim) {
        const float normalized = mul32(merged_o[dim], inverse);
        const uint16_t normalized_bf16 = tobf(normalized);
        const double truth = truth_o[dim] / truth_l;
        attention_fp32[q_base + dim] = normalized;
        attention_bf16[q_base + dim] = normalized_bf16;
        max_fp32_error = std::max(max_fp32_error, std::abs(double(normalized) - truth));
        max_bf16_error = std::max(max_bf16_error, std::abs(double(bf(normalized_bf16)) - truth));
      }
    }
  }

  save(output + "/attention_fp32.bin", attention_fp32);
  save(output + "/attention_bf16.bin", attention_bf16);
  save(output + "/attention_m_fp32.bin", m_values);
  save(output + "/attention_l_fp32.bin", l_values);
  const long long updates = 6297600;
  const long long merges = 43008;
  std::printf(
      "QWEN2_Q1024_ATTENTION_BACKEND_PASS commands=13 rows=1024 updates=%lld "
      "merges=%lld attention_values=%zu score_matrix_bytes=0 max_fp32_error=%.9g "
      "max_bf16_error=%.9g seconds=%.6f attention_fnv=%016llx\n",
      updates, merges, attention_bf16.size(), max_fp32_error, max_bf16_error,
      omp_get_wtime() - start, (unsigned long long)fnv(attention_bf16));
  return max_fp32_error <= 0.002 ? 0 : 5;
}

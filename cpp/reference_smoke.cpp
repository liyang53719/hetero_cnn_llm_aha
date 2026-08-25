// SPDX-License-Identifier: Apache-2.0
#include <array>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <utility>
#include <vector>

static std::vector<int32_t> gemm_i8(const std::vector<int8_t>& a,
                                    const std::vector<int8_t>& b,
                                    int m, int n, int k) {
  if (static_cast<int>(a.size()) != m * k || static_cast<int>(b.size()) != k * n) {
    throw std::invalid_argument("GEMM shape mismatch");
  }
  std::vector<int32_t> c(m * n, 0);
  for (int i = 0; i < m; ++i) {
    for (int j = 0; j < n; ++j) {
      for (int p = 0; p < k; ++p) {
        c[i * n + j] += static_cast<int32_t>(a[i * k + p]) *
                         static_cast<int32_t>(b[p * n + j]);
      }
    }
  }
  return c;
}

class TinyPagedKv {
 public:
  explicit TinyPagedKv(std::size_t page_tokens) : page_tokens_(page_tokens) {
    if (page_tokens_ == 0) throw std::invalid_argument("zero page size");
  }

  void append(int32_t k, int32_t v) {
    if (length_ % page_tokens_ == 0) pages_.push_back({});
    pages_.back().push_back({k, v});
    ++length_;
  }

  std::pair<int32_t, int32_t> read(std::size_t token) const {
    if (token >= length_) throw std::out_of_range("KV token");
    return pages_[token / page_tokens_][token % page_tokens_];
  }

  std::size_t pages() const { return pages_.size(); }
  std::size_t length() const { return length_; }

 private:
  std::size_t page_tokens_;
  std::size_t length_ = 0;
  std::vector<std::vector<std::pair<int32_t, int32_t>>> pages_;
};

int main() {
  const std::vector<int8_t> a = {1, 3, -2, 2, -1, 4};
  const std::vector<int8_t> b = {4, 5, 2, 1, -1, 3};
  const auto c = gemm_i8(a, b, 2, 2, 3);
  const std::array<int32_t, 4> expected = {12, 2, 2, 21};
  for (std::size_t i = 0; i < expected.size(); ++i) {
    if (c[i] != expected[i]) return EXIT_FAILURE;
  }

  TinyPagedKv kv(4);
  for (int i = 0; i < 9; ++i) kv.append(100 + i, 200 + i);
  if (kv.pages() != 3 || kv.length() != 9) return EXIT_FAILURE;
  if (kv.read(8) != std::pair<int32_t, int32_t>{108, 208}) return EXIT_FAILURE;

  std::cout << "{\"cpp_reference_smoke\":\"PASS\",\"gemm_outputs\":4,"
            << "\"kv_pages\":" << kv.pages() << ",\"kv_tokens\":" << kv.length()
            << "}\n";
  return EXIT_SUCCESS;
}

#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static constexpr int kRows = 16;
static constexpr int kInputs = 1536;
static constexpr int kOutputs = 8960;

static float from_bits(uint32_t value) {
  float result;
  std::memcpy(&result, &value, sizeof(result));
  return result;
}

static uint32_t to_bits(float value) {
  uint32_t result;
  std::memcpy(&result, &value, sizeof(result));
  return result;
}

static uint16_t to_bf16(float value) {
  uint32_t word = to_bits(value);
  return static_cast<uint16_t>((word + 0x7fffu + ((word >> 16) & 1u)) >> 16);
}

static std::vector<uint32_t> read_hex32(const std::string& path) {
  std::ifstream stream(path);
  if (!stream) throw std::runtime_error("open " + path);
  std::vector<uint32_t> values;
  std::string line;
  while (std::getline(stream, line)) {
    if (!line.empty()) values.push_back(static_cast<uint32_t>(std::stoul(line, nullptr, 16)));
  }
  return values;
}

static std::vector<uint16_t> read_hex16(const std::string& path) {
  std::ifstream stream(path);
  if (!stream) throw std::runtime_error("open " + path);
  std::vector<uint16_t> values;
  values.reserve(static_cast<size_t>(kInputs) * kOutputs);
  std::string line;
  while (std::getline(stream, line)) {
    if (!line.empty()) values.push_back(static_cast<uint16_t>(std::stoul(line, nullptr, 16)));
  }
  return values;
}

static void write_hex32(const std::string& path, const std::vector<uint32_t>& values) {
  std::ofstream stream(path);
  if (!stream) throw std::runtime_error("write " + path);
  stream << std::hex << std::setfill('0');
  for (uint32_t value : values) stream << std::setw(8) << value << '\n';
}

static void project(const std::vector<float>& input,
                    const std::string& weight_path,
                    const std::string& output_path) {
  std::vector<uint16_t> weights = read_hex16(weight_path);
  if (weights.size() != static_cast<size_t>(kInputs) * kOutputs)
    throw std::runtime_error("weight count");
  std::vector<uint32_t> output(static_cast<size_t>(kRows) * kOutputs);
#pragma omp parallel for schedule(static)
  for (int column = 0; column < kOutputs; ++column) {
    float accumulators[kRows] = {};
    for (int k = 0; k < kInputs; ++k) {
      float weight = from_bits(static_cast<uint32_t>(weights[static_cast<size_t>(k) * kOutputs + column]) << 16);
      for (int row = 0; row < kRows; ++row)
        accumulators[row] = std::fma(input[static_cast<size_t>(row) * kInputs + k], weight, accumulators[row]);
    }
    for (int row = 0; row < kRows; ++row)
      output[static_cast<size_t>(row) * kOutputs + column] = to_bits(accumulators[row]);
  }
  write_hex32(output_path, output);
}

int main(int argc, char** argv) {
  if (argc != 6) {
    std::cerr << "usage: golden norm2 gate_weights up_weights gate_out up_out\n";
    return 2;
  }
  try {
    std::vector<uint32_t> words = read_hex32(argv[1]);
    if (words.size() != static_cast<size_t>(kRows) * kInputs)
      throw std::runtime_error("input count");
    std::vector<float> input(words.size());
    for (size_t i = 0; i < words.size(); ++i)
      input[i] = from_bits(static_cast<uint32_t>(to_bf16(from_bits(words[i]))) << 16);
    project(input, argv[2], argv[4]);
    project(input, argv[3], argv[5]);
    std::cout << "L5_Q128_GATE_UP_CPP_GOLDEN_PASS rows=16 shape=1536x8960\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}

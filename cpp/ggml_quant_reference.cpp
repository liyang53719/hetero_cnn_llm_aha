#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static float fp16_to_float(uint16_t half) {
    const uint32_t sign = uint32_t(half & 0x8000u) << 16;
    uint32_t exponent = (half >> 10) & 0x1fu;
    uint32_t mantissa = half & 0x03ffu;
    uint32_t bits;
    if (exponent == 0) {
        if (mantissa == 0) {
            bits = sign;
        } else {
            int shift = 0;
            while ((mantissa & 0x0400u) == 0) {
                mantissa <<= 1;
                ++shift;
            }
            mantissa &= 0x03ffu;
            bits = sign | uint32_t(127 - 15 - shift) << 23 | mantissa << 13;
        }
    } else if (exponent == 31) {
        bits = sign | 0x7f800000u | mantissa << 13;
    } else {
        bits = sign | (exponent + (127 - 15)) << 23 | mantissa << 13;
    }
    return std::bit_cast<float>(bits);
}

static std::vector<uint8_t> hex_to_bytes(const std::string &hex) {
    if (hex.size() % 2) {
        throw std::runtime_error("hex length");
    }
    std::vector<uint8_t> output(hex.size() / 2);
    for (size_t index = 0; index < output.size(); ++index) {
        output[index] = uint8_t(std::stoul(hex.substr(2 * index, 2), nullptr, 16));
    }
    return output;
}

static int8_t signed_byte(uint8_t value) {
    return static_cast<int8_t>(value);
}

static double activation(int case_id, int index) {
    return std::sin(double(case_id + 1) * double(index + 3) * 0.001);
}

static double q8_dot(const std::vector<uint8_t> &payload, int case_id) {
    if (payload.size() != 34) {
        throw std::runtime_error("Q8_0 size");
    }
    const float scale = fp16_to_float(uint16_t(payload[0]) | uint16_t(payload[1]) << 8);
    double sum = 0.0;
    for (int index = 0; index < 32; ++index) {
        sum += double(scale) * double(signed_byte(payload[2 + index])) * activation(case_id, index);
    }
    return sum;
}

static double q6_dot(const std::vector<uint8_t> &payload, int case_id) {
    if (payload.size() != 210) {
        throw std::runtime_error("Q6_K size");
    }
    const uint8_t *low = payload.data();
    const uint8_t *high = payload.data() + 128;
    const uint8_t *scales = payload.data() + 192;
    const float delta = fp16_to_float(uint16_t(payload[208]) | uint16_t(payload[209]) << 8);
    double sum = 0.0;
    for (int half = 0; half < 2; ++half) {
        const int low_base = half * 64;
        const int high_base = half * 32;
        const int scale_base = half * 8;
        const int output_base = half * 128;
        for (int lane = 0; lane < 32; ++lane) {
            const int scale_lane = lane / 16;
            const uint8_t high_bits = high[high_base + lane];
            int quant[4] = {
                (low[low_base + lane] & 15) | (((high_bits >> 0) & 3) << 4),
                (low[low_base + lane + 32] & 15) | (((high_bits >> 2) & 3) << 4),
                (low[low_base + lane] >> 4) | (((high_bits >> 4) & 3) << 4),
                (low[low_base + lane + 32] >> 4) | (((high_bits >> 6) & 3) << 4),
            };
            int scale_index[4] = {
                scale_base + scale_lane,
                scale_base + scale_lane + 2,
                scale_base + scale_lane + 4,
                scale_base + scale_lane + 6,
            };
            for (int group = 0; group < 4; ++group) {
                const int index = output_base + lane + 32 * group;
                sum += double(delta) * double(signed_byte(scales[scale_index[group]]))
                    * double(quant[group] - 32) * activation(case_id, index);
            }
        }
    }
    return sum;
}

static std::array<int, 16> q3_scales(const uint8_t *source) {
    std::array<uint32_t, 4> auxiliary{};
    for (int index = 0; index < 12; ++index) {
        reinterpret_cast<uint8_t *>(auxiliary.data())[index] = source[index];
    }
    const uint32_t temporary = auxiliary[2];
    auxiliary[2] = ((auxiliary[0] >> 4) & 0x0f0f0f0fu) | (((temporary >> 0) & 0x03030303u) << 4);
    auxiliary[3] = ((auxiliary[1] >> 4) & 0x0f0f0f0fu) | (((temporary >> 2) & 0x03030303u) << 4);
    auxiliary[0] = (auxiliary[0] & 0x0f0f0f0fu) | (((temporary >> 4) & 0x03030303u) << 4);
    auxiliary[1] = (auxiliary[1] & 0x0f0f0f0fu) | (((temporary >> 6) & 0x03030303u) << 4);
    std::array<int, 16> output{};
    const auto *bytes = reinterpret_cast<uint8_t *>(auxiliary.data());
    for (int index = 0; index < 16; ++index) {
        output[index] = int(bytes[index]) - 32;
    }
    return output;
}

static double q3_dot(const std::vector<uint8_t> &payload, int case_id) {
    if (payload.size() != 110) {
        throw std::runtime_error("Q3_K size");
    }
    const auto scales = q3_scales(payload.data() + 96);
    const float delta = fp16_to_float(uint16_t(payload[108]) | uint16_t(payload[109]) << 8);
    double sum = 0.0;
    for (int half = 0; half < 2; ++half) {
        const int quant_base = half * 32;
        const int output_base = half * 128;
        const int mask_base = 1 << (half * 4);
        const int scale_base = half * 8;
        for (int lane = 0; lane < 32; ++lane) {
            const int scale_lane = lane / 16;
            const uint8_t packed = payload[32 + quant_base + lane];
            const uint8_t mask = payload[lane];
            for (int group = 0; group < 4; ++group) {
                const int low = (packed >> (2 * group)) & 3;
                const int quant = (mask & (mask_base << group)) ? low : low - 4;
                const int index = output_base + lane + 32 * group;
                sum += double(delta) * double(scales[scale_base + scale_lane + 2 * group])
                    * double(quant) * activation(case_id, index);
            }
        }
    }
    return sum;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        return 2;
    }
    std::ifstream input(argv[1]);
    std::string line;
    int count = 0;
    double maximum_error = 0.0;
    while (std::getline(input, line)) {
        if (line.empty() || line[0] == '#') {
            continue;
        }
        std::istringstream stream(line);
        std::string format;
        std::string payload_hex;
        int case_id;
        double expected;
        stream >> format >> case_id >> payload_hex >> expected;
        const auto payload = hex_to_bytes(payload_hex);
        const double actual = format == "Q8_0"
            ? q8_dot(payload, case_id)
            : format == "Q6_K"
                ? q6_dot(payload, case_id)
                : q3_dot(payload, case_id);
        const double error = std::abs(actual - expected);
        maximum_error = std::max(maximum_error, error);
        if (error > 1e-5) {
            return 1;
        }
        ++count;
    }
    std::cout << "{\"status\":\"PASS\",\"vectors\":" << count
              << ",\"max_abs_error\":" << std::setprecision(17)
              << maximum_error << "}\n";
    return 0;
}

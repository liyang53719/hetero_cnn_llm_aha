// Tiny test-only payload/private wiring behavior. Not a generated model or ABI test.
#define CANONICAL_RUNTIME_UNIT_TEST 1
#include "runtime_ram.hpp"
#include "canonical_launch.hpp"
#include "completion_payload.hpp"
#include <cstddef>
#include <cstdint>
#include <initializer_list>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
std::size_t checks = 0;

void require(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}

template<class Function>
void rejects(Function function, const char* expected) {
    bool rejected = false;
    try {
        function();
    } catch (const std::invalid_argument& error) {
        require(std::string(error.what()) == expected, "unexpected rejection");
        rejected = true;
    }
    require(rejected, "expected invalid payload rejection");
}

struct PayloadFixture {
    std::uint64_t io_launch_bits_commandBase = 0;
    std::uint64_t io_launch_bits_commandLimit = 0;
    std::uint16_t io_launch_bits_commands = 0;
    std::uint64_t io_launch_bits_descriptorBase = 0;
    std::uint64_t io_launch_bits_descriptorLimit = 0;
    std::uint32_t io_launch_bits_descriptors = 0;
    std::uint16_t io_launch_bits_epoch = 0;
    std::uint64_t io_launch_bits_regions_0_base = 0;
    std::uint64_t io_launch_bits_regions_0_limit = 0;
    bool io_launch_bits_regions_0_read = false;
    bool io_launch_bits_regions_0_write = true;
    std::uint64_t io_launch_bits_regions_1_base = 0;
    std::uint64_t io_launch_bits_regions_1_limit = 0;
    bool io_launch_bits_regions_1_read = false;
    bool io_launch_bits_regions_1_write = false;
    std::uint64_t io_launch_bits_regions_2_base = 0;
    std::uint64_t io_launch_bits_regions_2_limit = 0;
    bool io_launch_bits_regions_2_read = false;
    bool io_launch_bits_regions_2_write = true;
    std::uint64_t io_launch_bits_regions_3_base = 0;
    std::uint64_t io_launch_bits_regions_3_limit = 0;
    bool io_launch_bits_regions_3_read = false;
    bool io_launch_bits_regions_3_write = false;

    // Sentinels, never handshakes or a model success stub. There is no eval().
    bool io_launch_valid = false;
    bool io_launch_ready = true;
    bool io_completion_ready = false;
    bool clock = true;
    bool reset = true;
};

void test_launch_payload() {
    for (const bool valid_before : {false, true}) {
        PayloadFixture d;
        d.io_launch_valid = valid_before;
        canonical_host_wiring_v1::launch_payload(d);
        require(d.io_launch_bits_commandBase == 4294967296ULL, "command base");
        require(d.io_launch_bits_commandLimit == 4294967680ULL, "command limit");
        require(d.io_launch_bits_commands == 21, "21 public commands");
        require(d.io_launch_bits_descriptorBase == 4294971392ULL, "descriptor base");
        require(d.io_launch_bits_descriptorLimit == 4294974848ULL, "descriptor limit");
        require(d.io_launch_bits_descriptors == 215, "215 descriptors");
        require(d.io_launch_bits_epoch == 7, "epoch seven");
        require(d.io_launch_bits_regions_0_base == 4295032832ULL, "region zero base");
        require(d.io_launch_bits_regions_0_limit == 4483535808ULL, "region zero limit");
        require(d.io_launch_bits_regions_0_read, "region zero read");
        require(!d.io_launch_bits_regions_0_write, "region zero write");
        require(d.io_launch_bits_regions_1_base == 4483535808ULL, "region one base");
        require(d.io_launch_bits_regions_1_limit == 4507654464ULL, "region one limit");
        require(d.io_launch_bits_regions_1_read, "region one read");
        require(d.io_launch_bits_regions_1_write, "region one write");
        require(d.io_launch_bits_regions_2_base == 4294967296ULL, "region two base");
        require(d.io_launch_bits_regions_2_limit == 4295032832ULL, "region two limit");
        require(d.io_launch_bits_regions_2_read, "region two read");
        require(!d.io_launch_bits_regions_2_write, "region two write");
        require(d.io_launch_bits_regions_3_base == 4507654464ULL, "region three base");
        require(d.io_launch_bits_regions_3_limit == 4508440896ULL, "region three limit");
        require(d.io_launch_bits_regions_3_read, "region three read");
        require(d.io_launch_bits_regions_3_write, "region three write");
        require(d.io_launch_valid == valid_before, "launch valid was modified");
        require(d.io_launch_ready, "launch ready was modified");
        require(!d.io_completion_ready, "completion ready was modified");
        require(d.clock, "clock was modified");
        require(d.reset, "reset was modified");
    }
}

void test_completion_payload() {
    using canonical_host_wiring_v1::decode_completion;
    using canonical_host_wiring_v1::require_pc0_completion_payload;
    constexpr std::uint64_t pc0 = 0x10060000000ULL;
    const auto zero = decode_completion(0);
    require(zero.pc == 0 && zero.owner == 0 && zero.status == 0 && zero.signal == 0,
            "zero decode");
    const auto maximum = decode_completion(0x00ffffffffffffffULL);
    require(maximum.pc == 0x1fffffffU, "all 29 PC bits retained");
    require(maximum.owner == 7, "three owner bits");
    require(maximum.status == 255, "eight status bits");
    require(maximum.signal == 65535, "sixteen signal bits");
    const auto payload = require_pc0_completion_payload(pc0);
    require(payload.pc == 0, "PC0 payload PC");
    require(payload.owner == 3, "PC0 payload owner");
    require(payload.status == 0, "PC0 payload status");
    require(payload.signal == 1, "PC0 payload signal");
    require(pc0 == ((1ULL << 40) | (3ULL << 29)), "documented raw PC0 word");

    for (unsigned bit = 56; bit < 64; ++bit) {
        const auto raw = pc0 | (1ULL << bit);
        rejects([&] { (void)decode_completion(raw); },
                "completion payload exceeds 56 bits");
        rejects([&] { (void)require_pc0_completion_payload(raw); },
                "completion payload exceeds 56 bits");
    }
    for (unsigned bit = 0; bit < 29; ++bit)
        rejects([&] { (void)require_pc0_completion_payload(pc0 | (1ULL << bit)); },
                "completion payload is not PC0");
    for (unsigned owner = 0; owner < 8; ++owner) {
        if (owner == 3) continue;
        const auto raw = (pc0 & ~(7ULL << 29)) | (std::uint64_t{owner} << 29);
        rejects([&] { (void)require_pc0_completion_payload(raw); },
                "completion payload owner is not SFU_CGRA");
    }
    for (unsigned bit = 32; bit < 40; ++bit)
        rejects([&] { (void)require_pc0_completion_payload(pc0 | (1ULL << bit)); },
                "completion payload status is not zero");
    for (unsigned bit = 40; bit < 56; ++bit)
        rejects([&] { (void)require_pc0_completion_payload(pc0 ^ (1ULL << bit)); },
                "completion payload signal is not one");
}
} // namespace

#include "test_private_wiring.inc"

int main() {
    try {
        test_launch_payload();
        test_completion_payload();
        test_private_wiring();
        std::cout << "{\"status\":\"N0_WIRING_FIXTURE_BEHAVIOR_PASS\",\"checks\":" << checks
                  << ",\"max_synthetic_arena_bytes\":1024,\"modelbinding\":false,"
                     "\"adapter_runtime_bound\":false,\"canonical_input_sha_verified\":false,"
                     "\"actual_n0_execution\":false,\"full_host_ready\":false,"
                     "\"launch_ready\":false,\"eda_executed\":false}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "payload fixture test failed: " << error.what() << '\n';
        return 1;
    }
}

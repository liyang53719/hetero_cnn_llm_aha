// Fixed canonical16 real-file consumer. Initialization proof only; no Host/EDA.
#include "canonical16_binding.hpp"
#include <array>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace fixed = canonical16_binding_v1;
using same_buffer_loader_v1::Sha256;
static void require(bool ok, const char* why) {
    if (!ok) throw std::runtime_error(why);
}
static std::string hex(const Sha256::Digest& digest) {
    constexpr char alphabet[] = "0123456789abcdef";
    std::string text;
    text.reserve(64);
    for (auto byte : digest) {
        text.push_back(alphabet[byte >> 4]);
        text.push_back(alphabet[byte & 15]);
    }
    return text;
}
int main(int argc, char** argv) {
    try {
        require(argc == 3, "require metadata and provider directories");
        const std::filesystem::path metadata(argv[1]), providers(argv[2]);
        auto loader = fixed::make_canonical16_loader();
        for (std::size_t i = 0; i < fixed::expected_inputs.size(); ++i) {
            const auto& row = fixed::expected_inputs[i];
            const auto file = i < 2
                ? metadata / (std::string("host_") + row.name + ".bin")
                : providers / (std::string(row.name) + ".bin");
            require(!std::filesystem::is_symlink(file) &&
                    std::filesystem::is_regular_file(file), "regular input file required");
            require(std::filesystem::file_size(file) == row.bytes, "input file size differs");
            std::ifstream stream(file, std::ios::binary);
            require(stream.is_open(), "input open failed");
            // Default exception mask: loader itself requires exact terminal EOF.
            loader.load_next(row.name, stream);
        }
        auto token = loader.finish(); // seal coverage, then hash the same RAM
        const auto view = loader.take_ready(token); // one-shot token, rehash RAM
        std::array<Sha256::Digest, fixed::expected_inputs.size()> actual{};
        std::uint64_t coverage_bytes = 0;
        const std::uint8_t* anchor = nullptr;
        for (std::size_t i = 0; i < fixed::expected_inputs.size(); ++i) {
            const auto& row = fixed::expected_inputs[i];
            const auto span = view.read(i, 0, row.bytes); // checks initialized mask
            require(span.size == row.bytes && span.data != nullptr, "actual RAM span differs");
            if (i == 0) anchor = span.data;
            const auto offset = span.data - anchor; // same private backing array
            require(offset >= 0 && static_cast<std::uint64_t>(offset) == row.base - fixed::ram_base,
                    "actual RAM span offset differs");
            actual[i] = Sha256::hash(span.data, span.size); // fourth full SHA pass
            require(actual[i] == row.sha256, "actual view SHA256 mismatch");
            coverage_bytes += span.size;
        }
        require(coverage_bytes == 94920448ULL, "declared input coverage differs");
        // No output until every actual span passes. Digests below are computed
        // from the returned RAM spans, never copied from expected identities.
        std::ostringstream out;
        out << "{\"status\":\"CANONICAL16_SAME_RAM_VERIFIED\",\"inputs\":[";
        for (std::size_t i = 0; i < fixed::expected_inputs.size(); ++i) {
            const auto& row = fixed::expected_inputs[i];
            if (i) out << ',';
            out << "{\"index\":" << i << ",\"name\":\"" << row.name
                << "\",\"base\":" << row.base << ",\"bytes\":" << row.bytes
                << ",\"actual_sha256\":\"" << hex(actual[i]) << "\"}";
        }
        out << "],\"ram_base\":" << fixed::ram_base << ",\"ram_bytes\":" << fixed::ram_bytes
            << ",\"declared_coverage_bytes\":" << coverage_bytes
            << ",\"same_ram_offsets_verified\":true,\"coverage_sealed\":true"
            << ",\"token_redeemed_once\":true,\"sha256_passes\":4"
            << ",\"sha256_total_bytes\":" << 4 * coverage_bytes
            << ",\"full_host_ready\":false,\"launch_ready\":false,\"eda_executed\":false}";
        std::cout << out.str() << '\n';
        require(std::cout.good(), "result output failed");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "CANONICAL16_LOAD_FAILED: " << error.what() << '\n';
        return 1;
    } catch (...) {
        std::cerr << "CANONICAL16_LOAD_FAILED: unknown exception\n";
        return 1;
    }
}

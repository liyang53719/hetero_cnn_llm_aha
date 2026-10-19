#pragma once
#include "axi_protocol.hpp"
#include "first_n0_diagnostics.hpp"
#include "sha256.hpp"
#include <array>
#include <cstdint>
#include <vector>
namespace canonical_runtime_v1 {
struct FirstN0Counts {
    std::uint64_t cycles=0,launches=0,jobs=0,owner_dones=0,completion_acks=0;
    std::uint64_t core_read_requests=0,core_write_requests=0,core_responses=0;
    std::array<std::uint64_t,16> input_ar{},input_read_bytes{};
    std::array<std::uint64_t,128> core_state_cycles{};
};
struct FirstN0Result {
    enum class Status { Ack0ActualCaptured, IncompleteCycleBudget };
    Status status=Status::IncompleteCycleBudget;
    FirstN0Counts counts{};
    canonical_host::Ledger axi{};
    std::uint64_t committed_bytes=0,successful_b=0,writeback_bytes=0,completion_word=0;
    std::uint64_t idma_transfers=0,idma_read_bursts=0,idma_read_beats=0,idma_cache_hits=0;
    std::array<std::uint64_t,2> hub_accepted{},hub_returned{};
    unsigned post_pc=0,post_issued_jobs=0;
    std::array<same_buffer_loader_v1::Sha256::Digest,16> input_hashes{};
    same_buffer_loader_v1::Sha256::Digest actual_sha256{};
    // Local consumer-only bytes, NEVER print/publish as safe diagnostics.
    std::vector<std::uint8_t> actual_f32le;
};
}

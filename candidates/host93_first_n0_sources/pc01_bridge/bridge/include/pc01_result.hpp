#pragma once
#include "first_n0_result.hpp"
namespace canonical_runtime_v1 {
struct Pc01Result {
    enum class Status { IncompletePc0, IncompletePc1, Ack1Captured };
    Status status=Status::IncompletePc0;
    FirstN0Result n0;
    canonical_host::Ledger pc1_axi{};
    std::uint64_t total_cycles=0,pc1_entry_edge=0,pc1_accept_edge=0,ack1_edge=0,pc1_cycles=0;
    std::uint64_t pc1_jobs=0,pc1_dones=0,pc1_acks=0,qraw_committed=0,qraw_b=0;
    std::uint64_t matrix_wide_steps=0,matrix_slice_steps=0,matrix_stalls=0,add_requests=0,add_results=0;
    std::uint64_t useful_macs=0,executed_macs=0,completion_word=0,n0_read_bytes=0,wq_read_bytes=0;
    unsigned post_pc=0,post_issued_jobs=0;
    same_buffer_loader_v1::Sha256::Digest qraw_sha256{};
    std::vector<std::uint8_t> qraw_f32le;
};
namespace pc01 {
inline constexpr std::uint64_t useful_macs=301989888,physical_macs_per_cycle=4096;
inline constexpr std::uint64_t wide_steps=73728,slice_steps=589824,add_vectors=12288;
inline constexpr std::uint64_t qraw_bytes=786432,total_cycle_budget=8000000;
// This unchanged global cycle ceiling is exploratory, not a latency prediction.
// An independently reviewed wall-clock/resource launcher is still required.
}
}

#pragma once
#include <cstdint>
namespace canonical_runtime_v1::first_n0 {
inline constexpr std::uint64_t reduction_only_floor=2428928;
inline constexpr std::uint64_t cycle_budget=8000000;
inline constexpr std::uint64_t unproven_overhead_allowance=cycle_budget-reduction_only_floor;
inline constexpr std::uint64_t wall_seconds=3600,cpu_seconds=3540,address_space_bytes=6ULL*1024*1024*1024;
inline constexpr std::uint64_t native_wall_seconds=3540,comparison_and_save_reserve_seconds=45;
// Supervisor uses min(native_wall_seconds, shared_window_stop-now-45); never renew a deadline.
static_assert(unproven_overhead_allowance==5571072);
// This is an exploratory resource limit, not a completion or latency upper bound.
}

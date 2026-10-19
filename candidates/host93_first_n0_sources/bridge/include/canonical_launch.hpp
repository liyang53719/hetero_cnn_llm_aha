// SOURCE ONLY: fixed canonical M128 launch payload; no launch admission.
// Port names: canonical_host_pc0_startup_source_20261018/pc0/pc0_main.cpp:11-19.
// Values: EXPECTED_LAYOUT.json tables/epoch/regions and the exact region order
// in production_host_runtime_ram_portable_source_v1_20261018/runtime_policy.hpp.
#pragma once
#include <cstdint>

namespace canonical_host_wiring_v1 {

// Payload assignment alone proves neither input identity nor a launch handshake.
// This function has no override parameters, does not drive valid/ready/clock/reset,
// does not call eval(), and grants no RAM, owner, or publication authority.
template<class Model>
inline void launch_payload(Model& d) {
    d.io_launch_bits_commandBase = std::uint64_t{4294967296ULL};
    d.io_launch_bits_commandLimit = std::uint64_t{4294967680ULL};
    d.io_launch_bits_commands = std::uint16_t{21};
    d.io_launch_bits_descriptorBase = std::uint64_t{4294971392ULL};
    d.io_launch_bits_descriptorLimit = std::uint64_t{4294974848ULL};
    d.io_launch_bits_descriptors = std::uint32_t{215};
    d.io_launch_bits_epoch = std::uint16_t{7};

    d.io_launch_bits_regions_0_base = std::uint64_t{4295032832ULL};
    d.io_launch_bits_regions_0_limit = std::uint64_t{4483535808ULL};
    d.io_launch_bits_regions_0_read = true;
    d.io_launch_bits_regions_0_write = false;
    d.io_launch_bits_regions_1_base = std::uint64_t{4483535808ULL};
    d.io_launch_bits_regions_1_limit = std::uint64_t{4507654464ULL};
    d.io_launch_bits_regions_1_read = true;
    d.io_launch_bits_regions_1_write = true;
    d.io_launch_bits_regions_2_base = std::uint64_t{4294967296ULL};
    d.io_launch_bits_regions_2_limit = std::uint64_t{4295032832ULL};
    d.io_launch_bits_regions_2_read = true;
    d.io_launch_bits_regions_2_write = false;
    d.io_launch_bits_regions_3_base = std::uint64_t{4507654464ULL};
    d.io_launch_bits_regions_3_limit = std::uint64_t{4508440896ULL};
    d.io_launch_bits_regions_3_read = true;
    d.io_launch_bits_regions_3_write = true;
}

} // namespace canonical_host_wiring_v1

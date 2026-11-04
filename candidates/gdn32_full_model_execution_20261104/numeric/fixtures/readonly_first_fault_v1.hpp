#pragma once
#include "readonly_first_fault_access.hpp"
#include <cstdint>
#include <cstdio>

// Host-only diagnostic: no model writes, eval, clock step, or exception handling.
// The separately validated generated accessor reads exactly the fixed schema.
namespace readonly_first_fault {
static_assert(readonly_first_fault_access::field_count == 114, "fixed probe cardinality");
struct Sample {
    std::uint64_t cycle=0, active_cycle=0, completions=0;
    readonly_first_fault_access::Values values{};
};
class Collector {
    Sample previous{};
    bool previous_valid=false, emitted=false;
    static void print_sample(const char* slot, bool valid, const Sample& s) noexcept {
        std::printf("HOST_FIRST_FAULT_SLOT_V1 slot=%s valid=%u cycle=%llu active_cycle=%llu completions=%llu values=", slot, unsigned(valid),
                    static_cast<unsigned long long>(s.cycle), static_cast<unsigned long long>(s.active_cycle), static_cast<unsigned long long>(s.completions));
        for (std::size_t i=0; i<s.values.size(); ++i)
            std::printf(i ? ",%llu" : "%llu", static_cast<unsigned long long>(s.values[i]));
        std::printf("\n");
    }
public:
    void observe(const VHostBlockTopV4& top, std::uint64_t cycle,
                 std::uint64_t active_cycle, std::uint64_t completions,
                 bool reset_required) noexcept {
        const Sample current{cycle, active_cycle, completions,
                             readonly_first_fault_access::capture(top)};
        if (reset_required) {
            if (!emitted) {
                emitted=true;
                std::printf("HOST_FIRST_FAULT_V1 schema_sha256=%s fields=114 extra_eval=0 extra_clock=0\n", readonly_first_fault_access::schema_sha256);
                print_sample("previous_healthy", previous_valid, previous);
                print_sample("current_fault", true, current);
                std::fflush(stdout);
            }
        } else {
            previous=current;
            previous_valid=true;
        }
    }
};
}

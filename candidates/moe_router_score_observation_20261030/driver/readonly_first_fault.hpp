#pragma once
#include "readonly_first_fault_access.hpp"
#include "readonly_terminal_finite_access.hpp"
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
// Independent bounded summary; the original 114-field collector remains intact.
static_assert(readonly_terminal_finite_access::word_count == 4096, "fixed terminal words");
inline constexpr const char* terminal_summary_schema_sha256 = "10ef123a49d3490454b9f62ceb2ec63a1ac7325eb688cb001729b68af3c1fde4";
struct TerminalSummary {
    bool valid=false;
    std::uint64_t cycle=0, active_cycle=0, pc=0, completions=0, ng=0, context=0;
    std::uint64_t result_last=0, result_error=0, words=0, finite=0, nan=0, positive_infinity=0, negative_infinity=0;
    std::uint64_t effective_words=0, padding_words=0, unknown_region_words=0;
    std::uint64_t nonfinite_effective=0, nonfinite_padding=0, nonfinite_unknown_region=0;
    std::uint64_t first_nonfinite_index=4096;
    unsigned mapping=0, first_kind=0, first_region=0;
};
inline void print_terminal_summary(const TerminalSummary& s, std::uint64_t accepted_samples, std::uint64_t fault_pc) noexcept {
    const char* mapping[] = {"NONE", "SUPPORTED", "UNSUPPORTED_MAPPING"};
    const char* kinds[] = {"NONE", "NAN", "POS_INF", "NEG_INF"};
    const char* regions[] = {"NONE", "EFFECTIVE", "PADDING", "UNKNOWN"};
    std::printf("HOST_TERMINAL_FINITE_SUMMARY_V1 schema_sha256=%s sample_valid=%u accepted_samples=%llu cycle=%llu active_cycle=%llu pc=%llu completions=%llu ng=%llu context=%llu result_last=%llu result_error=%llu mapping=%s words=%llu finite=%llu nan=%llu positive_infinity=%llu negative_infinity=%llu effective_words=%llu padding_words=%llu unknown_region_words=%llu nonfinite_effective=%llu nonfinite_padding=%llu nonfinite_unknown_region=%llu first_nonfinite_index=%llu first_nonfinite_kind=%s first_nonfinite_region=%s fault_pc=%llu fault_at_target_pc=%u\n",
        terminal_summary_schema_sha256, unsigned(s.valid),
        (unsigned long long)accepted_samples, (unsigned long long)s.cycle, (unsigned long long)s.active_cycle,
        (unsigned long long)s.pc, (unsigned long long)s.completions, (unsigned long long)s.ng, (unsigned long long)s.context,
        (unsigned long long)s.result_last, (unsigned long long)s.result_error, mapping[s.mapping],
        (unsigned long long)s.words, (unsigned long long)s.finite, (unsigned long long)s.nan,
        (unsigned long long)s.positive_infinity, (unsigned long long)s.negative_infinity,
        (unsigned long long)s.effective_words, (unsigned long long)s.padding_words, (unsigned long long)s.unknown_region_words,
        (unsigned long long)s.nonfinite_effective, (unsigned long long)s.nonfinite_padding, (unsigned long long)s.nonfinite_unknown_region,
        (unsigned long long)s.first_nonfinite_index, kinds[s.first_kind], regions[s.first_region], (unsigned long long)fault_pc, unsigned(fault_pc==1));
}
inline TerminalSummary classify_terminal(const VHostBlockTopV4& top, const Sample& current,
                                         std::uint64_t pc) noexcept {
    TerminalSummary s;
    s.valid=true; s.cycle=current.cycle; s.active_cycle=current.active_cycle;
    s.pc=pc; s.completions=current.completions; s.ng=current.values[103]; s.context=current.values[110];
    s.result_last=current.values[111]; s.result_error=current.values[112];
    const auto cols=s.ng<1536 ? (1536-s.ng<160 ? 1536-s.ng : 160) : 0;
    const bool supported=s.ng<1536 && s.ng%160==0 && s.context<(cols+31)/32;
    s.mapping=supported ? 1 : 2;
    for (std::size_t i=0; i<4096; ++i) {
        const std::uint32_t bits=readonly_terminal_finite_access::word(top,i);
        const auto r=i/256, c=i%256;
        const auto m=c%128, n=s.ng+32*s.context+16*(c/128)+r;
        const unsigned region=!supported ? 3 : ((m<128 && n<1536 && n<s.ng+cols) ? 1 : 2);
        ++s.words;
        if (region==1) ++s.effective_words;
        else if (region==2) ++s.padding_words;
        else ++s.unknown_region_words;
        if ((bits & 0x7f800000U) != 0x7f800000U) { ++s.finite; continue; }
        const unsigned kind=(bits & 0x007fffffU) ? 1 : ((bits & 0x80000000U) ? 3 : 2);
        if (kind==1) ++s.nan;
        else if (kind==2) ++s.positive_infinity;
        else ++s.negative_infinity;
        if (region==1) ++s.nonfinite_effective;
        else if (region==2) ++s.nonfinite_padding;
        else ++s.nonfinite_unknown_region;
        if (s.first_nonfinite_index==4096) { s.first_nonfinite_index=i; s.first_kind=kind; s.first_region=region; }
    }
    return s;
}
class Collector {
    TerminalSummary terminal{};
    std::uint64_t terminal_samples=0;
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
                print_terminal_summary(terminal,terminal_samples,top.io_pc);
                std::fflush(stdout);
            }
        } else {
            if (top.io_pc==1 && completions==1 && current.values[107]==0 && current.values[108]!=0 && current.values[109]!=0) {
                terminal=classify_terminal(top,current,top.io_pc);
                ++terminal_samples;
            }
            previous=current;
            previous_valid=true;
        }
    }
};
}

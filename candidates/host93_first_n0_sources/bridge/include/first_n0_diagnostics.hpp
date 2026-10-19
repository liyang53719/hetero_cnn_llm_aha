#pragma once
#include <cstddef>
#include <string_view>
namespace canonical_runtime_v1 {
// Observation only. The driver overwrites this before model creation; never reads
// it to select model, input, arithmetic, clock, commit, ACK or authority behavior.
enum class RunPhase { INPUT_LOAD, READY, MODEL_ADMISSION, RTL_N0, OUTPUT };
enum class SafeCode {
    UNMAPPED, ACK0_COMPLETE, CYCLE_BUDGET, ALLOCATION_LIMIT, OUTPUT_DIRECTORY,
    OUTPUT_WRITE, OUTPUT_REPORT, OUTPUT_STDOUT, CLI_ARGUMENT_COUNT,
    CLI_INPUT_ROOT, CLI_OUTPUT_ROOT, CLI_PARENT_TRAVERSAL,
#define FIRST_N0_DIAGNOSTIC(CODE,TEXT) CODE,
#include "first_n0_diagnostic_codes.inc"
#undef FIRST_N0_DIAGNOSTIC
};
inline const char* phase_name(RunPhase phase)noexcept {
    switch(phase) {
        case RunPhase::INPUT_LOAD:return "INPUT_LOAD";
        case RunPhase::READY:return "READY";
        case RunPhase::MODEL_ADMISSION:return "MODEL_ADMISSION";
        case RunPhase::RTL_N0:return "RTL_N0";
        case RunPhase::OUTPUT:return "OUTPUT";
    }
    return "MODEL_ADMISSION"; // unreachable from the fixed producer, no raw enum leak
}
inline const char* code_name(SafeCode code)noexcept {
    switch(code) {
#define NAMED(CODE) case SafeCode::CODE:return #CODE;
        NAMED(UNMAPPED);NAMED(ACK0_COMPLETE);NAMED(CYCLE_BUDGET);NAMED(ALLOCATION_LIMIT);
        NAMED(OUTPUT_DIRECTORY);NAMED(OUTPUT_WRITE);NAMED(OUTPUT_REPORT);NAMED(OUTPUT_STDOUT);
        NAMED(CLI_ARGUMENT_COUNT);NAMED(CLI_INPUT_ROOT);NAMED(CLI_OUTPUT_ROOT);NAMED(CLI_PARENT_TRAVERSAL);
#undef NAMED
#define FIRST_N0_DIAGNOSTIC(CODE,TEXT) case SafeCode::CODE:return #CODE;
#include "first_n0_diagnostic_codes.inc"
#undef FIRST_N0_DIAGNOSTIC
    }
    return "UNMAPPED";
}
inline SafeCode exact_exception_code(const char* what)noexcept {
    if(!what)return SafeCode::UNMAPPED;
    std::size_t size=0;while(size<=192&&what[size]!='\0')++size;
    if(size>192)return SafeCode::UNMAPPED;
    const std::string_view actual(what,size);
#define FIRST_N0_DIAGNOSTIC(CODE,TEXT) if(actual==std::string_view(TEXT))return SafeCode::CODE;
#include "first_n0_diagnostic_codes.inc"
#undef FIRST_N0_DIAGNOSTIC
    return SafeCode::UNMAPPED;
}
}

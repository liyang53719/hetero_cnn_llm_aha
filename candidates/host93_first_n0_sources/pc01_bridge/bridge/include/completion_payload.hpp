// SOURCE ONLY: decode the actual HostBlockCommands completion wire format.
// HostBlockCommands.scala:31,180: UInt(56.W), then
// Cat(completionCommand(55,40),status,completionCommand(10,8),completionPc.pad(29)).
#pragma once
#include <cstdint>
#include <stdexcept>

namespace canonical_host_wiring_v1 {

struct CompletionPayload {
    std::uint32_t pc;       // raw bits 28:0; preserve all 29 bits for checking
    std::uint8_t owner;     // raw bits 31:29
    std::uint8_t status;    // raw bits 39:32
    std::uint16_t signal;   // raw bits 55:40
};

inline CompletionPayload decode_completion(std::uint64_t raw) {
    if ((raw >> 56) != 0)
        throw std::invalid_argument("completion payload exceeds 56 bits");
    return CompletionPayload{
        static_cast<std::uint32_t>(raw & 0x1fffffffULL),
        static_cast<std::uint8_t>((raw >> 29) & 0x7ULL),
        static_cast<std::uint8_t>((raw >> 32) & 0xffULL),
        static_cast<std::uint16_t>((raw >> 40) & 0xffffULL)
    };
}

// This checks payload content only, not completion.valid/ready, edge retirement,
// an accepted launch/job, owner-done, committed B responses, or publication.
// The raw wire contains NO epoch or owner tag. Those must later be validated
// against retained accepted-launch/job identity, never inferred from this word.
// No authority or success token is constructed here.
inline CompletionPayload require_pc0_completion_payload(std::uint64_t raw) {
    const auto decoded = decode_completion(raw);
    if (decoded.pc != 0)
        throw std::invalid_argument("completion payload is not PC0");
    if (decoded.owner != 3)
        throw std::invalid_argument("completion payload owner is not SFU_CGRA");
    if (decoded.status != 0)
        throw std::invalid_argument("completion payload status is not zero");
    if (decoded.signal != 1)
        throw std::invalid_argument("completion payload signal is not one");
    return decoded;
}

inline CompletionPayload require_pc1_completion_payload(std::uint64_t raw) {
    const auto decoded=decode_completion(raw);
    if(decoded.pc!=1||decoded.owner!=2||decoded.status!=0||decoded.signal!=2)
        throw std::invalid_argument("PC1 completion payload identity");
    return decoded;
}

} // namespace canonical_host_wiring_v1

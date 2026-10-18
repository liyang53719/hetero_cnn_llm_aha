// New per-input stream interface. SOURCE ONLY; canonical identity/launch UNBOUND.
// Not a reconstruction of any missing wire framing or former container digest.
#pragma once
#include "initialization_ram.hpp"
#include "sha256.hpp"
#include <array>
#include <istream>
#include <string>
#include <vector>

namespace same_buffer_loader_v1 {
using canonical_load_storage_v2::ConstBytes;
using canonical_load_storage_v2::InputSpan;
using canonical_load_storage_v2::InitializationRam;

// This is a TRUSTED caller parameter, never read from an input stream.
// The caller must independently authenticate the entire ordered specification.
struct ExpectedInput {
    InputSpan span;
    Sha256::Digest sha256;
};
class LoadError final : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// Single-threaded. Owns the RAM; never exposes its staging or sealing methods.
// No mutation callbacks, injected hash function, or public readiness boolean.
class SameBufferLoader final {
    enum class Phase { Filling, TokenIssued, ViewIssued, Poisoned };
    const std::vector<ExpectedInput> expected_;
    InitializationRam ram_;
    Phase phase_ = Phase::Filling;
    std::size_t next_ = 0;

    static void require(bool value, const char* message) {
        if (!value) throw LoadError(message);
    }
    static std::vector<ExpectedInput> copy_expected(const std::vector<ExpectedInput>& inputs) {
        require(!inputs.empty() && inputs.size() <= InitializationRam::maximum_inputs,
                "bounded nonempty trusted expected list required");
        for (const auto& input : inputs)
            require(!input.span.name.empty() && input.span.name.size() <= 128,
                    "trusted expected name must contain 1 to 128 bytes");
        // Always COPY nested std::string/vector/array, including rvalue callers.
        return std::vector<ExpectedInput>(inputs);
    }
    static std::vector<InputSpan> spans(const std::vector<ExpectedInput>& inputs) {
        std::vector<InputSpan> result;
        for (const auto& input : inputs) result.push_back(input.span);
        return result;
    }
    template<class Function>
    auto checked(Function&& function) -> decltype(function()) {
        try {
            require(phase_ != Phase::Poisoned, "loader permanently poisoned");
            return function();
        } catch (...) {
            phase_ = Phase::Poisoned;
            ram_.invalidate();
            throw;
        }
    }
    void verify_actual_ram() {
        for (std::size_t i = 0; i < expected_.size(); ++i) {
            const auto& input = expected_[i];
            const auto actual = ram_.read_input_span(i, 0, input.span.bytes);
            require(Sha256::hash(actual.data, actual.size) == input.sha256,
                    "actual same-RAM SHA-256 mismatch");
        }
    }
    ConstBytes read_ready(std::size_t index, std::uint64_t offset, std::uint64_t count) {
        return checked([&]() -> ConstBytes {
            require(phase_ == Phase::ViewIssued, "ready view no longer valid");
            return ram_.read_input_span(index, offset, count);
        });
    }
    void reverify_ready() {
        checked([&] {
            require(phase_ == Phase::ViewIssued, "ready view no longer valid");
            verify_actual_ram();
        });
    }
public:
    static constexpr std::size_t chunk_bytes = 64 * 1024;

    class ReadyToken final {
        friend class SameBufferLoader;
        SameBufferLoader* owner_;
        explicit ReadyToken(SameBufferLoader& owner) noexcept : owner_(&owner) {}
    public:
        ReadyToken(const ReadyToken&) = delete;
        ReadyToken& operator=(const ReadyToken&) = delete;
        ReadyToken(ReadyToken&&) = delete;
        ReadyToken& operator=(ReadyToken&&) = delete;
    };
    class ReadOnlyView final {
        friend class SameBufferLoader;
        SameBufferLoader& owner_;
        explicit ReadOnlyView(SameBufferLoader& owner) noexcept : owner_(owner) {}
    public:
        ReadOnlyView(const ReadOnlyView&) = delete;
        ReadOnlyView& operator=(const ReadOnlyView&) = delete;
        ReadOnlyView(ReadOnlyView&&) = delete;
        ReadOnlyView& operator=(ReadOnlyView&&) = delete;
        ConstBytes read(std::size_t index, std::uint64_t offset, std::uint64_t count) const {
            return owner_.read_ready(index, offset, count);
        }
        // Explicit integrity boundary, O(total declared bytes), never per beat.
        // Cannot revoke already returned pointers or defend against data races.
        void reverify() const { owner_.reverify_ready(); }
    };

    SameBufferLoader(std::uint64_t base, std::uint64_t bytes, std::uint64_t byte_budget,
                     const std::vector<ExpectedInput>& trusted_expected)
        : expected_(copy_expected(trusted_expected)),
          ram_(base, bytes, byte_budget, spans(expected_)) {}
    SameBufferLoader(const SameBufferLoader&) = delete;
    SameBufferLoader& operator=(const SameBufferLoader&) = delete;
    SameBufferLoader(SameBufferLoader&&) = delete;
    SameBufferLoader& operator=(SameBufferLoader&&) = delete;

    // Exactly one independently framed stream per expected input, in order.
    // Stream must start good, report full chunk reads and exact terminal EOF.
    // EOF probe uses read(1): ordinary eofbit|failbit is required, badbit forbidden.
    // Any thrown exception, including an EOF exception mask, poisons this loader.
    void load_next(const std::string& name, std::istream& input) {
        checked([&] {
            require(phase_ == Phase::Filling, "input after readiness");
            require(next_ < expected_.size(), "too many input streams");
            const auto& wanted = expected_[next_];
            require(name == wanted.span.name, "input name or order mismatch");
            require(input.good(), "input stream not initially good");
            Sha256 stream_hash;
            std::array<std::uint8_t, chunk_bytes> chunk{};
            std::uint64_t offset = 0;
            while (offset < wanted.span.bytes) {
                const auto left = wanted.span.bytes - offset;
                const auto count = static_cast<std::size_t>(left < chunk.size() ? left : chunk.size());
                input.read(reinterpret_cast<char*>(chunk.data()), static_cast<std::streamsize>(count));
                require(input.good() && input.gcount() == static_cast<std::streamsize>(count),
                        "input stream short read or bad state");
                ram_.stage_input(wanted.span.name, offset, {chunk.data(), count});
                stream_hash.update(chunk.data(), count);
                offset += count;
            }
            char trailing = 0;
            input.read(&trailing, 1);
            require(input.gcount() == 0 && input.eof() && input.fail() && !input.bad(),
                    "input stream trailing bytes or missing strict EOF");
            require(stream_hash.finish() == wanted.sha256, "input SHA-256 mismatch");
            ++next_;
        });
    }
    ReadyToken finish() {
        return checked([&]() -> ReadyToken {
            require(phase_ == Phase::Filling, "finish is one-shot");
            require(next_ == expected_.size(), "missing input streams");
            ram_.seal_coverage();
            verify_actual_ram();
            phase_ = Phase::TokenIssued;
            return ReadyToken(*this);
        });
    }
    // Token can be redeemed exactly once and only by the issuing loader.
    // Loader must outlive token, view, and every returned ConstBytes pointer.
    ReadOnlyView take_ready(ReadyToken& token) {
        return checked([&]() -> ReadOnlyView {
            require(phase_ == Phase::TokenIssued && token.owner_ == this,
                    "wrong, stale, or consumed ready token");
            verify_actual_ram();
            token.owner_ = nullptr;
            phase_ = Phase::ViewIssued;
            return ReadOnlyView(*this);
        });
    }
};
} // namespace same_buffer_loader_v1

// New independent source primitive. UNCOMPILED; not the missing HostMemory.
// Coverage sealing is not canonical hash/receipt verification or launch readiness.
#pragma once
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace canonical_load_storage_v1 {
struct ConstBytes {
    const std::uint8_t* data;
    std::size_t size;
};
struct InputSpan {
    std::string name;
    std::uint64_t base;
    std::uint64_t bytes;
};
class StorageError final : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// Single-threaded and noncopyable. One contiguous payload allocation and a
// separate byte-per-byte initialized mask; neither allocation ever resizes.
// InputSpan is a caller-supplied initialization whitelist, not a DDR permission.
class InitializationRam final {
    enum class State { Filling, CoverageSealed, Poisoned };
    mutable State state_ = State::Filling;
    const std::uint64_t base_;
    const std::size_t capacity_;
    const std::vector<InputSpan> inputs_;
    std::vector<std::uint8_t> bytes_;
    std::vector<std::uint8_t> initialized_;

    static void require(bool condition, const char* message) {
        if (!condition) throw StorageError(message);
    }
    static std::size_t capacity(std::uint64_t base, std::uint64_t bytes,
                                std::uint64_t byte_budget) {
        require(bytes != 0 && bytes <= byte_budget && bytes <= maximum_bytes,
                "nonempty RAM extent must fit explicit budget and hard cap");
        require(bytes <= std::numeric_limits<std::size_t>::max(), "RAM size_t overflow");
        require(bytes <= std::numeric_limits<std::uint64_t>::max() - base,
                "RAM exclusive limit overflow");
        return static_cast<std::size_t>(bytes);
    }
    // Subtraction-first checks never form address + count before validation.
    static bool contains(std::uint64_t base, std::uint64_t bytes,
                         std::uint64_t address, std::uint64_t count) {
        return count != 0 && address >= base && address - base <= bytes &&
               count <= bytes - (address - base);
    }
    static void require_slice(const InputSpan& span, std::uint64_t offset,
                              std::uint64_t count) {
        require(count != 0 && offset <= span.bytes && count <= span.bytes - offset,
                "nonempty input slice outside declared span");
    }
    template<class Function>
    auto checked(Function&& function) const -> decltype(function()) {
        try {
            require(state_ != State::Poisoned, "RAM permanently poisoned");
            return function();
        } catch (...) {
            state_ = State::Poisoned;
            throw;
        }
    }
    const InputSpan& named(const std::string& name) const {
        for (const auto& span : inputs_) if (span.name == name) return span;
        throw StorageError("unknown initialization input name");
    }
    void require_initialized(std::size_t start, std::size_t count) const {
        for (std::size_t i = 0; i < count; ++i)
            require(initialized_[start + i] == 1, "uninitialized RAM byte");
    }
    ConstBytes input_view(const InputSpan& span, std::uint64_t offset,
                          std::uint64_t count) const {
        require_slice(span, offset, count);
        const auto start = static_cast<std::size_t>(span.base - base_ + offset);
        const auto size = static_cast<std::size_t>(count);
        require_initialized(start, size);
        return {bytes_.data() + start, size};
    }
public:
    // Bounds metadata alone never allocates or grants access to resident DDR.
    // The cap is a resource bound; byte_budget lets the caller choose less.
    static constexpr std::uint64_t maximum_bytes = 256ULL * 1024 * 1024;
    static constexpr std::size_t maximum_inputs = 64;

    InitializationRam(std::uint64_t base, std::uint64_t bytes,
                      std::uint64_t byte_budget, std::vector<InputSpan> inputs)
        : base_(base), capacity_(capacity(base, bytes, byte_budget)),
          inputs_(std::move(inputs)) {
        require(!inputs_.empty() && inputs_.size() <= maximum_inputs,
                "bounded nonempty initialization whitelist required");
        for (std::size_t i = 0; i < inputs_.size(); ++i) {
            const auto& a = inputs_[i];
            require(!a.name.empty(), "empty initialization input name");
            require(contains(base_, capacity_, a.base, a.bytes), "input outside RAM extent");
            for (std::size_t j = 0; j < i; ++j) {
                const auto& b = inputs_[j];
                require(a.name != b.name, "duplicate initialization input name");
                // Both exclusive limits are safe because both spans fit RAM.
                require(a.base >= b.base + b.bytes || b.base >= a.base + a.bytes,
                        "overlapping initialization input spans");
            }
        }
        // Invalid layout is rejected before either backing allocation.
        bytes_.resize(capacity_, 0);
        initialized_.resize(capacity_, 0);
    }
    InitializationRam(const InitializationRam&) = delete;
    InitializationRam& operator=(const InitializationRam&) = delete;
    InitializationRam(InitializationRam&&) = delete;
    InitializationRam& operator=(InitializationRam&&) = delete;

    // Source must refer to size readable bytes for the duration of this call.
    // The bytes are copied here; retaining or changing source cannot change RAM.
    void stage_input(const std::string& name, std::uint64_t offset, ConstBytes source) {
        checked([&] {
            require(state_ == State::Filling, "initialization after coverage seal");
            const auto& span = named(name);
            require(source.data != nullptr, "null initialization source");
            require(source.size <= capacity_, "initialization chunk exceeds RAM cap");
            require_slice(span, offset, source.size);
            const auto start = static_cast<std::size_t>(span.base - base_ + offset);
            // Validate the whole chunk before changing even its first byte.
            for (std::size_t i = 0; i < source.size; ++i)
                require(initialized_[start + i] == 0, "duplicate byte initialization");
            for (std::size_t i = 0; i < source.size; ++i) {
                bytes_[start + i] = source.data[i];
                initialized_[start + i] = 1;
            }
        });
    }
    // Coverage only. A future private wrapper must hash this actual sealed RAM,
    // validate the real loader receipt/EOF and retain its own readiness gate.
    void seal_coverage() {
        checked([&] {
            require(state_ == State::Filling, "coverage seal is one-shot");
            for (const auto& span : inputs_)
                require_initialized(static_cast<std::size_t>(span.base - base_),
                                    static_cast<std::size_t>(span.bytes));
            state_ = State::CoverageSealed;
        });
    }
    ConstBytes read_input_span(std::size_t index, std::uint64_t offset,
                               std::uint64_t count) const {
        return checked([&]() -> ConstBytes {
            require(state_ == State::CoverageSealed, "read before coverage seal");
            require(index < inputs_.size(), "input index outside whitelist");
            return input_view(inputs_[index], offset, count);
        });
    }
    ConstBytes read_input_address(std::uint64_t address, std::uint64_t count) const {
        return checked([&]() -> ConstBytes {
            require(state_ == State::CoverageSealed, "read before coverage seal");
            require(contains(base_, capacity_, address, count), "read outside RAM extent");
            for (const auto& span : inputs_)
                if (contains(span.base, span.bytes, address, count))
                    return input_view(span, address - span.base, count);
            throw StorageError("read crosses input boundary or enters undeclared bytes");
        });
    }
    // Irreversible failure hook for a future digest/receipt verifier. Previously
    // returned const views cannot be revoked: that wrapper must keep them private.
    void invalidate() noexcept { state_ = State::Poisoned; }
};
} // namespace canonical_load_storage_v1

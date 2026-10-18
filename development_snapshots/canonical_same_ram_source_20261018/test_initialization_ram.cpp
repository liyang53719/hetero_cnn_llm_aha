// Synthetic 64-byte RAM tests only. No canonical payload, model, EDA or bus.
#include "initialization_ram.hpp"
#include "v1_initialization_ram.hpp"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <iostream>
#include <new>

// Read-only allocation probe for mutation atomicity after poison. Production
// exposes no pre-seal view. These standard replacement operators allocate real
// memory normally; the probe records only the two tiny backing allocations.
namespace probe {
struct Allocation { void* pointer; std::size_t bytes; };
static Allocation captured[8]{};
static std::size_t count = 0;
static bool active = false;
void record(void* p, std::size_t n) noexcept {
    if (active && n == 64 && count < 8) captured[count++] = {p, n};
}
struct Capture {
    Capture() { count = 0; active = true; }
    ~Capture() { active = false; }
    void stop() { active = false; }
};
}
void* operator new(std::size_t n) {
    if (void* p = std::malloc(n ? n : 1)) { probe::record(p, n); return p; }
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

using canonical_load_storage_v2::ConstBytes;
using canonical_load_storage_v2::InitializationRam;
using canonical_load_storage_v2::InputSpan;
using canonical_load_storage_v2::StorageError;
static unsigned checks = 0;
static constexpr std::uint64_t base = 0x1000;

static void check(bool ok, const char* why) {
    ++checks;
    if (!ok) throw std::runtime_error(why);
}
template<class F> static void rejected(F&& operation) {
    ++checks;
    try { operation(); } catch (const StorageError&) { return; }
    throw std::runtime_error("operation unexpectedly accepted");
}
static std::vector<InputSpan> spans() {
    return {{"a", base + 8, 16}, {"b", base + 40, 8}};
}
static const std::array<std::uint8_t, 16> a_bytes{
    0x00,0x01,0x7f,0x80,0xff,0x10,0x20,0x30,
    0x40,0x50,0x60,0x70,0x90,0xa0,0xb0,0xc0};
static const std::array<std::uint8_t, 8> b_bytes{
    0xde,0xad,0xbe,0xef,0xaa,0x55,0x00,0xff};
static void fill(InitializationRam& ram) {
    ram.stage_input("a", 8, {a_bytes.data() + 8, 8});
    ram.stage_input("b", 0, {b_bytes.data(), b_bytes.size()});
    ram.stage_input("a", 0, {a_bytes.data(), 8});
}
struct Buffers { std::size_t data; std::size_t mask; };
static std::array<std::uint8_t, 64> snapshot(std::size_t allocation) {
    check(probe::count == 2, "expected exactly payload and mask 64-byte allocations");
    check(probe::captured[0].pointer != probe::captured[1].pointer, "distinct mask allocation");
    std::array<std::uint8_t, 64> out{};
    std::copy_n(static_cast<const std::uint8_t*>(probe::captured[allocation].pointer), 64, out.begin());
    return out;
}
static Buffers identify_partial_buffers() {
    std::array<std::uint8_t, 64> expected_data{}, expected_mask{};
    std::copy_n(a_bytes.data() + 4, 4, expected_data.begin() + 12);
    std::fill_n(expected_mask.begin() + 12, 4, 1);
    const auto first = snapshot(0), second = snapshot(1);
    if (first == expected_data && second == expected_mask) return {0, 1};
    if (second == expected_data && first == expected_mask) return {1, 0};
    throw std::runtime_error("payload/mask allocation identity ambiguous");
}
static Buffers identify_sealed_buffers(ConstBytes view) {
    check(probe::count == 2, "expected exactly two backing allocations");
    for (std::size_t i = 0; i != 2; ++i)
        if (view.data == static_cast<const std::uint8_t*>(probe::captured[i].pointer) + 8)
            return {i, 1 - i};
    throw std::runtime_error("sealed view is not from captured backing allocation");
}
static void poison_closed(InitializationRam& ram) {
    rejected([&] { ram.seal_coverage(); });
    rejected([&] { ram.stage_input("a", 0, {a_bytes.data(), 1}); });
    rejected([&] { (void)ram.read_input_span(0, 0, 1); });
    rejected([&] { (void)ram.read_input_address(base + 8, 1); });
}
static void alias_regressions() {
    // Safe positive control of v1's real bug. No out-of-range memory access:
    // caller alias shrinks the required extent after only one of two bytes loads.
    { std::vector<canonical_load_storage_v1::InputSpan> inputs{{"x", 0, 2}};
      auto& alias = inputs[0];
      canonical_load_storage_v1::InitializationRam old(0, 8, 8, std::move(inputs));
      old.stage_input("x", 0, {a_bytes.data(), 1}); alias.bytes = 1;
      old.seal_coverage();
      check(old.read_input_span(0, 0, 1).size == 1, "v1 positive control not observed"); }
    // Exact same operation must leave v2's original two-byte obligation intact.
    { std::vector<InputSpan> inputs{{"x", 0, 2}}; auto& alias = inputs[0];
      InitializationRam ram(0, 8, 8, std::move(inputs));
      ram.stage_input("x", 0, {a_bytes.data(), 1}); alias.bytes = 1;
      rejected([&] { ram.seal_coverage(); });
      rejected([&] { (void)ram.read_input_span(0, 0, 1); }); }
    for (unsigned mode = 0; mode != 5; ++mode) {
        const std::string original_name(80, 'n'); // exercise owned heap string too
        std::vector<InputSpan> inputs{{original_name, base + 8, 16}, {"b", base + 40, 8}};
        auto& reference = inputs[0]; auto* pointer = &inputs[0];
        char* characters = inputs[0].name.data();
        InitializationRam ram(base, 64, 64, std::move(inputs));
        if (mode == 0) pointer->base = base + 9;
        if (mode == 1) reference.bytes = 1;
        if (mode == 2) characters[0] = 'z';
        if (mode == 3) reference.name = "renamed";
        if (mode == 4) inputs.clear(); // caller destroys its vector elements
        ram.stage_input(original_name, 0, {a_bytes.data(), a_bytes.size()});
        ram.stage_input("b", 0, {b_bytes.data(), b_bytes.size()}); ram.seal_coverage();
        const auto actual = ram.read_input_address(base + 8, a_bytes.size());
        check(std::equal(a_bytes.begin(), a_bytes.end(), actual.data),
              "caller metadata/name alias changed internal whitelist");
    }
}
static void construction_cases() {
    rejected([] { InitializationRam x(base, 0, 64, spans()); });
    rejected([] { InitializationRam x(base, 64, 63, spans()); });
    rejected([] { InitializationRam x(base, InitializationRam::maximum_bytes + 1,
                                    InitializationRam::maximum_bytes + 1, spans()); });
    rejected([] { InitializationRam x(UINT64_MAX - 31, 64, 64, spans()); });
    rejected([] { InitializationRam x(base, 64, 64, {}); });
    rejected([] { InitializationRam x(base, 64, 64, {{"a", base, 0}}); });
    rejected([] { InitializationRam x(base, 64, 64, {{"", base, 1}}); });
    rejected([] { InitializationRam x(base, 64, 64, {{std::string(129, 'n'), base, 1}}); });
    rejected([] { InitializationRam x(base, 64, 64, {{"a", base - 1, 1}}); });
    rejected([] { InitializationRam x(base, 64, 64, {{"a", base + 63, 2}}); });
    rejected([] { InitializationRam x(base, 64, 64, {{"a", base, 4}, {"a", base + 8, 4}}); });
    rejected([] { InitializationRam x(base, 64, 64, {{"a", base, 4}, {"b", base + 3, 4}}); });
    rejected([] { InitializationRam x(base, 64, 64, std::vector<InputSpan>(65, {"a", base, 1})); });
}
static void initialization_rejections() {
    for (unsigned mode = 0; mode != 7; ++mode) {
        InitializationRam ram(base, 64, 64, spans());
        rejected([&] {
            if (mode == 0) ram.stage_input("unknown", 0, {a_bytes.data(), 1});
            if (mode == 1) ram.stage_input("a", 0, {nullptr, 1});
            if (mode == 2) ram.stage_input("a", 0, {a_bytes.data(), 0});
            if (mode == 3) ram.stage_input("a", 0, {a_bytes.data(), 65});
            if (mode == 4) ram.stage_input("a", UINT64_MAX, {a_bytes.data(), 1});
            if (mode == 5) ram.stage_input("a", 15, {a_bytes.data(), 2});
            if (mode == 6) ram.stage_input("b", 8, {a_bytes.data(), 1});
        });
        poison_closed(ram);
    }
}
static void partial_failure_atomicity() {
    for (unsigned mode = 0; mode != 2; ++mode) {
        auto inputs = spans();
        probe::Capture capture;
        InitializationRam ram(base, 64, 64, std::move(inputs));
        capture.stop();
        ram.stage_input("a", 4, {a_bytes.data() + 4, 4});
        const auto buffers = identify_partial_buffers();
        const auto old_data = snapshot(buffers.data), old_mask = snapshot(buffers.mask);
        check(std::count(old_mask.begin(), old_mask.end(), 1) == 4, "exact initialized mask");
        rejected([&] {
            // mode 0 encounters four uninitialized bytes BEFORE a duplicate;
            // a write-as-you-check loop would visibly corrupt this prefix.
            if (mode == 0) ram.stage_input("a", 0, {a_bytes.data(), 8});
            else ram.stage_input("a", 14, {a_bytes.data(), 4});
        });
        check(snapshot(buffers.data) == old_data, "rejected chunk changed payload");
        check(snapshot(buffers.mask) == old_mask, "rejected chunk changed mask");
        poison_closed(ram);
    }
}
static void seal_and_read_rejections() {
    { InitializationRam ram(base, 64, 64, spans());
      rejected([&] { ram.seal_coverage(); }); poison_closed(ram); }
    { InitializationRam ram(base, 64, 64, spans());
      ram.stage_input("a", 0, {a_bytes.data(), a_bytes.size()});
      ram.stage_input("b", 0, {b_bytes.data(), b_bytes.size() - 1});
      rejected([&] { ram.seal_coverage(); }); poison_closed(ram); }
    { InitializationRam ram(base, 64, 64, spans()); fill(ram);
      rejected([&] { (void)ram.read_input_span(0, 0, 1); }); poison_closed(ram); }
    for (unsigned mode = 0; mode != 9; ++mode) {
        InitializationRam ram(base, 64, 64, spans()); fill(ram); ram.seal_coverage();
        rejected([&] {
            if (mode == 0) (void)ram.read_input_span(2, 0, 1);
            if (mode == 1) (void)ram.read_input_span(0, 16, 1);
            if (mode == 2) (void)ram.read_input_span(0, 0, 0);
            if (mode == 3) (void)ram.read_input_span(0, UINT64_MAX, 1);
            if (mode == 4) (void)ram.read_input_address(base + 7, 1);
            if (mode == 5) (void)ram.read_input_address(base + 23, 18);
            if (mode == 6) (void)ram.read_input_address(base + 64, 1);
            if (mode == 7) (void)ram.read_input_address(UINT64_MAX, UINT64_MAX);
            if (mode == 8) (void)ram.read_input_address(base + 8, 0);
        });
        poison_closed(ram);
    }
    { InitializationRam ram(base, 8, 8, {{"a", base, 4}, {"b", base + 4, 4}});
      ram.stage_input("a", 0, {a_bytes.data(), 4}); ram.stage_input("b", 0, {b_bytes.data(), 4});
      ram.seal_coverage(); rejected([&] { (void)ram.read_input_address(base, 8); }); poison_closed(ram); }
}
static std::string hex(ConstBytes view) {
    static const char digits[] = "0123456789abcdef";
    std::string result;
    for (std::size_t i = 0; i != view.size; ++i) {
        result += digits[view.data[i] >> 4]; result += digits[view.data[i] & 15];
    }
    return result;
}
static std::pair<std::string, std::string> same_allocation_and_lifecycle() {
    auto inputs = spans();
    probe::Capture capture;
    InitializationRam ram(base, 64, 64, std::move(inputs));
    capture.stop();
    auto source = a_bytes;
    ram.stage_input("a", 0, {source.data(), source.size()}); source.fill(0xee);
    ram.stage_input("b", 0, {b_bytes.data(), b_bytes.size()}); ram.seal_coverage();
    const auto av = ram.read_input_span(0, 0, 16), bv = ram.read_input_span(1, 0, 8);
    const auto buffers = identify_sealed_buffers(av);
    check(bv.data == static_cast<const std::uint8_t*>(probe::captured[buffers.data].pointer) + 40,
          "both inputs share original payload allocation");
    check(ram.read_input_address(base + 9, 3).data == av.data + 1, "address/index view identity");
    check(std::equal(a_bytes.begin(), a_bytes.end(), av.data), "input copy differs after source mutation");
    const auto data = snapshot(buffers.data), mask = snapshot(buffers.mask);
    check(std::count(mask.begin(), mask.end(), 1) == 24, "guards remain uninitialized");
    const auto output = std::make_pair(hex(av), hex(bv));
    rejected([&] { ram.stage_input("a", 0, {b_bytes.data(), 8}); });
    check(snapshot(buffers.data) == data && snapshot(buffers.mask) == mask, "post-seal write changed storage");
    poison_closed(ram);
    // Existing const views are stable but deliberately not revocable.
    check(hex(av) == output.first, "failed write changed existing view");
    { InitializationRam x(base, 64, 64, spans()); fill(x); x.seal_coverage();
      rejected([&] { x.seal_coverage(); }); poison_closed(x); }
    { InitializationRam x(base, 64, 64, spans()); fill(x); x.seal_coverage();
      x.invalidate(); poison_closed(x); }
    return output;
}
int main() {
    try {
        alias_regressions(); construction_cases(); initialization_rejections(); partial_failure_atomicity();
        seal_and_read_rejections(); const auto actual = same_allocation_and_lifecycle();
        std::cout << "{\"status\":\"PASS\",\"checks\":" << checks
                  << ",\"v1_alias_bypass_observed\":true,\"actual_a_hex\":\"" << actual.first
                  << "\",\"actual_b_hex\":\"" << actual.second << "\"}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n'; return 1;
    }
}

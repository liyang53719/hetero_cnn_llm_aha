// Synthetic single-TU tests: SOURCE ONLY. No native execution claimed.
#include "same_buffer_loader.hpp"
#include <algorithm>
#include <cstdlib>
#include <new>
#include <iostream>
#include <sstream>
#include <streambuf>
#include <type_traits>
#include <utility>

// Test-only standard allocation probe. Never guesses class layout or allocation
// order. Capture only construction-time 64-byte allocations; require exactly
// two, then identify the payload and mask by their full independent contents.
namespace probe {
struct Allocation { void* pointer; bool live; };
Allocation captured[8]{};
std::size_t count = 0;
bool active = false;
void record(void* p, std::size_t size) noexcept {
    if (active && size == 64) {
        if (count < 8) captured[count] = {p, true};
        ++count;
    }
}
void revoke(void* p) noexcept {
    for (std::size_t i = 0; i < count && i < 8; ++i)
        if (captured[i].pointer == p && captured[i].live) captured[i].live = false;
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
void operator delete(void* p) noexcept { probe::revoke(p); std::free(p); }
void operator delete(void* p, std::size_t) noexcept { probe::revoke(p); std::free(p); }

using namespace same_buffer_loader_v1;
namespace {
std::size_t checks = 0;
void check(bool value, const char* why) {
    ++checks;
    if (!value) throw std::runtime_error(why);
}
template<class Function> void rejects(Function&& fn) {
    bool thrown = false;
    try { fn(); } catch (const std::exception&) { thrown = true; }
    check(thrown, "expected exception was not thrown");
}
std::uint8_t nibble(char c) {
    if (c >= '0' && c <= '9') return static_cast<std::uint8_t>(c - '0');
    if (c >= 'a' && c <= 'f') return static_cast<std::uint8_t>(c - 'a' + 10);
    throw std::runtime_error("invalid fixed test digest");
}
Sha256::Digest digest(const std::string& hex) {
    check(hex.size() == 64, "fixed digest size");
    Sha256::Digest out{};
    for (std::size_t i = 0; i < out.size(); ++i)
        out[i] = static_cast<std::uint8_t>(16 * nibble(hex[2*i]) + nibble(hex[2*i+1]));
    return out;
}
const char* empty_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
const char* abc_sha = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
const char* xyz_sha = "3608bca1e44ea6c4d268eb6db02260269892c0b42b86bbf1e77a6fa16c3c9282";
std::vector<ExpectedInput> specs() {
    return {{{"a", 0x1000, 3}, digest(abc_sha)},
            {{"b", 0x1008, 3}, digest(xyz_sha)}};
}
void load_both(SameBufferLoader& loader) {
    std::istringstream a("abc"), b("xyz");
    loader.load_next("a", a); loader.load_next("b", b);
    check(a.eof() && a.fail() && !a.bad(), "first exact EOF state");
    check(b.eof() && b.fail() && !b.bad(), "second exact EOF state");
}
void poisoned(SameBufferLoader& loader) {
    rejects([&] { (void)loader.finish(); });
    std::istringstream valid("abc");
    rejects([&] { loader.load_next("a", valid); });
}
std::string pattern(std::size_t size) {
    std::string result(size, '\0');
    for (std::size_t i = 0; i < size; ++i)
        result[i] = static_cast<char>((131 * i + 17) & 255);
    return result;
}
const std::uint8_t* bytes(const std::string& value) {
    return reinterpret_cast<const std::uint8_t*>(value.data());
}
struct Vector { std::size_t size; const char* sha; };
// Fixed independent Python hashlib vectors; formula documented in TEST_PLAN.json.
const Vector vectors[] = {
    {1, "4a64a107f0cb32536e5bce6c98c393db21cca7f4ea187ba8c4dca8b51d4ea80a"},
    {55, "59aaae80b8e7958f5757b4ac9274f1fd57ec0dc7aa8349319102316781b92006"},
    {56, "dca902d31487ffab357ce36cc5abc6947fbb69127ec04c468ba5687268c4bf7c"},
    {63, "b8e655e9e7ad413b96f0a371eb1d6db71dcca27f4eee35892517cbe4bfaa6f9a"},
    {64, "e5146be62accc56709594cb45c651b361df94f622cbb09b91ea3ca7a2060bd53"},
    {65, "4b6c6774f0cbcd776a90e187b9494e04ca880c0afe3ea1c5cad51c8bbcb41f74"},
    {127, "b4f5398bf618d741f2ab0f6e2fcde06f4949c20d476b5f6e1d4bf8618bc8973a"},
    {128, "ed045c7c319e0c9286e1dea21c80bfd4a08eca43e02e13ee8a7a2c8b4b2baec9"},
    {129, "d6f2fca0407b3f98c9ce29ae92a6cdf489506450fdbb29172f6b18987bc685db"},
    {65535, "c6a1a875a56160beba80d5233caaf8cc4532780b37715889df1add7fc47c8282"},
    {65536, "d8f32a3b4c195f65444e342b0c61bdaf114802e84ab7821a1f88e3f66ea15100"},
    {65537, "65d80b2b0f0120bda1628b3749982090e058d2d9f4a5fad1bc70250b49bc4e96"},
};
void test_sha256() {
    check(Sha256::hash(nullptr, 0) == digest(empty_sha), "empty SHA-256");
    const std::string abc = "abc";
    check(Sha256::hash(bytes(abc), abc.size()) == digest(abc_sha), "abc SHA-256");
    Sha256 million;
    const std::string a1000(1000, 'a');
    for (unsigned i = 0; i < 1000; ++i) million.update(bytes(a1000), a1000.size());
    check(million.finish() == digest("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"),
          "million a SHA-256");
    rejects([&] { (void)million.finish(); });
    rejects([&] { million.update(nullptr, 0); });
    Sha256 invalid;
    rejects([&] { invalid.update(nullptr, 1); });
    for (const auto& v : vectors) {
        const auto data = pattern(v.size);
        const auto expected = digest(v.sha);
        check(Sha256::hash(bytes(data), data.size()) == expected, "fixed boundary SHA-256");
        for (const std::size_t chunk : {1U, 7U, 55U, 64U, 65536U}) {
            Sha256 split;
            for (std::size_t offset = 0; offset < data.size();) {
                const auto n = std::min(chunk, data.size() - offset);
                split.update(bytes(data) + offset, n); offset += n;
            }
            check(split.finish() == expected, "incremental boundary SHA-256");
        }
    }
}
class RecordingBuf : public std::stringbuf {
public:
    std::vector<std::streamsize> requests;
    explicit RecordingBuf(const std::string& data) : std::stringbuf(data) {}
    std::streamsize xsgetn(char* out, std::streamsize n) override {
        requests.push_back(n);
        return std::stringbuf::xsgetn(out, n);
    }
};
class ThrowBuf : public std::streambuf {
    std::streamsize xsgetn(char*, std::streamsize) override {
        throw std::runtime_error("synthetic stream failure");
    }
};
class ShortBuf : public std::stringbuf {
public:
    ShortBuf() : std::stringbuf("abc") {}
    std::streamsize xsgetn(char* out, std::streamsize n) override {
        return std::stringbuf::xsgetn(out, n > 1 ? n - 1 : n);
    }
};
class BadAtEofBuf : public std::stringbuf {
public:
    std::istream* stream = nullptr;
    BadAtEofBuf() : std::stringbuf("abc") {}
    std::streamsize xsgetn(char* out, std::streamsize n) override {
        const auto got = std::stringbuf::xsgetn(out, n);
        if (got == 0 && stream != nullptr) stream->setstate(std::ios::badbit);
        return got;
    }
};
void test_chunking_and_binary() {
    for (const auto& v : vectors) {
        const auto data = pattern(v.size);
        const std::vector<ExpectedInput> expected{{{"pattern", 0x2000, v.size}, digest(v.sha)}};
        SameBufferLoader loader(0x2000, v.size, v.size, expected);
        RecordingBuf buf(data); std::istream stream(&buf);
        loader.load_next("pattern", stream);
        auto token = loader.finish(); auto ready = loader.take_ready(token);
        const auto actual = ready.read(0, 0, v.size);
        check(actual.size == v.size && std::equal(actual.data, actual.data + actual.size, bytes(data)),
              "actual same-buffer fixed binary data");
        const auto second = ready.read(0, 0, v.size);
        check(second.data == actual.data, "read view points to same RAM");
        check(buf.requests.back() == 1, "strict EOF probe requested");
        check(buf.requests.size() == (v.size + SameBufferLoader::chunk_bytes - 1) /
              SameBufferLoader::chunk_bytes + 1, "bounded chunk request count");
        for (const auto n : buf.requests)
            check(n > 0 && n <= static_cast<std::streamsize>(SameBufferLoader::chunk_bytes),
                  "no unbounded stream read");
        ready.reverify();
    }
}
void test_good_view_and_alias() {
    SameBufferLoader loader(0x1000, 16, 16, specs()); load_both(loader);
    auto token = loader.finish(); auto view = loader.take_ready(token);
    const auto a = view.read(0, 0, 3), middle = view.read(0, 1, 1), b = view.read(1, 0, 3);
    check(a.data + 1 == middle.data && middle.data[0] == 'b', "same allocation slice");
    check(b.data - a.data == 8, "same contiguous allocation input distance");
    check(a.data[0] == 'a' && b.data[2] == 'z', "ordered expected data");
    view.reverify();

    auto expected = specs();
    const std::string original = "long_initialization_name_that_exceeds_small_string_storage";
    expected[0].span.name = original;
    auto* element = expected.data(); auto* name = expected[0].span.name.data();
    SameBufferLoader copied(0x1000, 16, 16, std::move(expected));
    name[0] = 'X'; element[0].span.bytes = 1; element[0].span.base = 0x1009;
    element[0].sha256.fill(0); element[1].span.name = "changed";
    expected.clear();
    std::istringstream aa("abc"), bb("xyz");
    copied.load_next(original, aa); copied.load_next("b", bb);
    auto ct = copied.finish(); auto cv = copied.take_ready(ct);
    check(cv.read(0, 0, 3).data[2] == 'c', "trusted expected deeply copied including rvalue aliases");
}
void test_stream_rejections() {
    for (const std::string bad : {"", "ab", "abd", "abcd", "abc "}) {
        SameBufferLoader loader(0x1000, 16, 16, specs());
        std::istringstream stream(bad);
        rejects([&] { loader.load_next("a", stream); }); poisoned(loader);
    }
    for (const auto state : {std::ios::badbit, std::ios::failbit, std::ios::eofbit}) {
        SameBufferLoader loader(0x1000, 16, 16, specs()); std::istringstream stream("abc");
        stream.setstate(state);
        rejects([&] { loader.load_next("a", stream); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); ThrowBuf buf; std::istream stream(&buf);
        rejects([&] { loader.load_next("a", stream); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); ThrowBuf buf; std::istream stream(&buf);
        stream.exceptions(std::ios::badbit);
        rejects([&] { loader.load_next("a", stream); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); ShortBuf buf; std::istream stream(&buf);
        rejects([&] { loader.load_next("a", stream); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); BadAtEofBuf buf; std::istream stream(&buf);
        buf.stream = &stream;
        rejects([&] { loader.load_next("a", stream); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); std::istringstream stream("abc");
        stream.exceptions(std::ios::failbit | std::ios::eofbit);
        rejects([&] { loader.load_next("a", stream); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); std::istringstream a("abc"), b("xy");
        loader.load_next("a", a);
        rejects([&] { loader.load_next("b", b); }); poisoned(loader);
    }
}
void test_order_and_one_shot() {
    for (const char* wrong : {"b", "unknown", "A", ""}) {
        SameBufferLoader loader(0x1000, 16, 16, specs()); std::istringstream stream("abc");
        rejects([&] { loader.load_next(wrong, stream); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); std::istringstream a("abc"), again("abc");
        loader.load_next("a", a);
        rejects([&] { loader.load_next("a", again); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); load_both(loader);
        std::istringstream extra("abc");
        rejects([&] { loader.load_next("a", extra); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs());
        rejects([&] { (void)loader.finish(); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); load_both(loader);
        auto token = loader.finish();
        rejects([&] { (void)loader.finish(); });
        rejects([&] { (void)loader.take_ready(token); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); load_both(loader);
        auto token = loader.finish(); std::istringstream extra("abc");
        rejects([&] { loader.load_next("a", extra); });
        rejects([&] { (void)loader.take_ready(token); }); poisoned(loader);
    }
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); load_both(loader);
        auto token = loader.finish(); auto view = loader.take_ready(token);
        rejects([&] { (void)loader.take_ready(token); });
        rejects([&] { (void)view.read(0, 0, 3); }); poisoned(loader);
    }
    {
        SameBufferLoader left(0x1000, 16, 16, specs()), right(0x1000, 16, 16, specs());
        load_both(left); load_both(right);
        auto lt = left.finish(); auto rt = right.finish();
        rejects([&] { (void)right.take_ready(lt); });
        rejects([&] { (void)right.take_ready(rt); }); poisoned(right);
        auto good = left.take_ready(lt);
        check(good.read(0, 0, 3).data[0] == 'a', "foreign token rejection leaves issuer intact");
    }
}
std::uint8_t* identified_test_ram() {
    check(probe::count == 2, "exactly two construction-time 64-byte allocations required");
    check(probe::captured[0].live && probe::captured[1].live,
          "both captured allocations must still be live before any memory read");
    check(probe::captured[0].pointer != nullptr && probe::captured[1].pointer != nullptr &&
          probe::captured[0].pointer != probe::captured[1].pointer,
          "two distinct non-null live backing allocations required");
    std::array<std::uint8_t, 64> payload{}, mask{}, first{}, second{};
    payload[0]='a'; payload[1]='b'; payload[2]='c';
    payload[8]='x'; payload[9]='y'; payload[10]='z';
    mask[0]=mask[1]=mask[2]=mask[8]=mask[9]=mask[10]=1;
    std::copy_n(static_cast<const std::uint8_t*>(probe::captured[0].pointer), 64, first.begin());
    std::copy_n(static_cast<const std::uint8_t*>(probe::captured[1].pointer), 64, second.begin());
    if (first == payload && second == mask)
        return static_cast<std::uint8_t*>(probe::captured[0].pointer);
    if (second == payload && first == mask)
        return static_cast<std::uint8_t*>(probe::captured[1].pointer);
    throw std::runtime_error("payload/mask identities are ambiguous");
}
void test_pre_ready_actual_ram_hash() {
    for (unsigned phase = 0; phase < 3; ++phase) {
        auto expected = specs();
        probe::Capture capture;
        SameBufferLoader loader(0x1000, 64, 64, expected);
        capture.stop(); load_both(loader);
        auto* actual = identified_test_ram();
        if (phase == 0) {
            actual[1] ^= 1U; // stream hash passed; seal-time actual-RAM hash must reject
            rejects([&] { (void)loader.finish(); }); poisoned(loader);
        } else {
            auto token = loader.finish();
            if (phase == 1) {
                actual[1] ^= 1U; // mutate after seal hash, before token redemption
                rejects([&] { (void)loader.take_ready(token); }); poisoned(loader);
            } else {
                auto view = loader.take_ready(token);
                check(view.read(0, 0, 3).data == actual,
                      "published const view uses the identified original RAM payload");
            }
        }
    }
}
void test_same_ram_tamper_and_range() {
    {
        SameBufferLoader loader(0x1000, 16, 16, specs()); load_both(loader);
        auto token = loader.finish(); auto view = loader.take_ready(token);
        const auto actual = view.read(0, 0, 3);
        // Deliberate test-only fault injection into known non-const owned bytes.
        // Production API never supplies a writable view. No data race is used.
        auto* injected = const_cast<std::uint8_t*>(actual.data);
        injected[1] ^= 1U;
        rejects([&] { view.reverify(); });
        rejects([&] { (void)view.read(0, 0, 3); }); poisoned(loader);
    }
    for (unsigned which = 0; which < 4; ++which) {
        SameBufferLoader loader(0x1000, 16, 16, specs()); load_both(loader);
        auto token = loader.finish(); auto view = loader.take_ready(token);
        rejects([&] {
            if (which == 0) (void)view.read(2, 0, 1);
            if (which == 1) (void)view.read(0, 0, 0);
            if (which == 2) (void)view.read(0, 2, 2);
            if (which == 3) (void)view.read(0, ~std::uint64_t(0), 1);
        });
        rejects([&] { view.reverify(); }); poisoned(loader);
    }
}
void test_constructor_rejections() {
    for (unsigned which = 0; which < 6; ++which) {
        auto expected = specs();
        if (which == 0) expected.clear();
        if (which == 1) expected[1].span.name = "a";
        if (which == 2) expected[1].span.base = 0x1001;
        if (which == 3) expected[0].span.bytes = 0;
        if (which == 4) expected[1].span.bytes = 1000;
        if (which == 5) expected[0].span.name = std::string(129, 'x');
        rejects([&] { SameBufferLoader invalid(0x1000, 16, 16, expected); });
    }
    rejects([&] { SameBufferLoader invalid(0x1000, 16, 15, specs()); });
}
} // namespace
static_assert(!std::is_default_constructible<SameBufferLoader::ReadyToken>::value, "private token");
static_assert(!std::is_copy_constructible<SameBufferLoader::ReadyToken>::value, "one token");
static_assert(!std::is_move_constructible<SameBufferLoader::ReadyToken>::value, "no token alias");
static_assert(!std::is_default_constructible<SameBufferLoader::ReadOnlyView>::value, "private view");
static_assert(!std::is_copy_constructible<SameBufferLoader::ReadOnlyView>::value, "one view");
static_assert(!std::is_copy_constructible<SameBufferLoader>::value, "one RAM owner");
int main() {
    try {
        test_sha256(); test_chunking_and_binary(); test_good_view_and_alias();
        test_stream_rejections(); test_order_and_one_shot();
        test_pre_ready_actual_ram_hash(); test_same_ram_tamper_and_range(); test_constructor_rejections();
        std::cout << "{\"status\":\"PASS\",\"checks\":" << checks
                  << ",\"max_synthetic_ram_bytes\":65537,\"canonical_identity_bound\":false,"
                     "\"launch_ready\":false}" << std::endl;
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << std::endl;
        return 1;
    }
}

// New independent standard SHA-256 implementation; SOURCE ONLY, not yet compiled.
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace same_buffer_loader_v1 {
class Sha256 final {
public:
    using Digest = std::array<std::uint8_t, 32>;
private:
    std::array<std::uint32_t, 8> h_{{0x6a09e667U, 0xbb67ae85U,
        0x3c6ef372U, 0xa54ff53aU, 0x510e527fU, 0x9b05688cU,
        0x1f83d9abU, 0x5be0cd19U}};
    std::array<std::uint8_t, 64> block_{};
    std::size_t used_ = 0;
    std::uint64_t bytes_ = 0;
    bool finished_ = false;

    static std::uint32_t rotate(std::uint32_t x, unsigned n) noexcept {
        return (x >> n) | (x << (32U - n));
    }
    void compress() noexcept {
        static constexpr std::uint32_t k[64] = {
            0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,
            0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
            0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,
            0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
            0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,
            0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
            0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,
            0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
            0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,
            0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
            0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,
            0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
            0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,
            0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
            0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,
            0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U};
        std::uint32_t w[64]{};
        for (std::size_t i = 0; i < 16; ++i) {
            const auto p = 4 * i;
            w[i] = (std::uint32_t(block_[p]) << 24U) |
                   (std::uint32_t(block_[p + 1]) << 16U) |
                   (std::uint32_t(block_[p + 2]) << 8U) |
                   std::uint32_t(block_[p + 3]);
        }
        for (std::size_t i = 16; i < 64; ++i) {
            const auto x = w[i - 15], y = w[i - 2];
            const auto s0 = rotate(x, 7) ^ rotate(x, 18) ^ (x >> 3U);
            const auto s1 = rotate(y, 17) ^ rotate(y, 19) ^ (y >> 10U);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        auto a=h_[0], b=h_[1], c=h_[2], d=h_[3];
        auto e=h_[4], f=h_[5], g=h_[6], h=h_[7];
        for (std::size_t i = 0; i < 64; ++i) {
            const auto s1 = rotate(e,6) ^ rotate(e,11) ^ rotate(e,25);
            const auto choice = (e & f) ^ (~e & g);
            const auto t1 = h + s1 + choice + k[i] + w[i];
            const auto s0 = rotate(a,2) ^ rotate(a,13) ^ rotate(a,22);
            const auto majority = (a & b) ^ (a & c) ^ (b & c);
            const auto t2 = s0 + majority;
            h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
        }
        h_[0]+=a; h_[1]+=b; h_[2]+=c; h_[3]+=d;
        h_[4]+=e; h_[5]+=f; h_[6]+=g; h_[7]+=h;
    }
public:
    void update(const std::uint8_t* data, std::size_t count) {
        if (finished_ || (count != 0 && data == nullptr) ||
            count > std::numeric_limits<std::uint64_t>::max() / 8 - bytes_)
            throw std::runtime_error("invalid SHA-256 update or bit length overflow");
        bytes_ += count;
        for (std::size_t i = 0; i < count; ++i) {
            block_[used_++] = data[i];
            if (used_ == block_.size()) { compress(); used_ = 0; }
        }
    }
    Digest finish() {
        if (finished_) throw std::runtime_error("SHA-256 finish is one-shot");
        finished_ = true;
        const auto bits = bytes_ * 8;
        block_[used_++] = 0x80U;
        if (used_ > 56) {
            while (used_ < 64) block_[used_++] = 0;
            compress(); used_ = 0;
        }
        while (used_ < 56) block_[used_++] = 0;
        for (unsigned i = 0; i < 8; ++i)
            block_[56 + i] = static_cast<std::uint8_t>(bits >> (56U - 8U * i));
        compress();
        Digest result{};
        for (std::size_t i = 0; i < h_.size(); ++i)
            for (unsigned j = 0; j < 4; ++j)
                result[4 * i + j] = static_cast<std::uint8_t>(h_[i] >> (24U - 8U * j));
        return result;
    }
    static Digest hash(const std::uint8_t* data, std::size_t count) {
        Sha256 hash;
        hash.update(data, count);
        return hash.finish();
    }
};
} // namespace same_buffer_loader_v1

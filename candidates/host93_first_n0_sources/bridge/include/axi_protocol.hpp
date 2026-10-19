// Adapted from pinned Kernel harness v2: protocol monitor only, no Q/K/V memory policy.
// External test memory only. This is not synthesized target storage or an FMA/service substitute.
#ifndef CANONICAL_HOST_AXI_PROTOCOL_HPP
#define CANONICAL_HOST_AXI_PROTOCOL_HPP
#include <array>
#include <cstdint>
#include <deque>
#include <iomanip>
#include <limits>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>


namespace canonical_host {
inline void require(bool ok, const std::string& reason) {
    if (!ok) throw std::runtime_error(reason); // Never compiled away by NDEBUG.
}
inline std::string hex(uint64_t value) {
    std::ostringstream out; out << "0x" << std::hex << value; return out.str();
}
using Data512 = std::array<uint32_t, 16>;
struct Address {
    uint64_t addr = 0; unsigned id = 0, len = 0, size = 0, burst = 0;
    auto key() const { return std::tie(addr, id, len, size, burst); }
    bool operator==(const Address& b) const { return key() == b.key(); }
};
struct WriteBeat {
    Data512 data{}; uint64_t strb = 0; bool last = false;
    bool operator==(const WriteBeat& b) const {
        return data == b.data && strb == b.strb && last == b.last;
    }
};
struct ReadBeat {
    Data512 data{}; unsigned id = 0, resp = 0; bool last = false;
    bool operator==(const ReadBeat& b) const {
        return data == b.data && id == b.id && resp == b.resp && last == b.last;
    }
};
struct WriteResponse {
    unsigned id = 0, resp = 0;
    bool operator==(const WriteResponse& b) const { return id == b.id && resp == b.resp; }
};
struct Sample {
    bool ar_valid = false, ar_ready = false, aw_valid = false, aw_ready = false;
    bool w_valid = false, w_ready = false, r_valid = false, r_ready = false;
    bool b_valid = false, b_ready = false;
    Address ar, aw; WriteBeat w; ReadBeat r; WriteResponse b;
    bool arf() const { return ar_valid && ar_ready; }
    bool awf() const { return aw_valid && aw_ready; }
    bool wf() const { return w_valid && w_ready; }
    bool rf() const { return r_valid && r_ready; }
    bool bf() const { return b_valid && b_ready; }
};
struct Ledger {
    uint64_t ars = 0, rbeats_expected = 0, rbeats = 0, rlasts = 0;
    uint64_t aws = 0, wbeats_expected = 0, wbeats = 0, wbeats_committed = 0, bs = 0, strobed_bytes = 0;
    uint64_t ar_stall = 0, aw_stall = 0, w_stall = 0, r_stall = 0, b_stall = 0;
    std::array<uint64_t, 256> ar_id{}, rlast_id{}, aw_id{}, b_id{};
    auto scalar_key() const {
        return std::tie(ars, rbeats_expected, rbeats, rlasts, aws, wbeats_expected,
                        wbeats, wbeats_committed, bs, strobed_bytes, ar_stall, aw_stall, w_stall, r_stall, b_stall);
    }
    bool operator==(const Ledger& b) const {
        return scalar_key() == b.scalar_key() && ar_id == b.ar_id && rlast_id == b.rlast_id
            && aw_id == b.aw_id && b_id == b.b_id;
    }
};

// This monitor observes only actual sampled pins, not RAM service state or DUT
// internals. Its debt queues are separate from the response-generating queues.
class IndependentLedger {
    struct ReadDebt { Address req; unsigned beat = 0; };
    std::deque<ReadDebt> reads_;
    std::deque<Address> addresses_;
    std::deque<WriteBeat> data_;
    std::deque<unsigned> responses_;
    Ledger counts_;
public:
    Ledger& counts() { return counts_; }
    const Ledger& counts() const { return counts_; }
    void consume(const Sample& s) {
        if (s.rf()) {
            require(!reads_.empty(), "independent ledger: unexpected/duplicate R");
            auto& debt = reads_.front();
            require(s.r.id == debt.req.id && s.r.resp == 0,
                    "independent ledger: R ID/RESP mismatch");
            require(s.r.last == (debt.beat == debt.req.len), "independent ledger: RLAST mismatch");
            ++counts_.rbeats;
            if (s.r.last) { ++counts_.rlasts; ++counts_.rlast_id[s.r.id]; reads_.pop_front(); }
            else ++debt.beat;
        }
        if (s.bf()) {
            require(!responses_.empty(), "independent ledger: unexpected/duplicate/early B");
            require(s.b.id == responses_.front() && s.b.resp == 0,
                    "independent ledger: B ID/RESP mismatch");
            ++counts_.bs; ++counts_.b_id[s.b.id]; responses_.pop_front();
        }
        if (s.arf()) {
            require(s.ar.id < 256 && s.ar.len < 256, "independent ledger: AR ID/len range");
            reads_.push_back({s.ar, 0});
            ++counts_.ars; ++counts_.ar_id[s.ar.id]; counts_.rbeats_expected += s.ar.len + 1;
        }
        if (s.awf()) {
            require(s.aw.id < 256 && s.aw.len < 256, "independent ledger: AW ID/len range");
            addresses_.push_back(s.aw);
            ++counts_.aws; ++counts_.aw_id[s.aw.id]; counts_.wbeats_expected += s.aw.len + 1;
        }
        if (s.wf()) { data_.push_back(s.w); ++counts_.wbeats; }
        if (!addresses_.empty() && data_.size() >= addresses_.front().len + 1) {
            const auto a = addresses_.front(); addresses_.pop_front();
            for (unsigned beat = 0; beat <= a.len; ++beat) {
                const auto w = data_.front(); data_.pop_front();
                require(w.last == (beat == a.len), "independent ledger: WLAST mismatch");
                ++counts_.wbeats_committed;
                for (unsigned b = 0; b < 64; ++b) counts_.strobed_bytes += (w.strb >> b) & 1ULL;
            }
            responses_.push_back(a.id);
        }
        require(counts_.rbeats <= counts_.rbeats_expected && counts_.rlasts <= counts_.ars,
                "independent read ledger exceeded accepted requests");
        require(counts_.bs <= counts_.aws && counts_.wbeats_committed <= counts_.wbeats,
                "independent write ledger exceeded accepted requests");
    }
    void require_retired() const {
        require(reads_.empty() && addresses_.empty() && data_.empty() && responses_.empty(),
                "independent ledger has outstanding debt");
        require(counts_.ars == counts_.rlasts && counts_.rbeats_expected == counts_.rbeats,
                "independent read accepted/returned mismatch");
        require(counts_.aws == counts_.bs && counts_.wbeats_expected == counts_.wbeats
                    && counts_.wbeats == counts_.wbeats_committed,
                "independent write accepted/returned mismatch");
        require(counts_.ar_id == counts_.rlast_id && counts_.aw_id == counts_.b_id,
                "independent accepted/returned ID mismatch");
    }
};

} // namespace canonical_host
#endif

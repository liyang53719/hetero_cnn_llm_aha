// SOURCE ONLY: partial physical observer. Unimplemented domains always fatal.
#pragma once
#include "resident_evidence.hpp"
// The real loader-qualified HostMemory interface, not a second conflicting RAM.
#include "host_memory.hpp"
namespace canonical_host::resident_physical {
class ResidentPhysicalObserver final : public PhysicalObserver {
    ResidentEvidence resident_;
    mutable bool failed_=false;
    void live()const {require(!failed_,"partial PhysicalObserver permanently failed");}
    [[noreturn]] void missing(const char* domain)const {
        failed_=true;
        throw silu_observation::Incomplete(std::string("physical domain remains unimplemented: ")+domain);
    }
    template<class F> auto checked(F&& action)const -> decltype(action()) {
        try {live();return action();} catch(...) {failed_=true;throw;}
    }
public:
    explicit ResidentPhysicalObserver(VHostBlockTop& model):resident_(model) {}
    ResidentPhysicalObserver(const ResidentPhysicalObserver&)=delete;
    ResidentPhysicalObserver& operator=(const ResidentPhysicalObserver&)=delete;
    ResidentPhysicalObserver(ResidentPhysicalObserver&&)=delete;
    ResidentPhysicalObserver& operator=(ResidentPhysicalObserver&&)=delete;
    // Do the real binding check, then refuse full-driver admission until reset
    // history and all physical domains have actual implementations.
    void require_bound_to_actual_host()const override {
        checked([&]{resident_.require_bound();missing("full reset provenance and remaining physical domains");});
    }
    void settle_low(uint64_t edge) {
        checked([&]{resident_.settle_low(edge);});
    }
    std::optional<ProvisionalSilu> rise_and_observe(uint64_t edge) {
        return checked([&]{return resident_.rise_and_observe(edge);});
    }
    Snapshot actual_resident_snapshot()const {return checked([&]{return resident_.actual_snapshot();});}
    void require_resident_retired()const {checked([&]{resident_.require_resident_retired();});}
    ResidentEvidence::Checkpoint resident_checkpoint()const {
        return checked([&]{return resident_.resident_checkpoint();});
    }
    void require_resident_quiescent(const ResidentEvidence::Checkpoint& c)const {
        checked([&]{resident_.require_resident_quiescent(c);});
    }
    WritePermit writer(uint64_t,uint64_t)const override {
        return checked([&]() -> WritePermit {missing("actual active DDR writer, owner SSA and prefix lease");});
    }
    void require_read_published(uint64_t,uint64_t,bool,uint32_t)const override {
        checked([&]{missing("actual B-retired publication, readers and prefix generation");});
    }
    void require_write_ack_owner(const WritePermit&)const override {
        checked([&]{missing("actual B handshake owner/lifetime and exact write permit");});
    }
    void require_completion_retired(unsigned pc)const override {
        checked([&]{
            require(pc<public_commands,"public PC range");
            if(pc==18)resident_.require_resident_retired();
            missing("completion still requires DMA/Matrix/DDR B and other owner debts");
        });
    }
    void begin_completion_hold(unsigned pc)override {
        checked([&]{
            require(pc<public_commands,"public PC range");
            if(pc==18)resident_.require_resident_retired();
            missing("full completion checkpoint needs all physical activity domains");
        });
    }
    void require_completion_hold_quiescent(unsigned)const override {
        checked([&]{missing("full completion hold activity freeze, not just resident counters");});
    }
    void end_completion_hold(unsigned)override {
        checked([&]{missing("actual public completion ACK and full hold checkpoint release");});
    }
    void begin_terminal_hold()override {
        checked([&]{resident_.require_resident_retired();missing("full terminal checkpoint");});
    }
    void require_terminal_hold_quiescent()const override {
        checked([&]{missing("full terminal and post-ACK physical quiescence");});
    }
    void require_terminal_retired(const std::array<unsigned,17>& expected)const override {
        checked([&]{
            require(expected==owner_pcs,"exact canonical owner PC contract");
            resident_.require_resident_retired();
            missing("remaining actual 17-owner reconciliation and all DMA/Matrix/prefix/B debts");
        });
    }
};
} // namespace canonical_host::resident_physical

// SOURCE ONLY. One scheduler for the actual N0 RAM and resident evidence slices.
#pragma once
#include "n0_participant.hpp"
#include "resident_participant.hpp"
namespace canonical_host::shared_edge {
class SharedEdgeRuntime final {
    VHostBlockTop& model_;
    n0_shared::N0PhysicalMemory memory_;
    resident_shared::ResidentEvidence resident_;
    mutable bool failed_=false;
    bool pending_=false,have_edge_=false;
    uint64_t edge_=0;
    actual_v2::HostFields::InputSnapshot inputs_{};
    void live()const {
        silu_observation::require(!failed_,"shared actual edge runtime permanently failed");
        actual_v2::HostFields::require_same_root(model_);
        silu_observation::require(!model_.reset&&!model_.io_resetRequired,"shared observation during reset/poison");
        silu_observation::require(!model_.contextp()->gotFinish()&&!model_.contextp()->gotError(),"actual context finished/errored");
    }
    template<class F> auto checked(F&& f)const -> decltype(f()) {
        try {live();return f();} catch(...) {failed_=true;throw;}
    }
    void settled()const {silu_observation::require(!pending_,"no external read/claim during unretired edge");}
    void unchanged_inputs(bool high)const {
        const auto now=actual_v2::HostFields::input_snapshot(model_);
        for(size_t i=0;i<now.size();++i)
            silu_observation::require(now[i]==(i==0?uint64_t(high):inputs_[i]),"shared sampled inputs changed outside scheduler clock");
    }
public:
    using ResidentCheckpoint=resident_shared::ResidentEvidence::Checkpoint;
    explicit SharedEdgeRuntime(VHostBlockTop& model):model_(model),memory_(model),resident_(model) {}
    SharedEdgeRuntime(const SharedEdgeRuntime&)=delete;
    SharedEdgeRuntime& operator=(const SharedEdgeRuntime&)=delete;
    SharedEdgeRuntime(SharedEdgeRuntime&&)=delete;
    SharedEdgeRuntime& operator=(SharedEdgeRuntime&&)=delete;
    CompletedCanonicalSinkStream load(std::istream& source) {
        return checked([&]{settled();silu_observation::require(!have_edge_,"load only before observation history");return memory_.load(source);});
    }
    void require_ready()const {checked([&]{settled();memory_.require_ready();});}
    ByteView read_input_span(size_t i,uint64_t offset,uint64_t bytes)const {
        return checked([&]{settled();return memory_.read_input_span(i,offset,bytes);});
    }
    void settle_low(uint64_t edge) {
        checked([&]{
            silu_observation::require(!pending_&&(!have_edge_||
                (edge_!=std::numeric_limits<uint64_t>::max()&&edge==edge_+1)),"one consecutive shared edge");
            memory_.prepare_low(edge); // real AXI input drive, same existing sealed RAM
            resident_.prepare_low(edge); // private actual recording frame, no evaluation
            model_.clock=0;model_.eval();
            live();
            inputs_=actual_v2::HostFields::input_snapshot(model_);
            memory_.observe_stable_low(edge);
            resident_.observe_stable_low(edge);
            unchanged_inputs(false);
            edge_=edge;pending_=true;
        });
    }
    std::optional<silu_observation::ProvisionalSilu> rise_and_observe(uint64_t edge) {
        return checked([&]{
            silu_observation::require(pending_&&edge==edge_&&model_.clock==0,"matching shared rising edge");
            unchanged_inputs(false);
            model_.clock=1;model_.eval();
            live();unchanged_inputs(true);
            // Original resident pre/post validation precedes original N0 B mutation.
            // If either participant throws, no capture/read/claim escapes this object.
            auto capture=resident_.observe_settled_high(edge);
            memory_.observe_settled_high(edge);
            unchanged_inputs(true);
            pending_=false;have_edge_=true;
            return capture;
        });
    }
    uint8_t actual_byte(uint64_t address)const {
        return checked([&]{settled();return memory_.actual_byte(address);});
    }
    void require_n0_published()const {checked([&]{settled();memory_.require_n0_published();});}
    n0_shared::PublicationEvidence n0_publication_evidence()const {
        return checked([&]{settled();return memory_.publication_evidence();});
    }
    resident_shared::Snapshot actual_resident_snapshot()const {
        return checked([&]{settled();return resident_.actual_snapshot();});
    }
    void require_resident_retired()const {checked([&]{settled();resident_.require_resident_retired();});}
    ResidentCheckpoint resident_checkpoint()const {
        return checked([&]{settled();return resident_.resident_checkpoint();});
    }
    void require_resident_quiescent(const ResidentCheckpoint& checkpoint)const {
        checked([&]{settled();resident_.require_resident_quiescent(checkpoint);});
    }
    void require_bound_to_actual_host()const {
        checked([&]{settled();memory_.require_bound_to_actual_host();}); // full-domain gap remains fatal
    }
};
} // namespace canonical_host::shared_edge

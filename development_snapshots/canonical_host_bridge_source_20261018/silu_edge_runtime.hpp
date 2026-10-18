// SOURCE ONLY. No main, launch loop, fallback model, or execution permission.
#pragma once
#include "host_fields.hpp"
#include <limits>
namespace canonical_host::actual_v2 {
// Only this adapter's methods perform evals. Callers must not change model
// inputs or evaluate between settle_low() and rise_and_observe(). The future
// full-driver gate must control that ownership and an external hard deadline.
class SiluEdgeRuntime {
    VHostBlockTop& model_;
    silu_observation::GeneratedBinding<VHostBlockTop> binding_;
    silu_observation::ActualHostObserver<VHostBlockTop> observer_;
    bool failed_=false,pending_=false,have_edge_=false;
    uint64_t edge_=0;
    HostFields::InputSnapshot inputs_{};
    void live()const {
        silu_observation::require(!failed_,"runtime adapter permanently failed");
        HostFields::require_same_root(model_);
        silu_observation::require(!model_.reset,"actual runtime adapter used during reset");
    }
public:
    explicit SiluEdgeRuntime(VHostBlockTop& model)
        :model_(model),binding_(model),observer_(binding_) {}
    // The driver must have already driven all external inputs for this cycle.
    // On return, it may take its immutable AXI/completion pre-edge sample.
    void settle_low(uint64_t edge) {
        try {
            live();
            silu_observation::require(!pending_ && (!have_edge_ ||
                (edge_!=std::numeric_limits<uint64_t>::max() && edge==edge_+1)),
                "one consecutive actual rising edge at a time");
            model_.clock=0;
            model_.eval();
            // A fatal Verilator diagnostic must not be reinterpreted as capture.
            silu_observation::require(!model_.contextp()->gotFinish() &&
                !model_.contextp()->gotError(),"actual eval terminated with finish/error");
            observer_.before_rising(edge);
            inputs_=HostFields::input_snapshot(model_);
            edge_=edge;pending_=true;
        } catch(...) {failed_=true;throw;}
    }
    // Exactly one real high eval; commit only after the original observer's
    // same-edge post checks. Caller next retires its own immutable AXI sample.
    std::optional<silu_observation::ProvisionalSilu> rise_and_observe(uint64_t edge) {
        try {
            live();
            silu_observation::require(pending_ && edge==edge_ && model_.clock==0,
                "high eval requires this exact pending low sample");
            silu_observation::require(HostFields::input_snapshot(model_)==inputs_,
                "actual inputs changed after pre-edge sample");
            model_.clock=1;
            model_.eval();
            silu_observation::require(!model_.contextp()->gotFinish() &&
                !model_.contextp()->gotError(),"actual high eval terminated with finish/error");
            auto capture=observer_.after_rising(edge);
            pending_=false;have_edge_=true;
            return capture; // Provisional actual words; no comparator/coverage override.
        } catch(...) {failed_=true;throw;}
    }
    void require_provisional_silu_coverage() {
        try {
            live();silu_observation::require(!pending_,"unfinished actual edge");
            observer_.require_provisional_silu_coverage();
        } catch(...) {failed_=true;throw;}
    }
};
} // namespace canonical_host::actual_v2

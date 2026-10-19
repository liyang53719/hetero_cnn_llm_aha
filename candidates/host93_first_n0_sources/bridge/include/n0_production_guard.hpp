// SOURCE ONLY. Concrete actual binding and original Observer, narrowed to PC0.
#pragma once
#include "generated_binding.hpp"
#include <optional>
namespace canonical_runtime_v1::first_n0 {
class ProductionGuard final {
    using Pre=canonical_host::silu_observation::PreEdge;
    using Post=canonical_host::silu_observation::PostEdge;
    using Capture=canonical_host::silu_observation::ProvisionalSilu;
    static void require(bool ok,const char* why) {canonical_host::silu_observation::require(ok,why);}
    class RecordingBinding final {
        canonical_host::silu_observation::GeneratedBinding<VHostBlockTop> actual_;
        mutable std::optional<Pre> pre_;
        mutable std::optional<Post> post_;
    public:
        explicit RecordingBinding(VHostBlockTop& model):actual_(model) {}
        void require_actual_profile()const {actual_.require_actual_profile();}
        Pre read_stable_low()const {
            require(!pre_&&!post_,"one actual resident low frame");pre_=actual_.read_stable_low();return *pre_;
        }
        Post read_settled_high()const {
            require(pre_&&!post_,"actual resident high requires low frame");post_=actual_.read_settled_high();return *post_;
        }
        const Pre& pre()const {require(bool(pre_),"resident low frame absent");return *pre_;}
        const Post& post()const {require(bool(post_),"resident high frame absent");return *post_;}
        void retire()noexcept {pre_.reset();post_.reset();}
    };
    VHostBlockTop& model_;
    const VHostBlockTop___024root* const root_;
    const VHostBlockTop__Syms* const syms_;
    RecordingBinding binding_;
    canonical_host::silu_observation::Observer<RecordingBinding> observer_;
    void identity()const {
        require(root_&&syms_&&model_.rootp==root_&&root_->vlSymsp==syms_&&&syms_->TOP==root_&&
                syms_->__Vm_modelp==&model_,"same actual Host/root/Syms identity");
        require(&model_.clock==&root_->clock&&&model_.reset==&root_->reset,"actual clock/reset aliases");
        require(!model_.reset&&!model_.io_resetRequired&&!model_.contextp()->gotError()&&!model_.contextp()->gotFinish(),
                "actual Host is reset, poisoned or stopped");
    }
    template<class T> static void registered(const VerilatedScope* scope,const char* name,
            const T* address,unsigned bits,VerilatedVarType type,const VHostBlockTop__Syms* syms) {
        require(scope&&scope->symsp()==syms,"N0 scope belongs to actual model");
        const auto* var=scope->varFind(name);
        require(var&&var->magicOk()&&var->datap()==static_cast<const void*>(address)&&var->vltype()==type&&
                var->entBits()==bits&&var->entSize()==sizeof(T)&&var->udims()==0&&var->pdims()==(bits==1?0:1)&&
                !var->isPublicRW()&&!var->isParam()&&!var->isSigned()&&!var->isForceable(),
                "N0 readonly registered address/type/width differs");
        if(bits!=1)require(var->packedRanges()[0].left()==int(bits)-1&&var->packedRanges()[0].right()==0,
                            "N0 packed field range differs");
    }
    void profile()const {
        identity();const auto& r=*root_;const auto& s=*syms_;
#include "n0_field_registry.inc"
    }
    void matrix_idle()const {
        const auto& r=*root_;
        require(r.HostBlockTop__DOT__owner__DOT__matrix__DOT__state==0&&
                !r.HostBlockTop__DOT__owner__DOT__matrix__DOT__poison&&
                !r.HostBlockTop__DOT__owner__DOT__matrix__DOT__io_port_step_valid&&
                r.HostBlockTop__DOT__owner__DOT__matrix__DOT__steps==0&&
                r.HostBlockTop__DOT__owner__DOT__matrix__DOT__wideSteps==0&&
                model_.io_usefulMacs==0&&model_.io_executedMacs==0&&model_.io_pipelineIssues==0,
                "PC0 must not activate matrix service");
    }
public:
    explicit ProductionGuard(VHostBlockTop& model):model_(model),root_(model.rootp),
        syms_(root_?root_->vlSymsp:nullptr),binding_(model),observer_(binding_) {profile();matrix_idle();}
    ProductionGuard(const ProductionGuard&)=delete;ProductionGuard& operator=(const ProductionGuard&)=delete;
    void before_rising(std::uint64_t edge) {
        identity();matrix_idle();observer_.before_rising(edge);const auto& f=binding_.pre();
        require(f.router_state!=3&&!f.host_group.valid&&!f.resident_group.valid&&!f.group_result.valid&&
                !f.bridge_start.valid&&!f.bridge_complete&&!f.tile_read.valid&&!f.tile_response.valid&&!f.tile_write.valid&&
                !f.bridge_request.valid&&!f.bridge_result.valid&&!f.raw_silu_valid,
                "resident FFN/SiLU work is outside PC0");
        require(!f.router_fault&&!f.router_bad&&!f.backend_reset&&!f.host_abort&&!f.host_reset_required&&
                !f.group_abort&&!f.group_reset_required&&!f.bridge_bad&&!f.bridge_abort&&!f.bridge_poison&&
                !f.loan_context.poison&&!f.loan_context.abort,"pre-edge shared/resident fault");
    }
    void after_rising(std::uint64_t edge) {
        identity();const auto capture=observer_.after_rising(edge);const auto& p=binding_.post();
        require(!capture&&p.router_state!=3&&!p.router_bad&&!p.bridge_bad&&!p.group_abort&&
                !p.group_reset_required&&!p.host_reset_required&&!p.loan_context.poison&&!p.loan_context.abort,
                "post-edge resident capture/fault outside PC0");
        matrix_idle();binding_.retire();
    }
};
}

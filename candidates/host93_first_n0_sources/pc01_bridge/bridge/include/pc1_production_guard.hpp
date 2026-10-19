// SOURCE ONLY. Same registered public/shared boundaries for fixed PC1 only.
#pragma once
#include "generated_binding.hpp"
#include "pc01_result.hpp"
#include <optional>
namespace canonical_runtime_v1::first_n0 {
class Pc1ProductionGuard final {
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
    struct Matrix {std::uint64_t steps,wide,stalls,state,mask;bool valid,ready,legal,poison;};
    Matrix matrix()const {
        const auto& r=*root_;
        return {r.HostBlockTop__DOT__owner__DOT__matrix__DOT__steps,
            r.HostBlockTop__DOT__owner__DOT__matrix__DOT__wideSteps,
            r.HostBlockTop__DOT__owner__DOT__matrix__DOT__stalls,
            r.HostBlockTop__DOT__owner__DOT__matrix__DOT__state,
            r.HostBlockTop__DOT__owner__DOT__matrix__DOT__group_sliceMask,
            bool(r.HostBlockTop__DOT__owner__DOT__matrix__DOT__io_port_step_valid),
            bool(r.HostBlockTop__DOT__owner__DOT__matrix__DOT__io_port_step_ready),
            bool(r.HostBlockTop__DOT__owner__DOT__matrix__DOT__legalStep),
            bool(r.HostBlockTop__DOT__owner__DOT__matrix__DOT__poison)};
    }
    Matrix baseline_{},low_{};
    bool pending_=false,loan_=false;
    std::uint64_t edge_=0,requests_=0,results_=0;
    canonical_host::silu_observation::Operands operands_{};
    std::optional<canonical_host::silu_observation::Operands> held_request_;
    std::optional<canonical_host::silu_observation::Words> held_result_;
    static void healthy(const Pre& f) {
        require(!f.router_fault&&!f.router_bad&&!f.backend_reset&&!f.host_abort&&!f.host_reset_required&&
                !f.group_abort&&!f.group_reset_required&&!f.bridge_bad&&!f.bridge_abort&&!f.bridge_poison&&
                !f.loan_context.poison&&!f.loan_context.abort&&!f.vector_error,"PC1 shared pre fault");
    }
public:
    explicit Pc1ProductionGuard(VHostBlockTop& model):model_(model),root_(model.rootp),
        syms_(root_?root_->vlSymsp:nullptr),binding_(model),observer_(binding_) {
        profile();baseline_=matrix();
        require(baseline_.state==0&&!baseline_.poison&&!baseline_.valid&&baseline_.steps==0&&baseline_.wide==0&&
                model.io_usefulMacs==0&&model.io_executedMacs==0,"PC1 begins after zero-Matrix PC0");
    }
    Pc1ProductionGuard(const Pc1ProductionGuard&)=delete;
    Pc1ProductionGuard& operator=(const Pc1ProductionGuard&)=delete;
    void before_rising(std::uint64_t edge,bool active) {
        identity();require(!pending_,"PC1 shared low duplicated");observer_.before_rising(edge);
        const auto& f=binding_.pre();healthy(f);low_=matrix();
        require(!low_.poison&&(f.router_state==0||f.router_state==2),"PC1 fixed reduction router only");
        require(!f.host_group.valid&&!f.resident_group.valid&&!f.group_result.valid&&!f.bridge_start.valid&&
                !f.bridge_complete&&!f.tile_read.valid&&!f.tile_response.valid&&!f.tile_write.valid&&
                !f.bridge_request.valid&&!f.bridge_result.valid&&!f.raw_silu_valid,
                "PC1 resident FFN or SiLU activity forbidden");
        if(low_.valid)require(active&&f.router_state==2&&low_.mask==255,"PC1 legal full transposed Matrix issue");
        require(f.loan_context.active==loan_,"PC1 actual shared loan debt");
        const bool req=f.vector_request.fire(),res=f.vector_result.fire();
        require(req==f.router_shared_request.fire()&&req==f.owner_request.fire()&&
                res==f.router_shared_result.fire()&&res==f.owner_result.fire(),"PC1 shared request result handshakes");
        if(f.vector_request.valid) {
            require(active&&f.router_state==2&&f.router_shared_request.valid&&f.owner_request.valid&&
                    f.router_shared_request.binary_add&&f.owner_request.binary_add&&f.vector_request.binary_add&&
                    f.router_shared_request.bits==f.vector_request.bits&&f.owner_request.bits==f.vector_request.bits,
                    "PC1 exact binaryAdd request aliases");
        }
        if(held_request_)require(f.vector_request.valid&&f.vector_request.bits==*held_request_,"PC1 held add operands changed");
        held_request_=f.vector_request.valid&&!f.vector_request.ready?
            std::optional<canonical_host::silu_observation::Operands>(f.vector_request.bits):std::nullopt;
        if(loan_)require(active&&f.router_state==2&&f.input_binary_add&&f.vector_phase==0&&f.vector_input==operands_,
                         "PC1 retained add mode operands");
        if(f.vector_result.valid)require(loan_&&f.router_shared_result.valid&&f.owner_result.valid&&
                !f.vector_result.error&&!f.owner_result.error&&!f.router_shared_result.error&&
                f.vector_result.value==f.owner_result.value&&f.vector_result.value==f.router_shared_result.value,
                "PC1 shared add result aliases");
        if(held_result_)require(f.vector_result.valid&&f.vector_result.value==*held_result_,"PC1 held add result changed");
        held_result_=f.vector_result.valid&&!f.vector_result.ready?
            std::optional<canonical_host::silu_observation::Words>(f.vector_result.value):std::nullopt;
        require(!(req&&res),"PC1 no add request result overlap");
        if(req)require(!loan_&&f.vector_state==0&&requests_<pc01::add_vectors,"PC1 unique idle add request");
        if(res)require(loan_&&f.vector_state==3&&results_<requests_,"PC1 original add result retirement");
        edge_=edge;pending_=true;
    }
    void after_rising(std::uint64_t edge) {
        identity();require(pending_&&edge==edge_,"PC1 shared matching high");
        const auto capture=observer_.after_rising(edge);const auto& f=binding_.pre();const auto& p=binding_.post();
        require(!capture&&!p.router_bad&&!p.bridge_bad&&!p.group_abort&&!p.group_reset_required&&!p.host_reset_required&&
                !p.loan_context.poison&&!p.loan_context.abort,"PC1 shared same-edge post fault");
        const auto now=matrix();const auto fire=low_.valid&&low_.ready;
        require(!fire||low_.legal,"PC1 accepted Matrix step legal");
        require(!now.poison&&now.steps==low_.steps+(fire?8:0)&&now.wide==low_.wide+(fire?1:0)&&
                now.stalls>=low_.stalls&&now.stalls-low_.stalls<=(low_.valid&&!low_.ready?1U:0U),"PC1 actual Matrix counter edge delta");
        if(f.vector_request.fire()) {
            require(p.loan_context.active&&p.vector_state==1&&p.vector_phase==0,"PC1 add actual latch");
            operands_=f.vector_request.bits;loan_=true;++requests_;
        }
        if(f.vector_result.fire()) {
            require(!p.loan_context.active&&p.vector_state==0,"PC1 add actual release");loan_=false;++results_;
        }
        require(p.loan_context.active==loan_,"PC1 post shared loan ledger");
        binding_.retire();pending_=false;
    }
    void require_terminal_low()const {
        require(pending_,"PC1 terminal requires current low");const auto& f=binding_.pre();const auto m=matrix();
        require(!loan_&&!held_request_&&!held_result_&&requests_==pc01::add_vectors&&results_==requests_&&
                !f.loan_context.active&&f.vector_state==0&&f.silu_drained&&f.tiles_drained&&
                !f.tiles[0].live&&!f.tiles[1].live&&!f.tiles[2].live&&m.state==0&&!m.valid&&!m.poison&&
                m.wide-baseline_.wide==pc01::wide_steps&&m.steps-baseline_.steps==pc01::slice_steps,
                "PC1 public shared services not fully retired");
    }
    std::uint64_t requests()const noexcept{return requests_;}
    std::uint64_t results()const noexcept{return results_;}
    std::uint64_t wide_steps()const{return matrix().wide-baseline_.wide;}
    std::uint64_t slice_steps()const{return matrix().steps-baseline_.steps;}
    std::uint64_t stalls()const{return matrix().stalls-baseline_.stalls;}
};
}

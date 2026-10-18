// SOURCE ONLY: real generated reads + original event qualification. No model run performed.
#pragma once
#include "host_fields.hpp"
#include <limits>
#include <memory>
#include <tuple>
#include <utility>
namespace canonical_host::resident_physical {
using silu_observation::require;
using silu_observation::PreEdge;
using silu_observation::PostEdge;
using silu_observation::ProvisionalSilu;
struct Counts {
    uint64_t groups_accepted=0,groups_retired=0,resident_loans_accepted=0,resident_loans_retired=0;
    uint64_t shared_loans_accepted=0,shared_loans_retired=0,captures=0;
    auto key()const {return std::tie(groups_accepted,groups_retired,resident_loans_accepted,
        resident_loans_retired,shared_loans_accepted,shared_loans_retired,captures);}
    bool operator==(const Counts& other)const {return key()==other.key();}
};
struct Snapshot {
    uint64_t actual_rising_edge;
    Counts counts;
    uint32_t actual_group_identity,actual_act_owner_tag;
    bool actual_shared_active,actual_shared_poison,actual_shared_abort;
};
class ResidentEvidence {
    // This bridge can only read the actual binding. It has no event injection API.
    class RecordingBinding {
        silu_observation::GeneratedBinding<VHostBlockTop> actual_;
        mutable std::optional<PreEdge> pre_;
        mutable std::optional<PostEdge> post_;
    public:
        explicit RecordingBinding(VHostBlockTop& model):actual_(model) {}
        void require_actual_profile()const {actual_.require_actual_profile();}
        void begin_frame() {require(!pre_&&!post_,"uncommitted actual frame");}
        PreEdge read_stable_low()const {
            require(!pre_&&!post_,"one actual low read per frame");
            auto p=actual_.read_stable_low();pre_=p;return p;
        }
        PostEdge read_settled_high()const {
            require(pre_&&!post_,"actual high read requires low frame");
            auto p=actual_.read_settled_high();post_=p;return p;
        }
        const PreEdge& pre()const {require(bool(pre_),"actual low frame missing");return *pre_;}
        const PostEdge& post()const {require(bool(post_),"actual high frame missing");return *post_;}
        void retire_frame() {require(pre_&&post_,"cannot retire incomplete frame");pre_.reset();post_.reset();}
    };
    VHostBlockTop& model_;
    RecordingBinding binding_;
    mutable silu_observation::Observer<RecordingBinding> observer_;
    mutable bool failed_=false;
    bool pending_=false,have_edge_=false;
    uint64_t edge_=0;
    actual_v2::HostFields::InputSnapshot inputs_{};
    Counts counts_{};
    uint32_t group_identity_=0,act_tag_=0;
    PostEdge last_post_{};
    // Observer-lifetime identity only, not an RTL generation or event value.
    // Checkpoints keep it alive, so allocator address reuse cannot rebind them.
    const std::shared_ptr<const uint8_t> lifetime_=std::make_shared<const uint8_t>(0);
    static void increment(uint64_t& n) {
        require(n!=std::numeric_limits<uint64_t>::max(),"actual activity counter overflow");++n;
    }
    void live()const {
        require(!failed_,"resident physical evidence permanently failed");
        actual_v2::HostFields::require_same_root(model_);
        require(!model_.reset,"resident evidence used during actual reset");
    }
    void commit_validated_frame(const std::optional<ProvisionalSilu>& capture) {
        const auto& pre=binding_.pre();const auto& post=binding_.post();
        // Called ONLY after the original Observer accepted this SAME real edge.
        // Count shared activity even before/after resident work, so a later
        // start-and-finish cannot hide behind a zero current loan debt.
        if(pre.owner_request.fire())increment(counts_.shared_loans_accepted);
        if(pre.owner_result.fire())increment(counts_.shared_loans_retired);
        if(pre.resident_group.fire()) {
            increment(counts_.groups_accepted);
            group_identity_=pre.resident_group.identity;
            act_tag_=pre.resident_group.act_tag; // actual act18, not identity17.
        }
        if(pre.router_state==3 && pre.bridge_request.fire())increment(counts_.resident_loans_accepted);
        if(pre.router_state==3 && pre.bridge_result.fire())increment(counts_.resident_loans_retired);
        if(capture)increment(counts_.captures);
        if(pre.group_result.fire())increment(counts_.groups_retired);
        require(counts_.shared_loans_retired<=counts_.shared_loans_accepted &&
            counts_.resident_loans_retired<=counts_.resident_loans_accepted &&
            counts_.groups_retired<=counts_.groups_accepted,"actual retirement exceeds observed acceptance");
        require(counts_.shared_loans_accepted-counts_.shared_loans_retired<=1 &&
            post.loan_context.active==bool(counts_.shared_loans_accepted-counts_.shared_loans_retired),
            "actual shared active disagrees with observed accepted/returned debt");
        last_post_=post;
    }
public:
    // This token certifies ONLY the resident/shared-loan subdomain. The owning
    // full PhysicalObserver must separately freeze all other activity/debts.
    class Checkpoint {
        friend class ResidentEvidence;
        const ResidentEvidence* owner_;
        std::shared_ptr<const uint8_t> lifetime_;
        Snapshot at_;
        Checkpoint(const ResidentEvidence* owner,std::shared_ptr<const uint8_t> lifetime,Snapshot at)
            :owner_(owner),lifetime_(std::move(lifetime)),at_(at) {}
    public:
        Checkpoint(const Checkpoint&)=default;
    };
    explicit ResidentEvidence(VHostBlockTop& model):model_(model),binding_(model),observer_(binding_) {}
    ResidentEvidence(const ResidentEvidence&)=delete;
    ResidentEvidence& operator=(const ResidentEvidence&)=delete;
    ResidentEvidence(ResidentEvidence&&)=delete;
    ResidentEvidence& operator=(ResidentEvidence&&)=delete;
    void require_bound()const {
        try {require(!failed_,"resident evidence failed");binding_.require_actual_profile();}
        catch(...) {failed_=true;throw;}
    }
    void settle_low(uint64_t edge) {
        try {
            live();require(!pending_&&(!have_edge_ ||
                (edge_!=std::numeric_limits<uint64_t>::max()&&edge==edge_+1)),"consecutive actual edge");
            binding_.begin_frame();model_.clock=0;model_.eval();
            require(!model_.contextp()->gotFinish()&&!model_.contextp()->gotError(),"actual low eval failed");
            observer_.before_rising(edge);inputs_=actual_v2::HostFields::input_snapshot(model_);
            edge_=edge;pending_=true;
        } catch(...) {failed_=true;throw;}
    }
    std::optional<ProvisionalSilu> rise_and_observe(uint64_t edge) {
        try {
            live();require(pending_&&edge==edge_&&model_.clock==0,"matching actual high edge");
            require(actual_v2::HostFields::input_snapshot(model_)==inputs_,"actual inputs changed after low sample");
            model_.clock=1;model_.eval();
            require(!model_.contextp()->gotFinish()&&!model_.contextp()->gotError(),"actual high eval failed");
            auto capture=observer_.after_rising(edge);
            commit_validated_frame(capture);
            binding_.retire_frame();pending_=false;have_edge_=true;
            return capture;
        } catch(...) {failed_=true;throw;}
    }
    Snapshot actual_snapshot()const {
        try {
            live();require(have_edge_&&!pending_,"resident evidence requires completed actual edge");
            return {edge_,counts_,group_identity_,act_tag_,last_post_.loan_context.active,
                last_post_.loan_context.poison,last_post_.loan_context.abort};
        } catch(...) {failed_=true;throw;}
    }
    void require_resident_retired()const {
        try {
            const auto s=actual_snapshot();observer_.require_provisional_silu_coverage();
            require(s.counts.groups_accepted==1&&s.counts.groups_retired==1 &&
                s.actual_group_identity==((7u<<16)|17u)&&s.actual_act_owner_tag==((7u<<16)|18u),
                "actual group17/act18 accept and retirement");
            require(s.counts.captures==128u*8960u/16u &&
                s.counts.resident_loans_accepted==s.counts.captures &&
                s.counts.resident_loans_retired==s.counts.captures &&
                s.counts.shared_loans_accepted==s.counts.shared_loans_retired &&
                !s.actual_shared_active&&!s.actual_shared_poison&&!s.actual_shared_abort,
                "actual resident coverage and shared-loan zero debt");
        } catch(...) {failed_=true;throw;}
    }
    Checkpoint resident_checkpoint()const {
        try {require_resident_retired();return Checkpoint(this,lifetime_,actual_snapshot());}
        catch(...) {failed_=true;throw;}
    }
    void require_resident_quiescent(const Checkpoint& checkpoint)const {
        try {
            require(checkpoint.owner_==this&&checkpoint.lifetime_==lifetime_,
                "checkpoint from a different actual model observer lifetime");
            require_resident_retired();const auto now=actual_snapshot();
            require(now.actual_rising_edge>=checkpoint.at_.actual_rising_edge &&
                now.counts==checkpoint.at_.counts &&
                now.actual_group_identity==checkpoint.at_.actual_group_identity &&
                now.actual_act_owner_tag==checkpoint.at_.actual_act_owner_tag,
                "actual resident/shared activity changed while held, even if debt returned to zero");
        } catch(...) {failed_=true;throw;}
    }
};
} // namespace canonical_host::resident_physical

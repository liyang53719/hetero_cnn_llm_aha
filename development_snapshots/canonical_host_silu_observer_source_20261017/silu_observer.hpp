// Source-only. Concrete read-only event qualification; generated Host leaf binding is absent.
#pragma once
#include <array>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
namespace canonical_host::silu_observation {
using Words=std::array<uint32_t,16>;
struct Incomplete : std::runtime_error { using std::runtime_error::runtime_error; };
struct Violation : std::runtime_error { using std::runtime_error::runtime_error; };
inline void require(bool ok,const char* why) { if(!ok)throw Violation(why); }
struct Handshake { bool valid,ready; bool fire()const{return valid&&ready;} };
struct Key {
    uint32_t identity;uint16_t ng,index;uint8_t slot;
    bool operator==(const Key& k)const{return identity==k.identity&&ng==k.ng&&index==k.index&&slot==k.slot;}
};
struct Call {
    uint32_t identity;uint16_t ng;uint8_t rows,cols;
    bool operator==(const Call& c)const{return identity==c.identity&&ng==c.ng&&rows==c.rows&&cols==c.cols;}
};
struct Operands { Words gate,up;bool operator==(const Operands& o)const{return gate==o.gate&&up==o.up;} };
struct Request : Handshake { Operands bits; };
struct SharedRequest : Request { bool binary_add; };
struct Result : Handshake { Words value;bool error; };
struct TileState {
    bool live,sealed;uint32_t identity;uint16_t ng,expected,produced,consumed;uint8_t rows,cols;
};
struct Group : Handshake {
    uint32_t identity,gate_tag,up_tag,act_tag;uint16_t gate_rows,up_rows,act_rows;
};
struct GroupResult : Handshake {uint32_t tag;uint8_t status;};
struct Context {bool active,poison,abort;};
struct TileRead : Handshake {Key key;};
struct TileResponse : Handshake {Key key;Words value;bool error;};
struct TileWrite : Handshake {Key key;Words value;};
// Observer-owned decoded snapshots, NOT added RTL ports. All members must be
// read from the source leaves listed in BINDING_REQUIREMENTS.json, one eval.
struct PreEdge {
    bool clock,reset;
    uint8_t router_state;bool router_fault,router_bad,backend_reset,host_abort,host_reset_required;
    Group host_group,resident_group;GroupResult group_result;
    bool group_abort,group_reset_required;
    Handshake bridge_start;Call start_call,bridge_call;uint8_t bridge_state;
    bool bridge_bad,bridge_abort,bridge_poison,bridge_complete,tiles_drained,silu_drained;
    std::array<TileState,3> tiles;
    TileRead tile_read;TileResponse tile_response;TileWrite tile_write;
    Request bridge_request,router_resident_request;
    SharedRequest router_shared_request,owner_request,vector_request;
    Result bridge_result,router_resident_result,router_shared_result,owner_result,vector_result;
    Context loan_context;
    uint8_t vector_state,vector_phase;bool vector_all_ready,vector_error,input_binary_add;
    Operands vector_input;Words vector_value;
    bool raw_silu_valid;Words raw_silu_value;
};
struct PostEdge {
    bool clock,reset;uint8_t router_state,vector_state,vector_phase;
    Context loan_context;
    bool router_bad,bridge_bad,group_abort,group_reset_required,host_reset_required;
};
// Source map only. No current generated header exists for this successor.
// A future specialization must resolve EVERY listed leaf/profile to a unique
// generated symbol with exact width. Missing/optimized/mismatched fields fail.
// This default never returns fabricated snapshots or successful profile flags.
template<class ActualHostModel> class GeneratedBinding {
public:
    explicit GeneratedBinding(ActualHostModel&) {throw Incomplete("generated Host leaf map unavailable");}
    void require_actual_profile()const {throw Incomplete("actual official resident/public21 profile unbound");}
    PreEdge read_stable_low()const {throw Incomplete("pre-edge generated leaf paths unbound");}
    PostEdge read_settled_high()const {throw Incomplete("post-edge generated leaf paths unbound");}
};
struct Qualification {
    bool raw_valid,resident_selected,group_matched,loan_matched,context_active;
    bool context_poison,context_abort,router_bad,bridge_bad,group_abort,group_reset;
    bool input_binary_add,vector_issue,phase_five,all_ready,vector_error,operands_match;
};
// This exact side-effect-free C++ expression is also extracted by Python cold
// tests. The flags are derived below from actual leaves + actual event ledger.
inline bool qualified(const Qualification& q) {
    return q.raw_valid && q.resident_selected && q.group_matched && q.loan_matched && q.context_active && !q.context_poison && !q.context_abort && !q.router_bad && !q.bridge_bad && !q.group_abort && !q.group_reset && !q.input_binary_add && q.vector_issue && q.phase_five && q.all_ready && !q.vector_error && q.operands_match;
}
struct ProvisionalSilu {
    uint64_t rising_edge;
    uint32_t group_identity,act_owner_tag;
    uint16_t ng,index,row_base,column;
    Words actual_materialized_phase4; // lane i => (batch0,row_base+i,column), unchanged u32 bits.
};
// Does not implement or replace PhysicalObserver's 11 methods. Captures remain
// provisional until enclosing owner/B/Host lifecycle and all27 checks succeed.
template<class Binding> class Observer {
    Binding& binding_;
    bool failed_=false,pending_edge_=false,have_edge_=false,group_live_=false,group_done_=false,bridge_live_=false;
    uint64_t edge_=0;PreEdge pre_{};
    uint32_t identity_=0,act_tag_=0;uint16_t next_ng_=0,index_=0;
    enum class Stage {GateRead,GateReply,UpRead,UpReply,Loan,BridgeEnd};
    Stage stage_=Stage::GateRead;
    std::optional<Key> outstanding_read_;Words gate_{};Operands loan_operands_{};
    std::optional<Key> loan_key_;bool raw_seen_=false;uint64_t captures_=0,loans_=0,results_=0;
    static constexpr uint32_t expected_group=(7u<<16)|17u,expected_act=(7u<<16)|18u;
    static constexpr uint64_t expected_vectors=128u*8960u/16u;
    static bool same_group(const Group&a,const Group&b) {
        return a.identity==b.identity&&a.gate_tag==b.gate_tag&&a.up_tag==b.up_tag&&a.act_tag==b.act_tag&&
               a.gate_rows==b.gate_rows&&a.up_rows==b.up_rows&&a.act_rows==b.act_rows;
    }
    bool selected(const PreEdge& f)const{return f.router_state==3; /* Scala Enum residentRun */}
    void healthy(const PreEdge& f)const {
        require(!f.router_fault&&!f.router_bad&&!f.backend_reset&&!f.host_abort&&!f.host_reset_required&&
                !f.group_abort&&!f.group_reset_required&&!f.bridge_bad&&!f.bridge_abort&&!f.bridge_poison&&
                !f.loan_context.poison&&!f.loan_context.abort,"resident/Host fault or abort is fatal");
    }
    void bank(const TileState& t,uint16_t consumed)const {
        require(t.live&&t.sealed&&t.identity==identity_&&t.ng==next_ng_&&t.rows==128&&t.cols==160&&
                t.expected==1280&&t.produced==1280&&t.consumed==consumed,"actual sealed tile identity/extent/counters");
    }
    void key(const Key& k,unsigned slot)const {
        require(k.identity==identity_&&k.ng==next_ng_&&k.index==index_&&k.slot==slot,"actual tile key identity/ng/index/slot");
    }
    void call(const Call& c)const {
        require(c.identity==identity_&&c.ng==next_ng_&&c.rows==128&&c.cols==160&&next_ng_<=8800&&next_ng_%160==0,
                "actual bridge invocation canonical bounds");
    }
    void loan_request(const PreEdge& f) {
        require(!loan_key_&&!f.loan_context.active&&f.silu_drained,"one actual idle loan");
        require(f.bridge_request.fire()&&f.router_resident_request.fire()&&f.router_shared_request.fire()&&
                f.owner_request.fire()&&f.vector_request.fire(),"matched resident-to-vector request handshakes");
        require(!f.router_shared_request.binary_add&&!f.owner_request.binary_add&&!f.vector_request.binary_add,
                "QKV binaryAdd cannot be canonical SiLU");
        Operands actual{gate_,f.tile_response.value};
        require(f.bridge_request.bits==actual&&f.router_resident_request.bits==actual&&f.router_shared_request.bits==actual&&
                f.owner_request.bits==actual&&f.vector_request.bits==actual,"gate/up response bytes match actual loan operands");
        require(f.vector_state==0,"vector request accepted from actual idle state");
        loan_operands_=actual;loan_key_=f.tile_response.key;raw_seen_=false;++loans_;stage_=Stage::Loan;
    }
    std::optional<ProvisionalSilu> consume(const PreEdge& f,const PostEdge& post) {
        std::optional<ProvisionalSilu> capture;
        const bool active_before=group_live_;
        const auto read_before=outstanding_read_;
        const bool loan_before=bool(loan_key_);
        if(group_done_) {healthy(f);require(!post.router_bad&&!post.bridge_bad&&!post.group_abort&&!post.group_reset_required&&
            !post.host_reset_required&&!post.loan_context.poison&&!post.loan_context.abort,"late fault poisons earlier captures");}
        if(f.host_group.fire()||f.resident_group.fire()) {
            require(!group_live_&&!group_done_&&!bridge_live_&&!loan_key_,"single canonical actual resident group");healthy(f);
            require(f.router_state==0&&f.host_group.fire()&&f.resident_group.fire()&&same_group(f.host_group,f.resident_group),
                    "matching actual Host/router/coordinator group acceptance");
            const auto& g=f.resident_group;
            require(g.identity==expected_group&&g.gate_tag==((7u<<16)|16u)&&g.up_tag==expected_group&&g.act_tag==expected_act&&
                    g.gate_rows==128&&g.up_rows==128&&g.act_rows==128,"group17 and actual act18 are distinct fields");
            require(post.router_state==3&&!f.loan_context.active,"resident selected from drained loan after actual group edge");
            identity_=g.identity;act_tag_=g.act_tag;group_live_=true;
        }
        // The entry edge cannot also masquerade as a prior resident operation.
        if(f.raw_silu_valid)require(active_before,"raw valid alone cannot establish group provenance");
        if(!active_before) {
            require(!f.bridge_start.fire()&&!f.bridge_complete&&!f.tile_read.fire()&&!f.tile_response.fire()&&
                    !f.bridge_request.fire()&&!f.bridge_result.fire()&&!f.group_result.fire(),"unmatched resident bridge/group event");
            return capture; // Other legitimate QKV loan activity is not SiLU capture.
        }
        healthy(f);require(selected(f),"actual router must retain resident selection");
        require(f.loan_context.active==loan_before,"continuous actual active debt matches accepted loan ledger");
        if(loan_before)require(f.vector_input==loan_operands_&&!f.input_binary_add&&!f.vector_error,"retained actual loan operands/mode/error");
        require(f.bridge_request.fire()==f.router_resident_request.fire()&&f.bridge_request.fire()==f.router_shared_request.fire()&&
                f.bridge_request.fire()==f.owner_request.fire()&&f.bridge_request.fire()==f.vector_request.fire(),"no untracked actual resident request");
        require(f.bridge_result.fire()==f.router_resident_result.fire()&&f.bridge_result.fire()==f.router_shared_result.fire()&&
                f.bridge_result.fire()==f.owner_result.fire()&&f.bridge_result.fire()==f.vector_result.fire(),"no untracked actual resident result");
        require(!post.router_bad&&!post.bridge_bad&&!post.group_abort&&!post.group_reset_required&&!post.host_reset_required&&
                !post.loan_context.poison&&!post.loan_context.abort,"same-edge post fault revokes provisional capture");
        if(f.bridge_start.fire()) {
            require(!bridge_live_&&!loan_key_&&!outstanding_read_&&index_==0,"no overlapping bridge invocation");
            call(f.start_call);bank(f.tiles[0],0);bank(f.tiles[1],0);
            require(!f.tiles[2].live&&f.tiles_drained&&f.silu_drained&&!f.loan_context.active&&f.bridge_state==0,
                    "accepted start uses real drained bank/SFU state");
            bridge_live_=true;stage_=Stage::GateRead;
        }
        if(f.tile_read.fire()) {
            require(bridge_live_&&!outstanding_read_&&!loan_key_,"actual read has unique outstanding identity");call(f.bridge_call);
            const bool gate=stage_==Stage::GateRead;
            require(gate||stage_==Stage::UpRead,"actual read order gate then up");
            require(f.bridge_state==(gate?2:4),"bridge gateRead/upRead state");key(f.tile_read.key,gate?0:1);bank(f.tiles[gate?0:1],index_);
            outstanding_read_=f.tile_read.key;stage_=gate?Stage::GateReply:Stage::UpReply;
        }
        if(f.tile_response.fire()) {
            require(bridge_live_&&read_before&&outstanding_read_&&f.tile_response.key==*read_before&&!f.tile_response.error,
                    "actual response must match previously accepted read");call(f.bridge_call);
            const bool gate=stage_==Stage::GateReply;require(gate||stage_==Stage::UpReply,"actual response stage");
            require(f.bridge_state==(gate?3:5),"bridge gateWait/upWait state");key(f.tile_response.key,gate?0:1);bank(f.tiles[gate?0:1],index_);
            outstanding_read_.reset();
            if(gate){require(!f.bridge_request.fire(),"gate response alone cannot loan");gate_=f.tile_response.value;stage_=Stage::UpRead;}
            else {loan_request(f);require(post.loan_context.active&&post.vector_state==1&&post.vector_phase==0,"actual loan latch after request edge");}
        } else require(!f.bridge_request.fire()&&!f.router_resident_request.fire(),"no resident loan without same-edge up response");
        if(f.raw_silu_valid) {
            const bool match=loan_key_&&loan_key_->identity==identity_&&loan_key_->ng==next_ng_&&loan_key_->index==index_&&
                             loan_key_->slot==1&&bridge_live_&&stage_==Stage::Loan&&!raw_seen_;
            const Qualification q{f.raw_silu_valid,selected(f),group_live_&&identity_==expected_group&&act_tag_==expected_act,match,
                f.loan_context.active,f.loan_context.poison,f.loan_context.abort,f.router_bad,f.bridge_bad,f.group_abort,f.group_reset_required,
                f.input_binary_add,f.vector_state==1,f.vector_phase==5,f.vector_all_ready,f.vector_error,f.vector_input==loan_operands_};
            require(qualified(q),"canonical SiLU requires matched resident live clean loan, not raw valid alone");call(f.bridge_call);
            require(f.bridge_state==6&&f.raw_silu_value==f.vector_value,"actual phase4 materialized register in bridge result wait");
            require(post.loan_context.active&&post.vector_state==2&&post.vector_phase==5,"phase5 actual issue edge");
            for(const auto word:f.raw_silu_value)require((word&0xffffu)==0&&(word&0x7f800000u)!=0x7f800000u,"finite materialized BF16 u32 bits, no conversion");
            raw_seen_=true;++captures_;
            const auto& actual_key=*loan_key_;
            capture=ProvisionalSilu{edge_,identity_,act_tag_,actual_key.ng,actual_key.index,
                uint16_t((actual_key.index/f.bridge_call.cols)*16),uint16_t(actual_key.ng+actual_key.index%f.bridge_call.cols),f.raw_silu_value};
        }
        if(f.bridge_result.fire()) {
            require(bridge_live_&&loan_before&&loan_key_&&raw_seen_&&!f.raw_silu_valid&&stage_==Stage::Loan&&f.bridge_state==6&&f.vector_state==3,"result cannot replace missing SiLU intermediate");
            require(f.router_resident_result.fire()&&f.router_shared_result.fire()&&f.owner_result.fire()&&f.vector_result.fire()&&f.tile_write.fire(),
                    "actual result/bridge tile-write same-edge retirement");
            require(!f.bridge_result.error&&!f.router_resident_result.error&&!f.router_shared_result.error&&!f.owner_result.error&&!f.vector_result.error,
                    "real numerical error is fatal");
            require(f.bridge_result.value==f.router_resident_result.value&&f.bridge_result.value==f.router_shared_result.value&&
                    f.bridge_result.value==f.owner_result.value&&f.bridge_result.value==f.vector_result.value&&f.tile_write.value==f.vector_result.value,
                    "actual phase5 product follows result path; never substitutes for SiLU");key(f.tile_write.key,2);
            require(f.loan_context.active&&!post.loan_context.active&&post.vector_state==0,"real loan result retires active debt");
            loan_key_.reset();raw_seen_=false;++results_;++index_;stage_=index_==1280?Stage::BridgeEnd:Stage::GateRead;
        } else require(!f.router_resident_result.fire()&&!f.tile_write.fire(),"no unmatched resident result/write");
        if(f.bridge_complete) {
            require(bridge_live_&&stage_==Stage::BridgeEnd&&index_==1280&&!loan_key_&&!outstanding_read_&&
                    f.bridge_state==10&&f.tiles_drained&&f.silu_drained&&!f.loan_context.active,"complete follows actual full bridge retirement");
            require(!f.tiles[0].live&&!f.tiles[1].live,"actual gate/up releases observed");bank(f.tiles[2],0);
            bridge_live_=false;index_=0;next_ng_+=160;
        }
        require(post.loan_context.active==bool(loan_key_),"post-edge actual active debt matches request/result retirement");
        if(f.group_result.fire()) {
            require(f.group_result.status==0&&f.group_result.tag==act_tag_&&next_ng_==8960&&!bridge_live_&&!loan_key_&&!outstanding_read_&&
                    captures_==expected_vectors&&loans_==captures_&&results_==captures_,"actual act18 result plus full SiLU coverage");
            require(post.router_state==0,"actual resident terminal handshake releases router");group_live_=false;group_done_=true;
        }
        return capture;
    }
public:
    explicit Observer(Binding& binding):binding_(binding){binding_.require_actual_profile();}
    void before_rising(uint64_t edge) {
        if(failed_)throw Violation("observer permanently failed");
        try {
            require(!pending_edge_&&(!have_edge_||edge==edge_+1),"one pre-edge snapshot per consecutive rising edge");
            pre_=binding_.read_stable_low();require(!pre_.clock&&!pre_.reset,"sample settled low clock after reset");
            edge_=edge;pending_edge_=true;
        } catch(...) {failed_=true;throw;}
    }
    std::optional<ProvisionalSilu> after_rising(uint64_t edge) {
        if(failed_)throw Violation("observer permanently failed");
        try {
            require(pending_edge_&&edge==edge_,"post-edge requires exact preceding snapshot");
            const auto post=binding_.read_settled_high();require(post.clock&&!post.reset,"observe actual settled high edge before commit");
            auto result=consume(pre_,post);pending_edge_=false;have_edge_=true;return result;
        } catch(...) {failed_=true;throw;}
    }
    void require_provisional_silu_coverage() {
        try {
            require(!failed_&&!pending_edge_&&group_done_&&!group_live_&&!bridge_live_&&!loan_key_&&!outstanding_read_&&
                    captures_==expected_vectors&&results_==captures_&&loans_==captures_,"SiLU capture incomplete or poisoned");
            // No DDR B retirement / 17-owner / 27-node / normal Host terminal claim.
        } catch(...) {failed_=true;throw;}
    }
};
template<class ActualHostModel> using ActualHostObserver=Observer<GeneratedBinding<ActualHostModel>>;
} // namespace canonical_host::silu_observation

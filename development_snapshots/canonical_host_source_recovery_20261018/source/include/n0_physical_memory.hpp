// SOURCE ONLY. One actual HostMemory, concrete N0 scalar B/SSA observation slice.
#pragma once
#include "n0_fields.hpp"
#include "axi_service.hpp"
#include "sink_stream_bridge.hpp"
namespace canonical_host::n0_physical {
class N0PhysicalMemory final : private PhysicalObserver {
    template<class> friend class AxiService;
    VHostBlockTop& model_;
    N0Fields fields_;
    HostMemory memory_{*this};
    AxiService<N0PhysicalMemory> axi_{memory_,*this};
    mutable bool failed_=false;
    bool pending_edge_=false,have_edge_=false,launched_=false,accepted_=false,done_=false,published_=false;
    bool retiring_=false,b_window_=false;
    mutable bool b_ack_checked_=false;
    uint64_t edge_=0,committed_bytes_=0,b_count_=0;
    uint16_t actual_epoch_=0,pre_launch_epoch_=0;
    bool pre_launch_fire_=false,pre_completion_fire_=false;
    Job accepted_job_{};Frame pre_{};
    actual_v2::HostFields::InputSnapshot inputs_{};
    struct WriteDebt {
        Request request;uint64_t transport_tag;
        bool dma_accepted=false,b_committed=false,dma_returned=false;
        WritePermit permit;
    };
    std::optional<WriteDebt> write_;
    std::optional<uint64_t> held_completion_;
    HubCounts held_hub_{};Ledger held_axi_{};
    void live()const {require(!failed_,"N0 physical memory permanently failed");}
    template<class F> auto checked(F&& f)const -> decltype(f()) {
        try{live();return f();}catch(...){failed_=true;throw;}
    }
    [[noreturn]] void missing(const char* why)const {
        failed_=true;throw silu_observation::Incomplete(why);
    }
    static bool same(const WritePermit& a,const WritePermit& b) {
        return a.public_pc==b.public_pc&&a.tag==b.tag&&a.generation==b.generation&&a.prefix==b.prefix;
    }
    static bool n0_span(uint64_t a,uint64_t n) {
        const auto& o=outputs[0];return n && a>=o.base && a-o.base<=o.bytes && n<=o.bytes-(a-o.base);
    }
    static void healthy(const Frame& f) {
        require(!f.owner_rejected&&!f.owner_poison&&!f.core_poison&&!f.hub_poison&&!f.dma_poison&&
            !f.router_bad&&!f.router_fault&&!f.writeback_error,"actual N0 physical poison/error");
    }
    void active_owner(const Frame& f)const {
        require(accepted_&&!done_&&f.owner_active&&f.owner_mode==0&&f.router_state==1&&
            f.owner_tag==accepted_job_.tag&&f.retained==accepted_job_&&!f.core_residual&&!f.cmd_pending,
            "actual accepted N0 owner must remain selected and unchanged");
    }
    void canonical_launch()const {
        require(model_.io_launch_bits_epoch==epoch&&model_.io_launch_bits_commands==public_commands&&
            model_.io_launch_bits_descriptors==descriptor_records&&
            model_.io_launch_bits_commandBase==inputs[0].base&&model_.io_launch_bits_commandLimit==inputs[0].base+inputs[0].bytes&&
            model_.io_launch_bits_descriptorBase==inputs[1].base&&model_.io_launch_bits_descriptorLimit==inputs[1].base+inputs[1].bytes,
            "actual canonical metadata launch");
#define N0_REGION(I) require(model_.io_launch_bits_regions_##I##_base==regions[I].base && \
        model_.io_launch_bits_regions_##I##_limit==regions[I].limit && \
        bool(model_.io_launch_bits_regions_##I##_read)==regions[I].read && \
        bool(model_.io_launch_bits_regions_##I##_write)==regions[I].write,"actual canonical region")
        N0_REGION(0);N0_REGION(1);N0_REGION(2);N0_REGION(3);
#undef N0_REGION
    }
    void consume_internal(const Frame& post) {
        healthy(pre_);healthy(post);
        const bool job=pre_.job_valid&&pre_.job_ready;
        require(job==bool(pre_.core_start),"actual Host acceptance and core start must match in N0 slice");
        if(job) {
            require(launched_&&!accepted_&&!write_&&model_.io_issuedJobs==1,"single actual first N0 owner");
            const auto& j=pre_.bound;
            require(j.kind==0&&j.tag==owner_tag(0)&&j.m==rows&&j.n==1536&&j.k==1536&&
                j.a==inputs[15].base&&j.b==inputs[9].base&&j.c==0&&j.dst==outputs[0].base&&j.writeBytes==outputs[0].bytes,
                "actual canonical N0 descriptor identity");
            accepted_job_=j;accepted_=true;active_owner(post);
        }
        if(pre_.memory_valid&&pre_.memory_ready&&pre_.core.write) {
            active_owner(pre_);require(!write_,"no second scalar write before original response");
            require(n0_span(pre_.core.address,64)&&pre_.core.address%64==0&&pre_.core.mask==~uint64_t(0),"N0 exact full 64B scalar store");
            require((pre_.core.tag>>32)==actual_epoch_,"actual scalar request epoch");
            require(pre_.hub_capture_ready&&pre_.hub_capture_valid&&post.hub_state==1&&post.hub_owner==1&&post.hub_original_tag==pre_.core.tag&&
                post.hub.same_payload(pre_.core),"same-edge accepted core store captured by owner hub client");
            // generation=0 is an unused NON-prefix observer field, never an RTL event.
            const WritePermit p{unsigned(accepted_job_.tag&0xffffu),uint32_t(accepted_job_.tag),0,false};
            write_=WriteDebt{pre_.core,post.hub.tag,false,false,false,p};
        }
        if(pre_.hub_state==1&&pre_.hub_ready&&pre_.hub.write) {
            require(write_&&!write_->dma_accepted&&!write_->b_committed,"unique owner store issued to actual DMA");
            active_owner(pre_);
            require(pre_.hub_owner==1&&pre_.hub_original_tag==write_->request.tag&&pre_.hub.tag==write_->transport_tag&&
                pre_.hub.same_payload(write_->request)&&post.dma.same_payload(pre_.hub)&&post.dma.tag==pre_.hub.tag,
                "actual owner/hub transport tag and DMA capture chain");
            require(post.hub_state==2&&post.dma_state==1&&!post.dma_stream&&!post.dma_write_burst&&!post.dma_error,"actual DMA accepted clean scalar write");
            write_->dma_accepted=true;
        }
        if(pre_.hub_state==2&&pre_.hub_response_valid&&write_) {
            require(write_->b_committed&&!write_->dma_returned&&pre_.hub_owner==1&&
                pre_.dma.tag==write_->transport_tag&&!pre_.dma_error&&post.hub_state==3&&
                post.hub_reply_tag==write_->request.tag&&!post.hub_reply_error,
                "actual DMA reply follows B and restores the original owner tag");
            write_->dma_returned=true;
        }
        if(pre_.response_fire&&write_) {
            active_owner(pre_);
            require(write_->b_committed&&write_->dma_returned&&pre_.hub_state==3&&pre_.hub_owner==1&&
                pre_.hub_reply_tag==write_->request.tag&&!pre_.hub_reply_error,"owner response must follow its real successful B commit");
            require(pre_.writeback_pending&&pre_.writeback_write&&pre_.writeback_tag==write_->request.tag&&
                pre_.writeback_byte_count==64&&pre_.writeback_total<=outputs[0].bytes-64&&
                post.writeback_total==pre_.writeback_total+64&&!post.writeback_pending,
                "actual writeback fence acknowledges precisely this B-retired scalar store");
            write_.reset();
        }
        const bool owner_done=pre_.done_valid&&pre_.done_ready;
        const bool core_done=pre_.core_result_valid&&pre_.core_selected&&pre_.router_state==1&&pre_.done_ready;
        if(owner_done||core_done) {
            require(owner_done&&core_done,"actual selected core/owner result handshakes agree");active_owner(pre_);
            require(!write_&&!b_window_&&pre_.core_status==0&&pre_.done_status==0&&pre_.done_bytes==outputs[0].bytes&&!pre_.writeback_pending&&
                pre_.writeback_total==outputs[0].bytes&&committed_bytes_==outputs[0].bytes,
                "N0 result cannot precede all real B and original response retirements");
            require(!post.owner_active&&post.router_state==0,"actual owner release after result");done_=true;
        }
        if(accepted_&&!done_)active_owner(post);
    }
    void begin_b(const Address& a,const std::vector<WriteBeat>& beats,const WritePermit& p,const Sample& s) {
        require(retiring_&&!b_window_&&write_&&write_->dma_accepted&&!write_->b_committed,
            "real sampled B authorization is unique and has prior DMA debt");
        active_owner(pre_);
        require(s.bf()&&pre_.axi.bf()&&s.b==pre_.axi.b&&s.b.resp==0&&s.b.id==a.id,
            "only successful actual pre-edge B handshake may publish");
        require(a.addr==write_->request.address&&a.len==0&&a.size==6&&a.burst==1&&beats.size()==1&&
            beats[0].last&&beats[0].strb==write_->request.mask&&beats[0].data==write_->request.data&&same(p,write_->permit),
            "actual AW/full W payload and frozen accepted owner permit");
        require(pre_.dma.same_payload(write_->request)&&pre_.dma.tag==write_->transport_tag&&!pre_.dma_error&&!pre_.dma_stream&&!pre_.dma_write_burst,
            "original DMA request identity retained through external B");
        b_window_=true;b_ack_checked_=false;
    }
    void end_b() {
        require(b_window_&&b_ack_checked_&&write_&&!write_->b_committed,"commit must consume exactly one B authorization");
        write_->b_committed=true;b_window_=false;b_ack_checked_=false;
        require(committed_bytes_<=outputs[0].bytes-64,"N0 B byte extent overflow");
        committed_bytes_+=64;++b_count_; // AFTER original HostMemory transaction mutation succeeds.
    }
    // This complete check covers every write this slice admits. It cannot bless
    // another owner, a prefix lease, a manually supplied sample, or a held B offer.
    void require_write_ack_owner(const WritePermit& p)const override {
        checked([&]{
            require(retiring_&&b_window_&&!b_ack_checked_&&write_&&write_->dma_accepted&&!write_->b_committed&&
                pre_.axi.bf()&&pre_.axi.b.resp==0&&same(p,write_->permit),"exact private B-retirement capability");
            active_owner(pre_);b_ack_checked_=true;
        });
    }
    WritePermit writer(uint64_t a,uint64_t n)const override {
        return checked([&]{
            if(!n0_span(a,n))missing("only N0 SSA writer bound; prefix/other owner lease is INCOMPLETE");
            require(retiring_&&write_&&write_->dma_accepted&&!write_->b_committed&&n==64&&a==write_->request.address,
                "writer needs exact actual accepted scalar DMA request");active_owner(pre_);
            require(b_window_||(pre_.axi.awf()&&pre_.axi.aw.addr==a&&pre_.axi.aw.len==0),"writer only at real AW or its B recheck");
            return write_->permit;
        });
    }
    void require_read_published(uint64_t a,uint64_t n,bool prefix,uint32_t generation)const override {
        checked([&]{
            if(prefix||!n0_span(a,n))missing("prefix generation/seed/readers or other SSA publication is INCOMPLETE");
            require(generation==prefix_generation&&published_&&done_&&committed_bytes_==outputs[0].bytes,
                "N0 read needs actual completion ACK and complete B publication");
            // HostMemory immediately checks its OWN initialized mask after this.
        });
    }
    void require_bound_to_actual_host()const override {checked([&]{missing("N0 B slice does not establish full Host reset/exclusive ownership or all physical domains");});}
    void require_completion_retired(unsigned)const override {checked([&]{missing("full completion physical debts INCOMPLETE");});}
    void begin_completion_hold(unsigned)override {checked([&]{missing("full completion hold INCOMPLETE");});}
    void require_completion_hold_quiescent(unsigned)const override {checked([&]{missing("full completion activity checkpoint INCOMPLETE");});}
    void end_completion_hold(unsigned)override {checked([&]{missing("full completion hold release INCOMPLETE");});}
    void begin_terminal_hold()override {checked([&]{missing("terminal full-domain checkpoint INCOMPLETE");});}
    void require_terminal_hold_quiescent()const override {checked([&]{missing("terminal full-domain quiet INCOMPLETE");});}
    void require_terminal_retired(const std::array<unsigned,17>&)const override {checked([&]{missing("17 owners and 27 captures INCOMPLETE");});}
public:
    explicit N0PhysicalMemory(VHostBlockTop& model):model_(model),fields_(model){}
    N0PhysicalMemory(const N0PhysicalMemory&)=delete;
    N0PhysicalMemory& operator=(const N0PhysicalMemory&)=delete;
    N0PhysicalMemory(N0PhysicalMemory&&)=delete;
    N0PhysicalMemory& operator=(N0PhysicalMemory&&)=delete;
private:
    // Private sink TYPE and object: the public generic bridge cannot use the
    // N0PhysicalMemory object as a StageSealSink or call its memory directly.
    class StageSealSink {
        N0PhysicalMemory& owner_;
    public:
        explicit StageSealSink(N0PhysicalMemory& owner):owner_(owner){}
        void stage_input(const std::string& name,uint64_t offset,ByteView bytes) {
            owner_.checked([&]{owner_.memory_.stage_input(name,offset,bytes);});
        }
        void verify_and_seal_inputs(const Sha256& sha,const CanonicalLoadReceipt& receipt) {
            owner_.checked([&]{owner_.memory_.verify_and_seal(sha,receipt);});
        }
    };
public:
    void require_ready()const{checked([&]{memory_.require_ready();});}
    ByteView read_input_span(size_t i,uint64_t off,uint64_t n)const{return checked([&]{return memory_.read_input_span(i,off,n);});}
    CompletedCanonicalSinkStream load(std::istream& source) {
        return checked([&]{StageSealSink sink(*this);CanonicalSinkStreamBridge bridge;return bridge.load(source,sink);});
    }
    // Caller owns launch/reset/completion pins. This slice never drives launch,
    // resets the DUT, or grants a full-driver admission. No external Sample API.
    void settle_low(uint64_t edge) {
        checked([&]{
            require(!pending_edge_&&(!have_edge_||(edge_!=~uint64_t(0)&&edge==edge_+1)),"one consecutive N0 edge");
            memory_.require_ready();require(!model_.reset&&!model_.io_resetRequired,"normal N0 observation only");
            axi_.drive(model_,edge);model_.clock=0;model_.eval();
            require(!model_.contextp()->gotFinish()&&!model_.contextp()->gotError(),"actual low eval failed");
            pre_=fields_.read(false);healthy(pre_);require(!model_.io_resetRequired,"actual low poison");
            if(!have_edge_)require(!pre_.owner_active&&!pre_.job_valid&&!pre_.core_start&&pre_.hub_state==0&&pre_.dma_state==0&&
                model_.io_issuedJobs==0&&actual_v2::HostFields::hub(model_)==HubCounts{},"observe idle before sole launch");
            if(!launched_)require(!pre_.axi.ar_valid&&!pre_.axi.aw_valid&&!pre_.axi.w_valid&&!pre_.job_valid,"traffic before actual launch");
            if(model_.io_launch_valid){require(!launched_,"duplicate launch offer");canonical_launch();}
            if(model_.io_completion_valid) {
                require(done_&&!published_&&!write_&&!pre_.axi.ar_valid&&!pre_.axi.aw_valid&&!pre_.axi.w_valid,"N0 completion after retired traffic");
                axi_.require_retired();const auto h=actual_v2::HostFields::hub(model_);
                require(h.accepted==h.returned&&!pre_.owner_active,"N0 actual hub and owner debt retired");
                const auto word=uint64_t(model_.io_completion_bits);
                require((word&((1ULL<<29)-1))==0&&((word>>29)&7)==completion_owners[0]&&((word>>32)&255)==0&&
                    (word>>40)==completion_signals[0],"actual first completion payload");
                require(!pre_.job_valid&&!pre_.core_start&&!pre_.memory_valid&&!pre_.response_fire,"no new local N0 traffic at visible completion");
                if(held_completion_)require(word==*held_completion_&&h==held_hub_&&axi_.ledger()==held_axi_,"held N0 completion activity changed");
                else {held_completion_=word;held_hub_=h;held_axi_=axi_.ledger();}
            }else require(!held_completion_,"N0 completion dropped before actual ACK");
            pre_launch_fire_=model_.io_launch_valid&&model_.io_launch_ready;
            pre_completion_fire_=model_.io_completion_valid&&model_.io_completion_ready;
            pre_launch_epoch_=model_.io_launch_bits_epoch;
            axi_.check_offers(pre_.axi,false);
            inputs_=actual_v2::HostFields::input_snapshot(model_);edge_=edge;pending_edge_=true;
        });
    }
    void rise_and_observe(uint64_t edge) {
        checked([&]{
            require(pending_edge_&&edge==edge_&&model_.clock==0&&actual_v2::HostFields::input_snapshot(model_)==inputs_,"same actual N0 edge/input snapshot");
            model_.clock=1;model_.eval();
            require(!model_.contextp()->gotFinish()&&!model_.contextp()->gotError()&&!model_.io_resetRequired,"actual high eval failed or poisoned");
            const auto post=fields_.read(true);healthy(post);
            if(pre_launch_fire_){require(!launched_&&!accepted_,"one launch");actual_epoch_=pre_launch_epoch_;launched_=true;}
            retiring_=true;consume_internal(post);axi_.advance(pre_.axi);
            require(!b_window_,"B authorization cannot escape its single commit call");
            if(pre_completion_fire_) {
                require(held_completion_&&done_&&!write_&&committed_bytes_==outputs[0].bytes&&b_count_==outputs[0].bytes/64,
                    "complete N0 B coverage before publication");
                published_=true;held_completion_.reset();
            }
            retiring_=false;pending_edge_=false;have_edge_=true;
        });
    }
    // Read actual owned RAM only; no expected/intermediate preload or mutable view.
    uint8_t actual_byte(uint64_t address)const {
        return checked([&]{require(!pending_edge_,"no comparator read inside pending edge");memory_.require_read(address,1);return memory_.actual_byte(address);});
    }
    void require_n0_published()const {checked([&]{require(!pending_edge_&&published_&&done_&&!write_&&!b_window_,"actual N0 publication incomplete");axi_.require_retired();});}
};
} // namespace canonical_host::n0_physical

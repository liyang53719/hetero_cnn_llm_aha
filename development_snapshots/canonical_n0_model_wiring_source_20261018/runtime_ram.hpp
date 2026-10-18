// Isolated runtime v1: one payload allocation, one mask, no public mutable span.
#pragma once
#include "runtime_policy.hpp"
#include "sha256.hpp"
#include "canonical16_identities.hpp"
#include "axi_protocol.hpp"
#include "n0_model_fields.hpp"
#include "canonical_launch.hpp"
#include "completion_payload.hpp"
#include <algorithm>
#include <array>
#include <istream>
#include <optional>
#include <string>
#include <vector>
namespace canonical_runtime_v1 {
using Sha256 = same_buffer_loader_v1::Sha256;
using canonical_host::Address;
using canonical_host::Data512;
using canonical_host::WriteBeat;
struct InputSpec { std::string name; std::uint64_t base, bytes; Sha256::Digest sha256; };
// A value describing an owner; never B authority by itself.
struct WritePermit {
    unsigned public_pc; std::uint32_t tag, generation; bool prefix;
    bool operator==(const WritePermit& p) const noexcept {
        return public_pc==p.public_pc && tag==p.tag && generation==p.generation && prefix==p.prefix;
    }
};
class RuntimeOwner;
#ifdef CANONICAL_RUNTIME_UNIT_TEST
class RuntimeTestAccess; // definition exists only in the unit-test TU
#endif
class RuntimeOwner final {
    class N0RetirementAdapter;
    template<class Model> class N0ModelScheduler;
#ifdef CANONICAL_RUNTIME_UNIT_TEST
    friend class RuntimeTestAccess;
#endif
    enum class Phase { Filling, TokenIssued, InputView, Runtime, Poisoned };
    struct OwnedAllocation { std::string name; std::uint64_t base,bytes,reserved; Access access; };
    struct Outstanding { const N0RetirementAdapter* adapter; Address address; WritePermit permit; std::uint64_t serial; };
    struct PreparedWrite { const Address* address; const std::vector<WriteBeat>* beats; std::uint64_t count; };
    const std::uint64_t base_,capacity_;
    const std::vector<Region> regions_;
    const std::vector<OwnedAllocation> allocations_;
    const std::vector<InputSpec> inputs_;
    std::vector<std::uint8_t> payload_,mask_;
    mutable Phase phase_=Phase::Filling;
    std::size_t next_=0;
    const N0RetirementAdapter* adapter_=nullptr;
    std::optional<Outstanding> outstanding_;
    std::uint64_t serial_=0;
    bool published_=false;
    static void require(bool ok,const char* why) { if(!ok) throw std::runtime_error(why); }
    template<class F> auto checked(F&& f) const -> decltype(f()) {
        try { require(phase_!=Phase::Poisoned,"runtime permanently poisoned"); return f(); }
        catch(...) {phase_=Phase::Poisoned;throw;}
    }
    static bool contains(std::uint64_t base,std::uint64_t bytes,std::uint64_t a,std::uint64_t n) noexcept {
        return n && a>=base && a-base<=bytes && n<=bytes-(a-base);
    }
    static std::vector<OwnedAllocation> own(const std::vector<Allocation>& source) {
        std::vector<OwnedAllocation> out;out.reserve(source.size());
        for(const auto& a:source) {
            require(a.name!=nullptr,"allocation name missing");
            out.push_back({std::string(a.name),a.base,a.bytes,a.reserved_bytes,a.access});
        }
        return out;
    }
    RuntimeOwner(const Policy& policy,const std::vector<InputSpec>& inputs)
      :base_(policy.base),capacity_(policy.bytes),regions_(policy.regions),allocations_(own(policy.allocations)),inputs_(inputs) {
        require(capacity_ && capacity_<=256ULL*1024*1024 && capacity_<=UINT64_MAX-base_,"bounded arena required");
        require(regions_.size()==4 && !inputs_.empty() && inputs_.size()<=64 && allocations_.size()<=64,"bounded metadata required");
        for(std::size_t i=0;i<regions_.size();++i) {
            const auto& r=regions_[i];require(r.limit>r.base && contains(base_,capacity_,r.base,r.limit-r.base),"region outside arena");
            for(std::size_t j=0;j<i;++j)require(r.base>=regions_[j].limit||regions_[j].base>=r.limit,"overlapping regions");
        }
        unsigned n0=0,input_allocations=0;
        for(std::size_t i=0;i<allocations_.size();++i) {
            const auto& a=allocations_[i];
            require(!a.name.empty() && a.name.size()<=128 && a.bytes<=a.reserved && contains(base_,capacity_,a.base,a.reserved),"allocation outside arena");
            (void)region(a.base,a.bytes,a.access==Access::N0);
            for(std::size_t j=0;j<i;++j) {
                const auto& b=allocations_[j];require(a.name!=b.name,"duplicate allocation name");
                require(a.base>=b.base+b.reserved||b.base>=a.base+a.reserved,"overlapping reservations");
            }
            if(a.access==Access::N0){require(a.name=="n0" && a.bytes<=786432 && a.bytes%64==0,"only bounded N0 writer");++n0;}
            if(a.access==Access::Input)++input_allocations;
        }
        require(n0==1 && input_allocations==inputs_.size(),"exact input/N0 policy required");
        for(std::size_t i=0;i<inputs_.size();++i) {
            const auto& in=inputs_[i];require(!in.name.empty()&&in.name.size()<=128,"input name bound");
            const auto& a=allocation(in.base,in.bytes);
            require(a.access==Access::Input&&a.name==in.name&&a.base==in.base&&a.bytes==in.bytes,"input policy differs");
            for(std::size_t j=0;j<i;++j)require(inputs_[j].name!=in.name,"duplicate input");
        }
        payload_.resize(static_cast<std::size_t>(capacity_),0);
        mask_.resize(static_cast<std::size_t>(capacity_),0); // never resized again
    }
    const Region& region(std::uint64_t address,std::uint64_t count,bool write) const {
        require(contains(base_,capacity_,address,count),"range outside arena/zero/overflow");
        for(const auto& r:regions_) if(contains(r.base,r.limit-r.base,address,count)) {
            require(r.read && (!write||r.write),"region permission denied");return r;
        }
        throw std::runtime_error("cross-region range");
    }
    const OwnedAllocation& allocation(std::uint64_t address,std::uint64_t count) const {
        for(const auto& a:allocations_)if(contains(a.base,a.bytes,address,count))return a;
        throw std::runtime_error("guard, reserved tail, unknown or cross-allocation range");
    }
    const OwnedAllocation& n0() const {
        for(const auto& a:allocations_)if(a.access==Access::N0)return a;
        throw std::runtime_error("N0 policy missing");
    }
    void require_mask(std::uint64_t address,std::uint64_t count) const {
        const auto start=static_cast<std::size_t>(address-base_);
        for(std::uint64_t i=0;i<count;++i)require(mask_[start+static_cast<std::size_t>(i)]==1,"uninitialized byte");
    }
    void verify_inputs() const {
        for(const auto& in:inputs_) {
            require_mask(in.base,in.bytes);
            require(Sha256::hash(payload_.data()+static_cast<std::size_t>(in.base-base_),static_cast<std::size_t>(in.bytes))==in.sha256,
                    "actual same-allocation input SHA256 mismatch");
        }
    }
    void read_permission(std::uint64_t address,std::uint64_t count,bool inputs_only=false) const {
        require(phase_==Phase::Runtime||phase_==Phase::InputView,"runtime token not redeemed");
        (void)region(address,count,false);const auto& a=allocation(address,count);
        require(a.access==Access::Input || (!inputs_only&&phase_==Phase::Runtime&&a.access==Access::N0),"allocation read denied");
        if(a.access==Access::N0)require(adapter_!=nullptr&&published_,"N0 completion not published");
        require_mask(address,count);
    }
    void stage_aw(const N0RetirementAdapter* adapter,const Address& a,const WritePermit& p) {
        require(phase_==Phase::Runtime&&adapter_==adapter&&adapter!=nullptr,"unbound runtime transport");
        require(!outstanding_ && serial_!=UINT64_MAX,"outstanding AW/serial exhausted");
        validate_address(a);const auto count=64ULL*(a.len+1);
        (void)region(a.addr,count,true);require(allocation(a.addr,count).access==Access::N0,"only N0 writes supported");
        require(p.public_pc==0&&p.tag==(7U<<16)&&p.generation==0&&!p.prefix,"N0 owner permit differs");
        const auto start=static_cast<std::size_t>(a.addr-base_);
        for(std::uint64_t i=0;i<count;++i)require(mask_[start+static_cast<std::size_t>(i)]==0,"AW SSA span is not fresh");
        outstanding_=Outstanding{adapter,a,p,++serial_}; // metadata only, never payload/mask
    }
    static void validate_address(const Address& a) {
        require(a.id<256&&a.len<256&&a.size==6&&a.burst==1&&a.addr%64==0,"64B INCR ID/len/alignment");
        const auto count=64ULL*(a.len+1);
        require((a.addr&4095ULL)+count<=4096 && a.addr<(1ULL<<56)&&count<=(1ULL<<56)-a.addr,"4KiB/56bit range");
    }
    PreparedWrite preflight_commit(const N0RetirementAdapter* adapter,const Address& a,
                                  const std::vector<WriteBeat>& beats,const WritePermit& p,std::uint64_t serial) {
        require(phase_==Phase::Runtime&&adapter_==adapter&&adapter!=nullptr,"unbound B transport");
        require(outstanding_&&outstanding_->adapter==adapter&&outstanding_->address==a&&outstanding_->permit==p&&
                outstanding_->serial==serial,"wrong or replayed private AW identity");
        validate_address(a);const auto bytes=64ULL*(a.len+1);
        (void)region(a.addr,bytes,true);require(allocation(a.addr,bytes).access==Access::N0,"B allocation denied");
        require(beats.size()==std::size_t(a.len)+1,"B beat count differs");
        std::uint64_t changed=0;
        for(std::size_t i=0;i<beats.size();++i) {
            const auto& w=beats[i];require(w.last==(i+1==beats.size())&&w.strb!=0,"WLAST/empty strobe");
            for(unsigned b=0;b<64;++b)if((w.strb>>b)&1ULL) {
                const auto offset=static_cast<std::size_t>(a.addr-base_)+64*i+b;
                require(mask_[offset]==0,"SSA byte overwrite");++changed;
            }
        }
        return PreparedWrite{&a,&beats,changed}; // fully checked, no payload/mask mutation
    }
    void commit_prevalidated(const PreparedWrite& tx) noexcept {
        // Only the private adapter calls this after its one-shot B gate. All
        // checks, allocations, owner debt and counter bounds precede this loop.
        for(std::size_t i=0;i<tx.beats->size();++i)for(unsigned b=0;b<64;++b) {
            const auto& w=(*tx.beats)[i];if((w.strb>>b)&1ULL) {
                const auto offset=static_cast<std::size_t>(tx.address->addr-base_)+64*i+b;
                payload_[offset]=static_cast<std::uint8_t>(w.data[b/4]>>(8*(b%4)));
                mask_[offset]=1;
            }
        }
        outstanding_.reset();
    }
    class N0RetirementAdapter final {
        template<class Model> friend class N0ModelScheduler;
    #ifdef CANONICAL_RUNTIME_UNIT_TEST
        friend class ::canonical_runtime_v1::RuntimeTestAccess;
    #endif
        RuntimeOwner& owner_;
        struct Debt {
            Address request;WriteBeat payload;WritePermit permit;
            std::uint64_t original_tag,transport_tag;
            bool dma_accepted=false,b_committed=false,dma_returned=false;
        };
        struct Pins {
            canonical_host::Sample axi;
            bool completion_valid=false,completion_ready=false;
            std::uint32_t completion_tag=0;std::uint16_t completion_epoch=0;
        };
        bool accepted_=false,done_=false,pending_=false,retiring_=false,b_window_=false,ack_checked_=false;
        bool have_edge_=false,held_b_=false;
        std::uint64_t edge_=0,committed_=0,b_count_=0,writeback_=0;
        Pins pre_{};
        bool completion_held_=false;
        std::optional<Debt> debt_;
        bool model_aw_id_pending_=false; // model scalar request has no AXI ID
        std::optional<Address> aw_;
        std::optional<WritePermit> permit_;
        std::uint64_t serial_=0;
        std::deque<WriteBeat> queue_;
        std::vector<WriteBeat> staged_;
        explicit N0RetirementAdapter(RuntimeOwner& owner):owner_(owner) {
            owner_.checked([&]{RuntimeOwner::require(owner_.phase_==RuntimeOwner::Phase::Runtime&&owner_.adapter_==nullptr,
                                                   "adapter requires this runtime session once");owner_.adapter_=this;});
        }
        ~N0RetirementAdapter() noexcept {
            if(owner_.adapter_==this){owner_.adapter_=nullptr;owner_.phase_=RuntimeOwner::Phase::Poisoned;}
        }
        N0RetirementAdapter(const N0RetirementAdapter&)=delete;
        N0RetirementAdapter& operator=(const N0RetirementAdapter&)=delete;
        static void require(bool ok,const char* why){RuntimeOwner::require(ok,why);}
        template<class F> auto checked(F&& f)->decltype(f()) {
            return owner_.checked([&]()->decltype(f()) {
                require(owner_.phase_==RuntimeOwner::Phase::Runtime&&owner_.adapter_==this,"foreign/dead adapter");return f();
            });
        }
        // These private events remain inaccessible in production until a concrete
        // generated-model scheduler binding is implemented and independently reviewed.
        // No friend named after an undefined, caller-definable production class.
        void accept_owner(unsigned pc,std::uint32_t tag,std::uint16_t epoch) {
            checked([&]{require(!accepted_&&!done_&&pc==0&&tag==(7U<<16)&&epoch==7,"fixed N0 owner identity");accepted_=true;});
        }
        void accept_request(const Address& a,const WriteBeat& w,std::uint64_t original,std::uint64_t transport,
                            const WritePermit& p) {
            checked([&]{require(accepted_&&!done_&&!debt_,"unique accepted N0 request");RuntimeOwner::validate_address(a);
                require(a.len==0&&w.last&&w.strb==UINT64_MAX,"real N0 scalar store is full 64B");
                require(RuntimeOwner::contains(owner_.n0().base,owner_.n0().bytes,a.addr,64),"request outside N0");
                require((original>>32)==7&&p.public_pc==0&&p.tag==(7U<<16)&&p.generation==0&&!p.prefix,"request epoch/owner/prefix");
                debt_=Debt{a,w,p,original,transport,false,false,false};
            });
        }
        void dma_accept(std::uint64_t original,std::uint64_t transport,const Address& request,const WriteBeat& data) {
            checked([&]{require(debt_&&!debt_->dma_accepted&&!debt_->b_committed&&debt_->original_tag==original&&
                debt_->transport_tag==transport&&debt_->request==request&&debt_->payload==data,"owner/hub/DMA identity differs");
                debt_->dma_accepted=true;
            });
        }
        void accept_model_request(std::uint64_t address,const WriteBeat& w,std::uint64_t original,
                                  std::uint64_t transport,const WritePermit& p) {
            // ID=0 is an explicitly UNBOUND placeholder, never accepted as wire evidence.
            accept_request({address,0,0,6,1},w,original,transport,p);
            model_aw_id_pending_=true;
        }
        WritePermit writer(const Address& a) {
            require(retiring_&&accepted_&&!done_&&debt_&&debt_->dma_accepted&&!debt_->b_committed,
                    "writer requires private retiring accepted DMA debt");
            if(model_aw_id_pending_) {
                require(!b_window_&&pre_.axi.awf()&&a.addr==debt_->request.addr&&a.len==0&&a.size==6&&a.burst==1,
                        "model AXI ID binds only at its real first AW fire");
                RuntimeOwner::validate_address(a);debt_->request=a;model_aw_id_pending_=false;
            }
            require(a==debt_->request&&(b_window_||pre_.axi.awf()),"writer needs exact AW/B window");
            return debt_->permit;
        }
        void require_write_ack_owner(const WritePermit& p) {
            require(retiring_&&b_window_&&!ack_checked_&&debt_&&debt_->dma_accepted&&!debt_->b_committed&&
                    pre_.axi.bf()&&pre_.axi.b.resp==0&&debt_->permit==p,"private B gate not live/unique");
            ack_checked_=true;
        }
        void stage_complete() {
            if(!aw_||queue_.size()<std::size_t(aw_->len)+1)return;
            require(!held_b_&&staged_.empty(),"held B overwrite");
            std::vector<WriteBeat> candidate;candidate.reserve(std::size_t(aw_->len)+1);
            for(unsigned i=0;i<=aw_->len;++i) {
                const auto w=queue_[i];require(w.last==(i==aw_->len)&&w.strb!=0,"W shape differs");candidate.push_back(w);
            }
            require(debt_&&aw_->len==0&&candidate.size()==1&&candidate[0]==debt_->payload,"accepted original payload differs");
            for(unsigned i=0;i<=aw_->len;++i)queue_.pop_front();
            staged_=std::move(candidate);held_b_=true; // staging and held B do not touch RAM
        }
        void retire_b() {
            require(retiring_&&held_b_&&aw_&&permit_&&debt_&&debt_->dma_accepted&&!debt_->b_committed&&!b_window_,
                    "B lacks original staged DMA debt");
            require(pre_.axi.bf()&&pre_.axi.b.resp==0&&pre_.axi.b.id==aw_->id,"exact pre-edge successful B required");
            require(*aw_==debt_->request&&staged_.size()==1&&staged_[0]==debt_->payload&&*permit_==debt_->permit,
                    "private original AW/W/permit identity differs");
            const auto tx=owner_.preflight_commit(this,*aw_,staged_,*permit_,serial_);
            // All counter bounds are checked BEFORE payload mutation, unlike the
            // prior source end_b post-mutation bound. No callback runs after commit.
            require(tx.count==64&&committed_<=owner_.n0().bytes-64&&b_count_<owner_.n0().bytes/64,
                    "N0 B byte/count overflow");
            b_window_=true;ack_checked_=false;
            require(writer(*aw_)==*permit_,"owner permit changed");
            require_write_ack_owner(*permit_);
            owner_.commit_prevalidated(tx); // noexcept payload+mask loop, same backing
            end_b_noexcept();
        }
        void end_b_noexcept() noexcept {
            debt_->b_committed=true;committed_+=64;++b_count_;
            b_window_=false;ack_checked_=false;held_b_=false;
            staged_.clear();aw_.reset();permit_.reset();
        }
        void capture_low(std::uint64_t edge,const Pins& pins) {
            checked([&]{require(!pending_&&(!have_edge_||(edge_!=UINT64_MAX&&edge==edge_+1)),"one consecutive settled-low snapshot");
                // Exactly the original AxiService::drive ready schedule. While
                // held_b_ is true, AWREADY and WREADY are both false, including
                // the cycle in which B fires. This narrow service has no overlap.
                require(pins.axi.aw_ready==(!aw_&&!held_b_&&edge%5!=0) &&
                        pins.axi.w_ready==(queue_.size()<256&&!held_b_&&edge%3!=0),
                        "actual ready pins differ from fixed service schedule");
                require(pins.axi.b_valid==held_b_,"B offer not generated by private staging");
                if(held_b_)require(aw_&&pins.axi.b.id==aw_->id&&pins.axi.b.resp==0,"held B ID/RESP changed");
                if(pins.completion_valid) {
                    require(done_&&pins.completion_tag==(7U<<16)&&pins.completion_epoch==7,"completion identity before done");
                    completion_held_=true;
                } else require(!completion_held_,"held completion dropped before ACK");
                pre_=pins;edge_=edge;pending_=true;
            });
        }
        void retire_high(std::uint64_t edge) {
            checked([&]{require(pending_&&edge==edge_,"high does not match captured low");retiring_=true;
                // Actual future binding must first verify resident high then N0 high,
                // consume internal owner/hub/DMA events, then call this with no new Sample.
                if(pre_.axi.bf()) {
                    require(!pre_.axi.awf()&&!pre_.axi.wf()&&!pre_.completion_valid,
                            "held B retirement cannot share new AW/W/completion fire");
                    retire_b();
                    retiring_=false;pending_=false;have_edge_=true;
                    return; // after commit: no fallible branch, allocation or callback
                }
                if(pre_.axi.awf()) {
                    require(!aw_&&!held_b_,"AW debt overwrite");const auto p=writer(pre_.axi.aw);
                    owner_.stage_aw(this,pre_.axi.aw,p);aw_=pre_.axi.aw;permit_=p;serial_=owner_.outstanding_->serial;
                }
                if(pre_.axi.wf()){require(queue_.size()<256&&!held_b_,"W staging capacity/held B");queue_.push_back(pre_.axi.w);}
                stage_complete();
                if(pre_.completion_valid&&pre_.completion_ready) {
                    require(done_&&!debt_&&!aw_&&!held_b_&&queue_.empty()&&!b_window_&&committed_==owner_.n0().bytes&&
                            writeback_==committed_&&b_count_==owner_.n0().bytes/64,"completion cannot precede retirement");
                    owner_.require_mask(owner_.n0().base,owner_.n0().bytes);
                    require(!owner_.published_,"duplicate completion publication");owner_.published_=true;completion_held_=false;
                }
                retiring_=false;pending_=false;have_edge_=true;
            });
        }
        void dma_return(std::uint64_t original,std::uint64_t transport) {
            checked([&]{require(debt_&&debt_->b_committed&&!debt_->dma_returned&&debt_->original_tag==original&&
                               debt_->transport_tag==transport,"DMA response must follow B and restore original tag");debt_->dma_returned=true;});
        }
        void writeback_ack(std::uint64_t original,std::uint64_t bytes) {
            checked([&]{require(debt_&&debt_->b_committed&&debt_->dma_returned&&debt_->original_tag==original&&bytes==64&&
                               writeback_<=owner_.n0().bytes-64,"original owner response/writeback ACK differs");
                writeback_+=64;debt_.reset();});
        }
        void owner_done(std::uint64_t bytes,unsigned status) {
            checked([&]{require(accepted_&&!done_&&!debt_&&!held_b_&&!aw_&&queue_.empty()&&!b_window_&&status==0&&
                               bytes==owner_.n0().bytes&&writeback_==bytes&&committed_==bytes,"owner done before full original responses");done_=true;});
        }
    };
    
#include "n0_model_scheduler.inc"
public:
    class ReadyToken final {
        friend class RuntimeOwner;RuntimeOwner* owner_;
        explicit ReadyToken(RuntimeOwner& o):owner_(&o){}
    public:
        ReadyToken(const ReadyToken&)=delete;ReadyToken& operator=(const ReadyToken&)=delete;
        ReadyToken(ReadyToken&&)=delete;ReadyToken& operator=(ReadyToken&&)=delete;
    };
    class ReadOnlyInputs final {
        friend class RuntimeOwner;RuntimeOwner& owner_;
        explicit ReadOnlyInputs(RuntimeOwner& o):owner_(o){}
    public:
        ReadOnlyInputs(const ReadOnlyInputs&)=delete;ReadOnlyInputs& operator=(const ReadOnlyInputs&)=delete;
        ReadOnlyInputs(ReadOnlyInputs&&)=delete;ReadOnlyInputs& operator=(ReadOnlyInputs&&)=delete;
        std::uint8_t actual_byte(std::uint64_t a) const {return owner_.checked([&]{owner_.read_permission(a,1,true);return owner_.payload_[static_cast<std::size_t>(a-owner_.base_)];});}
    };
    class RuntimeSession final {
        friend class RuntimeOwner;RuntimeOwner& owner_;
        explicit RuntimeSession(RuntimeOwner& o):owner_(o){}
    public:
        RuntimeSession(const RuntimeSession&)=delete;RuntimeSession& operator=(const RuntimeSession&)=delete;
        RuntimeSession(RuntimeSession&&)=delete;RuntimeSession& operator=(RuntimeSession&&)=delete;
        void require_ready() const {owner_.checked([&]{require(owner_.phase_==Phase::Runtime,"runtime not ready");});}
        void require_read(std::uint64_t a,std::uint64_t n) const {owner_.checked([&]{owner_.read_permission(a,n);});}
        std::uint8_t actual_byte(std::uint64_t a) const {return owner_.checked([&]{owner_.read_permission(a,1);return owner_.payload_[static_cast<std::size_t>(a-owner_.base_)];});}
        Data512 read_beat(std::uint64_t a) const {
            return owner_.checked([&]{require(a%64==0,"read beat alignment");owner_.read_permission(a,64);Data512 out{};
                for(unsigned b=0;b<64;++b) {
                    out[b/4]|=std::uint32_t(owner_.payload_[static_cast<std::size_t>(a-owner_.base_)+b])<<(8*(b%4));
                }
                return out;});
        }
        Sha256::Digest input_digest(std::size_t i) const {
            return owner_.checked([&]{require(i<owner_.inputs_.size(),"input digest index");const auto& in=owner_.inputs_[i];
                owner_.read_permission(in.base,in.bytes,true);return Sha256::hash(owner_.payload_.data()+static_cast<std::size_t>(in.base-owner_.base_),static_cast<std::size_t>(in.bytes));});
        }
    };
    static RuntimeOwner canonical() {
        std::vector<InputSpec> fixed;fixed.reserve(expected_inputs.size());
        for(const auto& r:expected_inputs)fixed.push_back({r.name,r.base,r.bytes,r.sha256});
        return RuntimeOwner(canonical_policy(),fixed);
    }
    RuntimeOwner(const RuntimeOwner&)=delete;RuntimeOwner& operator=(const RuntimeOwner&)=delete;
    RuntimeOwner(RuntimeOwner&&)=delete;RuntimeOwner& operator=(RuntimeOwner&&)=delete;
    void load_next(const std::string& name,std::istream& stream) {
        checked([&]{require(phase_==Phase::Filling&&next_<inputs_.size(),"unexpected input phase/count");
            const auto& in=inputs_[next_];require(name==in.name&&stream.good(),"input name/order/state differs");
            Sha256 hash;std::array<std::uint8_t,65536> chunk{};std::uint64_t offset=0;
            while(offset<in.bytes) {
                const auto count=static_cast<std::size_t>(std::min<std::uint64_t>(chunk.size(),in.bytes-offset));
                stream.read(reinterpret_cast<char*>(chunk.data()),static_cast<std::streamsize>(count));
                require(stream.good()&&stream.gcount()==static_cast<std::streamsize>(count),"input short/bad stream");
                const auto start=static_cast<std::size_t>(in.base-base_+offset);
                for(std::size_t i=0;i<count;++i)require(mask_[start+i]==0,"duplicate initialization byte");
                for(std::size_t i=0;i<count;++i){payload_[start+i]=chunk[i];mask_[start+i]=1;}
                hash.update(chunk.data(),count);offset+=count;
            }
            char tail=0;stream.read(&tail,1);
            require(stream.gcount()==0&&stream.eof()&&stream.fail()&&!stream.bad(),"strict input EOF required");
            require(hash.finish()==in.sha256,"input stream SHA256 differs");++next_;
        });
    }
    ReadyToken finish() {
        return checked([&]()->ReadyToken{require(phase_==Phase::Filling&&next_==inputs_.size(),"incomplete/duplicate finish");
            verify_inputs();phase_=Phase::TokenIssued;return ReadyToken(*this);});
    }
    RuntimeSession take_runtime(ReadyToken& token) {
        return checked([&]()->RuntimeSession{require(phase_==Phase::TokenIssued&&token.owner_==this,"wrong/consumed token");
            verify_inputs();token.owner_=nullptr;phase_=Phase::Runtime;return RuntimeSession(*this);});
    }
    ReadOnlyInputs take_ready(ReadyToken& token) {
        return checked([&]()->ReadOnlyInputs{require(phase_==Phase::TokenIssued&&token.owner_==this,"wrong/consumed token");
            verify_inputs();token.owner_=nullptr;phase_=Phase::InputView;return ReadOnlyInputs(*this);});
    }
};
} // namespace canonical_runtime_v1

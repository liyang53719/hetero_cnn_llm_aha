// Real tiny behavior tests, SOURCE ONLY until a separate bounded native gate.
// This macro is exclusive to this TU; no production factory parameter enables it.
#define CANONICAL_RUNTIME_UNIT_TEST 1
#include "canonical16_runtime_binding.hpp"
#include "n0_retirement_adapter.hpp"
#include "host_memory.hpp"
#include <functional>
#include <iostream>
#include <sstream>
#include <type_traits>
namespace canonical_runtime_v1 {
class RuntimeTestAccess final {
    static Policy policy() {
        return {4096,1024,{{4224,4480,true,false},{4480,4864,true,true},{4096,4224,true,false},{4864,5120,true,true}},
            {{"commands",4096,64,64,Access::Input},{"w",4288,64,128,Access::Input},{"n0",4544,128,128,Access::N0},
             {"gate",4736,64,64,Access::Denied},{"scores",4800,64,64,Access::Denied},{"workspace",4864,256,256,Access::Workspace}}};
    }
    static std::vector<InputSpec> inputs() {
        const std::string a(64,'A'),b(64,'B');
        return {{"commands",4096,64,Sha256::hash(reinterpret_cast<const std::uint8_t*>(a.data()),a.size())},
                {"w",4288,64,Sha256::hash(reinterpret_cast<const std::uint8_t*>(b.data()),b.size())}};
    }
    static void load(RuntimeOwner& owner) {
        std::istringstream a(std::string(64,'A')),b(std::string(64,'B'));
        owner.load_next("commands",a);owner.load_next("w",b);
    }
    static RuntimeOwner::RuntimeSession ready(RuntimeOwner& owner) {
        load(owner);auto token=owner.finish();return owner.take_runtime(token);
    }
    RuntimeOwner owner_;
    const std::uint8_t* allocation_at_construction_;
    RuntimeOwner::RuntimeSession session_;
    RuntimeOwner::N0RetirementAdapter adapter_;
    std::uint64_t edge_=1,sequence_=0;
    Address request_{};WriteBeat beat_{};
    std::uint64_t original_=0,transport_=0;
    void edge(RuntimeOwner::N0RetirementAdapter::Pins pins) {
        adapter_.capture_low(edge_,pins);adapter_.retire_high(edge_);++edge_;
    }
    RuntimeOwner::N0RetirementAdapter::Pins pins() const {
        RuntimeOwner::N0RetirementAdapter::Pins p;p.axi.b_valid=adapter_.held_b_;
        p.axi.aw_ready=!adapter_.aw_&&!adapter_.held_b_&&edge_%5!=0;
        p.axi.w_ready=adapter_.queue_.size()<256&&!adapter_.held_b_&&edge_%3!=0;
        if(adapter_.aw_)p.axi.b.id=adapter_.aw_->id;
        return p;
    }
public:
    using Adapter = RuntimeOwner::N0RetirementAdapter;
    RuntimeTestAccess():owner_(policy(),inputs()),allocation_at_construction_(owner_.payload_.data()),
                       session_(ready(owner_)),adapter_(owner_){}
    struct Snapshot {
        std::vector<std::uint8_t> payload,mask;
        bool operator==(const Snapshot& b)const{return payload==b.payload&&mask==b.mask;}
    };
    Snapshot snapshot()const{return {owner_.payload_,owner_.mask_};}
    bool same_allocation()const{return allocation_at_construction_==owner_.payload_.data();}
    bool poisoned()const{return owner_.phase_==RuntimeOwner::Phase::Poisoned;}
    std::uint8_t mask(std::uint64_t a)const{return owner_.mask_[static_cast<std::size_t>(a-owner_.base_)];}
    std::uint8_t raw_byte(std::uint64_t a)const{return owner_.payload_[static_cast<std::size_t>(a-owner_.base_)];}
    std::uint8_t actual(std::uint64_t a)const{return session_.actual_byte(a);}
    Data512 read_beat(std::uint64_t a)const{return session_.read_beat(a);}
    void read(std::uint64_t a,std::uint64_t n)const{session_.require_read(a,n);}
    Sha256::Digest input_digest()const{return session_.input_digest(1);}
    bool published()const{return owner_.published_;}
    static WritePermit permit(){return {0,7U<<16,0,false};}
    static WriteBeat data(bool last=true,std::uint64_t strobe=UINT64_MAX) {
        WriteBeat w;w.data.fill(0x44332211);w.strb=strobe;w.last=last;return w;
    }
    void accept(std::uint64_t address=4544) {
        if(!adapter_.accepted_)adapter_.accept_owner(0,7U<<16,7);
        request_={address,3,0,6,1};beat_=data();original_=(7ULL<<32)|++sequence_;transport_=0x100+sequence_;
        adapter_.accept_request(request_,beat_,original_,transport_,permit());
        adapter_.dma_accept(original_,transport_,request_,beat_);
    }
    void bad_owner(unsigned pc,std::uint32_t tag,std::uint16_t epoch){adapter_.accept_owner(pc,tag,epoch);}
    void bad_dma(){adapter_.dma_accept(original_+1,transport_,request_,beat_);}
    void stage(bool w_first=false) {
        bool need_aw=true,need_w=true;
        if(w_first) {
            while(need_w) {auto p=pins();p.axi.w_valid=true;p.axi.w=beat_;
                const bool fired=p.axi.w_ready;edge(p);if(fired)need_w=false;}
        }
        while(need_aw||need_w) {
            auto p=pins();p.axi.aw_valid=need_aw;p.axi.aw=request_;p.axi.w_valid=need_w;p.axi.w=beat_;
            const bool aw=need_aw&&p.axi.aw_ready,w=need_w&&p.axi.w_ready;
            edge(p);if(aw)need_aw=false;if(w)need_w=false;
        }
        if(!adapter_.held_b_)throw std::runtime_error("unit expected held B after accepted AW/W");
    }
    void hold_b(){auto p=pins();p.axi.b_ready=false;edge(p);}
    void b(){auto p=pins();p.axi.b_ready=true;edge(p);}
    void bad_b(unsigned id,unsigned resp){auto p=pins();p.axi.b_ready=true;p.axi.b.id=id;p.axi.b.resp=resp;edge(p);}
    void b_with_aw(){auto p=pins();p.axi.b_ready=true;p.axi.aw_valid=true;p.axi.aw_ready=true;p.axi.aw=request_;edge(p);}
    void fake_b_without_debt(){auto p=pins();p.axi.b_valid=true;p.axi.b_ready=true;p.axi.b.id=3;edge(p);}
    void responses(){adapter_.dma_return(original_,transport_);adapter_.writeback_ack(original_,64);}
    void early_response(){adapter_.dma_return(original_,transport_);}
    void done(){adapter_.owner_done(128,0);}
    void completion(bool ready) {
        auto p=pins();p.completion_valid=true;p.completion_ready=ready;p.completion_tag=7U<<16;p.completion_epoch=7;edge(p);
    }
    void drop_completion(){edge(pins());}
    void full_n0() {
        accept(4544);stage(true);b();responses();accept(4608);stage();b();responses();done();
    }
    // Unit-only direct kernel route: exercises partial strobes and multi-beat
    // preflight, which the stricter real-N0 adapter intentionally does not admit.
    void kernel_commit(Address a,std::vector<WriteBeat> beats,WritePermit p=permit()) {
        owner_.checked([&]{owner_.stage_aw(&adapter_,a,p);const auto tx=owner_.preflight_commit(
            &adapter_,a,beats,p,owner_.outstanding_->serial);owner_.commit_prevalidated(tx);});
    }
    void wrong_permit_after_aw() {
        owner_.checked([&]{const Address a{4544,3,0,6,1};auto p=permit();owner_.stage_aw(&adapter_,a,p);
            ++p.tag;const std::vector<WriteBeat> beats{data()};(void)owner_.preflight_commit(&adapter_,a,beats,p,owner_.outstanding_->serial);});
    }
    void foreign_adapter(RuntimeTestAccess& other) {
        owner_.checked([&]{owner_.stage_aw(&other.adapter_,{4544,3,0,6,1},permit());});
    }
    void tamper_input_before_reverify() { // deliberate unit corruption, no public span
        owner_.payload_[0]^=1;owner_.checked([&]{owner_.verify_inputs();});
    }
    static bool token_and_early_failures() {
        RuntimeOwner a(policy(),inputs()),b(policy(),inputs());load(a);load(b);auto ta=a.finish();auto tb=b.finish();
        bool cross=false;try{auto invalid=b.take_runtime(ta);(void)invalid;}catch(const std::exception&){cross=b.phase_==RuntimeOwner::Phase::Poisoned;}
        auto view=a.take_ready(ta);if(view.actual_byte(4096)!='A')return false;
        bool twice=false;try{auto invalid=a.take_runtime(ta);(void)invalid;}catch(const std::exception&){twice=a.phase_==RuntimeOwner::Phase::Poisoned;}
        (void)tb;
        RuntimeOwner early(policy(),inputs());bool unready=false;
        try{early.checked([&]{early.read_permission(4096,1);});}catch(const std::exception&){unready=early.phase_==RuntimeOwner::Phase::Poisoned;}
        return cross&&twice&&unready;
    }
    static bool strict_stream_failures() {
        bool all=true;
        for(unsigned kind=0;kind<4;++kind) {
            RuntimeOwner o(policy(),inputs());std::string bytes(64,'A');if(kind==0)bytes.pop_back();if(kind==1)bytes.push_back('X');
            if(kind==2)bytes[0]='Z';
            std::istringstream stream(bytes);if(kind==3)stream.setstate(std::ios::badbit);
            try{o.load_next("commands",stream);all=false;}catch(const std::exception&){all&=o.phase_==RuntimeOwner::Phase::Poisoned;}
        }
        return all;
    }
    static bool copied_metadata() {
        auto p=policy();auto in=inputs();char alias[]="commands";p.allocations[0].name=alias;
        RuntimeOwner o(p,in);alias[0]='X';in[0].name="bad";p.regions[2].write=true;p.allocations[0].base=5000;
        load(o);auto token=o.finish();auto view=o.take_ready(token);return view.actual_byte(4096)=='A';
    }
};
} // namespace canonical_runtime_v1
using canonical_runtime_v1::RuntimeTestAccess;
static unsigned checks=0;
static void check(bool value){++checks;if(!value)throw std::runtime_error("unit check failed");}
template<class F>static void fails_unchanged(RuntimeTestAccess& f,F action) {
    const auto before=f.snapshot();bool threw=false;
    try{action();}catch(const std::exception&){threw=true;}
    check(threw);check(f.poisoned());check(f.snapshot()==before);
    bool permanent=false;try{(void)f.actual(4096);}catch(const std::exception&){permanent=true;}check(permanent);
}
static_assert(!std::is_constructible<RuntimeTestAccess::Adapter,canonical_runtime_v1::RuntimeOwner&>::value,
              "private adapter construction must remain inaccessible");
static_assert(!std::is_constructible<canonical_runtime_v1::RuntimeOwner,canonical_runtime_v1::Policy,std::vector<canonical_runtime_v1::InputSpec>>::value,
              "production policy override constructor is private");
int main(){try{
    check(RuntimeTestAccess::token_and_early_failures());check(RuntimeTestAccess::strict_stream_failures());check(RuntimeTestAccess::copied_metadata());
    {RuntimeTestAccess f;check(f.same_allocation());check(f.actual(4096)=='A');check(f.actual(4288)=='B');check(f.mask(4544)==0);
     check(f.read_beat(4096)[0]==0x41414141U);fails_unchanged(f,[&]{f.read(4544,64);});}
    for(const auto& range:std::vector<std::pair<std::uint64_t,std::uint64_t>>{{4160,1},{4352,1},{4480,1},{4736,1},{4800,1},{4864,1},
            {4159,2},{4479,2},{UINT64_MAX,2},{4096,0},{4096,UINT64_MAX}}) {
        RuntimeTestAccess f;fails_unchanged(f,[&]{f.read(range.first,range.second);});
    }
    for(std::uint64_t address:{4096ULL,4288ULL,4352ULL,4480ULL,4736ULL,4800ULL,4864ULL}) {
        RuntimeTestAccess f;fails_unchanged(f,[&]{f.kernel_commit({address,1,0,6,1},{RuntimeTestAccess::data()});});
    }
    {RuntimeTestAccess f;const auto before=f.snapshot();f.accept();f.stage(true);check(f.snapshot()==before);f.hold_b();check(f.snapshot()==before);
     f.b();check(f.same_allocation());check(f.mask(4544)==1);check(f.raw_byte(4544)==0x11);check(!f.published());
     fails_unchanged(f,[&]{f.read(4544,64);});}
    {RuntimeTestAccess f;f.accept();f.stage();fails_unchanged(f,[&]{f.bad_b(3,2);});}
    {RuntimeTestAccess f;f.accept();f.stage();fails_unchanged(f,[&]{f.bad_b(4,0);});}
    {RuntimeTestAccess f;f.accept();f.stage();fails_unchanged(f,[&]{f.b_with_aw();});}
    {RuntimeTestAccess f;fails_unchanged(f,[&]{f.fake_b_without_debt();});}
    {RuntimeTestAccess f;f.accept();f.stage();f.b();fails_unchanged(f,[&]{f.fake_b_without_debt();});}
    {RuntimeTestAccess f;fails_unchanged(f,[&]{f.bad_owner(1,7U<<16,7);});}
    {RuntimeTestAccess f;fails_unchanged(f,[&]{f.bad_owner(0,6U<<16,6);});}
    {RuntimeTestAccess f;f.accept();fails_unchanged(f,[&]{f.bad_dma();});}
    {RuntimeTestAccess f;f.accept();fails_unchanged(f,[&]{f.early_response();});}
    {RuntimeTestAccess f;fails_unchanged(f,[&]{f.wrong_permit_after_aw();});}
    {RuntimeTestAccess a,b;fails_unchanged(a,[&]{a.foreign_adapter(b);});check(!b.poisoned());}
    {RuntimeTestAccess f;f.kernel_commit({4544,2,0,6,1},{RuntimeTestAccess::data(true,5)});
     check(f.mask(4544)==1&&f.mask(4545)==0&&f.mask(4546)==1);check(f.raw_byte(4544)==0x11&&f.raw_byte(4545)==0&&f.raw_byte(4546)==0x33);
     check(!f.published());fails_unchanged(f,[&]{f.kernel_commit({4544,2,0,6,1},{RuntimeTestAccess::data()});});}
    {RuntimeTestAccess f;fails_unchanged(f,[&]{f.kernel_commit({4544,2,1,6,1},{RuntimeTestAccess::data(false),RuntimeTestAccess::data(false)});});}
    {RuntimeTestAccess f;fails_unchanged(f,[&]{f.kernel_commit({4608,2,1,6,1},{RuntimeTestAccess::data(false),RuntimeTestAccess::data()});});}
    {RuntimeTestAccess f;fails_unchanged(f,[&]{f.kernel_commit({4544,2,0,6,1},{RuntimeTestAccess::data(true,0)});});}
    {RuntimeTestAccess f;auto p=RuntimeTestAccess::permit();p.prefix=true;p.generation=1;
     fails_unchanged(f,[&]{f.kernel_commit({4864,2,0,6,1},{RuntimeTestAccess::data()},p);});}
    {RuntimeTestAccess f;fails_unchanged(f,[&]{f.done();});}
    {RuntimeTestAccess f;f.full_n0();f.completion(false);check(!f.published());fails_unchanged(f,[&]{f.read(4544,128);});}
    {RuntimeTestAccess f;f.full_n0();f.completion(false);fails_unchanged(f,[&]{f.drop_completion();});}
    {RuntimeTestAccess f;const auto input=f.input_digest();f.full_n0();f.completion(false);check(!f.published());f.completion(true);
     check(f.published());check(f.same_allocation());check(f.input_digest()==input);check(f.read_beat(4544)[0]==0x44332211);
     check(f.actual(4671)==0x44);fails_unchanged(f,[&]{f.completion(true);});}
    {RuntimeTestAccess f;bool rejected=false;try{f.tamper_input_before_reverify();}catch(const std::exception&){rejected=true;}check(rejected&&f.poisoned());}
    std::cout<<"{\"status\":\"RUNTIME_MEMORY_UNIT_BEHAVIOR_PASS\",\"checks\":"<<checks
      <<",\"max_synthetic_arena_bytes\":1024,\"adapter_runtime_bound\":false,\"canonical_input_sha_verified\":false,\"full_host_ready\":false,\"launch_ready\":false,\"eda_executed\":false}\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}

// TEST ONLY: actual private C++ methods with scripted existing field storage.
// No generated model, reset/profile admission, real owner computation or ABI proof.
#include "fixture_model.hpp"
#include <sstream>
#include <utility>
namespace canonical_runtime_v1 {
class RuntimeTestAccess final {
    using Scheduler=RuntimeOwner::N0ModelScheduler<wiring_test::ScriptedFieldFixture>;
    static Policy policy() {
        return {4096,1024,{{4224,4480,true,false},{4480,4864,true,true},
                          {4096,4224,true,false},{4864,5120,true,true}},
            {{"commands",4096,64,64,Access::Input},{"n0",4544,64,64,Access::N0},
             {"workspace",4864,256,256,Access::Workspace}}};
    }
    static std::vector<InputSpec> inputs() {
        const std::string raw(64,'A');
        return {{"commands",4096,64,Sha256::hash(
            reinterpret_cast<const std::uint8_t*>(raw.data()),raw.size())}};
    }
    static RuntimeOwner::RuntimeSession ready(RuntimeOwner& owner) {
        std::istringstream stream(std::string(64,'A'));owner.load_next("commands",stream);
        auto token=owner.finish();return owner.take_runtime(token);
    }
    RuntimeOwner owner_;
    const std::uint8_t* allocation_;
    RuntimeOwner::RuntimeSession session_;
    wiring_test::ScriptedFieldFixture model_;
    Scheduler scheduler_;
    std::uint64_t next_=1;
    static constexpr std::uint64_t original_=(7ULL<<32)|1,transport_=41;
    static WriteBeat data() {WriteBeat w;w.data.fill(0x44332211);w.strb=UINT64_MAX;w.last=true;return w;}
    void edge() {scheduler_.settle_low(next_);scheduler_.rise_and_observe(next_);++next_;}
    void offered_job() {
        model_.HostBlockTop__DOT__cmd__DOT___io_job_valid_T_2=1;
        model_.HostBlockTop__DOT__cmd__DOT__io_job_ready_0=1;
        model_.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__io_startRequest_0=1;
        model_.HostBlockTop__DOT__cmd__DOT__bound_kind=0;
        model_.HostBlockTop__DOT__cmd__DOT__bound_tag=7U<<16;
        model_.HostBlockTop__DOT__cmd__DOT__bound_m=128;
        model_.HostBlockTop__DOT__cmd__DOT__bound_n=1536;
        model_.HostBlockTop__DOT__cmd__DOT__bound_k=1536;
        model_.HostBlockTop__DOT__cmd__DOT__bound_a=expected_inputs[15].base;
        model_.HostBlockTop__DOT__cmd__DOT__bound_b=expected_inputs[9].base;
        model_.HostBlockTop__DOT__cmd__DOT__bound_c=0;
        model_.HostBlockTop__DOT__cmd__DOT__bound_dst=4544;
        model_.HostBlockTop__DOT__cmd__DOT__bound_writeBytes=64;
    }
public:
    RuntimeTestAccess():owner_(policy(),inputs()),allocation_(owner_.payload_.data()),
        session_(ready(owner_)),model_(),scheduler_(owner_,model_) {}
    using Snapshot=std::pair<std::vector<std::uint8_t>,std::vector<std::uint8_t>>;
    Snapshot snapshot()const{return {owner_.payload_,owner_.mask_};}
    bool poisoned()const{return owner_.phase_==RuntimeOwner::Phase::Poisoned;}
    bool published()const{return owner_.published_;}
    void readable(){session_.require_read(4544,64);}
    void require_saved_identity()const {
        ::require(scheduler_.launched_&&scheduler_.accepted_epoch_==7,"accepted launch epoch was not retained");
        ::require(scheduler_.accepted_job_.tag==(7U<<16),"accepted job tag was not retained");
    }
    void launch_and_job() {
        model_.io_launch_ready=1;scheduler_.offer_launch();
        scheduler_.settle_low(next_);
        ::require(!scheduler_.launched_&&scheduler_.accepted_epoch_==0,"low launch must not save acceptance");
        scheduler_.rise_and_observe(next_++);
        ::require(scheduler_.launched_&&scheduler_.accepted_epoch_==7,"high launch did not save sampled epoch");
        // Disabled payload is deliberately changed after acceptance. The saved
        // identity must continue to come from the accepted event, not this port.
        model_.io_launch_bits_epoch=6;
        offered_job();model_.script=wiring_test::ScriptedFieldFixture::Script::AcceptOfferedJob;edge();
        require_saved_identity();
        ::require(scheduler_.adapter_.accepted_,"private owner event was not accepted");
        model_.HostBlockTop__DOT__cmd__DOT__bound_tag=6U<<16;
        require_saved_identity();
    }
    void bad_launch_epoch() {
        model_.io_launch_ready=1;scheduler_.offer_launch();model_.io_launch_bits_epoch=6;
        scheduler_.settle_low(next_);
    }
    void altered_inputs_between_edges() {
        model_.io_launch_ready=1;scheduler_.offer_launch();scheduler_.settle_low(next_);
        model_.io_launch_bits_epoch=6;scheduler_.rise_and_observe(next_);
    }
    void bad_owner_epoch() {scheduler_.adapter_.accept_owner(0,7U<<16,6);}
    void bad_owner_pc() {scheduler_.adapter_.accept_owner(1,7U<<16,7);}
    void bad_request_epoch() {
        scheduler_.adapter_.accept_model_request(4544,data(),(6ULL<<32)|1,transport_,{0,7U<<16,0,false});
    }
    void stage_to_held_b() {
        launch_and_job();
        auto& adapter=scheduler_.adapter_;
        // Explicit test-only injection: core->hub capture and DMA acceptance
        // are not produced by this fixture. Their production private gates run.
        adapter.accept_model_request(4544,data(),original_,transport_,{0,7U<<16,0,false});
        ::require(adapter.model_aw_id_pending_&&adapter.debt_->request.id==0,"ID must begin unbound");
        adapter.dma_accept(original_,transport_,adapter.debt_->request,data());
        model_.HostBlockTop__DOT__dma__DOT__req_write=1;
        model_.HostBlockTop__DOT__dma__DOT__req_address=4544;
        model_.HostBlockTop__DOT__dma__DOT__req_mask=UINT64_MAX;
        model_.HostBlockTop__DOT__dma__DOT__rsp_tag=transport_;
        model_.HostBlockTop__DOT__dma__DOT__req_data=data().data;
        const auto before=snapshot();
        edge();edge(); // edges 3,4: no AW/W
        model_.io_axi_aw_valid=1;model_.io_axi_aw_bits_addr=4544;
        model_.io_axi_aw_bits_id=37;model_.io_axi_aw_bits_len=0;
        model_.io_axi_aw_bits_size=6;model_.io_axi_aw_bits_burst=1;
        edge(); // edge 5: original schedule holds AWREADY low
        ::require(adapter.model_aw_id_pending_&&adapter.debt_->request.id==0,"stalled offer bound AXI ID");
        model_.io_axi_w_valid=1;model_.io_axi_w_bits_data=data().data;
        model_.io_axi_w_bits_strb=UINT64_MAX;model_.io_axi_w_bits_last=1;
        edge(); // edge 6: AW fire binds ID; WREADY low
        ::require(!adapter.model_aw_id_pending_&&adapter.debt_->request.id==37,"first AW fire failed to lock ID");
        ::require(adapter.aw_&&adapter.aw_->id==37,"AW staging lost accepted ID");
        model_.io_axi_aw_valid=0;edge(); // edge 7: W fire stages held B
        model_.io_axi_w_valid=0;
        ::require(adapter.held_b_,"accepted W did not form held B");
        ::require(snapshot()==before,"AW/W staged bytes before B");
        edge(); // edge 8: B held without BREADY
        ::require(snapshot()==before,"held B changed payload or mask");
    }
    void bad_b_id() {
        auto& adapter=scheduler_.adapter_;
        RuntimeOwner::N0RetirementAdapter::Pins pins{};
        pins.axi.aw_ready=false;pins.axi.w_ready=false;pins.axi.b_valid=true;
        pins.axi.b_ready=true;pins.axi.b.id=38;
        adapter.capture_low(next_,pins); // production held-B gate, not fabricated wire authority
    }
    void commit_b() {
        model_.io_axi_b_ready=1;edge(); // edge 9: real pre-edge sample -> private B commit
        ::require(scheduler_.adapter_.debt_->b_committed,"private B did not retire accepted debt");
        ::require(owner_.mask_[4544-owner_.base_]==1&&owner_.payload_[4544-owner_.base_]==0x11,"B did not write actual owner RAM");
        ::require(!published(),"B alone published N0 reads");
        ::require(allocation_==owner_.payload_.data(),"runtime changed payload allocation");
        model_.io_axi_b_ready=0;
    }
    void retire_responses() {
        // Explicit test-only injection of the original-tag response and done
        // events. No model-generated writeback/computation is claimed here.
        auto& adapter=scheduler_.adapter_;
        adapter.dma_return(original_,transport_);adapter.writeback_ack(original_,64);adapter.owner_done(64,0);
        model_.HostBlockTop__DOT__owner__DOT__active=0;
        model_.HostBlockTop__DOT__owner__DOT__qkvRouter__DOT__state=0;
    }
    void prepare_completion() {stage_to_held_b();commit_b();retire_responses();}
    void completion(std::uint64_t word=0x10060000000ULL) {
        model_.io_completion_valid=1;model_.io_completion_bits=word;
        model_.script=wiring_test::ScriptedFieldFixture::Script::AcknowledgeCompletion;
        edge();
    }
    void verify_readback() {
        ::require(published(),"raw completion ACK did not publish reads");require_saved_identity();
        ::require(allocation_==owner_.payload_.data(),"completion changed payload allocation");
        ::require(session_.actual_byte(4096)=='A',"input changed during runtime write");
        ::require(session_.actual_byte(4544)==0x11&&session_.actual_byte(4607)==0x44,"public completion byte read differs");
        const auto beat=session_.read_beat(4544);
        for(auto word:beat)::require(word==0x44332211,"public completion beat read differs");
        ::require(model_.eval_calls==20,"one low/high pair per ten fixture edges");
    }
};
} // namespace canonical_runtime_v1
namespace {
template<class Function>void private_rejects(canonical_runtime_v1::RuntimeTestAccess& f,Function action,const char* reason) {
    const auto before=f.snapshot();bool threw=false;
    try{action();}catch(const std::exception& error){require(std::string(error.what())==reason,"private wrong rejection boundary");threw=true;}
    require(threw,"private event was not rejected");require(f.poisoned(),"private rejection failed to poison");
    require(f.snapshot()==before,"private rejection changed RAM");
}
void test_private_wiring() {
    using Test=canonical_runtime_v1::RuntimeTestAccess;
    {Test f;private_rejects(f,[&]{f.bad_launch_epoch();},"actual fixed launch differs");}
    {Test f;private_rejects(f,[&]{f.altered_inputs_between_edges();},"model inputs changed outside private clock");}
    {Test f;private_rejects(f,[&]{f.bad_owner_epoch();},"fixed N0 owner identity");}
    {Test f;private_rejects(f,[&]{f.bad_owner_pc();},"fixed N0 owner identity");}
    {Test f;f.launch_and_job();private_rejects(f,[&]{f.bad_request_epoch();},"request epoch/owner/prefix");}
    {Test f;f.stage_to_held_b();private_rejects(f,[&]{f.bad_b_id();},"held B ID/RESP changed");}
    {Test f;f.stage_to_held_b();f.commit_b();private_rejects(f,[&]{f.readable();},"N0 completion not published");}
    const std::pair<std::uint64_t,const char*> bad[]={{0x10060000001ULL,"completion payload is not PC0"},
        {0x10080000000ULL,"completion payload owner is not SFU_CGRA"},
        {0x10160000000ULL,"completion payload status is not zero"},
        {0x00060000000ULL,"completion payload signal is not one"},
        {0x100010060000000ULL,"completion payload exceeds 56 bits"}};
    for(const auto& item:bad){Test f;f.prepare_completion();private_rejects(f,[&]{f.completion(item.first);},item.second);}
    {Test f;f.prepare_completion();f.completion();f.verify_readback();}
}
} // namespace

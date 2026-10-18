// SOURCE-only actual DPI observer: fixed no-job startup, then bounded PC0 scalar work.
// No arithmetic, memory provider, Host driver, reference result, or model evaluation here.
#pragma once
#include "startup_inputs.hpp"
#include "svdpi.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <initializer_list>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>
namespace host_startup {
enum class Kind {combo_ignore,combo_update,seq_update,final};
struct Record {
    void* handle=nullptr;
    uint64_t combo=0,seq=0,ignored=0,finals=0,next_sequence=0;
    uint64_t baseline_release_seq=0,reset_assert_seq=0,reset_release_seq=0;
    uint64_t startup_combo=0,startup_seq=0,startup_ignored=0,startup_next_sequence=0;
    uint64_t work_calls=0,work_combo=0,work_seq=0,work_ignored=0;
    unsigned last_rst=2,pending_rst=2;
    std::array<uint64_t,20> per_eval{};
    unsigned last_output_phase=0;
    std::array<unsigned,8> output{};
    bool output_seen=false;
};
class Ledger {
public:
    static constexpr uint64_t kMaxWorkCycles=2000000ULL;
    static constexpr uint64_t kMaxDpiCalls=kMaxWorkCycles*128ULL+100000ULL;
private:
    VHostBlockTop* model_=nullptr;
    const std::thread::id thread_=std::this_thread::get_id();
    std::array<Record,8> records_{};
    uint64_t hash_checks_=0,created_=0,calls_=0,evals_=0;
    uint64_t startup_calls_=0,work_calls_=0,work_evals_=0;
    unsigned work_clock_=0;
    bool work_started_=false,work_active_=false,active_work_eval_=false,work_done_=false;
    unsigned phase_=0;
    bool active_eval_=false,active_final_=false,closed_=false,failed_=false;
    void require(bool ok,const char* message) {
        if(!ok){failed_=true;throw std::runtime_error(message);}
    }
    void healthy() {
        require(!failed_,"startup observer permanently failed");
        require(std::this_thread::get_id()==thread_,"unexpected DPI thread");
    }
    void call_guard() {
        healthy();require(model_&&!closed_,"DPI outside owned actual model");
        require(active_eval_||active_work_eval_||active_final_,"DPI outside sole eval/work/final schedule");
        require(++calls_<=(work_started_?kMaxDpiCalls:100000ULL),"DPI call bound exceeded");
        if(active_work_eval_) {
            require_live_work();
            require(model_->clock==work_clock_,"DPI outside actual scheduled work clock");
            ++work_calls_;
        }
    }
    unsigned lookup(void* handle) {
        require(handle!=nullptr,"null DPI handle");
        for(unsigned i=0;i<8;++i)if(records_[i].handle==handle)return i;
        require(false,"unknown DPI handle");return 0; // unreachable; never an evidence fallback
    }
    void require_live_work() {
        require(model_&&model_->rootp&&!model_->reset&&!model_->io_resetRequired,"PC0 work reset/poison");
        require(&model_->clock==&model_->rootp->clock&&&model_->reset==&model_->rootp->reset,"actual work clock/reset aliases");
        require(!model_->contextp()->gotFinish()&&!model_->contextp()->gotError(),"actual work context finished/errored");
    }
    void require_work_leaf_idle() {
        require(created_==8&&hash_checks_==8,"work requires original eight creates/hash calls");
        const auto handles=root_handles(*model_);
        for(unsigned i=0;i<8;++i) {
            const auto& r=records_[i];
            require(handles[i]==reinterpret_cast<uintptr_t>(r.handle),"actual work root handle association mismatch");
            require(r.last_rst==1&&r.output_seen&&r.last_output_phase>=11,"work requires actual released leaf return");
            for(unsigned v:r.output)require(v==0,"actual PC0 idle leaf activity/error output");
        }
    }
public:
    void poison() noexcept {failed_=true;}
    void bind(VHostBlockTop& model) {
        healthy();require(!model_&&!closed_&&created_==0,"startup model reused");
        require(model.rootp&&std::string(model.name())=="TOP","actual root/model name");
        require(&model.clock==&model.rootp->clock&&&model.reset==&model.rootp->reset,"actual clock/reset aliases");
        model_=&model;
    }
    void begin_eval(unsigned phase,unsigned clock,unsigned reset) {
        healthy();require(model_&&!closed_&&!active_eval_&&!active_final_&&!work_started_,"nested or closed startup eval");
        require(phase==evals_&&phase<20,"fixed startup phase order");
        const unsigned expected_reset=(phase==0||(phase>=2&&phase<=10))?1:0;
        const unsigned expected_clock=((phase>=3&&phase<=10&&phase%2==1)||(phase>=12&&phase%2==0))?1:0;
        require(clock==expected_clock&&reset==expected_reset,"fixed reset/clock schedule");
        auto inputs=input_snapshot(*model_);
        require(inputs[0]==clock&&inputs[1]==reset,"actual Host clock/reset mismatch");
        for(unsigned i=2;i<inputs.size();++i)require(inputs[i]==0,"startup external input must remain idle zero");
        phase_=phase;active_eval_=true;
    }
    void end_eval() {
        healthy();require(active_eval_,"eval completion without begin");
        require(created_==8&&hash_checks_==8,"all eight actual creates/hash calls required");
        const auto handles=root_handles(*model_);
        for(unsigned i=0;i<8;++i)require(handles[i]==reinterpret_cast<uintptr_t>(records_[i].handle),"actual root handle association mismatch");
        require(!model_->io_launch_valid&&!model_->io_axi_ar_valid&&!model_->io_axi_aw_valid&&!model_->io_axi_w_valid,"no-job AXI or launch offer");
        if(phase_>=11) {
            require(model_->io_launch_ready&&!model_->io_result_valid&&!model_->io_completion_valid&&!model_->io_resetRequired,"Host idle/reset settled outputs");
            require(model_->io_pc==0&&model_->io_issuedJobs==0&&model_->io_writeBytes==0,"Host no-job state/counters");
            require(model_->io_memoryAccepted_0==0&&model_->io_memoryAccepted_1==0&&model_->io_memoryReturned_0==0&&model_->io_memoryReturned_1==0,"Host no-job hub counts");
            require(model_->io_idmaTransfers==0&&model_->io_idmaReadBursts==0&&model_->io_idmaReadBeats==0&&model_->io_idmaStreamedBeats==0&&model_->io_idmaStreamedWriteBeats==0,"Host no-job DMA counts");
            require(model_->io_usefulMacs==0&&model_->io_executedMacs==0&&model_->io_pipelineIssues==0,"Host no-job arithmetic counters");
            for(const auto& r:records_) {
                require(r.output_seen&&r.last_output_phase>=11,"missing actual post-release leaf return");
                for(unsigned v:r.output)require(v==0,"actual idle leaf activity/error output");
            }
        }
        active_eval_=false;++evals_;
    }
    void before_hash(int actual) {
        call_guard();require(active_eval_&&phase_==0&&hash_checks_<8&&hash_checks_==created_,"hash call lifecycle");
        require(static_cast<uint32_t>(actual)==3536998148U,"actual protected ABI hash");
    }
    void after_hash() {healthy();++hash_checks_;}
    unsigned before_create(const char* scope) {
        call_guard();require(active_eval_&&phase_==0&&scope,"create lifecycle/scope");
        for(unsigned i=0;i<8;++i)if(std::string(scope)=="TOP.HostBlockTop.owner.matrix.leaves_"+std::to_string(i)) {
            require(!records_[i].handle,"duplicate actual scope create");
            require(created_<8&&i==7-created_&&hash_checks_==created_+1,"actual scope create/hash order");return i;
        }
        require(false,"unknown actual create scope");return 0;
    }
    void after_create(unsigned index,void* actual) {
        healthy();require(index<8&&actual,"create did not return an actual handle");
        for(const auto& r:records_)require(r.handle!=actual,"two scopes share one actual handle");
        records_[index].handle=actual;++created_;
    }
    unsigned before_call(void* actual,Kind kind) {
        call_guard();const auto i=lookup(actual);
        require(records_[i].finals==0,"callback after actual final");
        require((kind==Kind::final)==active_final_,"callback/final phase mismatch");
        if(active_eval_)++records_[i].per_eval[phase_];
        if(active_work_eval_)++records_[i].work_calls;
        return i;
    }
    void no_job(unsigned begin,unsigned beat,unsigned commit,unsigned abort,unsigned command,unsigned step) {
        require(begin==0&&beat==0&&commit==0&&abort==0&&command==0&&step==0,"actual protected no-job input offer");
    }
    void seq_inputs(unsigned index,unsigned clock,unsigned rst_n) {
        require(index<8&&clock<=1&&rst_n<=1,"actual DPI logic not two-state");
        require(clock==gate_clocks(*model_)[index],"DPI clock differs from actual leaf gated clock");
        require(rst_n==(model_->reset?0U:1U),"DPI reset differs from actual inverted Host reset");
        auto& r=records_[index];
        if(phase_==2&&r.reset_assert_seq==0)require(r.baseline_release_seq>0&&r.last_rst==1,"actual child reset must transition from prior live rst_n=1");
        if(phase_==11&&r.reset_release_seq==0)require(r.reset_assert_seq>0&&r.last_rst==0,"actual child release must follow asserted rst_n=0");
        if(active_work_eval_)require(rst_n==1&&r.last_rst==1,"actual work leaf reset must remain released");
        r.pending_rst=rst_n;
    }
    void after_update(unsigned index,Kind kind,long long actual,unsigned ack,unsigned ack_error,unsigned reset_required,unsigned arithmetic_valid,unsigned out_valid,unsigned completion,unsigned protocol_error,const svLogicVecVal* busy) {
        healthy();auto& r=records_.at(index);
        require(kind==Kind::combo_update||kind==Kind::seq_update,"invalid update kind");
        require(actual>=0&&uint64_t(actual)==r.next_sequence&&r.next_sequence<uint64_t(std::numeric_limits<long long>::max()),"actual per-handle combo/seq return order");
        ++r.next_sequence;
        if(kind==Kind::combo_update)++r.combo;
        else {++r.seq;r.last_rst=r.pending_rst;if(phase_==1)++r.baseline_release_seq;if(phase_==2)++r.reset_assert_seq;if(phase_==11)++r.reset_release_seq;}
        require(busy&&busy[0].bval==0&&(busy[0].aval&~31U)==0,"actual five-bit arithmetic_busy output");
        for(auto v:{ack,ack_error,reset_required,arithmetic_valid,out_valid,completion,protocol_error})require(v<=1,"actual DPI output not two-state");
        r.output={{ack,ack_error,reset_required,arithmetic_valid,out_valid,completion,protocol_error,busy[0].aval}};
        r.output_seen=true;r.last_output_phase=phase_;
        if(active_work_eval_) {
            if(kind==Kind::combo_update)++r.work_combo;else ++r.work_seq;
            for(unsigned v:r.output)require(v==0,"actual PC0 protected return must remain idle");
        }
    }
    void after_void(unsigned index,Kind kind) {
        healthy();auto& r=records_.at(index);
        if(kind==Kind::final)++r.finals;
        else {require(kind==Kind::combo_ignore,"invalid void kind");++r.ignored;if(active_work_eval_)++r.work_ignored;}
    }
    // Call once after the unchanged twenty startup evaluations, before launch.
    void begin_work() {
        healthy();require(model_&&!closed_&&!active_eval_&&!active_final_&&!work_started_&&evals_==20,"work before fixed startup schedule or reused work");
        require_live_work();require_work_leaf_idle();
        require(model_->clock==0,"work must start after startup low clock");
        for(auto& r:records_) {
            require(r.handle&&r.combo>0&&r.seq>0&&r.baseline_release_seq>0&&r.reset_assert_seq>0&&r.reset_release_seq>0,"missing actual startup create/combo/seq/reset call coverage");
            r.startup_combo=r.combo;r.startup_seq=r.seq;r.startup_ignored=r.ignored;r.startup_next_sequence=r.next_sequence;
        }
        startup_calls_=calls_;work_started_=true;work_active_=true;
    }
    // Arm before the owner calls SharedEdgeRuntime, which alone sets clock/evaluates.
    void begin_work_eval(unsigned clock) {
        healthy();require(model_&&!closed_&&work_active_&&!work_done_&&!active_eval_&&!active_work_eval_&&!active_final_,"nested or inactive work eval");
        require(work_evals_<kMaxWorkCycles*2ULL,"PC0 full-cycle bound exceeded");
        require(clock<=1&&clock==unsigned(work_evals_&1ULL),"PC0 work requires alternating low/high evals");
        require_live_work();require_work_leaf_idle();
        work_clock_=clock;active_work_eval_=true;
    }
    void end_work_eval() {
        healthy();require(active_work_eval_&&work_active_,"work eval completion without begin");
        require_live_work();require_work_leaf_idle();
        require(model_->clock==work_clock_,"actual work clock differs from scheduled clock");
        active_work_eval_=false;++work_evals_;
    }
    // The caller may close work ONLY after independently proving actual ACK0.
    // This observer does not manufacture, infer, or claim ACK0/business qualification.
    void end_work() {
        healthy();require(work_active_&&!active_work_eval_&&!active_eval_&&!active_final_&&!work_done_,"work completion outside settled work");
        require(work_evals_>0&&(work_evals_&1ULL)==0&&work_evals_<=kMaxWorkCycles*2ULL,"work completion requires bounded full cycles");
        require_live_work();require_work_leaf_idle();
        require(model_->clock==1,"work completion requires settled rising edge");
        work_active_=false;work_done_=true;
    }
    void begin_final() {
        healthy();require(model_&&!closed_&&!active_eval_&&!active_work_eval_&&!active_final_&&evals_==20&&work_done_&&!work_active_,"final before startup and caller-closed PC0 work");
        require_live_work();require_work_leaf_idle();
        for(const auto& r:records_)require(r.handle&&r.combo>0&&r.seq>0&&r.baseline_release_seq>0&&r.reset_assert_seq>0&&r.reset_release_seq>0,"missing actual create/combo/seq/reset call coverage");
        active_final_=true;
    }
    void end_final() {
        healthy();require(active_final_,"final completion without begin");
        for(const auto& r:records_)require(r.finals==1,"missing actual per-handle final call");
        active_final_=false;closed_=true;model_=nullptr;
    }
    void report(std::ostream& out) {
        healthy();require(closed_&&evals_==20&&created_==8&&hash_checks_==8&&work_done_&&!work_active_,"incomplete PC0 observer receipt");
        out<<"{\"kind\":\"HOST_PC0_SCALAR_DPI_OBSERVER_ONLY\",\"eval_calls\":"<<evals_<<",\"work_eval_calls\":"<<work_evals_<<",\"work_cycles\":"<<work_evals_/2<<",\"max_work_cycles\":"<<kMaxWorkCycles<<",\"hash_calls\":"<<hash_checks_<<",\"actual_creates\":"<<created_<<",\"dpi_calls\":"<<calls_<<",\"startup_dpi_calls\":"<<startup_calls_<<",\"work_dpi_calls\":"<<work_calls_<<",\"caller_closed_work\":true,\"host_job_qualification\":false,\"handles\":[";
        for(unsigned i=0;i<8;++i) {const auto& r=records_[i];if(i)out<<',';
            out<<"{\"scope\":\"TOP.HostBlockTop.owner.matrix.leaves_"<<i<<"\",\"handle\":"<<reinterpret_cast<uintptr_t>(r.handle)<<",\"combo\":"<<r.combo<<",\"seq\":"<<r.seq<<",\"ignored\":"<<r.ignored<<",\"final\":"<<r.finals<<",\"baseline_release_seq\":"<<r.baseline_release_seq<<",\"reset_assert_seq\":"<<r.reset_assert_seq<<",\"reset_release_seq\":"<<r.reset_release_seq<<",\"next_sequence\":"<<r.next_sequence<<",\"startup_combo\":"<<r.startup_combo<<",\"startup_seq\":"<<r.startup_seq<<",\"startup_ignored\":"<<r.startup_ignored<<",\"startup_next_sequence\":"<<r.startup_next_sequence<<",\"work_calls\":"<<r.work_calls<<",\"work_combo\":"<<r.work_combo<<",\"work_seq\":"<<r.work_seq<<",\"work_ignored\":"<<r.work_ignored<<",\"per_eval\":[";
            for(unsigned p=0;p<20;++p){if(p)out<<',';out<<r.per_eval[p];}out<<"]}";
        }out<<"]}\n";
        require(bool(out),"startup receipt output failure");
    }
};
inline Ledger* active_ledger=nullptr;
inline Ledger& ledger() {if(!active_ledger)throw std::runtime_error("DPI without startup observer");return *active_ledger;}
} // namespace host_startup

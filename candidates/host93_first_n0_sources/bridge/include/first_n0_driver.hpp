// SOURCE ONLY: the sole production entry to private N0 transport authority.
#pragma once
#include "runtime_ram.hpp"
#include "verilated.h"
#include <thread>
namespace canonical_runtime_v1 {
inline FirstN0Result RuntimeOwner::run_first_n0(RunPhase& diagnostic_phase) {
    diagnostic_phase=RunPhase::MODEL_ADMISSION; // write-only diagnostic, never execution authority
    return checked([&] {
        require(phase_==Phase::Runtime&&adapter_==nullptr&&!published_&&!outstanding_,"one fresh private runtime required");
        verify_inputs();
        FirstN0Result result;
        for(std::size_t i=0;i<inputs_.size();++i) {
            const auto& in=inputs_[i];
            result.input_hashes[i]=Sha256::hash(payload_.data()+static_cast<std::size_t>(in.base-base_),static_cast<std::size_t>(in.bytes));
            require(result.input_hashes[i]==in.sha256,"same allocation input digest before actual model");
        }
        // Sole, concrete actual model. No caller-supplied Model, context, Frame or callback.
        VerilatedContext context;context.threads(1);context.randReset(0);context.randSeed(1);
        Verilated::threadContextp(&context);
        VHostBlockTop model{&context,"TOP"};first_n0::zero_inputs(model);
        const auto thread=std::this_thread::get_id();
        auto reset_eval=[&](unsigned clock,unsigned reset) {
            require(std::this_thread::get_id()==thread,"actual model thread changed");
            model.clock=clock;model.reset=reset;const auto before=first_n0::input_snapshot(model);
            model.eval();require(!context.gotFinish()&&!context.gotError()&&before==first_n0::input_snapshot(model),
                                 "actual reset eval/input failure");context.timeInc(1);
        };
        // Exact current-cluster reset schedule, not the old eight-endpoint lifecycle.
        reset_eval(0,1);
        for(unsigned i=0;i<4;++i){reset_eval(1,1);reset_eval(0,1);}
        reset_eval(0,0);
        for(unsigned i=0;i<4;++i){reset_eval(1,0);reset_eval(0,0);}
        require(!model.io_resetRequired&&model.io_pc==0&&model.io_issuedJobs==0&&model.io_writeBytes==0&&
                model.io_launch_ready&&!model.io_result_valid&&!model.io_completion_valid&&
                model.io_memoryAccepted_0==0&&model.io_memoryAccepted_1==0&&
                model.io_memoryReturned_0==0&&model.io_memoryReturned_1==0,"actual cluster reset release idle");
        N0ModelScheduler<VHostBlockTop> scheduler(*this,model);
        diagnostic_phase=RunPhase::RTL_N0;
        for(std::uint64_t edge=0;edge<first_n0::cycle_budget;++edge) {
            require(std::this_thread::get_id()==thread,"actual model thread changed");
            if(edge==1)scheduler.offer_launch();
            scheduler.settle_low(edge);context.timeInc(1);
            scheduler.rise_and_observe(edge);context.timeInc(1);
            if(published_)break; // no later low/high eval; first ACK0 high is the terminal edge
        }
        result.counts=scheduler.counts_;result.axi=scheduler.axi_audit_.counts();
        result.committed_bytes=scheduler.adapter_.committed_;result.successful_b=scheduler.adapter_.b_count_;
        result.writeback_bytes=scheduler.adapter_.writeback_;result.completion_word=scheduler.completion_word_;
        result.post_pc=model.io_pc;result.post_issued_jobs=model.io_issuedJobs;
        result.idma_transfers=model.io_idmaTransfers;result.idma_read_bursts=model.io_idmaReadBursts;
        result.idma_read_beats=model.io_idmaReadBeats;result.idma_cache_hits=model.io_idmaCacheHits;
        result.hub_accepted={model.io_memoryAccepted_0,model.io_memoryAccepted_1};
        result.hub_returned={model.io_memoryReturned_0,model.io_memoryReturned_1};
        if(!published_) {
            result.status=FirstN0Result::Status::IncompleteCycleBudget;
            return result; // no partial tensor or numerical mismatch claim
        }
        require(result.counts.completion_acks==1&&result.counts.launches==1&&result.counts.jobs==1&&
                result.counts.owner_dones==1&&result.post_pc==1&&result.post_issued_jobs==1&&
                result.committed_bytes==786432&&result.successful_b==12288&&result.writeback_bytes==786432,
                "ACK0 exact full N0 retirement");
        diagnostic_phase=RunPhase::OUTPUT;
        read_permission(n0().base,n0().bytes); // real published same-RAM payload + full initialization mask
        result.actual_f32le.resize(static_cast<std::size_t>(n0().bytes));
        for(std::size_t i=0;i<result.actual_f32le.size();++i)
            result.actual_f32le[i]=payload_[static_cast<std::size_t>(n0().base-base_)+i];
        result.actual_sha256=Sha256::hash(result.actual_f32le.data(),result.actual_f32le.size());
        result.status=FirstN0Result::Status::Ack0ActualCaptured;
        return result; // no model.final(), eval(), PC1 dispatch, or reference computation
    });
}
}

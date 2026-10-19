// SOURCE ONLY: the sole production entry to private N0 transport authority.
#pragma once
#include "runtime_ram.hpp"
#include "verilated.h"
#include <thread>
namespace canonical_runtime_v1 {
inline Pc01Result RuntimeOwner::run_pc01(RunPhase& diagnostic_phase,Pc01FailureCapsule& diagnostic) {
    diagnostic_phase=RunPhase::MODEL_ADMISSION; // write-only diagnostic, never execution authority
    return checked([&] {
        require(phase_==Phase::Runtime&&adapter_==nullptr&&!published_&&!outstanding_,"one fresh private runtime required");
        verify_inputs();
        Pc01Result full;auto& result=full.n0;
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
            if(published_)break; // ACK0 commits N0; the new PC1 scheduler continues below
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
            full.total_cycles=result.counts.cycles;return full; // no partial tensor or numerical mismatch claim
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
        // Pre-PC1 provenance only; survives unwinding without retaining the tensor.
        diagnostic.ack0s=result.counts.completion_acks;diagnostic.n0_cycles=result.counts.cycles;
        diagnostic.n0_jobs=result.counts.jobs;diagnostic.n0_dones=result.counts.owner_dones;
        diagnostic.n0_committed=result.committed_bytes;diagnostic.n0_b=result.successful_b;
        diagnostic.n0_sha256=result.actual_sha256;diagnostic.ack0_valid=true;
        // Original N0 scheduler and its private adapter stay alive in this stack.
        // No reload, new Host, reset, launch, or reference enters the continuation.
        diagnostic_phase=RunPhase::RTL_PC1;
        Pc1ModelScheduler pc1(*this,model,result.counts.cycles,diagnostic);
        full.status=Pc01Result::Status::IncompletePc1;
        for(std::uint64_t edge=result.counts.cycles;edge<pc01::total_cycle_budget;++edge) {
            require(std::this_thread::get_id()==thread,"PC1 actual model thread changed");
            pc1.settle_low(edge);context.timeInc(1);
            pc1.rise_and_observe(edge);context.timeInc(1);
            if(qraw_published_)break; // ACK1 high is final: zero subsequent eval/final calls
        }
        full.total_cycles=result.counts.cycles+pc1.cycles_;
        full.pc1_entry_edge=pc1.entry_edge_;full.pc1_accept_edge=pc1.accept_edge_;full.ack1_edge=pc1.ack_edge_;
        full.pc1_jobs=pc1.jobs_;full.pc1_dones=pc1.dones_;full.pc1_acks=pc1.acks_;
        full.qraw_committed=pc1.adapter_.committed_;full.qraw_b=pc1.adapter_.b_count_;
        full.pc1_axi=pc1.audit_.counts();full.completion_word=pc1.completion_;
        full.matrix_wide_steps=pc1.guard_.wide_steps();full.matrix_slice_steps=pc1.guard_.slice_steps();
        full.matrix_stalls=pc1.guard_.stalls();full.add_requests=pc1.guard_.requests();full.add_results=pc1.guard_.results();
        full.n0_read_bytes=pc1.n0_read_bytes_;full.wq_read_bytes=pc1.wq_read_bytes_;
        full.post_pc=model.io_pc;full.post_issued_jobs=model.io_issuedJobs;
        full.useful_macs=model.io_usefulMacs;full.executed_macs=model.io_executedMacs;
        if(!qraw_published_)return full;
        require(full.pc1_jobs==1&&full.pc1_dones==1&&full.pc1_acks==1&&full.post_pc==2&&full.post_issued_jobs==2&&
                full.qraw_committed==pc01::qraw_bytes&&full.ack1_edge>=full.pc1_accept_edge&&
                full.matrix_wide_steps==pc01::wide_steps&&full.matrix_slice_steps==pc01::slice_steps&&
                full.useful_macs==pc01::useful_macs&&full.executed_macs==pc01::useful_macs&&
                full.add_requests==pc01::add_vectors&&full.add_results==pc01::add_vectors&&
                full.n0_read_bytes>0&&full.wq_read_bytes>0,"PC1 complete output and resources");
        full.pc1_cycles=full.ack1_edge-full.pc1_accept_edge+1;
        diagnostic_phase=RunPhase::OUTPUT;verify_inputs();
        require(Sha256::hash(payload_.data()+std::size_t(n0().base-base_),std::size_t(n0().bytes))==result.actual_sha256,
                "PC1 same-RAM N0 changed after ACK0");
        read_permission(qraw().base,qraw().bytes);
        full.qraw_f32le.resize(std::size_t(qraw().bytes));
        for(std::size_t i=0;i<full.qraw_f32le.size();++i)full.qraw_f32le[i]=payload_[std::size_t(qraw().base-base_)+i];
        full.qraw_sha256=Sha256::hash(full.qraw_f32le.data(),full.qraw_f32le.size());
        full.status=Pc01Result::Status::Ack1Captured;
        return full; // no model.final(), further eval, or mathematical reference

    });
}
}

// SOURCE ONLY. Fixed 16 old-hash inputs; local actual output is not public diagnostics.
#include "pc01_driver.hpp"
#include "fixed_file_io.hpp"
#include <sstream>
#include <cstdio>
#include <filesystem>
#include <cerrno>
#include <fstream>
#include <iostream>
#include <new>
#include <fcntl.h>
#include <unistd.h>
namespace {
using namespace canonical_runtime_v1;
template<class T> void array(std::ostream& o,const T& values) {
    o<<'[';bool comma=false;for(auto v:values){if(comma)o<<',';o<<v;comma=true;}o<<']';
}
void report(std::ostream& out,const Pc01Result& r) {
    const bool ack=r.status==Pc01Result::Status::Ack1Captured;
    out<<"{\"scope\":\"PC0_ACK0_PC1_ACK1_M128_ONLY\",\"status\":\""
       <<(ack?"ACK1_ACTUAL_CAPTURED":r.status==Pc01Result::Status::IncompletePc0?"INCOMPLETE_PC0_CYCLE_BUDGET":"INCOMPLETE_PC1_CYCLE_BUDGET")
       <<"\",\"numeric_comparison\":\"NOT_RUN\",\"official_raw_numeric_pass\":null,\"full_block_pass\":false"
       <<",\"total_cycle_budget\":"<<pc01::total_cycle_budget<<",\"total_cycles\":"<<r.total_cycles
       <<",\"launches\":"<<r.n0.counts.launches<<",\"n0_jobs\":"<<r.n0.counts.jobs
       <<",\"n0_dones\":"<<r.n0.counts.owner_dones<<",\"ack0s\":"<<r.n0.counts.completion_acks
       <<",\"n0_cycles\":"<<r.n0.counts.cycles<<",\"n0_committed\":"<<r.n0.committed_bytes
       <<",\"pc1_jobs\":"<<r.pc1_jobs<<",\"pc1_dones\":"<<r.pc1_dones<<",\"ack1s\":"<<r.pc1_acks
       <<",\"pc1_entry_edge\":"<<r.pc1_entry_edge<<",\"pc1_accept_edge\":"<<r.pc1_accept_edge
       <<",\"ack1_edge\":"<<r.ack1_edge<<",\"pc1_complete_window_cycles\":"<<r.pc1_cycles
       <<",\"pc1_window_definition\":\"accepted_PC1_high_through_ACK1_high_inclusive\""
       <<",\"qraw_committed_bytes\":"<<r.qraw_committed<<",\"qraw_successful_b\":"<<r.qraw_b
       <<",\"post_pc\":"<<r.post_pc<<",\"post_issued_jobs\":"<<r.post_issued_jobs
       <<",\"further_eval_calls_after_ack1\":0,\"useful_macs\":"<<r.useful_macs
       <<",\"executed_macs\":"<<r.executed_macs<<",\"fixed_physical_macs_per_cycle\":4096"
       <<",\"utilization_numerator\":"<<(ack?pc01::useful_macs:0)
       <<",\"utilization_denominator\":"<<(ack?pc01::physical_macs_per_cycle*r.pc1_cycles:0)
       <<",\"matrix_wide_steps\":"<<r.matrix_wide_steps<<",\"matrix_slice_steps\":"<<r.matrix_slice_steps
       <<",\"matrix_stalls\":"<<r.matrix_stalls<<",\"binary_add_requests\":"<<r.add_requests
       <<",\"binary_add_results\":"<<r.add_results<<",\"n0_read_bytes_pc1\":"<<r.n0_read_bytes
       <<",\"wq_read_bytes_pc1\":"<<r.wq_read_bytes<<",\"pc1_axi\":{";
#define COUNT(N) out<<"\"" #N "\":"<<r.pc1_axi.N<<',';
    COUNT(ars);COUNT(rbeats_expected);COUNT(rbeats);COUNT(rlasts);COUNT(aws);COUNT(wbeats_expected);
    COUNT(wbeats);COUNT(wbeats_committed);COUNT(bs);COUNT(strobed_bytes);COUNT(ar_stall);COUNT(aw_stall);
    COUNT(w_stall);COUNT(r_stall);
#undef COUNT
    out<<"\"b_stall\":"<<r.pc1_axi.b_stall<<"},\"qraw_values\":"<<(ack?196608:0)
       <<",\"qraw_bytes\":"<<r.qraw_f32le.size()<<"}\n";out.flush();
}
}
int main(int argc,char** argv) {
    RunPhase phase=RunPhase::INPUT_LOAD;
    int output_fd=-1;
    Pc01FailureCapsule diagnostic; // outlives RuntimeOwner, model and checked() unwind
    auto terminal=[&](const char* status,SafeCode code,int exit_code) {
        std::array<char,1024> text{};
        const int size=std::snprintf(text.data(),text.size(),
            "{\"scope\":\"PC0_ACK0_PC1_ACK1_M128_ONLY\",\"status\":\"%s\",\"phase\":\"%s\",\"code\":\"%s\",\"numeric_comparison\":\"NOT_RUN\"}\n",
            status,phase_name(phase),code_name(code));
        if(size<=0||static_cast<std::size_t>(size)>=text.size())return 1;
        if(output_fd>=0)first_n0::exclusive_write(output_fd,"counts.json",text.data(),static_cast<std::size_t>(size));
        std::cout.write(text.data(),size);std::cout.flush();
        // Supplementary bounded line only; never changes the original terminal code/exit.
        diagnostic.emit_noexcept(stdout);return exit_code;
    };
    if(argc!=3)return terminal("CLI_ERROR",SafeCode::CLI_ARGUMENT_COUNT,64);
    try {
        const std::filesystem::path input_root(argv[1]),output_root(argv[2]);
        if(!input_root.is_absolute())return terminal("CLI_ERROR",SafeCode::CLI_INPUT_ROOT,64);
        if(!output_root.is_absolute())return terminal("CLI_ERROR",SafeCode::CLI_OUTPUT_ROOT,64);
        for(const auto& p:input_root)if(p=="..")return terminal("CLI_ERROR",SafeCode::CLI_PARENT_TRAVERSAL,64);
        for(const auto& p:output_root)if(p=="..")return terminal("CLI_ERROR",SafeCode::CLI_PARENT_TRAVERSAL,64);
        phase=RunPhase::OUTPUT; // fresh output-root setup only
        if(::mkdir(argv[2],0700)!=0)return terminal("INCOMPLETE_OUTPUT_IO",SafeCode::OUTPUT_DIRECTORY,2);
        first_n0::Fd output(first_n0::open_dir(argv[2]));output_fd=output.get();
        phase=RunPhase::INPUT_LOAD;
        first_n0::Fd input(first_n0::open_dir(argv[1]));
        first_n0::Fd metadata(::openat(input.get(),"metadata",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC));
        first_n0::Fd providers(::openat(input.get(),"providers",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC));
        auto owner=RuntimeOwner::canonical();
        for(std::size_t i=0;i<expected_inputs.size();++i) {
            const auto& in=expected_inputs[i];
            const std::string leaf=i==0?"host_commands.bin":i==1?"host_descriptors.bin":std::string(in.name)+".bin";
            first_n0::FixedInputBuffer buffer(i<2?metadata.get():providers.get(),leaf.c_str(),in.bytes);
            std::istream stream(&buffer);stream.exceptions(std::ios::badbit);owner.load_next(in.name,stream);
        }
        phase=RunPhase::READY;
        auto token=owner.finish();auto session=owner.take_runtime(token);session.require_ready();
        const auto result=owner.run_pc01(phase,diagnostic);
        const bool ack=result.status==Pc01Result::Status::Ack1Captured;
        phase=RunPhase::OUTPUT;
        if(result.n0.status==FirstN0Result::Status::Ack0ActualCaptured&&!first_n0::exclusive_write(output.get(),"actual_n0.f32le",result.n0.actual_f32le.data(),result.n0.actual_f32le.size()))
            return terminal("INCOMPLETE_OUTPUT_IO",SafeCode::OUTPUT_WRITE,2);
        if(ack&&!first_n0::exclusive_write(output.get(),"actual_qraw.f32le",result.qraw_f32le.data(),result.qraw_f32le.size()))
            return terminal("INCOMPLETE_OUTPUT_IO",SafeCode::OUTPUT_WRITE,2);
        std::ostringstream counts;report(counts,result);const auto raw=counts.str();
        if(!counts||!first_n0::exclusive_write(output.get(),"counts.json",raw.data(),raw.size()))
            return terminal("INCOMPLETE_OUTPUT_IO",SafeCode::OUTPUT_REPORT,2);
        output_fd=-1; // full immutable counts already saved; terminal must not overwrite it
        phase=ack?RunPhase::OUTPUT:(result.status==Pc01Result::Status::IncompletePc0?RunPhase::RTL_N0:RunPhase::RTL_PC1);
        const int code=terminal(ack?"ACK1_ACTUAL_CAPTURED":"INCOMPLETE_CYCLE_BUDGET",
            ack?SafeCode::ACK1_COMPLETE:SafeCode::CYCLE_BUDGET,ack?0:2);
        return std::cout?code:2;
    } catch(const first_n0::ResourceIncomplete& error) {
        output_fd=-1;return terminal("INCOMPLETE_RESOURCE",exact_exception_code(error.what()),2);
    } catch(const std::bad_alloc&) {
        output_fd=-1;return terminal("INCOMPLETE_RESOURCE",SafeCode::ALLOCATION_LIMIT,2);
    } catch(const std::exception& error) {
        // Exact bounded lookup only: unknown messages produce UNMAPPED, never raw text.
        output_fd=-1;return terminal("CONTRACT_ERROR",exact_exception_code(error.what()),1);
    } catch(...) {
        output_fd=-1;return terminal("CONTRACT_ERROR",SafeCode::UNMAPPED,1);
    }
}

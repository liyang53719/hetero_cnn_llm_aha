// SOURCE ONLY. Fixed 16 old-hash inputs; local actual output is not public diagnostics.
#include "first_n0_driver.hpp"
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
void report(std::ostream& out,const FirstN0Result& r) {
    const bool ack=r.status==FirstN0Result::Status::Ack0ActualCaptured;
    out<<"{\"scope\":\"FIRST_N0_M128_ONLY\",\"status\":\""
       <<(ack?"ACK0_ACTUAL_CAPTURED":"INCOMPLETE_CYCLE_BUDGET")
       <<"\",\"phase\":\""<<(ack?"OUTPUT":"RTL_N0")<<"\",\"code\":\""<<(ack?"ACK0_COMPLETE":"CYCLE_BUDGET")
       <<"\",\"numeric_comparison\":\"NOT_RUN\",\"full_block_pass\":false,\"root256_handles\":\"UNKNOWN\","
       <<"\"cycle_budget\":8000000,\"reduction_only_source_floor\":2428928,\"unproven_overhead_allowance\":5571072,"
       <<"\"cycles\":"<<r.counts.cycles<<",\"launches\":"<<r.counts.launches<<",\"jobs\":"<<r.counts.jobs
       <<",\"owner_dones\":"<<r.counts.owner_dones<<",\"completion_acks\":"<<r.counts.completion_acks
       <<",\"core_read_requests\":"<<r.counts.core_read_requests<<",\"core_write_requests\":"<<r.counts.core_write_requests
       <<",\"core_responses\":"<<r.counts.core_responses<<",\"committed_bytes\":"<<r.committed_bytes
       <<",\"successful_b\":"<<r.successful_b<<",\"writeback_bytes\":"<<r.writeback_bytes
       <<",\"post_pc\":"<<r.post_pc<<",\"post_issued_jobs\":"<<r.post_issued_jobs
       <<",\"further_eval_calls\":0,\"input_ar\":";array(out,r.counts.input_ar);
    out<<",\"input_read_bytes\":";array(out,r.counts.input_read_bytes);
    out<<",\"core_state_cycles\":";array(out,r.counts.core_state_cycles);
    out<<",\"hub_accepted\":";array(out,r.hub_accepted);
    out<<",\"hub_returned\":";array(out,r.hub_returned);
    out<<",\"idma_transfers\":"<<r.idma_transfers<<",\"idma_read_bursts\":"<<r.idma_read_bursts
       <<",\"idma_read_beats\":"<<r.idma_read_beats<<",\"idma_cache_hits\":"<<r.idma_cache_hits<<",\"axi\":{";
#define COUNT(N) out<<"\"" #N "\":"<<r.axi.N<<',';
    COUNT(ars);COUNT(rbeats_expected);COUNT(rbeats);COUNT(rlasts);COUNT(aws);COUNT(wbeats_expected);
    COUNT(wbeats);COUNT(wbeats_committed);COUNT(bs);COUNT(strobed_bytes);COUNT(ar_stall);COUNT(aw_stall);
    COUNT(w_stall);COUNT(r_stall);
#undef COUNT
    out<<"\"b_stall\":"<<r.axi.b_stall<<"},\"actual_values\":"<<(ack?196608:0)
       <<",\"actual_bytes\":"<<r.actual_f32le.size()<<"}\n";out.flush();
}
}
int main(int argc,char** argv) {
    RunPhase phase=RunPhase::INPUT_LOAD;
    int output_fd=-1;
    auto terminal=[&](const char* status,SafeCode code,int exit_code) {
        std::array<char,1024> text{};
        const int size=std::snprintf(text.data(),text.size(),
            "{\"scope\":\"FIRST_N0_M128_ONLY\",\"status\":\"%s\",\"phase\":\"%s\",\"code\":\"%s\",\"numeric_comparison\":\"NOT_RUN\"}\n",
            status,phase_name(phase),code_name(code));
        if(size<=0||static_cast<std::size_t>(size)>=text.size())return 1;
        if(output_fd>=0)first_n0::exclusive_write(output_fd,"counts.json",text.data(),static_cast<std::size_t>(size));
        std::cout.write(text.data(),size);std::cout.flush();return exit_code;
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
        const auto result=owner.run_first_n0(phase);
        const bool ack=result.status==FirstN0Result::Status::Ack0ActualCaptured;
        phase=RunPhase::OUTPUT;
        if(ack&&!first_n0::exclusive_write(output.get(),"actual_n0.f32le",result.actual_f32le.data(),result.actual_f32le.size()))
            return terminal("INCOMPLETE_OUTPUT_IO",SafeCode::OUTPUT_WRITE,2);
        std::ostringstream counts;report(counts,result);const auto raw=counts.str();
        if(!counts||!first_n0::exclusive_write(output.get(),"counts.json",raw.data(),raw.size()))
            return terminal("INCOMPLETE_OUTPUT_IO",SafeCode::OUTPUT_REPORT,2);
        output_fd=-1; // full immutable counts already saved; terminal must not overwrite it
        phase=ack?RunPhase::OUTPUT:RunPhase::RTL_N0;
        const int code=terminal(ack?"ACK0_ACTUAL_CAPTURED":"INCOMPLETE_CYCLE_BUDGET",
            ack?SafeCode::ACK0_COMPLETE:SafeCode::CYCLE_BUDGET,ack?0:2);
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

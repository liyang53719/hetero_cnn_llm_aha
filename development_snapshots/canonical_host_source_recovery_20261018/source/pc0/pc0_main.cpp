// SOURCE ONLY: fixed canonical M128 PC0, stop after the real completion0 ACK high.
#include "dpi_forwarders.hpp"
#include "shared_edge_runtime.hpp"
#include <fstream>
#include <sstream>
#include <vector>
#include <filesystem>
namespace host_pc0 {
using namespace canonical_host;
inline constexpr uint64_t max_cycles=2000000;
static void launch_payload(VHostBlockTop& d) {
    d.io_launch_bits_commandBase=inputs[0].base;d.io_launch_bits_commandLimit=inputs[0].base+inputs[0].bytes;
    d.io_launch_bits_commands=public_commands;d.io_launch_bits_descriptorBase=inputs[1].base;
    d.io_launch_bits_descriptorLimit=inputs[1].base+inputs[1].bytes;d.io_launch_bits_descriptors=descriptor_records;
    d.io_launch_bits_epoch=epoch;
#define PC0_REGION(I) d.io_launch_bits_regions_##I##_base=regions[I].base;d.io_launch_bits_regions_##I##_limit=regions[I].limit; \
    d.io_launch_bits_regions_##I##_read=regions[I].read;d.io_launch_bits_regions_##I##_write=regions[I].write;
    PC0_REGION(0);PC0_REGION(1);PC0_REGION(2);PC0_REGION(3);
#undef PC0_REGION
}
static void exact_pre_high(const VHostBlockTop& d,const n0_physical::Frame& f) {
    require(d.clock==0&&!d.reset&&!d.io_resetRequired&&d.io_pc==0&&d.io_issuedJobs<=1,"only PC0 before every high edge");
    if(f.job_valid) {
        const auto& j=f.bound;
        require(j.kind==0&&j.tag==owner_tag(0)&&j.m==128&&j.n==1536&&j.k==1536&&j.a==inputs[15].base&&
            j.b==inputs[9].base&&j.c==0&&j.dst==outputs[0].base&&j.writeBytes==outputs[0].bytes,"reject any non-N0 offer before high");
        require(d.io_issuedJobs==0,"reject duplicate N0 offer before high");
    }
    require(!d.io_result_valid,"full Host terminal is outside bounded PC0");
}
template<class T> static void array(std::ostream& o,const T& a) {o<<'[';bool comma=false;for(auto v:a){if(comma)o<<',';o<<v;comma=true;}o<<']';}
static void evidence(std::ostream& o,const n0_shared::PublicationEvidence& e) {
    const auto& a=e.axi;
    o<<"{\"ack_edge\":"<<e.edge<<",\"completion_ack_word\":"<<e.completion_ack_word<<",\"committed_bytes\":"<<e.committed_bytes
     <<",\"successful_b\":"<<e.successful_b<<",\"owner_tag\":"<<e.owner_tag<<",\"epoch\":"<<e.epoch
     <<",\"metadata_requests\":"<<e.metadata_requests<<",\"metadata_returns\":"<<e.metadata_returns<<",\"hub_accepted\":";array(o,e.hub.accepted);
    o<<",\"hub_returned\":";array(o,e.hub.returned);o<<",\"axi\":{";
#define PC0_COUNT(N) o<<"\"" #N "\":"<<a.N<<',';
    PC0_COUNT(ars);PC0_COUNT(rbeats_expected);PC0_COUNT(rbeats);PC0_COUNT(rlasts);PC0_COUNT(aws);PC0_COUNT(wbeats_expected);
    PC0_COUNT(wbeats);PC0_COUNT(wbeats_committed);PC0_COUNT(bs);PC0_COUNT(strobed_bytes);PC0_COUNT(ar_stall);PC0_COUNT(aw_stall);
    PC0_COUNT(w_stall);PC0_COUNT(r_stall);PC0_COUNT(b_stall);
#undef PC0_COUNT
    o<<"\"ar_id\":";array(o,a.ar_id);o<<",\"rlast_id\":";array(o,a.rlast_id);o<<",\"aw_id\":";array(o,a.aw_id);o<<",\"b_id\":";array(o,a.b_id);o<<"}}";
}
static void progress(uint64_t cycles,const VHostBlockTop& d,const char* phase) {
    std::cerr<<"{\"progress\":\""<<phase<<"\",\"completed_cycles\":"<<cycles<<",\"pc\":"<<d.io_pc
      <<",\"issued_jobs\":"<<d.io_issuedJobs<<",\"write_bytes\":"<<d.io_writeBytes<<"}\n";std::cerr.flush();
}
}
int main(int argc,char**) {
    if(argc!=1){std::cerr<<"FAIL: fixed PC0 consumer takes no arguments\n";return 1;}
    using namespace canonical_host;
    host_startup::Ledger audit;host_startup::active_ledger=&audit;
    uint64_t cycles=0;
    try {
        std::ostringstream body;
        {
            VerilatedContext context;context.threads(1);context.randReset(0);context.randSeed(1);Verilated::threadContextp(&context);
            VHostBlockTop model{&context,"TOP"};audit.bind(model);host_startup::zero_inputs(model);
            auto reset_step=[&](unsigned phase,unsigned clock,unsigned reset) {
                model.clock=clock;model.reset=reset;audit.begin_eval(phase,clock,reset);
                const auto before=host_startup::input_snapshot(model);model.eval();
                require(!context.gotFinish()&&!context.gotError()&&before==host_startup::input_snapshot(model),"reset eval/input failure");
                audit.end_eval();context.timeInc(1);
            };
            reset_step(0,0,1);reset_step(1,0,0);reset_step(2,0,1);
            for(unsigned p=3;p<=10;++p)reset_step(p,p%2==1?1:0,1);
            reset_step(11,0,0);for(unsigned p=12;p<=19;++p)reset_step(p,p%2==0?1:0,0);
            // Same model and same private RAM from load to B commit to actual readback.
            shared_edge::SharedEdgeRuntime runtime(model);n0_physical::N0Fields fields(model);
            host_pc0::progress(0,model,"loading_full14_plus2");
            const auto loaded=runtime.load(std::cin);loaded.require_all14_v2_streams_exhausted();runtime.require_ready();
            require(loaded.stream_sha256()=="fb078e0219e876a8e8fe10212113f7d7c2341a5ce916810c2101e3af410761c7","fixed framed stream hash");
            Sha256Cpu sha;std::array<std::string,16> ram_hashes{};
            for(size_t i=0;i<inputs.size();++i) {ram_hashes[i]=sha.digest(runtime.read_input_span(i,0,inputs[i].bytes));require(ram_hashes[i]==inputs[i].sha256,"independent actual RAM input hash");}
            host_pc0::progress(0,model,"actual_ram16_hashes_verified");
            audit.begin_work();host_pc0::launch_payload(model);model.io_completion_ready=1;model.io_result_ready=0;
            bool launched=false,acked=false;uint64_t completion_word=0;
            n0_shared::PublicationEvidence publication{};
            unsigned post_pc=0,post_issued=0,post_ar=0,post_aw=0,post_w=0,post_job=0;
            for(uint64_t edge=0;edge<host_pc0::max_cycles;++edge) {
                model.io_launch_valid=edge>0&&!launched;
                audit.begin_work_eval(0);runtime.settle_low(edge);audit.end_work_eval();context.timeInc(1);
                const auto pre=fields.read(false);host_pc0::exact_pre_high(model,pre);
                const bool launch_fire=model.io_launch_valid&&model.io_launch_ready;
                const bool completion_fire=model.io_completion_valid&&model.io_completion_ready;
                if(completion_fire)completion_word=model.io_completion_bits;
                audit.begin_work_eval(1);const auto capture=runtime.rise_and_observe(edge);audit.end_work_eval();context.timeInc(1);
                require(!capture,"no SiLU capture belongs to PC0");++cycles;
                if(launch_fire){require(!launched,"single launch handshake");launched=true;}
                if(completion_fire) {
                    runtime.require_n0_published();publication=runtime.n0_publication_evidence();
                    require(launched&&publication.completion_ack_word==completion_word,"same real ACK0 publication");
                    post_pc=model.io_pc;post_issued=model.io_issuedJobs;post_ar=model.io_axi_ar_valid;post_aw=model.io_axi_aw_valid;post_w=model.io_axi_w_valid;
                    post_job=fields.read(true).job_valid;
                    acked=true;break; // NO subsequent low/high evaluation, even if next metadata offer is now visible.
                }
                if(cycles%8192==0)host_pc0::progress(cycles,model,"running_pc0");
            }
            if(!acked) {
                host_pc0::progress(cycles,model,"cycle_bound_reached");audit.poison();host_startup::active_ledger=nullptr;
                std::cout<<"{\"scope\":\"BOUNDED_CANONICAL_M128_PC0_ONLY\",\"status\":\"NOT_COMPLETED\",\"completed_cycles\":"<<cycles<<"}\n";return 2;
            }
            require(cycles<=host_pc0::max_cycles&&post_issued==1&&post_pc==1,"ACK0 advance only, one owner issued");
            std::vector<uint8_t> actual(outputs[0].bytes);
            for(uint64_t i=0;i<outputs[0].bytes;++i)actual[i]=runtime.actual_byte(outputs[0].base+i);
            const auto actual_sha=sha.digest({actual.data(),actual.size()});
            require(!std::filesystem::exists("actual_n0.f32le"),"fresh actual-only output required");
            {std::ofstream output("actual_n0.f32le",std::ios::binary);require(bool(output),"actual output open");output.write(reinterpret_cast<const char*>(actual.data()),std::streamsize(actual.size()));output.close();require(bool(output),"actual output write/close");}
            body<<"{\"scope\":\"BOUNDED_CANONICAL_M128_PC0_ONLY\",\"status\":\"PC0_ACKED_ACTUAL_BYTES_CAPTURED\",\"full_block_pass\":false,\"completed_cycles\":"<<cycles
                <<",\"rows\":128,\"payload_bytes\":94920448,\"wire_bytes\":94921526,\"stream_sha256\":\""<<loaded.stream_sha256()<<"\",\"actual_input_hashes\":[";
            for(size_t i=0;i<inputs.size();++i){if(i)body<<',';body<<"{\"index\":"<<i<<",\"name\":\""<<inputs[i].name<<"\",\"bytes\":"<<inputs[i].bytes<<",\"sha256\":\""<<ram_hashes[i]<<"\"}";}
            body<<"],\"actual_n0_bytes\":"<<actual.size()<<",\"actual_n0_sha256\":\""<<actual_sha<<"\",\"publication\":";host_pc0::evidence(body,publication);
            body<<",\"post_ack\":{\"pc\":"<<post_pc<<",\"issued_jobs\":"<<post_issued<<",\"ar_offer\":"<<post_ar<<",\"aw_offer\":"<<post_aw<<",\"w_offer\":"<<post_w<<",\"job_offer\":"<<post_job<<",\"further_eval_calls\":0},\"dpi\":";
            audit.end_work();audit.begin_final();model.final();audit.end_final();
        }
        audit.report(body);body<<"}\n";require(bool(body),"PC0 report build");std::cout<<body.str();std::cout.flush();require(bool(std::cout),"PC0 report flush");
        host_startup::active_ledger=nullptr;return 0;
    } catch(const std::exception& error) {audit.poison();host_startup::active_ledger=nullptr;std::cerr<<"FAIL PC0 after "<<cycles<<" completed cycles: "<<error.what()<<'\n';return 1;}
      catch(...) {audit.poison();host_startup::active_ledger=nullptr;std::cerr<<"FAIL PC0 unknown after "<<cycles<<" completed cycles\n";return 1;}
}

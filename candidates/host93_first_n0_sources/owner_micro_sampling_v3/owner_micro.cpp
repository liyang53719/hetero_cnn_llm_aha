// Bounded original-owner RTL stimulus. No Host/N0 history or iDMA/AXI claim.
#include "VQwenOwnerKernel.h"
#include "VQwenOwnerKernel___024root.h"
#include "verilated.h"
#include "sha256.hpp"
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
#include <utility>

namespace micro {
constexpr std::uint64_t A=4483535872ULL, B=4295032896ULL, D=4484322368ULL;
constexpr std::uint64_t WORKSPACE=4507654464ULL, EXTENT=786432ULL;
constexpr std::uint32_t TAG=458753U, IDENTITY=TAG+1U;
constexpr std::uint64_t LIMIT=500000, PERIOD=32768;
constexpr const char* N0_SHA="3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f";
constexpr const char* WQ_SHA="ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72";
struct Failure { const char* code; };
void need(bool ok,const char* code) {if(!ok)throw Failure{code};}
struct Fd {int n; explicit Fd(int x):n(x){need(n>=0,"INPUT_OPEN");} ~Fd(){::close(n);} Fd(const Fd&)=delete;};
bool stamp(const struct stat& a,const struct stat& b) {
    return a.st_dev==b.st_dev&&a.st_ino==b.st_ino&&a.st_mode==b.st_mode&&a.st_size==b.st_size&&
      a.st_mtim.tv_sec==b.st_mtim.tv_sec&&a.st_mtim.tv_nsec==b.st_mtim.tv_nsec&&
      a.st_ctim.tv_sec==b.st_ctim.tv_sec&&a.st_ctim.tv_nsec==b.st_ctim.tv_nsec;
}
std::vector<std::uint8_t> load(const char* name,std::size_t size,const char* expected) {
    const std::string path(name);need(path.size()>1&&path[0]=='/'&&path.back()!='/',"INPUT_ABSOLUTE_PATH");
    auto dir=std::make_unique<Fd>(::open("/",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC));
    std::size_t at=1;std::string leaf;
    while(at<path.size()) {
        const auto slash=path.find('/',at);leaf=path.substr(at,slash==std::string::npos?slash:slash-at);
        need(!leaf.empty()&&leaf!="."&&leaf!="..","INPUT_PATH_COMPONENT");
        if(slash==std::string::npos)break;
        dir=std::make_unique<Fd>(::openat(dir->n,leaf.c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC));at=slash+1;
    }
    Fd fd(::openat(dir->n,leaf.c_str(),O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC));
    struct stat before{},after{},named{};
    need(::fstat(fd.n,&before)==0&&S_ISREG(before.st_mode)&&before.st_size>=0&&std::uint64_t(before.st_size)==size,"INPUT_SIZE_TYPE");
    std::vector<std::uint8_t> data(size);std::size_t pos=0;
    while(pos<size) {ssize_t n=::read(fd.n,data.data()+pos,size-pos);if(n<0&&errno==EINTR)continue;need(n>0,"INPUT_SHORT_READ");pos+=std::size_t(n);}
    std::uint8_t extra{};ssize_t n;do{n=::read(fd.n,&extra,1);}while(n<0&&errno==EINTR);
    need(n==0&&::fstat(fd.n,&after)==0&&::fstatat(dir->n,leaf.c_str(),&named,AT_SYMLINK_NOFOLLOW)==0&&stamp(before,after)&&stamp(before,named),"INPUT_STABLE_BUFFER");
    same_buffer_loader_v1::Sha256 hash;hash.update(data.data(),data.size());const auto digest=hash.finish();
    constexpr char hex[]="0123456789abcdef";std::string got;for(auto v:digest){got+=hex[v>>4];got+=hex[v&15];}
    need(got==expected,"INPUT_SHA256");return data;
}
struct Tap {
#define OBS(N,M) std::uint64_t N=0;
#include "owner_observations.inc"
#undef OBS
};
Tap observe(const VQwenOwnerKernel& d) {
    need(d.rootp!=nullptr,"MODEL_ROOT");const auto* r=d.rootp;Tap t;
#define OBS(N,M) t.N=r->M;
#include "owner_observations.inc"
#undef OBS
    return t;
}
using Beat=std::array<std::uint32_t,16>;
template<class T> Beat beat(const T& x){Beat b{};for(unsigned i=0;i<16;++i)b[i]=x[i];return b;}
template<class T> void drive_beat(T& x,const Beat& b){for(unsigned i=0;i<16;++i)x[i]=b[i];}
bool inside(std::uint64_t base,std::uint64_t bytes,std::uint64_t address,std::uint64_t count) {
    return address>=base&&address-base<=bytes&&count<=bytes-(address-base);
}
struct Frames {
    bool burst=false,read_response=false,write_request=false,write_data=false,write_response=false,job=false,done=false;
    std::uint64_t read_address=0,read_tag=0,write_address=0,write_tag=0,write_beats=0;
    bool last=false;Beat words{};
};
struct Ram {
    enum class State {Idle,Read,WriteData,WriteResponse};State state=State::Idle;
    const std::vector<std::uint8_t> a,b;
    std::vector<std::uint8_t> output=std::vector<std::uint8_t>(EXTENT,0);
    std::vector<std::uint8_t> covered=std::vector<std::uint8_t>(EXTENT,0);
    std::uint64_t address=0,tag=0,count=0,index=0,due=0;
    Beat data{};
    std::uint64_t reads=0,read_responses=0,a_requested=0,b_requested=0,a_returned=0,b_returned=0;
    std::uint64_t descriptors=0,data_beats=0,write_responses=0,committed=0;
    bool previous_burst_stall=false,previous_descriptor_stall=false,previous_data_stall=false;
    std::uint64_t held_read_address=0,held_read_tag=0,held_write_address=0,held_write_tag=0,held_write_beats=0;
    Beat held_words{};bool held_last=false;
    Ram(std::vector<std::uint8_t> aa,std::vector<std::uint8_t> bb):a(std::move(aa)),b(std::move(bb)){}
    Beat read(std::uint64_t addr)const {
        need((addr&63)==0,"READ_ALIGNMENT");const std::vector<std::uint8_t>* v=nullptr;std::uint64_t base=0;
        if(inside(A,a.size(),addr,64)){v=&a;base=A;}
        else if(inside(B,b.size(),addr,64)){v=&b;base=B;}
        need(v!=nullptr,"READ_PAYLOAD_RANGE");Beat out{};
        for(unsigned w=0;w<16;++w)for(unsigned k=0;k<4;++k)out[w]|=std::uint32_t((*v)[addr-base+4*w+k])<<(8*k);
        return out;
    }
    void drive(VQwenOwnerKernel& d,std::uint64_t cycle)const {
        d.io_memory_ready=0;d.io_response_valid=0;d.io_response_bits_tag=0;d.io_response_bits_error=0;drive_beat(d.io_response_bits_data,Beat{});
        d.io_burst_ready=state==State::Idle;
        d.io_burstResponse_valid=state==State::Read&&cycle>=due;
        d.io_burstResponse_bits_tag=tag;d.io_burstResponse_bits_last=1;d.io_burstResponse_bits_error=0;drive_beat(d.io_burstResponse_bits_data,data);
        d.io_writeRequest_ready=0; // settled low pass supplies original burst priority
        d.io_writeData_ready=state==State::WriteData;
        d.io_writeResponse_valid=state==State::WriteResponse&&cycle>=due;
        d.io_writeResponse_bits_tag=tag;d.io_writeResponse_bits_error=0;drive_beat(d.io_writeResponse_bits_data,Beat{});
    }
    void priority(VQwenOwnerKernel& d)const {
        d.io_burst_ready=state==State::Idle&&!d.io_memory_valid;
        d.io_writeRequest_ready=state==State::Idle&&!d.io_memory_valid&&!d.io_burst_valid;
    }
    Frames low(const VQwenOwnerKernel& d,bool accepted) {
        need(!d.io_memory_valid,"UNEXPECTED_MEMORY_CHANNEL");
        if(previous_burst_stall)need(d.io_burst_valid&&d.io_burst_bits_address==held_read_address&&d.io_burst_bits_tag==held_read_tag,"READ_STALL_MUTATION");
        if(previous_descriptor_stall)need(d.io_writeRequest_valid&&d.io_writeRequest_bits_address==held_write_address&&d.io_writeRequest_bits_tag==held_write_tag&&d.io_writeRequest_bits_beats==held_write_beats,"DESCRIPTOR_STALL_MUTATION");
        if(previous_data_stall)need(d.io_writeData_valid&&beat(d.io_writeData_bits_data)==held_words&&bool(d.io_writeData_bits_last)==held_last,"WRITE_STALL_MUTATION");
        previous_burst_stall=d.io_burst_valid&&!d.io_burst_ready;held_read_address=d.io_burst_bits_address;held_read_tag=d.io_burst_bits_tag;
        previous_descriptor_stall=d.io_writeRequest_valid&&!d.io_writeRequest_ready;held_write_address=d.io_writeRequest_bits_address;held_write_tag=d.io_writeRequest_bits_tag;held_write_beats=d.io_writeRequest_bits_beats;
        previous_data_stall=d.io_writeData_valid&&!d.io_writeData_ready;held_words=beat(d.io_writeData_bits_data);held_last=d.io_writeData_bits_last;
        Frames f;f.job=d.io_job_valid&&d.io_job_ready;f.done=d.io_done_valid&&d.io_done_ready;
        f.burst=d.io_burst_valid&&d.io_burst_ready;f.read_response=d.io_burstResponse_valid&&d.io_burstResponse_ready;
        f.write_request=d.io_writeRequest_valid&&d.io_writeRequest_ready;f.write_data=d.io_writeData_valid&&d.io_writeData_ready;
        f.write_response=d.io_writeResponse_valid&&d.io_writeResponse_ready;
        need(!(f.burst&&f.write_request),"EXCLUSIVE_EXTERNAL_TRANSACTION");
        need(accepted||!(f.burst||f.write_request||f.write_data||f.read_response||f.write_response),"TRAFFIC_BEFORE_JOB");
        f.read_address=d.io_burst_bits_address;f.read_tag=d.io_burst_bits_tag;f.write_address=d.io_writeRequest_bits_address;f.write_tag=d.io_writeRequest_bits_tag;f.write_beats=d.io_writeRequest_bits_beats;f.last=d.io_writeData_bits_last;f.words=beat(d.io_writeData_bits_data);
        return f;
    }
    void retire(const Frames& f,std::uint64_t cycle,bool draining) {
        need(unsigned(f.burst)+unsigned(f.read_response)+unsigned(f.write_request)+unsigned(f.write_data)+unsigned(f.write_response)<=1,"MULTIPLE_RAM_RETIREMENTS");
        if(f.burst){need(state==State::Idle,"READ_DEBT");need((f.read_tag>>32)==TAG,"READ_TAG_OWNER");data=read(f.read_address);address=f.read_address;tag=f.read_tag;state=State::Read;due=cycle+1;++reads;if(address>=A){a_requested+=64;}else b_requested+=64;}
        if(f.read_response){need(state==State::Read,"READ_RESPONSE_DEBT");++read_responses;if(address>=A)a_returned+=64;else b_returned+=64;state=State::Idle;}
        if(f.write_request){
            need(state==State::Idle&&draining,"WRITE_DESCRIPTOR_PHASE");need(descriptors<128,"EXTRA_WRITE_DESCRIPTOR");
            need(f.write_address==D+descriptors*6144&&f.write_beats==10,"WRITE_NG0_ROW_PACKET");
            need((f.write_address&63)==0&&f.write_beats>0&&f.write_beats<=16&&((f.write_address&1023)+64*f.write_beats)<=1024&&inside(D,EXTENT,f.write_address,64*f.write_beats),"WRITE_DESCRIPTOR_RANGE");
            need((f.write_tag>>32)==TAG,"WRITE_TAG_OWNER");address=f.write_address;tag=f.write_tag;count=f.write_beats;index=0;state=State::WriteData;++descriptors;
        }
        if(f.write_data){
            need(state==State::WriteData&&index<count,"WRITE_DATA_DEBT");need(f.last==(index+1==count),"WRITE_LAST");
            const auto off=address-D+64*index;need(off+64<=output.size(),"WRITE_BOUNDS");
            for(unsigned j=0;j<64;++j)need(!covered[off+j],"DUPLICATE_OUTPUT_BYTE");
            for(unsigned w=0;w<16;++w)for(unsigned k=0;k<4;++k){const auto n=off+4*w+k;output[n]=std::uint8_t(f.words[w]>>(8*k));covered[n]=1;}
            ++index;++data_beats;committed+=64;if(index==count){state=State::WriteResponse;due=cycle+1;}
        }
        if(f.write_response){need(state==State::WriteResponse&&index==count,"WRITE_RESPONSE_DEBT");++write_responses;state=State::Idle;}
    }
};
struct Progress {
    std::uint64_t jobs=0,requests=0,terminals=0,drain_requests=0,drain_terminals=0,groups=0,dones=0,issues=0,current_issues=0;
    std::uint64_t current=0;bool window_live=false,draining=false;
    std::array<std::uint64_t,4> request_edges{};std::array<std::uint64_t,3> terminal_edges{};std::uint64_t drain_edge=0,target_edge=0;
    void retire(const Tap& t,const Tap& post,const Frames& f,std::uint64_t edge,const Ram& ram) {
        if(f.job){need(jobs==0,"DUPLICATE_JOB");++jobs;}
        need(!f.done,"UNEXPECTED_FULL_JOB_TERMINAL");
        if(t.win_request_valid&&t.win_request_ready){
            need(jobs==1&&!window_live&&requests<4,"WINDOW_REQUEST_ORDER");
            const auto ng=(requests/2)*160, slot=requests%2;
            need(t.win_request_bits_identity==IDENTITY&&t.win_request_bits_ng==ng&&t.win_request_bits_cols==160&&t.win_request_bits_slot==slot&&t.win_request_bits_reuseA==(requests!=0)&&t.win_request_bits_kWindow_enabled==1&&t.win_request_bits_kWindow_begin==(slot?1024:0)&&t.win_request_bits_kWindow_end==(slot?1536:1024)&&t.win_request_bits_kWindow_blockId==slot+1&&t.win_request_bits_kWindow_pairReverse==1,"WINDOW_REQUEST_METADATA");
            need(requests<2||drain_terminals==1,"SECOND_WINDOW_REQUIRES_DRAIN");
            current=requests;current_issues=0;window_live=true;request_edges[requests]=edge;++requests;
        }
        if(t.matrix_io_port_group_valid&&t.matrix_io_port_group_ready){need(window_live&&groups==current,"MATRIX_GROUP_ORDER");++groups;}
        if(t.matrix_io_port_step_valid&&t.matrix_io_port_step_ready){
            need(window_live&&groups==current+1&&t.matrix_group_sliceMask==255&&t.matrix_legalStep,"MATRIX_STEP_PROFILE");
            ++issues;++current_issues;need(current_issues<=((current%2)?2560:5120),"PARTIAL_EXCESS_ISSUES");
        }
        if(t.matrix_io_port_done_valid&&t.matrix_io_port_done_ready){need(window_live&&dones==current,"MATRIX_DONE_ORDER");++dones;}
        if(t.win_result_valid&&t.win_result_ready){
            need(window_live&&terminals==current&&current<3,"WINDOW_TERMINAL_ORDER");const auto slot=current%2,ng=(current/2)*160;
            need(t.win_result_bits_tag==TAG&&t.win_result_bits_identity==IDENTITY&&t.win_result_bits_ng==ng&&t.win_result_bits_rows==128&&t.win_result_bits_cols==160&&t.win_result_bits_slot==slot&&t.win_result_bits_status==0&&t.win_result_bits_committed==1&&t.win_result_bits_producedBeats==1280&&t.win_result_bits_ddrWriteBytes==0&&t.win_result_bits_kWindow_enabled==1&&t.win_result_bits_kWindow_begin==(slot?1024:0)&&t.win_result_bits_kWindow_end==(slot?1536:1024)&&t.win_result_bits_kWindow_blockId==slot+1&&t.win_result_bits_kWindow_pairReverse==1&&t.win_leaseValid==1&&t.win_busy==1,"WINDOW_TERMINAL_METADATA");
            need(current_issues==(slot?2560:5120)&&dones==current+1,"WINDOW_PHYSICAL_RETIREMENT");terminal_edges[terminals]=edge;++terminals;window_live=false;
        }
        if(t.drain_request_valid&&t.drain_request_ready){
            need(terminals==2&&requests==2&&!window_live&&!draining&&drain_requests==0,"DRAIN_REQUEST_ORDER");
            need(t.drain_request_bits_identity==IDENTITY&&t.drain_request_bits_ng==0&&t.drain_request_bits_cols==160,"DRAIN_REQUEST_METADATA");++drain_requests;draining=true;
        }
        if(t.drain_result_valid&&t.drain_result_ready){
            need(draining&&drain_terminals==0,"DRAIN_TERMINAL_ORDER");
            need(t.drain_result_bits_tag==TAG&&t.drain_result_bits_identity==IDENTITY&&t.drain_result_bits_ng==0&&t.drain_result_bits_rows==128&&t.drain_result_bits_cols==160&&t.drain_result_bits_status==0&&t.drain_result_bits_committed==1&&t.drain_result_bits_consumedBeats==1280&&t.drain_result_bits_ddrWriteBytes==81920,"DRAIN_TERMINAL_METADATA");
            need(ram.committed==81920&&ram.descriptors==128&&ram.write_responses==128,"DRAIN_EXTERNAL_RETIREMENT");++drain_terminals;draining=false;drain_edge=edge;
        }
        need(post.matrix_wideSteps==issues&&post.matrix_steps==issues*8,"PHYSICAL_COUNTER_IDENTITY");
        if(current==3&&window_live&&current_issues==1){
            need(requests==4&&terminals==3&&drain_terminals==1&&issues==12801&&groups==4&&dones==3,"TARGET_BOUNDARY_LEDGER");target_edge=edge;
        }
    }
};
struct HighSample {bool captured=false;std::uint64_t edge=0;bool resetRequired=false;Tap rtl;};
void report(const char* status,const char* code,const char* sample,std::uint64_t edge,bool verified,const Tap& t,const Progress& p,const Ram* ram,const HighSample* high=nullptr) {
    std::cout<<"{\"schema\":\"OWNER_MICRO_V1\",\"scope\":\"M128_ORIGINAL_OWNER_TYPED_RAM_ONLY\",\"status\":\""<<status<<"\",\"code\":\""<<code<<"\",\"sample\":\""<<sample<<"\",\"edge\":"<<edge
      <<",\"cycle_limit\":"<<LIMIT<<",\"inputs_verified\":"<<(verified?"true":"false")<<",\"job_completed\":false,\"host_prefix_executed\":false,\"idma_axi_executed\":false,\"official_raw_numeric_pass\":null,\"application_accuracy_pass\":null,\"typed_recipe_bit_exact_to_rtl\":null,\"full_block_pass\":false"
      <<",\"software\":{\"jobs\":"<<p.jobs<<",\"window_requests\":"<<p.requests<<",\"window_terminals\":"<<p.terminals<<",\"drain_requests\":"<<p.drain_requests<<",\"drain_terminals\":"<<p.drain_terminals<<",\"matrix_groups\":"<<p.groups<<",\"matrix_dones\":"<<p.dones<<",\"issues\":"<<p.issues<<",\"current_window_issues\":"<<p.current_issues<<",\"target_edge\":"<<p.target_edge;
    if(ram)std::cout<<",\"ram_state\":"<<unsigned(ram->state)<<",\"read_requests\":"<<ram->reads<<",\"read_responses\":"<<ram->read_responses<<",\"n0_requested_bytes\":"<<ram->a_requested<<",\"wq_requested_bytes\":"<<ram->b_requested<<",\"n0_returned_bytes\":"<<ram->a_returned<<",\"wq_returned_bytes\":"<<ram->b_returned<<",\"write_descriptors\":"<<ram->descriptors<<",\"write_data_beats\":"<<ram->data_beats<<",\"write_responses\":"<<ram->write_responses<<",\"committed_bytes\":"<<ram->committed;
    std::cout<<"},\"request_edges\":[";for(unsigned i=0;i<4;++i)std::cout<<(i?",":"")<<p.request_edges[i];
    std::cout<<"],\"terminal_edges\":[";for(unsigned i=0;i<3;++i)std::cout<<(i?",":"")<<p.terminal_edges[i];
    std::cout<<"],\"drain_edge\":"<<p.drain_edge<<",\"rtl\":{";bool comma=false;
#define OBS(N,M) if(comma)std::cout<<',';comma=true;std::cout<<"\"" #N "\":"<<t.N;
#include "owner_observations.inc"
#undef OBS
    std::cout<<"},\"raw_high_before_settle\":";
    if(high&&high->captured&&high->edge==edge){
        std::cout<<"{\"edge\":"<<high->edge<<",\"sample\":\"HIGH_EVAL_POST_EXTERNAL_INPUTS_PRE_RETIREMENT\",\"reset_required\":"<<(high->resetRequired?"true":"false")<<",\"rtl\":{";comma=false;
#define OBS(N,M) if(comma)std::cout<<',';comma=true;std::cout<<"\"" #N "\":"<<high->rtl.N;
#include "owner_observations.inc"
#undef OBS
        std::cout<<"}}";
    }else std::cout<<"null";
    std::cout<<"}\n";std::cout.flush();need(bool(std::cout),"REPORT_IO");
}
void initialize(VQwenOwnerKernel& d) {
#include "owner_inputs.inc"
    d.io_done_ready=1;d.io_resident_result_ready=1;
    d.io_prefixWorkspace_valid=1;d.io_prefixWorkspace_base=WORKSPACE;d.io_prefixWorkspace_extent=EXTENT;d.io_prefixWorkspace_generation=8;
    d.io_job_bits_kind=1;d.io_job_bits_m=128;d.io_job_bits_n=1536;d.io_job_bits_k=1536;
    d.io_job_bits_a=A;d.io_job_bits_b=B;d.io_job_bits_dst=D;d.io_job_bits_weightBf16=1;d.io_job_bits_writeBytes=EXTENT;d.io_job_bits_tag=TAG;
}
} // namespace micro
int main(int argc,char** argv) {
    using namespace micro;Progress p;Tap last;HighSample high;std::unique_ptr<Ram> ram;std::uint64_t edge=0;bool verified=false;
    const char* sample="PRE_MODEL";
    try {
        need(argc==3,"CLI_ARGUMENTS");auto a=load(argv[1],786432,N0_SHA);auto b=load(argv[2],4718592,WQ_SHA);ram=std::make_unique<Ram>(std::move(a),std::move(b));verified=true;
        VerilatedContext context;context.threads(1);context.randReset(0);context.randSeed(1);context.fatalOnError(false);Verilated::threadContextp(&context);
        VQwenOwnerKernel d(&context,"TOP");initialize(d);
        for(unsigned i=0;i<4;++i){d.reset=1;d.clock=0;d.eval();context.timeInc(1);d.clock=1;d.eval();context.timeInc(1);need(!context.gotError()&&!context.gotFinish(),"RESET_RUNTIME_ERROR");}
        d.reset=0;d.clock=0;d.eval();
        for(unsigned i=0;i<4;++i){d.clock=1;d.eval();context.timeInc(1);d.clock=0;d.eval();context.timeInc(1);need(!context.gotError()&&!context.gotFinish(),"RESET_RELEASE_RUNTIME_ERROR");}
        last=observe(d);need(!d.io_resetRequired&&!context.gotError()&&!context.gotFinish()&&d.io_job_ready&&!d.io_done_valid&&!d.io_resident_busy&&last.router_state==0&&last.coor_state==0&&last.matrix_wideSteps==0&&last.matrix_steps==0&&!last.owner_matrixDebt&&!last.owner_seedDebt&&!last.owner_readDebt&&!last.owner_writeDebt&&!last.owner_memoryDebt,"RESET_RELEASE_ERROR");
        report("PROGRESS","READY","POST_RESET",0,verified,last,p,ram.get(),&high);
        for(edge=1;edge<=LIMIT;++edge){
            sample="LOW_PRE_EDGE";d.clock=0;d.io_job_valid=p.jobs==0;ram->drive(d,edge);d.eval();ram->priority(d);d.eval();
            last=observe(d);need(!d.io_resetRequired,"RESET_REQUIRED_LOW");need(!context.gotError()&&!context.gotFinish(),"RUNTIME_STOP_LOW");
            const auto low=last;const auto fires=ram->low(d,p.jobs==1);context.timeInc(1);d.clock=1;d.eval();sample="HIGH_EVAL_POST_SOFTWARE_PREVIOUS_EDGE";last=observe(d);
            high.captured=true;high.edge=edge;high.resetRequired=d.io_resetRequired;high.rtl=last;
            need(!context.gotError()&&!context.gotFinish(),"RUNTIME_STOP_HIGH");
            // Preserve raw high diagnostics, then settle the sampled producer retirement
            // at clock low before judging combinational resetRequired. No next rising edge.
            auto next=p;next.retire(low,last,fires,edge,*ram);ram->retire(fires,edge,next.draining);p=next;context.timeInc(1);
            sample="LOW_POST_EDGE_SETTLING_SOFTWARE_RETIRED";d.clock=0;ram->drive(d,edge+1);d.eval();ram->priority(d);d.eval();
            sample="LOW_POST_EDGE_SETTLED_SOFTWARE_RETIRED";last=observe(d);
            need(!d.io_resetRequired,"RESET_REQUIRED_SETTLED");need(!context.gotError()&&!context.gotFinish(),"RUNTIME_STOP_SETTLED");
            if(p.target_edge){report("TARGET_BOUNDARY_OBSERVED","NG160_PARTIAL1_FIRST_ISSUE",sample,edge,verified,last,p,ram.get(),&high);d.final();return 0;}
            if(edge%PERIOD==0)report("PROGRESS","RUNNING",sample,edge,verified,last,p,ram.get(),&high);
        }
        report("INCOMPLETE","CYCLE_LIMIT",sample,LIMIT,verified,last,p,ram.get(),&high);return 2;
    }catch(const Failure& f){
        const int primary_exit=verified?1:2;
        try{report(verified?"CONTRACT_FAILURE":"INPUT_ERROR",f.code,sample,edge,verified,last,p,ram.get(),&high);}catch(...){}
        return primary_exit;
    }catch(const std::bad_alloc&){try{report("INCOMPLETE","ALLOCATION",sample,edge,verified,last,p,ram.get(),&high);}catch(...){}return 2;
    }catch(...){try{report("CONTRACT_FAILURE","UNMAPPED_EXCEPTION",sample,edge,verified,last,p,ram.get(),&high);}catch(...){}return 1;}
}

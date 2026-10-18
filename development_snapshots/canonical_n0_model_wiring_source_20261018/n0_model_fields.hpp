// New template projection of real retained field expressions. Observation only.
// This is NOT GeneratedBinding attestation or admission; production construction remains blocked.
#pragma once
#include "axi_protocol.hpp"
#include <limits>
#include <stdexcept>
#include <tuple>
#include <type_traits>
namespace canonical_host_wiring_v1 {
using canonical_host::Data512;using canonical_host::Sample;
inline void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
struct Job {
    uint64_t kind=0,tag=0,m=0,n=0,k=0,a=0,b=0,c=0,dst=0,writeBytes=0;
    auto key()const{return std::tie(kind,tag,m,n,k,a,b,c,dst,writeBytes);}
    bool operator==(const Job& x)const{return key()==x.key();}
};
struct Request {
    uint64_t write=0,address=0,mask=0,tag=0;Data512 data{};
    bool same_payload(const Request& x)const{return write==x.write&&address==x.address&&mask==x.mask&&data==x.data;}
};
struct Frame {
    Sample axi;Job bound,retained;Request core,hub,dma;
    uint64_t dma_stream=0;
    uint64_t dma_write_burst=0;
    uint64_t hub_capture_ready=0;
    uint64_t hub_capture_valid=0;
    uint64_t done_status=0;
    uint64_t done_bytes=0;
    uint64_t writeback_write=0;
    uint64_t writeback_tag=0;
    uint64_t writeback_byte_count=0;
    uint64_t cmd_pending=0;
    uint64_t job_valid=0;
    uint64_t job_ready=0;
    uint64_t core_start=0;
    uint64_t owner_active=0;
    uint64_t owner_mode=0;
    uint64_t owner_tag=0;
    uint64_t owner_rejected=0;
    uint64_t owner_poison=0;
    uint64_t router_state=0;
    uint64_t router_bad=0;
    uint64_t router_fault=0;
    uint64_t core_state=0;
    uint64_t core_poison=0;
    uint64_t core_status=0;
    uint64_t core_residual=0;
    uint64_t memory_valid=0;
    uint64_t memory_ready=0;
    uint64_t response_fire=0;
    uint64_t done_valid=0;
    uint64_t done_ready=0;
    uint64_t core_result_valid=0;
    uint64_t core_selected=0;
    uint64_t hub_state=0;
    uint64_t hub_owner=0;
    uint64_t hub_ready=0;
    uint64_t hub_response_valid=0;
    uint64_t hub_poison=0;
    uint64_t hub_original_tag=0;
    uint64_t hub_reply_tag=0;
    uint64_t hub_reply_error=0;
    uint64_t dma_state=0;
    uint64_t dma_poison=0;
    uint64_t dma_error=0;
    uint64_t writeback_error=0;
    uint64_t writeback_total=0;
    uint64_t writeback_pending=0;
};
template<class Model> class N0Fields {
    Model& model_;
    decltype(model_.rootp) const root_;
    template<unsigned Bits,class T> static uint64_t scalar(const T& v) {
        static_assert(std::is_integral_v<T> && std::is_unsigned_v<T>);
        static_assert(Bits>0 && Bits<=64 && Bits<=std::numeric_limits<T>::digits);
        if constexpr(Bits<64)require((uint64_t(v)>>Bits)==0,"retained N0 field width");
        return uint64_t(v);
    }
    template<class Words> static Data512 words(const Words& v) {
        Data512 out{};for(unsigned i=0;i<16;++i)out[i]=v[i];return out;
    }
    static void require_same_root(const Model& d) {
        require(d.rootp!=nullptr,"actual Host root missing");
        require(&d.clock==&d.rootp->clock,"actual Host port alias clock");
        require(&d.reset==&d.rootp->reset,"actual Host port alias reset");
        require(&d.io_axi_w_ready==&d.rootp->io_axi_w_ready,"actual Host port alias io_axi_w_ready");
        require(&d.io_axi_r_valid==&d.rootp->io_axi_r_valid,"actual Host port alias io_axi_r_valid");
        require(&d.io_launch_ready==&d.rootp->io_launch_ready,"actual Host port alias io_launch_ready");
        require(&d.io_launch_valid==&d.rootp->io_launch_valid,"actual Host port alias io_launch_valid");
        require(&d.io_launch_bits_regions_0_read==&d.rootp->io_launch_bits_regions_0_read,"actual Host port alias io_launch_bits_regions_0_read");
        require(&d.io_launch_bits_regions_0_write==&d.rootp->io_launch_bits_regions_0_write,"actual Host port alias io_launch_bits_regions_0_write");
        require(&d.io_launch_bits_regions_1_read==&d.rootp->io_launch_bits_regions_1_read,"actual Host port alias io_launch_bits_regions_1_read");
        require(&d.io_launch_bits_regions_1_write==&d.rootp->io_launch_bits_regions_1_write,"actual Host port alias io_launch_bits_regions_1_write");
        require(&d.io_launch_bits_regions_2_read==&d.rootp->io_launch_bits_regions_2_read,"actual Host port alias io_launch_bits_regions_2_read");
        require(&d.io_launch_bits_regions_2_write==&d.rootp->io_launch_bits_regions_2_write,"actual Host port alias io_launch_bits_regions_2_write");
        require(&d.io_launch_bits_regions_3_read==&d.rootp->io_launch_bits_regions_3_read,"actual Host port alias io_launch_bits_regions_3_read");
        require(&d.io_launch_bits_regions_3_write==&d.rootp->io_launch_bits_regions_3_write,"actual Host port alias io_launch_bits_regions_3_write");
        require(&d.io_result_ready==&d.rootp->io_result_ready,"actual Host port alias io_result_ready");
        require(&d.io_result_valid==&d.rootp->io_result_valid,"actual Host port alias io_result_valid");
        require(&d.io_result_bits_status==&d.rootp->io_result_bits_status,"actual Host port alias io_result_bits_status");
        require(&d.io_completion_ready==&d.rootp->io_completion_ready,"actual Host port alias io_completion_ready");
        require(&d.io_completion_valid==&d.rootp->io_completion_valid,"actual Host port alias io_completion_valid");
        require(&d.io_axi_aw_ready==&d.rootp->io_axi_aw_ready,"actual Host port alias io_axi_aw_ready");
        require(&d.io_axi_aw_valid==&d.rootp->io_axi_aw_valid,"actual Host port alias io_axi_aw_valid");
        require(&d.io_axi_aw_bits_id==&d.rootp->io_axi_aw_bits_id,"actual Host port alias io_axi_aw_bits_id");
        require(&d.io_axi_aw_bits_len==&d.rootp->io_axi_aw_bits_len,"actual Host port alias io_axi_aw_bits_len");
        require(&d.io_axi_aw_bits_size==&d.rootp->io_axi_aw_bits_size,"actual Host port alias io_axi_aw_bits_size");
        require(&d.io_axi_aw_bits_burst==&d.rootp->io_axi_aw_bits_burst,"actual Host port alias io_axi_aw_bits_burst");
        require(&d.io_axi_w_valid==&d.rootp->io_axi_w_valid,"actual Host port alias io_axi_w_valid");
        require(&d.io_axi_w_bits_last==&d.rootp->io_axi_w_bits_last,"actual Host port alias io_axi_w_bits_last");
        require(&d.io_axi_b_ready==&d.rootp->io_axi_b_ready,"actual Host port alias io_axi_b_ready");
        require(&d.io_axi_b_valid==&d.rootp->io_axi_b_valid,"actual Host port alias io_axi_b_valid");
        require(&d.io_axi_b_bits_id==&d.rootp->io_axi_b_bits_id,"actual Host port alias io_axi_b_bits_id");
        require(&d.io_axi_b_bits_resp==&d.rootp->io_axi_b_bits_resp,"actual Host port alias io_axi_b_bits_resp");
        require(&d.io_axi_ar_ready==&d.rootp->io_axi_ar_ready,"actual Host port alias io_axi_ar_ready");
        require(&d.io_axi_ar_valid==&d.rootp->io_axi_ar_valid,"actual Host port alias io_axi_ar_valid");
        require(&d.io_axi_ar_bits_id==&d.rootp->io_axi_ar_bits_id,"actual Host port alias io_axi_ar_bits_id");
        require(&d.io_axi_ar_bits_len==&d.rootp->io_axi_ar_bits_len,"actual Host port alias io_axi_ar_bits_len");
        require(&d.io_axi_ar_bits_size==&d.rootp->io_axi_ar_bits_size,"actual Host port alias io_axi_ar_bits_size");
        require(&d.io_axi_ar_bits_burst==&d.rootp->io_axi_ar_bits_burst,"actual Host port alias io_axi_ar_bits_burst");
        require(&d.io_axi_r_ready==&d.rootp->io_axi_r_ready,"actual Host port alias io_axi_r_ready");
        require(&d.io_axi_r_bits_id==&d.rootp->io_axi_r_bits_id,"actual Host port alias io_axi_r_bits_id");
        require(&d.io_axi_r_bits_resp==&d.rootp->io_axi_r_bits_resp,"actual Host port alias io_axi_r_bits_resp");
        require(&d.io_axi_r_bits_last==&d.rootp->io_axi_r_bits_last,"actual Host port alias io_axi_r_bits_last");
        require(&d.io_resetRequired==&d.rootp->io_resetRequired,"actual Host port alias io_resetRequired");
        require(&d.io_launch_bits_commands==&d.rootp->io_launch_bits_commands,"actual Host port alias io_launch_bits_commands");
        require(&d.io_launch_bits_epoch==&d.rootp->io_launch_bits_epoch,"actual Host port alias io_launch_bits_epoch");
        require(&d.io_result_bits_completed==&d.rootp->io_result_bits_completed,"actual Host port alias io_result_bits_completed");
        require(&d.io_result_bits_failedPc==&d.rootp->io_result_bits_failedPc,"actual Host port alias io_result_bits_failedPc");
        require(&d.io_result_bits_epoch==&d.rootp->io_result_bits_epoch,"actual Host port alias io_result_bits_epoch");
        require(&d.io_pc==&d.rootp->io_pc,"actual Host port alias io_pc");
        require(&d.io_issuedJobs==&d.rootp->io_issuedJobs,"actual Host port alias io_issuedJobs");
        require(&d.io_launch_bits_descriptors==&d.rootp->io_launch_bits_descriptors,"actual Host port alias io_launch_bits_descriptors");
        require(&d.io_axi_w_bits_data==&d.rootp->io_axi_w_bits_data,"actual Host port alias io_axi_w_bits_data");
        require(&d.io_axi_r_bits_data==&d.rootp->io_axi_r_bits_data,"actual Host port alias io_axi_r_bits_data");
        require(&d.io_launch_bits_commandBase==&d.rootp->io_launch_bits_commandBase,"actual Host port alias io_launch_bits_commandBase");
        require(&d.io_launch_bits_commandLimit==&d.rootp->io_launch_bits_commandLimit,"actual Host port alias io_launch_bits_commandLimit");
        require(&d.io_launch_bits_descriptorBase==&d.rootp->io_launch_bits_descriptorBase,"actual Host port alias io_launch_bits_descriptorBase");
        require(&d.io_launch_bits_descriptorLimit==&d.rootp->io_launch_bits_descriptorLimit,"actual Host port alias io_launch_bits_descriptorLimit");
        require(&d.io_launch_bits_regions_0_base==&d.rootp->io_launch_bits_regions_0_base,"actual Host port alias io_launch_bits_regions_0_base");
        require(&d.io_launch_bits_regions_0_limit==&d.rootp->io_launch_bits_regions_0_limit,"actual Host port alias io_launch_bits_regions_0_limit");
        require(&d.io_launch_bits_regions_1_base==&d.rootp->io_launch_bits_regions_1_base,"actual Host port alias io_launch_bits_regions_1_base");
        require(&d.io_launch_bits_regions_1_limit==&d.rootp->io_launch_bits_regions_1_limit,"actual Host port alias io_launch_bits_regions_1_limit");
        require(&d.io_launch_bits_regions_2_base==&d.rootp->io_launch_bits_regions_2_base,"actual Host port alias io_launch_bits_regions_2_base");
        require(&d.io_launch_bits_regions_2_limit==&d.rootp->io_launch_bits_regions_2_limit,"actual Host port alias io_launch_bits_regions_2_limit");
        require(&d.io_launch_bits_regions_3_base==&d.rootp->io_launch_bits_regions_3_base,"actual Host port alias io_launch_bits_regions_3_base");
        require(&d.io_launch_bits_regions_3_limit==&d.rootp->io_launch_bits_regions_3_limit,"actual Host port alias io_launch_bits_regions_3_limit");
        require(&d.io_completion_bits==&d.rootp->io_completion_bits,"actual Host port alias io_completion_bits");
        require(&d.io_axi_aw_bits_addr==&d.rootp->io_axi_aw_bits_addr,"actual Host port alias io_axi_aw_bits_addr");
        require(&d.io_axi_w_bits_strb==&d.rootp->io_axi_w_bits_strb,"actual Host port alias io_axi_w_bits_strb");
        require(&d.io_axi_ar_bits_addr==&d.rootp->io_axi_ar_bits_addr,"actual Host port alias io_axi_ar_bits_addr");
        require(&d.io_idmaTransfers==&d.rootp->io_idmaTransfers,"actual Host port alias io_idmaTransfers");
        require(&d.io_idmaStreamedWriteBeats==&d.rootp->io_idmaStreamedWriteBeats,"actual Host port alias io_idmaStreamedWriteBeats");
        require(&d.io_idmaStreamedBeats==&d.rootp->io_idmaStreamedBeats,"actual Host port alias io_idmaStreamedBeats");
        require(&d.io_pipelineIssues==&d.rootp->io_pipelineIssues,"actual Host port alias io_pipelineIssues");
        require(&d.io_pipelineStalls==&d.rootp->io_pipelineStalls,"actual Host port alias io_pipelineStalls");
        require(&d.io_idmaReadBursts==&d.rootp->io_idmaReadBursts,"actual Host port alias io_idmaReadBursts");
        require(&d.io_idmaReadBeats==&d.rootp->io_idmaReadBeats,"actual Host port alias io_idmaReadBeats");
        require(&d.io_idmaCacheHits==&d.rootp->io_idmaCacheHits,"actual Host port alias io_idmaCacheHits");
        require(&d.io_usefulMacs==&d.rootp->io_usefulMacs,"actual Host port alias io_usefulMacs");
        require(&d.io_executedMacs==&d.rootp->io_executedMacs,"actual Host port alias io_executedMacs");
        require(&d.io_writeBytes==&d.rootp->io_writeBytes,"actual Host port alias io_writeBytes");
        require(&d.io_memoryAccepted_0==&d.rootp->io_memoryAccepted_0,"actual Host port alias io_memoryAccepted_0");
        require(&d.io_memoryAccepted_1==&d.rootp->io_memoryAccepted_1,"actual Host port alias io_memoryAccepted_1");
        require(&d.io_memoryReturned_0==&d.rootp->io_memoryReturned_0,"actual Host port alias io_memoryReturned_0");
        require(&d.io_memoryReturned_1==&d.rootp->io_memoryReturned_1,"actual Host port alias io_memoryReturned_1");
    }
    static Sample sample(const Model& d) {
        
        Sample s;
        s.ar_valid = d.io_axi_ar_valid; s.ar_ready = d.io_axi_ar_ready;
        s.aw_valid = d.io_axi_aw_valid; s.aw_ready = d.io_axi_aw_ready;
        s.w_valid = d.io_axi_w_valid; s.w_ready = d.io_axi_w_ready;
        s.r_valid = d.io_axi_r_valid; s.r_ready = d.io_axi_r_ready;
        s.b_valid = d.io_axi_b_valid; s.b_ready = d.io_axi_b_ready;
        s.ar = {d.io_axi_ar_bits_addr, d.io_axi_ar_bits_id, d.io_axi_ar_bits_len,
                d.io_axi_ar_bits_size, d.io_axi_ar_bits_burst};
        s.aw = {d.io_axi_aw_bits_addr, d.io_axi_aw_bits_id, d.io_axi_aw_bits_len,
                d.io_axi_aw_bits_size, d.io_axi_aw_bits_burst};
        s.w.strb = d.io_axi_w_bits_strb; s.w.last = d.io_axi_w_bits_last;
        for (unsigned i = 0; i < 16; ++i) s.w.data[i] = d.io_axi_w_bits_data[i];
        s.r.id = d.io_axi_r_bits_id; s.r.resp = d.io_axi_r_bits_resp; s.r.last = d.io_axi_r_bits_last;
        for (unsigned i = 0; i < 16; ++i) s.r.data[i] = d.io_axi_r_bits_data[i];
        s.b.id = d.io_axi_b_bits_id; s.b.resp = d.io_axi_b_bits_resp;
        return s;
    }
public:
    explicit N0Fields(Model& model):model_(model),root_(model.rootp){require(root_!=nullptr,"model root missing");}
    Frame read(bool high)const {
        require(model_.rootp==root_,"retained root identity changed");require_same_root(model_);
        require(model_.clock==high && !model_.reset,"N0 exact actual sampling edge");
        const auto& r=*model_.rootp;Frame f{};
        f.axi=sample(model_);
        f.dma_stream=scalar<1>(r.HostBlockTop__DOT__dma__DOT__stream);
        f.dma_write_burst=scalar<1>(r.HostBlockTop__DOT__dma__DOT__writeBurst);
        f.hub_capture_ready=scalar<1>(r.HostBlockTop__DOT__hub__DOT__arb__DOT__io_out_ready_0);
        f.hub_capture_valid=scalar<1>(r.HostBlockTop__DOT__hub__DOT__arb__DOT__io_out_valid_0);
        f.done_status=scalar<8>(r.HostBlockTop__DOT__cmd__DOT__r_status);
        f.done_bytes=scalar<64>(r.HostBlockTop__DOT__cmd__DOT__r_writeBytes);
        f.writeback_write=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__write);
        f.writeback_tag=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__tag);
        f.writeback_byte_count=scalar<7>(r.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__byteCount);
        f.cmd_pending=scalar<1>(r.HostBlockTop__DOT__cmd__DOT__pending);
        f.job_valid=scalar<1>(r.HostBlockTop__DOT__cmd__DOT___io_job_valid_T_2);
        f.job_ready=scalar<1>(r.HostBlockTop__DOT__cmd__DOT__io_job_ready_0);
        f.core_start=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__io_startRequest_0);
        f.owner_active=scalar<1>(r.HostBlockTop__DOT__owner__DOT__active);
        f.owner_mode=scalar<4>(r.HostBlockTop__DOT__owner__DOT__mode);
        f.owner_tag=scalar<32>(r.HostBlockTop__DOT__owner__DOT__tag);
        f.owner_rejected=scalar<1>(r.HostBlockTop__DOT__owner__DOT__rejected);
        f.owner_poison=scalar<1>(r.HostBlockTop__DOT__owner__DOT__sharedPoison);
        f.router_state=scalar<2>(r.HostBlockTop__DOT__owner__DOT__qkvRouter__DOT__state);
        f.router_bad=scalar<1>(r.HostBlockTop__DOT__owner__DOT__qkvRouter__DOT__bad);
        f.router_fault=scalar<1>(r.HostBlockTop__DOT__owner__DOT__qkvRouter__DOT__fault);
        f.core_state=scalar<7>(r.HostBlockTop__DOT__owner__DOT__core__DOT__state);
        f.core_poison=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__poisoned);
        f.core_status=scalar<8>(r.HostBlockTop__DOT__owner__DOT__core__DOT__status);
        f.core_residual=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__resActive);
        f.memory_valid=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__io_memory_valid_0);
        f.memory_ready=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__io_memory_ready_0);
        f.response_fire=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__io_response_valid_0);
        f.done_valid=scalar<1>(r.HostBlockTop__DOT__cmd__DOT__io_done_valid_0);
        f.done_ready=scalar<1>(r.HostBlockTop__DOT__cmd__DOT___io_done_ready_T_2);
        f.core_result_valid=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT___io_result_valid_T_4);
        f.core_selected=scalar<1>(r.HostBlockTop__DOT__owner__DOT___core_io_result_ready_T_1);
        f.hub_state=scalar<3>(r.HostBlockTop__DOT__hub__DOT__state);
        f.hub_owner=scalar<1>(r.HostBlockTop__DOT__hub__DOT__owner);
        f.hub_ready=scalar<1>(r.HostBlockTop__DOT__hub__DOT__io_memory_ready_0);
        f.hub_response_valid=scalar<1>(r.HostBlockTop__DOT__hub__DOT__io_response_valid_0);
        f.hub_poison=scalar<1>(r.HostBlockTop__DOT__hub__DOT__poison);
        f.hub_original_tag=scalar<64>(r.HostBlockTop__DOT__hub__DOT__originalTag);
        f.hub_reply_tag=scalar<64>(r.HostBlockTop__DOT__hub__DOT__reply_tag);
        f.hub_reply_error=scalar<1>(r.HostBlockTop__DOT__hub__DOT__reply_error);
        f.dma_state=scalar<3>(r.HostBlockTop__DOT__dma__DOT__state);
        f.dma_poison=scalar<1>(r.HostBlockTop__DOT__dma__DOT__poison);
        f.dma_error=scalar<1>(r.HostBlockTop__DOT__dma__DOT__rsp_error);
        f.writeback_error=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__error);
        f.writeback_total=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__totalBytes);
        f.writeback_pending=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__writeback__DOT__pending);
        f.bound.kind=scalar<4>(r.HostBlockTop__DOT__cmd__DOT__bound_kind);
        f.bound.tag=scalar<32>(r.HostBlockTop__DOT__cmd__DOT__bound_tag);
        f.bound.m=scalar<16>(r.HostBlockTop__DOT__cmd__DOT__bound_m);
        f.bound.n=scalar<16>(r.HostBlockTop__DOT__cmd__DOT__bound_n);
        f.bound.k=scalar<16>(r.HostBlockTop__DOT__cmd__DOT__bound_k);
        f.bound.a=scalar<64>(r.HostBlockTop__DOT__cmd__DOT__bound_a);
        f.bound.b=scalar<64>(r.HostBlockTop__DOT__cmd__DOT__bound_b);
        f.bound.c=scalar<64>(r.HostBlockTop__DOT__cmd__DOT__bound_c);
        f.bound.dst=scalar<64>(r.HostBlockTop__DOT__cmd__DOT__bound_dst);
        f.bound.writeBytes=scalar<64>(r.HostBlockTop__DOT__cmd__DOT__bound_writeBytes);
        f.retained.kind=scalar<4>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_kind);
        f.retained.tag=scalar<32>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_tag);
        f.retained.m=scalar<16>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_m);
        f.retained.n=scalar<16>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_n);
        f.retained.k=scalar<16>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_k);
        f.retained.a=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_a);
        f.retained.b=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_b);
        f.retained.c=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_c);
        f.retained.dst=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_dst);
        f.retained.writeBytes=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__owner_writeBytes);
        f.core.write=scalar<1>(r.HostBlockTop__DOT__owner__DOT__core__DOT__request_write);
        f.core.address=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__request_address);
        f.core.mask=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__request_mask);
        f.core.tag=scalar<64>(r.HostBlockTop__DOT__owner__DOT__core__DOT__request_tag);
        f.core.data=words(r.HostBlockTop__DOT__owner__DOT__core__DOT__request_data);
        f.hub.write=scalar<1>(r.HostBlockTop__DOT__hub__DOT__request_write);
        f.hub.address=scalar<64>(r.HostBlockTop__DOT__hub__DOT__request_address);
        f.hub.mask=scalar<64>(r.HostBlockTop__DOT__hub__DOT__request_mask);
        f.hub.tag=scalar<64>(r.HostBlockTop__DOT__hub__DOT__request_tag);
        f.hub.data=words(r.HostBlockTop__DOT__hub__DOT__request_data);
        f.dma.write=scalar<1>(r.HostBlockTop__DOT__dma__DOT__req_write);
        f.dma.address=scalar<64>(r.HostBlockTop__DOT__dma__DOT__req_address);
        f.dma.mask=scalar<64>(r.HostBlockTop__DOT__dma__DOT__req_mask);
        f.dma.tag=scalar<64>(r.HostBlockTop__DOT__dma__DOT__rsp_tag);
        f.dma.data=words(r.HostBlockTop__DOT__dma__DOT__req_data);
        return f;
    }
};
} // namespace canonical_host_wiring_v1

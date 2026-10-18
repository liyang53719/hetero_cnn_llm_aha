// SOURCE ONLY. Reads actual retained generated members; no fabricated event inputs.
#pragma once
#include "host_fields.hpp"
namespace canonical_host::n0_physical {
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
class N0Fields {
    VHostBlockTop& model_;
    silu_observation::GeneratedBinding<VHostBlockTop> identity_;
    template<unsigned Bits,class T> static uint64_t scalar(const T& v) {
        static_assert(std::is_integral_v<T> && std::is_unsigned_v<T>);
        static_assert(Bits>0 && Bits<=64 && Bits<=std::numeric_limits<T>::digits);
        if constexpr(Bits<64)require((uint64_t(v)>>Bits)==0,"retained N0 field width");
        return uint64_t(v);
    }
    static Data512 words(const VlWide<16>& v) {
        Data512 out{};for(unsigned i=0;i<16;++i)out[i]=v[i];return out;
    }
public:
    explicit N0Fields(VHostBlockTop& model):model_(model),identity_(model){}
    Frame read(bool high)const {
        identity_.require_actual_profile();actual_v2::HostFields::require_same_root(model_);
        require(model_.clock==high && !model_.reset,"N0 exact actual sampling edge");
        const auto& r=*model_.rootp;Frame f{};
        f.axi=actual_v2::HostFields::axi_sample(model_);
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
} // namespace canonical_host::n0_physical

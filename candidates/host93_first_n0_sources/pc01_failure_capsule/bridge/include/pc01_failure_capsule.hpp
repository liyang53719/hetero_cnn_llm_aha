// SOURCE ONLY. Fixed scalar diagnostics; no execution, RAM, or publication authority.
#pragma once
#include <array>
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <type_traits>
namespace canonical_runtime_v1 {
enum class Pc01IdentitySite : unsigned { SettleEntry, LowEvalPost, RiseEntry, HighEvalPost };
struct Pc01IdentitySample final {
    unsigned known_mask=0, true_mask=0, first_false=8;
    bool probe(unsigned index,bool value) noexcept {
        known_mask|=1U<<index;if(value)true_mask|=1U<<index;else if(first_false==8)first_false=index;
        return value;
    }
    const char* value(unsigned index)const noexcept {
        return !(known_mask&(1U<<index))?"null":(true_mask&(1U<<index))?"true":"false";
    }
};
struct Pc01FailureCapsule final {
    bool present=false,ack0_valid=false,root_valid=false,context_valid=false;
    Pc01IdentitySite site=Pc01IdentitySite::SettleEntry;
    Pc01IdentitySample predicates{};
    std::array<std::uint8_t,32> n0_sha256{};
    std::uint64_t owner_phase=0,edge=0,entry_edge=0,accept_edge=0,ack_edge=0,pc1_cycles=0,pc1_jobs=0,pc1_dones=0,pc1_acks=0,qraw_b=0,qraw_committed=0,n0_read_bytes=0,wq_read_bytes=0;
    std::uint64_t ack0s=0,n0_cycles=0,n0_jobs=0,n0_dones=0,n0_committed=0,n0_b=0;
    std::uint64_t clock=0,reset=0,reset_required=0,pc=0,issued_jobs=0,write_bytes=0,useful_macs=0,executed_macs=0,owner_rejected=0,owner_poison=0,router_state=0,router_bad=0,router_fault=0,backend_reset=0,host_abort=0,group_reset_required=0,core_state=0,core_poison=0,core_status=0,hub_poison=0,dma_poison=0,writeback_error=0,matrix_steps=0,matrix_wide_steps=0,matrix_stalls=0,matrix_state=0,matrix_mask=0,matrix_valid=0,matrix_ready=0,matrix_legal=0,matrix_poison=0;
    static const char* site_name(Pc01IdentitySite s) noexcept {
        switch(s) {
        case Pc01IdentitySite::SettleEntry:return "SETTLE_ENTRY";
        case Pc01IdentitySite::LowEvalPost:return "LOW_EVAL_POST";
        case Pc01IdentitySite::RiseEntry:return "RISE_ENTRY";
        case Pc01IdentitySite::HighEvalPost:return "HIGH_EVAL_POST";
        }
        return "UNKNOWN";
    }
    // Bounded formatting only. No raw exception text, paths, pointers or tensor values.
    std::size_t format(char* buffer,std::size_t capacity)const noexcept {
        if(!present||!buffer||capacity==0)return 0;
        std::size_t used=0;bool ok=true;
        auto append=[&](const char* fmt,auto... values) noexcept {
            if(!ok)return;
            const int n=std::snprintf(buffer+used,capacity-used,fmt,values...);
            if(n<0||std::size_t(n)>=capacity-used){ok=false;return;}used+=std::size_t(n);
        };
        auto number=[&](const char* key,std::uint64_t value,bool valid=true) noexcept {
            if(valid)append(",\"%s\":%llu",key,static_cast<unsigned long long>(value));
            else append(",\"%s\":null",key);
        };
        append("{\"scope\":\"PC01_IDENTITY_FAILURE_CAPSULE_V1\",\"code\":\"PC1_022\","
               "\"sample_time\":\"BEFORE_IDENTITY_REQUIRE_AND_CHECKED_POISON\","
               "\"site\":\"%s\",\"known_mask\":%u,\"true_mask\":%u,\"first_false\":%u,"
               "\"root_valid\":%s,\"context_valid\":%s,\"ack0_valid\":%s,\"predicates\":{"
               "\"phase_runtime\":%s,\"n0_published\":%s,\"qraw_unpublished\":%s,\"root_nonnull\":%s,"
               "\"reset_clear\":%s,\"reset_required_clear\":%s,\"context_error_clear\":%s,\"context_finish_clear\":%s}",
               site_name(site),predicates.known_mask,predicates.true_mask,predicates.first_false,
               root_valid?"true":"false",context_valid?"true":"false",ack0_valid?"true":"false",
               predicates.value(0),predicates.value(1),predicates.value(2),predicates.value(3),
               predicates.value(4),predicates.value(5),predicates.value(6),predicates.value(7));
        number("owner_phase",owner_phase);
        number("edge",edge);
        number("entry_edge",entry_edge);
        number("accept_edge",accept_edge);
        number("ack_edge",ack_edge);
        number("pc1_cycles",pc1_cycles);
        number("pc1_jobs",pc1_jobs);
        number("pc1_dones",pc1_dones);
        number("pc1_acks",pc1_acks);
        number("qraw_b",qraw_b);
        number("qraw_committed",qraw_committed);
        number("n0_read_bytes",n0_read_bytes);
        number("wq_read_bytes",wq_read_bytes);
        number("ack0s",ack0s,ack0_valid);
        number("n0_cycles",n0_cycles,ack0_valid);
        number("n0_jobs",n0_jobs,ack0_valid);
        number("n0_dones",n0_dones,ack0_valid);
        number("n0_committed",n0_committed,ack0_valid);
        number("n0_b",n0_b,ack0_valid);
        number("clock",clock,root_valid);
        number("reset",reset,root_valid);
        number("reset_required",reset_required,root_valid);
        number("pc",pc,root_valid);
        number("issued_jobs",issued_jobs,root_valid);
        number("write_bytes",write_bytes,root_valid);
        number("useful_macs",useful_macs,root_valid);
        number("executed_macs",executed_macs,root_valid);
        number("owner_rejected",owner_rejected,root_valid);
        number("owner_poison",owner_poison,root_valid);
        number("router_state",router_state,root_valid);
        number("router_bad",router_bad,root_valid);
        number("router_fault",router_fault,root_valid);
        number("backend_reset",backend_reset,root_valid);
        number("host_abort",host_abort,root_valid);
        number("group_reset_required",group_reset_required,root_valid);
        number("core_state",core_state,root_valid);
        number("core_poison",core_poison,root_valid);
        number("core_status",core_status,root_valid);
        number("hub_poison",hub_poison,root_valid);
        number("dma_poison",dma_poison,root_valid);
        number("writeback_error",writeback_error,root_valid);
        number("matrix_steps",matrix_steps,root_valid);
        number("matrix_wide_steps",matrix_wide_steps,root_valid);
        number("matrix_stalls",matrix_stalls,root_valid);
        number("matrix_state",matrix_state,root_valid);
        number("matrix_mask",matrix_mask,root_valid);
        number("matrix_valid",matrix_valid,root_valid);
        number("matrix_ready",matrix_ready,root_valid);
        number("matrix_legal",matrix_legal,root_valid);
        number("matrix_poison",matrix_poison,root_valid);
        if(ack0_valid) {
            std::array<char,65> hex{};constexpr char digits[]="0123456789abcdef";
            for(std::size_t i=0;i<n0_sha256.size();++i){hex[2*i]=digits[n0_sha256[i]>>4];hex[2*i+1]=digits[n0_sha256[i]&15];}
            append(",\"n0_sha256\":\"%s\"",hex.data());
        } else append(",\"n0_sha256\":null");
        append(",\"numeric_comparison\":\"NOT_RUN\",\"root_cause\":null}\n");
        return ok?used:0;
    }
    void emit_noexcept(std::FILE* stream)const noexcept {
        if(!present||!stream)return;
        std::array<char,8192> text{};const auto size=format(text.data(),text.size());
        if(size){(void)std::fwrite(text.data(),1,size,stream);(void)std::fflush(stream);}
    }
};
static_assert(std::is_trivially_copyable<Pc01FailureCapsule>::value,"fixed scalar snapshot only");
static_assert(sizeof(Pc01FailureCapsule)<=1024,"bounded scalar snapshot storage");
}

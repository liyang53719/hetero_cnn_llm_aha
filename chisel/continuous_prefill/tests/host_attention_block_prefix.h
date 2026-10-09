// SPDX-License-Identifier: Apache-2.0
// Default-off diagnostics for the production block driver. No RTL or AXI
// service changes: capture after its first low eval, stop only after step().
#pragma once
#include "host_physical_axi.h"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <utility>

namespace attention_block_prefix {
// Deliberately outside std::exception, which the driver treats as a failure.
struct PrefixStop {};
using Clock = std::chrono::steady_clock;
using Fields = std::vector<std::pair<std::string,uint64_t>>;
static constexpr uint64_t fnvOffset=14695981039346656037ULL,fnvPrime=1099511628211ULL;
inline uint64_t cycleLimit(const std::string& value) {
  host_test::require(!value.empty(),"empty diagnostic prefix");
  uint64_t n=0;
  for(char c:value) {
    host_test::require(c>='0'&&c<='9'&&n<=65536,"invalid diagnostic prefix");
    n=n*10+unsigned(c-'0');
  }
  host_test::require(n>=37&&n<=65536,"diagnostic prefix must be 37..65536 cycles");
  return n;
}
inline void field(Fields& f,const char* name,uint64_t value){f.emplace_back(name,value);}
inline std::string fieldsJson(const Fields& fields) {
  std::ostringstream s;s<<'{';bool first=true;
  for(const auto& [name,value]:fields){if(!first)s<<',';first=false;s<<'"'<<name<<"\":"<<value;}
  s<<'}';return s.str();
}
inline void hashBytes(uint64_t& h,const std::string& s){for(unsigned char c:s){h^=c;h*=fnvPrime;}}
// Every byte of the actual valid R/W bus payload contributes, in fixed LE order.
// FNV is a deterministic comparison aid, never a cryptographic acceptance proof.
template<class Data> uint64_t dataHash(const Data& data) {
  uint64_t h=fnvOffset;
  for(unsigned i=0;i<16;i++)for(unsigned j=0;j<4;j++){h^=(uint32_t(data[i])>>(8*j))&255U;h*=fnvPrime;}
  return h;
}
inline std::string hex64(uint64_t n){std::ostringstream s;s<<std::hex<<std::setfill('0')<<std::setw(16)<<n;return s.str();}
template<class Data> std::string payloadHex(const Data& data) {
  std::ostringstream s;s<<std::hex<<std::setfill('0');
  for(unsigned i=0;i<16;i++)for(unsigned j=0;j<4;j++)s<<std::setw(2)<<((uint32_t(data[i])>>(8*j))&255U);
  return s.str();
}

class Recorder {
 public:
  explicit Recorder(uint64_t limit=0):limit_(limit){host_test::require(!limit||(limit>=37&&limit<=65536),"invalid diagnostic prefix limit");}
  bool enabled()const{return limit_!=0;}
  uint64_t memoryBytesHashed()const{return memoryBytes_;}
  // PhysicalAxi invokes owner.traffic after its first low eval, before ACKs or
  // writes are processed. Do not infer handshakes from pins after the high eval.
  template<class Bus> void capture(const Bus& bus) {
    if(!enabled())return;
    host_test::require(!captured_,"duplicate prefix capture");captured_=true;
    const auto& d=bus.d;
    field(pre_,"pre_reset",d.reset);field(pre_,"pre_run",bus.owner.run);field(pre_,"pre_running",bus.owner.running);
    field(pre_,"pre_pc",d.io_pc);field(pre_,"pre_launch_valid",d.io_launch_valid);field(pre_,"pre_launch_ready",d.io_launch_ready);
    field(pre_,"pre_completion_valid",d.io_completion_valid);field(pre_,"pre_completion_ready",d.io_completion_ready);
    field(pre_,"pre_completion_word",d.io_completion_valid?uint64_t(d.io_completion_bits):0);
    field(pre_,"pre_result_valid",d.io_result_valid);field(pre_,"pre_result_ready",d.io_result_ready);
#define PREFIX_CHANNEL(CH) \
    field(pre_,"pre_" #CH "_valid",d.io_axi_##CH##_valid); \
    field(pre_,"pre_" #CH "_ready",d.io_axi_##CH##_ready)
    PREFIX_CHANNEL(ar);PREFIX_CHANNEL(aw);PREFIX_CHANNEL(w);PREFIX_CHANNEL(r);PREFIX_CHANNEL(b);
#undef PREFIX_CHANNEL
#define PREFIX_ADDRESS(CH) \
    field(pre_,"pre_" #CH "_address",d.io_axi_##CH##_valid?uint64_t(d.io_axi_##CH##_bits_addr):0); \
    field(pre_,"pre_" #CH "_id",d.io_axi_##CH##_valid?uint64_t(d.io_axi_##CH##_bits_id):0); \
    field(pre_,"pre_" #CH "_len",d.io_axi_##CH##_valid?uint64_t(d.io_axi_##CH##_bits_len):0); \
    field(pre_,"pre_" #CH "_size",d.io_axi_##CH##_valid?uint64_t(d.io_axi_##CH##_bits_size):0); \
    field(pre_,"pre_" #CH "_burst",d.io_axi_##CH##_valid?uint64_t(d.io_axi_##CH##_bits_burst):0)
    PREFIX_ADDRESS(ar);PREFIX_ADDRESS(aw);
#undef PREFIX_ADDRESS
    field(pre_,"pre_w_mask",d.io_axi_w_valid?uint64_t(d.io_axi_w_bits_strb):0);
    field(pre_,"pre_w_last",d.io_axi_w_valid?uint64_t(d.io_axi_w_bits_last):0);
    field(pre_,"pre_w_data_fnv1a64",d.io_axi_w_valid?dataHash(d.io_axi_w_bits_data):0);
    field(pre_,"pre_r_id",d.io_axi_r_valid?uint64_t(d.io_axi_r_bits_id):0);
    field(pre_,"pre_r_resp",d.io_axi_r_valid?uint64_t(d.io_axi_r_bits_resp):0);
    field(pre_,"pre_r_last",d.io_axi_r_valid?uint64_t(d.io_axi_r_bits_last):0);
    field(pre_,"pre_r_data_fnv1a64",d.io_axi_r_valid?dataHash(d.io_axi_r_bits_data):0);
    field(pre_,"pre_b_id",d.io_axi_b_valid?uint64_t(d.io_axi_b_bits_id):0);
    field(pre_,"pre_b_resp",d.io_axi_b_valid?uint64_t(d.io_axi_b_bits_resp):0);
    // Local-only trace retains every actual payload bit for the runner's SHA256.
    // The compact report carries only payload hashes, never tensor bytes.
    payload_=",\"pre_w_payload_le_hex\":\""+(d.io_axi_w_valid?payloadHex(d.io_axi_w_bits_data):"")+"\",\"pre_r_payload_le_hex\":\""+(d.io_axi_r_valid?payloadHex(d.io_axi_r_bits_data):"")+"\"";
    activeCycles_+=bool(bus.owner.running);resetCycles_+=bool(d.reset);
    ar_+=bool(d.io_axi_ar_valid&&d.io_axi_ar_ready);aw_+=bool(d.io_axi_aw_valid&&d.io_axi_aw_ready);
    w_+=bool(d.io_axi_w_valid&&d.io_axi_w_ready);r_+=bool(d.io_axi_r_valid&&d.io_axi_r_ready);b_+=bool(d.io_axi_b_valid&&d.io_axi_b_ready);
  }
  template<class Bus> void step(Bus& bus,const std::filesystem::path& out) {
    if(!enabled()){bus.step();return;}
    const auto start=Clock::now();
    bus.step(); // Must return: final low eval and all B/R ACK bookkeeping finish.
    stepElapsedNs_+=uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count());
    host_test::require(captured_&&bus.ticks==completed_+1&&bus.d.clock==0,"prefix requires a completed physical step");
    field(pre_,"cycle",bus.ticks);
#define PREFIX_BUS(NAME,VALUE) field(pre_,NAME,uint64_t(bus.VALUE))
    PREFIX_BUS("end_rng",rng);PREFIX_BUS("end_read_beats",readBeats);PREFIX_BUS("end_read_acks",readAcks);
    PREFIX_BUS("end_write_beats",writeBeats);PREFIX_BUS("end_write_acks",writeAcks);
    PREFIX_BUS("end_read_bursts",readBursts);PREFIX_BUS("end_write_bursts",writeBursts);
    PREFIX_BUS("end_pending_valid",pending.valid);PREFIX_BUS("end_pending_write",pending.write);
    PREFIX_BUS("end_pending_error",pending.error);PREFIX_BUS("end_pending_address",pending.address);
    PREFIX_BUS("end_pending_id",pending.id);PREFIX_BUS("end_pending_total",pending.total);
    PREFIX_BUS("end_pending_remaining",pending.remaining);PREFIX_BUS("end_pending_delay",pending.delay);
    PREFIX_BUS("end_pending_final",pending.final);PREFIX_BUS("end_aw_valid",aw.valid);
    PREFIX_BUS("end_collected_beats",collected.size());PREFIX_BUS("end_committing_beats",committing.size());
    PREFIX_BUS("end_ar_held",arHeld);PREFIX_BUS("end_aw_held",awHeld);PREFIX_BUS("end_w_held",wHeld);
#undef PREFIX_BUS
    const auto& d=bus.d;
#define PREFIX_PORT(NAME,PORT) field(pre_,NAME,uint64_t(d.PORT))
    PREFIX_PORT("end_pc",io_pc);PREFIX_PORT("end_issued_jobs",io_issuedJobs);
    PREFIX_PORT("end_pipeline_issues",io_pipelineIssues);PREFIX_PORT("end_pipeline_stalls",io_pipelineStalls);
    PREFIX_PORT("end_idma_transfers",io_idmaTransfers);PREFIX_PORT("end_idma_read_bursts",io_idmaReadBursts);
    PREFIX_PORT("end_idma_read_beats",io_idmaReadBeats);PREFIX_PORT("end_idma_cache_hits",io_idmaCacheHits);
    PREFIX_PORT("end_idma_streamed_beats",io_idmaStreamedBeats);PREFIX_PORT("end_idma_streamed_write_beats",io_idmaStreamedWriteBeats);
    PREFIX_PORT("end_memory_accepted_0",io_memoryAccepted_0);PREFIX_PORT("end_memory_returned_0",io_memoryReturned_0);
    PREFIX_PORT("end_memory_accepted_1",io_memoryAccepted_1);PREFIX_PORT("end_memory_returned_1",io_memoryReturned_1);
    PREFIX_PORT("end_useful_macs",io_usefulMacs);PREFIX_PORT("end_executed_macs",io_executedMacs);
    PREFIX_PORT("end_write_bytes",io_writeBytes);PREFIX_PORT("end_reset_required",io_resetRequired);
    PREFIX_PORT("end_completion_valid",io_completion_valid);PREFIX_PORT("end_result_valid",io_result_valid);
#undef PREFIX_PORT
#define PREFIX_OWNER(NAME,VALUE) field(pre_,NAME,uint64_t(bus.owner.VALUE))
    PREFIX_OWNER("end_run",run);PREFIX_OWNER("end_running",running);PREFIX_OWNER("end_completions",completions);
    PREFIX_OWNER("end_successful",successful);PREFIX_OWNER("end_metadata_reads",metadata);
    PREFIX_OWNER("end_ack_bytes",ackBytes);PREFIX_OWNER("end_physical_bytes",physicalBytes);
    PREFIX_OWNER("end_inferred_length",inferredCommittedLength);PREFIX_OWNER("end_inferred_generation",inferredCommittedGeneration);
#undef PREFIX_OWNER
    if(!events_.is_open()){
      host_test::require(std::filesystem::is_directory(out)&&!std::filesystem::exists(out/"prefix_events.jsonl"),"fresh prefix events required");
      events_.open(out/"prefix_events.jsonl",std::ios::binary|std::ios::out);
      append("{\"schema\":\"HOST_ATTENTION_BLOCK_PREFIX_EVENTS_V1\",\"numerical_acceptance\":false,\"payload_encoding\":\"le_u32x16_hex\",\"timing_excluded\":true}\n");
    }
    latest_=fieldsJson(pre_);append(latest_.substr(0,latest_.size()-1)+payload_+"}\n");pre_.clear();captured_=false;++completed_;
    if(completed_==limit_){
      // Snapshot the actual physical store once, after the last complete step.
      // bus.mem aliases the driver's owner.mem; neither references nor dumps
      // participate. This auxiliary FNV digest supplements the full AXI SHA256.
      for(uint32_t word:bus.mem.words)for(unsigned i=0;i<4;i++){
        memoryDigest_^=(word>>(i*8))&255U;memoryDigest_*=fnvPrime;++memoryBytes_;
      }
      report(out);throw PrefixStop{};
    }
  }
 private:
  uint64_t limit_=0,completed_=0,stepElapsedNs_=0,digest_=fnvOffset,eventBytes_=0;
  uint64_t memoryBytes_=0,memoryDigest_=fnvOffset;
  uint64_t resetCycles_=0,activeCycles_=0,ar_=0,aw_=0,w_=0,r_=0,b_=0;
  bool captured_=false;
  Fields pre_;
  std::string latest_,payload_;
  std::ofstream events_;
  void append(const std::string& event){events_<<event;host_test::require(bool(events_),"prefix event write");hashBytes(digest_,event);eventBytes_+=event.size();}
  void report(const std::filesystem::path& out) {
    events_.flush();host_test::require(bool(events_),"prefix event flush");
    host_test::require(!std::filesystem::exists(out/"prefix.json"),"fresh prefix report required");
    std::ofstream f(out/"prefix.json");
    f<<"{\n\"schema\":\"HOST_ATTENTION_BLOCK_PREFIX_V1\",\n\"status\":\"BOUNDED_DIAGNOSTIC_PREFIX\",\n"
     <<"\"numerical_acceptance\":false,\n\"prefix_reached\":true,\n\"cycles\":"<<completed_
     <<",\n\"cycle_limit\":"<<limit_<<",\n\"constructor_cycles\":36,\n\"step_elapsed_ns\":"<<stepElapsedNs_
     <<",\n\"timing_scope\":\"elapsed PhysicalAxi.step calls including capture overhead; excludes event serialization, final memory digest and report; not isolated eval timing\",\n"
     <<"\"event_file\":\"prefix_events.jsonl\",\n\"event_bytes\":"<<eventBytes_
     <<",\n\"prefix_fnv1a64\":\""<<hex64(digest_)<<"\",\n\"prefix_hash_is_noncryptographic\":true,\n"
     <<"\"memory_hash_is_noncryptographic\":true,\n"
     <<"\"sha256_input\":\"exact prefix_events.jsonl bytes; no timings or output paths\",\n"
     <<"\"deterministic\":{\"cycles\":"<<completed_<<",\"reset_cycles\":"<<resetCycles_<<",\"active_cycles\":"<<activeCycles_
     <<",\"ar_handshakes\":"<<ar_<<",\"aw_handshakes\":"<<aw_<<",\"w_handshakes\":"<<w_
     <<",\"r_handshakes\":"<<r_<<",\"b_handshakes\":"<<b_
     <<",\"memory_bytes\":"<<memoryBytes_<<",\"memory_fnv1a64\":\""<<hex64(memoryDigest_)<<"\",\"terminal_event\":"<<latest_<<"}\n}\n";
    f.close();host_test::require(bool(f),"prefix report write");
  }
};
} // namespace attention_block_prefix

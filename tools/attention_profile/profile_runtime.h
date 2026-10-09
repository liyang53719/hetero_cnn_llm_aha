// SPDX-License-Identifier: Apache-2.0
#pragma once
// This header is used only by a generated copy of the physical test service.
// No RTL ports, hierarchy, arithmetic, command construction or store are changed.
#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace attention_profile {
using Clock = std::chrono::steady_clock;
using Fields = std::vector<std::pair<std::string, uint64_t>>;
static constexpr uint64_t fnvOffset = 14695981039346656037ULL;
static constexpr uint64_t fnvPrime = 1099511628211ULL;
// Intentionally not derived from std::exception: the frozen main catches those
// as genuine driver failures. Only the small diagnostic wrapper catches this.
struct PrefixStop {};
inline uint64_t ns(Clock::duration d) {
  return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(d).count());
}
inline void check(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
inline void hashBytes(uint64_t& h, const std::string& text) {
  for (unsigned char c : text) { h ^= c; h *= fnvPrime; }
}
// Hash bus data as sixteen fixed-width little-endian uint32 words. These hashes
// are diagnostic comparison aids, not cryptographic integrity/acceptance proofs.
// Raw model/weight/activation bytes are never put in the event log.
template<class Data> uint64_t dataHash(const Data& data) {
  uint64_t h = fnvOffset;
  for (unsigned i = 0; i < 16; ++i) for (unsigned j = 0; j < 4; ++j) {
    h ^= (uint32_t(data[i]) >> (j * 8)) & 255U; h *= fnvPrime;
  }
  return h;
}
inline void field(Fields& values, const char* name, uint64_t value) {
  values.emplace_back(name, value);
}
inline std::string fieldsJson(const Fields& fields) {
  std::ostringstream s; s << '{';
  bool first = true;
  for (const auto& item : fields) {
    if (!first) s << ',';
    first = false; s << '"' << item.first << "\":" << item.second;
  }
  s << '}'; return s.str();
}
inline std::string hex64(uint64_t value) {
  std::ostringstream s; s << std::hex << std::setfill('0') << std::setw(16) << value; return s.str();
}
struct State {
  bool configured = false;
  uint64_t limit = 0, completed = 0, stepElapsedNs = 0;
  uint64_t evalNs = 0, evalCalls = 0, evalAttempts = 0, eventBytes = 0;
  uint64_t digest = fnvOffset, reportWritesNs = 0;
  uint64_t activeCycles = 0, resetCycles = 0, incompleteSteps = 0;
  uint64_t arTransfers = 0, awTransfers = 0, wTransfers = 0, rTransfers = 0, bTransfers = 0;
  std::array<uint64_t, 3> phaseNs{}, phaseCalls{};
  std::filesystem::path out;
  std::ofstream events;
  Fields latest;
  Clock::time_point begun;
};
inline State& state() { static State s; return s; }
inline void configure(const std::filesystem::path& out, uint64_t limit) {
  auto& s = state();
  check(!s.configured, "profile already configured");
  check(limit >= 1 && limit <= 65536, "invalid bounded prefix limit");
  check(!out.empty() && !std::filesystem::exists(out) && !std::filesystem::is_symlink(out),
        "fresh execution output required");
  s.configured = true; s.out = out; s.limit = limit; s.begun = Clock::now();
}
inline void openEvents() {
  auto& s = state();
  if (s.events.is_open()) return;
  check(std::filesystem::is_directory(s.out), "frozen driver did not create output");
  const auto path = s.out / "prefix_events.jsonl";
  check(!std::filesystem::exists(path), "stale prefix events");
  s.events.open(path, std::ios::binary | std::ios::out);
  check(bool(s.events), "cannot open prefix events");
  const std::string header = "{\"schema\":\"HOST_ATTENTION_PREFIX_EVENTS_V1\","
    "\"source_base_commit\":\"6959810545203d5f9508075b311dba52f1bee0c9\","
    "\"numerical_acceptance\":false,\"payload_encoding\":\"fnv1a64_le_u32x16\","
    "\"timing_excluded\":true}\n";
  s.events << header; hashBytes(s.digest, header); s.eventBytes += header.size();
}
inline void writeReport(const char* status, bool reached) {
  auto& s = state();
  check(s.configured, "profile not configured");
  check(s.stepElapsedNs >= s.evalNs, "invalid timing accounting");
  if (reached) check(s.completed == s.limit && s.evalCalls == 3 * s.completed,
                     "prefix stop missing complete triple-eval steps");
  check(std::filesystem::is_directory(s.out), "execution output was not created");
  s.events.flush();
  if (s.events.is_open()) check(bool(s.events), "cannot flush prefix events");
  const auto tmp = s.out / "attention_profile.json.tmp";
  std::ofstream f(tmp, std::ios::out | std::ios::trunc);
  check(bool(f), "cannot open profile report");
  f << "{\n\"schema_version\":1,\n\"schema\":\"HOST_ATTENTION_PREFIX_PROFILE_V1\",\n"
    << "\"status\":\"" << status << "\",\n"
    << "\"numerical_acceptance\":false,\n\"prefix_reached\":" << (reached ? "true" : "false") << ",\n"
    << "\"source_base_commit\":\"6959810545203d5f9508075b311dba52f1bee0c9\",\n"
    << "\"cycle_limit\":" << s.limit << ",\n\"cycles\":" << s.completed << ",\n"
    << "\"constructor_cycles_included\":36,\n\"active_cycles\":" << s.activeCycles
    << ",\n\"reset_cycles\":" << s.resetCycles << ",\n"
    << "\"incomplete_steps\":" << s.incompleteSteps << ",\n"
    << "\"eval_calls\":" << s.evalCalls << ",\n\"eval_attempts\":" << s.evalAttempts << ",\n"
    << "\"eval_ns\":" << s.evalNs << ",\n\"step_elapsed_ns\":" << s.stepElapsedNs << ",\n"
    << "\"driver_excluding_eval_ns\":" << s.stepElapsedNs - s.evalNs << ",\n"
    << "\"driver_includes_instrumentation_overhead\":true,\n"
    << "\"timing_scope\":\"PhysicalAxi steps including incomplete exception step on failure; steady_clock; includes event/report instrumentation; excludes construction outside steps and final report\",\n"
    << "\"timing_interpretation\":\"instrumented diagnostic, not original uninstrumented performance\",\n"
    << "\"profile_wall_ns\":" << ns(Clock::now() - s.begun) << ",\n"
    << "\"prior_checkpoint_report_writes_ns\":" << s.reportWritesNs << ",\n"
    << "\"eval_phase_ns\":[" << s.phaseNs[0] << ',' << s.phaseNs[1] << ',' << s.phaseNs[2] << "],\n"
    << "\"eval_phase_calls\":[" << s.phaseCalls[0] << ',' << s.phaseCalls[1] << ',' << s.phaseCalls[2] << "],\n"
    << "\"eval_phase_order\":[\"clock_low_before_transfers\",\"clock_high\",\"clock_low_after_bookkeeping\"],\n"
    << "\"ar_handshakes\":" << s.arTransfers << ",\n\"aw_handshakes\":" << s.awTransfers
    << ",\n\"w_handshakes\":" << s.wTransfers << ",\n\"r_handshakes\":" << s.rTransfers
    << ",\n\"b_handshakes\":" << s.bTransfers << ",\n"
    << "\"event_file\":\"prefix_events.jsonl\",\n\"event_bytes\":" << s.eventBytes << ",\n"
    << "\"prefix_fnv1a64\":\"" << hex64(s.digest) << "\",\n"
    << "\"prefix_hash_is_noncryptographic\":true,\n"
    << "\"sha256_input\":\"exact event file bytes, excluding all timings and output paths\",\n"
    << "\"matrix_progress_source\":\"public io_pipelineIssues (wideSteps) and io_pipelineStalls; no internal hierarchy access\",\n"
    << "\"deterministic\":{\"cycles\":" << s.completed
    << ",\"active_cycles\":" << s.activeCycles << ",\"reset_cycles\":" << s.resetCycles
    << ",\"ar_handshakes\":" << s.arTransfers << ",\"aw_handshakes\":" << s.awTransfers
    << ",\"w_handshakes\":" << s.wTransfers << ",\"r_handshakes\":" << s.rTransfers
    << ",\"b_handshakes\":" << s.bTransfers
    << ",\"terminal_event\":" << fieldsJson(s.latest) << "}\n}\n";
  f.close(); check(bool(f), "cannot finish profile report");
  std::filesystem::rename(tmp, s.out / "attention_profile.json");
}
inline void finish(const char* status, bool reached) { writeReport(status, reached); }

class StepTimer {
  Clock::time_point start_;
  Fields pre_;
  unsigned nextPhase_ = 0;
  bool captured_ = false, accounted_ = false;
 public:
  StepTimer() : start_(Clock::now()) {
    check(state().configured && state().completed < state().limit, "step outside bounded prefix");
    pre_.reserve(96);
  }
  StepTimer(const StepTimer&) = delete;
  StepTimer& operator=(const StepTimer&) = delete;
  ~StepTimer() {
    if (!accounted_) { state().stepElapsedNs += ns(Clock::now() - start_); ++state().incompleteSteps; }
  }
  template<class DUT> void eval(DUT& d, unsigned phase) {
    auto& s = state();
    check(phase < 3 && phase == nextPhase_, "invalid eval phase sequence");
    ++s.evalAttempts;
    const auto begin = Clock::now();
    try { d.eval(); }
    catch (...) {
      const uint64_t elapsed = ns(Clock::now() - begin);
      s.evalNs += elapsed; s.phaseNs[phase] += elapsed;
      ++s.evalCalls; ++s.phaseCalls[phase];
      throw;
    }
    const uint64_t elapsed = ns(Clock::now() - begin);
    s.evalNs += elapsed; s.phaseNs[phase] += elapsed;
    ++s.evalCalls; ++s.phaseCalls[phase]; ++nextPhase_;
  }
  template<class Bus> void capture(const Bus& bus) {
    check(nextPhase_ == 1 && !captured_, "capture must follow first eval exactly once");
    captured_ = true;
    const auto& d = bus.d;
    field(pre_, "pre_reset", d.reset); field(pre_, "pre_run", bus.owner.run);
    field(pre_, "pre_running", bus.owner.running); field(pre_, "pre_pc", d.io_pc);
    field(pre_, "pre_launch_valid", d.io_launch_valid); field(pre_, "pre_launch_ready", d.io_launch_ready);
    field(pre_, "pre_completion_valid", d.io_completion_valid); field(pre_, "pre_completion_ready", d.io_completion_ready);
    field(pre_, "pre_completion_word", d.io_completion_valid ? uint64_t(d.io_completion_bits) : 0);
    field(pre_, "pre_result_valid", d.io_result_valid); field(pre_, "pre_result_ready", d.io_result_ready);
#define PROFILE_CHANNEL(CH) \
    field(pre_, "pre_" #CH "_valid", d.io_axi_##CH##_valid); \
    field(pre_, "pre_" #CH "_ready", d.io_axi_##CH##_ready)
    PROFILE_CHANNEL(ar); PROFILE_CHANNEL(aw); PROFILE_CHANNEL(w); PROFILE_CHANNEL(r); PROFILE_CHANNEL(b);
#undef PROFILE_CHANNEL
#define PROFILE_ADDRESS(CH) \
    field(pre_, "pre_" #CH "_address", d.io_axi_##CH##_valid ? uint64_t(d.io_axi_##CH##_bits_addr) : 0); \
    field(pre_, "pre_" #CH "_id", d.io_axi_##CH##_valid ? uint64_t(d.io_axi_##CH##_bits_id) : 0); \
    field(pre_, "pre_" #CH "_len", d.io_axi_##CH##_valid ? uint64_t(d.io_axi_##CH##_bits_len) : 0); \
    field(pre_, "pre_" #CH "_size", d.io_axi_##CH##_valid ? uint64_t(d.io_axi_##CH##_bits_size) : 0); \
    field(pre_, "pre_" #CH "_burst", d.io_axi_##CH##_valid ? uint64_t(d.io_axi_##CH##_bits_burst) : 0)
    PROFILE_ADDRESS(ar); PROFILE_ADDRESS(aw);
#undef PROFILE_ADDRESS
    field(pre_, "pre_w_mask", d.io_axi_w_valid ? uint64_t(d.io_axi_w_bits_strb) : 0);
    field(pre_, "pre_w_last", d.io_axi_w_valid ? uint64_t(d.io_axi_w_bits_last) : 0);
    field(pre_, "pre_w_data_fnv1a64", d.io_axi_w_valid ? dataHash(d.io_axi_w_bits_data) : 0);
    field(pre_, "pre_r_id", d.io_axi_r_valid ? uint64_t(d.io_axi_r_bits_id) : 0);
    field(pre_, "pre_r_resp", d.io_axi_r_valid ? uint64_t(d.io_axi_r_bits_resp) : 0);
    field(pre_, "pre_r_last", d.io_axi_r_valid ? uint64_t(d.io_axi_r_bits_last) : 0);
    field(pre_, "pre_r_data_fnv1a64", d.io_axi_r_valid ? dataHash(d.io_axi_r_bits_data) : 0);
    field(pre_, "pre_b_id", d.io_axi_b_valid ? uint64_t(d.io_axi_b_bits_id) : 0);
    field(pre_, "pre_b_resp", d.io_axi_b_valid ? uint64_t(d.io_axi_b_bits_resp) : 0);
    auto& s = state();
    s.activeCycles += bool(bus.owner.running); s.resetCycles += bool(d.reset);
    s.arTransfers += bool(d.io_axi_ar_valid && d.io_axi_ar_ready);
    s.awTransfers += bool(d.io_axi_aw_valid && d.io_axi_aw_ready);
    s.wTransfers += bool(d.io_axi_w_valid && d.io_axi_w_ready);
    s.rTransfers += bool(d.io_axi_r_valid && d.io_axi_r_ready);
    s.bTransfers += bool(d.io_axi_b_valid && d.io_axi_b_ready);
  }
  template<class Bus> void complete(const Bus& bus) {
    auto& s = state();
    check(nextPhase_ == 3 && captured_, "incomplete three-eval step");
    check(bus.ticks == s.completed + 1, "cycle prefix skipped or reordered");
    const auto& d = bus.d;
    field(pre_, "cycle", bus.ticks); field(pre_, "end_rng", bus.rng);
#define PROFILE_BUS(NAME, VALUE) field(pre_, NAME, uint64_t(bus.VALUE))
    PROFILE_BUS("end_read_beats", readBeats); PROFILE_BUS("end_read_acks", readAcks);
    PROFILE_BUS("end_write_beats", writeBeats); PROFILE_BUS("end_write_acks", writeAcks);
    PROFILE_BUS("end_read_bursts", readBursts); PROFILE_BUS("end_write_bursts", writeBursts);
    PROFILE_BUS("end_pending_valid", pending.valid); PROFILE_BUS("end_pending_write", pending.write);
    PROFILE_BUS("end_pending_error", pending.error); PROFILE_BUS("end_pending_address", pending.address);
    PROFILE_BUS("end_pending_id", pending.id); PROFILE_BUS("end_pending_total", pending.total);
    PROFILE_BUS("end_pending_remaining", pending.remaining); PROFILE_BUS("end_pending_delay", pending.delay);
    PROFILE_BUS("end_pending_final", pending.final); PROFILE_BUS("end_aw_valid", aw.valid);
    PROFILE_BUS("end_collected_beats", collected.size()); PROFILE_BUS("end_committing_beats", committing.size());
    PROFILE_BUS("end_ar_held", arHeld); PROFILE_BUS("end_aw_held", awHeld); PROFILE_BUS("end_w_held", wHeld);
#undef PROFILE_BUS
#define PROFILE_PORT(NAME, PORT) field(pre_, NAME, uint64_t(d.PORT))
    PROFILE_PORT("end_pc", io_pc); PROFILE_PORT("end_issued_jobs", io_issuedJobs);
    PROFILE_PORT("end_pipeline_issues", io_pipelineIssues); PROFILE_PORT("end_pipeline_stalls", io_pipelineStalls);
    PROFILE_PORT("end_idma_transfers", io_idmaTransfers); PROFILE_PORT("end_idma_read_bursts", io_idmaReadBursts);
    PROFILE_PORT("end_idma_read_beats", io_idmaReadBeats); PROFILE_PORT("end_idma_cache_hits", io_idmaCacheHits);
    PROFILE_PORT("end_idma_streamed_beats", io_idmaStreamedBeats); PROFILE_PORT("end_idma_streamed_write_beats", io_idmaStreamedWriteBeats);
    PROFILE_PORT("end_memory_accepted_0", io_memoryAccepted_0); PROFILE_PORT("end_memory_returned_0", io_memoryReturned_0);
    PROFILE_PORT("end_memory_accepted_1", io_memoryAccepted_1); PROFILE_PORT("end_memory_returned_1", io_memoryReturned_1);
    PROFILE_PORT("end_useful_macs", io_usefulMacs); PROFILE_PORT("end_executed_macs", io_executedMacs);
    PROFILE_PORT("end_write_bytes", io_writeBytes); PROFILE_PORT("end_reset_required", io_resetRequired);
    PROFILE_PORT("end_completion_valid", io_completion_valid); PROFILE_PORT("end_result_valid", io_result_valid);
#undef PROFILE_PORT
#define PROFILE_OWNER(NAME, VALUE) field(pre_, NAME, uint64_t(bus.owner.VALUE))
    PROFILE_OWNER("end_run", run); PROFILE_OWNER("end_running", running);
    PROFILE_OWNER("end_completions", completions); PROFILE_OWNER("end_successful", successful);
    PROFILE_OWNER("end_metadata_reads", metadata); PROFILE_OWNER("end_ack_bytes", ackBytes);
    PROFILE_OWNER("end_physical_bytes", physicalBytes);
    PROFILE_OWNER("end_inferred_length", inferredCommittedLength);
    PROFILE_OWNER("end_inferred_generation", inferredCommittedGeneration);
#undef PROFILE_OWNER
    openEvents();
    const std::string event = fieldsJson(pre_) + "\n";
    s.events << event; check(bool(s.events), "cannot write prefix event");
    hashBytes(s.digest, event); s.eventBytes += event.size();
    s.latest = std::move(pre_); ++s.completed;
    s.stepElapsedNs += ns(Clock::now() - start_); accounted_ = true;
    if (s.completed == s.limit) throw PrefixStop{};
    // Preserve real measured progress if the external wall-time bound expires.
    // A running report can never be mistaken for a completed diagnostic prefix.
    if (s.completed == 1 || s.completed % 64 == 0) {
      const auto before = Clock::now();
      writeReport("PREFIX_RUNNING", false);
      const uint64_t overhead = ns(Clock::now() - before);
      s.stepElapsedNs += overhead; s.reportWritesNs += overhead;
    }
  }
};
} // namespace attention_profile

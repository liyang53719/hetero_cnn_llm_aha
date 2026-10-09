// SPDX-License-Identifier: Apache-2.0
// Unit-test-only physical bus exercise. Never compile this into a production DUT.
#include "VHostBlockTop.h"  // tiny stub emitted only in the unit-test temp folder
#include "host_physical_axi.h"
#include <filesystem>
#include <iostream>
static constexpr uint64_t base = 0x100000000ULL;
struct SyntheticDut : VHostBlockTop {
  unsigned stage = 0, sent = 0, received = 0, evaluations = 0;
  bool previousClock = false, addressAccepted = false;
  void eval() {
    ++evaluations;
    const bool rising = clock && !previousClock;
    previousClock = bool(clock);
    if (rising) {
      if (stage == 0 && io_axi_ar_valid && io_axi_ar_ready) stage = 1;
      else if (stage == 1 && io_axi_r_valid && io_axi_r_ready) {
        for (unsigned i = 0; i < 16; ++i)
          host_test::require(io_axi_r_bits_data[i] == 0x1000 + received * 16 + i,
                             "synthetic actual R payload");
        ++received;
        if (io_axi_r_bits_last) { host_test::require(received == 2, "synthetic RLAST"); stage = 2; }
      } else if (stage == 2) {
        if (io_axi_aw_valid && io_axi_aw_ready) addressAccepted = true;
        if (io_axi_w_valid && io_axi_w_ready) ++sent;
        if (addressAccepted && sent == 2) stage = 3;
      } else if (stage == 3 && io_axi_b_valid && io_axi_b_ready) stage = 4;
    }
    io_launch_ready = 1;
    io_axi_ar_valid = stage == 0; io_axi_ar_bits_addr = base;
    io_axi_ar_bits_len = 1; io_axi_ar_bits_size = 6; io_axi_ar_bits_burst = 1;
    io_axi_ar_bits_id = 7; io_axi_r_ready = stage == 1;
    io_axi_aw_valid = stage == 2 && !addressAccepted;
    io_axi_aw_bits_addr = base + 128; io_axi_aw_bits_len = 1;
    io_axi_aw_bits_size = 6; io_axi_aw_bits_burst = 1; io_axi_aw_bits_id = 9;
    io_axi_w_valid = stage == 2 && sent < 2;
    io_axi_w_bits_last = sent == 1; io_axi_w_bits_strb = ~uint64_t(0);
    for (unsigned i = 0; i < 16; ++i) io_axi_w_bits_data[i] = 0x9000 + sent * 16 + i;
    io_axi_b_ready = stage == 3;
    io_pipelineIssues = received; io_pipelineStalls = stage == 1;
  }
};
struct SyntheticPolicy {
  unsigned run = 0, completions = 0, successful = 0;
  unsigned inferredCommittedLength = 0, inferredCommittedGeneration = 0;
  bool running = true;
  uint64_t metadata = 0, ackBytes = 0, physicalBytes = 0;
  unsigned actualReads = 0, actualWrites = 0, readResponses = 0, writeResponses = 0;
  host_test::PhysicalMemory& mem;
  explicit SyntheticPolicy(host_test::PhysicalMemory& memory) : mem(memory) {}
  void drive() {}
  void traffic(bool) {}
  void readCheck(const host_test::Beat& b) {
    host_test::require(b.address == base && b.total == 2, "synthetic read geometry");
    ++actualReads;
  }
  void writeCheck(const host_test::Beat& b) {
    host_test::require(b.address >= base + 128 && b.address < base + 256,
                       "synthetic write geometry");
    ++actualWrites;
  }
  void request(host_test::Beat&) {}
  void observe() {}
  void readAcknowledged(const host_test::Beat&) { ++readResponses; }
  void acknowledged(const host_test::Beat& b) {
    host_test::require(b.total == 2 && !b.error, "synthetic B response");
    for (unsigned i = 0; i < 32; ++i)
      host_test::require(mem.words[mem.index(base + 128) + i] == 0x9000 + i,
                         "physical store must be committed before ACK callback");
    ++writeResponses; ackBytes += 128; physicalBytes += 128;
  }
};
int main(int argc, char** argv) {
  if (argc != 2) return 2;
#ifdef PROFILE_SYNTHETIC_TEST
  attention_profile::configure(argv[1], 96);
#endif
  std::filesystem::create_directories(argv[1]);
  SyntheticDut d;
  host_test::PhysicalMemory mem(base, base + 256);
  for (unsigned i = 0; i < 32; ++i) mem.words[i] = 0x1000 + i;
  SyntheticPolicy policy(mem);
  host_test::PhysicalAxi<SyntheticDut, SyntheticPolicy> bus(d, policy, mem);
#ifdef PROFILE_SYNTHETIC_TEST
  bool stopped = false;
  try { for (unsigned i = 0; i < 96; ++i) bus.step(); }
  catch (const attention_profile::PrefixStop&) { stopped = true; }
  host_test::require(stopped, "synthetic expected exact stop");
  attention_profile::finish("BOUNDED_DIAGNOSTIC_PREFIX", true);
#else
  for (unsigned i = 0; i < 96; ++i) bus.step();
#endif
  host_test::require(d.stage == 4 && bus.drained() && bus.readBeats == 2 && bus.readAcks == 2
    && bus.writeBeats == 2 && bus.writeAcks == 2 && policy.actualReads == 1
    && policy.actualWrites == 2 && policy.readResponses == 2 && policy.writeResponses == 1,
    "synthetic complete physical read/write lifecycle");
  uint64_t memoryHash = 14695981039346656037ULL;
  for (uint32_t value : mem.words) for (unsigned i = 0; i < 4; ++i) {
    memoryHash ^= (value >> (8 * i)) & 255U; memoryHash *= 1099511628211ULL;
  }
  std::cout << "{\"ticks\":" << bus.ticks << ",\"rng\":" << bus.rng
    << ",\"eval_calls\":" << d.evaluations << ",\"read_beats\":" << bus.readBeats
    << ",\"read_acks\":" << bus.readAcks << ",\"write_beats\":" << bus.writeBeats
    << ",\"write_acks\":" << bus.writeAcks << ",\"read_bursts\":" << bus.readBursts
    << ",\"write_bursts\":" << bus.writeBursts << ",\"memory_fnv1a64\":" << memoryHash
    << ",\"drained\":" << bus.drained() << "}\n";
}

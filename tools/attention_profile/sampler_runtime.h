// SPDX-License-Identifier: Apache-2.0
#pragma once
// Diagnostic-only Linux x86_64 sampler. Include in the generated testbench.
// The timer first starts inside Window, after DUT construction, and measures
// only that thread's CPU time. Helper threads are never sample targets.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#if defined(__linux__) && defined(__x86_64__)
#include <link.h>
#include <dirent.h>
#include <pthread.h>
#include <signal.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>
#endif
#ifndef ATTENTION_SAMPLE_CAPACITY
#define ATTENTION_SAMPLE_CAPACITY 65536
#endif
namespace attention_sampling {
#if defined(__linux__) && defined(__x86_64__)
namespace detail {
constexpr unsigned capacity = ATTENTION_SAMPLE_CAPACITY;
constexpr unsigned intervalNs = 9973000; // About 100 Hz; kernel resolution applies.
static_assert(capacity > 0, "sample buffer must be nonempty");
static_assert(std::atomic<std::uintptr_t>::is_always_lock_free, "lock-free RIP required");
static_assert(std::atomic<unsigned>::is_always_lock_free, "lock-free counters required");
struct Sample { std::atomic<std::uintptr_t> pc{0}; std::atomic<unsigned> phase{0}; };
struct Range { std::uintptr_t begin = 0, end = 0; };
struct Module { std::string path; std::uintptr_t bias = 0; std::vector<Range> ranges; };
struct State {
  bool configured = false, enabled = false, started = false, finished = false;
  timer_t timer{}; pid_t ownerTid = 0;
  unsigned threadsAtStart = 0, threadsAtFinish = 0;
  std::string executable; std::vector<Module> modules;
  sigset_t signalSet{}, savedMask{};
  struct sigaction savedAction{};
  std::uintptr_t loadBias = 0;
  Range ranges[32]{}; unsigned rangeCount = 0;
  unsigned char buildId[64]{}; unsigned buildIdSize = 0;
  std::atomic<unsigned> activePhase{0}, used{0}, dropped{0}, outside{0}, overruns{0};
  Sample samples[capacity]{};
  uint64_t windows[4]{};
};
inline State s;
inline thread_local bool ownerThread = false;
inline void check(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
inline void saturatingAdd(std::atomic<unsigned>& v, unsigned amount = 1) {
  const unsigned n = v.load(std::memory_order_relaxed);
  v.store(amount > ~0u - n ? ~0u : n + amount, std::memory_order_relaxed);
}
// No allocation, unwinding, locking, I/O, timer APIs, or other library calls.
// Only this timer's thread-directed SI_TIMER signals can touch the buffer.
__attribute__((noinline)) inline void signalHandler(int, siginfo_t* info, void* context) {
  if (info->si_code != SI_TIMER || info->si_value.sival_ptr != &s) return;
  if (info->si_overrun > 0) saturatingAdd(s.overruns, unsigned(info->si_overrun));
  const unsigned phase = s.activePhase.load(std::memory_order_relaxed);
  if (!phase) { saturatingAdd(s.outside); return; }
  const unsigned n = s.used.load(std::memory_order_relaxed);
  if (n == capacity) { saturatingAdd(s.dropped); return; }
  const auto* uc = static_cast<const ucontext_t*>(context);
  s.samples[n].pc.store(std::uintptr_t(uc->uc_mcontext.gregs[REG_RIP]), std::memory_order_relaxed);
  s.samples[n].phase.store(phase - 1, std::memory_order_relaxed);
  s.used.store(n + 1, std::memory_order_relaxed);
}
inline int mainImage(struct dl_phdr_info* info, std::size_t, void*) {
  if (info->dlpi_name && info->dlpi_name[0]) return 0;
  s.loadBias = info->dlpi_addr;
  for (unsigned i = 0; i < info->dlpi_phnum; ++i) {
    const auto& ph = info->dlpi_phdr[i];
    if (ph.p_type == PT_LOAD && (ph.p_flags & PF_X) && s.rangeCount < 32)
      s.ranges[s.rangeCount++] = {s.loadBias + ph.p_vaddr, s.loadBias + ph.p_vaddr + ph.p_memsz};
    if (ph.p_type != PT_NOTE) continue;
    const auto* bytes = reinterpret_cast<const unsigned char*>(s.loadBias + ph.p_vaddr);
    std::size_t offset = 0;
    while (ph.p_memsz - offset >= sizeof(ElfW(Nhdr))) {
      ElfW(Nhdr) note{}; std::memcpy(&note, bytes + offset, sizeof(note));
      offset += sizeof(note);
      const std::size_t nameSize = (std::size_t(note.n_namesz) + 3) & ~std::size_t(3);
      const std::size_t descSize = (std::size_t(note.n_descsz) + 3) & ~std::size_t(3);
      if (nameSize > ph.p_memsz - offset || descSize > ph.p_memsz - offset - nameSize) break;
      if (note.n_type == NT_GNU_BUILD_ID && note.n_namesz == 4 &&
          !std::memcmp(bytes + offset, "GNU", 4) && note.n_descsz <= 64) {
        s.buildIdSize = note.n_descsz;
        std::memcpy(s.buildId, bytes + offset + nameSize, s.buildIdSize);
      }
      offset += nameSize + descSize;
    }
  }
  return 1;
}
inline int collectModules(struct dl_phdr_info* info, std::size_t, void*) {
  check(s.modules.size() < 128, "sampler too many loaded modules");
  Module module; module.path = info->dlpi_name && info->dlpi_name[0] ? info->dlpi_name : s.executable;
  module.bias = info->dlpi_addr;
  for (unsigned i = 0; i < info->dlpi_phnum; ++i) {
    const auto& ph = info->dlpi_phdr[i];
    if (ph.p_type == PT_LOAD && (ph.p_flags & PF_X))
      module.ranges.push_back({module.bias + ph.p_vaddr, module.bias + ph.p_vaddr + ph.p_memsz});
  }
  if (!module.ranges.empty()) s.modules.push_back(std::move(module));
  return 0;
}
inline unsigned threadCount() {
  DIR* d = opendir("/proc/self/task");
  check(d != nullptr, "sampler cannot count threads");
  unsigned count = 0;
  while (auto* e = readdir(d)) if (e->d_name[0] >= '0' && e->d_name[0] <= '9') ++count;
  check(closedir(d) == 0, "sampler cannot close thread directory");
  return count;
}
inline void start() {
  s.ownerTid = pid_t(syscall(SYS_gettid));
  s.threadsAtStart = threadCount();
  sigemptyset(&s.signalSet); sigaddset(&s.signalSet, SIGPROF);
  check(pthread_sigmask(SIG_BLOCK, &s.signalSet, &s.savedMask) == 0, "sampler cannot block SIGPROF");
  bool installed = false, created = false;
  try {
    check(!sigismember(&s.savedMask, SIGPROF), "sampler SIGPROF is already blocked");
    struct itimerval oldTimer{};
    check(getitimer(ITIMER_PROF, &oldTimer) == 0, "sampler cannot inspect ITIMER_PROF");
    check(!oldTimer.it_value.tv_sec && !oldTimer.it_value.tv_usec &&
          !oldTimer.it_interval.tv_sec && !oldTimer.it_interval.tv_usec,
          "sampler ITIMER_PROF already in use");
    check(sigaction(SIGPROF, nullptr, &s.savedAction) == 0, "sampler cannot inspect SIGPROF");
    check(s.savedAction.sa_handler == SIG_DFL, "sampler SIGPROF handler already in use");
    sigset_t pending{};
    check(sigpending(&pending) == 0 && !sigismember(&pending, SIGPROF), "sampler SIGPROF already pending");
    // Fault in storage and collect ELF metadata before enabling sample delivery.
    for (auto& sample : s.samples) { sample.pc.store(0); sample.phase.store(0); }
    dl_iterate_phdr(mainImage, nullptr);
    dl_iterate_phdr(collectModules, nullptr);
    check(s.rangeCount != 0, "sampler cannot find main executable ranges");
    struct sigaction action{};
    action.sa_sigaction = signalHandler; action.sa_flags = SA_SIGINFO | SA_RESTART;
    sigemptyset(&action.sa_mask);
    check(sigaction(SIGPROF, &action, nullptr) == 0, "sampler cannot install SIGPROF");
    installed = true;
    struct sigevent event{};
    event.sigev_notify = SIGEV_THREAD_ID; event.sigev_signo = SIGPROF;
    event.sigev_value.sival_ptr = &s; event._sigev_un._tid = s.ownerTid;
    check(timer_create(CLOCK_THREAD_CPUTIME_ID, &event, &s.timer) == 0,
          "sampler cannot create targeted thread CPU timer");
    created = true;
    struct itimerspec timer{};
    timer.it_interval.tv_nsec = intervalNs; timer.it_value = timer.it_interval;
    check(timer_settime(s.timer, 0, &timer, nullptr) == 0, "sampler cannot arm thread CPU timer");
    s.started = true; ownerThread = true;
  } catch (...) {
    if (created) timer_delete(s.timer);
    if (installed) sigaction(SIGPROF, &s.savedAction, nullptr);
    pthread_sigmask(SIG_SETMASK, &s.savedMask, nullptr);
    throw;
  }
  check(pthread_sigmask(SIG_SETMASK, &s.savedMask, nullptr) == 0, "sampler cannot restore signal mask");
}
inline void stop() {
  if (!s.started) return;
  check(ownerThread, "sampler finish must run on the eval thread");
  s.activePhase.store(0, std::memory_order_relaxed);
  check(pthread_sigmask(SIG_BLOCK, &s.signalSet, nullptr) == 0, "sampler cannot block stop signal");
  struct itimerspec off{};
  check(timer_settime(s.timer, 0, &off, nullptr) == 0, "sampler cannot disarm timer");
  struct timespec zero{};
  for (;;) {
    const int got = sigtimedwait(&s.signalSet, nullptr, &zero);
    if (got == SIGPROF || (got < 0 && errno == EINTR)) continue;
    check(got < 0 && errno == EAGAIN, "sampler cannot drain pending signal");
    break;
  }
  check(timer_delete(s.timer) == 0, "sampler cannot delete timer");
  check(sigaction(SIGPROF, &s.savedAction, nullptr) == 0, "sampler cannot restore SIGPROF");
  check(pthread_sigmask(SIG_SETMASK, &s.savedMask, nullptr) == 0, "sampler cannot restore final signal mask");
  s.started = false; ownerThread = false;
  s.threadsAtFinish = threadCount();
}
}
inline void configure(bool enabled) {
  auto& s = detail::s;
  detail::check(!s.configured, "sampler already configured");
  s.configured = true; s.enabled = enabled;
  s.executable = std::filesystem::canonical("/proc/self/exe").string();
}
class Window {
  bool entered_ = false;
 public:
  explicit Window(unsigned phase = 3) {
    auto& s = detail::s;
    if (!s.enabled) return;
    detail::check(!s.finished && phase < 4, "invalid sampling window");
    if (!s.started) detail::start();
    detail::check(detail::ownerThread, "sampling window moved to another thread");
    detail::check(!s.activePhase.load(std::memory_order_relaxed), "nested sampling window");
    if (s.windows[phase] != std::numeric_limits<uint64_t>::max()) ++s.windows[phase];
    entered_ = true; s.activePhase.store(phase + 1, std::memory_order_relaxed);
  }
  Window(const Window&) = delete;
  Window& operator=(const Window&) = delete;
  ~Window() { if (entered_) detail::s.activePhase.store(0, std::memory_order_relaxed); }
};
inline void finish(const std::filesystem::path& out) {
  auto& s = detail::s;
  if (s.finished) return;
  detail::check(s.configured, "sampler not configured");
  detail::stop();
  const auto path = out / "samples.json", tmp = out / "samples.json.tmp";
  detail::check(!std::filesystem::exists(path) && !std::filesystem::exists(tmp), "stale sampler output");
  std::ofstream f(tmp);
  detail::check(bool(f), "cannot open sampler output");
  f << "{\n\"schema\":\"ATTENTION_RIP_SAMPLES_V1\",\n\"local_only\":true,\n"
    << "\"enabled\":" << (s.enabled ? "true" : "false") << ",\n\"completed\":true,\n\"executable\":" << std::quoted(s.executable)
    << ",\n\"target_tid\":" << s.ownerTid
    << ",\n\"threads_at_start\":" << s.threadsAtStart << ",\n\"threads_at_finish\":" << s.threadsAtFinish << ",\n"
    << "\"clock\":\"CLOCK_THREAD_CPUTIME_ID\",\n\"signal_target\":\"SIGEV_THREAD_ID\",\n"
    << "\"scope\":\"eval caller thread self CPU; helper CPU excluded\",\n"
    << "\"interval_ns\":" << detail::intervalNs << ",\n\"capacity\":" << detail::capacity
    << ",\n\"sample_count\":" << s.used.load() << ",\n\"dropped_buffer_full\":" << s.dropped.load()
    << ",\n\"timer_overruns\":" << s.overruns.load() << ",\n\"outside_eval_events\":" << s.outside.load()
    << ",\n\"counter_max\":" << std::numeric_limits<unsigned>::max()
    << ",\n\"load_bias\":\"0x" << std::hex << s.loadBias << "\",\n\"elf_build_id\":\"";
  for (unsigned i = 0; i < s.buildIdSize; ++i) f << std::setw(2) << std::setfill('0') << unsigned(s.buildId[i]);
  f << "\",\n\"executable_ranges\":[";
  for (unsigned i = 0; i < s.rangeCount; ++i) {
    if (i) f << ',';
    f << "[\"0x" << s.ranges[i].begin << "\",\"0x" << s.ranges[i].end << "\"]";
  }
  f << "],\n\"modules\":[";
  for (unsigned i = 0; i < s.modules.size(); ++i) {
    if (i) f << ',';
    const auto& module = s.modules[i];
    f << "{\"path\":" << std::quoted(module.path) << ",\"load_bias\":\"0x" << module.bias << "\",\"executable_ranges\":[";
    for (unsigned j = 0; j < module.ranges.size(); ++j) {
      if (j) f << ',';
      f << "[\"0x" << module.ranges[j].begin << "\",\"0x" << module.ranges[j].end << "\"]";
    }
    f << "]}";
  }
  f << "],\n\"window_counts\":[" << std::dec;
  for (unsigned i = 0; i < 4; ++i) { if (i) f << ','; f << s.windows[i]; }
  f << "],\n\"samples\":[\n";
  for (unsigned i = 0; i < s.used.load(); ++i) {
    if (i) f << ",\n";
    f << "{\"pc\":\"0x" << std::hex << s.samples[i].pc.load() << "\",\"phase\":" << std::dec << s.samples[i].phase.load() << '}';
  }
  f << "\n]}\n"; f.close();
  detail::check(bool(f), "cannot write sampler output");
  std::filesystem::rename(tmp, path); s.finished = true;
}
#else
inline void configure(bool enabled) {
  if (enabled) throw std::runtime_error("sampling requires Linux x86_64");
}
class Window { public: explicit Window(unsigned = 3) {} };
inline void finish(const std::filesystem::path&) {}
#endif
}

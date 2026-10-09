# SPDX-License-Identifier: Apache-2.0
"""Bounded synthetic sampler tests; no Verilator, RTL build or model data."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sample_symbols", HERE / "sample_symbols.py")
symbolizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(symbolizer)

SOURCE = r'''
#include "sampler_runtime.h"
#include <atomic>
#include <thread>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>
__attribute__((noinline)) uint64_t hot_mix(uint64_t x, uint64_t n) {
  asm volatile("" ::: "memory");
  for (unsigned long long i = 0; i < n; ++i) { x ^= x >> 12; x ^= x << 25; x ^= x >> 27; x *= 2685821657736338717ULL; }
  return x;
}
__attribute__((noinline)) void helper_hot(std::atomic<bool>& done) {
  volatile unsigned long long x = 17;
  while (!done.load(std::memory_order_relaxed)) x = x * 6364136223846793005ULL + 1;
}
__attribute__((noinline)) uint64_t cold_mix(uint64_t x) {
  asm volatile("" ::: "memory");
  for (unsigned i = 0; i < 20000000; ++i) { x ^= x >> 9; x ^= x << 21; x *= 19; }
  return x;
}
volatile unsigned long long cold_sink;
int main(int argc, char** argv) {
  if (argc != 4) return 3;
  const bool enabled = argv[1][0] == '1';
  const unsigned long long n = std::strtoull(argv[3], nullptr, 10);
  std::atomic<bool> done{false}; std::thread helper(helper_hot, std::ref(done));
  attention_sampling::configure(enabled);
  std::thread later;
  unsigned long long value;
  { attention_sampling::Window w(1);
    later = std::thread([] { usleep(1000); });
    value = hot_mix(0x123456789abcdefULL, n);
  }
  later.join();
  cold_sink = cold_mix(987);
  std::atomic<bool> wrongThreadRejected{!enabled};
  std::thread wrong([&] {
    try { attention_sampling::Window w(2); }
    catch (const std::runtime_error&) { wrongThreadRejected.store(true); }
  }); wrong.join();
  if (!wrongThreadRejected.load()) return 4;
  attention_sampling::finish(argv[2]);
  done.store(true); helper.join();
  struct sigaction action{}; sigaction(SIGPROF, nullptr, &action);
  if (action.sa_handler != SIG_DFL) return 5;
  attention_sampling::finish(argv[2]);
  std::printf("%016llx\n", value);
}
'''


@unittest.skipUnless(shutil.which("g++") and shutil.which("nm"), "requires existing compiler/binutils")
class SamplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="attention-sample-test-")
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / "synthetic.cpp"
        cls.source.write_text(SOURCE)
        cls.binaries = {}
        for name, flags in [("pie", ["-fPIE", "-pie"]), ("exec", ["-fno-pie", "-no-pie"]),
                            ("cap", ["-fPIE", "-pie", "-DATTENTION_SAMPLE_CAPACITY=4"])]:
            binary = cls.root / name
            cp = subprocess.run(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                                 "-ffp-contract=off", "-fno-fast-math", "-pthread", "-I", str(HERE),
                                 *flags, str(cls.source), "-o", str(binary)],
                                text=True, capture_output=True, timeout=30)
            if cp.returncode:
                raise AssertionError(cp.stderr)
            cls.binaries[name] = binary
        cls.runs = {}
        for name, enabled in [("pie", False), ("pie", True), ("exec", False), ("exec", True), ("cap", True)]:
            out = cls.root / f"{name}-{int(enabled)}"; out.mkdir()
            cp = subprocess.run([str(cls.binaries[name]), str(int(enabled)), str(out), "100000000"],
                                text=True, capture_output=True, timeout=3)
            if cp.returncode:
                raise AssertionError(cp.stderr or f"probe return code {cp.returncode}")
            cls.runs[(name, enabled)] = (cp.stdout, out, json.loads((out / "samples.json").read_text()))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def summarize(self, name="pie"):
        return symbolizer.summarize(self.binaries[name], self.runs[(name, True)][1] / "samples.json", self.root)

    def test_pie_exec_results_thread_target_and_windows(self):
        for name in ("pie", "exec"):
            with self.subTest(name=name):
                off, _, off_samples = self.runs[(name, False)]
                on, _, raw = self.runs[(name, True)]
                self.assertEqual(off, on)
                self.assertFalse(off_samples["enabled"])
                self.assertTrue(off_samples["completed"])
                self.assertEqual(off_samples["sample_count"], 0)
                summary = self.summarize(name)
                self.assertGreaterEqual(summary["sample_count"], 10)
                self.assertEqual(summary["unknown_count"], 0)
                self.assertTrue(summary["sample_elf_identity_verified"])
                self.assertGreaterEqual(summary["threads_at_start"], 2)
                self.assertGreaterEqual(summary["threads_at_finish"], 2)
                self.assertGreater(summary["outside_eval_events"], 0)
                self.assertTrue(summary["functions"][0]["name"].startswith("hot_mix("))
                self.assertEqual(summary["functions"][0]["percent_of_all_samples"], 100.0)
                self.assertTrue(summary["functions"][0]["generated_sources"])
                self.assertEqual(len(summary["functions"][0]["generated_sources"][0]["sha256"]), 64)
                self.assertTrue(summary["code_windows"])
                self.assertEqual(summary["phase_sample_counts"], [0, summary["sample_count"], 0, 0])
                self.assertEqual(summary["window_counts"], [0, 1, 0, 0])
                self.assertFalse(summary["raw_instruction_addresses_included"])
                for forbidden in ('"pc"', '"load_bias"', '"executable_ranges"', '"executable"'):
                    self.assertNotIn(forbidden, json.dumps(summary))
                if name == "pie": self.assertNotEqual(int(raw["load_bias"], 16), 0)
                else: self.assertEqual(int(raw["load_bias"], 16), 0)

    def test_capacity_drops_and_is_reported(self):
        summary = self.summarize("cap")
        self.assertEqual(summary["sample_count"], 4)
        self.assertGreater(summary["dropped_buffer_full"], 0)
        self.assertTrue(summary["buffer_saturated"])
        self.assertEqual(self.runs[("cap", True)][0], self.runs[("pie", False)][0])

    def test_bad_receipts_rejected(self):
        raw = self.runs[("pie", True)][2]
        changesets = [{"enabled": False}, {"completed": False}, {"elf_build_id": "0" * 40},
                     {"executable": str(self.binaries["exec"])}, {"target_tid": 0},
                     {"sample_count": raw["sample_count"] + 1}]
        for i, changes in enumerate(changesets):
            with self.subTest(changes=changes):
                path = self.root / f"bad-{i}.json"
                path.write_text(json.dumps(dict(raw, **changes)))
                with self.assertRaises(ValueError):
                    symbolizer.summarize(self.binaries["pie"], path, self.root)

    def test_hash_change_during_analysis_rejected(self):
        real = symbolizer.sha256
        calls = 0
        def changing(path):
            nonlocal calls
            if Path(path).resolve() != self.binaries["pie"].resolve():
                return real(path)
            calls += 1
            return real(path) if calls == 1 else "0" * 64
        with mock.patch.object(symbolizer, "sha256", side_effect=changing), self.assertRaises(ValueError):
            self.summarize()

    def test_dso_symbol_and_unknown_module_accounting(self):
        raw = self.runs[("pie", True)][2]
        libc = next(m for m in raw["modules"] if Path(m["path"]).name.startswith("libc.so"))
        symbols = symbolizer.sized_symbols(Path(libc["path"]), shutil.which("nm"), dynamic=True)
        address = next(a for a, item in symbols.items() if any(n.split("@")[0] == "getpid" for n in item["names"]))
        receipt = dict(raw, sample_count=1, samples=[{"pc": hex(int(libc["load_bias"], 16) + address), "phase": 0}])
        path = self.root / "synthetic-dso-receipt.json"
        path.write_text(json.dumps(receipt))
        summary = symbolizer.summarize(self.binaries["pie"], path, self.root)
        self.assertEqual(summary["unknown_count"], 0)
        self.assertTrue(any(n.split("@")[0] == "getpid" for n in [summary["functions"][0]["name"], *summary["functions"][0]["aliases"]]))
        self.assertTrue(summary["functions"][0]["module"].startswith("libc.so"))
        self.assertFalse(summary["functions"][0]["is_main_executable"])
        # Deliberately create an unresolved address inside this real module's
        # executable segment; this is parser coverage, not a measured hotspot.
        receipt["samples"][0]["pc"] = libc["executable_ranges"][0][0]
        path.write_text(json.dumps(receipt))
        summary = symbolizer.summarize(self.binaries["pie"], path, self.root)
        self.assertEqual(summary["unknown_count"], 1)
        self.assertEqual(summary["unknown_percent"], 100.0)
        self.assertEqual(next(m for m in summary["modules"] if m["module"].startswith("libc.so"))["unknown_samples"], 1)

    def test_handler_compiles_without_calls(self):
        binary = self.binaries["pie"]
        rows = subprocess.check_output(["nm", "-n", "-S", str(binary)], text=True)
        row = next(line.split() for line in rows.splitlines() if "signalHandler" in line)
        begin = int(row[0], 16); end = begin + int(row[1], 16)
        assembly = subprocess.check_output(["objdump", "-d", f"--start-address={begin}",
                                           f"--stop-address={end}", str(binary)], text=True)
        self.assertNotIn("\tcall", assembly)
        self.assertNotIn("\tsyscall", assembly)

if __name__ == "__main__":
    unittest.main()

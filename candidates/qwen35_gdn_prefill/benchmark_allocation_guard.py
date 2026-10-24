"""Reproduce host-only allocation-predicate timing, without importing the model.

Run: python candidates/qwen35_gdn_prefill/benchmark_allocation_guard.py
Prints JSON to stdout. Linux, one CPU, 30 seconds, 256 MiB address space.
The original predicate is reconstructed, not the complete historical source.
"""
import ast
import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import statistics
import time
import tracemalloc

SOURCE_SHA256 = 'e6e5a7c2b45e05f8081bb8d825a1832a0d8038bec7f301ade2c596f236b412c2'
OLD = 'set(self.memory.regions) == set(self.allocations)'
NEW = '''(self.memory.regions.keys() == self.allocations.keys()
                 if type(self.memory.regions) is dict and type(self.allocations) is dict
                 else set(self.memory.regions) == set(self.allocations))'''


def require(ok, message):
    if not ok:
        raise ValueError(message)


def timeout(signum, frame):
    raise TimeoutError('30-second metadata microbenchmark limit')


def main():
    start = time.monotonic()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024**2, 4 * 1024**2))
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, 30)

    # This local helper imports only stdlib and extracts guard AST, not a model.
    from test_allocation_guard_cold import extract, fixture
    source = Path(__file__).with_name('full_driver.py').read_bytes()
    require(hashlib.sha256(source).hexdigest() == SOURCE_SHA256, 'source hash drift')
    candidate = source.decode('utf-8')
    require(candidate.count(NEW) == 1, 'expected exactly one reviewed predicate')
    reconstructed = candidate.replace(NEW, OLD)
    _, original = extract(reconstructed)
    _, changed = extract(candidate)
    benchmarks = []
    for count in (1, 16, 57, 128, 512):
        metadata = fixture(count)
        samples = {'original': [], 'candidate': []}
        functions = [('original', original), ('candidate', changed)]
        for repeat in range(9):
            order = functions if repeat % 2 == 0 else list(reversed(functions))
            for name, function in order:
                for _ in range(100):
                    require(function(metadata), 'unexpected predicate failure')
                begin = time.perf_counter_ns()
                for _ in range(10000):
                    function(metadata)
                samples[name].append((time.perf_counter_ns() - begin) / 10000)
        peaks = {}
        for name, function in functions:
            gc.collect()
            tracemalloc.start()
            tracemalloc.reset_peak()
            before = tracemalloc.get_traced_memory()[0]
            for _ in range(100):
                require(function(metadata), 'unexpected predicate failure')
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks[name] = {'peak_extra_traced_bytes': peak - before,
                           'retained_extra_traced_bytes': current - before}
        medians = {name: statistics.median(values) for name, values in samples.items()}
        benchmarks.append({'regions': count, 'calls_per_repeat': 10000, 'repeats': 9,
                           'ns_per_call_samples': samples, 'median_ns_per_call': medians,
                           'speed_ratio': medians['original'] / medians['candidate'],
                           'tracemalloc': peaks})
    result = {'status': 'PASS_HOST_METADATA_MICROBENCH_ONLY',
              'source_sha256': SOURCE_SHA256,
              'original_predicate': OLD, 'candidate_predicate': NEW,
              'original_predicate_ast_sha256': hashlib.sha256(
                  ast.dump(ast.parse(OLD, mode='eval')).encode()).hexdigest(),
              'candidate_predicate_ast_sha256': hashlib.sha256(
                  ast.dump(ast.parse(NEW, mode='eval')).encode()).hexdigest(),
              'baseline_scope': 'Exact old predicate only; not historical full source',
              'measurement_scope': 'Allocation require condition: key comparison plus identity scan',
              'benchmark': benchmarks, 'cpu_affinity': sorted(os.sched_getaffinity(0)),
              'wall_seconds': time.monotonic() - start,
              'maxrss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'fullmodel_requalified': False, 'native_called': False,
              'hardware_performance_claim': False}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

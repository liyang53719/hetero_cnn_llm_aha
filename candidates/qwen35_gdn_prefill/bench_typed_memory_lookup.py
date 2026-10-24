"""Bounded 57-region synthetic lookup benchmark, never model arithmetic.

Run with python -m candidates.qwen35_gdn_prefill.bench_typed_memory_lookup.
The baseline is the preserved b74aa569 resolver in the memory-only test module.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import time

from . import typed_dense as t
from .test_typed_memory_lookup import LegacyTypedMemory


def make_memory(kind):
    memory = kind()
    spans = [(0x1000 + i * 512, (1 + i % 4) * 64) for i in range(57)]
    random.Random(913).shuffle(spans)
    for base, extent in spans:
        memory.add_readonly(base, bytes([base // 512 % 256]) * extent)
    return memory, spans


def measure(memory, queries, operation):
    resolve, read = memory._resolve, memory.read64
    checksum = 0
    started = time.perf_counter_ns()
    if operation == 'resolve':
        for address in queries:
            checksum ^= resolve(address).base
    else:
        for address in queries:
            checksum ^= read(address)[0]
    elapsed = time.perf_counter_ns() - started
    return elapsed / len(queries), checksum


def run(iterations=20000, samples=5):
    if not (100 <= iterations <= 50000 and 3 <= samples <= 9):
        raise ValueError('bounded benchmark: 100..50000 iterations, 3..9 samples')
    memories = {}
    for name, kind in (('baseline', LegacyTypedMemory), ('hoist', t.TypedMemory)):
        memories[name], spans = make_memory(kind)
    addresses = [base + offset for base, extent in spans for offset in range(0, extent, 64)]
    random.Random(57).shuffle(addresses)
    queries = [addresses[i % len(addresses)] for i in range(iterations)]
    digests = {name: hashlib.sha256(b''.join(memory.read64(address) for address in addresses)).hexdigest()
               for name, memory in memories.items()}
    if len(set(digests.values())) != 1:
        raise AssertionError('baseline/candidate bytes differ')
    results = {}
    for operation in ('resolve', 'read64'):
        timings = {name: [] for name in memories}
        for memory in memories.values():
            measure(memory, queries[:1000], operation)
        checksums = set()
        for sample in range(samples):
            order = ('baseline', 'hoist') if sample % 2 == 0 else ('hoist', 'baseline')
            for name in order:
                elapsed, checksum = measure(memories[name], queries, operation)
                timings[name].append(elapsed)
                checksums.add(checksum)
        if len(checksums) != 1:
            raise AssertionError('baseline/candidate checksum differs')
        medians = {name: statistics.median(values) for name, values in timings.items()}
        results[operation] = dict(ns_per_call_samples=timings, median_ns_per_call=medians,
                                  reduction_percent=100 * (1 - medians['hoist'] / medians['baseline']),
                                  checksum=checksums.pop())
    return dict(status='MEASURED_MEMORY_LOOKUP_ONLY', baseline_commit='b74aa569e2576b4b363006acab5529f536e63749',
                python=platform.python_version(), regions=57, iterations_per_sample=iterations,
                samples=samples, distinct_addresses=len(addresses), byte_sha256=digests,
                typed_dense_sha256=hashlib.sha256(Path(t.__file__).read_bytes()).hexdigest(),
                results=results, actual_model_executed=False, native_arithmetic_executed=False,
                rtl_executed=False, full_m128_status='TEMP_NOT_RUN',
                caveat='Synthetic wall-time microbenchmark only; no end-to-end speedup or hardware-cycle claim.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=20000)
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(run(args.iterations, args.samples), indent=2, sort_keys=True) + '\n'
    if args.output is not None:
        args.output.write_text(result)
    print(result, end='')

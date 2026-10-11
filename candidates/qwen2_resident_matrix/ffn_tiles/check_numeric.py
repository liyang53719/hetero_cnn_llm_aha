#!/usr/bin/env python3
"""Bounded actual-producer tiles through the shared A-bank host control model.

Only accepted bank-read gate/up payloads reach the source-tied host SiLU. Its
computed output is written to slot2 and collected after accepted bank reads.
Saved activation and independently indexed flat arithmetic are comparison-only
and become accessible only after all actual output responses are collected.
No Chisel/HardFloat/RTL execution, DMA ACK, full FFN, or native acceptance claim.
"""
from array import array
import argparse
from collections import Counter
import ctypes as C
from dataclasses import asdict, is_dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
SENTINEL = int.from_bytes(bytes.fromhex("5aa569963cc3f00f") * 4, "little")
PHASES = ("exp", "add", "div", "sign_mul", "gate_mul", "up_mul")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def wire_bytes(words):
    return struct.pack("<" + "I" * len(words), *words)


def checked_file(spec):
    data = (ROOT / spec["path"]).read_bytes()
    if len(data) != spec["bytes"] or sha(data) != spec["sha256"]:
        raise ValueError("frozen file identity drift: " + spec["path"])
    return data


def load_pins(check_provenance=True):
    """Always verify arithmetic sources; actual runs also require local receipts.

    check_provenance=False is only for small source/recipe unit tests in clean
    checkouts. The actual numerical runner deliberately uses the strict default.
    """
    pins = json.loads((TASK / "precision_pins.json").read_text())
    for category in ("sources", "provenance") if check_provenance else ("sources",):
        for name, digest in pins[category].items():
            if sha((ROOT / name).read_bytes()) != digest:
                raise ValueError("frozen source identity drift: " + name)
    source = (ROOT / "chisel/continuous_prefill/tests/qwen2_block.cpp").read_text()
    cpp = (TASK / "silu_recipe.cpp").read_text()
    for name in ("bits", "fp", "add", "mul"):
        line = next(line for line in source.splitlines() if line.startswith("static ") and " " + name + "(" in line)
        if line not in cpp:
            raise ValueError("original recipe helper changed: " + name)
    exp = source[source.index("static float expneg("):source.index("\nstruct Stage")]
    if exp not in cpp:
        raise ValueError("original exp recipe changed")
    if "sig=mul(sig,std::signbit(g)?e:1.0f)" not in cpp or "mul(mul(sig,g),u)" not in cpp:
        raise ValueError("original SiLU operation order changed")
    return pins


def verify_capture_sources(report, source_names):
    """Record post-capture identities and reject any source change."""
    report["source_sha256_after"] = {name: sha((TASK / name).read_bytes()) for name in source_names}
    report["source_changed_since_freeze"] = [name for name in source_names if report["source_sha256_after"][name] != report["source_sha256"][name]]
    if report["source_changed_since_freeze"]:
        raise ValueError("source changed during frozen numerical capture")


def build_library(out, pins, source_path=None):
    path = out / "silu_recipe.so"
    argv = ["g++", *pins["recipe"]["compiler_flags"], str(source_path or TASK / "silu_recipe.cpp"), "-o", str(path)]
    start = time.monotonic()
    with (out / "compile.log").open("w") as log:
        subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    library = C.CDLL(str(path))
    pointer = C.POINTER(C.c_uint32)
    library.sf_vector.argtypes = [pointer] * 6
    library.sf_vector.restype = C.c_int
    library.sf_reference.argtypes = [pointer, pointer, pointer, C.c_uint]
    library.sf_reference.restype = C.c_int
    if library.sf_reset() != 0:
        raise ValueError("host IEEE FP32/RNE/gradual-subnormal environment unsupported")
    return library, {"argv": argv, "binary_sha256": sha(path.read_bytes()),
                     "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
                     "wall_seconds": time.monotonic() - start}


def load_model(source_text=None):
    spec = importlib.util.spec_from_file_location("ffn_numeric_tile_model", TASK / "model.py")
    model = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = model
    # Compile exactly the bytes frozen before arithmetic. Preserve __file__ so
    # the model still resolves and validates its frozen physical-bank import.
    exec(compile(source_text if source_text is not None else (TASK / "model.py").read_text(),
                 str(TASK / "model.py"), "exec"), model.__dict__)
    return model


def flat_tile(raw, rows, cols, ng):
    return tuple(raw[m * 8960 + ng + n] for m in range(rows) for n in range(cols))


def beat_from_flat(flat, index, cols):
    row_group, n = divmod(index, cols)
    return tuple(flat[(row_group * 16 + lane) * cols + n] for lane in range(16))


def bank_region_hash(words, first, end):
    h = hashlib.sha256()
    for bank in words:
        for word in bank[first:end]:
            h.update(word.to_bytes(32, "little"))
    return h.hexdigest()


def preload_retained(bank_words, raw_n1):
    """Preexisting retained BF16 state; no test output is installed here."""
    for bank in bank_words:
        bank[:] = [SENTINEL] * 1376
    for m in range(128):
        for k in range(1536):
            x = raw_n1[m * 1536 + k]
            if x & 0x7f800000 == 0x7f800000:
                raise ValueError("retained n1 contains a nonfinite value")
            bf16 = ((x + 0x7fff + ((x >> 16) & 1)) >> 16) & 0xffff
            bank, word, shift = (k & 15) ^ (m // 16), (k // 16) * 8 + m // 16, 16 * (m % 16)
            bank_words[bank][word] = (bank_words[bank][word] & ~(0xffff << shift)) | (bf16 << shift)


def jsonable(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (str, int, float, bool, list, tuple, dict)) or value is None:
        return value
    raise TypeError("unrecordable model event: " + type(value).__name__)


class BankDriver:
    """Serial source-side driver; artificial stalls exercise response holding."""
    def __init__(self, module, bank, case, trace_file, deadline):
        self.module, self.bank, self.case = module, bank, case
        self.trace_file, self.deadline = trace_file, deadline
        self.trace = hashlib.sha256()
        self.counts = Counter()
        self.expected = [list(words) for words in bank.banks.words]

    def tick(self, **kwargs):
        if time.monotonic() > self.deadline:
            raise TimeoutError("bounded tile model budget exceeded")
        event = self.bank.tick(**kwargs)
        self.counts["ticks"] += 1
        for key in ("ctl_fire", "write_fire", "read_fire", "response_fire"):
            self.counts[key] += bool(event.get(key))
        expected_reads = 16 if event["read_fire"] or event["write_fire"] else 0
        expected_writes = 16 if event["rmw_commit"] else 0
        if len(event["reads"]) != expected_reads or len(event["writes"]) != expected_writes:
            raise ValueError("unexpected physical read/write port event count")
        for accesses in (event["reads"], event["writes"]):
            if any(not 0 <= bank < 16 or not 768 <= word < 1248 for bank, word in accesses.items()):
                raise ValueError("tile port escaped its physical bank region")
        self.counts["physical_bank_word_reads"] += len(event["reads"])
        self.counts["physical_bank_word_writes"] += len(event["writes"])
        encoded = (json.dumps({"tick": self.counts["ticks"], "inputs": kwargs, "events": event},
                              default=jsonable, sort_keys=True, separators=(",", ":")) + "\n").encode()
        self.trace_file.write(encoded)
        self.trace.update(encoded)
        if self.bank.poison:
            raise ValueError("tile model poisoned: " + str(event))
        return event

    def control(self, op, slot):
        c = self.case
        request = self.module.Control(op, slot, c["identity"], c["ng"], c["rows"], c["cols"])
        for _ in range(8):
            if self.tick(control=request)["ctl_fire"]:
                return
        raise ValueError("control request failed to fire")

    def write(self, slot, index, words):
        c = self.case
        request = self.module.Write(slot, c["identity"], c["ng"], index, tuple(words))
        for _ in range(8):
            if self.tick(write=request)["write_fire"]:
                break
        else:
            raise ValueError("bank write failed to fire")
        # The model performs the accepted read/modify/write on the next edge.
        self.tick()
        row_group, n = divmod(index, c["cols"])
        word, shift = 768 + 160 * slot + 20 * row_group + n // 8, 32 * (n % 8)
        for lane, value in enumerate(words):
            self.expected[lane][word] = (self.expected[lane][word] & ~(0xffffffff << shift)) | (value << shift)

    def read(self, slot, index):
        c = self.case
        request = self.module.Read(slot, c["identity"], c["ng"], index)
        for _ in range(8):
            if self.tick(read=request, response_ready=False)["read_fire"]:
                break
        else:
            raise ValueError("bank read failed to fire")
        held = None
        # Force synchronous-read latency plus two consumer backpressure edges.
        for _ in range(3):
            event = self.tick(response_ready=False)
            if event.get("response") is not None:
                if held is not None and held != event["response"]:
                    raise ValueError("held bank response changed under stall")
                held = event["response"]
        for _ in range(8):
            event = self.tick()
            if event["response_fire"]:
                response = event["response"]
                if (response.slot, response.identity, response.ng, response.index, response.error) != (
                        slot, c["identity"], c["ng"], index, False):
                    raise ValueError("accepted read identity/order/error mismatch")
                if held is not None and held != response:
                    raise ValueError("accepted bank response differs from held response")
                return tuple(response.words)
        raise ValueError("bank read response failed to fire")

    def check_storage(self):
        for bank, (actual, expected) in enumerate(zip(self.bank.banks.words, self.expected)):
            for word, (a, b) in enumerate(zip(actual, expected)):
                if a != b:
                    raise ValueError(f"shared bank corruption bank={bank} word={word}")


def execute_case(module, library, inputs, case, out, deadline):
    rows, cols, ng = case["rows"], case["cols"], case["ng"]
    if rows not in (16, 128) or cols not in (32, 64, 96, 128, 160) or ng % 32 or ng + cols > 8960:
        raise ValueError("unsupported bounded source tile")
    case_dir = out / f"m{rows}_n{cols}_ng{ng}"
    case_dir.mkdir()
    bank = module.TileBankModel()
    preload_retained(bank.banks.words, inputs["retained_n1"])
    retained_before = bank_region_hash(bank.banks.words, 0, 768)
    spare_before = bank_region_hash(bank.banks.words, 1248, 1376)
    gate = flat_tile(inputs["gate"], rows, cols, ng)
    up = flat_tile(inputs["up"], rows, cols, ng)
    beats = rows // 16 * cols
    operands = [(C.c_uint32 * 16)() for _ in range(3)]
    values, flags, errors = (C.c_uint32 * 96)(), (C.c_uint32 * 96)(), (C.c_uint32 * 16)()
    operation_hashes = {phase: hashlib.sha256() for phase in PHASES}
    flags_counts = {phase: Counter() for phase in PHASES}
    source_hashes = {name: hashlib.sha256() for name in ("gate", "up", "computed", "bank_accepted_output")}
    actual = [None] * (rows * cols)
    wall_start, cpu_start = time.monotonic(), time.process_time()
    registers = Counter()
    with (case_dir / "bank_events.jsonl").open("wb") as trace, (case_dir / "host_sfu_events.jsonl").open("w") as sftrace:
        driver = BankDriver(module, bank, case, trace, deadline)
        for slot in range(3):
            driver.control(0, slot)
        for slot, source in enumerate((gate, up)):
            for index in range(beats):
                driver.write(slot, index, beat_from_flat(source, index, cols))
            driver.control(1, slot)
        driver.check_storage()
        for index in range(beats):
            g = driver.read(0, index)
            u = driver.read(1, index)
            registers["gate_register_loads"] += 1
            registers["up_register_loads"] += 1
            source_hashes["gate"].update(wire_bytes(g))
            source_hashes["up"].update(wire_bytes(u))
            operands[0][:], operands[1][:] = g, u
            status = library.sf_vector(operands[0], operands[1], operands[2], values, flags, errors)
            registers["host_sfu_requests"] += 1
            record = {"index": index, "status": status, "lane_errors": list(errors),
                      "phase_flags": list(flags), "phase_values": list(values)}
            sftrace.write(json.dumps(record, separators=(",", ":")) + "\n")
            for phase, name in enumerate(PHASES):
                operation_hashes[name].update(wire_bytes(values[phase * 16:(phase + 1) * 16]))
                flags_counts[name].update(flags[phase * 16:(phase + 1) * 16])
            if status:
                raise ValueError(f"original numerical policy rejected host SiLU beat {index}: status={status}, errors={list(errors)}")
            result = tuple(operands[2])
            source_hashes["computed"].update(wire_bytes(result))
            registers["output_register_loads"] += 1
            driver.write(2, index, result)
        driver.control(1, 2)
        driver.check_storage()
        for index in range(beats):
            words = driver.read(2, index)
            source_hashes["bank_accepted_output"].update(wire_bytes(words))
            row_group, n = divmod(index, cols)
            for lane, word in enumerate(words):
                coordinate = (row_group * 16 + lane) * cols + n
                if actual[coordinate] is not None:
                    raise ValueError("duplicate acknowledged output coordinate")
                actual[coordinate] = word
        for slot in range(3):
            driver.control(2, slot)
        driver.check_storage()
    if any(word is None for word in actual):
        raise ValueError("incomplete acknowledged output")
    retained_after = bank_region_hash(bank.banks.words, 0, 768)
    spare_after = bank_region_hash(bank.banks.words, 1248, 1376)
    if (retained_after, spare_after) != (retained_before, spare_before):
        raise ValueError("retained input or spare sentinel changed")
    if source_hashes["computed"].digest() != source_hashes["bank_accepted_output"].digest():
        raise ValueError("computed/accepted output order differs")
    if source_hashes["gate"].hexdigest() != sha(b"".join(wire_bytes(beat_from_flat(gate, i, cols)) for i in range(beats))):
        raise ValueError("accepted bank gate inputs differ from producer bytes")
    if source_hashes["up"].hexdigest() != sha(b"".join(wire_bytes(beat_from_flat(up, i, cols)) for i in range(beats))):
        raise ValueError("accepted bank up inputs differ from producer bytes")
    expected_counters = {"read_requests": 3 * beats, "write_requests": 3 * beats,
                         "read_responses": 3 * beats, "rmw_commits": 3 * beats,
                         "logical_read_bytes": 3 * beats * 64, "logical_write_bytes": 3 * beats * 64,
                         "physical_read_bytes": 6 * beats * 512, "physical_write_bytes": 3 * beats * 512}
    if any(bank.counters[name] != count for name, count in expected_counters.items()):
        raise ValueError("actual port counters differ from exact tile access equations")
    if (driver.counts["physical_bank_word_reads"] * 32 != bank.counters["physical_read_bytes"] or
            driver.counts["physical_bank_word_writes"] * 32 != bank.counters["physical_write_bytes"]):
        raise ValueError("physical bank byte counters differ from actual port events")
    if bank.leased or not bank.idle or any(t.produced != beats or t.consumed != beats for t in bank.tags):
        raise ValueError("tile completed before every producer and consumer drained")
    # First persist actual response-accepted bytes. No expected activation or
    # flat reference calculation has been read or computed along this path.
    (case_dir / "bank_response_accepted_act.f32le").write_bytes(wire_bytes(actual))
    return {
        "case": case, "case_dir": str(case_dir.relative_to(out)), "output": tuple(actual),
        "gate": gate, "up": up, "values": rows * cols, "beats": beats,
        "bank_events": dict(driver.counts), "bank_counters": dict(bank.counters),
        "bank_event_sha256": driver.trace.hexdigest(), "host_register_events": dict(registers),
        "source_order_sha256": {name: h.hexdigest() for name, h in source_hashes.items()},
        "phase_value_sha256": {name: h.hexdigest() for name, h in operation_hashes.items()},
        "host_phase_exception_flags": {name: dict(counts) for name, counts in flags_counts.items()},
        "retained_input_sha256_before": retained_before, "retained_input_sha256_after": retained_after,
        "spare_sentinel_sha256_before": spare_before, "spare_sentinel_sha256_after": spare_after,
        "all_unwritten_bank_bits_preserved": True,
        "host_wall_seconds": time.monotonic() - wall_start,
        "host_process_cpu_seconds": time.process_time() - cpu_start,
        "protocol_model_ticks_are_hardware_cycles": False, "predicted_hardware_cycles": None,
        "ack_definition": "Accepted tile-bank read response; not an iDMA/AXI write response",
        "physical_traffic_definition": "A-bank port bytes only: reads=8*(logical reads+logical writes) including RMW; writes=8*logical writes. No DMA traffic claimed.",
    }


def run(out, only_rows=None):
    if out.exists():
        raise ValueError("use a new evidence directory")
    out.mkdir(parents=True)
    start, cpu_start = time.monotonic(), time.process_time()
    pins = load_pins()
    cases = [case for case in pins["default_cases"] if only_rows is None or case["rows"] == only_rows]
    source_bytes = {name: (TASK / name).read_bytes() for name in ("silu_recipe.cpp", "model.py", "check_numeric.py", "precision_pins.json")}
    report = {"status": "PREPARED_NOT_EXECUTED", "scope": pins["scope"], "acceptance": pins["acceptance"],
              "precision_pins_sha256": sha((TASK / "precision_pins.json").read_bytes()),
              "budget": {"wall_seconds": 60, "single_process": True, "estimated_memory_mib": 96,
                         "actual_path_fp32_values": sum(c["rows"] * c["cols"] for c in cases),
                         "independent_reference_fp32_values": sum(c["rows"] * c["cols"] for c in cases),
                         "sram_bytes": 16 * (1376 + 160) * 32,
                         "a_model_bytes": 16 * 1376 * 32,
                         "b_bank_payload_accesses": 0,
                         "b_banks_not_instantiated_by_tile_model": True,
                         "full_ffn_or_block_runs": 0, "rtl_or_eda_runs": 0},
              "source_sha256": {name: sha(data) for name, data in source_bytes.items()},
              "cases": []}

    def save():
        (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")

    # Immutable input specification and candidate bytes recorded before the
    # first compiler invocation or actual numerical operation.
    frozen_dir = out / "frozen_sources"
    frozen_dir.mkdir()
    for name, data in source_bytes.items():
        (frozen_dir / name).write_bytes(data)
    (out / "FROZEN_PINS.json").write_text(json.dumps({"pins": pins, "run": report}, indent=2) + "\n")
    save()
    try:
        if sys.byteorder != "little":
            raise ValueError("explicit little-endian host required")
        inputs = {}
        for name, spec in pins["inputs"].items():
            inputs[name] = array("I")
            inputs[name].frombytes(checked_file(spec))
        library, report["compile"] = build_library(out, pins, frozen_dir / "silu_recipe.cpp")
        model = load_model(source_bytes["model.py"].decode())
        completed = []
        for case in cases:
            completed.append(execute_case(model, library, inputs, case, out, start + 60))
        # Saved reference activation bytes are unavailable to the actual path.
        saved_act = array("I")
        saved_act.frombytes(checked_file(pins["comparison_only"]["act"]))
        for case_report in completed:
            output, gate, up = [case_report.pop(key) for key in ("output", "gate", "up")]
            count = len(output)
            cg, cu, ref = (C.c_uint32 * count)(*gate), (C.c_uint32 * count)(*up), (C.c_uint32 * count)()
            if library.sf_reference(cg, cu, ref, count):
                raise ValueError("independent flat reference nonfinite/domain failure")
            c = case_report["case"]
            expected = flat_tile(saved_act, c["rows"], c["cols"], c["ng"])
            flat_mismatch = sum(a != b for a, b in zip(output, ref))
            saved_mismatch = sum(a != b for a, b in zip(output, expected))
            path = out / case_report["case_dir"]
            (path / "comparison_flat_act.f32le").write_bytes(bytes(ref))
            (path / "comparison_saved_act.f32le").write_bytes(wire_bytes(expected))
            case_report.update(independent_flat_bit_mismatches=flat_mismatch, saved_act_bit_mismatches=saved_mismatch,
                               output_sha256=sha(wire_bytes(output)),
                               artifact_sha256={p.name: sha(p.read_bytes()) for p in path.iterdir() if p.is_file()})
            report["cases"].append(case_report)
            if flat_mismatch or saved_mismatch:
                raise ValueError("actual tile numerical comparison failed")
        report.update(status="PASS_BOUNDED_ACTUAL_TILES_HOST_MODEL_ONLY", wall_seconds=time.monotonic() - start,
                      host_process_cpu_seconds=time.process_time() - cpu_start,
                      host_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      compiler_child_cpu_seconds=resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime + resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime)
        verify_capture_sources(report, source_bytes)
        save()
        return report
    except Exception as error:
        report.update(status="FAILED", error=str(error), wall_seconds=time.monotonic() - start)
        save()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only-rows", type=int, choices=(16, 128))
    args = parser.parse_args()
    result = run(args.out.resolve(), args.only_rows)
    print(json.dumps({"status": result["status"], "cases": len(result["cases"]), "wall_seconds": result["wall_seconds"]}))

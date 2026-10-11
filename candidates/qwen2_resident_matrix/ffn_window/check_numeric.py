#!/usr/bin/env python3
"""Actual raw n1 -> Dense Gate -> retained-A Up -> tile SiLU host evidence.

Only n1 and real weights initialize the execution. Accepted physical Matrix
packets drive the unchanged sequential-K FP32 FMA; its results are committed
through the window owner's tile ports. Actual accepted Gate/Up tile reads
drive the unchanged SiLU recipe and actual Act tile writes/reads. Saved output
and independent direct-dot references are inaccessible until execution ends.
No native Matrix, HardFloat, RTL, full projection/FFN/block or timing claim.
"""
import argparse
from array import array
from collections import Counter, deque
import ctypes as C
from dataclasses import asdict
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
K, SOURCE_N = 1536, 8960
SOURCE_BASES = {"n1": 0x1000000, "gate_weight": 0x2000000, "up_weight": 0x4000000}
DESTINATION_BASES = {"gate": 0x8000000, "up": 0x9000000}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def descriptor_record(command):
    # Internal DMA tag carries the UInt32 job tag plus UInt32 sequence.
    return struct.pack("<cQIQ", command.kind.encode(), command.address, command.beats, command.tag)


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def checked_file(spec):
    raw = (ROOT / spec["path"]).read_bytes()
    require(len(raw) == spec["bytes"] and sha(raw) == spec["sha256"],
            "frozen input identity drift: " + spec["path"])
    return raw


def load_pins(check_provenance=True):
    """Recipe tests may omit local work receipts; actual runs use strict default."""
    pins = json.loads((TASK / "precision_pins.json").read_text())
    for category in ("sources", "provenance") if check_provenance else ("sources",):
        for path, digest in pins[category].items():
            require(file_sha(ROOT / path) == digest, "frozen source identity drift: " + path)
    source = (ROOT / "chisel/continuous_prefill/tests/qwen2_block.cpp").read_text()
    matrix = (TASK.parent / "transposed_down/numeric_smoke.cpp").read_text()
    for name in ("bits", "fp", "bf"):
        helper = next(line for line in source.splitlines() if line.startswith("static ") and " " + name + "(" in line)
        require(helper in matrix, "original Matrix recipe helper changed: " + name)
    require('#include "../transposed_down/numeric_smoke.cpp"' in (TASK / "numeric_recipe.cpp").read_text(),
            "physical Matrix recipe must be reused unchanged")
    require("dense(OFF_N1,OFF_WG,OFF_GATE,H,F)" in source and "dense(OFF_N1,OFF_WU,OFF_UP,H,F)" in source,
            "original Gate/Up input/call changed")
    return pins


def verify_provenance(pins):
    manifest = json.loads((ROOT / "work/qwen2_layer0_payload_20261011/manifest.json").read_text())
    require((manifest["model_id"], manifest["revision"], manifest["layer_id"]) ==
            (pins["model"], pins["revision"], pins["layer"]), "model origin drift")
    for role in ("gate", "up"):
        entries = [t for t in manifest["tensors"] if t["local_name"] == "mlp." + role + "_proj.weight"]
        require(len(entries) == 1 and entries[0]["dtype"] == "BF16" and
                entries[0]["shape"] == [SOURCE_N, K] and
                entries[0]["sha256"] == pins["inputs"][role + "_weight"]["sha256"],
                "actual weight provenance/shape mismatch: " + role)
        require(not any(t["local_name"] == "mlp." + role + "_proj.bias" for t in manifest["tensors"]),
                "unexpected bias requires explicit arithmetic")
    result = json.loads((ROOT / "work/qwen2_fullgraph_dataflow_20261011/cold_m128/RESULT.json").read_text())
    prepared = json.loads((ROOT / "work/qwen2_fullgraph_dataflow_20261011/PREPARED.json").read_text())
    require(result["tokens"] == 128 and result["all_15_stages_bit_exact"] and
            result["prepared_sha256"] == pins["provenance"]["work/qwen2_fullgraph_dataflow_20261011/PREPARED.json"] and
            result["arena_sha256"] == prepared["arena"]["sha256"], "saved producer receipt chain mismatch")
    for phase, width, entry in [(9, K, pins["inputs"]["n1"])] + [
            (i, SOURCE_N, pins["comparison_only"][role]) for i, role in ((10, "gate"), (11, "up"), (12, "act"))]:
        saved = next(t for t in result["stages"] if t["phase"] == phase)
        require(saved["width"] == width and saved["sha256"] == entry["sha256"] and
                saved["path"] == Path(entry["path"]).name, "saved stage provenance mismatch")
    return {"model_id": manifest["model_id"], "revision": manifest["revision"], "layer_id": 0,
            "official_framework_forward": False, "producer_origin": pins["producer_origin"]}


def build_library(out, pins, frozen_root=None):
    root = frozen_root or ROOT
    base = root / TASK.relative_to(ROOT)
    library_path = out / "numeric_recipe.so"
    argv = ["g++", *pins["recipe"]["compiler_flags"], str(base / "numeric_recipe.cpp"),
            str(base.parent / "ffn_tiles/silu_recipe.cpp"), "-o", str(library_path)]
    with (out / "compile.log").open("w") as log:
        subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    lib = C.CDLL(str(library_path))
    u16, u32 = C.POINTER(C.c_uint16), C.POINTER(C.c_uint32)
    lib.td_reset.argtypes, lib.td_reset.restype = [], C.c_int
    lib.td_group.argtypes, lib.td_group.restype = [C.c_uint] * 3, C.c_int
    lib.td_step.argtypes, lib.td_step.restype = [C.c_uint] * 6 + [u16, u16, u32], C.c_int
    lib.fw_reference.argtypes, lib.fw_reference.restype = [u32, u16, u32] + [C.c_uint] * 3, C.c_int
    lib.sf_vector.argtypes, lib.sf_vector.restype = [u32] * 6, C.c_int
    lib.sf_reference.argtypes, lib.sf_reference.restype = [u32, u32, u32, C.c_uint], C.c_int
    require(lib.td_reset() == 0 and lib.sf_reset() == 0, "host IEEE FP32/RNE/gradual-subnormal environment unsupported")
    return lib, {"argv": argv, "binary_sha256": file_sha(library_path),
                 "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0]}


def weight_response(raw, address, base, rows, ng, cols):
    """Read exact full-N K-major DDR coordinates from output-major source bytes."""
    require(address >= base and (address - base) % 64 == 0, "unaligned B source address")
    k, n = divmod((address - base) // 2, SOURCE_N)
    require(0 <= k < rows and ng <= n and n + 32 <= ng + cols, "B address escaped source window/stride")
    return tuple(raw[(n + lane) * rows + k] for lane in range(32))


class SourceMemory:
    """One address-decoded, immutable virtual DDR map, established prelaunch.

    Weight file bytes are [N,K]; virtual DDR bytes are their explicit [K,N]
    transpose. This lazy materializer needs no second full weight allocation.
    Selection depends ONLY on the requested address, never the active role,
    job, descriptor kind or expected answer. No output region exists here.
    """
    def __init__(self, inputs):
        self.inputs = inputs
        self.regions = [(SOURCE_BASES[name], SOURCE_BASES[name] + len(raw) * raw.itemsize, name)
                        for name, raw in inputs.items()]
        require(all(end <= other_start or other_end <= start
                    for i, (start, end, _) in enumerate(self.regions)
                    for other_start, other_end, _ in self.regions[i + 1:]), "source DDR regions alias")

    def read64(self, address):
        matches = [(start, name) for start, end, name in self.regions if start <= address and address + 64 <= end]
        require(len(matches) == 1 and address % 64 == 0, "unmapped/aliased/unaligned DDR read")
        base, name = matches[0]
        if name == "n1":
            index = (address - base) // 4
            words = tuple(self.inputs[name][index:index + 16])
        else:
            words = weight_response(self.inputs[name], address, base, K, 0, SOURCE_N)
        return name, words


def execute_window(model, lib, owner, memory, case, role, deadline):
    rows, cols, ng = (case[x] for x in ("rows", "cols", "ng"))
    slot = 0 if role == "gate" else 1
    job = model.Job(m=rows, k=K, n=SOURCE_N, activation_bf16=False, weight_bf16=True,
                    output_bf16=False, a=SOURCE_BASES["n1"], b=SOURCE_BASES[role + "_weight"],
                    dst=DESTINATION_BASES[role], tag=case["identity"] + slot, write_bytes=rows * SOURCE_N * 4)
    request = model.FfnWindowRequest(job, case["identity"], ng, cols, slot, reuse_a=bool(slot))
    event = owner.tick(window=request)
    require(event["window_fire"], "window request was not accepted")
    pending = None
    results = deque()
    counts, physical = Counter(), Counter()
    first_b = last_b = None
    descriptor_hash, packet_hash = hashlib.sha256(), hashlib.sha256()
    payload_hash = {name: hashlib.sha256() for name in ("a", "b")}
    aa, bb, terminal = (C.c_uint16 * 16)(), (C.c_uint16 * 256)(), (C.c_uint32 * 4096)()
    matrix_done_sent = False
    group_count = 0
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("bounded actual window exceeded wall budget")
        ports = owner.ports()
        kwargs = {"step_ready": not (ports["step"] is not None and ports["step"].last and len(results) >= 2)}
        if pending is not None:
            command, words = pending
            kwargs["read_beat"] = model.ReadBeat(command.tag, words, True)
        if results:
            kwargs["result"] = results[0]
        if (owner.group_started and not owner.group_done and
                owner.group_accepted_steps == K * (cols // 32) and owner.results_received == cols // 32 and not results):
            kwargs["matrix_done"] = model.MatrixDone(job.tag)
        event = owner.tick(**kwargs)
        for bank in ("a", "b"):
            for action in ("reads", "writes"):
                accesses = event.get(bank + "_" + action, {})
                require(len(accesses) <= 16, "physical bank port multiplicity")
                physical[bank + "_bank_word_" + action] += len(accesses)
        if event.get("group_fire"):
            group_count += 1
            require(group_count == 1 and lib.td_group(0, K, cols // 32) == 0, "unexpected window Matrix group")
        if event.get("read_fire"):
            require(pending is not None, "input response without descriptor")
            counts[pending[0].kind + "_read_responses"] += 1
            pending = None
        if event.get("read_command_fire"):
            require(pending is None, "overlapping DDR read descriptors")
            command = event["read_command"]
            require(command.beats == 1 and command.address % 64 == 0, "input descriptor shape/alignment")
            region, words = memory.read64(command.address)
            if command.kind == "a":
                offset = (command.address - job.a) // 4
                require(region == "n1" and command.address >= job.a and offset + 16 <= rows * K,
                        "A read outside exact raw source")
            else:
                require(command.kind == "b" and region == role + "_weight", "wrong address-decoded operand source")
                source_k, source_n = divmod((command.address - job.b) // 2, SOURCE_N)
                require(0 <= source_k < K and ng <= source_n and source_n + 32 <= ng + cols,
                        "B address escaped source window/stride")
                first_b = command.address if first_b is None else first_b
                last_b = command.address
            pending = (command, words)
            descriptor_hash.update(descriptor_record(command))
            payload_hash[command.kind].update(struct.pack("<" + ("I" if command.kind == "a" else "H") * len(words), *words))
            counts[command.kind + "_read_descriptors"] += 1
        if event.get("step_fire"):
            step = event["step"]
            aa[:], bb[:] = step.a, step.b
            packet_hash.update(struct.pack("<HBBBBB", step.k, step.context, step.clear, step.last, step.finish, step.emit))
            packet_hash.update(bytes(aa)); packet_hash.update(bytes(bb))
            status = lib.td_step(step.k, step.context, step.clear, step.last, step.finish, step.emit, aa, bb, terminal)
            require(status >= 0 and bool(status) == step.last, "actual physical-packet FMA failed")
            counts["matrix_steps"] += 1
            if status:
                tile = tuple(tuple(terminal[r * 256 + n] for n in range(256)) for r in range(16))
                results.append(model.MatrixResult(step.context, tile))
        if event.get("result_fire"):
            results.popleft()
            counts["matrix_results"] += 1
        if "matrix_done" in kwargs and event["matrix_done_ready"]:
            require(not matrix_done_sent, "duplicate MatrixDone")
            matrix_done_sent = True
        require(not event.get("write_command_fire") and not event.get("write_data_fire"), "window emitted DDR output")
        if event.get("window_result_fire"):
            completion = event["window_result"]
            break
        require(not owner.error, "window owner failed: " + str(owner.error))
    require(completion.status is None and completion.committed and completion.ddr_write_bytes == 0 and
            completion.produced_beats == rows // 16 * cols, "window failed commit/completion fence")
    require(not pending and not results and matrix_done_sent, "completion before all external obligations drained")
    require(counts["a_read_descriptors"] * 64 == (rows * K * 4 if slot == 0 else 0) and
            counts["b_read_descriptors"] * 64 == K * cols * 2 and counts["matrix_steps"] == K * (cols // 32) and
            counts["matrix_results"] == cols // 32, "window traffic/arithmetic count mismatch")
    require(owner.rmw_commits == (rows * K if slot == 0 else 0) and owner.a_fences == 1 and
            owner.lease == model.ALease.for_request(request), "actual A RMW/fence/reuse lease mismatch")
    return {"role": role, "completion": asdict(completion), "ddr": {
        "declared_full_destination_base": job.dst, "declared_full_destination_bytes": rows * SOURCE_N * 4,
        "a_read_bytes": counts["a_read_descriptors"] * 64, "b_read_bytes": counts["b_read_descriptors"] * 64,
        "output_write_bytes": 0, "source_n_stride": SOURCE_N,
        "first_b_address": first_b, "last_b_address": last_b,
        "first_b_offset_bytes": first_b - job.b, "last_b_offset_bytes": last_b - job.b,
        "expected_first_b_offset_bytes": ng * 2,
        "expected_last_b_offset_bytes": ((K - 1) * SOURCE_N + ng + cols - 32) * 2},
        "physical_sram": {**dict(physical), **{name.replace("word", "bytes"): value * 32 for name, value in physical.items()}},
        "accepted": dict(counts), "ddr_descriptor_sha256": descriptor_hash.hexdigest(),
        "ddr_descriptor_record_format": "<cQIQ: kind, byte_address, beats, full_64bit_internal_tag",
        "actual_a_ingress_rmw_commits": owner.rmw_commits, "actual_a_load_fences_total": owner.a_fences,
        "actual_a_lease": asdict(owner.lease),
        "accepted_ddr_payload_sha256": {name: digest.hexdigest() for name, digest in payload_hash.items()},
        "matrix_packet_sha256": packet_hash.hexdigest(), "matrix_result_source": "unchanged td_step on actual accepted bank packets"}


def execute_case(model, tile_check, lib, memory, case, out, deadline):
    rows, cols, ng = (case[x] for x in ("rows", "cols", "ng"))
    destination = out / f"m{rows}_n{cols}_ng{ng}"
    destination.mkdir()
    workspace = model.PrefixWorkspace(0x10000000, 16 * 1024, case["identity"], 2560)
    spans = list(memory.regions) + [(base, base + rows * SOURCE_N * 4, role + "_declared_destination")
                                   for role, base in DESTINATION_BASES.items()]
    spans.append((workspace.base, workspace.base + workspace.extent, "declared_prefix_workspace"))
    require(all(end <= other_start or other_end <= begin
                for i, (begin, end, _) in enumerate(spans)
                for other_start, other_end, _ in spans[i + 1:]), "cross-command full DDR spans alias")
    owner = model.FfnWindowOwnerModel(workspace, enable_ffn_window=True, enable_ffn_tiles=True)
    require(owner.tiles.banks is owner.a_banks, "Dense and tile ports must share actual A SRAM")
    started = time.monotonic()
    gate = execute_window(model, lib, owner, memory, case, "gate", deadline)
    retained = tile_check.bank_region_hash(owner.a_banks.words, 0, 768)
    up = execute_window(model, lib, owner, memory, case, "up", deadline)
    require(tile_check.bank_region_hash(owner.a_banks.words, 0, 768) == retained, "Up changed retained A")
    require(gate["ddr"]["first_b_offset_bytes"] == up["ddr"]["first_b_offset_bytes"] == ng * 2,
            "nonzero window did not use source N offset")
    for report in (gate, up):
        require(report["ddr"]["last_b_offset_bytes"] == report["ddr"]["expected_last_b_offset_bytes"],
                "last B read did not preserve full source stride")
    beats = rows // 16 * cols
    actual = {role: [None] * (rows * cols) for role in ("gate", "up", "act")}
    operands = [(C.c_uint32 * 16)() for _ in range(3)]
    values, flags, errors = (C.c_uint32 * 96)(), (C.c_uint32 * 96)(), (C.c_uint32 * 16)()
    phase_hash = hashlib.sha256()
    phase_flags = Counter()
    tile_before = dict(owner.tiles.counters)
    with (destination / "silu_bank_events.jsonl").open("wb") as trace:
        driver = tile_check.BankDriver(model.tiles, owner.tiles, case, trace, deadline)
        driver.control(0, 2)
        for index in range(beats):
            g, u = driver.read(0, index), driver.read(1, index)
            for role, words in (("gate", g), ("up", u)):
                row_group, n = divmod(index, cols)
                for lane, word in enumerate(words):
                    actual[role][(row_group * 16 + lane) * cols + n] = word
            operands[0][:], operands[1][:] = g, u
            status = lib.sf_vector(*operands, values, flags, errors)
            require(status == 0, f"unchanged SiLU policy rejected beat {index}: status={status}, errors={list(errors)}")
            phase_hash.update(bytes(values))
            phase_flags.update(flags)
            driver.write(2, index, tuple(operands[2]))
        driver.control(1, 2)
        for index in range(beats):
            words = driver.read(2, index)
            row_group, n = divmod(index, cols)
            for lane, word in enumerate(words):
                offset = (row_group * 16 + lane) * cols + n
                require(actual["act"][offset] is None, "duplicate Act read")
                actual["act"][offset] = word
        for slot in range(3):
            driver.control(2, slot)
        driver.check_storage()
    require(all(word is not None for output in actual.values() for word in output), "incomplete actual tile outputs")
    require(not owner.tiles.leased and owner.tiles.idle, "output tiles did not completely drain")
    require(tile_check.bank_region_hash(owner.a_banks.words, 0, 768) == retained, "SiLU changed retained A")
    after = owner.tiles.counters
    expected = {"read_requests": 3 * beats, "write_requests": beats, "read_responses": 3 * beats,
                "rmw_commits": beats, "logical_read_bytes": 3 * beats * 64, "logical_write_bytes": beats * 64,
                "physical_read_bytes": 4 * beats * 512, "physical_write_bytes": beats * 512}
    require(all(after[key] - tile_before[key] == value for key, value in expected.items()), "SiLU physical port accounting mismatch")
    for role, words in actual.items():
        (destination / ("actual_" + role + ".f32le")).write_bytes(tile_check.wire_bytes(words))
    return {"case": case, "actual": actual, "directory": destination.name, "windows": [gate, up],
            "cross_command_spans_disjoint": [{"begin": begin, "end_exclusive": end, "region": region}
                                             for begin, end, region in spans],
            "actual_a_loaded_once_reused_without_ddr": True, "same_physical_a_banks_across_entire_chain": True,
            "retained_a_sha256_after_gate_up_silu": retained,
            "silu": {"accepted_requests": beats, "physical_bank_word_reads": driver.counts["physical_bank_word_reads"],
                     "physical_bank_word_writes": driver.counts["physical_bank_word_writes"],
                     "port_counters": expected, "bank_event_sha256": driver.trace.hexdigest(),
                     "phase_value_sha256": phase_hash.hexdigest(), "host_phase_exception_flags": dict(phase_flags)},
            "host_wall_seconds": time.monotonic() - started,
            "host_fma_updates": {"physical_packet_arithmetic": 2 * K * (cols // 32) * 4096,
                                 "post_completion_independent_direct": 2 * rows * cols * K},
            "all_actual_outputs_completed_before_comparison": True}


def verify_capture_sources(report):
    current = {path: file_sha(ROOT / path) for path in report["source_sha256"]}
    report["source_changed_since_freeze"] = [path for path, digest in current.items() if digest != report["source_sha256"][path]]
    require(not report["source_changed_since_freeze"], "source changed during frozen numerical capture")
    report["source_sha256_after"] = current


def run(out, only_rows=16):
    require(not out.exists(), "use a new evidence directory")
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {"status": "PREPARING", "cases": []}
    def save():
        (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    try:
        require(sys.byteorder == "little", "explicit little-endian host required")
        meminfo = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available_kib = int(meminfo["MemAvailable"].split()[0])
        require(available_kib >= 512 * 1024, "less than 512 MiB available before bounded host capture")
        report["host_resources_before"] = {"available_memory_kib": available_kib,
                                           "process_max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        pins = load_pins()
        origin = verify_provenance(pins)
        cases = [c for c in pins["default_cases"] if only_rows is None or c["rows"] == only_rows]
        require(bool(cases), "no bounded cases selected")
        inputs = {}
        for name, spec in pins["inputs"].items():
            inputs[name] = array("I" if name == "n1" else "H")
            inputs[name].frombytes(checked_file(spec))
        memory = SourceMemory(inputs)
        # Hash only; no decoding or retained comparison values before completion.
        for spec in pins["comparison_only"].values():
            require((ROOT / spec["path"]).stat().st_size == spec["bytes"] and file_sha(ROOT / spec["path"]) == spec["sha256"],
                    "comparison-only file identity drift")
        source_paths = set(pins["sources"])
        source_paths.update(str((TASK / name).relative_to(ROOT)) for name in
                            ("check_numeric.py", "numeric_recipe.cpp", "precision_pins.json", "model.py"))
        composition_path = TASK / "source_pins.json"
        require(composition_path.exists(), "source composition must freeze before actual capture")
        composition = json.loads(composition_path.read_text())
        composition_sources = {str(composition_path.relative_to(ROOT)): composition_path.read_bytes()}
        for path, digest in composition["patches"].items():
            require(file_sha(ROOT / path) == digest, "source composition patch drift: " + path)
            composition_sources[path] = (ROOT / path).read_bytes()
        frozen = out / "frozen_sources"
        sources = {path: (ROOT / path).read_bytes() for path in sorted(source_paths)}
        for path, raw in {**sources, **composition_sources}.items():
            target = frozen / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        report.update(status="PINNED_BEFORE_EXECUTION", scope=pins["scope"], acceptance=pins["acceptance"],
                      origin=origin, pins=pins, source_sha256={path: sha(raw) for path, raw in sources.items()},
                      source_composition_snapshot=composition,
                      source_composition_snapshot_sha256={path: sha(raw) for path, raw in composition_sources.items()},
                      source_composition_scope="Pre-run snapshot only; Python model and arithmetic execute. Scala composition is validated separately and may advance after this snapshot.",
                      source_to_ddr={"selection": "one address-only source map; disjoint regions; no outputs initialized",
                          "n1": {"base": SOURCE_BASES["n1"], "shape": [128, K], "dtype": "FP32 little-endian",
                                 "conversion": "actual owner DDR/RMW ingress rounds to BF16 RNE in retained A"},
                          "weights": {"raw_layout": "output-major [N8960,K1536] BF16 little-endian",
                                      "ddr_layout": "explicit virtual transpose [K1536,N8960] BF16 little-endian",
                                      "materialization": "raw[n*K+k] serves DDR base+2*(k*8960+n); immutable lazy byte mapping",
                                      "bases": {role: SOURCE_BASES[role + "_weight"] for role in ("gate", "up")},
                                      "bytes_per_region": K * SOURCE_N * 2,
                                      "accepted_address_and_payload_hashes": "recorded separately for each completed window"}},
                      budget={"wall_seconds": 180, "compile_timeout_seconds": 30, "estimated_memory_mib": 256,
                              "single_host_process": True, "full_projection_or_block_runs": 0, "rtl_or_eda_runs": 0},
                      hardware_arithmetic_executed=False, rtl_executed=False, actual_idma=False,
                      protocol_model_ticks_are_hardware_cycles=False, predicted_hardware_cycles=None,
                      native_m128_and_fp32_final_acceptance="UNCHANGED_FAIL_POLICY_PENDING")
        save()
        (out / "FROZEN_PINS.json").write_text(json.dumps(report, indent=2) + "\n")
        lib, report["compile"] = build_library(out, pins, frozen)
        base = frozen / TASK.relative_to(ROOT)
        model = load_module("ffn_window_numeric_owner", base / "model.py")
        tile_check = load_module("ffn_window_existing_tile_numeric", base.parent / "ffn_tiles/check_numeric.py")
        completed = [execute_case(model, tile_check, lib, memory, case, out, start + 180) for case in cases]
        # Actual Gate + Up + Act output responses have ALL completed before
        # the first reference entry point or saved output decode is accessible.
        ca = (C.c_uint32 * len(inputs["n1"])).from_buffer(inputs["n1"])
        for case_report in completed:
            actual = case_report.pop("actual")
            c = case_report["case"]
            count = c["rows"] * c["cols"]
            direct = {role: (C.c_uint32 * count)() for role in ("gate", "up", "act")}
            for role in ("gate", "up"):
                cw = (C.c_uint16 * len(inputs[role + "_weight"])).from_buffer(inputs[role + "_weight"])
                require(lib.fw_reference(ca, cw, direct[role], c["rows"], c["cols"], c["ng"]) == 0, "independent direct dot failed")
            require(lib.sf_reference(direct["gate"], direct["up"], direct["act"], count) == 0, "independent direct SiLU failed")
            mismatches = {}
            for role in ("gate", "up", "act"):
                saved = array("I")
                saved.frombytes(checked_file(pins["comparison_only"][role]))
                saved_tile = tile_check.flat_tile(saved, c["rows"], c["cols"], c["ng"])
                mismatches[role] = {"independent_direct_bit_mismatches": sum(x != y for x, y in zip(actual[role], direct[role])),
                                    "saved_producer_bit_mismatches": sum(x != y for x, y in zip(actual[role], saved_tile)),
                                    "actual_sha256": sha(tile_check.wire_bytes(actual[role])),
                                    "direct_sha256": sha(bytes(direct[role])), "saved_sha256": sha(tile_check.wire_bytes(saved_tile))}
                for name, expected in (("independent_direct", direct[role]), ("saved_producer", saved_tile)):
                    mismatch = next((i for i, (x, y) in enumerate(zip(actual[role], expected)) if x != y), None)
                    mismatches[role][name + "_first_difference"] = None if mismatch is None else {
                        "flat_index": mismatch, "m": mismatch // c["cols"], "source_n": c["ng"] + mismatch % c["cols"],
                        "actual_fp32_bits": f"0x{actual[role][mismatch]:08x}",
                        "expected_fp32_bits": f"0x{expected[mismatch]:08x}"}
            case_report["comparison"] = mismatches
            report["cases"].append(case_report)
            require(all(not item["independent_direct_bit_mismatches"] and not item["saved_producer_bit_mismatches"] for item in mismatches.values()),
                    "actual window chain differs from independent or saved producer outputs")
        require(time.monotonic() < start + 180, "bounded actual chain exceeded wall budget")
        require(all(sha(raw.tobytes()) == pins["inputs"][name]["sha256"] for name, raw in inputs.items()),
                "immutable raw source changed during actual execution/reference")
        verify_capture_sources(report)
        report.update(status="PASS_ACTUAL_N1_GATE_UP_SILU_WINDOWS_HOST_MODEL_ONLY", wall_seconds=time.monotonic() - start,
                      host_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save()
        return report
    except Exception as error:
        report.update(status="FAILED", error=str(error), wall_seconds=time.monotonic() - start)
        save()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only-rows", type=int, choices=(16, 128), default=16,
                        help="first prove M16/N32; run M128/N160 separately after that gate passes")
    args = parser.parse_args()
    result = run(args.out.resolve(), args.only_rows)
    print(json.dumps({"status": result["status"], "cases": len(result["cases"]), "wall_seconds": result["wall_seconds"]}))

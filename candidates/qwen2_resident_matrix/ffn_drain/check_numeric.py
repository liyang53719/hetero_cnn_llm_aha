#!/usr/bin/env python3
"""Bounded actual raw n1 -> Gate -> retained-A Up -> SiLU -> act DDR/ACK.

Only raw n1 and official BF16 weights initialize execution. Existing bank
packets drive unchanged host FMA and SiLU recipes. The drain model reads the
computed act slot, repacks its existing final_value, and emits real accepted
64-byte write beats into address-decoded sentinel DDR. References and saved
outputs are decoded only after terminal success and every tagged write ACK.
This is host protocol/numeric evidence, not native Matrix/SFU, RTL or HostTop.
"""
import argparse
from array import array
from collections import Counter
import ctypes as C
from dataclasses import asdict, is_dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import struct
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
K, SOURCE_N = 1536, 8960
ACT_BASE = 0xA000000
FULL_MASK = (1 << 64) - 1
SENTINEL_WORD = 0xA5963CC3
CANARY_BYTES = 64
WALL_BUDGET = 180


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


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


window_check = load_module("ffn_drain_unchanged_window_numeric", TASK.parent / "ffn_window/check_numeric.py")
SOURCE_BASES, DESTINATION_BASES = window_check.SOURCE_BASES, window_check.DESTINATION_BASES
SourceMemory = window_check.SourceMemory


def checked_file(spec):
    raw = (ROOT / spec["path"]).read_bytes()
    require(len(raw) == spec["bytes"] and sha(raw) == spec["sha256"],
            "frozen input identity drift: " + spec["path"])
    return raw


def load_pins(check_provenance=True):
    """Local payload receipts are mandatory for real captures, never unit tests."""
    pins = json.loads((TASK / "precision_pins.json").read_text())
    for category in (("sources", "provenance") if check_provenance else ("sources",)):
        for path, digest in pins[category].items():
            require(file_sha(ROOT / path) == digest, "frozen source identity drift: " + path)
    return pins


def build_library(out, pins, frozen_root=None):
    # Compile the exact previously published recipe and source-tied SiLU.
    # There is deliberately no second numeric_recipe.cpp in this candidate.
    return window_check.build_library(out, pins, frozen_root)


def jsonable(value):
    if is_dataclass(value):
        return asdict(value)
    raise TypeError("unrecordable protocol event: " + type(value).__name__)


class OwnerTilePort:
    """Route the unchanged SFU bank driver through the owner's external port.

    Every idle producer/consumer/stall edge clocks the owner, so a model that
    steals or poisons an external response is observable. This remains Python
    port behavior; only separate source/RTL evidence can establish the Scala
    arbitration implementation. No new model storage or arithmetic is added.
    """
    def __init__(self, owner):
        self.owner = owner
        self.banks = owner.a_banks
        self.counts = Counter()

    @property
    def poison(self):
        return self.owner.tiles.poison or bool(self.owner.error)

    def tick(self, *, control=None, write=None, read=None, response_ready=True):
        require(self.owner.state == "idle", "external SiLU tile port offered while Dense owner was not idle")
        event = self.owner.tick(tile_control=control, tile_write=write, tile_read=read,
                                tile_response_ready=response_ready)
        require(not self.owner.error and not self.owner.tiles.poison, "owner poisoned external SiLU tile response")
        require(self.owner.state == "idle" and not any(event.get(key) for key in
                ("read_command_fire", "read_fire", "step_fire", "result_fire", "write_command_fire",
                 "write_data_fire", "write_ack_fire", "window_fire", "drain_fire", "response_fire")),
                "external SiLU tile edge emitted unrelated owner traffic")
        require("tile" in event, "owner did not route external SiLU tile edge")
        self.counts["owner_idle_ticks"] += 1
        for signal in ("ctl_fire", "read_fire", "write_fire", "response_fire", "rmw_commit"):
            self.counts[signal] += bool(event["tile"].get(signal))
        return dict(event["tile"], owner_external_tile_port={"model_tick": self.owner.clock,
                    "owner_state": self.owner.state, "owner_error": self.owner.error})


class DestinationMemory:
    """Address-only act DDR, with no expected tensor or role-dependent writes.

    The full Mx8960 output span and both surrounding guard cachelines begin as
    sentinels. Only accepted descriptor/data traffic mutates it; comparison
    code can read it after all matching successful ACKs have retired.
    """
    def __init__(self, rows, base=ACT_BASE, width=SOURCE_N):
        require(rows in (16, 128) and base % 64 == 0 and width % 16 == 0, "DDR destination geometry")
        self.rows, self.base, self.width = rows, base, width
        self.extent = rows * width * 4
        self.initial = struct.pack("<I", SENTINEL_WORD) * ((self.extent + 2 * CANARY_BYTES) // 4)
        self.data = bytearray(self.initial)
        self.pending = None
        self.next_beat = 0
        self.data_bytes = self.ack_bytes = 0
        self.write_addresses = set()
        self.descriptors = self.acks = 0
        self.last_tag = None

    def accept_command(self, command):
        require(self.pending is None, "DDR descriptor accepted before previous ACK")
        require(type(command.address) is int and command.address % 64 == 0,
                "DDR write address is not aligned to 64B")
        require(type(command.beats) is int and 1 <= command.beats <= 16, "DDR burst beat bound")
        require(command.address // 1024 == (command.address + command.beats * 64 - 1) // 1024,
                "DDR write burst crosses 1KiB boundary")
        require(self.base <= command.address and command.address + command.beats * 64 <= self.base + self.extent,
                "DDR write escaped address-only act region")
        require(type(command.tag) is int and 0 <= command.tag < 2**64, "DDR tag width")
        if self.last_tag is not None:
            require(command.tag == self.last_tag + 1, "DDR write sequence/tag discontinuity")
        self.pending, self.next_beat = command, 0
        self.last_tag = command.tag
        self.descriptors += 1

    def accept_data(self, beat):
        require(self.pending is not None, "DDR write data without descriptor")
        require(self.next_beat < self.pending.beats, "extra DDR data beat")
        require(beat.mask == FULL_MASK, "DDR write must use full 64-byte physical mask")
        require(len(beat.words) == 16 and all(type(word) is int and 0 <= word < 2**32 for word in beat.words),
                "DDR write data must contain sixteen FP32 bit patterns")
        require(beat.last == (self.next_beat + 1 == self.pending.beats), "DDR last marker disagrees with burst")
        address = self.pending.address + self.next_beat * 64
        require(address not in self.write_addresses, "duplicate physical DDR write address")
        offset = CANARY_BYTES + address - self.base
        self.data[offset:offset + 64] = struct.pack("<16I", *beat.words)
        self.write_addresses.add(address)
        self.next_beat += 1
        self.data_bytes += 64
        return address

    @property
    def awaiting_ack(self):
        return self.pending is not None and self.next_beat == self.pending.beats

    def accept_ack(self, ack):
        require(self.awaiting_ack, "DDR ACK before all write data")
        require(ack.tag == self.pending.tag and not ack.error and ack.nbytes == self.pending.beats * 64,
                "DDR ACK tag/status/byte count mismatch")
        self.ack_bytes += ack.nbytes
        self.acks += 1
        self.pending = None

    def validate_and_read(self, ng, cols):
        require(self.pending is None and self.acks == self.descriptors and self.data_bytes == self.ack_bytes,
                "DDR observed before all matching ACKs")
        require(ng % 32 == 0 and cols in (32, 64, 96, 128, 160) and ng + cols <= self.width,
                "DDR comparison window geometry")
        expected_addresses = {self.base + (m * self.width + ng + n) * 4
                              for m in range(self.rows) for n in range(0, cols, 16)}
        require(self.write_addresses == expected_addresses, "physical DDR write coverage mismatch")
        require(self.data[:CANARY_BYTES] == self.initial[:CANARY_BYTES] and
                self.data[-CANARY_BYTES:] == self.initial[-CANARY_BYTES:], "act DDR canary corruption")
        actual = []
        untouched = 2 * CANARY_BYTES
        for m in range(self.rows):
            first = CANARY_BYTES + (m * self.width + ng) * 4
            end = first + cols * 4
            row_begin = CANARY_BYTES + m * self.width * 4
            row_end = row_begin + self.width * 4
            require(self.data[row_begin:first] == self.initial[row_begin:first] and
                    self.data[end:row_end] == self.initial[end:row_end], "untouched full-stride act DDR region changed")
            actual.extend(struct.unpack("<" + "I" * cols, self.data[first:end]))
            untouched += (self.width - cols) * 4
        return actual, {"full_destination_bytes": self.extent, "written_bytes": self.data_bytes,
                        "successful_ack_bytes": self.ack_bytes, "write_descriptors": self.descriptors,
                        "successful_acks": self.acks, "distinct_physical_64b_writes": len(self.write_addresses),
                        "untouched_bytes_including_canaries": untouched, "canary_bytes": 2 * CANARY_BYTES,
                        "all_untouched_bytes_exact": True, "canaries_exact": True,
                        "full_destination_sha256": sha(self.data[CANARY_BYTES:-CANARY_BYTES]),
                        "sentinel_word_hex": hex(SENTINEL_WORD)}


def execute_drain(model, owner, case, destination, trace_file, deadline, *, final_ack_stall=5):
    """Drive accepted write traffic; never copy expected values into DDR."""
    rows, cols, ng = (case[x] for x in ("rows", "cols", "ng"))
    job = model.ActivationJob(m=rows, k=SOURCE_N, n=SOURCE_N,
        tag=case["identity"] + 2, a=DESTINATION_BASES["gate"], b=DESTINATION_BASES["up"],
        dst=destination.base, activation_bf16=False, weight_bf16=False, output_bf16=False,
        write_bytes=rows * SOURCE_N * 4)
    request = model.FfnDrainRequest(job, case["identity"], ng, cols)
    counts = Counter()
    hashes = {name: hashlib.sha256() for name in ("descriptor", "data", "ack", "trace")}
    tile_before = dict(owner.tiles.counters)
    held = {}
    stall_remaining = final_ack_stall
    final_ack_seen = False
    before_final_ack = None

    def log(inputs, event):
        encoded = (json.dumps({"model_tick": counts["ticks"], "inputs": inputs, "events": event},
                              default=jsonable, sort_keys=True, separators=(",", ":")) + "\n").encode()
        trace_file.write(encoded)
        hashes["trace"].update(encoded)

    event = owner.tick(drain=request)
    log({"drain": request}, event)
    require(event["drain_fire"], "activation drain request was not accepted")
    while True:
        require(time.monotonic() <= deadline, "bounded act drain exceeded wall budget")
        counts["ticks"] += 1
        ports = owner.ports()
        inputs = {"write_command_ready": counts["ticks"] % 5 != 0,
                  "write_data_ready": counts["ticks"] % 7 != 0}
        if destination.awaiting_ack:
            command = destination.pending
            is_final = destination.data_bytes == rows * cols * 4
            if is_final and stall_remaining:
                require(not ports.get("drain_result"), "drain completion appeared before final ACK")
                require(owner.tiles.tags[2].live, "act slot released before final ACK")
                if before_final_ack is None:
                    before_final_ack = {"data_bytes": destination.data_bytes, "ack_bytes": destination.ack_bytes,
                                        "slot2_live": owner.tiles.tags[2].live}
                stall_remaining -= 1
                counts["final_ack_stall_ticks"] += 1
            else:
                inputs["write_ack"] = model.WriteAck(command.tag, False, command.beats * 64)
        event = owner.tick(**inputs)
        # The held result describes the completed transaction, while a fault
        # arriving on its acceptance edge may poison the owner concurrently.
        # Check the post-edge sideband before accepting that immutable result.
        post = {"error": owner.error, "drain_poison": bool(getattr(owner, "drain_poison", False)),
                "tile_poison": owner.tiles.poison, "reset_required": bool(owner.ports().get("reset_required"))}
        event["post_tick_owner_status"] = post
        log(inputs, event)
        require(not any(post.values()), "act drain owner failed after edge: " + str(post))
        for signal, ready in (("write_command", inputs["write_command_ready"]),
                              ("write_data", inputs["write_data_ready"])):
            if signal in held:
                require(event.get(signal) == held[signal], signal + " changed while backpressured")
            if event.get(signal) is not None and not ready:
                held[signal] = event[signal]
                counts[signal + "_stall_ticks"] += 1
            else:
                held.pop(signal, None)
        require(not event.get("read_command_fire") and not event.get("read_fire") and
                not event.get("step_fire") and not event.get("result_fire"), "act drain emitted input DDR/Matrix traffic")
        for bank in ("a", "b"):
            for action in ("reads", "writes"):
                accesses = event.get(bank + "_" + action, {})
                counts[bank + "_physical_bank_word_" + action] += len(accesses)
        if event.get("write_command_fire"):
            command = event["write_command"]
            require(command.tag >> 32 == job.tag, "DDR descriptor job tag mismatch")
            destination.accept_command(command)
            hashes["descriptor"].update(struct.pack("<QIQ", command.address, command.beats, command.tag))
            counts["write_command_fire"] += 1
        if event.get("write_data_fire"):
            beat = event["write_data"]
            address = destination.accept_data(beat)
            hashes["data"].update(struct.pack("<QQ?16I", address, beat.mask, beat.last, *beat.words))
            counts["write_data_fire"] += 1
        if event.get("write_ack_fire"):
            ack = inputs.get("write_ack")
            require(ack is not None, "accepted write ACK without actual response")
            destination.accept_ack(ack)
            hashes["ack"].update(struct.pack("<Q?I", ack.tag, ack.error, ack.nbytes))
            counts["write_ack_fire"] += 1
            if destination.ack_bytes == rows * cols * 4:
                final_ack_seen = True
                counts["final_ack_tick"] = counts["ticks"]
        if event.get("drain_result_fire"):
            result = event["drain_result"]
            require(final_ack_seen and counts["ticks"] > counts["final_ack_tick"],
                    "drain result preceded real final ACK/release verification")
            require(result.status is None and result.committed and result.ddr_write_bytes == rows * cols * 4 and
                    result.consumed_beats == rows // 16 * cols, "failed act drain completion/count fence")
            require(not owner.tiles.tags[2].live and owner.tiles.idle, "act release/drain missing at completion")
            break
    require(counts["final_ack_stall_ticks"] == final_ack_stall, "final ACK stall did not execute")
    actual, memory_report = destination.validate_and_read(ng, cols)
    tile_delta = {key: owner.tiles.counters[key] - tile_before[key] for key in owner.tiles.counters}
    beats = rows // 16 * cols
    for key, value in {"read_requests": beats, "read_responses": beats, "logical_read_bytes": beats * 64,
                       "physical_read_bytes": beats * 512, "write_requests": 0, "physical_write_bytes": 0}.items():
        require(tile_delta[key] == value, "act drain physical tile accounting mismatch: " + key)
    require(counts["write_data_fire"] * 64 == rows * cols * 4 and counts["write_command_fire"] == counts["write_ack_fire"],
            "act DDR accepted transaction count mismatch")
    return actual, {"completion": asdict(result), "ddr": memory_report, "accepted": dict(counts),
                    "tile_port_counters": tile_delta, "before_final_ack": before_final_ack,
                    "hashes": {key + "_sha256": value.hexdigest() for key, value in hashes.items()},
                    "trace_record": "one JSON object per protocol model tick, including complete physical write masks/data and ACK tag/status/bytes",
                    "actual_output_source": "address-decoded act DDR after all accepted write beats, successful tagged ACKs and terminal result"}


def execute_case(model, old_check, tile_check, lib, memory, case, out, deadline):
    rows, cols, ng = (case[x] for x in ("rows", "cols", "ng"))
    destination_dir = out / f"m{rows}_n{cols}_ng{ng}"
    destination_dir.mkdir()
    workspace = model.window.PrefixWorkspace(0x10000000, 16 * 1024, case["identity"], 2560)
    target = DestinationMemory(rows)
    spans = list(memory.regions) + [(base, base + rows * SOURCE_N * 4, role + "_declared_destination")
                                   for role, base in DESTINATION_BASES.items()]
    spans += [(target.base - CANARY_BYTES, target.base + target.extent + CANARY_BYTES, "sentinel_act_ddr_with_canaries"),
              (workspace.base, workspace.base + workspace.extent, "declared_prefix_workspace")]
    require(all(end <= other_start or other_end <= begin for i, (begin, end, _) in enumerate(spans)
                for other_start, other_end, _ in spans[i + 1:]), "cross-command full DDR spans alias")
    owner = model.FfnDrainOwnerModel(workspace, enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
    require(owner.tiles.banks is owner.a_banks, "Dense/SiLU/drain must use the same actual A SRAM")
    started = time.monotonic()
    gate = old_check.execute_window(model.window, lib, owner, memory, case, "gate", deadline)
    retained = tile_check.bank_region_hash(owner.a_banks.words, 0, 768)
    up = old_check.execute_window(model.window, lib, owner, memory, case, "up", deadline)
    require(tile_check.bank_region_hash(owner.a_banks.words, 0, 768) == retained, "Up changed retained A")
    for report in (gate, up):
        report["actual_a_activation_transactions"] = report["accepted"].get("a_read_responses", 0)
        report["actual_a_rmw_bank_word_commits"] = report.pop("actual_a_ingress_rmw_commits")
        report["a_ingress_accounting"] = "One accepted FP32 activation DDR beat updates 16 physical A bank words; neither count is a hardware cycle count."
        require(report["ddr"]["first_b_offset_bytes"] == ng * 2 and
                report["ddr"]["last_b_offset_bytes"] == report["ddr"]["expected_last_b_offset_bytes"],
                "weight window ignored ng/full N stride")
    beats = rows // 16 * cols
    actual = {role: [None] * (rows * cols) for role in ("gate", "up")}
    operands = [(C.c_uint32 * 16)() for _ in range(3)]
    values, flags, errors = (C.c_uint32 * 96)(), (C.c_uint32 * 96)(), (C.c_uint32 * 16)()
    phase_hash, phase_flags = hashlib.sha256(), Counter()
    tile_before = dict(owner.tiles.counters)
    with (destination_dir / "silu_bank_events.jsonl").open("wb") as trace:
        external_tile = OwnerTilePort(owner)
        driver = tile_check.BankDriver(model.window.tiles, external_tile, case, trace, deadline)
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
        for slot in (0, 1):
            driver.control(2, slot)
        driver.check_storage()
    require(owner.tiles.tags[2].live and owner.tiles.tags[2].sealed, "computed act tile not sealed for drain")
    silu_delta = {key: owner.tiles.counters[key] - tile_before[key] for key in owner.tiles.counters}
    for key, value in {"read_requests": 2 * beats, "write_requests": beats, "read_responses": 2 * beats,
                       "rmw_commits": beats, "logical_read_bytes": 2 * beats * 64, "logical_write_bytes": beats * 64,
                       "physical_read_bytes": 3 * beats * 512, "physical_write_bytes": beats * 512}.items():
        require(silu_delta[key] == value, "SiLU physical port accounting mismatch: " + key)
    with (destination_dir / "act_ddr_events.jsonl").open("wb") as trace:
        actual["act"], drain = execute_drain(model, owner, case, target, trace, deadline)
    driver.check_storage()
    require(all(word is not None for output in actual.values() for word in output), "incomplete actual outputs")
    require(not owner.tiles.leased and owner.tiles.idle, "tile leases remain after terminal drain")
    require(tile_check.bank_region_hash(owner.a_banks.words, 0, 768) == retained, "SiLU/drain changed retained A")
    for role, words in actual.items():
        (destination_dir / ("actual_" + role + ".f32le")).write_bytes(tile_check.wire_bytes(words))
    (destination_dir / "actual_act_full_ddr_with_canaries.bin").write_bytes(target.data)
    return {"case": case, "actual": actual, "directory": destination_dir.name, "windows": [gate, up], "drain": drain,
            "cross_command_spans_disjoint": [{"begin": begin, "end_exclusive": end, "region": region} for begin, end, region in spans],
            "actual_a_loaded_once_reused_without_ddr": True, "same_physical_a_banks_across_entire_chain": True,
            "retained_a_sha256_after_terminal_drain": retained,
            "silu": {"accepted_requests": beats, "port_counters": silu_delta,
                     "owner_external_tile_port": dict(external_tile.counts),
                     "arbitration_evidence_scope": "Every SiLU edge clocked the Python owner external tile interface; no Scala/RTL/SFU arbitration execution is claimed.",
                     "bank_event_sha256": driver.trace.hexdigest(), "phase_value_sha256": phase_hash.hexdigest(),
                     "host_phase_exception_flags": dict(phase_flags)},
            "host_wall_seconds": time.monotonic() - started,
            "host_fma_updates": {"physical_packet_arithmetic": 2 * K * (cols // 32) * 4096,
                                 "post_completion_independent_direct": 2 * rows * cols * K},
            "all_actual_ddr_writes_acks_and_terminal_completed_before_comparison": True}


def verify_capture_sources(report):
    current = {path: file_sha(ROOT / path) for path in report["source_sha256"]}
    report["source_sha256_after"] = current
    report["source_changed_since_freeze"] = [path for path, digest in current.items() if digest != report["source_sha256"][path]]
    require(not report["source_changed_since_freeze"], "source changed during frozen numerical capture")


def host_preflight():
    meminfo = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available_kib = int(meminfo["MemAvailable"].split()[0])
    require(available_kib >= 512 * 1024, "less than 512 MiB available before bounded host capture")
    result = {"available_memory_kib": available_kib,
              "process_max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "logical_cpu_count": os.cpu_count(), "load_average": list(os.getloadavg()),
              "cpu_affinity_count": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None}
    for name in ("memory.max", "memory.current", "cpu.max"):
        path = Path("/sys/fs/cgroup") / name
        if path.exists():
            result["cgroup_" + name] = path.read_text().strip()
    if result.get("cgroup_memory.max", "max") != "max":
        remaining = int(result["cgroup_memory.max"]) - int(result.get("cgroup_memory.current", "0"))
        require(remaining >= 384 * 1024 * 1024, "less than 384 MiB cgroup headroom before bounded host capture")
    return result


def run(out, only_rows=16):
    require(not out.exists(), "use a new evidence directory")
    out.mkdir(parents=True)
    start = time.monotonic()
    cpu_start = time.process_time()
    report = {"status": "PREPARING", "cases": []}
    def save():
        (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    try:
        require(sys.byteorder == "little", "explicit little-endian host required")
        report["host_resources_before"] = host_preflight()
        pins = load_pins()
        require(str((TASK / "model.py").relative_to(ROOT)) in pins["sources"], "drain model must be pinned before actual capture")
        origin = window_check.verify_provenance(pins)
        cases = [case for case in pins["default_cases"] if case["rows"] == only_rows]
        require(len(cases) == 1, "exactly one bounded case must be selected")
        inputs = {}
        for name, spec in pins["inputs"].items():
            inputs[name] = array("I" if name == "n1" else "H")
            inputs[name].frombytes(checked_file(spec))
        memory = SourceMemory(inputs)
        for spec in pins["comparison_only"].values():
            require((ROOT / spec["path"]).stat().st_size == spec["bytes"] and file_sha(ROOT / spec["path"]) == spec["sha256"],
                    "comparison-only file identity drift")
        source_paths = set(pins["sources"])
        source_paths.update(str((TASK / name).relative_to(ROOT)) for name in ("check_numeric.py", "precision_pins.json", "test_numeric.py"))
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
            origin=origin, pins=pins, source_sha256={path: sha(raw) for path, raw in {**sources, **composition_sources}.items()},
            source_composition_snapshot=composition,
            source_composition_snapshot_sha256={path: sha(raw) for path, raw in composition_sources.items()},
            source_composition_scope="Pre-run Scala composition snapshot only; this capture executes Python protocol models and unchanged C++ arithmetic.",
            source_to_ddr={"selection": "one immutable address-only n1/weight source map and disjoint sentinel act destination",
                "n1": {"base": SOURCE_BASES["n1"], "shape": [128, K], "dtype": "FP32 little-endian",
                       "conversion": "actual owner DDR/RMW ingress rounds to BF16 RNE in retained A"},
                "weights": {"raw_layout": "official output-major [N8960,K1536] BF16 little-endian",
                    "ddr_layout": "explicit virtual transpose [K1536,N8960] BF16 little-endian",
                    "materialization": "raw[n*K+k] serves DDR base+2*(k*8960+n); immutable address-only lazy mapping",
                    "bases": {role: SOURCE_BASES[role + "_weight"] for role in ("gate", "up")}},
                "act": {"base": ACT_BASE, "full_shape": [only_rows, SOURCE_N], "initial": "sentinel only",
                        "write_source": "accepted drain write_data into accepted descriptor address; no expected outputs"}},
            budget={"wall_seconds": WALL_BUDGET, "compile_timeout_seconds": 30, "estimated_memory_mib": 320,
                    "single_host_process": True, "full_projection_or_block_runs": 0, "rtl_or_eda_runs": 0},
            hardware_arithmetic_executed=False, rtl_executed=False, actual_idma=False,
            host_production_coordinator_executed=False, protocol_model_ticks_are_hardware_cycles=False,
            predicted_hardware_cycles=None, physical_resource_qor_established=False,
            native_m128_and_fp32_final_acceptance="UNCHANGED_FAIL_POLICY_PENDING")
        save()
        (out / "FROZEN_PINS.json").write_text(json.dumps(report, indent=2) + "\n")
        lib, report["compile"] = build_library(out, pins, frozen)
        base = frozen / TASK.relative_to(ROOT)
        model = load_module("ffn_drain_numeric_owner", base / "model.py")
        old_check = load_module("ffn_drain_frozen_window_numeric", base.parent / "ffn_window/check_numeric.py")
        tile_check = load_module("ffn_drain_frozen_tile_numeric", base.parent / "ffn_tiles/check_numeric.py")
        completed = [execute_case(model, old_check, tile_check, lib, memory, case, out, start + WALL_BUDGET) for case in cases]
        # Neither independent direct dot nor saved producer tensor decode is
        # reachable until act DDR writes, matching ACKs and terminal finish.
        ca = (C.c_uint32 * len(inputs["n1"])).from_buffer(inputs["n1"])
        for case_report in completed:
            actual = case_report.pop("actual")
            case = case_report["case"]
            count = case["rows"] * case["cols"]
            direct = {role: (C.c_uint32 * count)() for role in ("gate", "up", "act")}
            for role in ("gate", "up"):
                weights = (C.c_uint16 * len(inputs[role + "_weight"])).from_buffer(inputs[role + "_weight"])
                require(lib.fw_reference(ca, weights, direct[role], case["rows"], case["cols"], case["ng"]) == 0,
                        "independent direct dot failed")
            require(lib.sf_reference(direct["gate"], direct["up"], direct["act"], count) == 0, "independent direct SiLU failed")
            mismatches = {}
            for role in ("gate", "up", "act"):
                saved = array("I")
                saved.frombytes(checked_file(pins["comparison_only"][role]))
                saved_tile = tile_check.flat_tile(saved, case["rows"], case["cols"], case["ng"])
                mismatches[role] = {"independent_direct_bit_mismatches": sum(x != y for x, y in zip(actual[role], direct[role])),
                    "saved_producer_bit_mismatches": sum(x != y for x, y in zip(actual[role], saved_tile)),
                    "actual_sha256": sha(tile_check.wire_bytes(actual[role])), "direct_sha256": sha(bytes(direct[role])),
                    "saved_sha256": sha(tile_check.wire_bytes(saved_tile))}
                for name, expected in (("independent_direct", direct[role]), ("saved_producer", saved_tile)):
                    first = next((i for i, (x, y) in enumerate(zip(actual[role], expected)) if x != y), None)
                    mismatches[role][name + "_first_difference"] = None if first is None else {
                        "flat_index": first, "m": first // case["cols"], "source_n": case["ng"] + first % case["cols"],
                        "actual_fp32_bits": f"0x{actual[role][first]:08x}", "expected_fp32_bits": f"0x{expected[first]:08x}"}
            case_report["comparison"] = mismatches
            report["cases"].append(case_report)
            require(all(not item["independent_direct_bit_mismatches"] and not item["saved_producer_bit_mismatches"]
                        for item in mismatches.values()), "actual chain differs from independent or saved producer outputs")
        require(time.monotonic() < start + WALL_BUDGET, "bounded actual chain exceeded wall budget")
        require(all(sha(raw.tobytes()) == pins["inputs"][name]["sha256"] for name, raw in inputs.items()),
                "immutable raw source changed during execution/reference")
        verify_capture_sources(report)
        report.update(status="PASS_ACTUAL_N1_GATE_UP_SILU_ACT_DDR_ACK_HOST_MODEL_ONLY", wall_seconds=time.monotonic() - start,
            host_cpu_seconds=time.process_time() - cpu_start, host_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save()
        return report
    except Exception as error:
        if "source_sha256" in report:
            report["source_sha256_after"] = {path: file_sha(ROOT / path) if (ROOT / path).is_file() else None
                                              for path in report["source_sha256"]}
            report["source_changed_since_freeze"] = [path for path, digest in report["source_sha256"].items()
                                                      if report["source_sha256_after"][path] != digest]
        report.update(status="FAILED", error=str(error), wall_seconds=time.monotonic() - start,
                      host_cpu_seconds=time.process_time() - cpu_start)
        save()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only-rows", type=int, choices=(16, 128), default=16,
                        help="first prove M16/N32; M128/N160 is a separately authorized dependency gate")
    args = parser.parse_args()
    result = run(args.out.resolve(), args.only_rows)
    print(json.dumps({"status": result["status"], "cases": len(result["cases"]), "wall_seconds": result["wall_seconds"]}))

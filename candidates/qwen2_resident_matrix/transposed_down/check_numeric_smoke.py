#!/usr/bin/env python3
"""Bounded actual-input HOST-model M128/K8960 Down, N160 or full N1536.

The only arithmetic inputs are phase-12 activation and real Down weight data.
Accepted bank-model A/B packets drive five existing C++ physical banks. Every
group erases them; continuation requires accepted seed packets reread from
ACK-written DDR prefixes. Prefix DDR versions are checked before overwrite.
Independent direct-dot and saved phase-13 comparisons run after owner DONE.
This is host evidence only, not retained RTL, IDMA or a hardware FPU execution.
"""
import argparse
from array import array
from collections import Counter, deque
import ctypes as C
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
M, K, SOURCE_N, CHUNK = 128, 8960, 1536, 2560
CHUNKS = ((0, 2560), (2560, 5120), (5120, 7680), (7680, 8960))
INPUTS = {
    "activation": ("work/qwen2_fullgraph_dataflow_20261011/cold_m128/phase_12_act_recipe.f32le",
                   "6df9c46c3f76abcf6dc9646e234a01a0a3dd91c111070d5d8fbb7e701b08876d", M*K*4),
    "weight_output_major": ("work/qwen2_layer0_payload_20261011/mlp.down_proj.weight.bin",
                            "8a9657234cffb29cec816483e03454846d80d3a1f4171e6bc40479f3ba73ce5a", SOURCE_N*K*2),
}
COMPARISON = ("work/qwen2_fullgraph_dataflow_20261011/cold_m128/phase_13_down_recipe.f32le",
              "48c8e5509f94fa9dae7dc0e13ffd2811d4aabda518e3c1a64ed4d79e415c8af1", M*SOURCE_N*4)
RECEIPTS = {
    "payload_manifest": ("work/qwen2_layer0_payload_20261011/manifest.json",
                         "582f34afe5c52633f5290b5ba071f76164193f59d6edfc0d949658fd1e9715d1"),
    "fullgraph_prepared": ("work/qwen2_fullgraph_dataflow_20261011/PREPARED.json",
                           "15b5043a945589cb320319035eeba82a21cc2689fc91ca42ce6bf4b5894726cb"),
    "fullgraph_result": ("work/qwen2_fullgraph_dataflow_20261011/cold_m128/RESULT.json",
                         "30614529e641616bfb3fad7857301c4a34104d5b76be92f6c9417e4c387308ae"),
}
RECIPE_COMMIT = "825caff3a6c618419c49c7da452e009ce86ae8b5"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024*1024):
            digest.update(block)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def group_schedule(columns):
    """Expected chunk-major sweep, including the final partial N group."""
    require(columns in (160, SOURCE_N), "columns must be 160 or 1536")
    groups = []
    for chunk_index, (start, end) in enumerate(CHUNKS):
        for n_base in range(0, columns, 160):
            groups.append({"sequence": len(groups)+1, "chunk_index": chunk_index,
                           "start": start, "end": end, "n_base": n_base,
                           "contexts": min(5, (columns-n_base)//32)})
    return groups


def run(out, columns=160):
    expected_groups = group_schedule(columns)
    groups_per_sweep = (columns+159)//160
    require(not out.exists(), "use a new evidence directory")
    out.mkdir(parents=True)
    started = time.monotonic()
    report = {
        "status": "STARTED",
        "scope": f"ACTUAL_INPUT_DOWN_M128_K8960_N{columns}_FOUR_CHUNKS_HOST_MODEL_ONLY",
        "rtl_generated": False, "hardware_arithmetic_executed": False,
        "actual_idma": False, "matrix_latency_modeled": False,
        "full_projection_or_block_executed": False,
        "full_projection_executed": False, "full_block_executed": False,
        "planned_full_down_projection": columns == SOURCE_N,
        "native_m128_and_fp32_final_acceptance": "UNCHANGED_FAIL_POLICY_PENDING",
        "shape": {"m": M, "k": K, "n": columns, "source_n": SOURCE_N},
        "expected_groups": expected_groups,
        "chunks": [list(pair) for pair in CHUNKS], "bias": None,
        "budget": {"total_wall_seconds": 180, "compile_timeout_seconds": 30,
                   "host_fma_updates": 2*M*columns*K,
                   "retained_host_accumulator_bytes": 5*16*256*4,
                   "estimated_memory_mib": 192},
    }

    def save():
        (out/"summary.json").write_text(json.dumps(report, indent=2)+"\n")

    def check_budget():
        if time.monotonic()-started > report["budget"]["total_wall_seconds"]:
            raise TimeoutError("bounded numeric smoke exceeded 180 seconds")

    try:
        require(sys.byteorder == "little", "explicit little-endian host required")
        data, receipts = {}, {}
        report["input_pins"], report["provenance_receipts"] = {}, {}
        for name, (path, digest, size) in INPUTS.items():
            raw = (ROOT/path).read_bytes()
            require(len(raw) == size and sha(raw) == digest, "frozen input identity drift: "+path)
            data[name] = raw
            report["input_pins"][name] = {"path": path, "sha256": digest, "bytes": size}
        # Hash comparison bytes before execution without retaining/decoding any
        # golden values. They cannot supply any Matrix result or seed packet.
        path, digest, size = COMPARISON
        require((ROOT/path).stat().st_size == size and file_sha(ROOT/path) == digest,
                "frozen phase-13 comparison identity drift")
        report["comparison_pin"] = {"path": path, "sha256": digest, "bytes": size,
                                    "use": "decode only after owner final ACK and response"}
        for name, (path, digest) in RECEIPTS.items():
            raw = (ROOT/path).read_bytes()
            require(sha(raw) == digest, "frozen provenance receipt drift: "+path)
            receipts[name] = json.loads(raw)
            report["provenance_receipts"][name] = {"path": path, "sha256": digest}
        manifest = receipts["payload_manifest"]
        down = [entry for entry in manifest["tensors"] if entry["local_name"] == "mlp.down_proj.weight"]
        require(len(down) == 1 and down[0]["shape"] == [SOURCE_N, K] and
                down[0]["dtype"] == "BF16" and down[0]["sha256"] == INPUTS["weight_output_major"][1],
                "actual Down tensor provenance/shape mismatch")
        require(not any(entry["local_name"] == "mlp.down_proj.bias" for entry in manifest["tensors"]),
                "unexpected actual Down bias requires explicit implementation")
        result, prepared = receipts["fullgraph_result"], receipts["fullgraph_prepared"]
        require(result["tokens"] == M and result["all_15_stages_bit_exact"] and
                result["prepared_sha256"] == RECEIPTS["fullgraph_prepared"][1] and
                result["arena_sha256"] == prepared["arena"]["sha256"], "fullgraph receipt chain mismatch")
        for phase, width, pin in ((12, K, INPUTS["activation"]), (13, SOURCE_N, COMPARISON)):
            entry = next(entry for entry in result["stages"] if entry["phase"] == phase)
            require(entry["width"] == width and entry["sha256"] == pin[1] and
                    entry["path"] == Path(pin[0]).name, "fullgraph stage provenance mismatch")
        report["payload_origin"] = {"model_id": manifest["model_id"], "revision": manifest["revision"],
                                    "layer_id": manifest["layer_id"], "down_tensor": down[0],
                                    "official_framework_forward": False}
        recipe = subprocess.check_output(
            ["git", "show", RECIPE_COMMIT+":chisel/continuous_prefill/tests/qwen2_block.cpp"], cwd=ROOT)
        cpp = (TASK/"numeric_smoke.cpp").read_text()
        for name in ("bits", "fp", "bf"):
            line = next(line for line in recipe.decode().splitlines() if line.startswith("static ") and " "+name+"(" in line)
            require(line in cpp, "original recipe helper changed: "+name)
        require("dense(OFF_ACT,OFF_WD,OFF_DOWN,F,H)" in recipe.decode(), "original Down call changed")
        report["recipe_source"] = {"commit": RECIPE_COMMIT, "sha256": sha(recipe),
                                   "reduction": "increasing global K; BF16 RNE activation; std::fma(float,float,float); +0 initial; no bias"}
        composition_raw = (TASK/"source_pins.json").read_bytes()
        composition = json.loads(composition_raw)
        patch_pins = composition["patches"]
        down_patch = str((TASK/"owner_down.patch").relative_to(ROOT))
        require(down_patch in patch_pins, "source composition does not bind owner_down.patch")
        patch_data = {}
        for path, digest in patch_pins.items():
            require((ROOT/path).resolve().is_relative_to(ROOT), "patch is outside repository")
            raw = (ROOT/path).read_bytes()
            require(sha(raw) == digest, "source composition patch drift: "+path)
            patch_data[path] = raw
        report["source_composition"] = {
            "source_pins": {"path": str((TASK/"source_pins.json").relative_to(ROOT)),
                            "sha256": sha(composition_raw)},
            "owner_down_patch": {"path": down_patch, "sha256": patch_pins[down_patch]},
            "validated_patch_sha256": patch_pins,
            "scope": "source composition identity only; Python owner is not Scala or RTL simulation",
        }
        report["source_sha256"] = {name: sha((TASK/name).read_bytes()) for name in
                                   ("numeric_smoke.cpp", "check_numeric_smoke.py", "model.py",
                                    "source_pins.json", "owner_down.patch")}
        require(report["source_sha256"]["source_pins.json"] == sha(composition_raw) and
                report["source_sha256"]["owner_down.patch"] == patch_pins[down_patch],
                "source composition changed while pinning")
        snapshot = out/"source"
        snapshot.mkdir()
        for name, digest in report["source_sha256"].items():
            raw = (TASK/name).read_bytes()
            require(sha(raw) == digest, "source changed before capture")
            (snapshot/name).write_bytes(raw)
        for path, raw in patch_data.items():
            target = snapshot/"patches"/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        del patch_data
        # Persist provenance, exact source hashes and the budget BEFORE compile,
        # derived-layout conversion, owner execution, or reference arithmetic.
        report["status"] = "PINNED_BEFORE_EXECUTION"
        save()
        (out/"pre_run_pins.json").write_text(json.dumps(report, indent=2)+"\n")
        library = out/"numeric_smoke.so"
        argv = ["g++", "-std=c++17", "-O2", "-fno-fast-math", "-ffp-contract=off", "-fPIC", "-shared",
                str(snapshot/"numeric_smoke.cpp"), "-o", str(library)]
        with (out/"compile.log").open("w") as log:
            subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=report["budget"]["compile_timeout_seconds"])
        report["compile"] = {"argv": argv, "binary_sha256": sha(library.read_bytes()),
                             "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0]}
        spec = importlib.util.spec_from_file_location("down_numeric_owner_model", snapshot/"model.py")
        model = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = model
        spec.loader.exec_module(model)
        lib = C.CDLL(str(library))
        u16, u32 = C.POINTER(C.c_uint16), C.POINTER(C.c_uint32)
        lib.td_reset.argtypes, lib.td_reset.restype = [], C.c_int
        lib.td_group.argtypes, lib.td_group.restype = [C.c_uint]*3, C.c_int
        lib.td_seed_begin.argtypes, lib.td_seed_begin.restype = [C.c_uint], C.c_int
        lib.td_seed_beat.argtypes, lib.td_seed_beat.restype = [C.c_uint, C.c_uint, u32], C.c_int
        lib.td_seed_commit.argtypes, lib.td_seed_commit.restype = [C.c_uint], C.c_int
        lib.td_step.argtypes, lib.td_step.restype = [C.c_uint]*6+[u16, u16, u32], C.c_int
        lib.td_reference.argtypes, lib.td_reference.restype = [u32, u16, u32, C.c_uint], C.c_int
        require(lib.td_reset() == 0, "cannot establish FE_TONEAREST")
        raw_a, raw_w = array("I"), array("H")
        raw_a.frombytes(data["activation"])
        raw_w.frombytes(data["weight_output_major"])
        del data
        weight = array("H", (raw_w[n*K+k] for k in range(K) for n in range(columns)))
        report["derived_weight"] = {"shape": [K, columns], "layout": f"K-major N{columns}; source output columns [0,{columns})",
                                    "source_row_stride": K, "job_row_stride": columns, "sha256": sha(weight.tobytes())}
        save()
        job = model.Job(m=M, k=K, n=columns, activation_bf16=False, weight_bf16=True, output_bf16=False,
                        a=0x1000000, b=0x2000000, dst=0x8000000, tag=0x444f574e, write_bytes=M*columns*4)
        workspace = model.PrefixWorkspace(0x10000000, (columns//32)*16384, 1, CHUNK)
        owner = model.DenseOwnerModel(workspace)
        owner.tick(job=job)
        operand_a, operand_b = (C.c_uint16*16)(), (C.c_uint16*256)()
        physical, seed_words = (C.c_uint32*4096)(), (C.c_uint32*16)()
        pending_read = pending_write = pending_ack = seed_ack = None
        results, staged = deque(), []
        destination, written = array("I", [0x7fc00001]*(M*columns)), set()
        prefix, read_versions, seeded_versions = {}, Counter(), Counter()
        prefix_writes, prefix_reads, seed_counts = Counter(), Counter(), Counter()
        seed_commits, matrix_done_groups, groups = set(), set(), []
        step_trace, seed_trace, transaction_trace = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
        seed_capture = bytearray()
        transactions = bytearray()
        counts = Counter()
        finished, result_peak = None, 0

        def transaction(kind, address, version, words, old_version=None):
            event = {"tick": owner.clock, "kind": kind, "address": address, "version": version,
                     "payload_sha256": sha(struct.pack("<16I", *words))}
            if old_version is not None:
                event["overwritten_version"] = old_version
            record = (json.dumps(event, sort_keys=True, separators=(",", ":"))+"\n").encode()
            transactions.extend(record)
            transaction_trace.update(record)

        while finished is None:
            check_budget()
            ports = owner.ports()
            kwargs = {"step_ready": not (ports["step"] is not None and ports["step"].last and len(results) >= 2)}
            chunk_index, chunk_start, chunk_end = owner.chunk_index, owner.chunk_start, owner.chunk_end
            n_base, group_sequence = owner.n_base, owner.group_sequence
            contexts = getattr(owner, "contexts", 0)
            if pending_read is not None:
                command, version, words = pending_read
                if command.kind == "prefix":
                    require(owner.prefix_valid and owner.committed_prefix_end == chunk_start and
                            owner.completed_prefix_sweeps == chunk_index, "restore before complete prior prefix sweep")
                    require(prefix[command.address] == (version, words) and version == chunk_index,
                            "prefix version changed between read acceptance and response")
                kwargs["read_beat"] = model.ReadBeat(command.tag, words, True)
            if results:
                kwargs["result"] = results[0]
            if (owner.group_started and not owner.group_done and
                    owner.group_accepted_steps == (chunk_end-chunk_start)*contexts and
                    owner.results_received == contexts and not results):
                kwargs["matrix_done"] = model.MatrixDone(job.tag)
            if pending_ack is not None:
                kwargs["write_ack"] = pending_ack
            if seed_ack is not None:
                kwargs["seed_ack"] = seed_ack
            edge = owner.tick(**kwargs)
            if edge["group_fire"]:
                observed = {"sequence": group_sequence, "chunk_index": chunk_index, "start": chunk_start,
                            "end": chunk_end, "n_base": n_base, "contexts": contexts}
                require(len(groups) < len(expected_groups) and observed == expected_groups[len(groups)],
                        "unexpected chunk-major group sequence/context count")
                require(matrix_done_groups == set(range(1, group_sequence)), "group started before prior MatrixDone")
                if chunk_index < len(CHUNKS)-1:
                    require(prefix_writes[chunk_index+1] == n_base//32*256,
                            "group began before every previous group prefix ACK")
                else:
                    require(len(written) == M*n_base, "group began before every previous group final ACK")
                if chunk_index and n_base == 0:
                    require(group_sequence == chunk_index*groups_per_sweep+1 and
                            prefix_writes[chunk_index] == columns//32*256 and
                            len(prefix) == columns//32*256 and all(version == chunk_index for version, _ in prefix.values()),
                            "next chunk began before all previous sweep writes ACKed and MatrixDone")
                    raw = b"".join(struct.pack("<16I", *prefix[address][1]) for address in sorted(prefix))
                    (out/f"acknowledged_prefix_{chunk_index}_physical.f32le").write_bytes(raw)
                require(lib.td_group(chunk_start, chunk_end, contexts) == 0, "host group setup")
                groups.append({"sequence": group_sequence, "chunk_index": chunk_index, "start": chunk_start,
                               "end": chunk_end, "n_base": n_base, "contexts": contexts, "start_tick": owner.clock})
            if edge["seed_begin_fire"]:
                request = edge["seed_begin"]
                require(chunk_index > 0 and request.tag == job.tag and request.sequence == group_sequence and
                        request.generation == workspace.generation and request.context < contexts,
                        "seed request identity mismatch")
                require(lib.td_seed_begin(request.context) == 0, "host seed reserve")
            if edge["seed_beat_fire"]:
                beat = edge["seed_beat"]
                address = workspace.base+(n_base//32+beat.request.context)*16384+model.prefix_ddr_beat(beat.index)*64
                version, words = prefix[address]
                require(version == chunk_index and tuple(beat.words) == words and read_versions[address, version] == 1,
                        "seed is not the exact accepted reread of its ACK-written prefix version")
                require(seeded_versions[address, version] == 0, "duplicate prefix seed version")
                seeded_versions[address, version] += 1
                seed_counts[version] += 1
                seed_words[:] = beat.words
                record = struct.pack("<IIIBBBB16I", beat.request.tag, beat.request.sequence, beat.request.generation,
                                     beat.request.context, beat.index, beat.last, 0, *beat.words)
                seed_capture.extend(record)
                seed_trace.update(record)
                require(lib.td_seed_beat(beat.request.context, beat.index, seed_words) == 0, "host seed write")
                if beat.last:
                    require(lib.td_seed_commit(beat.request.context) == 0, "host seed commit")
                    seed_ack = model.SeedAck(beat.request)
            if edge["seed_ack_fire"]:
                seed_commits.add((chunk_index, n_base//32+seed_ack.request.context))
                seed_ack = None
                counts["seed_acks"] += 1
            if edge["read_fire"]:
                command, version, words = pending_read
                if command.kind == "prefix":
                    require(read_versions[command.address, version] == 0, "duplicate prefix version reread")
                    read_versions[command.address, version] += 1
                    prefix_reads[version] += 1
                    transaction("read", command.address, version, words)
                pending_read = None
            if edge["read_command_fire"]:
                require(pending_read is None, "read descriptors overlap")
                command = edge["read_command"]
                require(command.beats == 1 and command.address % 64 == 0, "unexpected input read shape/alignment")
                if command.kind == "prefix":
                    require(command.address in prefix, "prefix was never ACK-written")
                    version, words = prefix[command.address]
                    require(version == chunk_index and prefix_writes[version] == columns//32*256,
                            "read stale or incompletely written prefix sweep")
                else:
                    require(command.kind in ("a", "b"), "unknown input source")
                    source, base, size = (raw_a, job.a, 4) if command.kind == "a" else (weight, job.b, 2)
                    offset = (command.address-base)//size
                    require(command.address >= base and offset+64//size <= len(source), "input descriptor outside full tensor stride")
                    words, version = tuple(source[offset:offset+64//size]), None
                pending_read = (command, version, words)
                counts["read_descriptors"] += 1
                counts[command.kind+"_read_descriptors"] += 1
            if edge["step_fire"]:
                step = edge["step"]
                require(chunk_start <= step.k < chunk_end and step.clear == (step.k == 0), "global K/clear semantics")
                operand_a[:], operand_b[:] = step.a, step.b
                step_trace.update(struct.pack("<IIHBBBBBB", group_sequence, n_base, step.k, step.context,
                                              step.clear, step.last, step.finish, step.emit, 0))
                step_trace.update(bytes(operand_a))
                step_trace.update(bytes(operand_b))
                returned = lib.td_step(step.k, step.context, step.clear, step.last, step.finish, step.emit,
                                       operand_a, operand_b, physical)
                require(returned >= 0 and bool(returned) == step.last, "accepted-step FMA protocol/finite error")
                counts["accepted_steps"] += 1
                if returned:
                    tile = tuple(tuple(physical[r*256+c] for c in range(256)) for r in range(16))
                    results.append(model.MatrixResult(step.context, tile))
                    result_peak = max(result_peak, len(results))
            if edge["result_fire"]:
                results.popleft()
                counts["accepted_results"] += 1
            if edge["write_command_fire"]:
                require(pending_write is None, "write descriptors overlap")
                pending_write = (edge["write_command"], 0, chunk_index)
                staged = []
            if edge["write_data_fire"]:
                require(pending_write is not None, "write data without descriptor")
                command, index, write_chunk = pending_write
                packet = edge["write_data"]
                require(len(packet.words) == 16 and packet.last == (index+1 == command.beats), "write beat width/LAST")
                staged.append((command.address+64*index, tuple(packet.words)))
                counts["write_data_beats"] += 1
                pending_write = (command, index+1, write_chunk)
                if packet.last:
                    pending_ack = model.WriteAck(command.tag, nbytes=64*command.beats)
            if edge["write_ack_fire"]:
                command, index, write_chunk = pending_write
                require(index == command.beats and len(staged) == command.beats, "ACK before complete staged write")
                for address, words in staged:
                    if workspace.base <= address < workspace.base+workspace.extent:
                        version = write_chunk+1
                        require(version in (1, 2, 3), "final chunk attempted prefix save")
                        old = prefix.get(address)
                        if version == 1:
                            require(old is None, "duplicate initial prefix ACK store")
                        else:
                            require(old is not None and old[0] == version-1 and
                                    read_versions[address, old[0]] == 1 and seeded_versions[address, old[0]] == 1 and
                                    (write_chunk, (address-workspace.base)//16384) in seed_commits,
                                    "prefix overwrite before exact old version reread and seed ACK")
                        prefix[address] = (version, words)
                        prefix_writes[version] += 1
                        transaction("ack_write", address, version, words, old[0] if old else None)
                    else:
                        require(write_chunk == 3 and address >= job.dst, "final output published before last chunk")
                        first = (address-job.dst)//4
                        for i, value in enumerate(words):
                            require(0 <= first+i < len(destination) and first+i not in written,
                                    "duplicate/out-of-bounds final store")
                            destination[first+i] = value
                            written.add(first+i)
                staged, pending_ack, pending_write = [], None, None
                counts["write_acks"] += 1
            if "matrix_done" in kwargs and edge["matrix_done_ready"]:
                require(group_sequence not in matrix_done_groups, "duplicate MatrixDone")
                matrix_done_groups.add(group_sequence)
            if edge["response_fire"]:
                finished = edge["response"]
            require(not owner.error, "clocked owner failed: "+str(owner.error))

        require(finished == (job.tag, None, M*columns*4) and len(written) == M*columns and
                counts["accepted_steps"] == K*(columns//32), "terminal/count/output completeness mismatch")
        require(not (pending_read or pending_write or pending_ack or results or staged or seed_ack),
                "completion with outstanding external obligation")
        require(len(groups) == len(expected_groups) and
                matrix_done_groups == set(range(1, len(expected_groups)+1)) and
                owner.completed_prefix_sweeps == 3 and owner.committed_prefix_end == 7680,
                "incomplete chunk/sweep completion")
        require(owner.prefix_bytes == 3*(columns//32)*16384 and counts["seed_acks"] == 3*(columns//32),
                "prefix ACK byte/seed ACK total mismatch")
        for version in (1, 2, 3):
            require(prefix_writes[version] == prefix_reads[version] == seed_counts[version] == (columns//32)*256,
                    "incomplete exact-version write/read/seed sweep")
        require(counts["a_read_descriptors"] == M*K//16 and counts["b_read_descriptors"] == K*columns//32 and
                owner.rmw_commits == M*K, "actual operand traffic/completeness mismatch")
        # No reference function or saved phase-13 decoding occurs until here.
        report["owner_completed_before_comparison"] = True
        report["full_projection_executed"] = columns == SOURCE_N
        report["full_projection_or_block_executed"] = columns == SOURCE_N
        report["owner_completion_tick"] = owner.clock
        (out/"acknowledged_dense.f32le").write_bytes(destination.tobytes())
        reference = (C.c_uint32*(M*columns))()
        ca = (C.c_uint32*len(raw_a)).from_buffer(raw_a)
        cw = (C.c_uint16*len(raw_w)).from_buffer(raw_w)
        check_budget()
        require(lib.td_reference(ca, cw, reference, columns) == 0, "nonfinite independent comparison")
        independent_mismatches = sum(value != reference[i] for i, value in enumerate(destination))
        comparison_path, comparison_digest, comparison_size = COMPARISON
        raw_comparison = (ROOT/comparison_path).read_bytes()
        require(len(raw_comparison) == comparison_size and sha(raw_comparison) == comparison_digest,
                "saved phase-13 changed after pre-run pins")
        saved = array("I")
        saved.frombytes(raw_comparison)
        saved_slice = array("I", (saved[m*SOURCE_N+n] for m in range(M) for n in range(columns)))
        saved_mismatches = sum(value != saved_slice[i] for i, value in enumerate(destination))
        (out/"independent_down.f32le").write_bytes(bytes(reference))
        (out/"saved_phase13_comparison_slice.f32le").write_bytes(saved_slice.tobytes())
        (out/"accepted_seed_records.bin").write_bytes(seed_capture)
        (out/"prefix_transactions.jsonl").write_bytes(transactions)
        report.update(dict(counts), groups=groups, completed_prefix_sweeps=owner.completed_prefix_sweeps,
                      host_fma_per_path=M*columns*K, prefix_ack_bytes=owner.prefix_bytes,
                      prefix_ack_beats=sum(prefix_writes.values()), prefix_read_beats=sum(prefix_reads.values()),
                      seed_beats=sum(seed_counts.values()), prefix_versions={str(v): {
                          "ack_beats": prefix_writes[v], "read_beats": prefix_reads[v], "seed_beats": seed_counts[v]
                      } for v in (1, 2, 3)}, exact_version_read_before_overwrite=True,
                      same_five_host_banks_erased_at_every_group=True,
                      accepted_step_trace_sha256=step_trace.hexdigest(), seed_trace_sha256=seed_trace.hexdigest(),
                      prefix_transaction_trace_sha256=transaction_trace.hexdigest(),
                      seed_record_format="<IIIBBBB16I", seed_record_bytes=80,
                      seed_record_sha256=sha(seed_capture), logical_output_cells=len(written),
                      acknowledged_bytes=finished[2], independent_down_bit_mismatches=independent_mismatches,
                      saved_phase13_bit_mismatches=saved_mismatches, protocol_model_ticks=owner.clock,
                      protocol_model_ticks_are_hardware_cycles=False, operand_reservation_peak=owner.max_reserved,
                      physical_result_fifo_peak=result_peak,
                      output_sha256={path.name: file_sha(path) for path in out.glob("*.f32le")},
                      wall_seconds=time.monotonic()-started)
        require(not independent_mismatches and not saved_mismatches, "numeric comparison failed")
        for name, digest in report["source_sha256"].items():
            require(sha((TASK/name).read_bytes()) == digest, "source changed during numeric run")
        for path, digest in patch_pins.items():
            require(file_sha(ROOT/path) == digest, "source composition patch changed during numeric run: "+path)
        check_budget()
        report["status"] = "PASS_ACTUAL_DOWN_FOUR_CHUNK_PREFIX_HOST_MODEL_ONLY"
        save()
        return report
    except Exception as error:
        report.update(status="FAILED", error=str(error), wall_seconds=time.monotonic()-started)
        save()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--columns", type=int, choices=(160, SOURCE_N), default=160,
                        help="execute the N160 slice (default) or all 1536 Down output columns")
    args = parser.parse_args()
    result = run(args.out.resolve(), columns=args.columns)
    print(json.dumps({"status": result["status"], "wall_seconds": result["wall_seconds"]}))

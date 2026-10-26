#!/usr/bin/env python3
"""Capture original BF16 embedding -> GDN0/1/2 -> complete L3, without a gate.

Source-only import and manifest validation need only Python's standard library.
Actual capture must be scheduled separately in the pinned isolated runtime.
M16 uses fixture slices 0:16 and 128:144. Its actual cache is 0 -> 16 -> 32,
while explicit RoPE positions remain 0:16 and 128:144. This is not M128 evidence.
No candidate owner, independent reference, comparison, build, or EDA is invoked.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import struct
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
SCOPE = "PINNED_OFFICIAL_BF16_PREFIX_THROUGH_L3_CAPTURE_ONLY"
CONTRACT = "config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json"
CONTRACT_SHA256 = "13b52da81746346f62c6a2f28cc1d6fa565989bd71d834dd4951ee2056355d97"
ARCHIVE_SHA256 = "15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d"
TORCH_GIT_VERSION = "449b1768410104d3ed79d3bcfe4ba1d65c7f22c0"
OFFICIAL_SOURCES = {
    "modeling": "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18",
    "cache": "abdcb0ae88aa5b924ef7d76879db680e9af8f3ec1dafbba7ce446ecb521a944b",
    "masking": "af3d84dfe82a0b57c40625c89fb32b2cd6bf7351432ee5e76a9e8eac4289575b",
    "activations": "5b20c0a3625edc0001a98f09ce3c6b5baa1100e1d7ad8dee649e4d45c8468665",
    "configuration": "2f26c4bb911772d42a5f16e82bdea4b9ba1ac07872df527ec228622d35f3c30e",
}
VARIANTS = {"baseline": ("default", "DEFAULT"), "avx2": ("avx2", "AVX2")}
WIDTHS = {"BF16": 2, "F32": 4, "I64": 8, "BOOL": 1}
MODEL_ID = "Qwen/Qwen3.5-0.8B"
REVISION = "2fc06364715b967f1860aea9cf38778875588b17"
FRAMEWORK_REVISION = "14e738b5d0cc69aa27a95dde272aea41fde44f2f"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"


def file_record(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=sha(raw))


def validate_tensor_record(record, directory=None):
    """Existing raw tensor manifest convention, with explicit integer metadata."""
    require(type(record) is dict, "tensor record must be an object")
    shape, dtype = record.get("shape"), record.get("dtype")
    require(type(shape) is list and all(type(n) is int and n > 0 for n in shape), "invalid tensor shape")
    require(type(dtype) is str and dtype in WIDTHS, "unsupported tensor storage dtype")
    require(type(record.get("bytes")) is int and record["bytes"] == math.prod(shape) * WIDTHS[dtype],
            "tensor shape/dtype byte count mismatch")
    filename = record.get("file")
    require(type(filename) is str and filename not in ("", ".", "..") and Path(filename).name == filename,
            "tensor path escape")
    digest = record.get("sha256")
    require(type(digest) is str and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
            "invalid tensor digest")
    if directory is not None:
        path = Path(directory) / filename
        require(not path.is_symlink() and path.is_file() and path.resolve().parent == Path(directory).resolve(),
                "tensor path escape or missing file")
        raw = path.read_bytes()
        require(len(raw) == record["bytes"] and sha(raw) == digest, "tensor bytes/hash mismatch")
        if dtype in ("BF16", "F32"):
            fmt, exponent = ("<H", 0x7F80) if dtype == "BF16" else ("<I", 0x7F800000)
            require(all(bits & exponent != exponent for (bits,) in struct.iter_unpack(fmt, raw)),
                    "nonfinite captured tensor")
        if dtype == "BOOL":
            require(all(b in (0, 1) for b in raw), "invalid boolean encoding")
    return record


def write_durable(path, data, mode="xb"):
    """Complete and fsync a new artifact, or one append, before returning."""
    with Path(path).open(mode) as stream:
        require(stream.write(data) == len(data), "incomplete artifact write")
        stream.flush()
        os.fsync(stream.fileno())


class TensorJournal:
    """Append one raw index entry after its file is fully written and fsynced.

    A process kill between these two commits can leave an unindexed raw file.
    Recovery never invents its key/shape or resumes a model from partial data.
    A newline commits an index record; an unterminated final line is ignored.
    """
    filename = "tensor_index.jsonl"

    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / self.filename
        self.keys, self.files = set(), set()
        write_durable(self.path, b"")

    def persist(self, key, record, data):
        require(type(key) is str and bool(key) and key not in self.keys, "duplicate/conflicting tensor journal key")
        validate_tensor_record(record)
        require(record["file"] not in self.files, "duplicate tensor journal file")
        require(len(data) == record["bytes"] and sha(data) == record["sha256"], "journal raw bytes/hash mismatch")
        line = json.dumps(dict(key=key, **record), sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        write_durable(self.directory / record["file"], data)
        write_durable(self.path, line, "ab")
        self.keys.add(key)
        self.files.add(record["file"])


def recover_tensor_journal(directory, *, verify_files=True):
    """Read completed entries only; partial evidence is not a success manifest.

    Ignore only the last line lacking a newline, even if its JSON is complete.
    Reject malformed complete lines, duplicate keys/files, and altered files.
    This is read-only and never repairs, deletes, resumes, or fabricates data.
    """
    directory = Path(directory)
    path = directory / TensorJournal.filename
    require(not path.is_symlink() and path.is_file(), "missing or symlinked tensor journal")
    tensors, files, tail = {}, set(), 0
    with path.open("rb") as stream:
        for line in stream:
            if not line.endswith(b"\n"):
                tail = len(line)
                break
            try:
                entry = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("malformed completed tensor journal line") from exc
            require(type(entry) is dict and set(entry) == {"key", "shape", "dtype", "bytes", "sha256", "file"},
                    "invalid tensor journal fields")
            key = entry.pop("key")
            require(type(key) is str and bool(key) and key not in tensors, "duplicate/conflicting tensor journal key")
            validate_tensor_record(entry, directory if verify_files else None)
            require(entry["file"] not in files, "duplicate tensor journal file")
            tensors[key] = entry
            files.add(entry["file"])
    return dict(tensors=tensors, completed_records=len(tensors), ignored_unterminated_tail_bytes=tail,
                partial_evidence_only=True, model_resume_supported=False)


def write_failure_receipt(output, exc, *, m, start, runner_at_start):
    """Ordinary-exception evidence only; SIGKILL/CPU hard kills cannot run this."""
    output = Path(output)
    evidence = {name: file_record(output / name) for name in
                (TensorJournal.filename, "capture_start.json", "verified_source_identity.json") if (output / name).is_file()}
    report = dict(status="FAILED_NATIVE_CAPTURE", query_tokens=m,
        exception_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc(),
        elapsed_seconds=time.monotonic() - start, runner_at_start=runner_at_start, runner_at_failure=file_record(__file__),
        persisted_evidence=evidence, partial_outputs_preserved=True, numerical_acceptance_relaxed=False,
        partial_evidence_is_success=False, process_completion_requires_external_supervision=True)
    write_durable(output / "failure.json", encoded(report))
    return report


def validate_manifest(manifest, directory=None):
    """Validate capture integrity only. This deliberately awards no quality PASS."""
    require(type(manifest) is dict and type(manifest.get("schema_version")) is int and
            manifest["schema_version"] == 1 and manifest.get("scope") == SCOPE, "capture manifest identity drift")
    require((manifest.get("model_id"), manifest.get("revision"), manifest.get("framework_revision")) ==
            (MODEL_ID, REVISION, FRAMEWORK_REVISION), "checkpoint/framework identity drift")
    m = manifest.get("query_tokens")
    require(type(m) is int and m in (16, 128), "unsupported capture length")
    identity = "cold128_then_carried128" if m == 128 else "cold16_then_carried16_from_second_window"
    require(manifest.get("case_identity") == identity, "capture case identity drift")
    require(manifest.get("status") == "CAPTURED_OFFICIAL_SOFTWARE_REFERENCE_ONLY", "capture status overclaim")
    for key in ("hardware_executed", "owner_executed", "official_full_model_executed",
                "numerical_comparison_performed", "numerical_acceptance_gate_added", "previous_fp32_gate_replaced"):
        require(manifest.get(key) is False, "capture scope overclaim: " + key)
    require(manifest.get("official_TextModel_prefix_executed") is True, "original prefix execution missing")
    require(manifest.get("contract_sha256") == CONTRACT_SHA256, "original BF16 contract drift")
    require(manifest.get("official_source_sha256") == OFFICIAL_SOURCES, "official source identity drift")
    tensors = manifest.get("tensors")
    require(type(tensors) is dict and tensors, "missing captured tensors")
    for key, record in tensors.items():
        require(type(key) is str and key, "invalid tensor key")
        validate_tensor_record(record, directory)
    require(len({r["file"] for r in tensors.values()}) == len(tensors), "duplicate captured tensor file")

    def tensor(key, shape, dtype):
        require(key in tensors and tensors[key]["shape"] == shape and tensors[key]["dtype"] == dtype,
                "boundary shape/dtype drift: " + str(key))

    def same(a, b):
        require(a in tensors and b in tensors and all(tensors[a][k] == tensors[b][k] for k in
                ("shape", "dtype", "bytes", "sha256")), "activation/cache continuity drift")

    def references(value):
        if isinstance(value, list):
            for item in value:
                references(item)
        elif isinstance(value, dict):
            if "tensor" in value:
                require(set(value) == {"tensor"} and value["tensor"] in tensors, "dangling observed tensor reference")
            elif "parameter" in value:
                require(set(value) == {"parameter"} and value["parameter"] in manifest.get("parameters", {}),
                        "dangling observed parameter reference")
            else:
                for item in value.values():
                    references(item)

    cases = manifest.get("cases")
    require(type(cases) is list and len(cases) == 2, "two actual cache calls required")
    for i, case in enumerate(cases):
        require(type(case.get("past_tokens")) is int and case["past_tokens"] == i * m and
                type(case.get("final_tokens")) is int and case["final_tokens"] == (i + 1) * m,
                "actual cache length drift")
        require(case.get("source_token_slice") == [128 * i, 128 * i + m] and
                case.get("position_span") == [128 * i, 128 * i + m], "original fixture/position span drift")
        require(type(case.get("cache_object_id")) is int and case["cache_object_id"] == cases[0].get("cache_object_id"),
                "same actual DynamicCache object required")
        tensor(case.get("token_ids"), [1, m], "I64")
        tensor(case.get("position_ids"), [1, m], "I64")
        tensor(case.get("rope_position_ids"), [3, 1, m], "I64")
        tensor(case.get("attention_mask"), [1, 1, m, (i + 1) * m], "BF16")
        for name in ("rope_cos", "rope_sin"):
            tensor(case.get(name), [1, m, 64], "BF16")
        tensor(case.get("embedding"), [1, m, 1024], "BF16")
        layers = case.get("layers")
        require(type(layers) is list and [r.get("layer") for r in layers] == list(range(4)), "prefix layer order drift")
        previous = case["embedding"]
        for layer in layers:
            for name in ("input", "output"):
                tensor(layer.get(name), [1, m, 1024], "BF16")
            same(previous, layer["input"])
            previous = layer["output"]
        same(case.get("input"), layers[3]["input"])
        same(case.get("output"), layers[3]["output"])
        for j in range(4):
            prior, final = case["prior_cache"][str(j)], case["final_cache"][str(j)]
            specs = (("conv_state", [1, 6144, 4], "BF16"), ("recurrent_state", [1, 16, 128, 128], "F32")) if j < 3 else (
                ("key", [1, 2, (i + 1) * m, 256], "BF16"), ("value", [1, 2, (i + 1) * m, 256], "BF16"))
            for name, shape, dtype in specs:
                tensor(final.get(name), shape, dtype)
                if i == 0:
                    require(prior.get(name) is None, "cold cache must be absent")
                else:
                    same(prior.get(name), cases[0]["final_cache"][str(j)][name])
            if j == 3:
                for name in ("key", "value"):
                    if i:
                        same(case["retained_kv_prefix"][name], prior[name])
        require(case.get("mask_uses_actual_cache_length") is True and case.get("packed_q_gate_split_verified") is True,
                "unverified mask or packed Q/gate boundary")
        require(case.get("official_function_counts") == {"rope": 1, "eager": 1, "attention": 1, "chunk": 3, "norm": 4, "norm_core": 4},
                "original function observation missing")
        require(type(case.get("dispatch_events")) is list and case["dispatch_events"], "missing actual L3 ATen boundaries")
        references(case["dispatch_events"])
        references(case.get("module_boundaries", {}))
        references(case.get("function_observations", []))
    return manifest


def configure_budget(variant):
    """One CPU; equal 120-second CPU limits and an interpreter-serviced alarm.

    The CPU hard limit can terminate without a failure receipt. SIGALRM may be
    delayed by native calls; external supervision must enforce strict wall/RSS
    limits and retain process exit/signal status. No RSS ceiling is set here.
    """
    require("torch" not in sys.modules, "configure runtime before importing Torch")
    require(variant in VARIANTS and os.environ.get("ATEN_CPU_CAPABILITY") == VARIANTS[variant][0],
            "explicit ATEN_CPU_CAPABILITY must match selected variant")
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    affinity = os.sched_getaffinity(0)
    require(bool(affinity), "no CPU available")
    os.sched_setaffinity(0, {min(affinity)})
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    def expired(signum, frame):
        raise TimeoutError("native prefix capture received its 120-second SIGALRM; native calls may delay delivery")
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(120)


def run(root, payload0, payload3, payload_extra, runtime, output, m, variant="baseline"):
    paths = [Path(p).resolve() for p in (root, payload0, payload3, payload_extra, runtime, output)]
    root, payload0, payload3, payload_extra, runtime, output = paths
    require(root == ROOT, "runner root/import identity drift")
    require(type(m) is int and m in (16, 128), "only M16 and M128 captures supported")
    require(output.is_relative_to(root / "work"), "raw captures must stay in ignored local work directory")
    require(not output.exists(), "fresh nonexistent output required; never overwrite or rerun silently")
    configure_budget(variant)
    start = time.monotonic()
    output.mkdir(parents=True)
    runner_at_start = file_record(__file__)
    try:
        write_durable(output / "capture_start.json", encoded(dict(scope=SCOPE, runner=runner_at_start,
            query_tokens=m, variant=variant, root=str(root), runtime=str(runtime),
            payload_directories=dict(layer0=str(payload0), layer3=str(payload3), additional_prefix=str(payload_extra)),
            contract_sha256=CONTRACT_SHA256, expected_official_source_sha256=OFFICIAL_SOURCES,
            source_verification_completed=False, numerical_acceptance_claimed=False)))
        return _run(root, payload0, payload3, payload_extra, runtime, output, m, variant, start)
    except BaseException as exc:
        signal.alarm(0)
        write_failure_receipt(output, exc, m=m, start=start, runner_at_start=runner_at_start)
        raise
    finally:
        signal.alarm(0)



# Exact external provenance records from the already qualified recovered runtime.
# They are not replaced, omitted or rewritten; the original per-file hash gate
# below still reads every item after this closed placement/metadata check.
_RECOVERED_RUNTIME_EXTERNAL = {
    'acquisition_provenance:source_ledger': ('runtime_parent', 'runtime_dependency_recovery/network.jsonl', 28683, '3814be9f5b4e39fd25772b61f3cdedf44fd32bfa47d871b8eccc0959b5e21928'),
    'acquisition_provenance:source_lock': ('runtime_parent', 'runtime_dependency_recovery/official_runtime.lock.json', 78695, '806f6a7f409e85965261bf864fcc8de4558aaedf9f3da26759323625ca131497'),
    'acquisition_provenance:window_extension': ('runtime_parent', 'runtime_dependency_recovery/window_extension.json', 453, 'a81e1a768dc344b2dd5dda56ad85f26439de15ef99166e2f32f765b2b78cebed'),
    'backend_runner_source': ('repository', 'scripts/qwen35_backend_runner.py', 2141, '43a4c91380fc9ad6e3ca2d7780e623e2780a5c69126983d93c40b653a8e309e4'),
    'installer_source': ('repository', 'scripts/install_qwen35_official_runtime.py', 20695, '517a64fe24b195e8a469a388284292a23e4cabd91361613b4076cc2f57601642'),
    'pip_driver_source': ('repository', 'scripts/pip_qwen35_offline_driver.py', 7752, 'd6b5953062250492f5fcb457b58704f4ed0122ac2e54f277c00b3b2cf569d193'),
    'qualifier_source': ('repository', 'scripts/qualify_qwen35_official_runtime.py', 50210, '7686d0da3a220607b91f73934a22df7a949eda2ab74d6c89c20a82fdfe6e74f4'),
    'transformers_archive': ('runtime_parent', 'runtime_dependency_recovery/transformers-14e738b5d0cc69aa27a95dde272aea41fde44f2f.zip', 28738230, '15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d'),
    'wheel:annotated-doc': ('runtime_parent', 'runtime_dependency_recovery/wheels/annotated_doc-0.0.5-py3-none-any.whl', 5302, '117bac03a25ede5df5440e855b32d556049ca169ead221505badf432fed4b101'),
    'wheel:anyio': ('runtime_parent', 'runtime_dependency_recovery/wheels/anyio-4.14.2-py3-none-any.whl', 125813, '9f505dda5ac9f0c8309b5e8bd445a8c2bf7246f3ce950121e45ea15bc41d1494'),
    'wheel:certifi': ('runtime_parent', 'runtime_dependency_recovery/wheels/certifi-2026.7.22-py3-none-any.whl', 136983, '62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775'),
    'wheel:click': ('runtime_parent', 'runtime_dependency_recovery/wheels/click-8.4.2-py3-none-any.whl', 119243, 'e6f9f66136c816745b9d65817da91d61d957fb16e02e4dcd0552553c5a197b76'),
    'wheel:filelock': ('runtime_parent', 'runtime_dependency_recovery/wheels/filelock-3.20.0-py3-none-any.whl', 16054, '339b4732ffda5cd79b13f4e2711a31b0365ce445d95d243bb996273d072546a2'),
    'wheel:fsspec': ('runtime_parent', 'runtime_dependency_recovery/wheels/fsspec-2025.12.0-py3-none-any.whl', 201422, '8bf1fe301b7d8acfa6e8571e3b1c3d158f909666642431cc78a1b7b4dbc5ec5b'),
    'wheel:h11': ('runtime_parent', 'runtime_dependency_recovery/wheels/h11-0.16.0-py3-none-any.whl', 37515, '63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86'),
    'wheel:hf-xet': ('runtime_parent', 'runtime_dependency_recovery/wheels/hf_xet-1.7.0-cp38-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl', 4212180, '2814a6e999d13464c4d679b788cc5d784eb5a4edfc638a31f10e9a11ab531ef8'),
    'wheel:httpcore': ('runtime_parent', 'runtime_dependency_recovery/wheels/httpcore-1.0.9-py3-none-any.whl', 78784, '2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55'),
    'wheel:httpx': ('runtime_parent', 'runtime_dependency_recovery/wheels/httpx-0.28.1-py3-none-any.whl', 73517, 'd909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad'),
    'wheel:huggingface-hub': ('runtime_parent', 'runtime_dependency_recovery/wheels/huggingface_hub-1.33.0-py3-none-any.whl', 846435, '04e434b06e100eddbce9a6e817d72693a7884b10a79bd67ab48080d5c07eb899'),
    'wheel:idna': ('runtime_parent', 'runtime_dependency_recovery/wheels/idna-3.18-py3-none-any.whl', 65455, '7f952cbe720b688055e3f87de14f5c3e5fdaa8bc3928985c4077ca689de849a2'),
    'wheel:iniconfig': ('runtime_parent', 'runtime_dependency_recovery/wheels/iniconfig-2.3.1-py3-none-any.whl', 7552, '9121e2c1fdb355232495be3194c8dfe87ccc2d5dee45947b78e68f499790d7a7'),
    'wheel:jinja2': ('runtime_parent', 'runtime_dependency_recovery/wheels/jinja2-3.1.6-py3-none-any.whl', 134899, '85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67'),
    'wheel:markdown-it-py': ('runtime_parent', 'runtime_dependency_recovery/wheels/markdown_it_py-4.2.0-py3-none-any.whl', 91687, '9f7ebbcd14fe59494226453aed97c1070d83f8d24b6fc3a3bcf9a38092641c4a'),
    'wheel:markupsafe': ('runtime_parent', 'runtime_dependency_recovery/wheels/markupsafe-3.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl', 22947, 'd6dd0be5b5b189d31db7cda48b91d7e0a9795f31430b7f271219ab30f1d3ac9d'),
    'wheel:mdurl': ('runtime_parent', 'runtime_dependency_recovery/wheels/mdurl-0.1.2-py3-none-any.whl', 9979, '84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8'),
    'wheel:mpmath': ('runtime_parent', 'runtime_dependency_recovery/wheels/mpmath-1.3.0-py3-none-any.whl', 536198, 'a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c'),
    'wheel:networkx': ('runtime_parent', 'runtime_dependency_recovery/wheels/networkx-3.6.1-py3-none-any.whl', 2068504, 'd47fbf302e7d9cbbb9e2555a0d267983d2aa476bac30e90dfbe5669bd57f3762'),
    'wheel:numpy': ('runtime_parent', 'runtime_dependency_recovery/wheels/numpy-2.3.5-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl', 16606086, '0d8163f43acde9a73c2a33605353a4f1bc4798745a8b1d73183b28e5b435ae28'),
    'wheel:packaging': ('runtime_parent', 'runtime_dependency_recovery/wheels/packaging-26.3-py3-none-any.whl', 129956, 'd7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c'),
    'wheel:pip': ('runtime_parent', 'runtime_dependency_recovery/wheels/pip-26.2.1-py3-none-any.whl', 1816632, '71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e'),
    'wheel:pluggy': ('runtime_parent', 'runtime_dependency_recovery/wheels/pluggy-1.6.0-py3-none-any.whl', 20538, 'e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746'),
    'wheel:pygments': ('runtime_parent', 'runtime_dependency_recovery/wheels/pygments-2.21.0-py3-none-any.whl', 1250147, '2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9'),
    'wheel:pytest': ('runtime_parent', 'runtime_dependency_recovery/wheels/pytest-8.4.2-py3-none-any.whl', 365750, '872f880de3fc3a5bdc88a11b39c9710c3497a547cfa9320bc3c5e62fbf272e79'),
    'wheel:pyyaml': ('runtime_parent', 'runtime_dependency_recovery/wheels/pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl', 807870, 'ba1cc08a7ccde2d2ec775841541641e4548226580ab850948cbfda66a1befcdc'),
    'wheel:regex': ('runtime_parent', 'runtime_dependency_recovery/wheels/regex-2025.11.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl', 803501, 'a12ab1f5c29b4e93db518f5e3872116b7e9b1646c9f9f426f777b50d44a09e8c'),
    'wheel:rich': ('runtime_parent', 'runtime_dependency_recovery/wheels/rich-15.0.0-py3-none-any.whl', 310654, '33bd4ef74232fb73fe9279a257718407f169c09b78a87ad3d296f548e27de0bb'),
    'wheel:safetensors': ('runtime_parent', 'runtime_dependency_recovery/wheels/safetensors-0.8.0-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl', 516040, 'fd6f3f93c9a0a7cc2788ee63fb763353d4bd2e89b0751bc78fcf7dda00bea774'),
    'wheel:setuptools': ('runtime_parent', 'runtime_dependency_recovery/wheels/setuptools-84.0.0-py3-none-any.whl', 818216, '51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670'),
    'wheel:shellingham': ('runtime_parent', 'runtime_dependency_recovery/wheels/shellingham-1.5.4-py2.py3-none-any.whl', 9755, '7ecfff8f2fd72616f7481040475a65b2bf8af90a56c89140852d1120324e8686'),
    'wheel:sympy': ('runtime_parent', 'runtime_dependency_recovery/wheels/sympy-1.14.0-py3-none-any.whl', 6299353, 'e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5'),
    'wheel:tokenizers': ('runtime_parent', 'runtime_dependency_recovery/wheels/tokenizers-0.23.2-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl', 3386843, '41c2f84d172449b4dadb9cdc508e3e364076613c35b16e76ecfe47a60d1e3305'),
    'wheel:torch': ('runtime_parent', 'runtime_dependency_recovery/wheels/torch-2.10.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl', 188943803, 'ee40b8a4b4b2cf0670c6fd4f35a7ef23871af956fecb238fbf5da15a72650b1d'),
    'wheel:tqdm': ('runtime_parent', 'runtime_dependency_recovery/wheels/tqdm-4.70.1-py3-none-any.whl', 80199, 'c293e525e6fef9c20e8728fd4612df02a0aa31bb5fe91ecd93e123b1b7bffa73'),
    'wheel:typer': ('runtime_parent', 'runtime_dependency_recovery/wheels/typer-0.27.3-py3-none-any.whl', 123312, 'e50022f28b82a86313e54501317a1db64bf8f8d036ff8cfe5ca7e47675454aff'),
    'wheel:typing-extensions': ('runtime_parent', 'runtime_dependency_recovery/wheels/typing_extensions-4.15.0-py3-none-any.whl', 44614, 'f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548'),
    'wheel:wheel': ('runtime_parent', 'runtime_dependency_recovery/wheels/wheel-0.48.0-py3-none-any.whl', 33320, '3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab'),
}


# Seven exact installed/provenance aliases in the same sealed receipt.
_RECOVERED_RUNTIME_ALIASES = {'acquisition.json': (('acquisition_report', 'install_provenance:acquisition_report'),
                      884,
                      '91491ed72d80fc1f28bd725450286c0e5604e5c04e49e9d1c898a922f0ab064d'),
 'dependency_lock.json': (('dependency_lock', 'install_provenance:dependency_lock'),
                          78695,
                          '806f6a7f409e85965261bf864fcc8de4558aaedf9f3da26759323625ca131497'),
 'guard/sitecustomize.py': (('install_provenance:guard_installed', 'network_guard_source'),
                            3226,
                            'adf905304fe32c34ccb07892f2627fcb76417178d36058270b74a4666b28c2c5'),
 'install_transformers.json': (('install_provenance:transformers_install_report', 'pip_transformers_report'),
                               34416,
                               'e75a371bbeca700e685dd34425d57b6646db9f41fff054f7179278ffcbcb3fa7'),
 'install_wheels.json': (('install_provenance:wheel_install_report', 'pip_wheels_report'),
                         451056,
                         '872884caa096ef9131a101a7c11664ba514e9ab73e1223ff078538e7df80d788'),
 'python.sh': (('install_provenance:python_wrapper', 'python_wrapper'),
               750,
               'ed58028b1d356fce9209f46ad26da5a3c7e3dbf8b57206a3692dd9fc73f8aa71'),
 'site-packages/transformers-5.19.0.dev0.dist-info/direct_url.json': (('install_provenance:transformers_direct_url',
                                                                       'installed:transformers-5.19.0.dev0.dist-info/direct_url.json'),
                                                                      298,
                                                                      '468b1813bda036ec8e12393b5fcaea28e48d49a1347031fb50e080c06a8f1f6a')}

def runtime_artifact_path(root, runtime, name, record):
    """Accept installed runtime files or exactly the 46 sealed recovery items."""
    root, runtime = Path(root).resolve(strict=True), Path(runtime).resolve(strict=True)
    require(runtime.is_relative_to(root), 'runtime outside explicit repository')
    relative = Path(record['path'])
    require(not relative.is_absolute() and '..' not in relative.parts and str(relative) == record['path'],
            'runtime artifact relative path escape')
    unresolved = root / relative
    require(all(not (root / Path(*relative.parts[:i])).is_symlink()
                for i in range(1, len(relative.parts) + 1)), 'runtime artifact symlink refused')
    path = unresolved.resolve(strict=True)
    require(path.is_file() and path.is_relative_to(root), 'runtime artifact path escape')
    if path.is_relative_to(runtime):
        require(name not in _RECOVERED_RUNTIME_EXTERNAL, 'external provenance relabelled as installed runtime')
        return path
    require(name in _RECOVERED_RUNTIME_EXTERNAL, 'unknown external runtime artifact category: ' + str(name))
    scope, suffix, size, digest = _RECOVERED_RUNTIME_EXTERNAL[name]
    allowed = (root if scope == 'repository' else runtime.parent) / suffix
    require(path == allowed and type(record.get('bytes')) is int and record['bytes'] == size and
            record.get('sha256') == digest, 'runtime provenance path/metadata mismatch: ' + name)
    return path


def validate_runtime_layout(root, runtime, receipt):
    """Require all-or-none recovery provenance; reject missing/extra records."""
    artifacts = receipt['artifacts']
    require(type(artifacts) is dict and artifacts, 'nonempty runtime artifact map required')
    paths = {name: runtime_artifact_path(root, runtime, name, record) for name, record in artifacts.items()}
    external = {name for name, path in paths.items() if not path.is_relative_to(Path(runtime).resolve())}
    recovered = receipt.get('package_dependency_closure_verified') is True or bool(external)
    require(not recovered or external == set(_RECOVERED_RUNTIME_EXTERNAL),
            'complete 46-item recovered provenance inventory required')
    aliases = {}
    for name, path in paths.items():
        aliases.setdefault(path, []).append(name)
    for path, names in aliases.items():
        if len(names) == 1:
            continue
        require(path.is_relative_to(Path(runtime).resolve()), 'duplicate external runtime artifact path')
        suffix = str(path.relative_to(Path(runtime).resolve()))
        require(suffix in _RECOVERED_RUNTIME_ALIASES, 'unknown duplicate runtime artifact path')
        expected_names, size, digest = _RECOVERED_RUNTIME_ALIASES[suffix]
        require(set(names) == set(expected_names) and all(type(artifacts[n].get('bytes')) is int and
                artifacts[n]['bytes'] == size and artifacts[n].get('sha256') == digest for n in names),
                'runtime provenance alias metadata drift')
    return paths


def _run(root, payload0, payload3, payload_extra, runtime, output, m, variant, start):
    contract_path = root / CONTRACT
    require(sha(contract_path.read_bytes()) == CONTRACT_SHA256, "original BF16 contract drift")
    contract = json.loads(contract_path.read_bytes())
    require(len(contract["producer_sequence"]) == 57, "original producer inventory drift")
    source_files = {"runner": file_record(__file__), "contract": file_record(contract_path)}
    for name, digest in contract["fresh_prefix_source_sha256"].items():
        source_files[name] = file_record(root / name)
        require(source_files[name]["sha256"] == digest, "pinned prefix dependency source drift: " + name)
    sys.path[:0] = [str(root), str(root / "src")]
    from heteronpu import pinned_block_payload, pinned_gdn_payload, pinned_prefix_payload

    # Existing loaders verify fixed checkpoint headers, spans, slice hashes and
    # original HTTP receipts. This entrypoint never downloads or accepts hidden
    # inputs from a saved smoke, a candidate, or a command-line digest override.
    manifests, payloads, raw_values = {}, {}, {}
    for name, module, directory in (("layer0", pinned_gdn_payload, payload0),
            ("layer3", pinned_block_payload, payload3), ("additional_prefix", pinned_prefix_payload, payload_extra)):
        require(Path(inspect.getfile(module)).resolve() == root / "src/heteronpu" / (module.__name__.split(".")[-1] + ".py"),
                "payload loader import drift")
        manifest, raw = module.load_payload(root, directory)
        manifests[name], raw_values[name] = manifest, raw
        payloads[name] = dict(directory=str(directory), manifest=file_record(directory / "manifest.json"),
                              payload_bytes=manifest["payload_bytes"], tensors=manifest["tensors"])
        source_files[name + "_loader"] = file_record(inspect.getfile(module))
    fixture = pinned_prefix_payload.token_fixture(root)
    receipt_path = runtime / "runtime_receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    require(receipt.get("status") == "PASS_ISOLATED_PINNED_RUNTIME_READY" and receipt.get("checks") and
            all(v is True for v in receipt["checks"].values()), "isolated runtime is not verified ready")
    runtime_files = {"runtime_receipt": file_record(receipt_path)}
    runtime_paths = validate_runtime_layout(root, runtime, receipt)
    for name, record in receipt["artifacts"].items():
        path = runtime_paths[name]
        actual = file_record(path)
        require(actual["bytes"] == record["bytes"] and actual["sha256"] == record["sha256"], "runtime artifact drift: " + name)
        runtime_files[name] = actual

    import torch
    import transformers.activations as activations_source
    import transformers.cache_utils as cache_source
    import transformers.masking_utils as masking_source
    from torch.utils._python_dispatch import TorchDispatchMode
    from transformers.cache_utils import DynamicCache
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig

    require(sys.byteorder == "little", "raw artifact encoding requires little-endian host")
    require(torch.__version__ == "2.10.0+cpu" and torch.version.git_version == TORCH_GIT_VERSION and
            torch.version.cuda is None, "pinned Torch 2.10.0 CPU build required")
    require(importlib.metadata.version("numpy") == contract["numpy_version"], "pinned NumPy runtime drift")
    sources = dict(modeling=Path(inspect.getfile(official)), cache=Path(inspect.getfile(cache_source)),
        masking=Path(inspect.getfile(masking_source)), activations=Path(inspect.getfile(activations_source)),
        configuration=Path(inspect.getfile(Qwen3_5TextConfig)))
    for name, path in sources.items():
        require(path.resolve().is_relative_to(runtime / "site-packages") and sha(path.read_bytes()) == OFFICIAL_SOURCES[name],
                "installed official source drift: " + name)
    direct_url = json.loads(importlib.metadata.distribution("transformers").read_text("direct_url.json") or "{}")
    require(direct_url.get("url") == "https://github.com/huggingface/transformers/archive/" + FRAMEWORK_REVISION + ".zip" and
            direct_url.get("archive_info", {}).get("hashes", {}).get("sha256") == ARCHIVE_SHA256,
            "pinned Transformers archive identity drift")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    torch.set_flush_denormal(False)
    require(torch.backends.cpu.get_cpu_capability() == VARIANTS[variant][1], "actual CPU dispatch mismatch")
    config_path = root / "config/upstream/qwen3_5_0p8b/config.json"
    require(sha(config_path.read_bytes()) == contract["config_sha256"], "original model config drift")
    config = Qwen3_5TextConfig.from_dict(json.loads(config_path.read_bytes())["text_config"])
    config._attn_implementation = "eager"
    config_before = config.to_dict()
    require(config.num_hidden_layers == 24 and config.layer_types[:4] == ["linear_attention"] * 3 + ["full_attention"],
            "complete original prefix configuration drift")
    source_files.update({name: file_record(path) for name, path in sources.items()})
    source_files.update(config=file_record(config_path), token_fixture=file_record(root / pinned_prefix_payload.FIXTURE_PATH))
    write_durable(output / "verified_source_identity.json", encoded(dict(scope=SCOPE, source_files=source_files,
        runtime_files=runtime_files, payloads=payloads, transformers_direct_url=direct_url,
        original_parameter_load_completed=False, model_forward_executed=False, numerical_acceptance_claimed=False)))
    with torch.device("meta"):
        model = official.Qwen3_5TextModel(config)

    dtype_names = {torch.bfloat16: "BF16", torch.float32: "F32", torch.int64: "I64", torch.bool: "BOOL"}
    def raw(tensor):
        require(tensor.device.type == "cpu" and tensor.dtype in dtype_names, "unsupported capture tensor")
        # reshape also supports scalar ATen results without altering their bits.
        return tensor.detach().contiguous().reshape(-1).view(torch.uint8).numpy().tobytes()

    parameters, parameter_objects = {}, {}
    def load_tensor(record, data):
        require(record["dtype"] in ("BF16", "F32"), "unsupported checkpoint dtype")
        dtype = torch.bfloat16 if record["dtype"] == "BF16" else torch.float32
        tensor = torch.frombuffer(bytearray(data), dtype=dtype).reshape(record["shape"])
        require(torch.isfinite(tensor).all().item() and sha(raw(tensor)) == record["sha256"], "nonfinite/altered checkpoint tensor")
        return tensor

    embedding_record = next(r for r in manifests["additional_prefix"]["tensors"] if r["local_name"] == "embed_tokens.rows_0_255")
    embedding = load_tensor(embedding_record, raw_values["additional_prefix"].pop(embedding_record["local_name"]))
    model.embed_tokens = torch.nn.Embedding.from_pretrained(embedding, freeze=True)
    model.rotary_emb = official.Qwen3_5TextRotaryEmbedding(config)
    for layer in range(4):
        payload_name = "layer" + str(layer) if layer in (0, 3) else "additional_prefix"
        prefix = f"layers.{layer}." if layer in (1, 2) else ""
        records = [r for r in manifests[payload_name]["tensors"] if not prefix or r["local_name"].startswith(prefix)]
        values = {r["local_name"].removeprefix(prefix): load_tensor(r, raw_values[payload_name].pop(r["local_name"])) for r in records}
        loaded = model.layers[layer].load_state_dict(values, strict=True, assign=True)
        require(not loaded.missing_keys and not loaded.unexpected_keys, "incomplete original prefix parameter load")
        actual = dict(model.layers[layer].named_parameters())
        require(len(actual) == len(records) == (11 if layer == 3 else 14), "parameter inventory drift")
        for record in records:
            name = record["local_name"].removeprefix(prefix)
            tensor = actual[name]
            require(dtype_names[tensor.dtype] == record["dtype"] and list(tensor.shape) == record["shape"] and
                    sha(raw(tensor)) == record["sha256"], "loaded parameter dtype/bytes drift: " + name)
            key = f"layers.{layer}." + name
            parameters[key] = {k: record[k] for k in ("shape", "dtype", "bytes", "sha256")}
            parameter_objects[id(tensor)] = key
        del values
    require(all(not remaining for remaining in raw_values.values()), "unused/missing selected checkpoint tensors")
    del raw_values
    require(all(p.is_meta for layer in model.layers[4:] for p in layer.parameters()) and
            all(p.is_meta for p in model.norm.parameters()), "unused suffix weights must stay meta")
    model.eval()
    cache = DynamicCache(config=config)
    require(len(cache.layers) == 24, "original cache configuration drift")
    tensors, dedup, cases, events, hooks, stack = {}, {}, [], [], [], []
    tensor_journal = TensorJournal(output)
    active, observation_depth, capture_bytes = {}, 0, 0

    @contextmanager
    def observing():
        nonlocal observation_depth
        observation_depth += 1
        try:
            yield
        finally:
            observation_depth -= 1

    def save(key, tensor):
        nonlocal capture_bytes
        if tensor is None:
            return None
        with observing():
            require(isinstance(tensor, torch.Tensor) and tensor.dtype in dtype_names and tensor.numel() > 0,
                    "unsupported/empty captured tensor: " + key)
            require(torch.isfinite(tensor).all().item(), "nonfinite official tensor: " + key)
            data = raw(tensor)
            dtype, shape, digest = dtype_names[tensor.dtype], list(tensor.shape), sha(data)
            identity = (dtype, tuple(shape), digest)
            if identity in dedup:
                return dedup[identity]
            require(key not in tensors, "duplicate tensor observation key: " + key)
            capture_bytes += len(data)
            require(capture_bytes <= 256 * 1024 * 1024, "capture exceeded 256 MiB disk budget")
            record = dict(file=f"{len(tensors):04d}." + dtype.lower() + "le", shape=shape,
                          dtype=dtype, bytes=len(data), sha256=digest)
            tensor_journal.persist(key, record, data)
            tensors[key] = validate_tensor_record(record)
            dedup[identity] = key
            return key

    def tree(key, value):
        if isinstance(value, torch.Tensor):
            if value.numel() == 0:
                require(value.device.type == "cpu" and value.dtype in dtype_names, "unsupported empty tensor")
                return {"empty_tensor": dict(shape=list(value.shape), dtype=dtype_names[value.dtype], bytes=0)}
            parameter = parameter_objects.get(id(value))
            return {"parameter": parameter} if parameter else {"tensor": save(key, value)}
        if isinstance(value, (tuple, list)):
            return [tree(key + f".{i}", v) for i, v in enumerate(value)]
        if isinstance(value, dict):
            return {str(k): tree(key + "." + str(k), v) for k, v in value.items()}
        if value is None or type(value) in (str, bool, int, float):
            return value
        if isinstance(value, (torch.dtype, torch.device, torch.memory_format, torch.layout)):
            return {"torch_type": str(value)}
        require(value is cache, "unexpected opaque capture argument: " + type(value).__name__)
        return {"type": "DynamicCache", "object_id": id(cache)}

    def snapshot(label):
        state = {}
        for i in range(4):
            slot = cache.layers[i]
            if i < 3:
                state[str(i)] = dict(conv_state=save(label + f".{i}.conv", slot.conv_states[0]),
                    recurrent_state=save(label + f".{i}.ssm", slot.recurrent_states[0]),
                    has_previous_state=bool(cache.has_previous_state(i)))
            else:
                state[str(i)] = dict(key=save(label + ".3.key", slot.keys), value=save(label + ".3.value", slot.values),
                                     tokens=int(cache.get_seq_length(3)))
        return state

    class PrefixComplete(Exception):
        """Stop unmodified TextModel.forward at the completed L3 boundary."""

    def reject_unused(*args, **kwargs):
        raise ValueError("unused meta suffix/final norm reached")

    for module in (model.layers[4], model.norm):
        hooks.append(module.register_forward_pre_hook(reject_unused))

    def embedding_hook(module, args, result):
        active["embedding"] = save(active["name"] + ".embedding", result)
        with observing():
            require(raw(result) == raw(embedding[args[0]]), "embedding lookup differs from exact pinned rows")
    hooks.append(model.embed_tokens.register_forward_hook(embedding_hook))

    def rotary_hook(module, args, result):
        active["rope_position_ids"] = save(active["name"] + ".rope_position_ids", args[1])
        active["rope_cos"], active["rope_sin"] = (save(active["name"] + ".rope_" + n, t) for n, t in zip(("cos", "sin"), result))
    hooks.append(model.rotary_emb.register_forward_hook(rotary_hook))

    for index in range(4):
        def layer_before(module, args, kwargs, index=index):
            require(len(active["layers"]) == index, "official layer execution order drift")
            require(kwargs["past_key_values"] is cache, "prefix layer did not receive same actual cache")
            key = active["name"] + f".layer{index}.input"
            active["layer_inputs"][index] = save(key, args[0])
            if index < 3:
                require(kwargs["attention_mask"] is None, "original all-valid GDN mask should be absent")
            else:
                active["input"] = active["layer_inputs"][3]
                active["attention_mask"] = save(active["name"] + ".attention_mask", kwargs["attention_mask"])
                with observing():
                    past = active["past_tokens"]
                    allowed = torch.arange(past + m)[None, :] <= (torch.arange(m)[:, None] + past)
                    expected = torch.where(allowed, 0.0, torch.finfo(torch.bfloat16).min).to(torch.bfloat16)[None, None]
                    require(raw(kwargs["attention_mask"]) == raw(expected) and
                            list(kwargs["attention_mask"].shape) == [1, 1, m, past + m], "original cache-derived causal mask drift")
                    require(raw(kwargs["position_ids"]) == raw(active["positions"]), "original explicit position IDs drift")
                active["mask_uses_actual_cache_length"] = True
        def layer_after(module, args, kwargs, result, index=index):
            key = save(active["name"] + f".layer{index}.output", result)
            active["layers"].append(dict(layer=index, input=active["layer_inputs"][index], output=key))
            if index == 3:
                active["output"] = key
                raise PrefixComplete()
        hooks.append(model.layers[index].register_forward_pre_hook(layer_before, with_kwargs=True))
        # Register the terminal hook after L3 module observers below.
        if index < 3:
            hooks.append(model.layers[index].register_forward_hook(layer_after, with_kwargs=True))
        else:
            terminal_hook = layer_after

    for name, module in model.layers[3].named_modules():
        def before(module, args, kwargs, name=name):
            require(torch.is_inference_mode_enabled() and not torch.is_autocast_enabled("cpu"), "execution mode drift")
            stack.append(name)
            key = active["name"] + ".module." + (name or "layer3")
            with observing():
                event = dict(case=active["name"], module=name, phase="input", args=tree(key + ".args", args), kwargs=tree(key + ".kwargs", kwargs))
                events.append(event)
                active["module_boundaries"].setdefault(name, {})["input"] = event
        def after(module, args, kwargs, result, name=name):
            require(stack and stack[-1] == name, "L3 module stack drift")
            key = active["name"] + ".module." + (name or "layer3")
            with observing():
                event = dict(case=active["name"], module=name, phase="output", result=tree(key + ".result", result))
                events.append(event)
                active["module_boundaries"].setdefault(name, {})["output"] = event
            stack.pop()
        hooks.append(module.register_forward_pre_hook(before, with_kwargs=True))
        hooks.append(module.register_forward_hook(after, with_kwargs=True))
    hooks.append(model.layers[3].register_forward_hook(terminal_hook, with_kwargs=True))

    class Trace(TorchDispatchMode):
        """Record actual ATen calls, with original operands/results unchanged.

        No op is renamed into a contractual producer. Consumers can assign the
        saved calls to the unchanged 57-producer contract in a later comparator.
        Observer-generated tensor operations are excluded by a reentrant guard.
        """
        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            if observation_depth or not stack:
                return func(*args, **(kwargs or {}))
            number = len(active["dispatch_events"])
            key = active["name"] + f".aten{number:04d}"
            with observing():
                event = dict(index=number, module=stack[-1], op=str(func),
                             args=tree(key + ".args", args), kwargs=tree(key + ".kwargs", kwargs or {}))
            result = func(*args, **(kwargs or {}))
            with observing():
                event["result"] = tree(key + ".result", result)
                active["dispatch_events"].append(event)
            return result

    previous_profile = sys.getprofile()
    require(previous_profile is None, "unexpected existing profiler")
    norm_modules = {id(module): name for name, module in model.layers[3].named_modules()
                    if isinstance(module, official.Qwen3_5RMSNorm)}
    require(set(norm_modules.values()) == {"input_layernorm", "self_attn.q_norm", "self_attn.k_norm", "post_attention_layernorm"},
            "original L3 RMS module inventory drift")
    def profiler(frame, event, result):
        if observation_depth or event != "return" or frame.f_code.co_filename != str(sources["modeling"]):
            return
        local, name = frame.f_locals, frame.f_code.co_name
        label, values = None, {}
        if frame.f_code is official.apply_rotary_pos_emb.__code__:
            label = "rope"
            values = {n: local[n] for n in ("q", "k", "cos", "sin", "q_rot", "q_pass", "k_rot", "k_pass", "q_embed", "k_embed")}
        elif frame.f_code is official.eager_attention_forward.__code__:
            require(local["module"] is model.layers[3].self_attn, "unexpected eager attention module")
            label = "eager"
            values = {n: local[n] for n in ("query", "key", "value", "attention_mask", "key_states", "value_states", "attn_weights", "attn_output")}
        elif name == "forward" and local.get("self") is model.layers[3].self_attn:
            label = "attention"
            values = {n: local[n] for n in ("gate", "query_states", "key_states", "value_states", "attn_output", "attn_weights")}
        elif id(local.get("self")) in norm_modules and name in ("forward", "_norm"):
            label = "norm" if name == "forward" else "norm_core"
            values = dict(module=norm_modules[id(local["self"])], input=local["x"], result=result)
            if name == "forward":
                values["fp32_weighted_output"] = local["output"]
        # The public function can have a hub decorator. Observe the pinned
        # original body's filename/name, not the outer wrapper's code object.
        elif name == "torch_chunk_gated_delta_rule":
            label = "chunk"
            number = active["official_function_counts"][label]
            require(number in (0, 1, 2), "unexpected extra original GDN chunk call")
            initial = local["initial_state"]
            require(initial is cache.layers[number].recurrent_states[0], "original chunk prior state object drift")
            initial_key = save(active["name"] + f".chunk{number}.initial_state", initial)
            expected_key = active["prior_cache"][str(number)]["recurrent_state"]
            require(initial_key == expected_key, "original chunk did not consume actual prior GDN state bytes")
            values = {n: local[n] for n in ("chunk_size", "num_chunks", "sequence_length", "pad_size")}
            require(values == dict(chunk_size=64, num_chunks=(m + 63) // 64, sequence_length=m, pad_size=(64 - m % 64) % 64),
                    "original GDN chunk geometry drift")
            values["initial_state"] = initial
            values["final_state"] = result[1]
        if label is not None:
            number = active["official_function_counts"][label]
            active["official_function_counts"][label] += 1
            with observing():
                active["function_observations"].append(dict(function=label, invocation=number,
                    observation="original Python return-frame locals", values=tree(active["name"] + f".function.{label}{number}", values)))

    try:
        for i, phase in enumerate(("cold", "carried")):
            offset = 128 * i
            active = dict(name=phase + str(m), source_token_slice=[offset, offset + m], position_span=[offset, offset + m],
                past_tokens=int(cache.get_seq_length(3)), cache_object_id=id(cache), layers=[], layer_inputs={},
                dispatch_events=[], module_boundaries={}, function_observations=[],
                official_function_counts=dict(rope=0, eager=0, attention=0, chunk=0, norm=0, norm_core=0))
            require(active["past_tokens"] == i * m, "actual cache length before call drift")
            active["prior_cache"] = snapshot(active["name"] + ".prior_cache")
            ids = torch.tensor(fixture["token_ids"][offset:offset + m], dtype=torch.int64).reshape(1, m)
            positions = torch.arange(offset, offset + m, dtype=torch.int64).reshape(1, m)
            # Match the original prefix runner's original-window mask length;
            # pinned masking_utils trims to the actual DynamicCache KV length.
            mask = torch.ones((1, offset + m), dtype=torch.int64)
            active["token_ids"] = save(active["name"] + ".token_ids", ids)
            active["position_ids"] = save(active["name"] + ".position_ids", positions)
            active["supplied_attention_mask"] = save(active["name"] + ".supplied_attention_mask", mask)
            active["positions"] = positions
            sys.setprofile(profiler)
            try:
                with torch.inference_mode(), torch.autocast(device_type="cpu", enabled=False), Trace():
                    model(input_ids=ids, attention_mask=mask, position_ids=positions, past_key_values=cache, use_cache=True)
            except PrefixComplete:
                pass
            else:
                raise ValueError("original TextModel did not reach exact L3 capture boundary")
            finally:
                sys.setprofile(previous_profile)
            require(not stack and len(active["layers"]) == 4, "incomplete original prefix execution")
            active.pop("positions")
            active.pop("layer_inputs")
            active["final_tokens"] = int(cache.get_seq_length(3))
            active["final_cache"] = snapshot(active["name"] + ".final_cache")
            chunks = [entry for entry in active["function_observations"] if entry["function"] == "chunk"]
            require(len(chunks) == 3, "three actual GDN chunk observations required")
            for j, entry in enumerate(chunks):
                require(entry["values"]["final_state"]["tensor"] == active["final_cache"][str(j)]["recurrent_state"],
                        "observed chunk final state differs from actual GDN cache")
            active["retained_kv_prefix"] = {name: save(active["name"] + ".retained_" + name,
                getattr(cache.layers[3], attr)[..., :i * m, :]) if i else None for name, attr in (("key", "keys"), ("value", "values"))}
            # Compare only observed byte views; no attention arithmetic replay.
            observations = {o["function"]: o for o in active["function_observations"] if o["function"] != "chunk"}
            q_key = active["module_boundaries"]["self_attn.q_proj"]["output"]["result"]["tensor"]
            gate_key = observations["attention"]["values"]["gate"]["tensor"]
            q_input_key = active["module_boundaries"]["self_attn.q_norm"]["input"]["args"][0]["tensor"]
            packed = (output / tensors[q_key]["file"]).read_bytes()
            q_bytes, gate_bytes = bytearray(), bytearray()
            for cursor in range(0, len(packed), 1024):
                q_bytes.extend(packed[cursor:cursor + 512])
                gate_bytes.extend(packed[cursor + 512:cursor + 1024])
            require(sha(q_bytes) == tensors[q_input_key]["sha256"] and sha(gate_bytes) == tensors[gate_key]["sha256"],
                    "per-head packed Q/gate split drift")
            active["packed_q_gate_split_verified"] = True
            cases.append(active)
            print(json.dumps(dict(case=active["name"], status="CAPTURED", elapsed_seconds=round(time.monotonic() - start, 3))), flush=True)
    finally:
        sys.setprofile(previous_profile)
        for hook in hooks:
            hook.remove()
    require(config.to_dict() == config_before and not model.training, "original config/eval mode changed")
    require(all(p.is_meta for layer in model.layers[4:] for p in layer.parameters()) and all(p.is_meta for p in model.norm.parameters()),
            "unused meta suffix changed")
    for name, tensor in model.named_parameters():
        if name in parameters:
            require(sha(raw(tensor)) == parameters[name]["sha256"] and dtype_names[tensor.dtype] == parameters[name]["dtype"],
                    "loaded parameter changed during capture: " + name)
    require(sha(raw(model.embed_tokens.weight)) == embedding_record["sha256"], "embedding parameter changed during capture")
    for record in (*source_files.values(), *runtime_files.values()):
        require(file_record(record["path"]) == record, "capture/runtime source changed during execution")
    for name, path in sources.items():
        require(sha(path.read_bytes()) == OFFICIAL_SOURCES[name], "official source changed during capture")
        source_files[name] = file_record(path)
    source_files.update(runner=file_record(__file__), config=file_record(config_path), contract=file_record(contract_path),
                        token_fixture=file_record(root / pinned_prefix_payload.FIXTURE_PATH))
    for name, entry in payloads.items():
        require(file_record(entry["manifest"]["path"]) == entry["manifest"], "payload manifest changed during capture")
        for record in entry["tensors"]:
            require(sha((Path(entry["directory"]) / record["file"]).read_bytes()) == record["sha256"], "checkpoint payload changed during capture")
    require(pinned_prefix_payload.token_fixture(root) == fixture, "token fixture changed during capture")
    report = dict(schema_version=1, scope=SCOPE, status="CAPTURED_OFFICIAL_SOFTWARE_REFERENCE_ONLY",
        created_at=datetime.now(timezone.utc).isoformat(), model_id=MODEL_ID, revision=REVISION, framework_revision=FRAMEWORK_REVISION,
        query_tokens=m, case_identity="cold128_then_carried128" if m == 128 else "cold16_then_carried16_from_second_window",
        input_origin="fixed artificial original token fixture; real pinned BF16 embedding followed by original GDN0/1/2",
        configuration="complete original 24-layer TextModel config, eager attention, unused suffix/final norm remain meta",
        forward_scope="unmodified original TextModel.forward interrupted only after complete original L3 output",
        position_scope="explicit text/RoPE offsets 0 and 128; causal query offsets use actual cache lengths 0 and M",
        m16_scope="M16 contains 16 true prior tokens on call2, not a 128-token history; positional gap is intentional original fixture semantics",
        payloads=payloads, parameters=parameters, fixture=fixture, source_files=source_files, runtime_files=runtime_files,
        official_source_sha256=OFFICIAL_SOURCES, contract_sha256=CONTRACT_SHA256,
        original_producer_sequence=contract["producer_sequence"], full_57_producer_assignment_performed=False,
        cases=cases, tensors=tensors, module_events=events,
        observation_scope="read-only hooks return None; ATen observer calls original functions once and returns unchanged results; original Python frame locals are observed without patching source",
        unobserved_internals=["native GEMM/softmax/rsqrt/sigmoid/SiLU kernel reduction trees and transient intermediates inside ATen kernels",
            "GDN internals except original layer boundaries, return-frame chunk geometry and logical conv/SSM states",
            "unused layers4..23, final norm, language head, vision, MTP"],
        environment=dict(python=platform.python_version(), packages={n: importlib.metadata.version(n) for n in
            ("torch", "transformers", "numpy", "huggingface-hub", "tokenizers", "safetensors")},
            transformers_direct_url=direct_url, torch_git_version=torch.version.git_version, variant=variant,
            aten_cpu_capability=os.environ["ATEN_CPU_CAPABILITY"], torch_cpu_capability=torch.backends.cpu.get_cpu_capability(),
            torch_threads=torch.get_num_threads(), torch_interop_threads=torch.get_num_interop_threads(),
            cpu_affinity=sorted(os.sched_getaffinity(0)), eval=True, inference=True, autocast=False,
            deterministic_algorithms=torch.are_deterministic_algorithms_enabled(), float32_matmul_precision=torch.get_float32_matmul_precision(),
            flush_denormal=False),
        resources=dict(wall_alarm_seconds=120, cpu_soft_limit_seconds=120, cpu_hard_limit_seconds=120,
            strict_wall_limit_enforced=False, rss_limit_enforced=False, external_exit_supervision_required=True,
            elapsed_seconds=time.monotonic() - start,
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, activation_bytes=capture_bytes),
        official_TextModel_prefix_executed=True, official_full_model_executed=False, owner_executed=False, hardware_executed=False,
        original_parameter_bytes_verified=True, full_checkpoint_sha256_verified=False, physical_cache_conditions_measured=False,
        numerical_comparison_performed=False, numerical_acceptance_gate_added=False, previous_fp32_gate_replaced=False)
    validate_manifest(report, output)
    (output / "manifest.json").write_bytes(encoded(report))
    summary = dict(status=report["status"], case_identity=report["case_identity"], manifest=file_record(output / "manifest.json"),
                   captures=len(tensors), resources=report["resources"],
                   claim="Official BF16 prefix capture only. No numerical acceptance; existing FP32 gate and 57-producer comparator unchanged.")
    (output / "summary.json").write_bytes(encoded(summary))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--payload-layer0", type=Path, required=True)
    parser.add_argument("--payload-layer3", type=Path, required=True)
    parser.add_argument("--payload-extra", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tokens", type=int, choices=(16, 128), required=True)
    parser.add_argument("--variant", choices=tuple(VARIANTS), default="baseline")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.root, args.payload_layer0, args.payload_layer3, args.payload_extra,
                         args.runtime, args.output, args.tokens, args.variant), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

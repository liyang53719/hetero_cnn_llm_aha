#!/usr/bin/env python3
"""Fixed raw2 acquisition adapter; source-only unless --execute is explicit.

Run only with Python -I -S -B under the caller's CPU/wall supervisor. This
adapter does not change process resource limits, signal masks, or timers.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
import types

ORIGINAL_RELATIVE = "development_snapshots/canonical_raw_acquisition_source_20261018/acquire_raw.py"
ORIGINAL_BYTES = 17991
ORIGINAL_SHA256 = "4cff91b1a5e76a6a1701426fd1e6cb1f8db32ee8b7e762bb17575364b12d932a"
PLAN_BYTES = 14096
PLAN_SHA256 = "7af00f7b0ebe36a2d31cd18de72ff9da487197eb91ab671cb60a53b2c076d220"
PAYLOAD_BYTES = 789504
MAX_WALL_SECONDS = 180

# Only exact strings emitted by frozen original require() sites are classified.
# Arbitrary exceptions, URLs, paths, headers and text never enter public output.
ORIGINAL_FAILURE_CODES = {
    "symlink path refused": "PATH_SYMLINK",
    "nonregular or oversized input": "INPUT_BOUND",
    "input size drift": "INPUT_SIZE",
    "input grew beyond bound": "INPUT_GROWTH",
    "input changed length": "INPUT_LENGTH",
    "fixed acquisition plan hash drift": "PLAN_HASH",
    "platform API evidence hash drift": "EVIDENCE_HASH",
    "platform metadata evidence identity drift": "EVIDENCE_IDENTITY",
    "source path escape": "SOURCE_PATH",
    "source Git blob drift": "SOURCE_BLOB",
    "helper definitions drift": "HELPER_DEFINITIONS",
    "raw pin identity drift": "RAW_PIN_IDENTITY",
    "bundle identity drift": "BUNDLE_IDENTITY",
    "shard count drift": "SHARD_COUNT",
    "shard identity drift": "SHARD_IDENTITY",
    "tensor dtype/size drift": "TENSOR_GEOMETRY",
    "segment count drift": "SEGMENT_COUNT",
    "segment geometry drift": "SEGMENT_GEOMETRY",
    "tensor plan drift": "TENSOR_PLAN",
    "request plan drift": "REQUEST_PLAN",
    "fixed acquisition budget drift": "ACQUISITION_BUDGET",
    "retained cache budget drift": "CACHE_BUDGET",
    "unapproved redirect URL": "REDIRECT_URL",
    "shared wall deadline exceeded": "DEADLINE",
    "HTTP error or redirect limit; no retry": "HTTP_OR_REDIRECT",
    "missing or duplicate range header": "RANGE_HEADER",
    "ambiguous transport framing": "TRANSPORT_FRAMING",
    "redirect limit": "REDIRECT_LIMIT",
    "refuse output overwrite": "OUTPUT_EXISTS",
    "cache symlink refused": "CACHE_SYMLINK",
    "nonregular cache refused": "CACHE_TYPE",
    "output disk budget exceeded": "DISK_BUDGET",
    "insufficient remaining disk": "DISK_FREE",
    "segment destination already exists": "SEGMENT_EXISTS",
    "tensor size drift": "TENSOR_SIZE",
    "tensor too long": "TENSOR_LONG",
    "tensor hash drift": "TENSOR_HASH",
    "tensor destination already exists": "TENSOR_EXISTS",
    "assembled tensor too long": "ASSEMBLY_LONG",
    "assembled tensor SHA mismatch": "ASSEMBLY_HASH",
    "output must be a new directory under an existing parent": "OUTPUT_FRESH",
    "output must be outside repository": "OUTPUT_REPOSITORY",
    "historical work tree refused": "HISTORICAL_WORK",
    "need at least 512 MiB free disk": "DISK_PREFLIGHT",
    "duplicate JSON key": "JSON_DUPLICATE",
    "non-finite JSON number": "JSON_NONFINITE",
    "range fields must be integers": "RANGE_TYPE",
    "unbounded payload range": "RANGE_BOUND",
    "server ignored/mismatched range; body refused": "HTTP_RANGE",
    "range Content-Length mismatch": "HTTP_LENGTH",
    "encoded range refused": "HTTP_ENCODING",
    "payload body length mismatch": "BODY_LENGTH",
    "Qwen2 payload HTTP receipt drift": "RECEIPT_IDENTITY",
    "Qwen2 segment bytes/hash mismatch": "SEGMENT_HASH",
}
for _source in (
    "config/payload_pins/qwen2_layer0.json",
    "config/upstream/weight_headers/qwen2_1p5b/manifest.json",
    "scripts/qwen2_layer0_payload.py",
    "src/heteronpu/pinned_block_payload.py",
    "src/heteronpu/pinned_gdn_payload.py",
):
    ORIGINAL_FAILURE_CODES["source SHA256 drift: " + _source] = "SOURCE_HASH"

# Closed receipt identity, independent of caller paths and remote response data.
FIXED_RECEIPT = {'automatic_retries': 0,
 'canonical_loader_executed': False,
 'completed_request_indices': [0, 1],
 'header_sha256': '124516afba769374e2b948e185dd3e9203e2412daaef3f2ccf7bdbaca0f88987',
 'layer_id': 0,
 'model_id': 'Qwen/Qwen2-1.5B-Instruct',
 'native_executed': False,
 'original_source': {'bytes': 17991,
                     'path': 'development_snapshots/canonical_raw_acquisition_source_20261018/acquire_raw.py',
                     'sha256': '4cff91b1a5e76a6a1701426fd1e6cb1f8db32ee8b7e762bb17575364b12d932a'},
 'payload_bytes': 789504,
 'providers_generated': False,
 'request_count': 2,
 'requests': [{'bytes': 786432,
               'end': 824967,
               'index': 0,
               'segment_index': 0,
               'sha256': '3cdd8eecf1d0948c6ebf40ca947875b7b706521733fa3107e934d3815e45c014',
               'start': 38536,
               'tensor': 'embed_tokens.rows_0_255'},
              {'bytes': 3072,
               'end': 466788999,
               'index': 1,
               'segment_index': 0,
               'sha256': 'ea77d5968e396420086f0c6c45c08df4ca4228e0c8a0be5d6ec5d0d247110a0e',
               'start': 466785928,
               'tensor': 'input_layernorm.weight'}],
 'revision': 'ba1cf1846d7df0a0591d6c00649f57e798519da8',
 'rtl_executed': False,
 'schema': 1,
 'source_plan': {'bytes': 14096,
                 'platform_api_evidence': {'bytes': 635,
                                           'path': 'PLATFORM_API_EVIDENCE.json',
                                           'scope': 'safe public projection of a single official '
                                                    'small metadata API observation; original body '
                                                    'not retained; no raw execution proof',
                                           'sha256': 'e44c899d4cb57dfb13bca3723e0640ab9e0872d7738a17722d7b6b8133e2c53f',
                                           'source_evidence_sha256': 'c45183b3d77308fda8d984f45d3d04529a1d5dfc0ca491b359e9aea3a16dc4ec'},
                 'sha256': '7af00f7b0ebe36a2d31cd18de72ff9da487197eb91ab671cb60a53b2c076d220',
                 'source_commit': '9f1ca820c6d2ca241eea9bbd38457f60849994b2',
                 'sources': [{'bytes': 11221,
                              'git_blob': '841e9877577c15959f52cde584b63481cf32c562',
                              'path': 'config/payload_pins/qwen2_layer0.json',
                              'sha256': '190e1fca0edff7c783c6981a6759f57162e63c4754ffc0f3481df64de9d06f88'},
                             {'bytes': 5109,
                              'git_blob': '5f0236a242438d37d51e1d84a630a74a90c492bc',
                              'path': 'config/upstream/weight_headers/qwen2_1p5b/manifest.json',
                              'sha256': '46818a6fde79b4bff4615abc38cca7d8cb9386cdd0298bc07c403cb3d2ceab25'},
                             {'bytes': 11555,
                              'git_blob': '1905761c3cc4c46d44c143751bc09861799f2fc6',
                              'path': 'scripts/qwen2_layer0_payload.py',
                              'sha256': '202b73649dfceed5e0d8ec73fd0b1e9f0de96d936141e3d9808d5e10d5c1beb9'},
                             {'bytes': 7517,
                              'git_blob': '1ecfbbcee837efd30eb6748ecd18d849cf7e86d1',
                              'path': 'src/heteronpu/pinned_block_payload.py',
                              'sha256': 'db35754b316c97b13915cb6a54d0746ce3d95f9193b0e2cb760f47d1fa198c30'},
                             {'bytes': 6626,
                              'git_blob': '1b412a21f95c6ec9200aa5cf2313881181bea6e1',
                              'path': 'src/heteronpu/pinned_gdn_payload.py',
                              'sha256': '0ca49fdfccd3c6dbd9e7dfd7809229d46e05b3cd9de46007ed0ad013b786b01b'}]},
 'status': 'RAW2_ONLY',
 'tensors': [{'bytes': 786432,
              'dtype': 'BF16',
              'end': 824967,
              'local_name': 'embed_tokens.rows_0_255',
              'sha256': '3cdd8eecf1d0948c6ebf40ca947875b7b706521733fa3107e934d3815e45c014',
              'shape': [256, 1536],
              'start': 38536},
             {'bytes': 3072,
              'dtype': 'BF16',
              'end': 466788999,
              'local_name': 'input_layernorm.weight',
              'sha256': 'ea77d5968e396420086f0c6c45c08df4ca4228e0c8a0be5d6ec5d0d247110a0e',
              'shape': [1536],
              'start': 466785928}],
 'whole_checkpoint_sha256_verified': False,
 'whole_file_bytes': 3087467144}

SAFE_MARKERS = frozenset(
    json.dumps({"status": "RAW2_REFUSED", "code": code}, sort_keys=True, separators=(",", ":"))
    for code in set(ORIGINAL_FAILURE_CODES.values()) | {"UNEXPECTED"}
)
SOURCE_ONLY_MARKER = '{"status":"SOURCE_CHECK_ONLY","selected_tensors":2,"requests":2,"bytes":789504,"raw_GETs":0}'
SUCCESS_MARKER = '{"status":"RAW2_ONLY","selected_tensors":2,"requests":2,"bytes":789504}'


class BootstrapRefused(ValueError):
    """Private bootstrap failure; public classification is always UNEXPECTED."""


def guard(condition):
    if not condition:
        raise BootstrapRefused()


def current_deadline(deadline, original=None):
    valid = (type(deadline) in (int, float) and math.isfinite(deadline)
             and 0 < deadline - time.monotonic() <= MAX_WALL_SECONDS)
    if original is None:
        guard(valid)
    else:
        original.require(valid, "shared wall deadline exceeded")


def load_original(repo):
    """Hash the one bounded buffer, then compile that identical buffer once."""
    repo = Path(repo)
    guard(repo.is_absolute())
    source = repo / ORIGINAL_RELATIVE
    for part in (source, *source.parents):
        guard(not part.is_symlink())
    with source.open("rb") as stream:
        info = os.fstat(stream.fileno())
        guard(stat.S_ISREG(info.st_mode) and info.st_size == ORIGINAL_BYTES)
        raw = stream.read(ORIGINAL_BYTES + 1)
    guard(len(raw) == ORIGINAL_BYTES and hashlib.sha256(raw).hexdigest() == ORIGINAL_SHA256)
    module = types.ModuleType("fixed_original_raw_acquirer")
    module.__file__ = str(source)
    exec(compile(raw, str(source), "exec", dont_inherit=True), module.__dict__)
    guard(module.PLAN_BYTES == PLAN_BYTES and module.PLAN_SHA256 == PLAN_SHA256)
    return module


def fixed_selection(original, plan):
    """Closed exact two-row selection; never accepts caller-provided subsets."""
    tensors = [
        {"local_name": "embed_tokens.rows_0_255", "dtype": "BF16", "shape": [256, 1536],
         "start": 38536, "end": 824967, "bytes": 786432,
         "sha256": "3cdd8eecf1d0948c6ebf40ca947875b7b706521733fa3107e934d3815e45c014"},
        {"local_name": "input_layernorm.weight", "dtype": "BF16", "shape": [1536],
         "start": 466785928, "end": 466788999, "bytes": 3072,
         "sha256": "ea77d5968e396420086f0c6c45c08df4ca4228e0c8a0be5d6ec5d0d247110a0e"},
    ]
    requests = [
        {"index": 0, "tensor": "embed_tokens.rows_0_255", "segment_index": 0,
         "start": 38536, "end": 824967, "bytes": 786432,
         "sha256": "3cdd8eecf1d0948c6ebf40ca947875b7b706521733fa3107e934d3815e45c014"},
        {"index": 1, "tensor": "input_layernorm.weight", "segment_index": 0,
         "start": 466785928, "end": 466788999, "bytes": 3072,
         "sha256": "ea77d5968e396420086f0c6c45c08df4ca4228e0c8a0be5d6ec5d0d247110a0e"},
    ]
    # Canonical JSON equality includes every key and distinguishes booleans/floats.
    original.require(type(plan["raw_tensors"]) is list and len(plan["raw_tensors"]) == 13
                     and original.json_bytes(plan["raw_tensors"][:2]) == original.json_bytes(tensors),
                     "tensor plan drift")
    original.require(type(plan["requests"]) is list and len(plan["requests"]) == 22
                     and original.json_bytes(plan["requests"][:2]) == original.json_bytes(requests),
                     "request plan drift")
    original.require(sum(row["bytes"] for row in requests) == PAYLOAD_BYTES,
                     "fixed acquisition budget drift")
    return tensors, requests


def collect_raw2(original, plan, helpers, shard, output, deadline):
    tensors, requests = fixed_selection(original, plan)
    current_deadline(deadline, original)
    opener = original.strict_opener(deadline)
    completed = []
    for spec in requests:
        current_deadline(deadline, original)
        raw, receipt = helpers["fetch_range"](plan["url"], spec["start"], spec["end"],
                                              plan["whole_file_bytes"], opener=opener)
        current_deadline(deadline, original)
        original.save_segment(output, spec, raw, receipt, helpers["validate_http"], shard)
        current_deadline(deadline, original)
        del raw
        completed.append(spec["index"])
    for tensor, spec in zip(tensors, requests, strict=True):
        current_deadline(deadline, original)
        original.assemble_tensor(output, tensor, [spec], helpers["validate_http"], shard)
        current_deadline(deadline, original)
    for tensor in tensors:
        current_deadline(deadline, original)
        original.verify_tensor(output / "tensors" / (tensor["local_name"] + ".bin"), tensor)
        current_deadline(deadline, original)
    report = json.loads(json.dumps(FIXED_RECEIPT, allow_nan=False))
    original.require(report["completed_request_indices"] == completed, "request plan drift")
    original.require(original.json_bytes(report["tensors"]) == original.json_bytes(tensors)
                     and original.json_bytes(report["requests"]) == original.json_bytes(requests),
                     "tensor plan drift")
    current_deadline(deadline, original)
    original.disk_check(output, len(original.json_bytes(report)))
    current_deadline(deadline, original)
    original.atomic_json(output / "RAW2_RECEIPT.json", report)
    current_deadline(deadline, original)
    return report


def _private_read(path, maximum, exact=None):
    for part in (path, *path.parents):
        guard(not part.is_symlink())
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        guard(stat.S_ISREG(info.st_mode) and info.st_size <= maximum)
        if exact is not None:
            guard(info.st_size == exact)
        raw = stream.read(maximum + 1)
    guard(len(raw) <= maximum and (exact is None or len(raw) == exact))
    return raw


def verify_receipt(raw2_dir):
    """Read-only parent postflight: exact private identity and both raw hashes.

    Returns only fixed public constants. Raises on any missing/drifted input.
    Never imports project/native code and never performs a network operation.
    """
    output = Path(raw2_dir)
    guard(output.is_absolute())
    for part in (output, *output.parents):
        guard(not part.is_symlink())
    info = output.stat()
    guard(stat.S_ISDIR(info.st_mode) and info.st_mode & 0o077 == 0)
    guard({p.name for p in output.iterdir()} == {"segments", "tensors", "RAW2_RECEIPT.json"})
    def pairs(items):
        result = {}
        for key, value in items:
            guard(key not in result)
            result[key] = value
        return result
    def invalid(value):
        raise BootstrapRefused()
    raw = _private_read(output / "RAW2_RECEIPT.json", 16384)
    receipt = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    guard(canonical(receipt) == canonical(FIXED_RECEIPT))
    tensors_dir = output / "tensors"
    guard(not tensors_dir.is_symlink() and tensors_dir.is_dir())
    guard({p.name for p in tensors_dir.iterdir()} ==
          {tensor["local_name"] + ".bin" for tensor in FIXED_RECEIPT["tensors"]})
    segments_dir = output / "segments"
    guard(not segments_dir.is_symlink() and segments_dir.is_dir())
    guard({p.name for p in segments_dir.iterdir()} == {"00", "01"})
    for tensor in FIXED_RECEIPT["tensors"]:
        body = _private_read(tensors_dir / (tensor["local_name"] + ".bin"), tensor["bytes"], tensor["bytes"])
        guard(hashlib.sha256(body).hexdigest() == tensor["sha256"])
        del body
    return {"status": "RAW2_ONLY", "selected_tensors": 2, "requests": 2, "bytes": PAYLOAD_BYTES}


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        raise BootstrapRefused()


def public_failure_code(error, original):
    if original is not None and type(error) is original.Refused:
        # No str(error): exact primitive arguments only, never custom formatting.
        if len(error.args) == 1 and type(error.args[0]) is str:
            return ORIGINAL_FAILURE_CODES.get(error.args[0], "UNEXPECTED")
    return "UNEXPECTED"


def main(argv=None):
    original = None
    try:
        parser = QuietParser(add_help=False, allow_abbrev=False)
        parser.add_argument("--repo", type=Path, required=True)
        parser.add_argument("--out", type=Path)
        parser.add_argument("--deadline", type=float)
        parser.add_argument("--execute", action="store_true")
        args = parser.parse_args(argv)
        guard(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode)
        guard(args.repo.is_absolute())
        if args.out is not None:
            guard(args.out.is_absolute())
        if args.execute:
            guard(args.out is not None and args.deadline is not None)
        deadline = args.deadline if args.deadline is not None else time.monotonic() + MAX_WALL_SECONDS
        current_deadline(deadline)
        original = load_original(args.repo)
        current_deadline(deadline, original)
        plan, helpers, shard = original.check_sources(args.repo, Path(original.__file__).with_name("ACQUISITION_PLAN.json"))
        current_deadline(deadline, original)
        fixed_selection(original, plan)
        current_deadline(deadline, original)
        if not args.execute:
            print(SOURCE_ONLY_MARKER)
            return 0
        output = original.prepare_output(args.repo, args.out)
        current_deadline(deadline, original)
        collect_raw2(original, plan, helpers, shard, output, deadline)
        current_deadline(deadline, original)
        print(SUCCESS_MARKER)
        return 0
    except BaseException as error:
        print(json.dumps({"status": "RAW2_REFUSED", "code": public_failure_code(error, original)},
                         sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

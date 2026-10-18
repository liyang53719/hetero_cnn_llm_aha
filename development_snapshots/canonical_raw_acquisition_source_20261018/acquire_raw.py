#!/usr/bin/env python3
"""Fixed Qwen2 raw13 acquisition. Default is source check only; no project imports."""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PLAN_BYTES = 14096
PLAN_SHA256 = "7af00f7b0ebe36a2d31cd18de72ff9da487197eb91ab671cb60a53b2c076d220"
MAX_RANGE_BYTES = 8388608
DISK_CAP = 268435456
META_RESERVE = 1048576


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def invalid(_):
        raise Refused("non-finite JSON number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def no_symlinks(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        require(not part.is_symlink(), "symlink path refused")
    return path


def bounded_read(path, limit, expected_size=None):
    path = no_symlinks(path)
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit,
                "nonregular or oversized input")
        if expected_size is not None:
            require(info.st_size == expected_size, "input size drift")
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "input grew beyond bound")
    if expected_size is not None:
        require(len(raw) == expected_size, "input changed length")
    return raw


def helpers_from_sources(sources):
    """Only these exact FunctionDefs are executed from the verified same bytes."""
    namespace = {"__builtins__": __builtins__, "require": require, "sha256": sha256,
                 "MAX_RANGE_BYTES": MAX_RANGE_BYTES, "urllib": urllib,
                 "datetime": datetime, "timezone": timezone}
    choices = {"src/heteronpu/pinned_block_payload.py": ["fetch_range"],
               "src/heteronpu/pinned_gdn_payload.py": ["ranges"],
               "scripts/qwen2_layer0_payload.py": ["_same", "validate_http"]}
    for path, names in choices.items():
        tree = ast.parse(sources[path], filename=path)
        functions = [node for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name in names]
        require([node.name for node in functions] == names, "helper definitions drift")
        prefix = ast.parse("from __future__ import annotations\n").body
        selected = ast.fix_missing_locations(ast.Module(body=prefix + functions, type_ignores=[]))
        exec(compile(selected, path, "exec", dont_inherit=True), namespace)
    return namespace


def check_sources(repo, plan_path):
    raw = bounded_read(plan_path, PLAN_BYTES, PLAN_BYTES)
    require(sha256(raw) == PLAN_SHA256, "fixed acquisition plan hash drift")
    plan = strict_json(raw)
    evidence_pin = plan["platform_api_evidence"]
    evidence_raw = bounded_read(plan_path.parent / evidence_pin["path"], evidence_pin["bytes"], evidence_pin["bytes"])
    require(sha256(evidence_raw) == evidence_pin["sha256"], "platform API evidence hash drift")
    evidence = strict_json(evidence_raw)
    probe = evidence["probe"]
    require(probe["status"] == "METADATA_ONLY_OK" and probe["http_status"] == 200
            and probe["model_id_matches"] is True and probe["revision_matches"] is True
            and probe["final_host_is_huggingface"] is True and evidence["raw_weight_requests"] == 0,
            "platform metadata evidence identity drift")
    repo = no_symlinks(repo).resolve(strict=True)
    sources = {}
    for expected in plan["sources"]:
        relative = Path(expected["path"])
        require(not relative.is_absolute() and ".." not in relative.parts, "source path escape")
        data = bounded_read(repo / relative, expected["bytes"], expected["bytes"])
        require(sha256(data) == expected["sha256"], "source SHA256 drift: " + str(relative))
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(blob == expected["git_blob"], "source Git blob drift")
        sources[str(relative)] = data
    helpers = helpers_from_sources(sources)
    pin = strict_json(sources["config/payload_pins/qwen2_layer0.json"])
    bundle = strict_json(sources["config/upstream/weight_headers/qwen2_1p5b/manifest.json"])
    same = helpers["_same"]
    require(same(pin, {key: plan[key] for key in ("model_id", "revision", "layer_id", "header_sha256")}),
            "raw pin identity drift")
    require(same(bundle, {key: plan[key] for key in ("model_id", "revision")}), "bundle identity drift")
    require(len(bundle["shards"]) == 1, "shard count drift")
    shard = bundle["shards"][0]
    require(shard["url"] == plan["url"] and shard["file_bytes"] == plan["whole_file_bytes"]
            and shard["header"]["sha256"] == plan["header_sha256"], "shard identity drift")
    tensors, requests = [], []
    for tensor in pin["tensors"]:
        tensors.append({k: tensor[k] for k in ("local_name", "dtype", "shape", "start", "end", "bytes", "sha256")})
        require(tensor["dtype"] == "BF16" and tensor["bytes"] == tensor["end"] - tensor["start"] + 1,
                "tensor dtype/size drift")
        spans = list(helpers["ranges"](tensor))
        require(len(spans) == len(tensor["segments"]), "segment count drift")
        for i, (segment, span) in enumerate(zip(tensor["segments"], spans, strict=True)):
            start, end = span
            require(same(segment, {"start": start, "end": end, "bytes": end - start + 1}), "segment geometry drift")
            requests.append({**segment, "index": len(requests), "tensor": tensor["local_name"], "segment_index": i})
    require(same(plan["raw_tensors"], tensors) and same(tensors, plan["raw_tensors"]), "tensor plan drift")
    require(same(plan["requests"], requests) and same(requests, plan["requests"]), "request plan drift")
    require(len(tensors) == 13 and len(requests) == 22 and sum(s["bytes"] for s in requests) == 94382080,
            "fixed acquisition budget drift")
    require(pin["payload_bytes"] == 94382080 and 2 * pin["payload_bytes"] + META_RESERVE < DISK_CAP,
            "retained cache budget drift")
    return plan, helpers, shard


def allowed_url(url):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == "https" and parsed.hostname in ("huggingface.co", "us.aws.cdn.hf.co")
            and parsed.port in (None, 443) and parsed.username is None and parsed.password is None
            and not parsed.fragment, "unapproved redirect URL")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def strict_opener(deadline, transport=None):
    # Delegate normal platform transit; never add application credentials or a direct fallback.
    # Target URLs remain fixed/allowlisted. Redirect bodies are never read.
    transport = transport or urllib.request.build_opener(NoRedirect())
    def open_range(request, timeout):
        original_headers = dict(request.header_items())
        url = request.full_url
        for hop in range(5):
            allowed_url(url)
            remaining = deadline - time.monotonic()
            require(remaining > 0, "shared wall deadline exceeded")
            req = urllib.request.Request(url, headers=original_headers, method="GET")
            try:
                response = transport.open(req, timeout=min(timeout, 90, remaining))
            except urllib.error.HTTPError as error:
                location = error.headers.get("Location")
                code = error.code
                error.close()
                require(code in (301, 302, 303, 307, 308) and location and hop < 4,
                        "HTTP error or redirect limit; no retry")
                url = urllib.parse.urljoin(url, location)
                continue
            try:
                allowed_url(response.geturl())
                # Reject ambiguous/framed/encoded responses before the original helper reads.
                for key in ("Content-Range", "Content-Length"):
                    require(len(response.headers.get_all(key, [])) == 1, "missing or duplicate range header")
                require(len(response.headers.get_all("Content-Encoding", [])) <= 1
                        and not response.headers.get_all("Transfer-Encoding", []), "ambiguous transport framing")
                return response
            except BaseException:
                response.close()
                raise
        raise Refused("redirect limit")
    return open_range


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def atomic_json(path, value):
    temporary = path.with_name("." + path.name + ".pending")
    require(not path.exists(), "refuse output overwrite")
    write_new(temporary, json_bytes(value))
    os.rename(temporary, path)
    sync_dir(path.parent)


def disk_check(output, additional=0):
    total = 0
    for path in output.rglob("*"):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode), "cache symlink refused")
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "nonregular cache refused")
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
    require(total + additional + META_RESERVE <= DISK_CAP, "output disk budget exceeded")
    require(shutil.disk_usage(output).free >= additional + META_RESERVE, "insufficient remaining disk")
    return total


def save_segment(output, spec, raw, receipt, validate_http, shard):
    validate_http(shard, spec["start"], spec["end"], raw, receipt, spec["sha256"])
    disk_check(output, len(raw) + 8192)
    directory = output / "segments" / f'{spec["index"]:02d}'
    pending = directory.with_name("." + directory.name + ".pending")
    pending.mkdir()
    write_new(pending / "payload.bin", raw)
    write_new(pending / "receipt.json", json_bytes(receipt))
    sync_dir(pending)
    require(not directory.exists(), "segment destination already exists")
    os.rename(pending, directory)
    sync_dir(directory.parent)


def cached_segment(output, spec, validate_http, shard):
    directory = output / "segments" / f'{spec["index"]:02d}'
    raw = bounded_read(directory / "payload.bin", spec["bytes"], spec["bytes"])
    receipt = strict_json(bounded_read(directory / "receipt.json", 8192))
    validate_http(shard, spec["start"], spec["end"], raw, receipt, spec["sha256"])
    return raw


def verify_tensor(path, expected):
    no_symlinks(path)
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        require(os.fstat(stream.fileno()).st_size == expected["bytes"], "tensor size drift")
        while True:
            raw = stream.read(min(1048576, expected["bytes"] - count + 1))
            if not raw:
                break
            count += len(raw)
            require(count <= expected["bytes"], "tensor too long")
            digest.update(raw)
    require(count == expected["bytes"] and digest.hexdigest() == expected["sha256"], "tensor hash drift")


def assemble_tensor(output, tensor, segments, validate_http, shard):
    disk_check(output, tensor["bytes"])
    target = output / "tensors" / (tensor["local_name"] + ".bin")
    pending = target.with_name("." + target.name + ".pending")
    require(not target.exists(), "tensor destination already exists")
    digest, count = hashlib.sha256(), 0
    with pending.open("xb") as stream:
        for spec in segments:
            raw = cached_segment(output, spec, validate_http, shard)
            count += len(raw)
            require(count <= tensor["bytes"], "assembled tensor too long")
            digest.update(raw)
            stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(count == tensor["bytes"] and digest.hexdigest() == tensor["sha256"], "assembled tensor SHA mismatch")
    verify_tensor(pending, tensor)
    os.rename(pending, target)
    sync_dir(target.parent)


def prepare_output(repo, output):
    output = no_symlinks(output)
    require(not output.exists() and output.parent.is_dir(), "output must be a new directory under an existing parent")
    require(not output.is_relative_to(repo.resolve()) and not repo.resolve().is_relative_to(output), "output must be outside repository")
    require("work" not in output.parts, "historical work tree refused")
    require(shutil.disk_usage(output.parent).free >= 536870912, "need at least 512 MiB free disk")
    output.mkdir(mode=0o700)
    (output / "segments").mkdir()
    (output / "tensors").mkdir()
    sync_dir(output.parent)
    return output


def collect_fixed(plan, helpers, shard, output, opener):
    completed = []
    for spec in plan["requests"]:
        raw, receipt = helpers["fetch_range"](plan["url"], spec["start"], spec["end"], plan["whole_file_bytes"], opener=opener)
        save_segment(output, spec, raw, receipt, helpers["validate_http"], shard)
        del raw
        completed.append(spec["index"])
    for tensor in plan["raw_tensors"]:
        segments = [s for s in plan["requests"] if s["tensor"] == tensor["local_name"]]
        assemble_tensor(output, tensor, segments, helpers["validate_http"], shard)
    for tensor in plan["raw_tensors"]:
        verify_tensor(output / "tensors" / (tensor["local_name"] + ".bin"), tensor)
    report = {"schema": 1, "status": "ACQUIRED_FIXED_RAW13_ONLY", "plan_sha256": PLAN_SHA256,
              "model_id": plan["model_id"], "revision": plan["revision"], "payload_bytes": 94382080,
              "completed_segment_indices": completed, "tensors": plan["raw_tensors"],
              "whole_checkpoint_sha256_verified": False, "providers_generated": False,
              "canonical_loader_executed": False, "rtl_executed": False}
    disk_check(output, len(json_bytes(report)))
    atomic_json(output / "ACQUIRED.json", report)
    return report


def wall_expired(_signum, _frame):
    raise TimeoutError("shared wall deadline exceeded")


def require_alarm_unblocked():
    # Query only. Never unblock an inherited mask or change the caller's policy.
    require(hasattr(signal, "pthread_sigmask"), "cannot inspect signal mask")
    blocked = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    require(signal.SIGALRM not in blocked, "inherited SIGALRM block defeats shared deadline")


def main(argv=None):
    start = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true", help="raw GET; only after separate review/authorization")
    args = parser.parse_args(argv)
    if args.execute:
        require_alarm_unblocked()
    plan, helpers, shard = check_sources(args.repo, Path(__file__).with_name("ACQUISITION_PLAN.json"))
    if not args.execute:
        print(json.dumps({"status": "SOURCE_CHECK_ONLY", "tensors": 13, "ranges": 22, "bytes": 94382080, "raw_GETs": 0}))
        return 0
    require(args.output is not None, "--execute requires --output")
    # Shared wall limit includes earlier source preflight; never increases an existing AS cap.
    remaining = 900 - (time.monotonic() - start)
    require(remaining > 0 and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "deadline/timer conflict")
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    caps = [536870912] + [x for x in (soft, hard) if x != resource.RLIM_INFINITY]
    resource.setrlimit(resource.RLIMIT_AS, (min(caps), hard))
    previous = signal.signal(signal.SIGALRM, wall_expired)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    output = None
    try:
        output = prepare_output(args.repo, args.output)
        atomic_json(output / "RUN_PLAN.json", {"plan_sha256": PLAN_SHA256, "source_commit": plan["source_commit"],
                    "status": "INCOMPLETE_UNTIL_ACQUIRED_JSON", "started_at": datetime.now(timezone.utc).isoformat()})
        report = collect_fixed(plan, helpers, shard, output, strict_opener(start + 900))
        print(json.dumps({"status": report["status"], "tensors": 13, "ranges": 22, "bytes": 94382080}))
        return 0
    except BaseException as error:
        # Never print exception URLs (redirect query tokens); retain every existing file.
        if output is not None:
            try:
                atomic_json(output / "FAILURE.json", {"status": "FAILED_PRESERVED_NO_RETRY", "exception_type": type(error).__name__,
                    "completed_segments": len([p for p in (output / "segments").iterdir() if p.name.isdigit()]),
                    "has_completion_manifest": (output / "ACQUIRED.json").exists()})
            except BaseException:
                pass
        print(json.dumps({"status": "FAILED_PRESERVED_NO_RETRY", "exception_type": type(error).__name__}), file=sys.stderr)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "PREFLIGHT_REFUSED", "exception_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
"""Capture pinned official complete L0 software reference, never owner/RTL evidence.

Torch is imported only by run(). The validator and its tests need stdlib only.
Run M16 first, then M128, in separate processes and fresh output directories.
M16 uses the first 16 tokens of each original window: its second call has only
16 tokens of actual cache history and is NOT a cold128/carried128 reference.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import functools
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
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
SCOPE = "PINNED_OFFICIAL_COMPLETE_L0_CHUNK_REFERENCE_ONLY"
ARCHIVE_SHA256 = "15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d"
CACHE_SHA256 = "abdcb0ae88aa5b924ef7d76879db680e9af8f3ec1dafbba7ce446ecb521a944b"
MASKING_SHA256 = "af3d84dfe82a0b57c40625c89fb32b2cd6bf7351432ee5e76a9e8eac4289575b"
WIDTHS = {"BF16": 2, "F32": 4}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_record(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=sha(raw))


def encoded(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"


def validate_tensor_record(record, directory=None):
    """Reject ambiguous shapes, storage dtypes, path escapes and altered bytes."""
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
    return record


def validate_manifest(manifest, directory=None):
    """Portable capture contract; does not import Torch or execute reference math."""
    require(type(manifest) is dict and type(manifest.get("schema_version")) is int and
            manifest["schema_version"] == 1 and manifest.get("scope") == SCOPE, "capture manifest identity drift")
    m = manifest.get("query_tokens")
    require(type(m) is int and m in (16, 128), "unsupported capture length")
    expected_identity = "cold128_then_carried128" if m == 128 else "cold16_then_carried16_from_second_window"
    require(manifest.get("case_identity") == expected_identity, "capture case identity drift")
    require(manifest.get("hardware_executed") is False and manifest.get("owner_executed") is False and
            manifest.get("official_full_model_executed") is False, "capture scope overclaim")
    tensors = manifest.get("tensors")
    require(type(tensors) is dict and tensors, "missing captured tensors")
    files = []
    for key, record in tensors.items():
        require(type(key) is str and key, "invalid tensor key")
        validate_tensor_record(record, directory)
        files.append(record["file"])
    require(len(set(files)) == len(files), "duplicate captured tensor file")
    cases = manifest.get("cases")
    require(type(cases) is list and len(cases) == 2, "two actual cache calls required")
    for i, case in enumerate(cases):
        require(type(case) is dict and type(case.get("past_tokens")) is int and case["past_tokens"] == i * m,
                "actual past token count drift")
        require(case.get("source_token_slice") == [i * 128, i * 128 + m], "original input window drift")
        require(case.get("cache_object_id") == cases[0].get("cache_object_id") and
                type(case.get("cache_object_id")) is int, "same DynamicCache object required")
        prior = case.get("prior_cache")
        final = case.get("final_cache")
        require(type(prior) is dict and type(final) is dict, "cache snapshots required")
        for which, shape, dtype in (("conv_state", [1, 6144, 4], "BF16"),
                                     ("recurrent_state", [1, 16, 128, 128], "F32")):
            for key in ([final.get(which)] if i == 0 else [prior.get(which), final.get(which)]):
                require(key in tensors and tensors[key]["shape"] == shape and tensors[key]["dtype"] == dtype,
                        "cache shape/dtype drift")
            if i == 0:
                require(prior.get(which) is None, "cold cache must really be absent")
            else:
                require(tensors[prior[which]]["sha256"] == tensors[cases[0]["final_cache"][which]]["sha256"],
                        "prior cache does not match cold final cache")
        for name in ("input", "output"):
            key = case.get(name)
            require(key in tensors and tensors[key]["shape"] == [1, m, 1024] and tensors[key]["dtype"] == "BF16",
                    "layer input/output shape/dtype drift")
        calls = case.get("chunk_calls")
        require(type(calls) is list and len(calls) == 1, "one actual chunk call per window required")
        call = calls[0]
        require(type(call.get("chunk_size")) is int and call["chunk_size"] == 64 and
                type(call.get("num_chunks")) is int and call["num_chunks"] == (m + 63) // 64 and
                call.get("sequence_length") == m and call.get("pad_size") == (64 - m % 64) % 64,
                "actual official chunk geometry drift")
        require(call.get("official_function_body_observed") is True and
                call.get("initial_state_is_actual_prior_cache") is True, "unobserved chunk/cache execution")
        initial = call.get("initial_state")
        require(initial is None if i == 0 else initial in tensors, "chunk initial state missing or invented")
        if i:
            require(tensors[initial]["sha256"] == tensors[prior["recurrent_state"]]["sha256"],
                    "chunk initial state differs from prior cache")
        state = call.get("final_state")
        require(state in tensors and tensors[state]["dtype"] == "F32" and
                tensors[state]["sha256"] == tensors[final["recurrent_state"]]["sha256"],
                "chunk final state differs from actual cache")
    return manifest


def _budget():
    """One CPU, one thread, hard 120-second CPU/wall limits, before Torch import."""
    require("torch" not in sys.modules, "configure runtime before importing Torch")
    require(os.environ.get("ATEN_CPU_CAPABILITY") == "default", "ATEN_CPU_CAPABILITY must be lowercase default")
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    affinity = os.sched_getaffinity(0)
    require(bool(affinity), "no available CPU")
    os.sched_setaffinity(0, {min(affinity)})
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    def expired(signum, frame):
        raise TimeoutError("native capture exceeded hard 120-second wall budget")
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(120)


def run(root, fixture, runtime, output, m):
    root, fixture, runtime, output = map(lambda p: Path(p).resolve(), (root, fixture, runtime, output))
    require(type(m) is int and m in (16, 128), "only M16 and M128 captures supported")
    require(not output.exists(), "fresh nonexistent capture output required; never overwrite or rerun silently")
    _budget()
    start = time.monotonic()
    output.mkdir(parents=True)
    try:
        return _run(root, fixture, runtime, output, m, start)
    except BaseException as exc:
        (output / "failure.json").write_bytes(encoded(dict(status="FAILED_NATIVE_CAPTURE", query_tokens=m,
            exception_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc(),
            elapsed_seconds=time.monotonic() - start, runner=file_record(__file__),
            partial_outputs_preserved=True, numerical_acceptance_relaxed=False)))
        raise
    finally:
        signal.alarm(0)


def _run(root, fixture, runtime, output, m, start):
    sys.path[:0] = [str(root), str(root / "src")]
    from candidates.qwen35_gdn_prefill.input_fixture import load_fixture
    from heteronpu.pinned_gdn_payload import load_payload, F32_NAMES

    fm, input_files = load_fixture(root, fixture)
    payload = Path(fm["sources"]["layer0_directory"])
    pm, raw_weights = load_payload(root, payload)
    receipt_path = runtime / "runtime_receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    require(receipt.get("status") == "PASS_ISOLATED_PINNED_RUNTIME_READY" and all(receipt["checks"].values()),
            "isolated runtime is not verified ready")
    runtime_files = {"runtime_receipt": file_record(receipt_path)}
    for name, record in receipt["artifacts"].items():
        actual = file_record(root / record["path"])
        require(actual["bytes"] == record["bytes"] and actual["sha256"] == record["sha256"], "runtime receipt artifact drift: " + name)
        runtime_files[name] = actual

    import torch
    import transformers.cache_utils as cache_source
    import transformers.masking_utils as masking_source
    from transformers.cache_utils import DynamicCache
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig

    require(sys.byteorder == "little", "raw artifact encoding requires little-endian host")
    require(torch.__version__ == "2.10.0+cpu", "Torch 2.10.0 CPU runtime required")
    require(Path(inspect.getfile(official)).resolve().is_relative_to(runtime / "site-packages"), "official module outside isolated runtime")
    profile = json.loads((root / "config/model_profiles/qwen3_5_0p8b.json").read_bytes())
    config_path = root / "config/upstream/qwen3_5_0p8b/config.json"
    require(sha(config_path.read_bytes()) == profile["config_sha256"], "original model config drift")
    sources = {"modeling": Path(inspect.getfile(official)), "cache": Path(inspect.getfile(cache_source)),
               "masking": Path(inspect.getfile(masking_source)), "configuration": Path(inspect.getfile(Qwen3_5TextConfig))}
    hashes = dict(modeling=profile["transformers_source"]["sha256"], cache=CACHE_SHA256, masking=MASKING_SHA256,
                  configuration=sha((root / "config/upstream/qwen3_5_0p8b/configuration_qwen3_5.py").read_bytes()))
    require(all(sha(path.read_bytes()) == hashes[name] for name, path in sources.items()), "installed official source drift")
    direct_url = json.loads(importlib.metadata.distribution("transformers").read_text("direct_url.json") or "{}")
    require(direct_url.get("url") == "https://github.com/huggingface/transformers/archive/" +
            profile["transformers_source"]["commit"] + ".zip" and
            direct_url.get("archive_info", {}).get("hashes", {}).get("sha256") == ARCHIVE_SHA256,
            "pinned Transformers archive identity drift")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    raw_config = json.loads(config_path.read_bytes())["text_config"]
    config = Qwen3_5TextConfig.from_dict(raw_config)
    config_before = config.to_dict()
    require(config.num_hidden_layers == 24 and config.layer_types[0] == "linear_attention", "complete official config drift")
    # Meta construction avoids creating temporary FP32 weights or modifying any
    # official layer/config. assign=True preserves the checkpoint's 14 dtypes.
    with torch.device("meta"):
        layer = official.Qwen3_5DecoderLayer(config, layer_idx=0)
    values = {}
    for record in pm["tensors"]:
        name = record["local_name"]
        dtype = torch.float32 if name in F32_NAMES else torch.bfloat16
        values[name] = torch.frombuffer(bytearray(raw_weights.pop(name)), dtype=dtype).reshape(record["shape"])
        require(torch.isfinite(values[name]).all().item(), "nonfinite checkpoint parameter: " + name)
    loaded = layer.load_state_dict(values, strict=True, assign=True)
    require(not loaded.missing_keys and not loaded.unexpected_keys, "incomplete official L0 parameter load")
    layer.eval()
    del raw_weights, values

    def raw(tensor):
        require(tensor.device.type == "cpu" and tensor.dtype in (torch.bfloat16, torch.float32), "unsupported capture tensor")
        return tensor.detach().contiguous().view(torch.uint8).numpy().tobytes()

    parameters = {}
    for record in pm["tensors"]:
        name = record["local_name"]
        tensor = dict(layer.named_parameters())[name]
        require(str(tensor.dtype) == ("torch.float32" if name in F32_NAMES else "torch.bfloat16"), "parameter dtype altered: " + name)
        require(list(tensor.shape) == record["shape"] and sha(raw(tensor)) == record["sha256"], "loaded parameter bytes drift: " + name)
        parameters[name] = {k: record[k] for k in ("shape", "dtype", "bytes", "sha256")}
    require(len(parameters) == len(list(layer.named_parameters())) == 14, "parameter inventory drift")

    tensors, cases, hooks, events = {}, [], [], []
    active = {}
    cache = DynamicCache(config=config)
    capture_bytes = 0

    def save(key, tensor):
        nonlocal capture_bytes
        if tensor is None:
            return None
        require(key not in tensors, "duplicate capture key: " + key)
        require(torch.isfinite(tensor).all().item(), "nonfinite official activation: " + key)
        data = raw(tensor)
        capture_bytes += len(data)
        require(capture_bytes <= 128 * 1024 * 1024, "activation capture exceeded 128 MiB disk budget")
        record = dict(file=f"{len(tensors):04d}." + ("bf16le" if tensor.dtype == torch.bfloat16 else "f32le"),
                      shape=list(tensor.shape), dtype="BF16" if tensor.dtype == torch.bfloat16 else "F32",
                      bytes=len(data), sha256=sha(data))
        (output / record["file"]).write_bytes(data)
        tensors[key] = validate_tensor_record(record)
        return key

    def tree(key, value):
        if isinstance(value, torch.Tensor):
            return {"tensor": save(key, value)}
        if isinstance(value, (tuple, list)):
            return [tree(key + f".{i}", v) for i, v in enumerate(value)]
        if isinstance(value, dict):
            return {k: tree(key + "." + k, v) for k, v in value.items()}
        if value is None or type(value) in (str, bool, int, float):
            return value
        require(value is cache, "unexpected opaque hook argument")
        return {"type": "DynamicCache", "object_id": id(value)}

    def snapshot(name):
        slot = cache.layers[0]
        return dict(conv_state=save(name + ".conv_state", slot.conv_states[0]),
                    recurrent_state=save(name + ".recurrent_state", slot.recurrent_states[0]),
                    has_previous_state=bool(cache.has_previous_state(0)), record_past=slot.record_past)

    module_names = list(dict(layer.named_modules()))
    counts = {name or "layer0": 0 for name in module_names}
    for name, module in layer.named_modules():
        name = name or "layer0"
        def before(module, args, kwargs, name=name):
            require(torch.is_inference_mode_enabled() and not torch.is_autocast_enabled("cpu"), "capture execution mode drift")
            call = counts[name]
            counts[name] += 1
            key = active["name"] + ".module." + name
            events.append(dict(case=active["name"], module=name, phase="input", invocation=call,
                               args=tree(key + ".args", args), kwargs=tree(key + ".kwargs", kwargs)))
            return None
        def after(module, args, kwargs, result, name=name):
            key = active["name"] + ".module." + name
            events.append(dict(case=active["name"], module=name, phase="output", result=tree(key + ".result", result)))
            return None
        hooks.append(module.register_forward_pre_hook(before, with_kwargs=True))
        hooks.append(module.register_forward_hook(after, with_kwargs=True))

    original_chunk = official.torch_chunk_gated_delta_rule
    original_conv = official.causal_conv1d_fn
    signature = inspect.signature(original_chunk)
    original_profile = sys.getprofile()
    require(original_profile is None, "unexpected existing Python profiler")
    official_path = str(sources["modeling"])

    def profiler(frame, event, arg):
        if event == "return" and frame.f_code.co_filename == official_path and frame.f_code.co_name == "torch_chunk_gated_delta_rule":
            call = active["chunk_calls"][-1]
            require(not call.get("official_function_body_observed", False), "multiple official chunk bodies per call")
            call.update({k: int(frame.f_locals[k]) for k in ("chunk_size", "num_chunks", "sequence_length", "pad_size")})
            call["official_function_body_observed"] = True

    @functools.wraps(original_chunk)
    def chunk(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = bound.arguments
        number = len(active["chunk_calls"])
        key = active["name"] + f".chunk{number}"
        require(number == 0, "more than one chunk invocation in a layer call")
        prior = cache.layers[0].recurrent_states[0]
        require(arguments["initial_state"] is prior, "chunk was not passed actual prior cache object")
        call = dict(inputs={name: save(key + "." + name, arguments[name]) for name in ("query", "key", "value", "g", "beta")},
                    initial_state=save(key + ".initial_state", arguments["initial_state"]),
                    initial_state_is_actual_prior_cache=True, output_final_state=arguments["output_final_state"],
                    use_qk_l2norm_in_kernel=arguments["use_qk_l2norm_in_kernel"])
        active["chunk_calls"].append(call)
        require(call["output_final_state"] is True and call["use_qk_l2norm_in_kernel"] is True, "official chunk flags drift")
        result = original_chunk(*args, **kwargs)  # original arguments, original arithmetic, unchanged return
        call["output"] = save(key + ".output", result[0])
        call["final_state"] = save(key + ".final_state", result[1])
        return result

    @functools.wraps(original_conv)
    def conv(*args, **kwargs):
        key = active["name"] + ".causal_conv1d_fn"
        hidden = args[0]
        call = dict(input=save(key + ".input", hidden), activation=kwargs.get("activation"),
                    includes_prior_history=active["past_tokens"] > 0)
        if active["past_tokens"]:
            prefix = raw(hidden[..., :4])
            require(sha(prefix) == tensors[active["prior_cache"]["conv_state"]]["sha256"],
                    "functional convolution did not receive actual prior history")
            call["prior_history_bit_exact"] = True
        require(list(hidden.shape) == [1, 6144, m + (4 if active["past_tokens"] else 0)], "conv history geometry drift")
        result = original_conv(*args, **kwargs)
        call["output"] = save(key + ".output", result)
        active["conv_calls"].append(call)
        return result

    official.torch_chunk_gated_delta_rule = chunk
    official.causal_conv1d_fn = conv
    try:
        for i, name in enumerate(("cold", "carried")):
            active = dict(name=name + str(m), source_token_slice=[i * 128, i * 128 + m],
                          past_tokens=i * m, cache_object_id=id(cache), chunk_calls=[], conv_calls=[])
            active["prior_cache"] = snapshot(active["name"] + ".prior_cache")
            input_name = fm["cases"][i]["input_file"]
            data = input_files[input_name][:m * 1024 * 2]
            x = torch.frombuffer(bytearray(data), dtype=torch.bfloat16).reshape(1, m, 1024)
            active["input"] = save(active["name"] + ".input", x)
            require(tensors[active["input"]]["sha256"] == sha(data), "input BF16 bytes drift")
            sys.setprofile(profiler)
            try:
                with torch.inference_mode(), torch.autocast(device_type="cpu", enabled=False):
                    y = layer(x, position_embeddings=None, attention_mask=None, past_key_values=cache)
            finally:
                sys.setprofile(original_profile)
            active["output"] = save(active["name"] + ".output", y)
            active["final_cache"] = snapshot(active["name"] + ".final_cache")
            require(len(active["conv_calls"]) == 1, "exactly one actual prefill convolution required")
            cases.append(active)
            print(json.dumps(dict(case=active["name"], status="CAPTURED", elapsed_seconds=round(time.monotonic() - start, 3))), flush=True)
    finally:
        official.torch_chunk_gated_delta_rule = original_chunk
        official.causal_conv1d_fn = original_conv
        sys.setprofile(original_profile)
        for hook in hooks:
            hook.remove()
    require(config.to_dict() == config_before, "original config was changed")
    require(not layer.training and all(not module.training for module in layer.modules()), "eval mode drift")
    source_files = {name: file_record(path) for name, path in sources.items()}
    source_files.update(runner=file_record(__file__), config=file_record(config_path),
                        input_fixture_loader=file_record(inspect.getfile(load_fixture)),
                        payload_loader=file_record(inspect.getfile(load_payload)))
    # Recheck the original fixture and all source bytes after execution. These
    # are identity checks, not an extra inference or a numeric replay claim.
    checked_fixture, _ = load_fixture(root, fixture)
    require(encoded(checked_fixture) == encoded(fm), "input fixture changed during capture")
    require(all(sha(path.read_bytes()) == hashes[name] for name, path in sources.items()), "official source changed during capture")
    report = dict(schema_version=1, scope=SCOPE, status="CAPTURED_OFFICIAL_SOFTWARE_REFERENCE_ONLY",
        created_at=datetime.now(timezone.utc).isoformat(), model_id=fm["model_id"], revision=fm["revision"], layer_id=0,
        query_tokens=m, case_identity="cold128_then_carried128" if m == 128 else "cold16_then_carried16_from_second_window",
        input_origin="original pinned BF16 embedding fixture; exact first M rows of each original 128-token window",
        mask="None, frozen all-valid/no-padding L0 mask as in original TextModel prefix execution",
        configuration="complete original 24-layer config; only original complete decoder layer0 instantiated/executed",
        source_files=source_files, runtime_files=runtime_files, transformers_direct_url=direct_url,
        framework_revision=profile["transformers_source"]["commit"],
        fixture=dict(directory=str(fixture), manifest=file_record(fixture / "manifest.json"), files=fm["files"], sources=fm["sources"]),
        payload=dict(directory=str(payload), manifest=file_record(payload / "manifest.json"), bytes=pm["payload_bytes"], tensors=parameters),
        cases=cases, tensors=tensors, module_events=events, module_invocations=counts,
        observed_module_names=[name for name, count in counts.items() if count],
        unobserved_module_names=[name for name, count in counts.items() if not count],
        observation_scope="Read-only input/output hooks return None; wrappers call original functions with unchanged arguments and return original results. Python return-frame observer records actual chunk loop geometry.",
        unobserved_internals=["conv1d module forward (official uses functional causal_conv1d_fn, whose boundary is captured)",
            "chunk internal L2-normalized Q/K, FP32 triangular systems/solves and per-chunk intermediate states",
            "functional residual-add and activation internals (adjacent named module boundaries are captured)"],
        environment=dict(python=platform.python_version(), packages={n: importlib.metadata.version(n) for n in
            ("torch", "transformers", "numpy", "huggingface-hub", "tokenizers", "safetensors")},
            aten_cpu_capability=os.environ["ATEN_CPU_CAPABILITY"], torch_cpu_capability=torch.backends.cpu.get_cpu_capability(),
            torch_threads=torch.get_num_threads(), torch_interop_threads=torch.get_num_interop_threads(),
            cpu_affinity=sorted(os.sched_getaffinity(0)), eval=True, inference=True, autocast=False,
            deterministic_algorithms=torch.are_deterministic_algorithms_enabled(), float32_matmul_precision=torch.get_float32_matmul_precision()),
        resources=dict(wall_budget_seconds=120, cpu_budget_seconds=120, elapsed_seconds=time.monotonic() - start,
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, activation_bytes=capture_bytes),
        original_parameter_bytes_verified=True, input_fixture_reverified=True, official_complete_layer0_executed=True,
        official_full_model_executed=False, owner_executed=False, hardware_executed=False,
        physical_cache_conditions_measured=False, full_checkpoint_sha256_verified=False,
        previous_prefix_only_reference_reverified=False, numerical_acceptance_gate_added=False,
        numerical_comparison_performed=False, producer_precision_contract_frozen=False)
    validate_manifest(report, output)
    (output / "manifest.json").write_bytes(encoded(report))
    summary = dict(status=report["status"], case_identity=report["case_identity"],
        manifest=file_record(output / "manifest.json"), resources=report["resources"],
        captures=len(tensors), observed_modules=report["observed_module_names"],
        unobserved_modules=report["unobserved_module_names"],
        cases=[dict(name=c["name"], prior_tokens=c["past_tokens"], chunk_size=c["chunk_calls"][0]["chunk_size"],
                    num_chunks=c["chunk_calls"][0]["num_chunks"], output=tensors[c["output"]],
                    final_cache={k: tensors[c["final_cache"][k]] for k in ("conv_state", "recurrent_state")}) for c in cases],
        claim="Official complete L0 CPU reference only; no owner/Chisel/RTL run or numeric acceptance assertion.")
    (output / "summary.json").write_bytes(encoded(summary))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tokens", type=int, choices=(16, 128), required=True)
    args = parser.parse_args(argv)
    report = run(args.root, args.fixture, args.runtime, args.output, args.tokens)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""TEMP fresh full-block software reference; official forward is never patched.

Numerical execution requires a separately reviewed runtime and external resource
supervisor. This is not a hardware model and supplies no output or router IDs to
hardware. Input-only exports are segregated from observed reference outputs.
"""
import argparse
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import time
from stimulus import bf16_bytes, storage_bytes, require

HERE = Path(__file__).resolve().parent
PROFILES_SHA = "d1c846e7b17fb07fab77643f0470c16660d0b872e9f66354f571e6585b6472b0"
TORCH_GIT = "449b1768410104d3ed79d3bcfe4ba1d65c7f22c0"
PLAN_SHA = "df2d2a42cb3fa7c837b78ff5aabceca147f64015f1c3f36393deac76d826609f"
CREATED_OUTPUT = None


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def load_profile(index):
    require(sha_file(HERE / "profiles.json") == PROFILES_SHA, "profile manifest drift")
    profiles = json.loads((HERE / "profiles.json").read_text())
    require(type(index) is int and 0 <= index < 5, "profile must be 0..4")
    return profiles[index]


def tensor_records(payload, profile):
    """Read only complete acquisition receipts; bind semantic header geometry."""
    prefix = ("model.layers." if profile["profile"] == 0 else "model.language_model.layers.") + str(profile["layer"]) + "."
    require(sha_file(HERE / "tensor_acquisition_plan.json") == PLAN_SHA, "official tensor geometry plan drift")
    plan = json.loads((HERE / "tensor_acquisition_plan.json").read_text())[profile["model"]]
    expected = {r["name"]: r for r in plan["tensors"] if r["name"].startswith(prefix)}
    records = []
    for path in sorted((Path(payload) / profile["model"]).glob("*.receipt.json")):
        r = json.loads(path.read_text())
        if not r["name"].startswith(prefix):
            continue
        require(r["status"] == "ACQUIRED_ORIGINAL_TENSOR_BYTES_ONLY_NOT_REFERENCE_OR_DUT", "unfinished tensor")
        require(r["revision"] == profile["checkpoint_revision"] and r["model"] == profile["model"], "checkpoint identity")
        require(r["name"] in expected, "unexpected layer tensor")
        require(all(r[k] == expected[r["name"]][k] for k in ("shape", "dtype", "bytes", "start", "end", "url", "shard_bytes")), "official semantic header/range binding")
        require(r["dtype"] in ("BF16", "F32"), "parameter dtype")
        raw_path = Path(payload) / r["file"]
        require(not raw_path.is_symlink(), "payload final-component symlink")
        p = raw_path.resolve()
        require(p.is_relative_to(Path(payload).resolve()), "payload escape")
        require(p.stat().st_size == r["bytes"] == r["actual_bytes"] and sha_file(p) == r["actual_sha256"], "parameter integrity")
        records.append((r["name"][len(prefix):], p, r))
    require(len(records) == len(expected) == [12, 14, 11, 18, 15][profile["profile"]], "complete layer tensor count")
    require(len({name for name, _, _ in records}) == len(records), "duplicate local parameter name")
    return records


def execute(args):
    global CREATED_OUTPUT
    p = load_profile(args.profile)
    require("torch" not in sys.modules, "configure runtime before Torch import")
    expected_env = "avx512" if p["profile"] == 0 else "default"
    require(os.environ.get("ATEN_CPU_CAPABILITY") == expected_env, "explicit original ATEN capability required")
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        require(os.environ.get(name) == str(p["threads"]), "explicit thread environment required: " + name)
    require(sha_file(args.runtime_receipt) == args.runtime_receipt_sha256, "reviewed runtime receipt identity")
    config_path = Path(args.config)
    require(sha_file(config_path) == p["config_sha256"], "official checkpoint config drift")
    records = tensor_records(args.payload, p)
    output = Path(args.output).resolve()
    output.mkdir(exist_ok=False)
    CREATED_OUTPUT = output
    inputs = output / "input_only"
    refs = output / "reference_only"
    inputs.mkdir(); refs.mkdir()
    start = time.monotonic()
    import torch
    import transformers
    require(torch.__version__ == "2.10.0+cpu" and torch.version.git_version == TORCH_GIT, "pinned Torch CPU build")
    require(torch.backends.cpu.get_cpu_capability() == p["torch_capability"], "actual CPU dispatch profile")
    if p["profile"] == 0:
        require(transformers.__version__ == "4.40.1", "original Qwen2 Transformers")
    torch.set_num_threads(p["threads"])
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    require(torch.get_default_dtype() is torch.float32, "constructor default FP32")
    module = importlib.import_module("transformers.models." + p["module"] + ".modeling_" + p["module"])
    configuration = importlib.import_module("transformers.models." + p["module"] + ".configuration_" + p["module"])
    require(sha_file(inspect.getfile(module)) == p["source_sha256"], "exact official forward source required")
    # Sidecar must be derived and independently reviewed from the exact official
    # runtime archive/wheel locks. Never generate it by trusting a live import.
    require(sha_file(args.runtime_source_pins) == args.runtime_source_pins_sha256, "reviewed runtime source sidecar identity")
    sidecar = json.loads(Path(args.runtime_source_pins).read_text())
    required_modules = {module.__name__, configuration.__name__, "transformers.activations", "transformers.cache_utils", "torch.nn.functional", "torch._C"}
    if p["profile"] != 0: required_modules.add("transformers.masking_utils")
    require(sidecar["framework_revision"] == p["framework_revision"] and set(sidecar["module_sha256"]) == required_modules, "complete exact imported helper source set")
    for name, expected in sidecar["module_sha256"].items():
        imported = importlib.import_module(name)
        require(sha_file(inspect.getfile(imported)) == expected, "imported helper or native Torch identity drift: " + name)
    config_data = json.loads(config_path.read_text())
    cfg = getattr(configuration, p["configuration_class"])(**(config_data if p["profile"] == 0 else config_data["text_config"]))
    cfg._attn_implementation = "eager"
    require(cfg.hidden_size == p["width"], "full original hidden geometry")
    decoder = getattr(module, p["decoder_class"])
    if p["profile"] == 0:
        # Same original FP32 constructor -> BF16 module conversion as historical
        # official Qwen2 capture, including its complete 32768-position RoPE cache.
        layer = decoder(cfg, layer_idx=0).to(dtype=torch.bfloat16, device="cpu")
    else:
        with torch.device("meta"):
            layer = decoder(cfg, layer_idx=p["layer"])
    values = {}
    for name, path, r in records:
        dtype = torch.bfloat16 if r["dtype"] == "BF16" else torch.float32
        width = 2 if r["dtype"] == "BF16" else 4
        values[name] = torch.from_file(str(path), shared=False, size=r["bytes"] // width, dtype=dtype).reshape(r["shape"])
    loaded = layer.load_state_dict(values, strict=True, assign=True)
    require(not loaded.missing_keys and not loaded.unexpected_keys, "strict complete original parameter binding")
    require(set(dict(layer.named_parameters())) == set(values), "complete parameter inventory")
    layer.eval()
    raw_hidden = bf16_bytes(p["width"], p["seed"])
    x = torch.frombuffer(bytearray(raw_hidden), dtype=torch.bfloat16).reshape(1, 128, p["width"])
    pos = torch.arange(128, dtype=torch.long).unsqueeze(0)
    raw = lambda t: t.detach().contiguous().view(torch.uint8).numpy().tobytes()
    saved = {}; written = 0

    def save(folder, name, tensor):
        nonlocal written
        require(tensor.device.type == "cpu" and tensor.dtype in (torch.bfloat16, torch.float32, torch.int64, torch.bool), "unsupported observed tensor")
        data = raw(tensor)
        written += len(data)
        require(written <= 128 * 1024 * 1024, "128 MiB observation cap")
        file = folder / (name + ".bin")
        with file.open("xb") as f:
            f.write(data)
        r = dict(file=str(file.relative_to(output)), shape=list(tensor.shape), dtype=str(tensor.dtype), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        saved[name] = r
        return r

    save(inputs, "hidden_native", x)
    save(inputs, "hidden_storage", x.float() if p["profile"] == 0 else x)
    save(inputs, "positions", pos)
    if p["profile"] == 0:
        cos, sin = layer.self_attn.rotary_emb(x, seq_len=128)
        save(inputs, "rope_cos", cos.float()); save(inputs, "rope_sin", sin.float())
        mask = torch.triu(torch.full((128, 128), torch.finfo(torch.bfloat16).min, dtype=torch.bfloat16), diagonal=1).reshape(1, 1, 128, 128)
        save(inputs, "causal_mask", mask)
        def call():
            return layer(x, attention_mask=mask, position_ids=pos, past_key_value=None, output_attentions=True, use_cache=False)[0], {}
    else:
        rotary = getattr(module, p["rotary_class"])(cfg)
        cos, sin = rotary(x, pos.unsqueeze(0).expand(3, -1, -1))
        save(inputs, "rope_cos", cos); save(inputs, "rope_sin", sin)
        require(tuple(cos.shape) == tuple(sin.shape) == (1, 128, 64), "original64 rotary shape")
        require(torch.equal(cos[..., :32], cos[..., 32:]) and torch.equal(sin[..., :32], sin[..., 32:]), "duplicate rotary halves")
        save(inputs, "rope_packed", torch.cat((cos[..., :32], sin[..., :32]), dim=-1))
        from transformers.cache_utils import DynamicCache
        def call():
            cache = DynamicCache(config=cfg)
            kwargs = dict(config=cfg, inputs_embeds=x, attention_mask=None, past_key_values=cache, position_ids=pos)
            mask_fn = module.create_recurrent_attention_mask if p["layer"] == 0 else module.create_causal_mask
            mask = mask_fn(**kwargs)
            y = layer(x, position_embeddings=(cos, sin), attention_mask=mask, position_ids=pos, past_key_values=cache, use_cache=True)
            slot = cache.layers[p["layer"]]
            state = {}
            def flatten(name, value):
                if isinstance(value, torch.Tensor): state[name] = value
                elif isinstance(value, (list, tuple)):
                    for i, item in enumerate(value): flatten(name+"."+str(i), item)
                else: require(value is None, "unexpected cache state value")
            fields = ("conv_states", "recurrent_states") if p["layer"] == 0 else ("keys", "values")
            for field in fields:
                require(hasattr(slot, field), "original cache interface changed: " + field)
                flatten(field, getattr(slot, field))
                require(any(name == field or name.startswith(field+".") for name in state), "missing complete final cache: " + field)
            return y, state
    # Unobserved official full-block baseline first. The observed arm runs the
    # SAME layer/inputs with a NEW cold cache, not looped single-token calls.
    with torch.inference_mode(), torch.autocast("cpu", enabled=False):
        baseline, baseline_state = call()
    baseline_bytes = raw(baseline)
    save(refs, "baseline_output", baseline)
    baseline_state_bytes = {name: raw(t) for name, t in baseline_state.items()}
    for name, t in baseline_state.items(): save(refs, "baseline_cache."+name, t)
    handles = []; calls = {}
    selected = {"input_layernorm", "post_attention_layernorm", "self_attn", "linear_attn", "mlp", "mlp.gate"}
    selected.update(n for n, _ in layer.named_modules() if n.endswith(("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj", "q_norm", "k_norm")))

    def observe(name):
        def hook(_module, _args, value):
            count = calls.get(name, 0); calls[name] = count + 1
            def tree(v, suffix):
                if isinstance(v, torch.Tensor):
                    save(refs, "stage." + name + "." + str(count) + suffix, v)
                elif isinstance(v, (tuple, list)):
                    for i, child in enumerate(v): tree(child, suffix + "." + str(i))
                else:
                    require(v is None, "unexpected module output")
            tree(value, "")
        return hook

    for name, submodule in layer.named_modules():
        if name in selected: handles.append(submodule.register_forward_hook(observe(name)))
    try:
        with torch.inference_mode(), torch.autocast("cpu", enabled=False):
            observed, observed_state = call()
    finally:
        for handle in handles: handle.remove()
    require(raw(observed) == baseline_bytes, "observer changed exact official output")
    require({name: raw(t) for name, t in observed_state.items()} == baseline_state_bytes, "observer changed final cache")
    for name, t in observed_state.items(): save(refs, "final_cache."+name, t)
    require(tuple(observed.shape) == (1, 128, p["width"]) and torch.isfinite(observed).all().item(), "complete finite output")
    save(refs, "output_storage", observed.float() if p["profile"] == 0 else observed)
    for name, path, r in records:
        require(sha_file(path) == r["actual_sha256"], "source parameter changed during reference")
    result = dict(status="CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY", profile=p,
                  runtime_receipt_sha256=args.runtime_receipt_sha256, elapsed_seconds=time.monotonic()-start,
                  runtime_source_pins_sha256=args.runtime_source_pins_sha256,
                  exact_baseline_observer_output_equal=True, complete_block_tokens=128, forward_calls=2,
                  input_identity="NEW_EXTERNAL_BOUNDARY_NOT_HISTORICAL_PREFIX", tensor_records=saved, observed_module_calls=calls,
                  hardware_executed=False, numerical_comparison_with_hardware=False, router_policy="UNMODIFIED_OFFICIAL_TORCH_TOPK",
                  no_reference_outputs_or_router_ids_allowed_in_hardware_stimulus=True,
                  limits=["TEMP until actual isolated runtime execution and independent review", "No cross-runtime arithmetic equivalence claimed", "Functional-call-only intermediates are not all captured"])
    (output / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=int, required=True)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--runtime-receipt", required=True)
    parser.add_argument("--runtime-receipt-sha256", required=True)
    parser.add_argument("--runtime-source-pins", required=True)
    parser.add_argument("--runtime-source-pins-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute-reviewed", action="store_true")
    args = parser.parse_args()
    require(args.execute_reviewed, "not executed: requires independent review and bounded launcher")
    try:
        execute(args)
    except BaseException as exc:
        output = Path(args.output)
        if CREATED_OUTPUT == output.resolve() and not (output / "FAILURE.json").exists():
            (output / "FAILURE.json").write_text(json.dumps(dict(status="FAIL_REFERENCE_PRESERVE_OUTPUTS", error=type(exc).__name__+": "+str(exc)), indent=2)+"\n")
        raise


if __name__ == "__main__":
    main()

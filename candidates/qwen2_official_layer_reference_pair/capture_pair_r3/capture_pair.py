"""Same-instance M16 baseline/observed Qwen2 pair; import is stdlib-only.

No public entry executes numerical work in this preparation revision. A future
independently reviewed launcher must connect its one-use authorization gate.
"""
import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import struct
import sys
import types

PINS_SHA256 = "0a129018f3c82d959014a0d7a205d736ea0d589d958e970cc96f7ecf2899fa13"
FIELD_ORDER = (
    "x", "mask", "n0", "qr", "kr", "v", "cos", "sin", "q", "k",
    "cache_k", "cache_v", "repeat_k", "repeat_v", "scores", "logits",
    "softmax_fp32", "prob", "pv", "att", "o", "r", "n1", "gate", "silu",
    "up", "act", "down", "y",
)
LINE_FIELDS = {
    280: (("q", "query_states"), ("k", "key_states"),
          ("cache_k", "key_states"), ("cache_v", "value_states")),
    283: (("repeat_k", "key_states"), ("repeat_v", "value_states")),
    285: (("scores", "attn_weights"),),
    300: (("logits", "attn_weights"),),
    302: (("prob", "attn_weights"),),
    304: (("pv", "attn_output"),),
}
CLASSES = ("Qwen2RMSNorm", "Qwen2RotaryEmbedding", "Qwen2MLP",
           "Qwen2Attention", "Qwen2FlashAttention2", "Qwen2SdpaAttention",
           "Qwen2DecoderLayer")
FUNCTIONS = ("rotate_half", "apply_rotary_pos_emb", "repeat_kv")
MODEL_REL = "transformers/models/qwen2/modeling_qwen2.py"
CONFIG_REL = "transformers/models/qwen2/configuration_qwen2.py"
SOFTMAX_REL = "torch/nn/functional.py"


class CaptureFailure(RuntimeError):
    """A terminal FAIL receipt exists; it is not eligible for comparison."""


class ExecutionDisabled(RuntimeError):
    """The independent approved one-use launcher gate is not yet connected."""


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def load_pins():
    raw = Path(__file__).with_name("pins.json").read_bytes()
    need(sha256(raw) == PINS_SHA256, "capture pin manifest drift")
    pins = json.loads(raw)
    need(set(pins["fields"]) == set(FIELD_ORDER), "29-field pin set drift")
    return pins


def _constant(value):
    if isinstance(value, types.CodeType):
        return {"code": code_tree(value)}
    if value is None or value is Ellipsis:
        return {"type": type(value).__name__}
    if isinstance(value, (tuple, frozenset)):
        items = [_constant(x) for x in value]
        if isinstance(value, frozenset):
            items.sort(key=lambda x: json.dumps(x, sort_keys=True))
        return {"type": type(value).__name__, "items": items}
    if isinstance(value, bytes):
        return {"type": "bytes", "hex": value.hex()}
    if isinstance(value, (str, int, float, complex)):
        return {"type": type(value).__name__, "repr": repr(value)}
    raise TypeError("unhandled code constant: " + type(value).__name__)


def code_tree(code):
    """All stable CPython code data, recursively, including source locations.

    Avoid marshal's incidental shared-string reference encoding. No code runs.
    """
    attributes = ("co_argcount", "co_posonlyargcount", "co_kwonlyargcount",
                  "co_nlocals", "co_stacksize", "co_flags", "co_code",
                  "co_names", "co_varnames", "co_filename", "co_name",
                  "co_qualname", "co_firstlineno", "co_linetable",
                  "co_exceptiontable", "co_freevars", "co_cellvars")
    data = {key: _constant(getattr(code, key)) for key in attributes}
    data["co_consts"] = [_constant(x) for x in code.co_consts]
    return data


def code_sha256(code):
    return sha256(json.dumps(code_tree(code), sort_keys=True,
                             separators=(",", ":")).encode())


def child_code(parent, name):
    found = [x for x in parent.co_consts
             if isinstance(x, types.CodeType) and x.co_name == name]
    need(len(found) == 1, "ambiguous or absent official code: " + name)
    return found[0]


def bind_function(function, expected, source_path):
    need(inspect.isfunction(function), "expected original Python function")
    need(Path(function.__code__.co_filename).resolve() == source_path.resolve(),
         "function filename is not fixed source")
    actual = code_sha256(function.__code__)
    need(actual == code_sha256(expected), "compiled official code identity mismatch")
    return {"filename": str(source_path), "first_line": function.__code__.co_firstlineno,
            "complete_code_sha256": actual}


def bind_official_module(module, source_path):
    """Compile complete verified file for code comparison, never AST rewriting."""
    compiled = compile(source_path.read_bytes(), str(source_path), "exec",
                       dont_inherit=True, optimize=sys.flags.optimize)
    identities = {}
    for name in CLASSES:
        cls = getattr(module, name)
        need(cls.__module__ == module.__name__, "non-official class: " + name)
        expected_class = child_code(compiled, name)
        for method, function in vars(cls).items():
            if inspect.isfunction(function):
                identities[name + "." + method] = bind_function(
                    function, child_code(expected_class, method), source_path)
        expected_methods = {x.co_name for x in expected_class.co_consts
                            if isinstance(x, types.CodeType)}
        actual_methods = {n for n, f in vars(cls).items() if inspect.isfunction(f)}
        need(expected_methods == actual_methods, "class method set drift: " + name)
    for name in FUNCTIONS:
        identities[name] = bind_function(getattr(module, name),
                                         child_code(compiled, name), source_path)
    expected_backends = {"eager": module.Qwen2Attention,
                         "flash_attention_2": module.Qwen2FlashAttention2,
                         "sdpa": module.Qwen2SdpaAttention}
    need(module.QWEN2_ATTENTION_CLASSES == expected_backends,
         "official attention class dictionary drift")
    return identities


def validate_context(context):
    """This is an audit binding, not a replacement for launcher enforcement."""
    required = {"run_id", "numerical_runtime_root", "transformers_root", "config_path", "runtime_receipt_path",
                "runtime_receipt_sha256", "softmax_source_sha256",
                "launch_authorization", "resource_controls", "reviewed_runtime_profile", "capture_profile"}
    need(isinstance(context, dict) and set(context) == required,
         "explicit controlled execution context required; unexpected keys rejected")
    need(isinstance(context["run_id"], str) and bool(context["run_id"].strip()),
         "nonempty launcher run_id required")
    for name in ("launch_authorization", "resource_controls"):
        need(isinstance(context[name], dict) and bool(context[name]),
             "launcher must disclose " + name)
    need(file_sha256(context["runtime_receipt_path"]) == context["runtime_receipt_sha256"],
         "launcher runtime receipt binding mismatch")
    need(context["capture_profile"] == PAIR_PROFILE, "exact two-arm capture profile required; old single-arm authority rejected")
    need(sys.byteorder == "little", "raw BF16 and exports require little endian")
    need(sys.gettrace() is None, "existing trace must not be overwritten")
    return (Path(context["numerical_runtime_root"]).resolve(),
            Path(context["transformers_root"]).resolve())


def verify_runtime_sources(numerical_root, transformers_root, context, pins):
    need(context["softmax_source_sha256"] == pins["torch_functional_source_sha256"],
         "launcher softmax source differs from the fixed audited torch source")
    files = dict(pins["official_files"])
    files[SOFTMAX_REL] = context["softmax_source_sha256"]
    records = {}
    for relative, expected in files.items():
        root = numerical_root if relative == SOFTMAX_REL else transformers_root
        path = (root / relative).resolve()
        need(path.is_relative_to(root), "runtime source escapes approved root")
        actual = file_sha256(path)
        need(actual == expected, "runtime source hash mismatch: " + relative)
        records[relative] = {"path": str(path), "sha256": actual}
    need(file_sha256(context["config_path"]) == pins["config_sha256"],
         "original config.json hash mismatch")
    return records


def raw_path(root, pin):
    path = (root / (pin["local_name"] + ".bin")).resolve()
    need(path.is_relative_to(root), "raw input escapes supplied raw_root")
    return path


def verify_raw13(raw_root, pins):
    """Fresh full payload hashing at actual execution time, not old receipts."""
    root = Path(raw_root).resolve()
    verified = []
    need(len(pins["raw13"]) == 13, "exactly 13 original BF16 inputs required")
    for pin in pins["raw13"]:
        path = raw_path(root, pin)
        need(pin["dtype"] == "BF16" and pin["bytes"] == 2 * math.prod(pin["shape"]),
             "raw pin shape/dtype/byte inconsistency")
        need(path.stat().st_size == pin["bytes"], "raw input byte size mismatch")
        actual = file_sha256(path)
        need(actual == pin["sha256"], "raw input full payload hash mismatch: " + str(path))
        verified.append(dict(pin, path=str(path), fresh_payload_sha256=actual))
    return verified


def load_raw_bf16(torch, pin):
    # Read again and bind the very bytes converted, closing the hash/read gap.
    data = bytearray(Path(pin["path"]).read_bytes())
    need(len(data) == pin["bytes"] and sha256(data) == pin["sha256"],
         "raw bytes changed between audit and tensor binding")
    return torch.frombuffer(data, dtype=torch.bfloat16).reshape(pin["shape"]).clone()


def cold_mask_bytes():
    return b"".join(struct.pack("<H", 0xFF7F if k > q else 0)
                    for q in range(16) for k in range(16))


def widen_bf16(raw):
    need(len(raw) % 2 == 0, "unaligned BF16 export")
    out = bytearray(len(raw) * 2)
    out[2::4], out[3::4] = raw[0::2], raw[1::2]
    return bytes(out)


def fp32_nonfinite_count(raw):
    return sum((word[0] & 0x7F800000) == 0x7F800000
               for word in struct.iter_unpack("<I", raw))


def tensor_native_sha256(torch, tensor):
    """Hash actual bound bytes in small chunks, without NumPy or a huge list."""
    byte_view = tensor.detach().contiguous().view(torch.uint8).reshape(-1)
    digest = hashlib.sha256()
    for start in range(0, byte_view.numel(), 65536):
        digest.update(bytes(byte_view[start:start + 65536].tolist()))
    return digest.hexdigest()


PAIR_PROFILE = {
    "name": "same_layer_baseline_then_observed_v1",
    "layer_instances": 1, "forward_calls": 2,
    "arm_order": ["baseline_no_capture_observer", "observed_all29"],
    "same_input_objects": ["x", "mask", "positions"],
    "baseline_outputs": ["y", "prob"], "comparison": "native_bytes_exact",
    "state_checkpoints": ["before_baseline", "after_baseline", "after_observed"],
    "unchanged_state": ["inputs", "parameters", "buffers"],
    "all29_intermediate_noninterference_claimed": False,
}


def tensor_native_bytes(torch, tensor):
    """Freeze actual return bytes immediately, never use the second arm as baseline."""
    return bytes(tensor.detach().contiguous().view(torch.uint8).reshape(-1).tolist())


def state_tensor_record(torch, tensor):
    # Identity is recorded on the ORIGINAL tensor object, not a clone/detach.
    # Hash serialization may materialize contiguous bytes but does not redefine identity.
    return {"object_id": hex(id(tensor)), "shape": list(tensor.shape),
            "stride": list(tensor.stride()), "storage_offset": tensor.storage_offset(),
            "storage_data_ptr": tensor.untyped_storage().data_ptr(),
            "storage_bytes": tensor.untyped_storage().nbytes(),
            "dtype": str(tensor.dtype), "device": str(tensor.device),
            "native_bytes": tensor.numel() * tensor.element_size(),
            "native_sha256": tensor_native_sha256(torch, tensor)}


def capture_state(torch, layer, x, mask, positions):
    # Fresh enumerations at EVERY boundary detect replacement of registered
    # parameters/buffers; never reuse a prior dictionary of tensor references.
    parameters = dict(layer.named_parameters())
    buffers = dict(layer.named_buffers())
    modules = dict(layer.named_modules())
    need(len(parameters) == 12, "complete live parameter set required at every boundary")
    need(set(buffers) == {"self_attn.rotary_emb.inv_freq", "self_attn.rotary_emb.cos_cached", "self_attn.rotary_emb.sin_cached"},
         "complete live rotary buffer set required at every boundary")
    return {"layer_object_id": hex(id(layer)),
            "inputs": {name: state_tensor_record(torch, tensor)
                       for name, tensor in (("x", x), ("mask", mask), ("positions", positions))},
            "parameters": {name: state_tensor_record(torch, tensor) for name, tensor in sorted(parameters.items())},
            "buffers": {name: state_tensor_record(torch, tensor) for name, tensor in sorted(buffers.items())},
            "module_object_ids": {name: hex(id(module)) for name, module in sorted(modules.items())},
            "module_training": {name: bool(module.training) for name, module in sorted(modules.items())},
            "attention_dropout": layer.self_attn.attention_dropout,
            "rotary_max_seq_len_cached": layer.self_attn.rotary_emb.max_seq_len_cached}


def require_same_state(before, after, label):
    need(set(before) == set(after), "state evidence structure changed: " + label)
    changed = [name for name in before if before[name] != after[name]]
    need(not changed, "input/parameter/buffer/object state changed at " + label + ": " + ",".join(changed))
    return {"passed": True, "compared_sections": sorted(before),
            "original_object_identities_compared": True, "native_hashes_compared": True}


def require_baseline_without_observer(torch, layer):
    need(sys.gettrace() is None, "baseline must start without capture trace")
    need(not torch.is_grad_enabled(), "both arms require no_grad")
    need(layer.self_attn.attention_dropout == 0.0, "paired profile requires dropout zero")
    hooks = ("_forward_hooks", "_forward_pre_hooks", "_backward_hooks", "_backward_pre_hooks")
    for name, module in layer.named_modules():
        need(not module.training, "paired profile requires every module eval: " + name)
        need(not any(getattr(module, hook, {}) for hook in hooks), "baseline has existing module observer hooks: " + name)
    registry = torch.nn.modules.module
    global_hooks = ("_global_forward_hooks", "_global_forward_pre_hooks",
                    "_global_backward_hooks", "_global_backward_pre_hooks")
    need(not any(getattr(registry, name, {}) for name in global_hooks), "baseline has existing global module hooks")
    return {"capture_trace_absent": True, "module_hooks_absent": True,
            "global_module_hooks_absent": True, "eval": True, "no_grad": True,
            "attention_dropout": 0.0, "safety_profile_remains_active": sys.getprofile() is not None}


def freeze_baseline(torch, returned, output, pins):
    need(isinstance(returned, tuple) and len(returned) == 2, "baseline no-cache/output-attentions return contract mismatch")
    folder = output / "baseline"
    folder.mkdir(exist_ok=False)
    values, records = {}, {}
    for name, tensor in zip(("y", "prob"), returned):
        field = pins["fields"][name]
        need(list(tensor.shape) == field["shape"] and str(tensor.dtype).removeprefix("torch.") == field["dtype"]
             and str(tensor.device) == "cpu", "baseline original output shape/dtype/device mismatch: " + name)
        raw = tensor_native_bytes(torch, tensor)
        need(len(raw) == field["export_f32_bytes"] // 2, "baseline original native size mismatch: " + name)
        need(fp32_nonfinite_count(widen_bf16(raw)) == 0, "nonfinite baseline output: " + name)
        path = folder / (name + ".native.bin")
        with path.open("xb") as stream:
            stream.write(raw)
        values[name] = raw
        records[name] = {"file": str(path.relative_to(output)), "native_bytes": len(raw),
                         "native_sha256": sha256(raw), "shape": field["shape"],
                         "native_dtype": field["dtype"], "original_return_object_id": hex(id(tensor))}
    return values, records


def compare_pair_outputs(torch, baseline_bytes, returned):
    need(set(baseline_bytes) == {"y", "prob"}, "baseline y/prob native bytes missing")
    need(isinstance(returned, tuple) and len(returned) == 2, "observed return contract mismatch")
    comparisons = {}
    for name, tensor in zip(("y", "prob"), returned):
        actual = tensor_native_bytes(torch, tensor)
        need(type(baseline_bytes[name]) is bytes, "baseline must be frozen bytes")
        comparisons[name] = {"byte_identical": actual == baseline_bytes[name], "native_bytes": len(actual),
                             "baseline_sha256": sha256(baseline_bytes[name]),
                             "observed_sha256": sha256(actual)}
    return {"passed": all(item["byte_identical"] for item in comparisons.values()), "outputs": comparisons,
            "claim_scope": "y/prob only; no claim that all29 baseline intermediates were observed",
            "all29_intermediate_noninterference_claimed": False}


class Observer:
    """Read-only hooks/trace. Observation errors accumulate; official flow runs.

    Snapshots are immediate detach().clone(), not views and not recomputation.
    """
    def __init__(self, fields, snapshot=None):
        self.fields = fields
        self.snapshot = snapshot or (lambda value: value.detach().clone())
        self.values, self.metadata, self.objects = {}, {}, {}
        self.errors, self.order = [], []
        self.attention, self.attention_code, self.softmax_code = None, None, None
        self.attention_frame, self.softmax_frame = None, None
        self.attention_calls = self.softmax_calls = 0
        self.line_visits = {}
        self.float32 = None

    def error(self, where, error):
        self.errors.append({"where": where, "error": type(error).__name__ + ": " + str(error)})

    def record(self, name, value):
        try:
            need(name not in self.values and name not in self.order,
                 "duplicate observation: " + name)
            self.order.append(name)
            # Keep originals solely for alias auditing. Never write into them.
            self.objects[name] = value
            self.metadata[name] = {"shape": list(value.shape),
                                   "stride": list(value.stride()),
                                   "storage_offset": value.storage_offset(),
                                   "original_storage_data_ptr": value.untyped_storage().data_ptr(),
                                   "original_storage_bytes": value.untyped_storage().nbytes(),
                                   "native_dtype": str(value.dtype).removeprefix("torch."),
                                   "device": str(value.device)}
            self.values[name] = self.snapshot(value)
        except Exception as error:
            self.error("record:" + name, error)
        return None

    def output_hook(self, name):
        def hook(module, args, output):
            self.record(name, output)
            return None
        return hook

    def input_hook(self, name):
        def hook(module, args):
            try:
                self.record(name, args[0])
            except Exception as error:
                self.error("prehook:" + name, error)
            return None
        return hook

    def rotary_hook(self, module, args, output):
        try:
            self.record("cos", output[0])
            self.record("sin", output[1])
        except Exception as error:
            self.error("rotary_hook", error)
        return None

    def decoder_hook(self, module, args, output):
        try:
            self.record("y", output[0])
        except Exception as error:
            self.error("decoder_hook", error)
        return None

    def trace(self, frame, event, arg):
        try:
            if frame.f_code is self.attention_code:
                if event == "call":
                    if frame.f_locals.get("self") is not self.attention:
                        return None
                    self.attention_calls += 1
                    need(self.attention_frame is None, "multiple/nested Attention calls")
                    self.attention_frame = frame
                if frame is not self.attention_frame:
                    return None
                if event == "line" and frame.f_lineno in LINE_FIELDS:
                    line = frame.f_lineno
                    self.line_visits[line] = self.line_visits.get(line, 0) + 1
                    for name, local in LINE_FIELDS[line]:
                        self.record(name, frame.f_locals[local])
                if event == "return":
                    self.attention_frame = None
                return self.trace
            if frame.f_code is self.softmax_code:
                if event == "call":
                    if frame.f_back is not self.attention_frame or self.attention_frame is None:
                        return None
                    need(frame.f_back.f_lineno == 300, "softmax not from official Attention line300")
                    need(frame.f_locals.get("input") is frame.f_back.f_locals["attn_weights"],
                         "softmax input is not original logits")
                    need(frame.f_locals.get("dim") == -1 and
                         frame.f_locals.get("dtype") is self.float32,
                         "softmax is not original FP32 call")
                    self.softmax_calls += 1
                    need(self.softmax_frame is None, "multiple/nested softmax calls")
                    self.softmax_frame = frame
                if frame is not self.softmax_frame:
                    return None
                if event == "return":
                    self.record("softmax_fp32", arg)
                    self.softmax_frame = None
                return self.trace
        except Exception as error:
            self.error("trace:" + event, error)
            # Never raise from observational code or alter f_locals/f_lineno.
            return self.trace
        return None

    def validate(self):
        problems = []
        if self.order != list(FIELD_ORDER):
            problems.append("29-field exact observation order/set differs")
        if set(self.values) != set(FIELD_ORDER):
            problems.append("one or more snapshots missing")
        for name, meta in self.metadata.items():
            expected = self.fields[name]
            if meta["shape"] != expected["shape"] or meta["native_dtype"] != expected["dtype"]:
                problems.append("observed shape/native dtype mismatch: " + name)
            if meta["device"] != "cpu":
                problems.append("non-CPU observation: " + name)
        if self.attention_calls != 1 or self.softmax_calls != 1:
            problems.append("exactly one Attention and one FP32 softmax call required")
        if self.line_visits != {line: 1 for line in LINE_FIELDS}:
            problems.append("Attention observation lines not seen exactly once")
        if self.objects.get("k") is not self.objects.get("cache_k"):
            problems.append("cache_k is not original cold k alias")
        if "v" in self.metadata and "cache_v" in self.metadata:
            for key in ("original_storage_data_ptr", "storage_offset", "original_storage_bytes"):
                if self.metadata["v"][key] != self.metadata["cache_v"][key]:
                    problems.append("cache_v is not original transposed v storage alias: " + key)
        self.errors.extend({"where": "validation", "error": p} for p in problems)
        return not self.errors


def install_hooks(layer, observer):
    handles = []
    try:
        outputs = ((layer.input_layernorm, "n0"), (layer.self_attn.q_proj, "qr"),
                   (layer.self_attn.k_proj, "kr"), (layer.self_attn.v_proj, "v"),
                   (layer.self_attn.o_proj, "o"), (layer.post_attention_layernorm, "n1"),
                   (layer.mlp.gate_proj, "gate"), (layer.mlp.up_proj, "up"),
                   (layer.mlp.act_fn, "silu"), (layer.mlp.down_proj, "down"))
        for module, name in outputs:
            handles.append(module.register_forward_hook(observer.output_hook(name)))
        for module, name in ((layer.self_attn.o_proj, "att"),
                             (layer.post_attention_layernorm, "r"),
                             (layer.mlp.down_proj, "act")):
            handles.append(module.register_forward_pre_hook(observer.input_hook(name)))
        handles.append(layer.self_attn.rotary_emb.register_forward_hook(observer.rotary_hook))
        handles.append(layer.register_forward_hook(observer.decoder_hook))
        return handles
    except Exception:
        for handle in handles:
            handle.remove()
        raise


def export_snapshots(torch, observer, output, pins):
    exports = {}
    for name in FIELD_ORDER:
        if name not in observer.values:
            continue
        tensor = observer.values[name]
        try:
            native = bytes(tensor.contiguous().view(torch.uint8).reshape(-1).tolist())
            dtype = observer.metadata[name]["native_dtype"]
            need(dtype in ("bfloat16", "float32"), "unsupported observed dtype")
            wide = widen_bf16(native) if dtype == "bfloat16" else native
            need(len(wide) == pins["fields"][name]["export_f32_bytes"],
                 "observed export size differs from M16 geometry")
            entry = dict(observer.metadata[name], native_bytes=len(native),
                         native_sha256=sha256(native), fp32_bytes=len(wide),
                         fp32_sha256=sha256(wide), nonfinite_count=fp32_nonfinite_count(wide),
                         native_file=name + ".native.bin", fp32_file=name + ".f32.bin")
            for suffix, data in ((".native.bin", native), (".f32.bin", wide)):
                with (output / (name + suffix)).open("xb") as stream:
                    stream.write(data)
            if entry["nonfinite_count"]:
                observer.error("export:" + name, ValueError("nonfinite actual tensor"))
            exports[name] = entry
        except Exception as error:
            observer.error("export:" + name, error)
    return exports


def write_json_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def run_capture(raw_root, output_new, context):
    """Fail closed until an independently reviewed one-use launcher is wired.

    A caller-supplied dictionary/run_id is metadata, never execution authority.
    There is intentionally no boolean, environment variable or CLI override.
    """
    raise ExecutionDisabled("EXECUTION_DISABLED: independent one-use launcher authorization gate remains unconnected")


def _capture_pair_impl(raw_root, output_new, context):
    """Execute one approved same-layer baseline/observed M16 pair under caller-owned controls.

    raw_root contains only the fixed <local_name>.bin input files. No provider,
    past/reference output, weight download, default model loader or stub route
    exists. Success is capture completeness, never numerical/DUT acceptance.
    """
    output = Path(output_new).resolve()
    output.mkdir(parents=False, exist_ok=False)
    report = {"schema": 1, "status": "FAIL", "numeric_acceptance": "NOT_RUN",
              "dut_comparison": "NOT_RUN", "official_layer_call_started": False,
              "official_layer_call_returned": False, "baseline_layer_call_started": False,
              "baseline_layer_call_returned": False, "full_model_forward_executed": False,
              "capture_profile": PAIR_PROFILE, "layer_instance_count": 0, "forward_call_count": 0,
              "dynamic_cache_executed": False, "legacy_results_inherited": False,
              "source_rewritten": False, "observation_noninterference_proven": False,
              "execution_context": context}
    observer, error = None, None
    try:
        pins = load_pins()
        numerical_root, root = validate_context(context)
        report["sources"] = verify_runtime_sources(numerical_root, root, context, pins)
        report["raw13"] = verify_raw13(raw_root, pins)
        # Normal imports of complete official modules, not source extraction.
        torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
        config_module = importlib.import_module("transformers.models.qwen2.configuration_qwen2")
        model = importlib.import_module("transformers.models.qwen2.modeling_qwen2")
        config_base = importlib.import_module("transformers.configuration_utils")
        for module, module_root, relative in ((model, root, MODEL_REL),
                                             (config_module, root, CONFIG_REL),
                                             (torch.nn.functional, numerical_root, SOFTMAX_REL),
                                             (torch, numerical_root, "torch/__init__.py"),
                                             (transformers, root, "transformers/__init__.py"),
                                             (config_base, root, "transformers/configuration_utils.py")):
            need(Path(module.__file__).resolve() == (module_root / relative).resolve(),
                 "normal import resolved outside approved runtime: " + module.__name__)
        need(torch.__version__ == pins["torch_version"], "torch version drift")
        need(transformers.__version__ == pins["transformers_version"], "transformers version drift")
        actual_runtime = {"cpu_capability": torch.backends.cpu.get_cpu_capability(),
                          "torch_build_sha256": sha256(torch.__config__.show().encode()),
                          "torch_git_version": torch.version.git_version,
                          "intraop_threads": torch.get_num_threads(),
                          "interop_threads": torch.get_num_interop_threads(),
                          "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                          "python_major_minor": list(sys.version_info[:2])}
        report["actual_runtime_profile"] = actual_runtime
        report["torch_build_configuration"] = torch.__config__.show()
        report["actual_process_configuration"] = {
            "affinity": sorted(os.sched_getaffinity(0)),
            "environment": {key: os.environ.get(key) for key in
                            ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                             "ATEN_CPU_CAPABILITY", "ONEDNN_MAX_CPU_ISA", "DNNL_MAX_CPU_ISA")},
            "default_dtype": str(torch.get_default_dtype()),
            "float32_matmul_precision": torch.get_float32_matmul_precision(),
            "mkldnn_enabled": torch.backends.mkldnn.enabled,
        }
        need(actual_runtime == context["reviewed_runtime_profile"],
             "actual runtime/backend dispatch differs from independently reviewed exact profile")
        need(actual_runtime["intraop_threads"] == 4 and actual_runtime["interop_threads"] == 1
             and actual_runtime["deterministic_algorithms"] is True,
             "fixed arithmetic profile requires 4/1 threads and deterministic algorithms")
        need(torch.get_default_dtype() is torch.float32,
             "official constructor/rotary cache must begin with default FP32")
        report["code_identities"] = bind_official_module(model, root / MODEL_REL)
        config_code = compile((root / CONFIG_REL).read_bytes(), str(root / CONFIG_REL),
                              "exec", dont_inherit=True, optimize=sys.flags.optimize)
        report["code_identities"]["Qwen2Config.__init__"] = bind_function(
            config_module.Qwen2Config.__init__,
            child_code(child_code(config_code, "Qwen2Config"), "__init__"), root / CONFIG_REL)
        need(config_module.Qwen2Config.__bases__ == (config_base.PretrainedConfig,),
             "Qwen2Config must inherit actual normal-import PretrainedConfig")
        softmax_source = numerical_root / SOFTMAX_REL
        softmax_compiled = compile(softmax_source.read_bytes(), str(softmax_source), "exec",
                                   dont_inherit=True, optimize=sys.flags.optimize)
        report["code_identities"]["torch.nn.functional.softmax"] = bind_function(
            torch.nn.functional.softmax, child_code(softmax_compiled, "softmax"), softmax_source)
        config_data = json.loads(Path(context["config_path"]).read_bytes())
        config = config_module.Qwen2Config(**config_data)
        config._attn_implementation = "eager"
        need(config.max_position_embeddings == 32768 and config.rope_theta == 1e6
             and config.use_sliding_window is False, "original official config must be preserved")
        report["config"] = {"to_dict": config.to_dict(),
                            "actual_attn_implementation": config._attn_implementation,
                            "eager_is_explicit_wrapper_choice": True,
                            "rotary_256_profile_executed": False}
        # Construction performs official initialization, then every learned
        # parameter is replaced from original BF16 bytes before any forward.
        layer = model.Qwen2DecoderLayer(config, layer_idx=0).to(dtype=torch.bfloat16, device="cpu")
        layer.eval()
        report["layer_instance_count"] = 1
        need(type(layer) is model.Qwen2DecoderLayer and type(layer.self_attn) is model.Qwen2Attention,
             "only actual original eager decoder/attention permitted")
        parameters = dict(layer.named_parameters())
        parameter_pins = {x["local_name"]: x for x in report["raw13"]
                          if x["local_name"] != "embed_tokens.rows_0_255"}
        need(len(parameters) == 12 and set(parameters) == set(parameter_pins),
             "complete official 12-parameter binding set mismatch")
        report["parameter_bindings"] = {}
        with torch.no_grad():
            for name, parameter in parameters.items():
                pin = parameter_pins[name]
                need(list(parameter.shape) == pin["shape"] and parameter.dtype is torch.bfloat16,
                     "official parameter shape/dtype mismatch: " + name)
                value = load_raw_bf16(torch, pin)
                parameter.copy_(value)
                bound_hash = tensor_native_sha256(torch, parameter)
                need(bound_hash == pin["sha256"], "bound parameter bytes differ: " + name)
                report["parameter_bindings"][name] = {"shape": list(parameter.shape),
                                                     "dtype": "bfloat16", "sha256": bound_hash}
                del value
            embedding = next(x for x in report["raw13"] if x["local_name"] == "embed_tokens.rows_0_255")
            x = load_raw_bf16(torch, embedding)[:16].unsqueeze(0).clone()
            mask_raw = bytearray(cold_mask_bytes())
            mask = torch.frombuffer(mask_raw, dtype=torch.bfloat16).reshape(1, 1, 16, 16).clone()
            positions = torch.arange(16, dtype=torch.long, device="cpu").unsqueeze(0)
            # FIRST arm: the exact same layer and original input objects, before
            # creating Observer or installing ANY capture hook/trace. Safety
            # audit/model/network profile remains installed by the worker.
            report["baseline_controls"] = require_baseline_without_observer(torch, layer)
            report["state_checkpoints"] = {"before_baseline": capture_state(torch, layer, x, mask, positions)}
            report["baseline_layer_call_started"] = True
            report["forward_call_count"] += 1
            baseline_returned = layer(x, attention_mask=mask, position_ids=positions,
                                      past_key_value=None, output_attentions=True, use_cache=False)
            report["baseline_layer_call_returned"] = True
            # Freeze actual first-return bytes immediately, before the observed arm.
            baseline_bytes, report["baseline_exports"] = freeze_baseline(torch, baseline_returned, output, pins)
            report["state_checkpoints"]["after_baseline"] = capture_state(torch, layer, x, mask, positions)
            report["baseline_state_unchanged"] = require_same_state(
                report["state_checkpoints"]["before_baseline"], report["state_checkpoints"]["after_baseline"], "after_baseline")
            need(sys.gettrace() is None, "baseline installed a trace unexpectedly")
            observer = Observer(pins["fields"])
            observer.attention = layer.self_attn
            observer.attention_code = model.Qwen2Attention.forward.__code__
            observer.softmax_code = torch.nn.functional.softmax.__code__
            observer.float32 = torch.float32
            observer.record("x", x)
            observer.record("mask", mask)
            handles = install_hooks(layer, observer)
            try:
                report["official_layer_call_started"] = True
                report["forward_call_count"] += 1
                sys.settrace(observer.trace)
                returned = layer(x, attention_mask=mask, position_ids=positions,
                                 past_key_value=None, output_attentions=True, use_cache=False)
                report["official_layer_call_returned"] = True
            finally:
                sys.settrace(None)
                for handle in handles:
                    handle.remove()
            need(isinstance(returned, tuple) and len(returned) == 2,
                 "official no-cache/output-attentions return contract mismatch")
            need(observer.objects.get("y") is returned[0] and observer.objects.get("prob") is returned[1],
                 "captured values must be exact official returned objects")
            report["state_checkpoints"]["after_observed"] = capture_state(torch, layer, x, mask, positions)
            report["observed_state_unchanged"] = require_same_state(
                report["state_checkpoints"]["before_baseline"], report["state_checkpoints"]["after_observed"], "after_observed")
            report["pair_output_comparison"] = compare_pair_outputs(torch, baseline_bytes, returned)
            need(report["layer_instance_count"] == 1 and report["forward_call_count"] == 2,
                 "exactly one instance and two ordered forwards required")
        observer.validate()
        report["exports"] = export_snapshots(torch, observer, output, pins)
        report["comparison_gates_not_applied"] = pins["comparison_gates"]
        report["origin_disclosures"] = {
            "x": "original raw embedding rows 0:16; token IDs 0..15; no embedding module call",
            "mask": "explicit caller-side BF16 causal argument, not official mask helper and not DUT capture",
            "mask_words": {"allowed": "0x0000", "future": "0xff7f"},
            "mask_counts": {"allowed": 136, "future": 120, "diagonal": 16},
            "scores_domain_counts": {"causal": 1632, "future": 1440},
            "position_ids": list(range(16)), "past_key_value": None, "use_cache": False,
            "cache_k": "cold semantic alias of post-RoPE k before repeat_kv; no Cache.update",
            "cache_v": "cold semantic alias of original transposed v before repeat_kv; no Cache.update",
            "native_hash_layout": "logical row-major contiguous serialization; original strides/offset recorded",
            "fp32_export": "exact BF16 bit widening, or actual FP32 softmax return bytes unchanged",
            "scope": "complete Qwen2DecoderLayer.__call__/forward only; not Qwen2Model/ForCausalLM.forward",
            "unselected_backends_executed": False,
        }
        need(not observer.errors and len(report["exports"]) == 29,
             "observation/export validation failed; official computation was not patched")
        need(report["pair_output_comparison"]["passed"],
             "baseline/observed actual y/prob native bytes differ; failed pair is not a reference")
        report["sources_after_capture"] = verify_runtime_sources(numerical_root, root, context, pins)
        report["status"] = "PAIR_CAPTURE_COMPLETE_NOT_NUMERIC_PASS"
    except Exception as caught:
        error = caught
        report["failure"] = {"type": type(caught).__name__, "message": str(caught)}
    finally:
        if observer is not None:
            report["observation"] = {"order": observer.order, "errors": observer.errors,
                                     "attention_calls": observer.attention_calls,
                                     "softmax_calls": observer.softmax_calls,
                                     "line_visits": observer.line_visits}
        write_json_new(output / "RESULT.json", report)
    if error is not None:
        raise CaptureFailure("terminal FAIL: " + str(output / "RESULT.json")) from error
    seal = {"schema": 1, "status": report["status"],
            "result_sha256": file_sha256(output / "RESULT.json"),
            "capture_source_sha256": file_sha256(__file__), "pins_sha256": PINS_SHA256,
            "files": {str(path.relative_to(output)): file_sha256(path) for path in sorted(output.rglob("*.bin"))},
            "capture_profile": PAIR_PROFILE, "layer_instances": 1, "forward_calls": 2,
            "noninterference_scope": "actual y/prob native bytes and boundary input/parameter/buffer state only"}
    write_json_new(output / "SEAL.json", seal)
    return report

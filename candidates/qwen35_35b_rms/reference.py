"""Execute the exact pinned upstream class, without importing a full model.

The complete class AST, including constructor and repr, is extracted unchanged.
Only torch and torch.nn are supplied as external names. This is official RMS
component execution, not full native-forward, installed MoE-module, or RTL
execution. Diagnostic arrays here are host observations, not owner storage.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "config/upstream/weight_headers/qwen3_5_35b_a3b/modeling_qwen3_5_moe.py"
SOURCE_SHA = "ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30"
CLASS_SHA = "106cb15a68082e904cf98595202659710df28f2c059ace123246369914436073"
CONFIG = "config/upstream/weight_headers/qwen3_5_35b_a3b/config.json"
CONFIG_SHA = "5e4d7f74fec2f360eb9cfbfcd6ec0c4c76e684d3a11caaed259d9fd9bfbc7944"
MODEL_REVISION = "62704185bd97ad488cfc404e7caea797396b74dc"
TRANSFORMERS_REVISION = "42ca97014c85d71a88ad60d55f08cb9fb4d26e2c"
RUNTIME = ROOT / "work/qwen35_runtime_20261012_recovered"
RUNTIME_PINS = {
    "python.sh": "989e013c0407c5a964386b30129998c74b864b2186cb6741ecb51053c4fad247",
    "runtime_receipt.json": "06be2d4f193b19c4f8509159ca8ef7ef0b26c5d733debf6147ecfc6e9b4e4cc2",
    "site-packages/torch/lib/libtorch_cpu.so": "4dc5b3a649b61d8f39be127866bc258dda19d74e339f449fe18103db63e8d76f",
    "site-packages/torch/_C.cpython-312-x86_64-linux-gnu.so": "2a4e075c33f292a709006fe69bca669e681351fad1fcddd7c957fcf96362d1a8",
    "site-packages/numpy/_core/_multiarray_umath.cpython-312-x86_64-linux-gnu.so": "ba96467ae494babaf7c3458b09cc03c4200c2e10010860d80e452ffb8b01c8cd",
}
WIDTH, EPS = 2048, 1e-6


def require(ok, message):
    if not ok:
        raise ValueError("35B RMS: " + message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _source_definition(root=ROOT):
    """Verify source/config without importing Torch or any runtime package."""
    root = Path(root)
    raw = (root / SOURCE).read_bytes()
    require(sha(raw) == SOURCE_SHA, "official modeling source drift")
    config = (root / CONFIG).read_bytes()
    require(sha(config) == CONFIG_SHA, "official model config drift")
    config = json.loads(config)["text_config"]
    require(config["hidden_size"] == WIDTH and config["rms_norm_eps"] == EPS,
            "official H2048/epsilon contract drift")
    classes = [n for n in ast.parse(raw).body if isinstance(n, ast.ClassDef)
               and n.name == "Qwen3_5MoeRMSNorm"]
    require(len(classes) == 1, "one original RMS class required")
    node = classes[0]
    exact = b"".join(raw.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    require((node.lineno, node.end_lineno) == (878, 895) and sha(exact) == CLASS_SHA,
            "complete original RMS class drift")
    return node, dict(
        model_revision=MODEL_REVISION, transformers_revision=TRANSFORMERS_REVISION,
        source=SOURCE, source_sha256=SOURCE_SHA, config_sha256=CONFIG_SHA,
        class_name=node.name, class_lines=[878, 895], class_sha256=CLASS_SHA,
        extraction="complete unmodified class AST; original filename and line numbers",
        external_namespace=["torch", "torch.nn"], full_native_forward=False,
        installed_moe_module_imported=False, rtl_executed=False)


def source_identity(root=ROOT):
    """Pure source/config verification; no Torch, work cache, or execution."""
    return _source_definition(root)[1]


def source_class(root=ROOT):
    """Verify byte identities before compiling the untouched original class."""
    node, identity = _source_definition(root)
    import torch
    namespace = {"torch": torch, "nn": torch.nn, "__name__": "pinned_qwen35_35b_rms"}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(Path(root) / SOURCE), "exec"), namespace)
    return namespace[node.name], identity


def runtime_selection(profile=None, root=ROOT):
    # Explicit recovery profiles preserve historical wrapper/receipt identity.
    # Binary authority and all actual runtime checks remain mandatory.
    pins = RUNTIME_PINS
    profile = (os.environ.get("HETERO_35B_RUNTIME_PROFILE", "historical_20261012")
               if profile is None else profile)
    require(profile in ("historical_20261012", "recovery_20261013"), "unknown runtime profile")
    if profile == "recovery_20261013":
        lock = json.loads((Path(root) / "candidates/qwen35_35b_rms/runtime_recovery_20261013.json").read_bytes())
        pins = lock["sha256"]
        require(set(pins) == set(RUNTIME_PINS), "runtime pin set changed")
        require(all(pins[n] == RUNTIME_PINS[n] for n in pins if n.startswith("site-packages/")),
                "recovery arithmetic binary drift")
        selected_runtime = Path(root) / "work/runtime_recovery"
    else:
        selected_runtime = RUNTIME
    return profile, selected_runtime, pins


def runtime_identity(runtime=None):
    """Verify relevant binaries and runtime receipt; record actual dispatch."""
    import numpy as np
    import torch
    profile, selected_runtime, pins = runtime_selection()
    runtime = Path(selected_runtime if runtime is None else runtime).resolve()
    require(sys.byteorder == "little", "little-endian host required")
    require(torch.__version__ == "2.10.0+cpu" and np.__version__ == "2.3.5", "runtime version drift")
    require(torch.version.git_version == "449b1768410104d3ed79d3bcfe4ba1d65c7f22c0", "Torch commit drift")
    require(os.environ.get("ATEN_CPU_CAPABILITY") == "default" and
            torch.backends.cpu.get_cpu_capability() == "DEFAULT", "DEFAULT CPU dispatch required")
    require(torch.get_num_threads() == torch.get_num_interop_threads() == 1, "both Torch thread counts must be one")
    require(len(os.sched_getaffinity(0)) == 1, "one CPU affinity required")
    for module in (torch, np):
        require(Path(module.__file__).resolve().is_relative_to(runtime / "site-packages"), "module outside isolated runtime")
    observed = {}
    for name, digest in pins.items():
        observed[name] = file_sha(runtime / name)
        require(observed[name] == digest, "runtime artifact drift: " + name)
    receipt = json.loads((runtime / "runtime_receipt.json").read_bytes())
    require(receipt["status"] == "PASS_ISOLATED_PINNED_RUNTIME_READY" and all(receipt["checks"].values()),
            "runtime receipt not ready")
    return dict(runtime_profile=profile, runtime_root=str(runtime), torch_version=torch.__version__, torch_git_revision=torch.version.git_version,
                numpy_version=np.__version__, python_version=sys.version,
                cpu_capability=torch.backends.cpu.get_cpu_capability(),
                intraop_threads=torch.get_num_threads(), interop_threads=torch.get_num_interop_threads(),
                affinity=sorted(os.sched_getaffinity(0)), sha256=observed,
                build_config_sha256=sha(torch.__config__.show().encode()),
                complete_runtime_dependency_source_closure=False,
                installed_transformers_is_not_35b_source_authority=True)


def validate_raw(hidden, weight, tokens):
    import numpy as np
    require(type(tokens) is int and 1 <= tokens <= 128, "M1..128 required")
    require(type(hidden) is bytes and len(hidden) == tokens * WIDTH * 2, "complete BF16[M,2048] input required")
    require(type(weight) is bytes and len(weight) == WIDTH * 2, "complete BF16[2048] weight required")
    for raw in (hidden, weight):
        require(not np.any((np.frombuffer(raw, "<u2") & 0x7f80) == 0x7f80), "nonfinite BF16 input/weight")


def component(hidden, weight, tokens, *, root=ROOT):
    """Run original class on BF16[1,M,2048]; observe actual dispatched nodes.

    The additional torch.sum is explicitly auxiliary: upstream uses mean,
    and that actual mean is captured from the unmodified forward execution.
    """
    import torch
    from torch.utils._python_dispatch import TorchDispatchMode
    validate_raw(hidden, weight, tokens)
    cls, identity = source_class(root)
    x = torch.frombuffer(bytearray(hidden), dtype=torch.bfloat16).reshape(1, tokens, WIDTH)
    w = torch.frombuffer(bytearray(weight), dtype=torch.bfloat16)
    with torch.device("meta"):
        model = cls(WIDTH, eps=EPS)
    model.load_state_dict({"weight": w}, assign=True)
    model.eval()
    sequence = [
        ("aten.to.dtype", "input_fp32"), ("aten.pow.Tensor_Scalar", "squares"),
        ("aten.mean.dim", "mean"), ("aten.add.Tensor", "mean_eps"),
        ("aten.rsqrt.default", "inverse"), ("aten.mul.Tensor", "scaled"),
        ("aten.to.dtype", "weight_fp32"), ("aten.add.Tensor", "gamma"),
        ("aten.mul.Tensor", "weighted"), ("aten.type_as.default", "output"),
    ]
    snapshots, operations = {}, []

    class Observe(TorchDispatchMode):
        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            index = len(operations)
            require(index < len(sequence) and str(func) == sequence[index][0], "official operation trace drift")
            result = func(*args, **(kwargs or {}))
            operations.append(str(func))
            snapshots[sequence[index][1]] = result.detach().clone()
            return result

    with torch.inference_mode(), Observe():
        out = model(x)
    require(len(operations) == len(sequence) and out.dtype == torch.bfloat16, "incomplete component execution")
    snapshots["sum_auxiliary"] = snapshots["squares"].sum(-1, keepdim=True)
    output = out.view(torch.uint16).numpy().astype("<u2", copy=False).tobytes()
    trace = {name: tensor.float().numpy().copy() for name, tensor in snapshots.items() if name != "output"}
    return dict(output=output, trace=trace, source=identity, operations=operations,
                input_sha256=sha(hidden), weight_sha256=sha(weight), output_sha256=sha(output))


def payload_case(directory, manifest_sha256, token_ids, *, root=ROOT, include_qkv=False):
    """Local verified payload only; no acquisition and no tokenizer/remapping.

    Caller supplies the independently retained acquisition-manifest digest.
    The payload loader rechecks original headers, ranges, receipts and bytes.
    """
    from candidates.qwen35_35b_payload.packer import load_payload
    require(isinstance(token_ids, (list, tuple)) and 1 <= len(token_ids) <= 128 and
            all(type(i) is int and 0 <= i < 256 for i in token_ids), "original embedding IDs 0..255 required")
    manifest, values = load_payload(Path(root), Path(directory), manifest_sha256=manifest_sha256, include_qkv=include_qkv)
    embedding = values["embed_tokens.rows_0_255"]
    hidden = b"".join(embedding[i * WIDTH * 2:(i + 1) * WIDTH * 2] for i in token_ids)
    weight = values["layers.0.input_layernorm.weight"]
    validate_raw(hidden, weight, len(token_ids))
    return hidden, weight, dict(kind="actual_pinned_embedding_and_input_norm", token_ids=list(token_ids),
        manifest_sha256=manifest_sha256, model_revision=MODEL_REVISION,
        embedding_rows_sha256=sha(embedding), input_sha256=sha(hidden), weight_sha256=sha(weight),
        payload_hashes_are_first_acquisition_observations=True, full_checkpoint_sha256_verified=False)

"""Pinned 35B L0 gated RMSNorm on caller-supplied complete native inputs.

This is component-only native execution. The original norm and SiLU forwards
are unmodified. Only their optional hub decorators are removed. The caller
establishes the frozen runtime; this module has no global Torch setters and
never reads candidate owners, payload caches, old summaries, or scalar models.

The local activation source archive is pinned to the official Transformers
revision below and is never imported as a full module. Source identity and raw
validation are Torch/NumPy-free.
"""
from __future__ import annotations

import ast
import copy
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "config/upstream/weight_headers/qwen3_5_35b_a3b/modeling_qwen3_5_moe.py"
SOURCE_SHA = "ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30"
CONFIG = "config/upstream/weight_headers/qwen3_5_35b_a3b/config.json"
CONFIG_SHA = "5e4d7f74fec2f360eb9cfbfcd6ec0c4c76e684d3a11caaed259d9fd9bfbc7944"
MODEL_REVISION = "62704185bd97ad488cfc404e7caea797396b74dc"
TRANSFORMERS_REVISION = "42ca97014c85d71a88ad60d55f08cb9fb4d26e2c"
NORM_CLASS = "Qwen3_5MoeRMSNormGated"
NORM_CLASS_AST_SHA = "a7d8b68ca2232cb7c8dc4a1d84edc73c8c44012722790520251f5b6689ec007d"
NORM_FORWARD_AST_SHA = "0fbdca7808f8662c957741cd7647873651468de54c3681616b3d7b249bf27738"
NORM_EXECUTABLE_CLASS_AST_SHA = "d2c86532c5f5102d522ef34fe27385d4c7129c1feb8ada00ec75b6bd84789e82"
ACTIVATIONS = "config/upstream/weight_headers/qwen3_5_35b_a3b/activations.py"
ACTIVATIONS_SHA = "5b20c0a3625edc0001a98f09ce3c6b5baa1100e1d7ad8dee649e4d45c8468665"
ACTIVATIONS_GIT_BLOB_SHA = "2c3ad21a0c2b2cf71b288886283be7189dcb70a3"
ACTIVATIONS_URL = ("https://github.com/huggingface/transformers/blob/" +
                   TRANSFORMERS_REVISION + "/src/transformers/activations.py")
SILU_CLASS_AST_SHA = "b5c48ab9c11080ac560e5cde7274d4d2218e53633dbeb43a8c151bbc038b5310"
INSTANTIER_CLASS_AST_SHA = "3cf2610f447c6d9301c16a5db6c00851fa5a57a02610b84b41ad12a3353af034"
HEADS, WIDTH, EPS = 32, 128, 1e-6
STATUS = "DIAGNOSTIC_ONLY_NO_APPROVED_35B_GATED_NORM_THRESHOLD"
# Each tensor is the actual result of this original-forward operator. No
# independent arithmetic is substituted or added to the reference forward.
OP_SEQUENCE = (
    ("aten.to.dtype", "input_fp32", 185, "hidden_states assignment 1", "float32"),
    ("aten.pow.Tensor_Scalar", "squares", 186, "variance expression square", "float32"),
    ("aten.mean.dim", "variance", 186, "variance assignment", "float32"),
    ("aten.add.Tensor", "variance_eps", 188, "variance + epsilon", "float32"),
    ("aten.rsqrt.default", "inverse_rms", 188, "rsqrt expression", "float32"),
    ("aten.mul.Tensor", "normalized_fp32", 188, "hidden_states assignment 2", "float32"),
    ("aten.to.dtype", "normalized_bf16", 189, "first normalization BF16 cast", "bfloat16"),
    ("aten.mul.Tensor", "weighted_fp32", 189, "hidden_states assignment 3", "float32"),
    ("aten.to.dtype", "gate_fp32", 190, "gate FP32 cast", "float32"),
    ("aten.silu.default", "silu_fp32", 190, "SiLUActivation.forward result", "float32"),
    ("aten.mul.Tensor", "gated_fp32", 190, "hidden_states assignment 4", "float32"),
    ("aten.to.dtype", "output_bf16", 192, "original return BF16 cast", "bfloat16"),
)


def require(ok, detail):
    if not ok:
        raise ValueError("35B gated norm reference: " + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _find_class(tree, name):
    found = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    require(len(found) == 1, "one original " + name + " class required")
    return found[0]


def _forward(node):
    return next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "forward")


def _source_ast():
    """Verify all source bytes and unchanged executable forward ASTs."""
    raw = (ROOT / SOURCE).read_bytes()
    config_raw = (ROOT / CONFIG).read_bytes()
    activation_raw = (ROOT / ACTIVATIONS).read_bytes()
    require(sha(raw) == SOURCE_SHA, "official modeling source drift")
    require(sha(config_raw) == CONFIG_SHA, "official configuration drift")
    require(sha(activation_raw) == ACTIVATIONS_SHA, "official activations source drift")
    git_blob = hashlib.sha1(b"blob " + str(len(activation_raw)).encode() + b"\0" + activation_raw).hexdigest()
    require(git_blob == ACTIVATIONS_GIT_BLOB_SHA, "official activations Git blob drift")
    config = json.loads(config_raw)["text_config"]
    require((config["linear_num_value_heads"], config["linear_value_head_dim"], config["rms_norm_eps"])
            == (HEADS, WIDTH, EPS), "35B gated norm geometry/epsilon drift")
    norm = _find_class(ast.parse(raw), NORM_CLASS)
    require(sha(ast.dump(norm).encode()) == NORM_CLASS_AST_SHA, "original norm class AST drift")
    require(sha(ast.dump(_forward(norm)).encode()) == NORM_FORWARD_AST_SHA, "original norm forward AST drift")
    act_tree = ast.parse(activation_raw)
    silu = _find_class(act_tree, "SiLUActivation")
    instantier = _find_class(act_tree, "ClassInstantier")
    require(sha(ast.dump(silu).encode()) == SILU_CLASS_AST_SHA, "original SiLU class AST drift")
    require(sha(ast.dump(instantier).encode()) == INSTANTIER_CLASS_AST_SHA, "original activation instantier AST drift")
    mapping = [n.value for n in act_tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "ACT2CLS" for t in n.targets)]
    require(len(mapping) == 1 and isinstance(mapping[0], ast.Dict), "original activation mapping required")
    entries = {k.value: ast.unparse(v) for k, v in zip(mapping[0].keys, mapping[0].values)}
    require(entries["silu"] == "SiLUActivation", "original silu mapping drift")
    require(any(isinstance(n, ast.Assign) and ast.unparse(n) == "ACT2FN = ClassInstantier(ACT2CLS)"
                for n in act_tree.body), "original ACT2FN construction drift")
    executable_norm, executable_silu = copy.deepcopy(norm), copy.deepcopy(silu)
    require([ast.unparse(n) for n in norm.decorator_list] == ["use_kernel_forward_from_hub('RMSNormGated')"],
            "original norm decorator drift")
    require([ast.unparse(n) for n in silu.decorator_list] == ["use_kernel_forward_from_hub('SiLU')"],
            "original SiLU decorator drift")
    executable_norm.decorator_list = []
    executable_silu.decorator_list = []
    require(ast.dump(_forward(norm)) == ast.dump(_forward(executable_norm)), "norm forward altered")
    require(ast.dump(_forward(silu)) == ast.dump(_forward(executable_silu)), "SiLU forward altered")
    require(sha(ast.dump(executable_norm).encode()) == NORM_EXECUTABLE_CLASS_AST_SHA, "executable norm AST drift")
    # Compile separately so original source filenames/line numbers remain useful.
    norm_module = ast.Module(body=[executable_norm], type_ignores=[])
    activation_module = ast.Module(body=[executable_silu, copy.deepcopy(instantier)], type_ignores=[])
    identity = dict(
        source=SOURCE, source_sha256=SOURCE_SHA, config=CONFIG, config_sha256=CONFIG_SHA,
        model_revision=MODEL_REVISION, transformers_revision=TRANSFORMERS_REVISION,
        class_name=NORM_CLASS, class_lines=[norm.lineno, norm.end_lineno],
        original_class_ast_sha256=NORM_CLASS_AST_SHA, forward_ast_sha256=NORM_FORWARD_AST_SHA,
        executable_class_ast_sha256=NORM_EXECUTABLE_CLASS_AST_SHA,
        original_forward_unchanged=True, original_constructor_unchanged=True,
        activation_source=ACTIVATIONS, activation_source_url=ACTIVATIONS_URL, activation_source_sha256=ACTIVATIONS_SHA,
        activation_source_git_blob_sha=ACTIVATIONS_GIT_BLOB_SHA,
        activation_class="SiLUActivation", activation_class_lines=[silu.lineno, silu.end_lineno],
        activation_class_ast_sha256=SILU_CLASS_AST_SHA,
        activation_instantier_ast_sha256=INSTANTIER_CLASS_AST_SHA,
        activation_forward="return nn.functional.silu(input)", activation_forward_unchanged=True,
        activation_binding="original ClassInstantier({'silu': original SiLUActivation})",
        modifications=["remove optional RMSNormGated hub decorator", "remove optional SiLU hub decorator",
                       "reduce ACT2CLS to the sole requested silu entry"],
        full_transformers_module_executed=False, installed_transformers_imported=False,
        full_official_block_executed=False,
    )
    return (norm_module, activation_module), identity


def source_identity():
    """Pure source/config/AST verification, without importing Torch or NumPy."""
    return _source_ast()[1]


def validate_inputs(core_raw, z_raw, gamma_raw, tokens):
    """Raw BF16[M,32,128], BF16[M,32,128], original F32[128]."""
    require(type(tokens) is int and 1 <= tokens <= 128, "M1..128 required")
    for name, raw, count, fmt, mask in (
        ("core", core_raw, tokens * HEADS * WIDTH * 2, "<H", 0x7f80),
        ("Z", z_raw, tokens * HEADS * WIDTH * 2, "<H", 0x7f80),
        ("gamma", gamma_raw, WIDTH * 4, "<I", 0x7f800000),
    ):
        require(type(raw) is bytes and len(raw) == count, "complete " + name + " raw extent required")
        require(all(word[0] & mask != mask for word in struct.iter_unpack(fmt, raw)), "nonfinite " + name)


def _raw(tensor):
    import torch
    return tensor.detach().contiguous().reshape(-1).view(torch.uint8).numpy().tobytes()


def _tensor_identity(tensor):
    raw = _raw(tensor)
    return dict(shape=list(tensor.shape), stride=list(tensor.stride()), dtype=str(tensor.dtype),
                contiguous=tensor.is_contiguous(), device=str(tensor.device), bytes=len(raw), sha256=sha(raw))


def native_norm(core_raw, z_raw, gamma_raw, tokens):
    """Return (BF16 bytes, JSON-safe identity, intermediate dictionaries).

    Each intermediate contains exact raw bytes, shape/dtype/SHA, source line,
    operator, and passed=None. All are observations from the ONE original
    forward call, including every hidden_states tensor assignment, variance,
    square, mean+eps, rsqrt, first BF16 cast, weighted result, SiLU, and final
    multiply/return. No intermediate is an independent diagnostic recomputation.
    Shapes entering the class are [M*32,128], matching the original flatten.
    Gamma remains original FP32 and is neither rounded to BF16 nor offset by 1.
    Provenance of supplied actual core/Z/gamma is the caller's responsibility.
    """
    validate_inputs(core_raw, z_raw, gamma_raw, tokens)
    (norm_module, activation_module), source = _source_ast()
    require(os.environ.get("ATEN_CPU_CAPABILITY") == "default", "DEFAULT must precede Torch import")
    import torch
    from torch.utils._python_dispatch import TorchDispatchMode
    from candidates.qwen35_35b_prep.chunk_reference import _runtime

    before = _runtime(torch)
    namespace = dict(torch=torch, nn=torch.nn, Tensor=torch.Tensor, OrderedDict=OrderedDict,
                     __name__="pinned_qwen35_35b_gated_norm")
    exec(compile(activation_module, str(ROOT / ACTIVATIONS), "exec"), namespace)
    namespace["ACT2FN"] = namespace["ClassInstantier"]({"silu": namespace["SiLUActivation"]})
    exec(compile(norm_module, str(ROOT / SOURCE), "exec"), namespace)
    core = torch.frombuffer(bytearray(core_raw), dtype=torch.bfloat16).reshape(tokens * HEADS, WIDTH)
    z = torch.frombuffer(bytearray(z_raw), dtype=torch.bfloat16).reshape(tokens * HEADS, WIDTH)
    gamma = torch.frombuffer(bytearray(gamma_raw), dtype=torch.float32)
    with torch.device("meta"):
        model = namespace[NORM_CLASS](WIDTH, eps=EPS)
    model.load_state_dict({"weight": gamma}, assign=True)
    model.eval()
    require(model.weight.dtype == torch.float32 and _raw(model.weight) == gamma_raw, "original F32 gamma altered")
    tensors = dict(core=core, z=z, gamma=model.weight)
    inputs = {name: _tensor_identity(value) for name, value in tensors.items()}
    require(_raw(core) == core_raw and _raw(z) == z_raw, "flatten changed input bits")
    snapshots, operations = {}, []

    class Observe(TorchDispatchMode):
        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            index = len(operations)
            require(index < len(OP_SEQUENCE), "unexpected extra original-forward operation")
            operator, name, _, _, dtype = OP_SEQUENCE[index]
            require(str(func) == operator, "original-forward operation trace drift at " + name)
            result = func(*args, **(kwargs or {}))
            require(result.dtype == getattr(torch, dtype), "original-forward dtype drift at " + name)
            expected_shape = [tokens * HEADS, 1 if name in ("variance", "variance_eps", "inverse_rms") else WIDTH]
            require(list(result.shape) == expected_shape, "original-forward shape drift at " + name)
            operations.append(str(func))
            # Dispatch mode is popped while this callback runs; detach/clone do
            # not re-enter the observed stream and never replace result.
            snapshots[name] = result.detach().clone()
            return result

    with torch.inference_mode(), torch.autocast(device_type="cpu", enabled=False), Observe():
        output = model(core, z)
    require(len(operations) == len(OP_SEQUENCE), "incomplete original-forward execution")
    require(output.dtype == torch.bfloat16 and list(output.shape) == [tokens * HEADS, WIDTH],
            "complete BF16[M*32,128] output required")
    require(all(torch.isfinite(t).all().item() for t in snapshots.values()), "nonfinite original-forward observation")
    output_raw = _raw(output)
    require(len(output_raw) == tokens * HEADS * WIDTH * 2, "complete BF16 output extent required")
    require(_raw(snapshots["output_bf16"]) == output_raw, "observed return differs from returned output")
    require(inputs == {name: _tensor_identity(value) for name, value in tensors.items()}, "supplied input mutated")
    after = _runtime(torch)
    require(before == after, "runtime changed during original norm execution")
    require(source_identity() == source, "official source changed during execution")
    intermediate = {}
    for operator, name, line, original_role, _ in OP_SEQUENCE:
        tensor = snapshots[name]
        intermediate[name] = dict(
            raw=_raw(tensor), **_tensor_identity(tensor), operator=operator,
            original_forward_source=SOURCE, original_forward_line=line,
            original_role=original_role, observation="actual unmodified forward dispatch result",
            independent_diagnostic_recomputation=False, passed=None,
        )
    identity = dict(
        status=STATUS, passed=None, thresholds=None, native_acceptance=False,
        source=source, runtime=before, runtime_after=after, runtime_verified_before_and_after=True,
        implementation_sha256=sha(Path(__file__).read_bytes()), tokens=tokens, heads=HEADS, width=WIDTH,
        input_shape=[tokens, HEADS, WIDTH], flattened_shape=[tokens * HEADS, WIDTH],
        input_layout="contiguous token-head-feature; original reshape(-1,128)", inputs=inputs,
        core_sha256=sha(core_raw), z_sha256=sha(z_raw), gamma_sha256=sha(gamma_raw),
        input_bits_preserved=True, supplied_inputs_consumed=True, actual_input_provenance_verified=False,
        gamma_dtype="F32", gamma_transform="none; original gamma values, no BF16 cast, no +1",
        output=_tensor_identity(output), output_sha256=sha(output_raw),
        operations=operations, observations={name: {k: v for k, v in value.items() if k != "raw"}
                                             for name, value in intermediate.items()},
        observation_method="TorchDispatchMode result snapshots from one original forward; detach/clone only",
        independent_diagnostic_recomputation=False, original_forward_calls=1,
        original_hidden_states_assignment_observations=["input_fp32", "normalized_fp32", "weighted_fp32", "gated_fp32"],
        full_transformers_module_executed=False, full_official_block_executed=False,
        candidate_called=False, scalar_or_owner_called=False, vector_called=False, matrix_candidate_called=False,
        rtl_executed=False, hardware_cycles=None, state_committed=False, history_committed=False,
        generation_advanced=False, global_torch_settings_mutated=False,
        complete_gdn_final_gate="REQUIRED_DOWNSTREAM_UNCHANGED; not evaluated here",
    )
    return output_raw, identity, intermediate

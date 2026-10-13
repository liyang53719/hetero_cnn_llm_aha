"""Pinned 35B official chunk suffix on an already-prepared FP32 boundary.

Cold-state, full-32-head reference only. Inputs are supplied by the caller; this
module has no summary pins, artifact writes, producer calls, or global Torch
setters. The runner must establish the frozen runtime before native_chunk.
Standalone chunk/state native acceptance remains unassigned.
"""
from __future__ import annotations

import ast
import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from candidates.qwen35_35b_rms import reference as rms

ROOT = rms.ROOT
SOURCE = "config/upstream/weight_headers/qwen3_5_35b_a3b/modeling_qwen3_5_moe.py"
SOURCE_SHA = "ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30"
CONFIG = "config/upstream/weight_headers/qwen3_5_35b_a3b/config.json"
CONFIG_SHA = "5e4d7f74fec2f360eb9cfbfcd6ec0c4c76e684d3a11caaed259d9fd9bfbc7944"
SUFFIX_AST_SHA = "427c9083192058cce00dafb890878159e34585ed5163b2758c6e2efd2983d9c9"
EXECUTABLE_AST_SHA = "f4455d3dd3240e3a67289bac9a076dbbbaa253acb1d7e020f7b15760ae1b9bd8"
HEADS, WIDTH, VECTOR, CORE, CHUNK = 32, 128, 4096, 12800, 64
STATE_BYTES = HEADS * WIDTH * WIDTH * 4
STATUS = "DIAGNOSTIC_ONLY_NO_APPROVED_35B_CHUNK_THRESHOLD"
BINDING = """initial_dtype = torch.bfloat16
batch_size = 1
sequence_length = query.shape[2]
k_head_dim = 128
num_v_heads = 32
v_head_dim = 128
recurrent_state_shape = (batch_size, num_v_heads, k_head_dim, v_head_dim)
padded_output_shape = (batch_size, num_v_heads, -1, v_head_dim)
decay = g
"""


def require(ok, detail):
    if not ok:
        raise ValueError("35B prepared chunk reference: " + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _source_ast():
    """Replace only preparation; retain the original full suffix and signature."""
    source = (ROOT / SOURCE).read_bytes()
    config_raw = (ROOT / CONFIG).read_bytes()
    require(sha(source) == SOURCE_SHA, "official source drift")
    require(sha(config_raw) == CONFIG_SHA, "official config drift")
    config = json.loads(config_raw)["text_config"]
    keys = ("linear_num_key_heads", "linear_num_value_heads", "linear_key_head_dim", "linear_value_head_dim")
    require(tuple(config[k] for k in keys) == (16, HEADS, WIDTH, WIDTH), "35B geometry drift")
    found = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
             and n.name == "torch_chunk_gated_delta_rule"]
    require(len(found) == 1, "one original chunk function required")
    original = found[0]
    boundaries = [i for i, n in enumerate(original.body) if isinstance(n, ast.Assign)
                  and ast.unparse(n) == "query = query * scaling"]
    require(len(boundaries) == 1, "unambiguous original prepared boundary required")
    prefix, suffix = original.body[:boundaries[0] + 1], original.body[boundaries[0] + 1:]
    require(ast.unparse(suffix[0]) == "pad_size = (chunk_size - sequence_length % chunk_size) % chunk_size",
            "original prepared suffix boundary changed")
    dump = lambda nodes: ast.dump(ast.Module(body=nodes, type_ignores=[])).encode()
    require(sha(dump(suffix)) == SUFFIX_AST_SHA, "pinned suffix AST drift")
    function = copy.deepcopy(original)
    function.decorator_list = []
    bindings = ast.parse(BINDING).body
    function.body = bindings + copy.deepcopy(suffix)
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    require(dump(function.body[len(bindings):]) == dump(suffix), "suffix modified during extraction")
    require(sha(ast.dump(module).encode()) == EXECUTABLE_AST_SHA, "prepared executable AST drift")
    require(not any(isinstance(n, ast.Name) and n.id in ("l2norm", "scaling") for n in ast.walk(module)),
            "second Q/K normalization or Q scale is forbidden")
    identity = dict(source=SOURCE, source_sha256=SOURCE_SHA, config=CONFIG, config_sha256=CONFIG_SHA,
        model_revision="62704185bd97ad488cfc404e7caea797396b74dc",
        transformers_revision="42ca97014c85d71a88ad60d55f08cb9fb4d26e2c",
        original_function_ast_sha256=sha(ast.dump(original).encode()),
        removed_preparation_ast_sha256=sha(dump(prefix)), unchanged_suffix_ast_sha256=SUFFIX_AST_SHA,
        explicit_binding_ast_sha256=sha(dump(bindings)), executable_ast_sha256=EXECUTABLE_AST_SHA,
        original_function_lines=[original.lineno, original.end_lineno],
        removed_prefix_lines=[prefix[0].lineno, prefix[-1].end_lineno],
        unchanged_suffix_lines=[suffix[0].lineno, suffix[-1].end_lineno], suffix_unchanged=True,
        modifications=["remove_optional_hub_decorator", "replace_preparation_prefix_with_explicit_stage_bindings"],
        initial_dtype_binding="BF16_original_function_entry_before_preparation",
        query_transform="none_already_L2_normalized_and_scaled", key_transform="none_already_L2_normalized",
        export_branch=False, full_official_block_executed=False)
    return module, identity


def source_identity():
    """Pure source/config/AST verification without importing Torch."""
    return _source_ast()[1]


def _runtime(torch):
    """Verify caller-established settings; deliberately contains no setters."""
    require(os.environ.get("HETERO_35B_RUNTIME_PROFILE") == "recovery_20261013", "explicit recovery runtime profile required")
    require(os.environ.get("ATEN_CPU_CAPABILITY") == "default", "DEFAULT dispatch must precede Torch import")
    identity = rms.runtime_identity()
    require(len(identity["sha256"]) == 5, "all five runtime pins required")
    require(torch.are_deterministic_algorithms_enabled(), "runner must enable deterministic algorithms")
    require(torch.get_float32_matmul_precision() == "highest", "runner must select highest FP32 matmul precision")
    require(not torch.is_autocast_enabled("cpu"), "CPU autocast must be disabled")
    require(torch.backends.mkldnn.enabled, "frozen runtime has MKLDNN enabled")
    libc = ctypes.CDLL(None)
    libc.fegetround.restype = ctypes.c_int
    require(libc.fegetround() == 0, "FE_TONEAREST required")
    tiny = torch.tensor([1, 0x00800000, -2147483648], dtype=torch.int32).view(torch.float32)
    require((tiny[0] + tiny[0]).view(torch.int32).item() == 2 and
            (tiny[1] * .5).view(torch.int32).item() == 0x00400000 and
            (tiny[2] + tiny[2]).view(torch.int32).item() == -2147483648,
            "runner must preserve gradual underflow and signed zero")
    identity.update(deterministic_algorithms=True, float32_matmul_precision="highest", autocast=False,
        mkldnn_enabled=True, rounding="FE_TONEAREST", gradual_underflow_verified=True,
        global_torch_settings_mutated=False)
    return identity


def validate_inputs(raw, tokens):
    require(type(tokens) is int and 1 <= tokens <= 128, "M1..128 required")
    require(type(raw) is bytes and len(raw) == tokens * CORE * 4, "complete FP32[M,12800] bytes required")
    words = np.frombuffer(raw, "<u4").reshape(tokens, CORE)
    require(not np.any((words & 0x7f800000) == 0x7f800000), "nonfinite prepared input")
    data = words.view("<f4")
    q, k, v = [data[:, start:start + VECTOR].reshape(tokens, HEADS, WIDTH)
               for start in (0, VECTOR, 2 * VECTOR)]
    gates = data[:, 3 * VECTOR:].reshape(tokens, HEADS, 16)
    g, beta = gates[..., 0], gates[..., 1]
    require(np.all(g <= 0) and np.all(beta >= 0) and np.all(beta <= 1), "prepared gate domain")
    require(np.all(gates[..., 2:].view("<u4") == 0), "gate padding must be positive zero")
    require(np.all((v.view("<u4") & 0xffff) == 0) and np.all((beta.view("<u4") & 0xffff) == 0),
            "V and beta must retain BF16-widened FP32 bits")
    return q, k, v, g, beta


def _raw(tensor):
    import torch
    return tensor.detach().contiguous().reshape(-1).view(torch.uint8).numpy().tobytes()


def _tensor_identity(tensor):
    raw = _raw(tensor)
    return dict(shape=list(tensor.shape), stride=list(tensor.stride()), dtype=str(tensor.dtype),
        contiguous=tensor.is_contiguous(), device=str(tensor.device), bytes=len(raw), sha256=sha(raw))


def _prepared_tensors(torch, raw, tokens):
    q, k, v, g, beta = validate_inputs(raw, tokens)
    def head_contiguous(array):
        shape = (1, HEADS, tokens, WIDTH) if array.ndim == 3 else (1, HEADS, tokens)
        target = torch.empty(shape, dtype=torch.float32, device="cpu")
        target.copy_(torch.from_numpy(np.array(array, copy=True, order="C")).unsqueeze(0).transpose(1, 2))
        return target
    tensors = dict(query=head_contiguous(q), key=head_contiguous(k), value=head_contiguous(v),
        beta=head_contiguous(beta), g=torch.from_numpy(np.array(g, copy=True, order="C")).unsqueeze(0).transpose(1, 2))
    require(list(tensors["g"].stride()) == [HEADS * tokens, 1, HEADS], "original g FP32 transpose stride")
    require(list(tensors["beta"].stride()) == [HEADS * tokens, tokens, 1], "original beta head-contiguous stride")
    require(all(list(tensors[n].stride()) == [HEADS * tokens * WIDTH, tokens * WIDTH, WIDTH, 1]
                for n in ("query", "key", "value")), "original QKV head-contiguous stride")
    # Repack words only, to verify that layout adaptation changed no input bits.
    rebuilt = np.zeros((tokens, CORE), dtype="<u4")
    for i, name in enumerate(("query", "key", "value")):
        rebuilt[:, i * VECTOR:(i + 1) * VECTOR] = tensors[name].transpose(1, 2).reshape(tokens, VECTOR).numpy().view("<u4")
    gate_words = rebuilt[:, 3 * VECTOR:].reshape(tokens, HEADS, 16)
    for i, name in enumerate(("g", "beta")):
        gate_words[..., i] = tensors[name].transpose(1, 2).reshape(tokens, HEADS).numpy().view("<u4")
    require(rebuilt.tobytes() == raw, "prepared layout adaptation changed input bits")
    return tensors


def native_chunk(raw, tokens):
    """Return ({output: BF16 bytes, state: FP32 bytes}, identity).

    Complete cold-state original chunk64 suffix on caller-supplied actual Prep
    bytes. M65..128 remain one official function call with two chunk iterations.
    Q/K are already normalized, Q already scaled, and heads already repeated.
    The function never imports an owner, reads old summaries, writes artifacts,
    changes global Torch settings, or assigns a standalone acceptance threshold.
    """
    validate_inputs(raw, tokens)
    module, source = _source_ast()
    require(os.environ.get("ATEN_CPU_CAPABILITY") == "default", "set DEFAULT before importing Torch")
    import torch
    before = _runtime(torch)
    tensors = _prepared_tensors(torch, raw, tokens)
    inputs = {name: _tensor_identity(tensor) for name, tensor in tensors.items()}
    namespace = dict(torch=torch, F=torch.nn.functional, is_torchdynamo_exporting=lambda: False)
    exec(compile(module, str(ROOT / SOURCE) + ":prepared_chunk_suffix", "exec"), namespace)
    with torch.inference_mode(), torch.autocast(device_type="cpu", enabled=False):
        output, state = namespace["torch_chunk_gated_delta_rule"](
            tensors["query"], tensors["key"], tensors["value"], tensors["g"], tensors["beta"],
            chunk_size=CHUNK, initial_state=None, output_final_state=True, use_qk_l2norm_in_kernel=False)
    require(list(output.shape) == [1, tokens, HEADS, WIDTH] and output.dtype == torch.bfloat16,
            "complete official BF16 output shape/type")
    require(list(state.shape) == [1, HEADS, WIDTH, WIDTH] and state.dtype == torch.float32,
            "complete official FP32 state shape/type")
    require(torch.isfinite(output).all().item() and torch.isfinite(state).all().item(), "nonfinite official terminal result")
    require(inputs == {name: _tensor_identity(tensor) for name, tensor in tensors.items()}, "supplied prepared tensors mutated")
    result = dict(output=_raw(output), state=_raw(state))
    require(len(result["output"]) == tokens * VECTOR * 2 and len(result["state"]) == STATE_BYTES,
            "complete output/state byte extents")
    after = _runtime(torch)
    require(before == after, "runtime changed during suffix execution")
    require(source_identity() == source, "official source changed during suffix execution")
    identity = dict(status=STATUS, source=source, runtime=before, runtime_after=after,
        runtime_verified_before_and_after=True, implementation_sha256=sha(Path(__file__).read_bytes()),
        tokens=tokens, heads=HEADS, key_dim=WIDTH, value_dim=WIDTH, chunk_size=CHUNK,
        chunks=(tokens + CHUNK - 1) // CHUNK, pad_size=(-tokens) % CHUNK,
        input_shape=[tokens, CORE], input_sha256=sha(raw),
        input_layout="Q4096_K4096_V4096_gate32x16_FP32; gate={g,beta,14_positive_zero}",
        prepared_input_layout=inputs, prepared_input_bits_preserved=True,
        output=_tensor_identity(output), state=_tensor_identity(state),
        output_sha256=sha(result["output"]), state_sha256=sha(result["state"]),
        cold=True, initial_state_shape=[1, HEADS, WIDTH, WIDTH], initial_state_bytes=STATE_BYTES,
        initial_state_sha256=sha(bytes(STATE_BYTES)), initial_state_mode="official initial_state=None",
        query_transform="none_already_normalized_and_scaled", key_transform="none_already_normalized",
        reference_only=True, supplied_prepared_input_consumed=True, actual_prep_provenance_verified=False,
        input_provenance="caller responsibility; no historical summary or producer pin read", candidate_called=False,
        scalar_or_owner_called=False, vector_called=False, matrix_candidate_called=False,
        full_official_block_executed=False, rtl_executed=False, hardware_cycles=None,
        state_committed=False, history_committed=False, generation_advanced=False,
        native_acceptance=False, passed=None, thresholds=None,
        complete_gdn_final_gate="REQUIRED_DOWNSTREAM_UNCHANGED; not evaluated here")
    return result, identity


def _metric(actual, expected, dtype):
    """Raw finite BF16/FP32 metrics; exact FP64 decode includes subnormals."""
    require(dtype in ("bf16", "fp32"), "comparison dtype")
    size, frac_bits = (2, 7) if dtype == "bf16" else (4, 23)
    require(type(actual) is bytes and type(expected) is bytes and len(actual) == len(expected)
            and len(actual) > 0 and len(actual) % size == 0, "same complete nonempty comparison bytes")
    a, b = (np.frombuffer(x, "<u2" if size == 2 else "<u4") for x in (actual, expected))
    sign = 1 << (size * 8 - 1)
    def decode(words):
        bits = words.astype(np.int64)
        exponent = (bits >> frac_bits) & 255
        require(not np.any(exponent == 255), "nonfinite comparison value")
        fraction = bits & ((1 << frac_bits) - 1)
        significand = np.where(exponent == 0, fraction, (1 << frac_bits) + fraction)
        power = np.where(exponent == 0, 1 - 127 - frac_bits, exponent - 127 - frac_bits)
        value = np.ldexp(significand.astype(np.float64), power)
        return np.copysign(value, np.where(bits & sign, -1.0, 1.0))
    def ordered(words):
        bits = words.astype(np.int64)
        return np.where(bits & sign, sign - (bits & (sign - 1)), sign + bits)
    def subnormals(words):
        return int(np.count_nonzero((((words.astype(np.int64) >> frac_bits) & 255) == 0)
                                    & ((words.astype(np.int64) & ((1 << frac_bits) - 1)) != 0)))
    af, bf = decode(a), decode(b)
    different, ulp, delta = a != b, np.abs(ordered(a) - ordered(b)), np.abs(af - bf)
    return dict(dtype=dtype, elements=int(a.size), bit_mismatches=int(np.count_nonzero(different)),
        numerical_mismatches=int(np.count_nonzero(ulp)), signed_zero_only_mismatches=int(np.count_nonzero(different & (ulp == 0))),
        first_bit_mismatch=int(np.flatnonzero(different)[0]) if different.any() else None,
        max_ulp=int(ulp.max()), max_abs=float(delta.max()), mean_abs=float(delta.mean()),
        actual_subnormal_count=subnormals(a), expected_subnormal_count=subnormals(b),
        actual_sha256=sha(actual), expected_sha256=sha(expected), nonfinite=False,
        comparison_domain="finite_" + dtype + "_exact_fp64_decode", passed=None, thresholds=None)


def compare_outputs(actual, expected, tokens):
    """Full-shape output/state diagnostics, never a standalone native pass."""
    require(type(tokens) is int and 1 <= tokens <= 128, "M1..128 comparison geometry")
    for name, value in (("actual", actual), ("expected", expected)):
        require(type(value) is dict and set(value) == {"output", "state"}, name + " output/state pair required")
        require(type(value["output"]) is bytes and len(value["output"]) == tokens * VECTOR * 2
                and type(value["state"]) is bytes and len(value["state"]) == STATE_BYTES,
                name + " complete BF16[M,32,128] / FP32[32,128,128] geometry required")
    return dict(status=STATUS, tokens=tokens, passed=None, thresholds=None, native_acceptance=False,
        output=_metric(actual["output"], expected["output"], "bf16"),
        state=_metric(actual["state"], expected["state"], "fp32"),
        complete_gdn_final_gate="REQUIRED_DOWNSTREAM_UNCHANGED; not evaluated here")


def diagnose(actual, expected):
    """Full byte-extent diagnostics; infer M, never infer an acceptance gate."""
    require(type(expected) is dict and set(expected) == {"output", "state"}
            and type(expected["output"]) is bytes, "expected complete output/state byte pair required")
    row_bytes = VECTOR * 2
    require(len(expected["output"]) > 0 and len(expected["output"]) % row_bytes == 0,
            "complete BF16[M,32,128] output extent required")
    return compare_outputs(actual, expected, len(expected["output"]) // row_bytes)

"""Independent, pinned 35B InputPrep operations and per-role diagnostics.

The reference executes original forward AST nodes and the original chunk prefix
through query scaling. It does not import the actual Prep model/scalar, execute
recurrence, run a complete official model, or assign a standalone tolerance.
The caller persists returned raw bytes; this module performs no artifact writes.
"""
from __future__ import annotations

import ast
import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from ..qwen35_35b_rms import reference as rms

ROOT = Path(__file__).resolve().parents[2]
SOURCE, SOURCE_SHA = rms.SOURCE, rms.SOURCE_SHA
CONFIG, CONFIG_SHA = rms.CONFIG, rms.CONFIG_SHA
MODEL_REVISION, TRANSFORMERS_REVISION = rms.MODEL_REVISION, rms.TRANSFORMERS_REVISION
KEY_HEADS, VALUE_HEADS, WIDTH = 16, 32, 128
KEY_VECTOR, VECTOR, CONV, AB, CORE = 2048, 4096, 8192, 64, 12800
STATUS = "DIAGNOSTIC_ONLY_NO_APPROVED_35B_INPUT_PREP_THRESHOLD"


def require(ok, detail):
    if not ok:
        raise ValueError("35B InputPrep reference: " + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _rows(rows):
    require(type(rows) is int and 1 <= rows <= 128, "M1..128 geometry required")


def validate_inputs(conv_raw, ab_raw, alog_raw, dtbias_raw, rows):
    """Accept complete consumed boundaries, including original FP32 A_log."""
    _rows(rows)
    for name, raw, size, dtype in (
        ("Conv", conv_raw, rows * CONV * 2, "<u2"),
        ("AB", ab_raw, rows * AB * 2, "<u2"),
        ("A_log", alog_raw, VALUE_HEADS * 4, "<u4"),
        ("dt_bias", dtbias_raw, VALUE_HEADS * 2, "<u2"),
    ):
        require(type(raw) is bytes and len(raw) == size, "complete raw " + name + " shape required")
        bits = np.frombuffer(raw, dtype)
        mask = 0x7f80 if dtype == "<u2" else 0x7f800000
        require(not np.any((bits & mask) == mask), "nonfinite " + name + " input")


def _definitions(root=ROOT):
    """Verify whole source/config, then retain unchanged official AST nodes."""
    rms.source_identity(root)
    root = Path(root)
    source = (root / SOURCE).read_bytes()
    config = json.loads((root / CONFIG).read_bytes())["text_config"]
    require(tuple(config[name] for name in (
        "linear_num_key_heads", "linear_num_value_heads",
        "linear_key_head_dim", "linear_value_head_dim",
    )) == (KEY_HEADS, VALUE_HEADS, WIDTH, WIDTH), "16:32 grouped-head config drift")
    tree = ast.parse(source)

    def one(nodes, kind, name):
        found = [node for node in nodes if isinstance(node, kind) and node.name == name]
        require(len(found) == 1, "one original " + name + " required")
        return found[0]

    norm = one(tree.body, ast.FunctionDef, "l2norm")
    chunk = one(tree.body, ast.FunctionDef, "torch_chunk_gated_delta_rule")
    cls = one(tree.body, ast.ClassDef, "Qwen3_5MoeGatedDeltaNet")
    forward = one(cls.body, ast.FunctionDef, "forward")
    start = next(i for i, node in enumerate(forward.body) if isinstance(node, ast.Assign)
                 and ast.unparse(node.targets[0]) == "(query, key, value)")
    end = next(i for i in range(start, len(forward.body)) if isinstance(forward.body[i], ast.If)
               and ast.unparse(forward.body[i].test) == "self.num_v_heads // self.num_k_heads > 1")
    preparation = forward.body[start:end + 1]
    require([ast.unparse(node) for node in preparation[1:-1]] == [
        "query = query.reshape(batch_size, seq_len, -1, self.head_k_dim)",
        "key = key.reshape(batch_size, seq_len, -1, self.head_k_dim)",
        "value = value.reshape(batch_size, seq_len, -1, self.head_v_dim)",
        "beta = b.sigmoid()",
        "g = -self.A_log.float().exp() * F.softplus(a.float() + self.dt_bias)",
    ], "original reshape/gate expressions drift")
    require([ast.unparse(node) for node in preparation[-1].body] == [
        "query = query.repeat_interleave(self.num_v_heads // self.num_k_heads, dim=2)",
        "key = key.repeat_interleave(self.num_v_heads // self.num_k_heads, dim=2)",
    ], "original grouped Q/K repetition drift")
    stop = next(i for i, node in enumerate(chunk.body) if isinstance(node, ast.Assign)
                and ast.unparse(node) == "query = query * scaling")
    prefix = copy.deepcopy(chunk)
    prefix.decorator_list = []  # Never dispatch an optional external FLA kernel.
    prefix.body = prefix.body[:stop + 1]
    prefix.body.append(ast.Return(value=ast.Tuple(elts=[
        ast.Name(id=name, ctx=ast.Load()) for name in ("query", "key", "value", "decay", "beta")
    ], ctx=ast.Load())))

    def nodes_identity(nodes):
        module = ast.Module(body=nodes, type_ignores=[])
        return dict(ast_sha256=sha(ast.dump(module, include_attributes=False).encode()),
                    lines=[nodes[0].lineno, nodes[-1].end_lineno])

    identity = dict(
        model_revision=MODEL_REVISION, transformers_revision=TRANSFORMERS_REVISION,
        source=SOURCE, source_sha256=sha(source), config=CONFIG, config_sha256=CONFIG_SHA,
        class_name=cls.name, l2norm=nodes_identity([norm]),
        forward_preparation=nodes_identity(preparation), chunk_prefix=nodes_identity(chunk.body[:stop + 1]),
        extraction="unchanged forward nodes; unchanged l2norm; chunk prefix through Q scale plus observation return",
        optional_hub_decorator="removed; original Torch fallback only",
        external_namespace=["torch", "torch.nn.functional", "shape-and-parameter-only self"],
        full_official_block_executed=False, recurrence_implemented=False, rtl_executed=False,
    )
    return norm, preparation, prefix, identity


def source_identity(root=ROOT):
    """Source-only audit, without importing Torch or touching work artifacts."""
    return _definitions(root)[3]


def _official_ast(torch, root=ROOT):
    norm, preparation, prefix, identity = _definitions(root)
    namespace = dict(torch=torch, F=torch.nn.functional)
    functions = ast.fix_missing_locations(ast.Module(body=[norm, prefix], type_ignores=[]))
    exec(compile(functions, str(Path(root) / SOURCE), "exec"), namespace)
    prepare_code = compile(ast.Module(body=preparation, type_ignores=[]), str(Path(root) / SOURCE), "exec")
    return namespace, prepare_code, identity


def _runtime(torch):
    torch.set_num_threads(1)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    require(torch.set_flush_denormal(False), "gradual underflow configuration unavailable")
    libc = ctypes.CDLL(None)
    libc.fegetround.restype = ctypes.c_int
    require(libc.fegetround() == 0, "FE_TONEAREST required")
    tiny = torch.tensor([1, 0x00800000, -2147483648], dtype=torch.int32).view(torch.float32)
    require((tiny[0] + tiny[0]).view(torch.int32).item() == 2 and
            (tiny[1] * .5).view(torch.int32).item() == 0x00400000 and
            (tiny[2] + tiny[2]).view(torch.int32).item() == -2147483648,
            "gradual underflow and signed zero required")
    identity = rms.runtime_identity()
    identity.update(deterministic_algorithms=True, autocast=False,
                    float32_matmul_precision="highest", flush_denormal=False,
                    rounding="FE_TONEAREST", mkldnn_enabled=torch.backends.mkldnn.enabled)
    return identity


def native_prep(conv_raw, ab_raw, alog_raw, dtbias_raw, rows, *, root=ROOT):
    """Return (official-boundary FP32[M,12800] bytes, pin/runtime/hash identity).

    Conv is BF16[M,8192]=Q2048,K2048,V4096. AB is BF16[M,64]=A32,B32.
    A_log is original FP32[32], and dt_bias is BF16[32] with no padding.
    Output is Q4096,K4096,V4096,32 gate records of {g,beta,14 positive zeros}.
    Same-input versus independently upstream-produced inputs is the caller's
    choice; the reference never consumes actual Prep output to construct data.
    """
    validate_inputs(conv_raw, ab_raw, alog_raw, dtbias_raw, rows)
    require(os.environ.get("ATEN_CPU_CAPABILITY") == "default",
            "set ATEN_CPU_CAPABILITY=default before importing Torch")
    # Audit source before any numerical execution.
    source_identity(root)
    import torch
    runtime = _runtime(torch)
    namespace, prepare_code, source = _official_ast(torch, root)
    mixed = torch.frombuffer(bytearray(conv_raw), dtype=torch.bfloat16).reshape(1, rows, CONV)
    ab = torch.frombuffer(bytearray(ab_raw), dtype=torch.bfloat16).reshape(1, rows, AB)
    alog = torch.frombuffer(bytearray(alog_raw), dtype=torch.float32)
    bias = torch.frombuffer(bytearray(dtbias_raw), dtype=torch.bfloat16)
    namespace.update(mixed_qkv=mixed, batch_size=1, seq_len=rows,
        a=ab[..., :VALUE_HEADS], b=ab[..., VALUE_HEADS:],
        self=SimpleNamespace(num_k_heads=KEY_HEADS, num_v_heads=VALUE_HEADS,
            head_k_dim=WIDTH, head_v_dim=WIDTH, key_dim=KEY_VECTOR, value_dim=VECTOR,
            A_log=alog, dt_bias=bias))
    with torch.inference_mode(), torch.autocast(device_type="cpu", enabled=False):
        exec(prepare_code, namespace)
        require(namespace["beta"].dtype == torch.bfloat16 and namespace["g"].dtype == torch.float32,
                "official beta BF16 / g FP32 boundary drift")
        q, k, v, g, beta = namespace["torch_chunk_gated_delta_rule"](
            namespace["query"], namespace["key"], namespace["value"],
            namespace["g"], namespace["beta"], use_qk_l2norm_in_kernel=True)
        require(all(tuple(x.shape) == (1, VALUE_HEADS, rows, WIDTH) for x in (q, k, v)) and
                all(tuple(x.shape) == (1, VALUE_HEADS, rows) for x in (g, beta)), "official fullshape drift")
        require(all(x.dtype == torch.float32 and torch.isfinite(x).all().item()
                    for x in (q, k, v, g, beta)), "nonfinite or non-FP32 official output")
        output = torch.zeros((rows, CORE), dtype=torch.float32)
        for role, value in enumerate((q, k, v)):
            output[:, role * VECTOR:(role + 1) * VECTOR] = value.transpose(1, 2).reshape(rows, VECTOR)
        gates = output[:, 3 * VECTOR:].reshape(rows, VALUE_HEADS, 16)
        gates[..., 0] = g.transpose(1, 2).reshape(rows, VALUE_HEADS)
        gates[..., 1] = beta.transpose(1, 2).reshape(rows, VALUE_HEADS)
    raw = output.numpy().astype("<f4", copy=False).tobytes()
    identity = dict(scope="PINNED_35B_OFFICIAL_INPUT_PREP_OPERATIONS_ONLY", source=source, runtime=runtime,
        implementation_sha256=sha(Path(__file__).read_bytes()), rows=rows, key_heads=KEY_HEADS,
        value_heads=VALUE_HEADS, head_width=WIDTH, input_conv_shape=[rows, CONV],
        input_ab_shape=[rows, AB], output_shape=[rows, CORE],
        input_dtypes=dict(conv="BF16", ab="BF16_A32_then_B32", a_log="original_FP32", dt_bias="BF16_32_no_padding"),
        conv_sha256=sha(conv_raw), ab_sha256=sha(ab_raw), a_log_sha256=sha(alog_raw),
        dt_bias_sha256=sha(dtbias_raw), output_sha256=sha(raw),
        qkv_before_repeat_shapes=[[1, rows, KEY_HEADS, WIDTH]] * 2 + [[1, rows, VALUE_HEADS, WIDTH]],
        qkv_before_chunk_shape=[1, rows, VALUE_HEADS, WIDTH], chunk_qkv_shape=[1, VALUE_HEADS, rows, WIDTH],
        layout="FP32[M,12800]=Q4096_K4096_V4096_gates512; gate64B={g,beta,14_positive_zero}",
        qk_head_mapping="destination_head//2; repeat_interleave(2,dim=2) before chunk",
        operation_order=["BF16 split/reshape Q16 K16 V32", "BF16 beta=b.sigmoid()",
            "FP32 g=-exp(A_log.float())*softplus(a.float()+BF16_dt_bias)",
            "BF16 Q/K repeat_interleave(2,dim=2)",
            "transpose(1,2).to(FP32,memory_format=contiguous_format)",
            "FP32 Q/K multiply by rsqrt(sum(x*x)+1e-6)", "FP32 Q multiply by 128**-0.5"],
        scalar_or_owner_called=False, actual_prep_output_consumed=False,
        reference_only=True, token_independent=True, full_official_block_executed=False,
        recurrence_implemented=False, rtl_executed=False, hardware_cycles=None,
        history_committed=False, state_committed=False, generation_advanced=False,
        official_stage_acceptance="UNASSIGNED; diagnostics only")
    return raw, identity


def compare_fp32(actual, expected):
    """FP32 diagnostics with no threshold, and no hidden relative-error floor.

    Relative error is abs(actual-reference)/abs(reference). For reference=0,
    0/0 is defined as 0; a nonzero actual is counted explicitly and aggregate
    relative values are null. Nonfinite values also make aggregate metrics null.
    ULP ordering treats signed zeros numerically equal but retains bit mismatch.
    """
    require(type(actual) is bytes and type(expected) is bytes and len(actual) == len(expected)
            and len(actual) > 0 and len(actual) % 4 == 0, "same complete FP32 comparison shape required")
    a, b = np.frombuffer(actual, "<u4"), np.frombuffer(expected, "<u4")
    fa, fb = a.view("<f4"), b.view("<f4")
    finite = np.isfinite(fa) & np.isfinite(fb)
    all_finite = bool(finite.all())
    different = a != b

    def ordered(bits):
        value = bits.astype(np.int64)
        return np.where(value & 0x80000000, 0x80000000 - (value & 0x7fffffff), 0x80000000 + value)

    ulp = np.abs(ordered(a) - ordered(b))
    af, bf = fa[finite].astype(np.float64), fb[finite].astype(np.float64)
    delta = np.abs(af - bf)
    nz = bf != 0
    zero_failures = int(np.count_nonzero(~nz & (af != 0)))
    rel_nonzero = delta[nz] / np.abs(bf[nz])
    relative_defined = all_finite and zero_failures == 0
    return dict(elements=int(a.size), bit_mismatches=int(different.sum()),
        numerical_mismatches=int(np.count_nonzero(ulp[finite])),
        signed_zero_only_mismatches=int(np.count_nonzero(different & (ulp == 0) & finite)),
        max_abs=float(delta.max()) if all_finite else None,
        mean_abs=float(delta.mean()) if all_finite else None,
        max_relative=float(rel_nonzero.max(initial=0)) if relative_defined else None,
        mean_relative=float(rel_nonzero.sum() / a.size) if relative_defined else None,
        reference_nonzero_elements=int(nz.sum()),
        max_relative_reference_nonzero=float(rel_nonzero.max()) if len(rel_nonzero) else None,
        mean_relative_reference_nonzero=float(rel_nonzero.mean()) if len(rel_nonzero) else None,
        relative_reference_nonzero_scope="finite actual/reference pairs with nonzero reference",
        zero_reference_nonzero_actual=zero_failures,
        relative_definition="abs(actual-reference)/abs(reference); 0/0=0; nonzero/0 makes aggregate null",
        max_fp32_ulp=int(ulp.max()) if all_finite else None,
        actual_nonfinite=int((~np.isfinite(fa)).sum()), expected_nonfinite=int((~np.isfinite(fb)).sum()),
        nonfinite=not all_finite,
        first_bit_mismatch=int(np.flatnonzero(different)[0]) if different.any() else None,
        actual_sha256=sha(actual), expected_sha256=sha(expected))


def _roles(raw, rows):
    _rows(rows)
    require(type(raw) is bytes and len(raw) == rows * CORE * 4, "complete FP32[M,12800] output required")
    words = np.frombuffer(raw, "<u4").reshape(rows, CORE)
    gates = words[:, 3 * VECTOR:].reshape(rows, VALUE_HEADS, 16)
    arrays = dict(query=words[:, :VECTOR], key=words[:, VECTOR:2 * VECTOR],
        value=words[:, 2 * VECTOR:3 * VECTOR], beta=gates[..., 1], g=gates[..., 0],
        gate_padding=gates[..., 2:])
    return {name: np.ascontiguousarray(value).tobytes() for name, value in arrays.items()}


def compare_roles(actual_raw, expected_raw, rows):
    """Return separate query/key/value/beta/g/padding diagnostics in row order."""
    actual, expected = _roles(actual_raw, rows), _roles(expected_raw, rows)
    result = {}
    for name in actual:
        item = compare_fp32(actual[name], expected[name])
        shape = ([rows, VALUE_HEADS, WIDTH] if name in ("query", "key", "value") else
                 [rows, VALUE_HEADS, 14] if name == "gate_padding" else [rows, VALUE_HEADS])
        item["shape"] = shape
        first = item["first_bit_mismatch"]
        item["first_bit_mismatch_coordinates"] = list(map(int, np.unravel_index(first, shape))) if first is not None else None
        result[name] = item
    return result


def diagnose(actual_raw, expected_raw, rows, *, identity=None):
    """Compare supplied outputs only; never issue a numerical acceptance gate."""
    roles = compare_roles(actual_raw, expected_raw, rows)
    if identity is not None:
        require(identity.get("output_sha256") == sha(expected_raw) and identity.get("rows") == rows,
                "reference identity must match expected output and rows")
    padding = _roles(actual_raw, rows)["gate_padding"]
    return dict(status=STATUS, passed=None, thresholds=None, official_stage_acceptance="UNASSIGNED",
        rows=rows, roles=roles, identity=identity, actual_sha256=sha(actual_raw), expected_sha256=sha(expected_raw),
        all_gate_padding_positive_zero=bool(np.all(np.frombuffer(padding, "<u4") == 0)),
        complete_gdn_final_gate="REQUIRED_DOWNSTREAM_UNCHANGED; not evaluated by this stage",
        full_official_block_executed=False, rtl_executed=False)

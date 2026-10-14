"""Pinned original decoder residual and post-attention RMS component only.

Line 943 executes with original hidden input as ``residual`` and the actual
owner O output as ``hidden_states``. Line 947 then calls the complete original
RMS class on that observed BF16 residual. No candidate formula, producer, MoE,
or full decoder is executed. Returned reference bytes are diagnostics only.

Import, source inspection, wrappers, and raw admission use only the standard
library. Torch and NumPy are loaded only by the explicit component execution.
"""
from __future__ import annotations

import ast
from pathlib import Path
import struct

from candidates.qwen35_35b_rms import reference as rms

ROOT = Path(__file__).resolve().parents[2]
SOURCE, SOURCE_SHA = rms.SOURCE, rms.SOURCE_SHA
CONFIG, CONFIG_SHA = rms.CONFIG, rms.CONFIG_SHA
MODEL_REVISION, TRANSFORMERS_REVISION = rms.MODEL_REVISION, rms.TRANSFORMERS_REVISION
WIDTH, EPS = rms.WIDTH, rms.EPS
DECODER_SHA = "f10fc30285138600a3d48ba604242a81773c97048350713de3681660648fac8d"
RESIDUAL_SHA = "81b51790c99c03e1b1894be33d47d68f706201ec0b1d47fb77096c3b34b8836d"
POSTNORM_SHA = "1b0cd09b22c66b1fb99b03d87160da761b139920b802fbb66a5c520f385c1dc2"
RMS_CLASS_SHA = rms.CLASS_SHA
sha, file_sha = rms.sha, rms.file_sha
runtime_identity, runtime_selection = rms.runtime_identity, rms.runtime_selection

RMS_SEQUENCE = (
    ("aten.to.dtype", "input_fp32"),
    ("aten.pow.Tensor_Scalar", "squares"),
    ("aten.mean.dim", "mean"),
    ("aten.add.Tensor", "mean_eps"),
    ("aten.rsqrt.default", "inverse"),
    ("aten.mul.Tensor", "scaled"),
    ("aten.to.dtype", "weight_fp32"),
    ("aten.add.Tensor", "gamma"),
    ("aten.mul.Tensor", "weighted"),
    ("aten.type_as.default", "output"),
)
SEQUENCE = (("aten.add.Tensor", "residual"),) + RMS_SEQUENCE


def require(ok, why):
    if not ok:
        raise ValueError("35B residual/postnorm reference: " + why)


def _source_definition(root=ROOT):
    """Pin whole source, complete decoder/class, and both untouched statements."""
    root = Path(root)
    _, rms_identity = rms._source_definition(root)
    raw = (root / SOURCE).read_bytes()
    require(sha(raw) == SOURCE_SHA, "official modeling source drift")
    lines = raw.splitlines(keepends=True)
    classes = [n for n in ast.parse(raw).body if isinstance(n, ast.ClassDef)
               and n.name == "Qwen3_5MoeDecoderLayer"]
    require(len(classes) == 1, "one original decoder class required")
    decoder = classes[0]
    require((decoder.lineno, decoder.end_lineno) == (898, 954) and
            sha(b"".join(lines[897:954])) == DECODER_SHA, "complete original decoder class drift")
    forwards = [n for n in decoder.body if isinstance(n, ast.FunctionDef) and n.name == "forward"]
    require(len(forwards) == 1, "one original decoder forward required")
    expected = (
        (943, RESIDUAL_SHA, "hidden_states = residual + hidden_states"),
        (947, POSTNORM_SHA, "hidden_states = self.post_attention_layernorm(hidden_states)"),
    )
    nodes, statements = [], []
    for line, digest, text in expected:
        matches = [n for n in forwards[0].body if isinstance(n, ast.Assign) and n.lineno == line]
        require(len(matches) == 1, "one original statement required at line " + str(line))
        node = matches[0]
        require(node.end_lineno == line and sha(lines[line - 1]) == digest and
                ast.dump(node, include_attributes=False) == ast.dump(ast.parse(text).body[0], include_attributes=False),
                "original statement drift at line " + str(line))
        nodes.append(node)
        statements.append(dict(line=line, end_line=line, source=text, sha256=digest,
                               ast_sha256=sha(ast.dump(node, include_attributes=True).encode())))
    return tuple(nodes), dict(
        model_revision=MODEL_REVISION, transformers_revision=TRANSFORMERS_REVISION,
        source=SOURCE, source_sha256=SOURCE_SHA, config=CONFIG, config_sha256=CONFIG_SHA,
        decoder_class="Qwen3_5MoeDecoderLayer", decoder_lines=[898, 954], decoder_sha256=DECODER_SHA,
        statements=statements, rms=rms_identity,
        extraction="unmodified original assignment AST nodes inside transport-only function wrappers; original filename and line numbers",
        residual_dtype="torch.bfloat16", postnorm_input="observed residual BF16; no FP32 carry-through",
        full_native_forward=False, installed_moe_module_imported=False, mlp_executed=False,
        rtl_executed=False, reference_bytes_may_fill_producer=False)


def source_identity(root=ROOT):
    """Cold source/config verification without Torch, NumPy, or work artifacts."""
    return _source_definition(root)[1]


def _statement_module(node, name, arguments):
    """Wrap, never rewrite, the exact source assignment. The return is plumbing."""
    wrapper = ast.FunctionDef(
        name=name,
        args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=x) for x in arguments],
                           vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
        body=[node, ast.copy_location(ast.Return(value=ast.Name(id="hidden_states", ctx=ast.Load())), node)],
        decorator_list=[], returns=None, type_comment=None)
    ast.copy_location(wrapper, node)
    return ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))


def source_functions(root=ROOT):
    """Compile the exact two statements; no arithmetic library is needed here."""
    nodes, identity = _source_definition(root)
    namespace = {"__name__": "pinned_qwen35_35b_residual_postnorm"}
    specs = (("original_residual", ("residual", "hidden_states")),
             ("original_postnorm", ("self", "hidden_states")))
    for node, (name, arguments) in zip(nodes, specs):
        exec(compile(_statement_module(node, name, arguments), str(Path(root) / SOURCE), "exec"), namespace)
    return (namespace[specs[0][0]], namespace[specs[1][0]]), identity


def validate_raw(hidden_raw, o_raw, weight_raw, tokens):
    """Finite, complete BF16 inputs. Pure stdlib; bool is not a token count."""
    require(type(tokens) is int and 1 <= tokens <= 128, "M1..128 required")
    for name, raw, size in (("hidden", hidden_raw, tokens * WIDTH * 2),
                            ("actual O", o_raw, tokens * WIDTH * 2),
                            ("post-attention weight", weight_raw, WIDTH * 2)):
        require(type(raw) is bytes and len(raw) == size, "complete BF16 " + name + " required")
        require(all((word & 0x7f80) != 0x7f80 for word, in struct.iter_unpack("<H", raw)),
                "nonfinite BF16 " + name)


def component(hidden_raw, o_raw, weight_raw, tokens, *, root=ROOT):
    """Execute 1 BF16 residual add + original RMS's 10 dispatches, same input.

    Runtime checking is mandatory and never changes runtime settings. Caller
    selects the pinned wrapper/profile and configures one intra/inter-op thread.
    ``trace`` uses the existing RMS reference's names and FP32 array shapes.
    ``sum_auxiliary`` is a separately labelled observer-only reduction, never
    the original mean or a producer input. No numerical tolerance is applied.
    """
    validate_raw(hidden_raw, o_raw, weight_raw, tokens)
    (residual_fn, postnorm_fn), identity = source_functions(root)
    import torch
    from torch.utils._python_dispatch import TorchDispatchMode

    runtime = runtime_identity()
    cls, class_identity = rms.source_class(root)
    require(class_identity == identity["rms"], "RMS source identity changed before execution")
    hidden = torch.frombuffer(bytearray(hidden_raw), dtype=torch.bfloat16).reshape(1, tokens, WIDTH)
    actual_o = torch.frombuffer(bytearray(o_raw), dtype=torch.bfloat16).reshape(1, tokens, WIDTH)
    weight = torch.frombuffer(bytearray(weight_raw), dtype=torch.bfloat16)
    with torch.device("meta"):
        norm = cls(WIDTH, eps=EPS)
    norm.load_state_dict({"weight": weight}, assign=True)
    model = torch.nn.Module()
    model.post_attention_layernorm = norm
    model.eval()
    snapshots, operations, dispatch = {}, [], []

    class Observe(TorchDispatchMode):
        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            index = len(operations)
            require(index < len(SEQUENCE) and str(func) == SEQUENCE[index][0], "official operation trace drift")
            result = func(*args, **(kwargs or {}))
            name = SEQUENCE[index][1]
            expected_dtype = torch.bfloat16 if name in ("residual", "output") else torch.float32
            expected_shape = ([WIDTH] if name in ("weight_fp32", "gamma") else
                              [1, tokens, 1] if name in ("mean", "mean_eps", "inverse") else [1, tokens, WIDTH])
            require(result.dtype == expected_dtype and list(result.shape) == expected_shape,
                    "original dtype/shape drift at " + name)
            operations.append(str(func))
            dispatch.append(dict(index=index, name=name, operation=str(func), dtype=str(result.dtype),
                                 shape=list(result.shape), original_execution=True))
            snapshots[name] = result.detach().clone()
            return result

    with torch.inference_mode(), torch.autocast("cpu", enabled=False), Observe():
        residual = residual_fn(hidden, actual_o)
        output = postnorm_fn(model, residual)
    require(len(operations) == len(SEQUENCE), "incomplete component execution")
    residual_bytes = residual.view(torch.uint16).numpy().astype("<u2", copy=False).tobytes()
    output_bytes = output.view(torch.uint16).numpy().astype("<u2", copy=False).tobytes()
    snapshots["sum_auxiliary"] = snapshots["squares"].sum(-1, keepdim=True)
    trace = {name: tensor.numpy().copy() for name, tensor in snapshots.items()
             if name not in ("residual", "output")}
    trace_raw = {name: value.astype("<f4", copy=False).tobytes() for name, value in trace.items()}
    return dict(
        residual=residual_bytes, output=output_bytes, postnorm=output_bytes,
        trace=trace, trace_raw=trace_raw, operations=operations, dispatch=dispatch,
        residual_operations=operations[:1], rms_operations=operations[1:],
        trace_provenance={name: ("auxiliary observer sum; not an original forward operation" if name == "sum_auxiliary"
                                 else "original RMS dispatch output") for name in trace},
        source=identity, runtime=runtime,
        input_sha256=sha(hidden_raw), hidden_sha256=sha(hidden_raw), o_sha256=sha(o_raw),
        weight_sha256=sha(weight_raw), residual_sha256=sha(residual_bytes),
        output_sha256=sha(output_bytes), postnorm_sha256=sha(output_bytes),
        same_input_reference=True, full_native_forward=False, reference_bytes_may_fill_producer=False,
        passed=None, thresholds=None)

"""Pinned 35B Conv fallback component; independent recipe reused, no full block."""
import ast
import json
from pathlib import Path
import numpy as np
from ..qwen35_35b_rms import reference as rms
from ..qwen35_gdn_prefill.conv import reference as fixed

ROOT = Path(__file__).resolve().parents[2]
CHANNELS = 8192


def source_function(root=ROOT):
    rms.source_identity(root)  # exact 35B modeling file/config/class authority
    raw = (Path(root) / rms.SOURCE).read_bytes()
    source = ast.parse(raw)
    fn = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'causal_conv1d_fn']
    fixed.require(len(fn) == 1, 'one original Conv function')
    fixed.require([ast.unparse(x) for x in fn[0].decorator_list] ==
        ["use_kernel_func_from_hub_with_fallback('causal_conv1d_fn', 'causal_conv1d')"], 'Conv dispatch drift')
    cfg = json.loads((Path(root) / rms.CONFIG).read_bytes())['text_config']
    fixed.require(cfg['linear_conv_kernel_dim'] == 4 and cfg['hidden_act'] == 'silu' and
        2*cfg['linear_num_key_heads']*cfg['linear_key_head_dim']+
        cfg['linear_num_value_heads']*cfg['linear_value_head_dim'] == CHANNELS, '35B Conv config drift')
    return fn[0], dict(model_revision=rms.MODEL_REVISION, transformers_revision=rms.TRANSFORMERS_REVISION,
        source=rms.SOURCE, source_sha256=rms.SOURCE_SHA,
        function_sha256=fixed.sha(ast.get_source_segment(raw.decode(),fn[0]).encode()),
        lines=[fn[0].lineno, fn[0].end_lineno], scope='PINNED_35B_CONV_FALLBACK_COMPONENT_ONLY',
        optional_hub_decorator='identity_no_external_kernel', full_block=False, rtl_executed=False)


def native_conv(qkv_raw, weight_raw, rows, *, root=ROOT):
    x, weight, history = fixed._inputs(qkv_raw, weight_raw, rows, CHANNELS, None)
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    identity = rms.runtime_identity()
    fn, source = source_function(root)
    namespace = dict(torch=torch, nn=torch.nn, F=torch.nn.functional,
        ACT2FN={'silu':torch.nn.functional.silu},
        use_kernel_func_from_hub_with_fallback=lambda *args: lambda func: func)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(Path(root)/rms.SOURCE), 'exec'), namespace)
    hidden=torch.frombuffer(bytearray(qkv_raw),dtype=torch.bfloat16).reshape(1,rows,CHANNELS).transpose(1,2)
    weights=torch.frombuffer(bytearray(weight_raw),dtype=torch.bfloat16).reshape(CHANNELS,4)
    with torch.inference_mode():
        pre=namespace['causal_conv1d_fn'](hidden,weights,bias=None,activation=None)
        post=namespace['causal_conv1d_fn'](hidden,weights,bias=None,activation='silu')
    fixed.require(list(pre.shape)==[1,CHANNELS,rows] and list(post.shape)==[1,CHANNELS,rows], 'full Conv shape')
    fixed.require(torch.isfinite(pre).all().item() and torch.isfinite(post).all().item(), 'finite native Conv')
    def raw(t):return t.transpose(1,2).contiguous().view(torch.int16).numpy().astype('<i2',copy=False).tobytes()
    return dict(conv=raw(pre),silu=raw(post),history=fixed._history(x,history)), dict(source=source,runtime=identity,
        qkv_sha256=fixed.sha(qkv_raw),weight_sha256=fixed.sha(weight_raw),cold=True,history_committed=False)


def fixed_conv(qkv_raw, weight_raw, rows):
    source_function()
    return fixed.fixed_conv(qkv_raw, weight_raw, rows, channels=CHANNELS)

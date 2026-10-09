#!/usr/bin/env python3
"""Prepare a bounded true-checkpoint recurrent-core oracle, never a full block gate.

This consumes verified Dense/Conv reference input files solely to define this
substage's explicit input boundary. Expected output/state files are comparator
only and must never be written into simulated DDR in place of owner arithmetic.
"""
from pathlib import Path
import argparse
import hashlib
import inspect
import json
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.pinned_gdn_payload import load_payload
from heteronpu.qwen35_gdn_recurrent_fp32 import recurrent_step, bf16_rne, expand_bf16
from heteronpu.qwen35_gdn_numpy_reference import recurrent_gated_delta_rule
from heteronpu.qwen35_numpy_reference import compare


def sha(x): return hashlib.sha256(x).hexdigest()

def ulp(a, b):
    a, b = np.asarray(a).astype(np.int32), np.asarray(b).astype(np.int32)
    ordered = lambda x: np.where(x & 0x8000, 0x8000 - (x & 0x7fff), 0x8000 + x)
    distance = np.abs(ordered(a) - ordered(b))
    return {'max_bf16_ulp': int(distance.max()), 'bit_mismatches': int(np.count_nonzero(a != b)),
            'threshold_bf16_ulp': 1, 'signed_zero_numeric_equal': True, 'pass': bool(distance.max() <= 1)}


def run(source, output, heads):
    import torch
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    profile = json.loads((ROOT / 'config/model_profiles/qwen3_5_0p8b.json').read_text())
    config_bytes = (ROOT / 'config/upstream/qwen3_5_0p8b/config.json').read_bytes()
    assert sha(config_bytes) == profile['config_sha256']
    config = json.loads(config_bytes)['text_config']
    assert (config['linear_num_key_heads'], config['linear_num_value_heads'], config['linear_key_head_dim'], config['linear_value_head_dim'], config['mamba_ssm_dtype']) == (16, 16, 128, 128, 'float32')
    installed = Path(inspect.getfile(official))
    assert sha(installed.read_bytes()) == profile['transformers_source']['sha256']
    manifest, raw = load_payload(ROOT, ROOT / 'work/qwen35_layer0_payload')
    source_manifest = json.loads((source / 'manifest.json').read_text())
    assert source_manifest['model_revision'] == profile['revision']
    for name, rec in source_manifest['files'].items():
        data = (source / name).read_bytes()
        assert len(data) == rec['bytes'] and sha(data) == rec['sha256'], name
    def weight(name):
        spec = next(x for x in manifest['tensors'] if x['local_name'] == name)
        x = np.frombuffer(raw[name], dtype='<f4' if spec['dtype'] == 'F32' else '<u2').reshape(spec['shape'])
        return torch.from_numpy(x.copy() if spec['dtype'] == 'F32' else expand_bf16(x).copy()).to(torch.float32 if spec['dtype'] == 'F32' else torch.bfloat16)
    a_weight, b_weight = weight('linear_attn.in_proj_a.weight'), weight('linear_attn.in_proj_b.weight')
    a_log, dt = weight('linear_attn.A_log'), weight('linear_attn.dt_bias')
    assert not output.exists() or not any(output.iterdir())
    output.mkdir(parents=True, exist_ok=True)
    files, checks = {}, []
    def save(name, array):
        data = np.ascontiguousarray(array).tobytes()
        (output / name).write_bytes(data)
        files[name] = {'bytes': len(data), 'sha256': sha(data)}
    ours_state = native_state = fp64_state = None
    for token in range(2):
        conv = expand_bf16(np.fromfile(source / f'expected_output{token}.bf16le', dtype='<u2')).reshape(3,16,128)[:, :heads]
        qraw, kraw, v = [torch.from_numpy(x.copy()) for x in conv]
        qnorm = official.l2norm(qraw, dim=-1, eps=1e-6)
        knorm = official.l2norm(kraw, dim=-1, eps=1e-6)
        scaled = qnorm * (128 ** -0.5) if token == 0 else qnorm / (128 ** 0.5)
        x = torch.from_numpy(expand_bf16(np.fromfile(source / f'activation{token}.bf16le', dtype='<u2')).copy()).to(torch.bfloat16)
        a, b = torch.nn.functional.linear(x, a_weight), torch.nn.functional.linear(x, b_weight)
        beta = b.sigmoid().float()[:heads]
        g = (-a_log.float().exp() * torch.nn.functional.softplus(a.float() + dt))[:heads]
        gates = np.stack((g.numpy(), beta.numpy()), axis=-1)
        q, k, values = scaled.numpy(), knorm.numpy(), v.numpy()
        out, ours_state, out32 = recurrent_step(q, k, values, gates, ours_state)
        # Official recurrence runs independently from its own preceding state.
        # Query is unscaled here because upstream applies its own sqrt scaling.
        native_fn = official.torch_chunk_gated_delta_rule if token == 0 else official.torch_recurrent_gated_delta_rule
        native_out, native_state = native_fn(
            qnorm[None,None], knorm[None,None], v[None,None], g[None,None], beta[None,None],
            initial_state=native_state, output_final_state=True, use_qk_l2norm_in_kernel=False)
        fp64_out, fp64_state = recurrent_gated_delta_rule(qnorm.numpy()[None,None], k[None,None], values[None,None],
            g.numpy()[None,None], beta.numpy()[None,None], fp64_state, normalize_qk=False)
        metrics = {'case': 'cold_m1' if token == 0 else 'carried_decode_m1',
                   'official_state_fp32': compare(ours_state, native_state.numpy()[0]),
                   'official_core_fp32': compare(out32, native_out.numpy()[0,0]),
                   'official_output_bf16': ulp(out, bf16_rne(native_out.numpy()[0,0])),
                   'independent_fp64_state': compare(ours_state, fp64_state[0]),
                   'independent_fp64_output': compare(out32, fp64_out[0,0]),
                   'official_path': 'chunk_cold_multiply_inv_sqrt' if token == 0 else 'recurrent_decode_divide_sqrt',
                   'log_decay_min': float(g.min()), 'log_decay_max': float(g.max())}
        if token:
            reset_out, reset_state, _ = recurrent_step(q, k, values, gates)
            metrics['carried_vs_reset_state_max_abs'] = float(np.max(np.abs(ours_state-reset_state)))
            assert metrics['carried_vs_reset_state_max_abs'] > 0
        checks.append(metrics)
        for label, array in [('query',q), ('key',k), ('value',values), ('expected_state',ours_state), ('expected_core_fp32',out32),
                             ('official_state',native_state.numpy()[0])]:
            save(f'{label}{token}.f32le', np.asarray(array, dtype='<f4'))
        padded_gates = np.zeros((heads,16), dtype='<f4'); padded_gates[:,:2] = gates
        save(f'gates{token}.f32le', padded_gates)
        save(f'expected_output{token}.bf16le', out)
    # Freeze unchanged existing audit thresholds; do not retune from observations.
    passed = all(m['official_output_bf16']['pass'] and all(m[k]['mismatches'] == 0 for k in
        ('official_state_fp32','official_core_fp32','independent_fp64_state','independent_fp64_output')) for m in checks)
    sources = ['src/heteronpu/qwen35_gdn_recurrent_fp32.py','scripts/prepare_gdn_recurrent_fixture.py',
               'src/heteronpu/qwen35_gdn_numpy_reference.py','config/upstream/qwen3_5_0p8b/config.json',
               'config/upstream/qwen3_5_0p8b/layer0_payload_pin.json','config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py']
    report = {'status':'PASS_RECURRENT_REFERENCE_ONLY' if passed else 'FAIL_RECURRENT_REFERENCE',
              'scope':'M1 checkpoint-conditioned recurrent core; software QK normalization/scaling and gates, no complete GDN or Host claim',
              'model_revision':profile['revision'],'framework_revision':profile['transformers_source']['commit'],
              'official_source_sha256':sha(installed.read_bytes()),'source_fixture':str(source),'source_fixture_manifest_sha256':sha((source/'manifest.json').read_bytes()),
              'source_token_ids':source_manifest['token_ids'],'heads':heads,'key_dim':128,'value_dim':128,
              'state_dtype':'FP32','output_dtype':'BF16_RNE','source_sha256':{p:sha((ROOT/p).read_bytes()) for p in sources},
              'all14_weight_sha256':{r['local_name']:r['sha256'] for r in manifest['tensors']},
              'checks':checks,'files':files,'passed':passed,'full_block_supported':False,'rtl_executed':False}
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'checks':checks},indent=2))
    return 0 if passed else 1

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--heads',type=int,default=2)
    a=p.parse_args();assert 1 <= a.heads <= 16
    raise SystemExit(run(a.source,a.output,a.heads))

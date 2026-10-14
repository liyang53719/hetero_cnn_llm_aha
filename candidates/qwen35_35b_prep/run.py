"""Bounded actual35B RMS/QKV/Conv/AB/pack/Prep, with diagnostic Prep roles.

Upstream original numeric gates remain strict. Prep has no newly assigned
native tolerance; raw FP32 role differences are reported without a PASS gate.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np

from ..qwen35_35b_payload.packer import load_payload
from ..qwen35_35b_rms import reference as rms_reference
from ..qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library
from ..qwen2_resident_matrix.dense_block_reduce.profile import ReductionProfile
# The existing shared Add adapter imports its Request lazily on first issue.
# Load that exact source closure before freezing the execution identity.
from ..qwen2_resident_matrix.dense_block_reduce import vector_add_model
from . import driver as p
from . import reference as prep_reference
from ..qwen35_35b_ab import payload as ab_payload, reference as ab_reference
from ..qwen35_35b_ab.run import checked_calibration
from ..qwen35_35b_conv import payload as conv_payload, reference as conv_reference, verify as conv_verify

ROOT = Path(__file__).resolve().parents[2]


def record(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=p.sha(raw))


def checked_record(item):
    p.require(type(item) is dict and set(('path', 'bytes', 'sha256')) <= item.keys(), 'file identity fields')
    raw = Path(item['path']).resolve(strict=True).read_bytes()
    p.require(len(raw) == item['bytes'] and p.sha(raw) == item['sha256'], 'frozen file bytes/hash drift')
    return raw


def source_closure():
    paths = {Path(__file__).resolve()}
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        # Torch's synthetic torch.classes advertises relative '_classes.py';
        # it is not a repository source. Real imported files have absolute paths.
        if name and Path(name).is_absolute():
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py' and not path.is_relative_to(ROOT / 'work'):
                paths.add(path)
    return {str(path.relative_to(ROOT)): p.sha(path.read_bytes()) for path in sorted(paths)}


def compare_window(actual, full_reference, tokens, window):
    p.require(len(full_reference) == tokens * 8192 * 2, 'original full-shape reference required')
    expected = np.frombuffer(full_reference, '<u2').reshape(tokens, 8192)[
        :, window.start:window.start + window.columns].copy().tobytes()
    result = compare_finite_bf16(actual, expected)
    segments = {}
    aa = np.frombuffer(actual, '<u2').reshape(tokens, window.columns)
    bb = np.frombuffer(expected, '<u2').reshape(tokens, window.columns)
    for name, begin, end in (('q', 0, 2048), ('k', 2048, 4096), ('v', 4096, 8192)):
        start, stop = max(begin, window.start), min(end, window.start + window.columns)
        if start < stop:
            a, b = start-window.start, stop-window.start
            segment = compare_finite_bf16(aa[:, a:b].copy().tobytes(), bb[:, a:b].copy().tobytes())
            segment['passed'] = segment['max_abs'] <= .03125 and segment['mean_abs'] <= .005
            segments[name] = segment
    whole_pass = result['max_abs'] <= .03125 and result['mean_abs'] <= .005
    return dict(result, passed=whole_pass and all(s['passed'] for s in segments.values()),
                whole_passed=whole_pass, segments=segments,
                thresholds=dict(max_abs=.03125, mean_abs=.005), original_full_shape_sliced=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--reference-report', type=Path, required=True)
    parser.add_argument('--reference-report-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gate-policy',choices=(p.prep.FINITE_GATE_35B,p.prep.DUAL_EXP_GATE_35B),default=p.prep.FINITE_GATE_35B)
    parser.add_argument('--reduction-policy',choices=(p.prep.ASCENDING,p.prep.CPU_DEFAULT_35B),default=p.prep.ASCENDING)
    parser.add_argument('--tokens', type=int, choices=(16, 128), default=16)
    parser.add_argument('--full-qkv', action='store_true')
    parser.add_argument('--chunk', action='store_true', help='same-invocation full32 cold chunk staging')
    parser.add_argument('--conv-payload', type=Path)
    parser.add_argument('--conv-manifest-sha256')
    parser.add_argument('--wall-seconds', type=int, default=180)
    parser.add_argument('--ab-payload',type=Path,required=True)
    parser.add_argument('--ab-manifest-sha256',required=True)
    parser.add_argument('--ab-reference-report',type=Path,required=True)
    parser.add_argument('--ab-reference-report-sha256',required=True)
    parser.add_argument('--gated-norm',action='store_true')
    parser.add_argument('--z-norm-payload',type=Path)
    parser.add_argument('--z-norm-manifest-sha256')
    parser.add_argument('--z-reference-report',type=Path)
    parser.add_argument('--z-reference-report-sha256')
    parser.add_argument('--output-projection',action='store_true')
    parser.add_argument('--o-payload',type=Path)
    parser.add_argument('--o-manifest-sha256')
    parser.add_argument('--o-reference-report',type=Path)
    parser.add_argument('--o-reference-report-sha256')
    parser.add_argument('--postnorm',action='store_true')
    parser.add_argument('--postnorm-payload',type=Path)
    parser.add_argument('--postnorm-manifest-sha256')
    args = parser.parse_args(argv)
    postnorm_weight=None
    if args.postnorm:
        from ..qwen35_35b_postnorm import payload as post_payload, reference as post_reference
        from ..qwen35_35b_rms import formula as post_formula
        p.require(args.output_projection and args.postnorm_payload is not None, 'postnorm requires actual O and payload')
        _,post_values=post_payload.load(args.postnorm_payload,args.postnorm_manifest_sha256)
        postnorm_weight=post_values['layers.0.post_attention_layernorm.weight']
    if args.chunk:
        from . import chunk_reference
    z_weight=gated_weight=z_profile=z_ref=None
    if args.gated_norm:
        from ..qwen35_35b_gated_norm import payload as z_payload, z_reference, norm_reference
        p.require(args.chunk and args.z_norm_payload is not None and args.z_reference_report is not None,
                  'norm requires actual chunk and independent full N4096 reference')
        z_record=record(args.z_reference_report)
        p.require(z_record['sha256']==args.z_reference_report_sha256,'N4096 independent report pin')
        z_ref=json.loads(checked_record(z_record))
        p.require(z_ref['status']=='COMPLETE_Z_N4096_DIAGNOSTICS_NO_ADMISSION' and
                  (z_ref['m'],z_ref['n'],z_ref['k'])==(args.tokens,4096,2048) and z_ref['sources_unchanged'],
                  'separate complete N4096 diagnostics')
        for path,digest in z_ref['source_frozen'].items():
            p.require(p.sha(Path(path).read_bytes())==digest,'N4096 reference source drift')
        checked_record(z_ref['input']);checked_record(z_ref['official'])
        checked_record(z_ref['results']['pair_hi_first_two_k1024']['output'])
        _,z_values=z_payload.load(args.z_norm_payload,args.z_norm_manifest_sha256)
        z_weight=z_values['layers.0.linear_attn.in_proj_z.weight']
        gated_weight=z_values['layers.0.linear_attn.norm.weight']
        p.require(p.sha(z_weight)==z_ref['weight']['sha256'],'same complete N4096 weight')
        z_c=Path(z_reference.__file__).with_name('reference.c')
        z_profile=ReductionProfile('diagnostic_35b_z_n4096_pair_high',((0,1024),(1024,2048)),True,p.sha(z_c.read_bytes()))
        norm_reference.source_identity()
    else:
        p.require(all(x is None for x in (args.z_norm_payload,args.z_norm_manifest_sha256,args.z_reference_report,args.z_reference_report_sha256)),
                  'Z/norm arguments require explicit stage')
    o_weight=o_ref=o_profile=None
    if args.output_projection:
        from ..qwen35_35b_output import payload as o_payload, o_reference
        from ..qwen35_35b_output.calibration import input_record as o_input_record
        p.require(args.gated_norm and args.o_payload is not None and args.o_reference_report is not None,
                  'O requires same-invocation norm and separate complete K4096/N2048 reference')
        o_record=record(args.o_reference_report)
        p.require(o_record['sha256']==args.o_reference_report_sha256,'O reference report pin')
        o_ref=json.loads(checked_record(o_record))
        p.require(o_ref['status']=='COMPLETE_O_N2048_K4096_DIAGNOSTICS_NO_ADMISSION' and
                  (o_ref['m'],o_ref['n'],o_ref['k'])==(args.tokens,2048,4096) and o_ref['sources_unchanged'],
                  'independent complete O geometry/reference')
        for path,digest in o_ref['source_frozen'].items():
            p.require(p.sha(Path(path).read_bytes())==digest,'O reference source drift')
        checked_record(o_input_record(o_ref));checked_record(o_ref['official'])
        checked_record(o_ref['results']['pair_high_four_independent_k1024_leftfold']['output'])
        _,o_values=o_payload.load(args.o_payload,args.o_manifest_sha256)
        o_weight=o_values['layers.0.linear_attn.out_proj.weight']
        p.require(p.sha(o_weight)==o_ref['weight']['sha256'],'same complete O weight')
        o_c=Path(o_reference.__file__).with_name('reference.c')
        o_profile=p.output_stage.FourProfile('official_shape_diagnostic_four_k1024_leftfold',p.sha(o_c.read_bytes()))
    else:
        p.require(all(x is None for x in (args.o_payload,args.o_manifest_sha256,args.o_reference_report,args.o_reference_report_sha256)),
                  'O arguments require explicit stage')
    p.require(not args.output.exists() and not args.output.is_symlink() and
              args.output.resolve().is_relative_to(ROOT / 'work'), 'fresh ignored work output required')
    p.require(30 <= args.wall_seconds <= 1800, 'bounded explicit software budget 30..1800 seconds')
    p.require(args.full_qkv and args.conv_payload is not None, 'complete QKV/Conv required')
    ab_ref=checked_calibration(args.ab_reference_report,args.ab_reference_report_sha256,args.tokens)
    _,ab_values=ab_payload.load(args.ab_payload,args.ab_manifest_sha256)
    ab_weights={n:ab_values['layers.0.linear_attn.in_proj_'+n+'.weight'] for n in ('a','b')}
    p.require(all(p.sha(ab_weights[n])==ab_ref['results'][n]['weight_sha256'] for n in ab_weights),'same N32 calibration weights')
    ab_c=Path(ab_reference.__file__).with_name('reference.c')
    ab_profiles={n:ReductionProfile('independent_35b_'+n+'_n32',((0,1024),(1024,2048)),True,p.sha(ab_c.read_bytes())) for n in ab_weights}
    reference_record = record(args.reference_report)
    p.require(reference_record['sha256'] == args.reference_report_sha256, 'independently retained reference digest')
    reference = json.loads(checked_record(reference_record))
    p.require((reference['m'], reference['k'], reference['n']) == (args.tokens, 2048, 8192), 'full native geometry')
    p.require(reference['status'] == 'PASS_PAIR_PROFILE_ORIGINAL_GATES', 'reference numerical status')
    for path,digest in reference['source_frozen'].items():
        p.require(p.sha(Path(path).read_bytes())==digest,'QKV original calibration source drift')
    checked_record(reference['input']);checked_record(reference['weight'])
    manifest, payload = load_payload(ROOT, args.payload, include_qkv=True,
                                     manifest_sha256=args.manifest_sha256)
    hidden = payload['embed_tokens.rows_0_255'][:args.tokens * 4096]
    norm_weight = payload['layers.0.input_layernorm.weight']
    qkv = payload['layers.0.linear_attn.in_proj_qkv.weight']
    p.require((args.conv_payload is None) == (args.conv_manifest_sha256 is None), 'Conv payload and digest together')
    conv_weight = None
    if args.conv_payload is not None:
        p.require(args.full_qkv, 'Conv requires complete QKV')
        _, conv_values = conv_payload.load(args.conv_payload.resolve(), args.conv_manifest_sha256)
        conv_weight = conv_values[conv_payload.LOCAL]
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        rms_reference.runtime_identity()
        if args.chunk:
            prep_reference._runtime(torch)
            chunk_reference._runtime(torch)
            chunk_reference.source_identity()
    p.require(p.sha(qkv) == reference['weight']['sha256'] and
              len(qkv) == reference['weight']['bytes'], 'same native NK weight identity')
    rms_identity = rms_reference.source_identity()
    p.require(reference['official_source']['sha256'] == rms_identity['source_sha256'], 'official source identity')
    pair_source = ROOT / 'candidates/qwen35_35b_projection_reference/reference.c'
    p.require(reference['source_frozen'].get(str(pair_source)) == p.sha(pair_source.read_bytes()),
              'same independent fixed arithmetic source')
    profile = ReductionProfile('diagnostic_35b_onednn371_avx512bf16_two_k1024_pair_high',
                               ((0, 1024), (1024, 2048)), True, p.sha(pair_source.read_bytes()))
    windows = ((p.ColumnWindow(0, 8192),) if args.full_qkv else
               tuple(p.ColumnWindow(i, 160) for i in (0, 2048, 4096)))
    library = p.dense.library_from_environment(ROOT)
    lib = configure_library(ctypes.CDLL(str(library)))
    p.require(lib.td_reset() == 0, 'fresh shared Matrix')
    matrix = p.dense.MatrixService(lib)
    vector = p.Vector16(Path(os.environ['GDN_VECTOR16_LIBRARY']), exception_policy=p.IEEE_POLICY)
    compile_receipt = Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT'])
    native_paths = [pair_source, library, compile_receipt, vector.library,
                    vector.library.with_suffix('.json'),
                    ROOT / 'candidates/qwen35_gdn_prefill/chunk/vector16.cpp']
    native_paths += [ab_c]
    if args.gated_norm:native_paths += [z_c,ROOT/norm_reference.ACTIVATIONS]
    if args.output_projection:native_paths += [o_c]
    native_paths += [ROOT / name for name in json.loads(compile_receipt.read_bytes())['sources_before']]
    conv_preact = np.zeros((args.tokens,8192), dtype='<u2') if conv_weight is not None else None
    conv_seen = set()
    def conv_observe(tag, token, channel, bits):
        p.require((token,channel) not in conv_seen, 'duplicate Conv preactivation observation')
        conv_seen.add((token,channel)); conv_preact[token,channel] = bits
    postnorm_nodes={}
    def postnorm_observe(name,token,words):
        node=postnorm_nodes.setdefault(name,{})
        p.require(token not in node, "duplicate postnorm actual node")
        node[token]=np.asarray(words,dtype="<u4").tobytes()
    args.output.mkdir(parents=True)
    started = time.monotonic()
    report = dict(status='RUNNING', gate_policy=args.gate_policy, reduction_policy=args.reduction_policy, chunk_requested=args.chunk, tokens=args.tokens, windows=[vars(w) for w in windows],
                  full_qkv=args.full_qkv, conv_requested=conv_weight is not None, full_block=False, rtl_executed=False,
                  conv_manifest_sha256=args.conv_manifest_sha256,
                  reference=reference_record, manifest_sha256=args.manifest_sha256,
                  input_identity=dict(hidden_sha256=p.sha(hidden), norm_weight_sha256=p.sha(norm_weight),
                                      qkv_nk_sha256=p.sha(qkv)),
                  matrix_library=record(library), vector_library=record(os.environ['GDN_VECTOR16_LIBRARY']),
                  matrix_compile_receipt=record(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT']),
                  source_sha256=source_closure(), arithmetic_source_sha256={
                      str(pair_source.relative_to(ROOT)): p.sha(pair_source.read_bytes())},
                  native_artifact_records=[record(path) for path in native_paths],
                  ab_reference=record(args.ab_reference_report),ab_manifest_sha256=args.ab_manifest_sha256,
                  prep_native_acceptance=False,gated_norm_requested=args.gated_norm,norm_native_acceptance=False,
                  postnorm_requested=args.postnorm,postnorm_manifest_sha256=args.postnorm_manifest_sha256,
                  output_projection_requested=args.output_projection,o_native_acceptance=False,
                  o_reference=record(args.o_reference_report) if args.output_projection else None,
                  o_manifest_sha256=args.o_manifest_sha256,
                  z_reference=record(args.z_reference_report) if args.gated_norm else None,
                  z_norm_manifest_sha256=args.z_norm_manifest_sha256,observations=[], comparisons={})

    def save():
        report['host_seconds'] = time.monotonic() - started
        (args.output / 'summary.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    def observe(stage, details, raw):
        path = args.output / (stage + ('.actual.fp32le' if stage in ('prep','chunk_state_staging','chunk_scratch_staging') else '.actual.bf16le'))
        path.write_bytes(raw)
        report['observations'].append(dict(stage=stage, output=record(path), owner=details))
        save()
        print(json.dumps(dict(stage=stage, host_seconds=time.monotonic()-started,
                              output_sha256=p.sha(raw))), flush=True)

    def chunk_progress(item):
        report['chunk_progress']=item
        save()
        print(json.dumps(dict(stage='chunk_progress',**item)),flush=True)

    def timeout(*_):
        raise TimeoutError('bounded typed prefix software budget')

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(args.wall_seconds)
    save()
    try:
        execution, _ = p.execute_prep_prefix(hidden, norm_weight, qkv, tokens=args.tokens, windows=windows,
            profile=profile, matrix=matrix, vector=vector, deadline=started+args.wall_seconds, observe=observe,
            conv_weights=conv_weight, conv_observe=conv_observe,ab_weights=ab_weights,ab_profiles=ab_profiles,
            a_log=ab_values['layers.0.linear_attn.A_log'],dt_bias=ab_values['layers.0.linear_attn.dt_bias'],reduction_policy=args.reduction_policy,gate_policy=args.gate_policy,run_chunk=args.chunk,chunk_progress=chunk_progress,on_chunk_interrupt=lambda:signal.alarm(0),
            z_weight=z_weight,z_profile=z_profile,gated_weight=gated_weight,o_weight=o_weight,o_profile=o_profile,postnorm_weight=postnorm_weight,
            postnorm_observe=postnorm_observe if args.postnorm else None)
        report['execution'] = execution
        p.require(execution['status'] == ('PASS_TYPED_POSTNORM_PREFIX_EXECUTION_ONLY' if args.postnorm else 'PASS_TYPED_OUTPUT_PREFIX_EXECUTION_ONLY' if args.output_projection else 'PASS_TYPED_GATED_NORM_PREFIX_EXECUTION_ONLY' if args.gated_norm else 'PASS_TYPED_CHUNK_STAGING_EXECUTION_ONLY' if args.chunk else 'PASS_TYPED_PREP_PREFIX_EXECUTION_ONLY'), 'actual typed prefix failed')
        p.require(execution['actual_rms_output_sha256'] == reference['input']['sha256'], 'actual RMS differs from reference input')
        native = checked_record(reference['official_output'])
        fixed = checked_record(reference['results']['pair_hi_first_two_k1024']['output'])
        expected_stages = ['input_norm'] + ['qkv_columns_' + str(w.start) for w in windows]
        if conv_weight is not None:
            expected_stages += ['conv4_silu', 'conv_history_staging']
        expected_stages += ['a','b','ab_pack','prep']
        if args.gated_norm:expected_stages += ['z']
        if args.chunk:expected_stages += ['chunk','chunk_state_staging','chunk_scratch_staging']
        if args.gated_norm:expected_stages += ['gated_norm']
        if args.output_projection:expected_stages += ['output_projection']
        if args.postnorm:expected_stages += ['attention_residual','post_attention_norm']
        p.require([o['stage'] for o in report['observations']] == expected_stages, 'exact observation inventory')
        p.require(len(execution['terminals']) == len(windows)+1+(conv_weight is not None)+4+int(args.chunk)+2*int(args.gated_norm)+int(args.output_projection)+2*int(args.postnorm), 'exact owner terminal count')
        for window, observation in zip(windows, report['observations'][1:1+len(windows)], strict=True):
            actual = checked_record(observation['output'])
            numeric = dict(native=compare_window(actual, native, args.tokens, window),
                           fixed=compare_window(actual, fixed, args.tokens, window))
            report['comparisons'][observation['stage']] = numeric
            p.require(numeric['fixed']['bit_mismatches'] == 0, 'actual Matrix/Vector differs from independent fixed recipe')
            p.require(numeric['native']['passed'], 'original native threshold failed')
        if conv_weight is not None:
            p.require(len(conv_seen) == args.tokens*8192, 'complete actual Conv preactivation coverage')
            qkv_actual = checked_record(report['observations'][1]['output'])
            post_actual = checked_record(report['observations'][2]['output'])
            history_actual = checked_record(report['observations'][3]['output'])
            pre_actual = conv_preact.tobytes()
            pre_path = args.output / 'conv_preact.actual.bf16le'; pre_path.write_bytes(pre_actual)
            report['conv_preact_record'] = record(pre_path)
            fixed_conv, fixed_id = conv_reference.fixed_conv(qkv_actual, conv_weight, args.tokens)
            native_conv, native_id = conv_reference.native_conv(qkv_actual, conv_weight, args.tokens)
            # Also check end-to-end inherited QKV rounding against the frozen official producer.
            end_conv, end_id = conv_reference.native_conv(native, conv_weight, args.tokens)
            actual_conv = dict(conv=pre_actual,silu=post_actual,history=history_actual)
            strict = conv_verify.compare(actual_conv,fixed_conv,native_conv,end_conv)
            report['conv_strict_gates'] = strict
            report['conv_comparisons'] = strict['comparisons']
            report['conv_reference_records'] = conv_verify.save_raw(args.output/'conv_references',
                dict(fixed=fixed_conv,same_input=native_conv,end_to_end=end_conv))
            p.require(strict['passed'], 'original strict Conv gates failed')
            report['conv_references'] = dict(fixed=fixed_id,native=native_id,end_to_end=end_id)
            p.require(execution['conv_history_staging']['published'] is False and
                      execution['conv_history_staging']['generation_advanced'] is False, 'no local block commit')
        observations={o['stage']:o for o in report['observations']}
        p.require(execution['actual_rms_output_sha256']==ab_ref['input']['sha256'],'same N32 RMS source')
        for name in ('a','b'):
            actual=checked_record(observations[name]['output'])
            fixed_ab=checked_record(ab_ref['results'][name]['recipes']['pair_hi_first_two_k1024']['output'])
            official_ab=checked_record(ab_ref['results'][name]['official'])
            p.require(actual==fixed_ab,'actual A/B independent fixed gate')
            report['comparisons'][name]=ab_reference.gate(actual,official_ab)
            p.require(report['comparisons'][name]['passed'],'original A/B gate')
        ab_actual=checked_record(observations['ab_pack']['output'])
        ab_a=checked_record(observations['a']['output']);ab_b=checked_record(observations['b']['output'])
        p.require(ab_actual==b''.join(raw[t*64:(t+1)*64] for t in range(args.tokens) for raw in (ab_a,ab_b)),'ACKed AB row pack bytes')
        prep_actual=checked_record(observations['prep']['output'])
        prep_expected,prep_identity=prep_reference.native_prep(post_actual,ab_actual,ab_values['layers.0.linear_attn.A_log'],ab_values['layers.0.linear_attn.dt_bias'],args.tokens)
        prep_path=args.output/'prep.same_input.reference.fp32le';prep_path.write_bytes(prep_expected)
        report['prep_reference']=record(prep_path)
        report['prep_diagnostics']=prep_reference.diagnose(prep_actual,prep_expected,args.tokens,identity=prep_identity)
        report['prep_native_acceptance']=False
        if args.chunk:
            from . import chunk_reference
            expected, identity=chunk_reference.native_chunk(prep_actual,args.tokens)
            report['chunk_reference_records']={}
            for name,raw in expected.items():
                path=args.output/('chunk.'+name+'.reference.'+('bf16le' if name=='output' else 'fp32le'))
                path.write_bytes(raw);report['chunk_reference_records'][name]=record(path)
            report['chunk_reference_identity']=identity
            report['chunk_diagnostics']=chunk_reference.diagnose(
                {'output':checked_record(observations['chunk']['output']),'state':checked_record(observations['chunk_state_staging']['output'])},expected)
        if args.gated_norm:
            p.require(execution['actual_rms_output_sha256']==z_ref['input']['sha256'],'same N4096 actual RMS producer')
            z_actual=checked_record(observations['z']['output'])
            z_fixed=checked_record(z_ref['results']['pair_hi_first_two_k1024']['output'])
            p.require(z_actual==z_fixed,'Z Matrix fixed arithmetic identity')
            report['z_diagnostics']=z_reference.diagnostics(z_actual,checked_record(z_ref['official']),args.tokens)
            norm_actual=checked_record(observations['gated_norm']['output'])
            norm_expected,norm_identity,intermediates=norm_reference.native_norm(
                checked_record(observations['chunk']['output']),z_actual,gated_weight,args.tokens)
            norm_path=args.output/'gated_norm.same_input.reference.bf16le';norm_path.write_bytes(norm_expected)
            report['gated_norm_reference']=record(norm_path)
            report['gated_norm_reference_identity']=norm_identity
            report['gated_norm_diagnostics']=dict(compare_finite_bf16(norm_actual,norm_expected),
                passed=None,thresholds=None,native_acceptance=False)
            report['gated_norm_intermediates']={}
            for name,item in intermediates.items():
                item=dict(item);raw=item.pop('raw')
                path=args.output/('gated_norm.reference.'+name+'.raw');path.write_bytes(raw)
                report['gated_norm_intermediates'][name]=dict(item,record=record(path))
        if args.output_projection:
            o_actual=checked_record(observations['output_projection']['output'])
            norm_input=checked_record(observations['gated_norm']['output'])
            p.require(p.sha(norm_input)==o_input_record(o_ref)['sha256'],'O actual norm producer differs from calibration input')
            p.require(o_actual==checked_record(o_ref['results']['pair_high_four_independent_k1024_leftfold']['output']),
                      'actual four-part O differs from independent complete FP32 left-fold recipe')
            report['o_fixed_recipe_bitexact']=True
            report['o_diagnostics']=o_reference.diagnostics(o_actual,checked_record(o_ref['official']),args.tokens)
        if args.postnorm:
            actual_residual=checked_record(observations['attention_residual']['output'])
            actual_postnorm=checked_record(observations['post_attention_norm']['output'])
            native_post=post_reference.component(hidden,o_actual,postnorm_weight,args.tokens)
            # Formula is an independent diagnostic only. No reference bytes
            # enter the typed producer memory map or its arithmetic.
            fixed_post=post_formula.formula(actual_residual,postnorm_weight,args.tokens)
            p.require(actual_postnorm==fixed_post['output'],'postnorm differs from independent FP32 recipe')
            report['postnorm_fixed_recipe_bitexact']=True
            report['postnorm_source']=native_post['source']
            report['postnorm_dispatch']=native_post['dispatch']
            report['postnorm_runtime']=native_post['runtime']
            report['residual_diagnostics']=dict(compare_finite_bf16(actual_residual,native_post['residual']),
                passed=None,thresholds=None,native_acceptance=False)
            report['postnorm_diagnostics']=dict(compare_finite_bf16(actual_postnorm,native_post['output']),
                passed=None,thresholds=None,native_acceptance=False)
            report['postnorm_reference_records']={}
            for name,raw in dict(residual=native_post['residual'],output=native_post['output'],
                                 fixed_output=fixed_post['output'],**native_post['trace_raw']).items():
                path=args.output/('postnorm.reference.'+name+'.raw');path.write_bytes(raw)
                report['postnorm_reference_records'][name]=record(path)
            report['postnorm_actual_nodes']={}
            for name,rows in postnorm_nodes.items():
                p.require(set(rows)==set(range(args.tokens)),'complete actual postnorm node rows')
                raw=b''.join(rows[i] for i in range(args.tokens))
                path=args.output/('postnorm.actual.'+name+'.fp32le');path.write_bytes(raw)
                item=dict(actual=record(path),actual_observed=True)
                if name in native_post['trace_raw']:
                    a=np.frombuffer(raw,'<f4');b=np.frombuffer(native_post['trace_raw'][name],'<f4')
                    if name=='gamma':b=np.tile(b,args.tokens)
                    p.require(a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all(),'postnorm diagnostic shape/finite')
                    delta=np.abs(a.astype('float64')-b.astype('float64'))
                    item.update(bit_mismatches=int(np.count_nonzero(a.view('<u4')!=b.view('<u4'))),
                        max_abs=float(delta.max()),mean_abs=float(delta.mean()),passed=None,thresholds=None)
                elif name=='sum':item['reference_role']='auxiliary sum only; original op is mean'
                elif name=='root':item['reference_role']='candidate sqrt node only; official op is rsqrt'
                report['postnorm_actual_nodes'][name]=item
        report['source_sha256_after'] = source_closure()
        report['sources_unchanged'] = report['source_sha256'] == report['source_sha256_after']
        p.require(report['sources_unchanged'], 'execution source drift')
        for item in report['native_artifact_records']:
            checked_record(item)
        report['native_artifacts_unchanged'] = True
        report['status'] = 'UPSTREAM_ORIGINAL_GATES_PASS_POSTNORM_DIAGNOSTICS_ONLY' if args.postnorm else 'UPSTREAM_ORIGINAL_GATES_PASS_PREP_CHUNK_NORM_O_DIAGNOSTICS_ONLY' if args.output_projection else 'UPSTREAM_ORIGINAL_GATES_PASS_PREP_CHUNK_NORM_DIAGNOSTICS_ONLY' if args.gated_norm else 'UPSTREAM_ORIGINAL_GATES_PASS_PREP_CHUNK_DIAGNOSTICS_ONLY' if args.chunk else 'UPSTREAM_ORIGINAL_GATES_PASS_PREP_DIAGNOSTICS_ONLY'
    except BaseException as error:
        report['source_sha256_after']=source_closure()
        report['sources_unchanged']=report['source_sha256']==report['source_sha256_after']
        report.update(status='FAILED', error=dict(type=type(error).__name__, message=str(error)))
        if isinstance(error, p.PrefixExecutionError):
            report['execution'] = error.execution_report
            report['interrupted_owner'] = error.snapshot
            partial = args.output / 'interrupted_owner.partial.bf16le'
            partial.write_bytes(error.partial_output)
            report['interrupted_output'] = record(partial)
            if error.partial_history is not None:
                history_path = args.output / 'interrupted_owner.history.bf16le'
                history_path.write_bytes(error.partial_history)
                report['interrupted_history'] = record(history_path)
        if isinstance(error,p.chunk_stage.ChunkInterrupted):
            report['execution']=error.execution_report
            report['interrupted_owner']=error.snapshot
            report['interrupted_chunk_records']={}
            for name,raw in error.raw.items():
                path=args.output/('interrupted_chunk.'+name+'.raw');path.write_bytes(raw)
                report['interrupted_chunk_records'][name]=record(path)
        save()
        raise
    finally:
        signal.alarm(0)
    save()


if __name__ == '__main__':
    main()

"""Two adjacent source rows, real-cache expected values only; never DUT memory.

Uses the production parameterized projection and Norm/RoPE factories.
No saved reference receipt can substitute for their live capture authorities.
"""
from pathlib import Path
import json
import subprocess
import tempfile
import numpy as np

import host_bf16_qkv_reference as projection
import host_bf16_qk_rope_reference as norm_rope
from heteronpu import qwen35_gqa_fixed_reference as gqa
from heteronpu.matrix_norm_rope_candidate import fma_rne

require, digest = projection.require, projection.digest
WINDOWS = (('cold', 0, 1), ('cold', 1, 1))


def bf16_bytes(values):
    values = np.asarray(values, dtype='<f4')
    gqa.require_bf16(values, 'expected terminal')
    return (values.view('<u4') >> 16).astype('<u2').tobytes()


def decoded(raw, shape):
    require(type(raw) is bytes and len(raw) == 2 * int(np.prod(shape)), 'BF16 byte geometry')
    return (np.frombuffer(raw, dtype='<u2').astype('<u4') << 16).view('<f4').reshape(shape)


def matrix_fma_witness(query, cache, trace, output):
    """Every increasing-K QK/PV FMA with recursively verified accumulators.

    The existing independent C --fma mode checks all triplets and flags. No
    synthetic padding changes accumulation order, and masked +0 PV terms stay.
    """
    inputs, expected = [], []
    def dot(left, right):
        acc = 0
        for a, b in zip(left.view('<u4'), right.view('<u4'), strict=True):
            inputs.append((int(a), int(b), acc))
            acc, flags = fma_rne(int(a), int(b), acc)
            expected.append((acc, flags))
        return acc
    live = cache[:, :trace['qk_fp32'].shape[-1]]
    for row in range(query.shape[0]):
        for head in range(8):
            first = (head // 4) * 256
            for key in range(live.shape[1]):
                word = dot(query[row, head], live[0, key, first:first + 256])
                require(word == int(trace['qk_fp32'].view('<u4')[row, head, key]), 'QK witness final')
            probability = trace['probabilities_bf16'][row, head]
            for col in range(256):
                word = dot(probability, live[1, :, first + col])
                require(word == int(trace['pv_fp32'].view('<u4')[row, head, col]), 'PV witness final')
                require(gqa._bf16(word) == int(output.reshape(-1, 8, 256).view('<u4')[row, head, col]),
                        'PV terminal BF16 witness')
    return np.asarray(inputs, dtype='<u4'), np.asarray(expected, dtype='<u4')


def crosscheck_fma(executable, directory, query, cache, trace, output):
    inputs, expected = matrix_fma_witness(query, cache, trace, output)
    source, target = directory / 'fma_input.bin', directory / 'fma_output.bin'
    inputs.tofile(source)
    subprocess.run([str(executable), '--fma', str(source), str(target)], check=True,
                   capture_output=True, timeout=30)
    actual = np.fromfile(target, dtype='<u4')
    require(actual.size == expected.size and np.array_equal(actual.reshape(expected.shape), expected),
            'independent integer/C attention FMA or flags mismatch')
    return dict(status='PASS_INTEGER_C_EVERY_QK_PV_FMA', fmas=len(inputs),
                bit_mismatches=0, flag_mismatches=0,
                input_sha256=digest(inputs.tobytes()), output_sha256=digest(actual.tobytes()))


def prepare_attention_core_expectations(session, projection_session, attention_session, *, variant='baseline'):
    """Return raw input bytes, audit-only expectations and live-source proof.

    The second hardware launch is carried from the first real cache fence,
    while both upstream input rows originate in the official cold_m128
    capture. This is not an executed upstream GDN decode or complete block.
    """
    require(type(projection_session) is projection.FreshProjectionReferenceSession and
            type(attention_session) is norm_rope.FreshAttentionReferenceSession, 'live factory authorities')
    projected_receipt = projection_session.verify(session=session)
    attention_receipt = attention_session.verify(session=session, projection_reference_session=projection_session)
    def core_sources():
        paths = (Path(__file__).resolve(), Path(gqa.__file__).resolve())
        require(all(p.is_file() and not p.is_symlink() and p.is_relative_to(projection.ROOT) for p in paths),
                'core reference source identity/path')
        return {str(p.relative_to(projection.ROOT)): projection.file_digest(p) for p in paths}
    initial_core_sources = core_sources()
    require(projected_receipt['requested_windows'] == attention_receipt['requested_windows'] == [list(w) for w in WINDOWS],
            'expected source cold token0 then cold token1')
    require(variant in projected_receipt['variants'] and variant in attention_receipt['variants'], 'uncomputed variant')
    official = session.verify()
    _, weights, _ = projection._load_weights(session)
    activation, _ = projection._load_window(session, official, variant, 'cold', 0)
    inputs = {'activation.bf16le': activation.tobytes()}
    inputs.update({'weight_' + r + '.bf16le': weights[r].tobytes() for r in 'qkv'})
    gamma = norm_rope._parameters(session)
    inputs.update({name + '.bf16le': raw for name, raw in gamma.items()})
    # The entire shared trig allocation is an authenticated parameter, including
    # its inactive suffix; no zeros are invented to impersonate official data.
    native_path = session.directory / variant / 'native/all_bf16_producers.npz'
    norm_rope.capture._verify_file(native_path, official['corpora'][variant]['fresh_audit_arrays'])
    audit_path = session.directory / variant / 'native/result.json'
    norm_rope.capture._verify_file(audit_path, official['corpora'][variant]['fresh_audit_report'])
    audit = json.loads(audit_path.read_text())
    context_key = 'self_attn|aten.matmul.default|1'
    context_indices = [i for i,row in enumerate(audit['producer_sequence']) if row['key'] == context_key]
    require(len(context_indices) == 1 and audit['producer_sequence'][context_indices[0]]['storage_dtype'] == 'bfloat16',
            'native context producer identity/dtype')
    context_rows = [r for r in audit['comparisons'] if r['case'] == 'cold_m128' and r['producer'] == context_key]
    require(len(context_rows) == 1, 'native context comparison inventory')
    original_context_comparison = context_rows[0]
    require(original_context_comparison['max_abs_limit'] == audit['thresholds']['operator']['max_abs'] and
            original_context_comparison['mean_abs_limit'] == audit['thresholds']['operator']['mean_abs'], 'native context threshold drift')
    trig_rows = []
    with np.load(native_path, allow_pickle=False) as native:
        native_context_words = norm_rope.capture._bf16_words(
            native[f'cold_m128_native_producer_{context_indices[0]:02d}'], (1,8,128,256), 'native PV context')[0,:,:2,:].copy()
        for phase in ('cold', 'carried'):
            prefix = phase + '_m128_'
            cos = norm_rope.capture._bf16_words(native[prefix + 'native_cos'], (1,128,64), 'cos')[0]
            sin = norm_rope.capture._bf16_words(native[prefix + 'native_sin'], (1,128,64), 'sin')[0]
            require(np.array_equal(cos[:,:32], cos[:,32:]) and np.array_equal(sin[:,:32], sin[:,32:]), 'trig pair layout')
            trig_rows.append(np.concatenate((cos[:,:32], sin[:,:32]), axis=1))
    inputs['trig.bf16le'] = (np.concatenate(trig_rows) >> 16).astype('<u2').tobytes()
    expected, proofs = {}, {}
    cache = np.zeros((2,256,512), dtype='<f4')  # software expected state only
    executable = Path(projected_receipt['tools']['executable']['path'])
    for token, label in enumerate(('cold0', 'carried1')):
        p, projection_proof = projection_session.select(activation, weights, session=session,
            variant=variant, phase='cold', token_base=token, token_count=1)
        n, norm_proof = attention_session.select(activation, weights, session=session,
            projection_reference_session=projection_session, variant=variant, phase='cold', token_base=token, token_count=1)
        require(n['trig'] == inputs['trig.bf16le'][token*128:(token+1)*128], 'selected trig differs')
        cache[0,token] = decoded(n['rope_k'], (512,))
        cache[1,token] = decoded(p['v'], (512,))
        query = decoded(n['rope_q'], (1,8,256))
        context, trace = gqa.causal_gqa(query, cache, query_start=token, cache_length=token+1, return_trace=True)
        with tempfile.TemporaryDirectory(prefix='.gqa_fma_', dir=projection_session.directory.parent) as temporary:
            checked = crosscheck_fma(executable, Path(temporary), query, cache, trace, context)
        expected[label] = {r + '.bf16le': p[r] for r in 'qkv'}
        expected[label].update({name + '.bf16le': n[name] for name in ('norm_q','gate','norm_k','rope_q','rope_k')})
        expected[label].update({'cache_k.bf16le': n['rope_k'], 'cache_v.bf16le': p['v'], 'context.bf16le': bf16_bytes(context)})
        native_diagnostic = norm_rope._native_diagnostic(context.reshape(8,256).view('<u4'),
            native_context_words[:,token], original_context_comparison)
        native_diagnostic.update(scope='two_selected_adjacent_rows_not_full128',
            predecessor_bit_identity_claimed=False, original_native_report_sha256=projection.file_digest(audit_path))
        proofs[label] = dict(source_phase='cold', source_token=token, absolute_position=token,
            host_cold=token == 0, host_expected_length=token, host_expected_generation=token,
            projection_reference=projection_proof, norm_rope_reference=norm_proof, matrix_reference=checked,
            projection_native_diagnostics=projected_receipt['windows'][variant + '/cold' + str(token)]['native'],
            context_policy=gqa.POLICY, numerical_rtl_executed=False,
            native_context_diagnostic=native_diagnostic,
            native_context_gate='UNASSIGNED_DIAGNOSTIC_ONLY_NOT_NATIVE_ACCEPTANCE')
    # Verify unchanged authority/tool/source bytes again after all arithmetic.
    require(projection_session.verify(session=session) == projected_receipt and
            attention_session.verify(session=session, projection_reference_session=projection_session) == attention_receipt,
            'reference authority changed during core expectations')
    require(core_sources() == initial_core_sources, 'core reference source changed during expectations')
    receipt = dict(status='PREPARED_ADJACENT_ATTENTION_CORE_EXPECTED_ONLY', variant=variant,
        official_manifest_sha256=session.manifest_sha256, input_injection=False,
        expected_only=True, intermediate_preload_allowed=False, actual_cache_execution=False,
        full_block_supported=False, upstream_gdn_decode_executed=False, full128_executed=False,
        native_full_block_failures=attention_receipt['native_full_block_failures'],
        projection_native_operator_gate_pass=projected_receipt['native_operator_gate_pass'],
        projection_native_thresholds=projected_receipt['native_thresholds'],
        original_operator_gate_pass=attention_receipt['original_operator_gate_pass'],
        original_operator_criteria=attention_receipt['original_native_criteria'],
        source_sha256=projected_receipt['source_sha256'] | attention_receipt['source_sha256'] | initial_core_sources,
        inputs={n:dict(bytes=len(raw),sha256=digest(raw)) for n,raw in inputs.items()},
        expected={label:{n:dict(bytes=len(raw),sha256=digest(raw)) for n,raw in files.items()} for label,files in expected.items()},
        cases=proofs)
    return inputs, expected, receipt

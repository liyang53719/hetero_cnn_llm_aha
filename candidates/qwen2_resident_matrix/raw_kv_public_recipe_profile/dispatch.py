"""Preparation-only prerequisite for the public paired-recipe profile.

This module validates already verified, bounded metadata. It never loads tensor
arrays or native libraries, selects an ISA, downloads inputs, or starts a run.
The caller must supply an independently captured current-run context, including
canonical report/diagnostic hashes; deriving that context from untrusted input
does not establish provenance or freshness. The returned evidence is only a
numerical prerequisite, never Public-chain admission or backend-order proof.
"""

from ..raw_kv_native_qk_run import phase


PROFILE = 'qwen2-public-pv16-native-pair-avx512bf16-v1'
IMPLEMENTATION = 'brg_matmul:avx512_core_bf16'
ISA = 'avx512_core_bf16'
MAX_SUMMARY_BYTES = 8192

# These identities must match across both fresh shapes and the trusted context.
SHARED_REPORT_HASHES = (
    'source_manifest_sha256', 'contract_sha256', 'original_module_sha256',
    'generated_module_sha256', 'library_sha256', 'library_receipt_sha256',
    'recipe_pins_sha256', 'qkv_library_sha256', 'qkv_library_receipt_sha256',
    'qkv_recipe_pins_sha256', 'payload_manifest_sha256',
)
SHARED_CONTEXT_HASHES = SHARED_REPORT_HASHES + ('payload_tensor_map_sha256',)
CASE_CONTEXT_HASHES = (
    'result_sha256', 'source_manifest_sha256', 'report_sha256',
    'diagnostics_sha256',
)
REPORT_DIAGNOSTIC_IDENTITIES = (
    'tokens', 'result_sha256', 'source_manifest_sha256', 'contract_sha256',
    'generated_module_sha256', 'library_sha256', 'qkv_library_sha256',
    'payload_manifest_sha256',
)


def need(ok):
    if not ok:
        raise ValueError('public paired-recipe dispatch prerequisite')


def _hash_map(value, keys):
    need(type(value) is dict and set(value) == set(keys))
    need(all(phase.kernel.digest(value[key]) for key in keys))
    return {key: value[key] for key in keys}


def _context(value):
    need(type(value) is dict and set(value) == {
        'schema', 'profile', 'shared', 'native16', 'native128'})
    need(type(value['schema']) is int and value['schema'] == 1)
    need(type(value['profile']) is str and value['profile'] == PROFILE)
    shared = _hash_map(value['shared'], SHARED_CONTEXT_HASHES)
    cases = {name: _hash_map(value[name], CASE_CONTEXT_HASHES)
             for name in ('native16', 'native128')}
    need(all(case['source_manifest_sha256'] == shared['source_manifest_sha256']
             for case in cases.values()))
    need(cases['native16']['result_sha256'] != cases['native128']['result_sha256'])
    return dict(schema=1, profile=PROFILE, shared=shared, **cases)


def _case(report, diagnostics, tokens, expected, shared):
    # Retain the original two-mode/29-stage/nine-semantic verdict validators.
    report = phase.validate_report(report)
    diagnostics = phase.validate_diagnostics(diagnostics)
    need(report['tokens'] == tokens and diagnostics['tokens'] == tokens)
    need(report['status'] == 'COMPLETE_NATIVE_VALIDATION' and
         report['native_status'] == 'PASS_BF16_STAGE_BUDGET' and
         report['native_acceptance'] is True)
    need(diagnostics['status'] == 'COMPLETE_DIAGNOSTICS')
    need(phase.continuation_eligible(diagnostics))
    environment = diagnostics['fenv']
    snapshots = list(environment['libraries'].values()) + [
        environment[key] for key in ('before_recipe', 'after_recipe', 'after_gate')]
    expected_fenv = dict(status='OBSERVED', x87_round=0, sse_round=0, ftz=False, daz=False)
    need(len(snapshots) == 6 and all(phase.same(item, expected_fenv) for item in snapshots))
    need(all(changed is False for changed in diagnostics['fenv_changes'].values()))
    need(all(record['implementation'] == IMPLEMENTATION and record['isa'] == ISA
             for record in diagnostics['capture']['bf16']['records']))
    need(all(report[key] == diagnostics[key]
             for key in REPORT_DIAGNOSTIC_IDENTITIES))
    need(all(report[key] == shared[key] for key in SHARED_REPORT_HASHES))
    need(diagnostics['payload_tensor_map_sha256'] == shared['payload_tensor_map_sha256'])
    need(report['result_sha256'] == expected['result_sha256'] and
         report['source_manifest_sha256'] == expected['source_manifest_sha256'])
    need(phase.kernel.sha(phase.kernel.encoded(report)) == expected['report_sha256'])
    need(phase.kernel.sha(phase.kernel.encoded(diagnostics)) == expected['diagnostics_sha256'])
    return report, diagnostics


def validate_pair(native16_report, native16_diagnostics, native128_report,
                  native128_diagnostics, *, context):
    """Return bounded prerequisite evidence, or reject the whole native pair.

    ``context`` has exact keys schema=1, profile=PROFILE, shared, native16 and
    native128. The shared hash map uses SHARED_CONTEXT_HASHES; each shape map
    uses CASE_CONTEXT_HASHES. Report/diagnostic hashes cover the existing
    kernel.encoded canonical JSON representation, including its final newline.
    No context is fabricated here and no artifact bytes are independently read.
    """
    context = _context(context)
    small, small_diagnostics = _case(native16_report, native16_diagnostics, 16,
                                     context['native16'], context['shared'])
    large, large_diagnostics = _case(native128_report, native128_diagnostics, 128,
                                     context['native128'], context['shared'])
    need(large['m16_result_sha256'] == small['result_sha256'])
    need(phase.same(small_diagnostics['payload_sha256'], large_diagnostics['payload_sha256']))
    # These bounded observations identify this pair, not a general arithmetic
    # equivalence class. A different host/build/fenv cannot be spliced into it.
    need(all(phase.same(small_diagnostics[key], large_diagnostics[key])
             for key in ('backend_build', 'cpu', 'fenv', 'fenv_changes')))
    summary = dict(
        schema=1, profile=PROFILE, status='NUMERICAL_PREREQUISITE_ONLY',
        preparation_only=True, native_numerical_prerequisite_passed=True,
        runtime_ready=False, actual_chain_executed=False, public_execution=False,
        backend_order_proven=False, rtl_execution=False, full_29_node_acceptance=False,
        implementation=IMPLEMENTATION, isa=ISA, tokens=[16, 128],
        bf16_matmuls_per_shape=9, stages_per_mode=29, semantics_per_mode=9,
        shared=context['shared'], native16=context['native16'],
        native128=context['native128'], m16_result_sha256=small['result_sha256'],
    )
    need(len(phase.kernel.encoded(summary)) <= MAX_SUMMARY_BYTES)
    return phase.canonical(summary)

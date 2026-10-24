"""Standard-library-only, fail-closed handoff. This module never imports a DUT.

The parent must supply and independently review admission.py and ADMISSION.json.
Neither is provided by the integration shell; source authoring is not admission.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

CONTRACT = 'original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1'


class MissingPrerequisite(ValueError):
    """A required source, observation, or actual-admission prerequisite is absent."""


def need(condition, message):
    if not condition:
        raise MissingPrerequisite(message)


def _identity(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink(), 'missing regular prerequisite: ' + str(path))
    h = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            size += len(block)
            h.update(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def _bound_path(root, relative):
    relative = Path(relative)
    need(not relative.is_absolute() and '..' not in relative.parts, 'nonrelative admission binding')
    path = root / relative
    need(path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)),
         'aliased prerequisite: ' + str(path))
    return path


def _load_admission_bridge(root, expected):
    """Load pinned bridge bytes without a cached-bytecode import path."""
    import types
    module_name = 'admission'
    need(module_name not in sys.modules, 'new admission bridge is single-use, not a retry path')
    path = _bound_path(root, 'admission.py')
    raw = path.read_bytes()
    need(dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) == expected,
         'admission bridge bytes changed after prerequisite checks')
    code = compile(raw, str(path), 'exec', dont_inherit=True, optimize=0)
    bridge = types.ModuleType(module_name)
    bridge.__file__, bridge.__package__ = str(path), ''
    sys.modules[module_name] = bridge
    try:
        exec(code, bridge.__dict__)
        need(sys.modules.get(module_name) is bridge and bridge.__file__ == str(path) and
             bridge.__name__ == module_name, 'canonical new admission bridge required')
    except BaseException:
        if sys.modules.get(module_name) is bridge:
            del sys.modules[module_name]
        raise
    return bridge


def load_runtime(candidate, request):
    """Validate assembly prerequisites BEFORE importing the new admission bridge.

    ADMISSION.json is only the local assembly declaration. The separately pinned
    bridge must validate independent review, explicit one-use authority, fresh
    resource admission and immutable runtime pins. A JSON boolean is not authority.
    The bridge must reject replay and must never build/recompile a native artifact.
    """
    root = Path(candidate).resolve()
    admission_path = root / 'ADMISSION.json'
    need(admission_path.is_file(), 'missing NEW reviewed fullblock ADMISSION.json; source-only shell')
    need(admission_path.stat().st_size <= 2 * 1024 * 1024, 'oversized admission document')
    declaration = json.loads(admission_path.read_bytes())
    need(type(declaration) is dict and declaration.get('schema') == 'fixed93-fullblock-admission-v1',
         'new fullblock admission schema required')
    need(declaration.get('status') == 'REVIEWED_FIXED93_M128_PUBLIC21_ACTUAL' and
         declaration.get('actual_execution_authorized') is True and
         declaration.get('source_only') is False and declaration.get('automatic_retry') is False,
         'source-only/unreviewed/retry-enabled declaration cannot authorize actual execution')
    need(declaration.get('evidence_contract') == CONTRACT, 'evidence contract changed')
    bindings = declaration.get('files')
    need(type(bindings) is dict, 'exact new assembly file identities required')
    required = {'admission.py', 'SOURCE_MANIFEST.json',
                'observation/fullblock_attention.py', 'integration/runner.py',
                'integration/interface.py', 'integration/__init__.py',
                'integration/EVIDENCE_INVENTORY.json', 'capture/anchors.json', 'capture/CODEC_PINS.json'}
    # Every supplied Python observation/integration file must be bound, including
    # decoder/adapter helpers. New helpers cannot be injected behind a pinned entry.
    for base in ('observation', 'integration', 'capture'):
        directory = root / base
        need(directory.is_dir(), 'missing ' + base + ' source assembly')
        required.update(str(p.relative_to(root)) for p in directory.rglob('*.py'))
    need(required <= bindings.keys(), 'new bridge/observation/integration file pins are incomplete')
    for relative, expected in bindings.items():
        need(type(relative) is str and type(expected) is dict and
             set(expected) == {'bytes', 'sha256'}, 'invalid exact prerequisite identity')
        need(_identity(_bound_path(root, relative)) == expected, 'prerequisite drift: ' + relative)
    source_root = _bound_path(root, 'source')
    need(source_root.is_dir(), 'missing frozen source mirror')
    source_manifest = _bound_path(root, 'SOURCE_MANIFEST.json')
    reviewed = request.get('reviewed_source_manifest')
    need(type(reviewed) is str and len(reviewed) == 64 and all(c in '0123456789abcdef' for c in reviewed),
         'explicit reviewed NEW source-manifest SHA256 required')
    need(reviewed == _identity(source_manifest)['sha256'], 'reviewed source-manifest file identity differs')
    manifest = json.loads(source_manifest.read_bytes())
    hashes, sizes = manifest.get('source_sha256'), manifest.get('source_bytes')
    need(type(hashes) is dict and type(sizes) is dict and hashes.keys() == sizes.keys() and hashes,
         'source manifest requires exact source_sha256/source_bytes')
    for relative, digest in hashes.items():
        need(_identity(_bound_path(source_root, relative)) == {'bytes': sizes[relative], 'sha256': digest},
             'source mirror drift: ' + relative)
    # Preserve the public-selected correspondence witness as a separate identity.
    selected, selected_sizes = manifest.get('selected_source_sha256'), manifest.get('selected_source_bytes')
    need(type(selected) is dict and type(selected_sizes) is dict and selected and
         selected.keys() == selected_sizes.keys(),
         'exact selected Fixed93 witness identities required; historical source/chisel is not selected')
    for relative, digest in selected.items():
        need(_identity(_bound_path(root / 'selected', relative)) ==
             {'bytes': selected_sizes[relative], 'sha256': digest}, 'selected Fixed93 witness drift: ' + relative)
    module_name = 'admission'
    need(module_name not in sys.modules, 'new admission bridge is single-use, not a retry path')
    # The reviewed bridge imports only the exact new assembly/source namespaces.
    # Path setup happens after hash checks and before its admitted imports.
    sys.path.insert(0, str(source_root))
    sys.path.insert(0, str(root))
    bridge = _load_admission_bridge(root, bindings['admission.py'])
    need(callable(getattr(bridge, 'admit', None)), 'new bridge must implement admit(request)')
    runtime = bridge.admit(dict(request, candidate=str(root), declaration=declaration))
    need(type(runtime) is dict, 'new admission bridge must return a runtime dictionary')
    fields = {'gates', 'native_artifact', 'initialize_runtime', 'source_root', 'source_manifest',
              'source_sha256', 'limits', 'attention_trace_limits', 'wholeblock_observation',
              'one_use_authority_verified', 'native_artifact_mode', 'evidence_contract'}
    need(fields <= runtime.keys(), 'new runtime handoff is incomplete')
    need(runtime['one_use_authority_verified'] is True and runtime['evidence_contract'] == CONTRACT,
         'independent one-use actual admission missing')
    need(runtime['native_artifact_mode'] == 'verified_existing_profile2_elf_reused',
         'only the existing verified profile2 ELF is admissible; no build or hermetic claim')
    need(Path(runtime['source_root']).resolve() == source_root and
         Path(runtime['source_manifest']).resolve() == source_manifest and runtime['source_sha256'] == hashes,
         'new runtime source binding differs')
    need(callable(runtime['initialize_runtime']), 'exact runtime initializer missing')
    limits = runtime['limits']
    keys = ('inner_wall_seconds', 'outer_wall_seconds', 'rss_bytes', 'output_bytes',
            'file_bytes', 'log_bytes', 'progress_loop_interval')
    need(type(limits) is dict and all(type(limits.get(k)) is int and limits[k] > 0 for k in keys),
         'new reviewed wholeblock limits missing; no inherited default budget')
    need(limits.get('automatic_retry') is False and limits['outer_wall_seconds'] > limits['inner_wall_seconds'],
         'new no-retry outer/inner limits required')
    need(limits['progress_loop_interval'] == 131072,
         'unchanged accepted-memory driver sampling interval must be admitted explicitly')
    need(type(runtime['attention_trace_limits']) is dict and runtime['attention_trace_limits'], 'new explicit observer bounds missing')
    need(callable(runtime['wholeblock_observation']), 'new source-bound wholeblock observation factory missing')
    return runtime


def validate_wholeblock_context(whole):
    need(all(callable(getattr(whole, n, None)) for n in ('__enter__', '__exit__', 'bind', 'seal', 'close')) and
         getattr(whole, 'public_trace', None) is not None, 'wholeblock source-bound observation is unimplemented')
    need(all(callable(getattr(whole.public_trace, n, None)) for n in ('event', 'write', 'report', 'close')),
         'lossless delegate-compatible public trace missing')
    dispatcher = getattr(whole, 'trace_dispatcher', None)
    need(dispatcher is not None and all(callable(getattr(dispatcher, n, None)) for n in ('register', 'unregister')),
         'source-bound composed trace dispatcher missing')


def validate_observation(capture, report):
    need(type(report) is dict and report.get('schema') == 'fixed93-fullblock-attention-pv-reuse-observation-v1',
         'PV reuse observation schema required')
    expected_reuse = {'normalization_evaluations_per_causal_key':1, 'probability_use_repeats':8,
                      'normalization_reuses_per_causal_key':7, 'observed_normalization_reuses':693504}
    need(all(type(report.get(k)) is int and report[k] == v for k,v in expected_reuse.items()) and
         report.get('scalar_schedule_changed') is True and
         report.get('both_probability_domains_repeats_verified') is True,
         'actual one normalization/eight operands/seven reuses contract required')
    need(type(report) is dict and report.get('complete_observation') is True and
         report.get('control_only') is False and str(report.get('status', '')).startswith('COMPLETE_'),
         'complete actual Fixed93 observation required')
    need(all(callable(getattr(capture, n, None)) for n in ('report', 'save', 'field_words', 'legacy_adapter')),
         'Fixed93 observation/export interface incomplete')
    shapes = {name: (12, 128, 128) for name in ('dot_raw', 'dot_bf16', 'scale_fp32', 'score_bf16',
                'score_difference', 'exp_fp32', 'denominator_step')}
    shapes.update({name: (12, 128, 128, 16) for name in ('packed_stripes', 'fold_before', 'fold_after')})
    shapes.update({name: (12, 128, 128, 8) for name in ('probability_fp32', 'probability_bf16')})
    shapes.update(pv_key_raw=(12, 128, 128, 8, 16), normalizer=(12, 128, 3),
                  pv_final_raw=(12, 128, 128), pv_bf16=(12, 128, 128))
    need(set(capture.fields) == set(shapes), 'frozen Attention field inventory changed')
    for name, shape in shapes.items():
        field = capture.fields[name]
        need(tuple(field['shape']) == shape and 'frequency' in field, 'Attention shape/frequency missing: ' + name)
    # Coverage and eight-use consistency are checked by the pinned observer and
    # checked again by legacy_adapter only after the whole actual output seal.
    need(len(capture.field_words('pv_bf16')) == 786432, 'complete M128 PV output extent required')


def validate_wholeblock_seal(seal, algorithm_seal):
    need(type(seal) is dict and seal.get('evidence_contract') == CONTRACT and
         seal.get('complete_declared_schedule') is True and seal.get('complete_declared_cache') is True and
         algorithm_seal.get('complete_algorithm_arrays') is True and seal.get('source_bound') is True and
         seal.get('lossless_streams_sealed') is True and seal.get('six_actual_silu_phases_complete') is True,
         'wholeblock original arrays + true schedule/cache streams remain incomplete')
    need(seal.get('native_silu_inner_exp_observed') is False and
         seal.get('native_silu_pre_bf16_product_observed') is False,
         'unchanged ELF cannot attest unexported SiLU exp/pre-BF16-product values')
    need(type(seal.get('artifacts')) is dict and bool(seal['artifacts']), 'wholeblock evidence artifact seal missing')
    need(type(seal.get('covered_schedule_domains')) is list and bool(seal['covered_schedule_domains']),
         'finite declared schedule/cache domain inventory missing')


def validate_comparison_scope(report):
    """Preserve the inherited 22 + 1 + 6 classification, not a 29-node PASS."""
    prefix = {'n0', 'qr', 'q', 'kr', 'k', 'v'}
    raw = {'qraw', 'kraw', 'vraw'}
    attention = {'scores', 'logits', 'prob', 'pv', 'att'}
    tail = {'o', 'r', 'n1', 'gate', 'up', 'silu', 'act', 'down', 'y'}
    only = {'x', 'cos', 'sin', 'repeat_k', 'repeat_v', 'mask'}
    need(set(report['producer_comparisons']) == prefix | raw and
         set(report['attention_comparisons']) == attention | {'softmax_fp32'} and
         set(report['tail_comparisons']) == tail and set(report['cold_cache_comparisons']) == {'cache_k', 'cache_v'},
         'original 22 numerical gates/one diagnostic inventory changed')
    need(all(report['producer_comparisons'][n]['official_numeric_pass'] is None for n in raw) and
         report['attention_comparisons']['softmax_fp32']['official_numeric_pass'] is None and
         report.get('softmax_fp32_tolerance') is None,
         'invented raw-QKV or softmax-FP32 official numerical gate')
    need(report.get('full_29_node_acceptance') is False and set(report.get('reference_only_nodes', ())) == only and
         set(report.get('missing_official_raw_nodes', ())) == raw and
         report.get('typed_attention_bit_exact_executed') is False,
         'wholeblock acceptance was broadened beyond inherited comparison scope')

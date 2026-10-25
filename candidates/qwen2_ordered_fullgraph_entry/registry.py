"""Terminal-only metadata registry of actual public21 outputs and observations.

No DUT, native library, reference, arithmetic recipe, or tensor constructor is
imported here. Array buffers are read in place. Gate/Up are real tile-read audit
copies, NOT DDR outputs; causal Attention fields remain passive observations.
Source/code binding belongs to the caller's cold admission, not to this schema.
Successful registration proves inventory/control closure, never numeric PASS.
"""
from array import array
from dataclasses import dataclass
import hashlib
import sys


STAGE_WIDTHS = dict(zip(
    ('n0', 'qr', 'kr', 'v', 'q', 'k', 'att', 'o', 'r', 'n1',
     'gate', 'up', 'act', 'down', 'y'),
    (1536, 1536, 256, 256, 1536, 256, 1536, 1536, 1536, 1536,
     8960, 8960, 8960, 1536, 1536)))
RAW_WIDTHS = {'qraw': 1536, 'kraw': 256, 'vraw': 256}
ATTENTION_FIELDS = (
    'dot_parts', 'unrounded_dot_sum', 'dot_bf16', 'scores_bf16',
    'softmax_exp', 'softmax_fp32', 'prob_bf16', 'normalizer',
    'pv_raw', 'pv_bf16')
NORMAL_PROVENANCE = 'NORMAL_LOADED_SOURCE_SOFTWARE'
SENTINEL = 0xa5963cc3
OFFICIAL_REQUIRED_STAGES = (
    'x', 'n0', 'qr', 'kr', 'v', 'q', 'k', 'cache_k', 'cache_v',
    'repeat_k', 'repeat_v', 'scores', 'logits', 'prob', 'pv', 'att',
    'o', 'r', 'n1', 'gate', 'up', 'silu', 'act', 'down', 'y',
    'cos', 'sin', 'mask', 'softmax_fp32')


def official_coverage_plan():
    """Describe existing sources and absent nodes, never construct a value.

    REQUIRED_STAGES defines 29 public comparison nodes, not all scalar
    internals. Neither a 32-entry registry nor a source mapping claims that
    all 29 official tensors were observed or numerically accepted.
    """
    nodes = {}
    for name in OFFICIAL_REQUIRED_STAGES:
        if name in STAGE_WIDTHS or name == 'silu':
            nodes[name] = dict(status='ACTUAL_SOURCE_PRESENT_COMPARISON_PENDING', source=name,
                               layout='original token-major storage; official view conversion not performed')
        elif name in ('cache_k', 'cache_v'):
            nodes[name] = dict(status='ACTUAL_KV_VIEW_METADATA_ONLY', source=name,
                               layout='original token-major parent kv; official head-major view not materialized')
        elif name == 'pv':
            nodes[name] = dict(status='ACTUAL_SOURCE_PRESENT_COMPARISON_PENDING', source='pv_bf16',
                               layout='head-major; equality to actual att storage checked without copying')
        elif name in ('scores', 'prob', 'softmax_fp32'):
            nodes[name] = dict(status='ACTUAL_CAUSAL_ONLY_PARTIAL_SOURCE',
                               source={'scores': 'scores_bf16', 'prob': 'prob_bf16',
                                       'softmax_fp32': 'softmax_fp32'}[name],
                               missing='future-key positions are intentionally unobserved sentinels')
        else:
            reason, future_source = {
                'x': ('input excluded from the suffix output registry',
                      'existing original readonly input, with input provenance and shape validation'),
                'repeat_k': ('addressed KV reuse is not a materialized repeated-key tensor',
                             'actual accepted KV-head mapping/read observations, never np.repeat reconstruction'),
                'repeat_v': ('addressed KV reuse is not a materialized repeated-value tensor',
                             'actual accepted KV-head mapping/read observations, never np.repeat reconstruction'),
                'cos': ('BF16 RoPE cosine operands are not observed by current capture',
                        'OfficialPrefixOwner._rope actual cosine after bf returns'),
                'sin': ('BF16 RoPE sine operands are not observed by current capture',
                        'OfficialPrefixOwner._rope actual sine after bf returns'),
                'mask': ('causal protocol omits future keys; no explicit mask tensor is produced',
                         'document absent producer; do not synthesize a comparison tensor'),
                'logits': ('no independent scores-plus-mask tensor is produced or observed',
                           'document absent producer; do not relabel scores as full logits'),
            }[name]
            status = ('READONLY_INPUT_NOT_REGISTERED' if name == 'x' else
                      'MISSING_ACTUAL_OPERAND_CAPTURE' if name in ('cos', 'sin') else
                      'PHYSICALLY_NONMATERIALIZED_SEMANTIC_NODE')
            nodes[name] = dict(status=status, reason=reason,
                               future_source_requirement=future_source)
        if name in STAGE_WIDTHS and name not in ('gate', 'up'):
            storage, capture = 'ACKED_PUBLISHED_DDR', 'ACTUAL_SUFFIX_OUTPUT'
        elif name in ('gate', 'up'):
            storage, capture = 'RESIDENT_TILES_WITH_VIRTUAL_DDR_RESERVATION', 'ACTUAL_TILE_READ_AUDIT'
        elif name in ('cache_k', 'cache_v'):
            storage, capture = 'VIEW_OF_PHYSICAL_KV_PARENT', 'METADATA_VIEW_OF_ACTUAL_BUFFER'
        elif name == 'silu':
            storage, capture = 'ACTUAL_PHASE4_RETURN_NO_STANDALONE_DDR', 'SEALED_ACTUAL_PHASE4'
        elif name == 'pv':
            storage, capture = 'ACTUAL_STORE_WORDS_PHYSICALLY_PUBLISHED_AS_ATT', 'PASSIVE_COMPLETE_OBSERVATION'
        elif name in ('scores', 'prob'):
            storage, capture = 'VIRTUAL_DDR_RESERVATION_ACTUAL_CAUSAL_VALUES_ONLY', 'PASSIVE_CAUSAL_ONLY_OBSERVATION'
        elif name == 'softmax_fp32':
            storage, capture = 'ACTUAL_SCALAR_RETURNS_NO_STANDALONE_DDR', 'PASSIVE_CAUSAL_ONLY_OBSERVATION'
        elif name in ('cos', 'sin'):
            storage, capture = 'ACTUAL_BF16_OPERANDS_FROM_READONLY_FP32_TABLE_NO_EXPANDED_TENSOR', 'MISSING_ACTUAL_OPERAND_CAPTURE'
        elif name == 'x':
            storage, capture = 'ORIGINAL_READONLY_INPUT', 'NOT_REGISTERED_IN_SUFFIX_INVENTORY'
        else:
            storage, capture = 'NO_INDEPENDENT_TENSOR_PRODUCER', 'NOT_CAPTUREABLE_AS_EXISTING_MATERIALIZED_TENSOR'
        nodes[name].update(physical_materialization=storage, actual_capture=capture,
                           values_synthesized=False, numeric_pass_inherited=False)
    missing = ('x', 'repeat_k', 'repeat_v', 'logits', 'cos', 'sin', 'mask')
    return dict(required_stage_source='scripts/qwen2_layer0_model_gate.py:REQUIRED_STAGES',
                required_stage_source_sha256='917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85',
                required_count=29, nodes=nodes, complete_official_29_node_coverage=False,
                actual_registry_inventory_is_official_29_coverage=False,
                missing_or_nonmaterialized_nodes=list(missing),
                missing_actual_operand_capture_nodes=['cos', 'sin'],
                physically_nonmaterialized_semantic_nodes=['repeat_k', 'repeat_v', 'logits', 'mask'],
                readonly_inputs_not_registered=['x'],
                partially_observed_nodes=['scores', 'prob', 'softmax_fp32'],
                numeric_comparison_performed=False, values_reconstructed_to_fill_gaps=False,
                historical_assigned_27_reference_policy=dict(
                    status='NOT_IMPORTED_OR_VALIDATED_BY_THIS_REGISTRY',
                    reuse_must_be_explicit=True, new_node_coverage_inherited=False,
                    numeric_pass_inherited=False, missing_actual_values_may_be_filled=False,
                    required_matching_evidence=['raw_input_identities', 'row_and_cache_profile',
                        'producer_and_reference_source_identities', 'node_semantics_and_layout',
                        'actual_presence_masks', 'materialization_policy_and_thresholds'],
                    allowed_use='comparison context only after matching evidence is validated and whole terminal gate opens'),
                unobserved_internal_diagnostics={
                    'norm': dict(public_pcs=[0, 15], materialized_outputs=['n0', 'n1'],
                        producer='official_bf16.owners.OfficialPrefixOwner._norm',
                        producer_source_sha256='0c87797587281b4e7f23663242e947ffe4157db9a644e788d67eb5c9045c50c1',
                        unobserved_locals=['square', 'partial', 'residue_sum', 'lane_sum',
                            'total', 'mean', 'epsilon', 'root', 'scale', 'scaled'],
                        scope='not separate REQUIRED_STAGES nodes; future passive observation only'),
                    'rope': dict(public_pcs=[3, 6], materialized_outputs=['q', 'k'],
                        producer='official_bf16.owners.OfficialPrefixOwner._rope',
                        producer_source_sha256='0c87797587281b4e7f23663242e947ffe4157db9a644e788d67eb5c9045c50c1',
                        unobserved_locals=['cosine', 'sine', 'xc', 'ys', 'xs', 'yc'],
                        scope='cos/sin are required public nodes; products are internal diagnostics; no reconstruction')})


def inventory_correspondence():
    """All 32 registry entries mapped without counting aliases as new nodes."""
    names = tuple(STAGE_WIDTHS) + tuple(RAW_WIDTHS) + ('kv', 'silu') + ATTENTION_FIELDS + ('cache_k', 'cache_v')
    semantic = {'scores_bf16': 'scores', 'prob_bf16': 'prob', 'pv_bf16': 'pv'}
    result = {}
    for name in names:
        if name in STAGE_WIDTHS or name in ('silu', 'softmax_fp32'):
            nodes, role = [name], 'actual_value_source'
        elif name in ('cache_k', 'cache_v'):
            nodes, role = [name], 'metadata_view_not_additional_value_or_allocation'
        elif name == 'kv':
            nodes, role = ['cache_k', 'cache_v'], 'shared_parent_not_two_additional_nodes'
        elif name in semantic:
            nodes, role = [semantic[name]], 'actual_passive_observation'
        else:
            nodes, role = [], 'extra_diagnostic_not_an_official_named_node'
        result[name] = dict(official_semantic_nodes=nodes, role=role,
                           official_node_pass_claimed=False)
    return result


def need(condition, message):
    if not condition:
        raise ValueError(message)


def _digest(buffer):
    return hashlib.sha256(memoryview(buffer).cast('B')).hexdigest()


def _words(value, count, name):
    need(type(value) is array and value.typecode == 'I' and value.itemsize == 4
         and len(value) == count, 'actual uint32 word extent: ' + name)
    return _digest(value)


def _host_terminal(report):
    need(type(report) is dict and
         report.get('status') == 'PUBLIC21_PC0_20_SOFTWARE_EXECUTED',
         'whole original suffix return required')
    for key in ('full_block_executed', 'full_block_software_model_executed',
                'same_owner_and_banks', 'same_physical_memory_and_services'):
        need(report.get(key) is True, 'whole suffix identity/terminal: ' + key)
    need(report.get('reference_arithmetic_executed') is False,
         'reference arithmetic cannot supply actual registry')
    host = report['host']
    result, accepted = host['launch_result'], host['accepted']
    need(type(result) is dict and 'status' in result and result['status'] is None and
         result.get('completed') == 21 and result.get('jobs') == 17,
         'whole terminal needs 21 completions and 17 actual jobs')
    need([c['pc'] for c in host['completions']] == list(range(21)) and
         all('status' in c and c['status'] is None for c in host['completions']) and
         host['events'] == list(range(22)), 'missing/duplicate public completion or event')
    need(all(type(accepted.get(k)) is int and accepted[k] == v for k, v in
             {'completion_fire': 21, 'request_fire': 17,
              'owner_result_fire': 17, 'result_fire': 1}.items()),
         'whole public accepted handshake counts differ')
    need(host.get('reset_required') is False and
         report['matrix'].get('reset_required') is False,
         'whole terminal retained reset obligation')
    return host


@dataclass
class _TerminalEvidence:
    execution: object
    physical: object
    memory: object
    report: dict
    consumed: bool = False


def _live_terminal(x, physical, memory, report):
    host = _host_terminal(report)
    need(x.host.state == 'idle' and len(x.host.program) == 21 and
         x.host.pc == x.host.completed == 21 and x.host.jobs == 17 and
         x.launch_result == host['launch_result'] and
         x.completions == host['completions'] and
         x.host.events == set(range(22)), 'live whole launch terminal differs')
    need(all(x.counts[k] == host['accepted'][k] for k in
             ('completion_fire', 'request_fire', 'owner_result_fire', 'result_fire')),
         'live whole accepted counts differ')
    need(x.owner.state == x.prefix_owner.state == x.attention_owner.state == 'idle'
         and x.owner.lease is None and x.owner.tiles.idle and not x.owner.tiles.leased,
         'owner or resident tile obligations remain')
    matrix = x.matrix_service
    # Read backing attributes, NEVER native-backed done/reset_required/ports.
    need(matrix.owner is None and matrix.group is None and matrix.result is None
         and matrix._done is None and matrix._dense is None and
         x.prefix_owner.scalar.client is None, 'shared service obligations remain')
    attention = x.attention_owner
    need(attention.matrix is matrix and attention.scalar is x.prefix_owner.scalar
         and attention.matrix_client is None and not attention.memory_pending
         and not attention.scratch_pending and not attention.scratch_leased
         and not attention.poison, 'Attention resource or identity obligations remain')
    need(physical.pending is None and memory.workspace.finished and
         memory.physical_memory is physical and
         memory.workspace.physical_memory is physical and
         memory.act.data is physical.regions['act']['data'] and
         x.frontend.memory.physical_memory is physical and
         x.frontend.port.memory is x.frontend.memory,
         'physical output/workspace identity or obligations remain')
    return host


def terminal_snapshot(x, physical, memory, execution_report):
    """Read clean live state after suffix return, without native-backed calls."""
    _live_terminal(x, physical, memory, execution_report)
    return _TerminalEvidence(x, physical, memory, execution_report)


def _attention(rows, fields, report):
    need(type(report) is dict and report.get('execution_provenance') == NORMAL_PROVENANCE,
         'Attention reference/AST/unknown provenance forbidden')
    need(report.get('status') == 'COMPLETE_SOFTWARE_OBSERVATION_NOT_HARDWARE' and
         report.get('terminal', {}).get('clean') is True and
         report['terminal'].get('same_services') is True and
         report.get('observer_launches_native_or_rtl') is False,
         'complete clean passive Attention observation required')
    need(type(report.get('packed_acks')) is int and report['packed_acks'] > 0 and
         report['packed_acks'] == report.get('packed_done'),
         'Attention result/done acknowledgement coverage')
    need(type(fields) is dict and set(fields) == set(ATTENTION_FIELDS) and
         set(report['fields']) == set(ATTENTION_FIELDS),
         'exact ten actual Attention fields required')
    entries = {}
    for name in ATTENTION_FIELDS:
        f = fields[name]
        shape = ((12, rows, rows, 16) if name == 'dot_parts' else
                 (12, rows, 3) if name == 'normalizer' else
                 (12, rows, 128) if name in ('pv_raw', 'pv_bf16') else
                 (12, rows, rows))
        count = 1
        for dimension in shape:
            count *= dimension
        need(tuple(f['shape']) == shape, 'Attention field shape: ' + name)
        raw_hash = _words(f['words'], count, name)
        need(type(f['observed']) is bytearray and len(f['observed']) == count and
             type(f['frequency']) is array and f['frequency'].typecode == 'H'
             and f['frequency'].itemsize == 2 and len(f['frequency']) == count,
             'Attention presence/frequency extent: ' + name)
        width = shape[-1] if name in ('dot_parts', 'normalizer', 'pv_raw', 'pv_bf16') else 1
        causal = name not in ('normalizer', 'pv_raw', 'pv_bf16')
        repeated = name in ('softmax_fp32', 'prob_bf16')
        observed = 0
        for h in range(12):
            for token in range(rows):
                for key in range(rows) if causal else (None,):
                    present = key is None or key <= token
                    start = ((h * rows + token) * rows + key) * width if causal else (h * rows + token) * width
                    frequency = (8 if repeated else 1) if present else 0
                    for index in range(start, start + width):
                        need(f['observed'][index] == int(present) and
                             f['frequency'][index] == frequency,
                             'missing/duplicate Attention observation: ' + name)
                        need(present or f['words'][index] == SENTINEL,
                             'future causal field filled: ' + name)
                        observed += int(present)
        repeats = 7 * observed if repeated else 0
        need(type(f['writes']) is int and f['writes'] == observed and
             type(f['repeats']) is int and f['repeats'] == repeats,
             'Attention event accounting: ' + name)
        summary = dict(shape=list(shape), words=count, observed_words=observed,
                       raw_sha256=raw_hash, presence_sha256=_digest(f['observed']),
                       frequency_sha256=_digest(f['frequency']), writes=observed,
                       identical_repeats=repeats)
        source = dict(report['fields'][name])
        source['shape'] = list(source['shape'])
        need(source == summary, 'Attention report/buffer digest mismatch: ' + name)
        entries[name] = dict(summary, provenance='ACTUAL_PASSIVE_ATTENTION_OBSERVATION',
                             storage='observer_only_not_DDR',
                             coverage='causal_positions_only' if causal else 'complete')
    return entries


def seal_registry(*, rows, actual, execution_report, capture_report,
                  capture_fields, silu_library, terminal,
                  actual_provenance=NORMAL_PROVENANCE):
    """Validate complete actual inventory, then invoke the original SiLU seal.

    The supplied silu_library is the existing source-bound ObservedSiluLibrary.
    This function stores only hashes, shapes, source roles and view metadata.
    The caller must not open references before obtaining terminal_snapshot.
    """
    need(sys.byteorder == 'little', 'reviewed little-endian buffers required')
    need(type(rows) is int and rows in (16, 128), 'original fullgraph row geometry')
    need(type(terminal) is _TerminalEvidence and not terminal.consumed and
         terminal.report is execution_report, 'fresh matching whole terminal required')
    _live_terminal(terminal.execution, terminal.physical, terminal.memory, execution_report)
    need(actual_provenance == NORMAL_PROVENANCE, 'reference/AST/unknown actual provenance forbidden')
    widths = dict(STAGE_WIDTHS, **RAW_WIDTHS)
    need(type(actual) is dict and set(actual) == set(widths) | {'kv'},
         'exact original stage/raw/KV actual output inventory required')
    physical = execution_report['memory']['outputs']
    virtual = execution_report['virtual_outputs']
    need(virtual.get('unchanged') is True and virtual.get('physical_writes') == 0 and
         set(virtual['initial_and_final_sha256']) == {'gate', 'up'},
         'Gate/Up virtual DDR reservations changed')
    entries = {}
    for name, value in actual.items():
        shape = (2, rows, 2, 128) if name == 'kv' else (rows, widths[name])
        count = rows * 512 if name == 'kv' else rows * widths[name]
        raw_hash = _words(value, count, name)
        record = physical[name]
        need(record['bytes'] == count * 4, 'physical allocation extent: ' + name)
        tile_audit = name in ('gate', 'up')
        if tile_audit:
            need(record['written_bytes'] == record['ack_bytes'] == 0 and
                 record['terminal'] is False and record['published'] is False,
                 'Gate/Up audit was incorrectly treated as DDR output')
        else:
            need(record['written_bytes'] == record['ack_bytes'] == count * 4 and
                 record['terminal'] is True and record['published'] is True and
                 record['sha256'] == raw_hash, 'actual output not ACKed/published: ' + name)
        entries[name] = dict(shape=list(shape), words=count, bytes=count * 4,
                             raw_sha256=raw_hash, coverage='complete',
                             storage='tile_read_audit_not_DDR' if tile_audit else 'ACKed_published_DDR',
                             provenance='ACTUAL_FFN_TILE_READS' if tile_audit else 'ACTUAL_SUFFIX_RETURN')
    for name in ('scores', 'probabilities'):
        r = physical[name]
        need(r['written_bytes'] == r['ack_bytes'] == 0 and r['terminal'] is False
             and r['published'] is False, 'Attention virtual DDR materialized: ' + name)
    attention = _attention(rows, capture_fields, capture_report)
    # Compare the two existing storage orders directly, without a transpose,
    # reconstruction, reference, new arithmetic or copied numerical tensor.
    pv, att = capture_fields['pv_bf16']['words'], actual['att']
    need(all(pv[(head * rows + token) * 128 + col] ==
             att[token * 1536 + head * 128 + col]
             for head in range(12) for token in range(rows) for col in range(128)),
         'observed PV differs from actual ACKed Attention output')
    need(getattr(silu_library, 'rows', None) == rows,
         'SiLU observer does not belong to this row profile')
    # The only bytes conversion follows the original observer seal interface.
    silu = silu_library.seal(actual['act'].tobytes())
    need(type(silu) is bytes and len(silu) == rows * 8960 * 4,
         'actual SiLU phase4 seal extent')
    entries['silu'] = dict(shape=[rows, 8960], words=rows * 8960,
                           bytes=len(silu), raw_sha256=_digest(silu), coverage='complete',
                           provenance='ACTUAL_SF_VECTOR_PHASE4_SEALED', storage='observer_only_not_DDR')
    entries.update(attention)
    for index, name in enumerate(('cache_k', 'cache_v')):
        entries[name] = dict(shape=[rows, 2, 128], words=rows * 256,
                             bytes=rows * 256 * 4, byte_offset=index * rows * 256 * 4,
                             parent='kv', storage='view_of_ACKed_published_DDR',
                             provenance='ORIGINAL_KV_ALLOCATION_VIEW', coverage='complete')
    terminal.consumed = True
    return dict(status='COMPLETE_ACTUAL_INVENTORY_NUMERIC_TEMP', numerical_status='TEMP',
                rows=rows, entries=entries, original_stages=list(STAGE_WIDTHS),
                attention_fields=list(ATTENTION_FIELDS), whole_terminal=True,
                official_node_coverage=official_coverage_plan(),
                actual_inventory_correspondence=inventory_correspondence(),
                public_completions=21, actual_owner_jobs=17, launch_results=1,
                resources_clean=True, tensor_reconstruction=False,
                reference_values_used=False, numeric_acceptance=False,
                native_acceptance=False, hardware_acceptance=False,
                fixed_physical_macs=4096, legacy_pv_upper_bound_percent=63.57,
                hardware_cycles=None, full_wall_mac_utilization=None)

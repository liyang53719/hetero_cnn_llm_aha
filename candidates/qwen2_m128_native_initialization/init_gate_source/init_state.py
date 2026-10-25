"""Read-only pre-first-PC state admission; no target import or constructor.

Only the explicitly listed native metadata/counter getters are called. Every
other target field is read from existing __dict__ storage, never report(),
ports(), done, an arithmetic method, a provider, or accumulator memory.
This snapshot is not historical proof: source-bound exclusion, input/source/
ELF identity and the independently SEALED oracle remain required separately.
"""
from array import array
from collections import Counter, deque
from functools import lru_cache
import hashlib
import json
import math

SENTINEL = bytes.fromhex('c33c96a5')
NATIVE_ZERO_GETTERS = ('matrix_state', 'matrix_ticket', 'matrix_dense_fmas', 'matrix_normal_fmas')
SILU_ZERO_GETTERS = ('sf_calls', 'sf_failures')
TILE_COUNTERS = ('read_requests', 'write_requests', 'read_responses', 'rmw_commits',
    'logical_read_bytes', 'logical_write_bytes', 'physical_read_bytes',
    'physical_write_bytes', 'aborted', 'dense_grants', 'response_stall_cycles')
DENSE_ZERO = ('clock', 'responses', 'write_bytes', 'read_sequence', 'write_sequence',
    'accepted_steps', 'rmw_commits', 'written', 'max_reserved', 'chunk_index',
    'committed_prefix_end', 'completed_prefix_sweeps', 'restored_contexts',
    'prefix_saved_contexts', 'prefix_bytes', 'group_sequence', 'seed_context',
    'seed_index', 'adapter_index', 'loaded_a_bytes', 'a_fences', 'results_received',
    'group_accepted_steps', 'drain_consumed', 'drain_started', 'drain_column',
    'write_row', 'write_row_beat', 'k_a_fences')
DENSE_NONE = ('error', 'job', 'read_active', 'a_hold', 'a_rmw_pending', 'pending',
    'final_value', 'seed_hold', 'window_request', 'lease', 'window_result',
    'drain_request', 'drain_result', 'drain_expected', 'accepted_write')
DENSE_FALSE = ('group_started', 'group_done', 'restoring', 'prefix_valid',
    'seed_outstanding', 'window_begun', 'drain_poison')
PREFIX_ZERO = ('serial', 'clock', 'start_clock', 'ack_bytes', 'tag_prefix',
    'row_words', 'peak_row_words', 'peak_copy_words', 'peak_add_words')
PREFIX_NONE = ('job', 'request', 'result', 'program', 'status', 'detail')
EXEC_NONE = ('coupled', 'down_job', 'down_terminal', 'launch_result',
    'down_terminal_tick', 'down_start_tick', 'last_host_edge', 'window_matrix_bridge',
    'attention_transport', 'attention_transport_binding', 'reduction')


def _need(ok, label):
    if not ok:
        raise ValueError('pre-first-PC state: ' + label)


def _backing(obj, label):
    try:
        value = object.__getattribute__(obj, '__dict__')
    except (AttributeError, TypeError):
        raise ValueError('pre-first-PC state: missing backing dictionary: ' + label) from None
    _need(type(value) is dict, label + ' backing dictionary')
    return value


def _field(obj, name, label):
    data = _backing(obj, label)
    _need(name in data, label + '.' + name + ' missing backing field')
    return data[name]


def _strict(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) in (list, tuple):
        return len(actual) == len(expected) and all(_strict(a,b) for a,b in zip(actual,expected))
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(_strict(actual[k],v) for k,v in expected.items())
    if type(expected) is set:
        return len(actual) == len(expected) and all(any(_strict(a,b) for b in expected) for a in actual)
    return actual == expected


def _equal(obj, name, expected, label):
    actual = _field(obj, name, label)
    _need(_strict(actual, expected), label + '.' + name)
    return actual


def _same(obj, name, expected, label):
    _need(_field(obj, name, label) is expected, label + '.' + name + ' identity')


def _zeros(obj, names, label):
    for name in names:
        _equal(obj, name, 0, label)


def _nones(obj, names, label):
    for name in names:
        _same(obj, name, None, label)


def _false(obj, names, label):
    for name in names:
        _same(obj, name, False, label)


def _empty(obj, names, label):
    for name in names:
        value = _field(obj, name, label)
        _need(type(value) in (dict, Counter, list, tuple, set, deque) and len(value) == 0,
              label + '.' + name + ' not empty')


def _primitive(value, label):
    """Copy only source-identity metadata, never arbitrary object repr/payloads."""
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float:
        _need(math.isfinite(value), label + ' nonfinite metadata')
        return value
    if type(value) is bytes:
        return {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
    if type(value) in (list, tuple):
        return [_primitive(v, label) for v in value]
    if type(value) is dict:
        _need(all(type(k) is str for k in value), label + ' metadata key')
        return {k: _primitive(v, label + '.' + k) for k, v in value.items()}
    raise ValueError('pre-first-PC state: nonprimitive source identity: ' + label)


@lru_cache(maxsize=64)
def _sentinel_sha(size):
    _need(type(size) is int and size >= 0 and size % 4 == 0, 'sentinel byte extent')
    h = hashlib.sha256()
    chunk = SENTINEL * 4096
    while size:
        count = min(size, len(chunk))
        h.update(chunk[:count])
        size -= count
    return h.hexdigest()


def _sentinel_buffer(value, size, label, *, words=False):
    if words:
        _need(type(value) is array and value.typecode == 'I' and value.itemsize == 4,
              label + ' uint32 buffer')
    else:
        _need(type(value) in (bytes, bytearray), label + ' byte buffer')
    view = memoryview(value)
    _need(view.nbytes == size, label + ' buffer length')
    actual = hashlib.sha256(view).hexdigest()
    _need(actual == _sentinel_sha(size), label + ' sentinel changed')
    return {'bytes': size, 'sha256': actual}


def _zero_buffer(value, size, label, *, frequency=False):
    if frequency:
        _need(type(value) is array and value.typecode == 'B', label + ' frequency buffer')
    else:
        _need(type(value) is bytearray, label + ' presence buffer')
    _need(len(value) == size and not any(value), label + ' observed occurrence/length')
    return {'bytes': size, 'observed': 0}


def _empty_hash(obj, name, label):
    value = _field(obj, name, label)
    empty = hashlib.sha256()
    _need(type(value) is type(empty), label + '.' + name + ' hash object')
    # Only a verified stdlib SHA256 object is queried, never a target getter.
    _need(value.hexdigest() == empty.hexdigest(), label + '.' + name + ' changed')


def _source_identity(obj, label):
    identity = _field(obj, 'identity', label)
    _need(type(identity) is dict and bool(identity), label + ' source identity absent')
    return _primitive(identity, label + '.identity')


def inspect_state(*, runtime, fixture, physical, memory, owner, service, scalar,
                  execution, silu, observation, rope, providers, after_cleanup=False):
    """Return JSON-safe exact initialized-state evidence; raise on any mismatch.

    providers is the exact admitted readonly provider dictionary, supplied by
    the worker closure. Calls neither providers nor target constructors.
    after_cleanup checks the same untouched state after normal RoPE context exit.
    """
    _need(type(after_cleanup) is bool, 'explicit cleanup phase')
    _need(type(providers) is dict and providers and
          all(type(k) is str and callable(v) for k, v in providers.items()), 'admitted providers')
    lib, selected = _field(runtime, 'library', 'runtime'), _field(runtime, 'selected', 'runtime')
    _same(selected, 'library', lib, 'selected')
    _same(service, 'lib', lib, 'service')
    _same(silu, 'selected', selected, 'silu')
    _same(physical, 'fixture', fixture, 'physical')
    _same(memory, 'physical_memory', physical, 'memory')
    _same(execution, 'owner', owner, 'execution')
    _same(execution, 'matrix_service', service, 'execution')
    _same(execution, 'policy_fixture', fixture, 'execution')
    prefix = _field(execution, 'prefix_owner', 'execution')
    attention = _field(execution, 'attention_owner', 'execution')
    _need(prefix is not attention, 'distinct prefix and attention owners')
    for obj, label in ((prefix, 'prefix'), (attention, 'attention')):
        _same(obj, 'scalar', scalar, label)
        _equal(obj, 'state', 'idle', label)
        _same(obj, 'poison', False, label)
        _nones(obj, PREFIX_NONE, label)
        _zeros(obj, PREFIX_ZERO, label)
        _empty(obj, ('counts', 'scalar_baseline', 'scalar_counts'), label)
        for key, value in (('hidden',1536), ('kv',256), ('head_dim',128), ('max_tokens',1024)):
            _equal(obj, key, value, label)
    _same(attention, 'matrix', service, 'attention')
    _nones(attention, ('matrix_client', 'matrix_request', 'packed_schedule', 'scratch_request',
        'scratch_write_tag', 'scratch_last', 'packed_memory_tag', 'ordered_work', 'ordered_adapter'), 'attention')
    _false(attention, ('memory_pending', 'abort_pending', 'scratch_pending', 'scratch_leased'), 'attention')
    _zeros(attention, ('fma_baseline', 'useful_macs', 'executed_macs',
        'peak_score_words', 'peak_probability_words'), 'attention')
    _empty(attention, ('matrix_baseline', 'matrix_counts'), 'attention')
    _same(scalar, 'client', None, 'scalar')
    _empty(scalar, ('calls',), 'scalar')
    _nones(service, ('owner', 'mode', 'owner_tag', 'group', 'result', '_done', '_dense'), 'service')
    _zeros(service, ('epoch',), 'service')
    _same(service, '_owner_retired', False, 'service')
    _empty(service, ('counts', '_bindings'), 'service')
    _same(service, 'profile', _field(_field(runtime, 'profiles', 'runtime'), 'QWEN2_QKV_PROFILE', 'profiles'), 'service')

    # Direct inherited owner fields; do not ask ports(), idle, or leased.
    _equal(owner, 'state', 'idle', 'owner')
    _zeros(owner, DENSE_ZERO, 'owner')
    _nones(owner, DENSE_NONE, 'owner')
    _false(owner, DENSE_FALSE, 'owner')
    _empty(owner, ('fifo', 'seed_acked'), 'owner')
    _equal(owner, 'ready', [False, False], 'owner')
    _equal(owner, 'ready_k', [None, None], 'owner')
    for field in ('write_state', 'seed_state', 'adapter_phase', 'drain_phase'):
        _equal(owner, field, 'idle', 'owner')
    for field in ('enable_dense_drain', 'enable_k_window', 'enable_ffn_window', 'enable_ffn_tiles', 'enable_ffn_drain'):
        _same(owner, field, True, 'owner')
    _equal(owner, 'traffic', dict(a_read_bytes=0, b_read_bytes=0, windows=0), 'owner')
    banks = [_field(owner, name, 'owner') for name in ('a_banks', 'b_banks')]
    _need(banks[0] is not banks[1], 'distinct original A/B banks')
    for bank, depth, name in zip(banks, (1376,160), ('a_banks','b_banks')):
        _equal(bank, 'depth', depth, name)
        _empty(bank, ('reads', 'writes'), name)
        words = _field(bank, 'words', name)
        _need(type(words) is list and len(words) == 16 and
              all(type(lane) is list and len(lane) == depth for lane in words), name + ' physical dimensions')
        # Do not inspect bank operand values: only dimensions and port debts.
    tiles = _field(owner, 'tiles', 'owner')
    _same(tiles, 'banks', banks[0], 'tiles')
    _same(tiles, 'poison', False, 'tiles')
    _nones(tiles, ('reason', 'pending', 'response'), 'tiles')
    _zeros(tiles, ('cycle',), 'tiles')
    _equal(tiles, 'counters', dict.fromkeys(TILE_COUNTERS, 0), 'tiles')
    tags = _field(tiles, 'tags', 'tiles')
    _need(type(tags) is list and len(tags) == 3, 'tiles tags')
    for i, tag in enumerate(tags):
        label = 'tiles.tag' + str(i)
        _zeros(tag, ('identity', 'ng', 'rows', 'cols', 'produced', 'consumed'), label)
        _false(tag, ('live', 'sealed'), label)

    _empty(execution, ('counts', 'completions', 'requests', 'ordinary_history', 'policy_jobs', 'reduction_reports'), 'execution')
    _false(execution, ('completion_ready', 'result_ready'), 'execution')
    _nones(execution, EXEC_NONE, 'execution')
    _zeros(execution, ('prefix_jobs', 'prefix_results', 'attention_jobs', 'attention_results'), 'execution')
    _equal(execution, 'bank_ids', (id(owner), id(banks[0]), id(banks[1]), id(banks[0])), 'execution')
    host = _field(execution, 'host', 'execution')
    frontend = _field(execution, 'frontend', 'execution')
    _equal(host, 'state', 'decode', 'host')
    _same(host, 'poison', False, 'host')
    _zeros(host, ('pc', 'completed', 'jobs', 'useful', 'executed', 'written', 'completion_index'), 'host')
    _equal(host, 'events', {0}, 'host')
    _empty(host, ('published', 'virtual', 'group_commands', 'policies'), 'host')
    _nones(host, ('result', 'group', 'scanner', 'bound', 'status', 'reason'), 'host')
    _same(host, 'frontend', frontend, 'host')
    _equal(host, 'program', range(21), 'host')
    current = _field(host, 'current_command', 'host')
    _zeros(current, ('opcode', 'engine', 'wait', 'signal', 'reserved'), 'host.current_command')
    for name in ('a', 'b', 'd'):
        _equal(current, name, 0xffffff, 'host.current_command')
    _same(host, 'reader', _field(frontend, 'reader', 'frontend'), 'host')
    _same(host, 'enabled', True, 'host')
    _same(host, 'legacy_prefix', True, 'host')
    _same(host, 'legacy_attention', True, 'host')
    _equal(host, 'profile', 'legacy_qwen2', 'host')
    _equal(host, 'max_commands', 64, 'host')
    _equal(host, 'event_slots', 256, 'host')
    _equal(host, 'max_tokens', 1024, 'host')
    _empty(frontend, ('command_reads', 'policy_reads'), 'frontend')
    _zeros(frontend, ('current_pc',), 'frontend')
    config = _field(fixture, 'config', 'fixture')
    frontconfig = _field(frontend, 'config', 'frontend')
    epoch = _field(config, 'epoch', 'config')
    _equal(host, 'epoch', epoch, 'host')
    _equal(frontconfig, 'epoch', epoch, 'frontend.config')
    _same(frontconfig, 'transposed_down', True, 'frontend.config')
    _same(config, 'transposed_down', True, 'config')
    for name in ('command', 'descriptor'):
        _same(frontconfig, name, _field(config, name, 'config'), 'frontend.config')
    regions = _field(config, 'regions', 'config')
    frontregions = _field(frontconfig, 'regions', 'frontend.config')
    _need(type(regions) is tuple and len(regions) == 4 and type(frontregions) is tuple and
          len(frontregions) == 4 and all(a is b for a,b in zip(regions,frontregions)), 'configuration region identities')
    _equal(_field(owner, 'workspace', 'owner'), 'base', _field(regions[3], 'base', 'reservation'), 'owner.workspace')
    _equal(_field(owner, 'workspace', 'owner'), 'extent', _field(regions[3], 'limit', 'reservation') - _field(regions[3], 'base', 'reservation'), 'owner.workspace')
    _equal(_field(owner, 'workspace', 'owner'), 'generation', epoch + 1, 'owner.workspace')
    _equal(_field(owner, 'workspace', 'owner'), 'split_k', 2560, 'owner.workspace')
    port = _field(frontend, 'port', 'frontend')
    meta = _field(frontend, 'memory', 'frontend')
    _same(meta, 'physical_memory', physical, 'metadata_port')
    _same(port, 'memory', meta, 'record_port')
    _empty(port, ('trace',), 'record_port')
    _nones(port, ('response_filter', 'result_filter'), 'record_port')
    machine = _field(port, 'machine', 'record_port')
    _equal(machine, 'state', 'idle', 'record_reader')
    _same(machine, 'poison', False, 'record_reader')
    _zeros(machine, ('serial', 'address', 'slot'), 'record_reader')
    _same(machine, 'result', None, 'record_reader')
    reader = _field(frontend, 'reader', 'frontend')
    _same(reader, 'port', port, 'typed_reader')
    _same(reader, 'config', frontconfig, 'typed_reader')
    _empty(reader, ('reads',), 'typed_reader')
    fixture_memory = _field(fixture, 'memory', 'fixture')
    _empty(fixture_memory, ('reads',), 'fixture.memory')
    _same(fixture_memory, 'before_read', None, 'fixture.memory')
    _equal(fixture, 'scope', 'QWEN2_21_METADATA_ONLY', 'fixture')
    _equal(_field(config, 'command', 'config'), 'count', 21, 'command_table')
    _equal(reader, 'descriptor_count', _field(_field(config, 'descriptor', 'config'), 'count', 'descriptor_table'), 'typed_reader')

    _same(physical, 'pending', None, 'physical')
    _empty(physical, ('counts', 'read_regions', 'published_hashes'), 'physical')
    pregions = _field(physical, 'regions', 'physical')
    allocations = _field(fixture, 'allocations', 'fixture')
    _need(type(pregions) is dict and type(allocations) is dict and
          set(pregions) == set(allocations) | {'workspace', 'command_table', 'descriptor_table'}, 'physical region coverage')
    _need(set(providers) == {name for name,a in allocations.items() if _field(a,'readonly','allocation') is True}, 'provider allocation coverage')
    region_evidence = {}
    for name, r in pregions.items():
        _need(type(r) is dict, 'physical region dictionary ' + name)
        if name in ('command_table', 'descriptor_table'):
            _need(r['readonly'] is True and r['virtual'] is False and callable(r['provider']), name + ' metadata source')
            # Metadata-only regions intentionally have no data/written/acked fields.
            continue
        for key in ('written', 'acked'):
            _need(type(r[key]) is set and not r[key], name + '.' + key)
        _need(type(r['records']) is list and not r['records'] and r['terminal'] is False and r['published'] is False,
              name + ' write/publication debts')
        if name in allocations:
            a = allocations[name]
            shape = _field(a, 'shape', 'allocation.' + name)
            dtype = _field(a, 'dtype', 'allocation.' + name)
            size = (math.prod(shape) * (2 if dtype == 5 else 4) + 63) // 64 * 64
            for key, value in (('base', _field(a,'address','allocation')), ('extent',size),
                    ('reserved', _field(a,'reserved_bytes','allocation')), ('dtype',dtype),
                    ('readonly',_field(a,'readonly','allocation')), ('virtual',_field(a,'virtual','allocation'))):
                _need(type(r[key]) is type(value) and r[key] == value, name + '.' + key)
        if r['readonly']:
            _need(r['provider'] is providers[name] and r['data'] is None, name + ' admitted provider identity')
            region_evidence[name] = {'provider_object_id': id(r['provider']), 'read_bytes': 0}
        else:
            _need(r['provider'] is None, name + ' unexpected provider')
            region_evidence[name] = _sentinel_buffer(r['data'], r['extent'] + 128, name)
    act = _field(memory, 'act', 'memory')
    _same(act, 'physical_memory', physical, 'act')
    _equal(act, 'name', 'act', 'act')
    _same(act, 'data', pregions['act']['data'], 'act')
    _zeros(act, ('descriptors', 'acks'), 'act')
    _same(act, 'last_tag', None, 'act')
    _sentinel_buffer(_field(act,'initial','act'), pregions['act']['extent'] + 128, 'act.initial')
    workspace = _field(memory, 'workspace', 'memory')
    _same(workspace, 'physical_memory', physical, 'workspace')
    _same(workspace, 'region', pregions['workspace'], 'workspace')
    _need(pregions['workspace']['workspace_transport'] is workspace, 'workspace transport identity')
    _same(workspace, 'data', pregions['workspace']['data'], 'workspace')
    _nones(workspace, ('job', 'reservation', 'view', 'group', 'invalidated', 'pending_read'), 'workspace')
    _same(workspace, 'finished', False, 'workspace')
    _empty(workspace, ('seeds', 'seed_commits', 'versions', 'data_versions', 'read_versions', 'seed_versions', 'counts'), 'workspace')
    _equal(workspace, 'epoch', epoch, 'workspace')
    for name, value in (('base', _field(regions[3], 'base', 'reservation')),
                        ('extent', _field(regions[3], 'limit', 'reservation') - _field(regions[3], 'base', 'reservation'))):
        _equal(workspace, name, value, 'workspace')
        _need(type(pregions['workspace'][name]) is int and pregions['workspace'][name] == value, 'workspace region ' + name)
    _need(pregions['workspace']['reserved'] == pregions['workspace']['extent'] and
          pregions['workspace']['readonly'] is False and pregions['workspace']['virtual'] is False and
          pregions['workspace']['dtype'] == 7, 'workspace physical geometry')
    for name in ('base', 'extent'):
        _equal(act, name, pregions['act'][name], 'act')
    _equal(act, 'rows', _field(allocations['act'], 'shape', 'allocation.act')[0], 'act')
    _equal(act, 'width', _field(allocations['act'], 'shape', 'allocation.act')[-1], 'act')
    virtual_hashes = _field(memory, 'virtual_hashes', 'memory')
    _need(type(virtual_hashes) is dict and set(virtual_hashes) == {'gate','up'} and
          all(virtual_hashes[name] == region_evidence[name]['sha256'] for name in virtual_hashes), 'virtual sentinel identity')
    _equal(memory, 'spans', [(r['base'], r['base']+r['reserved'], name) for name,r in pregions.items()], 'memory')
    trace = _field(execution, 'trace', 'execution')
    _same(trace, 'stream', None, 'trace')
    _zeros(trace, ('total', 'saved', 'records'), 'trace')
    _same(trace, 'truncated', False, 'trace')
    _empty_hash(trace, 'digest', 'trace')

    _equal(silu, 'rows', 128, 'silu')
    _zeros(silu, ('calls',), 'silu')
    silu_evidence = {name: _sentinel_buffer(_field(silu,name,'silu'),128*8960*4,'silu.'+name,words=True)
                     for name in ('silu','product')}
    silu_evidence['observed'] = _zero_buffer(_field(silu,'observed','silu'),128*8960,'silu.observed')
    _need(type(observation) is dict and type(observation.get('invocations')) is int and observation['invocations'] == 0,
          'attention observation invocations')
    for key in ('capture', 'capture_report', 'capture_error', 'service_events', 'service_events_raw', 'service_error'):
        _need(key in observation and observation[key] is None, 'attention observation ' + key)
    _need('service_events_raw_error' not in observation, 'unexpected raw service error')
    _same(rope, 'owner', prefix, 'rope')
    _same(rope, 'fixture', fixture, 'rope')
    _same(rope, 'physical', physical, 'rope')
    _equal(rope, 'rows', 128, 'rope')
    _same(rope, 'error', None, 'rope')
    _same(rope, 'sealed', False, 'rope')
    data = _field(rope, 'data', 'rope')
    _equal(data, 'rows', 128, 'rope.data')
    _zeros(data, ('cursor',), 'rope.data')
    _same(data, 'finished', False, 'rope.data')
    _empty_hash(data, 'events', 'rope.data')
    values, frequency = _field(data,'values','rope.data'), _field(data,'frequency','rope.data')
    _need(type(values) is dict and type(frequency) is dict and set(values) == set(frequency) == {'cos','sin'}, 'RoPE buffer fields')
    rope_evidence = {}
    for name in ('cos','sin'):
        rope_evidence[name] = _sentinel_buffer(values[name],128*64*4,'rope.'+name,words=True)
        rope_evidence[name]['frequency'] = _zero_buffer(frequency[name],128*64,'rope.frequency.'+name,frequency=True)
    probe = _field(rope, 'probe', 'rope')
    bindings = _field(rope, 'bindings', 'rope')
    _need(type(bindings) is dict and set(bindings) == {'rope','op','read'}, 'RoPE binding keys')
    _same(probe, 'code', bindings['rope'], 'probe')
    capture_line = _field(rope, 'line', 'rope')
    _need(type(capture_line) is int and capture_line > 0, 'RoPE capture line')
    _equal(probe, 'line', capture_line, 'probe')
    _same(probe, 'started', True, 'probe')
    _same(probe, 'error', None, 'probe')
    _empty(probe, ('cleanup_errors',), 'probe')
    _same(probe, 'residual_tool', None, 'probe')
    _same(probe, 'registration_replaced', False, 'probe')
    _same(probe, '_stale_callback_restored', False, 'probe')
    _same(probe, '_callback_attempted', True, 'probe')
    _same(probe, '_local_attempted', True, 'probe')
    for name, expected in (('closed',after_cleanup), ('cleanup_complete',after_cleanup),
        ('_cleanup_attempted',after_cleanup), ('_disarmed',after_cleanup),
        ('_callback_registered',not after_cleanup), ('_local_configured',not after_cleanup)):
        _same(probe, name, expected, 'probe')
    tool = _field(probe, 'tool', 'probe')
    _need(tool is None if after_cleanup else type(tool) is int and tool in (3,4), 'probe owned monitoring tool')

    native = {}
    for name in NATIVE_ZERO_GETTERS:
        getter = _field(lib, name, 'native_library')
        _need(callable(getter), 'native readonly getter ' + name)
        value = getter()
        _need(type(value) is int and value == 0, 'native.' + name)
        native[name] = value
    for name in SILU_ZERO_GETTERS:
        getter = _field(selected, name, 'selected')
        _need(callable(getter), 'SiLU readonly getter ' + name)
        value = getter()
        _need(type(value) is int and value == 0, 'native.' + name)
        native[name] = value
    for name in ('matrix_accumulator_address', 'matrix_accumulator_bytes'):
        getter = _field(lib,name,'native_library')
        _need(callable(getter), 'native readonly getter ' + name)
        native[name] = getter()
        _need(type(native[name]) is int, 'native metadata type ' + name)
    _need(native['matrix_accumulator_address'] > 0 and
          native['matrix_accumulator_address'] == _field(service,'resource_address','service') and
          native['matrix_accumulator_bytes'] == 81920, 'same single physical accumulator metadata')
    result = {'status':'PASS_PRE_FIRST_PC_STATE_ONLY', 'after_cleanup':after_cleanup,
        'scope':'snapshot; not universal historical proof or numerical/hardware acceptance',
        'host':dict(state='decode',pc=0,completed=0,jobs=0,useful=0,executed=0,written=0,events=[0]),
        'native':native,
        'owner':{name:0 for name in DENSE_ZERO},
        'prefix':{name:0 for name in PREFIX_ZERO},
        'attention':dict(useful_macs=0,executed_macs=0,matrix_counts={},scalar_counts={}),
        'service':dict(owner=None,result=None,_done=None,epoch=0,counts={},bindings={}),
        'workspace':dict(finished=False,counts={},seeds=0,versions=0,pending_read=None),
        'trace':dict(total=0,saved=0,records=0),
        'scalar_source_identity':_source_identity(scalar,'scalar'),
        'matrix_source_identity':_source_identity(service,'service'),
        'physical_regions':region_evidence, 'silu':silu_evidence, 'rope':rope_evidence,
        'monitor':dict(started=True,closed=after_cleanup,cleanup_complete=after_cleanup,tool=tool,residual_tool=None),
        'shared_object_ids':dict(fixture=id(fixture),physical=id(physical),owner=id(owner),
            service=id(service),scalar=id(scalar),library=id(lib),selected=id(selected),
            a_banks=id(banks[0]),b_banks=id(banks[1])),
        'task_provider_calls_by_verifier':0,'accumulator_contents_read':False,
        'numeric_comparison_performed':False,'hardware_acceptance':False}
    json.dumps(result,allow_nan=False)
    return result

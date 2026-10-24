"""Parent-only, source-only structural check of one newly sealed success M16.

The caller pins and supplies the original r3/representation decoder classes and
explicit codec limits. Nothing imports a DUT, native library, or numeric oracle.
No pair comparison, identity normalization, execution admission, or file writes.
A result exists only after both original decoders reach their genuine EOF seals.
"""
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
from math import prod
import os
from pathlib import Path
import stat
import struct

M = 16
QBASE, KBASE, VBASE, OBASE = 0x100000, 0x200000, 0x300000, 0x400000
OUTPUT_BYTES = M * 1536 * 4
READS, WRITES, ACKS = 27648, 1536, 1536
SENTINEL = 0xa5963cc3
TRANSPORT_CAP = 32 * 1024 * 1024
FIELD_SHAPES = {n: (12, M, M) for n in (
    'dot_raw', 'dot_bf16', 'scale_fp32', 'score_bf16',
    'score_difference', 'exp_fp32', 'denominator_step')}
FIELD_SHAPES.update({n: (12, M, M, 16) for n in ('packed_stripes', 'fold_before', 'fold_after')})
FIELD_SHAPES.update({n: (12, M, M, 8) for n in ('probability_fp32', 'probability_bf16')})
FIELD_SHAPES.update(pv_key_raw=(12, M, M, 8, 16), normalizer=(12, M, 3),
                    pv_final_raw=(12, M, 128), pv_bf16=(12, M, 128))
MATRIX_ANCHORS = frozenset('matrix_' + n for n in (
    'acquire', 'accept_group', 'accept_step', 'retire_result', 'retire_done',
    'retire_legacy_reply', 'retire_owner_response', 'release'))
LIMIT_KEYS = frozenset(('contexts', 'bank_bytes', 'max_chunk', 'max_metadata',
                        'max_record', 'max_records', 'max_output', 'max_raw'))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def _pairs(items):
    value = {}
    for key, item in items:
        need(key not in value, 'duplicate JSON key')
        value[key] = item
    return value


def _bad_constant(value):
    raise ValueError('nonfinite JSON constant: ' + value)


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_bad_constant)


def _uint(value, bits=64):
    return type(value) is int and 0 <= value < 1 << bits


def _signature(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
            s.st_mtime_ns, s.st_ctime_ns)


class _HashReader:
    """Sequential bounded reads; the original decoder consumes this same FD."""
    def __init__(self, stream, size):
        self.stream, self.size = stream, size
        self.used, self.eof = 0, False
        self.digest = hashlib.sha256()

    def read(self, n):
        need(type(n) is int and 0 <= n <= 69720, 'bounded read required')
        if n == 0:
            return b''  # Decoder control records may request a zero-length payload; this is not EOF.
        need(self.used <= self.size, 'read exceeds admitted extent')
        raw = self.stream.read(min(n, self.size - self.used + 1))
        need(type(raw) is bytes and self.used + len(raw) <= self.size,
             'artifact grew beyond admitted extent')
        self.used += len(raw)
        self.digest.update(raw)
        if raw == b'':
            self.eof = True
        return raw

    def identity(self):
        need(self.used == self.size and self.eof, 'artifact not consumed through real EOF')
        return dict(bytes=self.used, sha256=self.digest.hexdigest())


@contextmanager
def _owned(root, relative, cap, exact=None):
    relative = Path(relative)
    need(not relative.is_absolute() and '..' not in relative.parts, 'owned relative artifact')
    path = root / relative
    need(path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)),
         'aliased artifact path: ' + str(relative))
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= cap and
         (exact is None or before.st_size == exact), 'artifact type/cap/extent: ' + str(relative))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        need(_signature(before) == _signature(opened), 'artifact changed while opening')
        reader = _HashReader(stream, opened.st_size)
        yield reader
        reader.identity()
        need(_signature(opened) == _signature(os.fstat(stream.fileno())) ==
             _signature(path.lstat()), 'artifact changed during check: ' + str(relative))


def _read_file(root, relative, cap, identities, exact=None):
    with _owned(root, relative, cap, exact) as f:
        parts = []
        while True:
            raw = f.read(65536)
            if not raw:
                break
            parts.append(raw)
        value = b''.join(parts)
        identities[relative] = f.identity()
    return value


def _policy(Limits, limits):
    need(type(limits) is dict and set(limits) == LIMIT_KEYS and
         all(type(v) is int and v > 0 for v in limits.values()), 'explicit finite codec limits')
    return Limits(**limits).validate()


def _count_map(value, label):
    need(type(value) is dict and len(value) <= 128 and
         all(type(k) is str and 1 <= len(k) <= 96 and _uint(v) for k, v in value.items()), label)
    return value


def _schedule():
    """Literal owner source loop order, addresses only, no arithmetic model."""
    for token in range(M):
        for head in range(12):
            kv_head = head // 6
            for depth in range(0, 128, 16):
                yield False, QBASE + (token * 1536 + head * 128 + depth) * 4
            for key_base in range(0, token + 1, 16):
                for depth in range(0, 128, 16):
                    for selected in range(min(16, token + 1 - key_base)):
                        yield False, KBASE + ((key_base + selected) * 256 + kv_head * 128 + depth) * 4
            for col in range(0, 128, 16):
                for key in range(token + 1):
                    yield False, VBASE + (key * 256 + kv_head * 128 + col) * 4
                yield True, OBASE + (token * 1536 + head * 128 + col) * 4


def _transport(value, summary, output):
    need(type(value) is dict and all(type(value.get(k)) is int and value[k] == n for k, n in
         (('reads', READS), ('writes', WRITES), ('write_acks', ACKS))), 'M16 transport exact totals')
    need(value['terminal'] == summary['terminal'], 'transport/attention terminal mismatch')
    rows = value['transactions']
    need(type(rows) is list and len(rows) == READS + WRITES, 'M16 transaction extent')
    expected, last_tick, writes = _schedule(), -1, 0
    for index, row in enumerate(rows):
        need(type(row) is dict, 'transport packet object')
        write, address = next(expected)
        keys = {'index', 'tick', 'tag', 'address', 'write', 'mask',
                'data_hex' if write else 'response_words'}
        need(set(row) == keys and type(row['write']) is bool and row['write'] is write and
             row['address'] == address and _uint(row['address']) and
             _uint(row['index']) and row['index'] == index and
             _uint(row['tag']) and row['tag'] == ((summary['job']['tag'] >> 16) << 32) | index and
             _uint(row['tick']) and row['tick'] > last_tick,
             'transport exact sequence/tag/address/order')
        last_tick = row['tick']
        need(_uint(row['mask']) and row['mask'] == ((1 << 64) - 1 if write else 0),
             'transport mask')
        if write:
            off = address - OBASE
            raw = output[off:off + 64]
            need(type(row['data_hex']) is str and row['data_hex'] == raw.hex() and len(raw) == 64,
                 'transport packet/output bytes mismatch')
            writes += 1
        else:
            words = row['response_words']
            need(type(words) is list and len(words) == 16 and all(_uint(w, 32) for w in words),
                 'transport returned input words schema')
    need(next(expected, None) is None and writes == WRITES, 'complete source address schedule')
    need(_uint(value['ticks']) and value['ticks'] > last_tick, 'transport final tick bound')
    controls = value['controls']
    need(type(controls) is list and len(controls) == 8 and
         Counter(x['kind'] for x in controls) == {'last_ack_held': 4, 'owner_response_held': 4},
         'four ACK and four terminal hold observations')
    return rows


def _fields(root, summary, output, identities):
    need(type(summary['fields']) is dict and set(summary['fields']) == set(FIELD_SHAPES),
         'exact sixteen-field inventory')
    for name, shape in FIELD_SHAPES.items():
        report, words = summary['fields'][name], prod(shape)
        need(report['shape'] == list(shape) and type(report['total_words']) is int and
             report['total_words'] == words, 'fixed M16 shape/word extent: ' + name)
        raw_path, presence_path = 'attention/' + name + '.u32le', 'attention/' + name + '.presence'
        stride, observed, index = prod(shape[3:]), 0, 0
        repeated = None
        with _owned(root, raw_path, words * 4, words * 4) as data, \
             _owned(root, presence_path, words, words) as presence:
            while index < words:
                n = min(16384, words - index)
                raw, seen = data.read(n * 4), presence.read(n)
                need(len(raw) == n * 4 and len(seen) == n, 'field truncated')
                for local, (word,) in enumerate(struct.iter_unpack('<I', raw)):
                    i = index + local
                    expected = 1 if name in ('normalizer', 'pv_final_raw', 'pv_bf16') else \
                        int((i // stride) % M <= (i // stride // M) % M)
                    need(seen[local] == expected and (expected or word == SENTINEL),
                         'presence/noncausal sentinel mismatch: ' + name)
                    observed += expected
                    if name in ('probability_fp32', 'probability_bf16'):
                        if i % 8 == 0:
                            repeated = word
                        need(word == repeated, 'eight observed probability uses differ: ' + name)
                    if name == 'pv_bf16':
                        head, remainder = divmod(i, M * 128)
                        token, col = divmod(remainder, 128)
                        off = (token * 1536 + head * 128 + col) * 4
                        need(output[off:off + 4] == struct.pack('<I', word),
                             'observed pv_bf16/accepted output bytes mismatch')
                index += n
            need(data.read(1) == presence.read(1) == b'', 'field trailing bytes')
            identities[raw_path], identities[presence_path] = data.identity(), presence.identity()
        need(identities[raw_path]['sha256'] == report['raw_sha256'] and
             identities[presence_path]['sha256'] == report['frequency_sha256'] and
             type(report['observed_words']) is int and report['observed_words'] == observed,
             'field/presence summary hash/count mismatch: ' + name)


def _event_value(raw):
    need(type(raw) is bytes and len(raw) <= 16384, 'attention event byte cap')
    value = _json(raw)
    need(type(value) is dict and len(value) <= 64 and canonical(value) == raw,
         'noncanonical attention event')
    for key, item in value.items():
        need(type(key) is str and 0 < len(key) <= 74, 'attention event key')
        if key.endswith('_bytes_hex'):
            need(type(item) is str and len(item) <= 2048 and len(item) % 2 == 0 and
                 bytes.fromhex(item).hex() == item, 'canonical event byte string')
        elif type(item) is list:
            need(len(item) <= 256 and all(_uint(x, 32) for x in item), 'event word vector')
        else:
            need(item is None or type(item) is bool or
                 (type(item) is int and -(1 << 63) <= item < 1 << 64) or
                 (type(item) is str and len(item) <= 512), 'flat event scalar')
    return value


def _sealed(decoder, reader, expected, records):
    need(decoder.seal is not None and asdict(decoder.seal) == expected and
         decoder.seal.records == records and decoder.seal.encoded_bytes == reader.size,
         'genuine decoder EOF/external seal/count/extent mismatch')
    return reader.identity()


def _attention(root, summary, rows, *, Decoder, policy, decode_exp, identities):
    count, tick, accepted, acks = 0, -1, 0, 0
    counts, payload = Counter(), hashlib.sha256()
    pending = ack_pending = None
    relative = 'attention/attention-events.lec1'
    with _owned(root, relative, policy.max_output) as f:
        decoder = Decoder(f, policy)
        for record in decoder.records():
            need(count < policy.max_records and record.ordinal == count and record.kind == 8,
                 'attention record budget/ordinal/kind')
            meta = record.metadata
            need(type(meta) is dict and set(meta) == {'schema', 'sequence', 'kind'} and
                 type(meta['sequence']) is int and meta['sequence'] == count and
                 type(meta['kind']) is str and 1 <= len(meta['kind']) <= 64, 'attention outer metadata')
            if meta['schema'] == 'fixed93-attention-exp-envelope-v1':
                value, raw = decode_exp(record.data, meta)
                need(0 <= value['head'] < 12 and 0 <= value['key'] <= value['token'] < M,
                     'exp causal coordinate')
                encoded = canonical(value)
                payload.update(len(encoded).to_bytes(4, 'little')); payload.update(encoded)
                payload.update(len(raw).to_bytes(4, 'little')); payload.update(raw)
                counts['exp_actual_primitives'] += value['node_count']
            else:
                need(meta['schema'] == 'fixed93-attention-event-v2', 'attention schema')
                value = _event_value(record.data)
                payload.update(len(record.data).to_bytes(4, 'little')); payload.update(record.data)
            need(value['sequence'] == count and value['kind'] == meta['kind'] and
                 _uint(value['tick']) and value['tick'] >= tick, 'attention sequence/kind/tick')
            tick = value['tick']
            kind = meta['kind']
            counts[kind] += 1
            need(len(counts) <= 128, 'attention count-map bound')
            need(kind not in ('owner_fault', 'matrix_abort', 'matrix_reset', 'observed_exception'),
                 'fault/exception/reset in successful attention stream')
            if kind in ('matrix_accept_group', 'matrix_accept_step') and value['accepted'] is True:
                counts['accepted_matrix_groups' if kind.endswith('group') else 'accepted_matrix_steps'] += 1
            if kind == 'job_accepted':
                need({k[4:]: v for k, v in value.items() if k.startswith('job_') and k != 'job_object'} ==
                     summary['job'], 'accepted job/summary mismatch')
            elif kind == 'owner_terminal_accepted':
                need({k: v for k, v in value.items() if k not in ('sequence', 'kind', 'tick')} ==
                     summary['terminal'], 'accepted terminal/summary mismatch')
            elif kind in ('memory_read_accepted', 'memory_write_accepted'):
                need(pending is None and ack_pending is None and accepted < len(rows), 'memory outstanding debt')
                pending = rows[accepted]
                need(all(value[k] == pending[k] and type(value[k]) is type(pending[k])
                         for k in ('tag', 'address', 'write', 'mask')) and
                     (kind == 'memory_write_accepted') is pending['write'], 'attention/transport request mismatch')
                need(value.get('data_bytes_hex') == pending['data_hex'] if pending['write'] else
                     value.get('data') is None and 'data_bytes_hex' not in value,
                     'attention/transport write payload mismatch')
                accepted += 1
            elif kind in ('read_response', 'write_response'):
                need(pending is not None and value['tag'] == pending['tag'] and
                     value['address'] == pending['address'] and (kind == 'write_response') is pending['write'] and
                     value['error'] is False and value['nbytes'] == 64 and value['ack_bytes'] == acks * 64,
                     'attention response identity/width/ACK position')
                if pending['write']:
                    need(value.get('data') is None, 'write response carries data')
                    ack_pending = pending
                else:
                    need(value.get('data') == pending['response_words'], 'accepted read response/transport words')
                pending = None
            elif kind == 'write_ack':
                need(ack_pending is not None and value['tag'] == ack_pending['tag'] and
                     value['address'] == ack_pending['address'] and value['error'] is False and
                     value['nbytes'] == 64 and value['ack_bytes'] == (acks + 1) * 64, 'write ACK debt/extent')
                ack_pending = None
                acks += 1
            count += 1
        identities[relative] = _sealed(decoder, f, summary['event_codec_seal'], count)
    need(pending is None and ack_pending is None and accepted == len(rows) and acks == ACKS,
         'attention terminal memory debt/coverage')
    need(count == summary['event_count'] and dict(counts) == _count_map(summary['event_counts'], 'event counts') and
         payload.hexdigest() == summary['event_payload_sha256'], 'attention logical count/digest mismatch')
    causal, groups = 12 * M * (M + 1) // 2, 12 * M
    expected = {k: 8 * causal for k in ('pv_probability_fp32_use', 'pv_bf16_input',
                'pv_selected16_finite_check', 'pv_selected16_finite_pass')}
    expected.update({k: causal for k in ('pv_normalize', 'qk_selected16_finite_check',
                     'qk_selected16_finite_pass', 'score_finite_commit', 'exp_nodes')})
    expected.update({k: WRITES for k in ('store_finite_check', 'store_finite_pass',
                     'memory_write_accepted', 'write_ack', 'write_response')})
    expected.update(memory_read_accepted=READS, read_response=READS, job_accepted=1,
                    owner_finish_called=1, owner_terminal_accepted=1, matrix_release=1,
                    accepted_matrix_groups=groups + WRITES, accepted_matrix_steps=groups * 8 + 8 * causal,
                    matrix_retire_result=groups + 8 * causal, matrix_retire_done=groups + WRITES,
                    matrix_retire_legacy_reply=8 * causal)
    need(all(counts[k] == n for k, n in expected.items()), 'source M16 attention coverage counts')
    return dict(records=count, event_counts=dict(counts), payload_sha256=payload.hexdigest())


def _whole(root, report, attention, *, Decoder, policy, TokenDecoder, OperandDecoder, identities):
    count, logical, semantic = 0, 0, 0
    counts, token, operands = Counter(), TokenDecoder(), OperandDecoder()
    relative = 'wholeblock_events.lec1'
    with _owned(root, relative, policy.max_output) as f:
        decoder = Decoder(f, policy)
        for record in decoder.records():
            need(count < policy.max_records and record.ordinal == count, 'whole record budget/ordinal')
            count += 1
            row = token.feed(record)
            if row is None:
                continue
            logical += 1
            need(logical <= policy.max_records, 'whole logical record budget')
            original_metadata, meta, raw = row
            need(canonical(meta) == original_metadata, 'whole original metadata canonical form')
            domain = meta['domain']
            need(domain in ('operand_definition', 'semantic'), 'non-M16 wholeblock domain')
            counts['records_' + domain] += 1
            if domain == 'operand_definition':
                need(meta['source_domain'] == 'normal_step' and meta['anchor'] == 'matrix_accept_step',
                     'unexpected M16 operand definition source')
                operands.definition(raw, meta)
            else:
                value = operands.semantic(raw, meta)
                anchor = meta['anchor']
                need(anchor in MATRIX_ANCHORS and 'exception_type' not in value, 'non-success M16 semantic anchor')
                semantic += 1
                counts['semantic_events'] += 1
                counts['anchor_' + anchor] += 1
                if anchor == 'matrix_accept_step':
                    counts['normal_steps'] += 1
                    counts['normal_emits'] += value.get('rc') == 1
                elif anchor == 'matrix_accept_group':
                    counts['normal_groups'] += 1
        identities[relative] = _sealed(decoder, f, report['wholeblock']['codec_seal'], count)
        need(token.finish(decoder.seal) == logical, 'whole logical count/finish')
        operands.finish(semantic)
    need(identities[relative] == report['wholeblock']['artifact'], 'whole sealed artifact identity')
    need(dict(counts) == _count_map(report['wholeblock']['counts'], 'whole count map'),
         'whole decoded source counts mismatch')
    a = attention['event_counts']
    need(counts['normal_steps'] == a['accepted_matrix_steps'] and
         counts['normal_groups'] == a['accepted_matrix_groups'] and
         counts['normal_emits'] == a['matrix_retire_result'], 'whole/attention accepted matrix totals')
    for anchor in MATRIX_ANCHORS - {'matrix_accept_group', 'matrix_accept_step'}:
        need(counts['anchor_' + anchor] == a.get(anchor, 0), 'whole/attention anchor count: ' + anchor)
    return dict(records=count, logical_records=logical, semantic_records=semantic, counts=dict(counts))


def check_m16(case, *, Decoder, Limits, decode_exp, TokenDecoder, OperandDecoder,
              attention_limits, whole_limits):
    """Read-only check; caller supplies original pinned classes and codec dicts.

    Raises on any failed check. The caller owns codec/source pin verification and
    independent admission of this exact fresh case. This function grants none.
    Report/summary/transport JSON use fixed 256 KiB/1 MiB/32 MiB caps. Only the
    98,304-byte output and bounded transport JSON are retained; r3 records are
    processed one at a time. FD stat stability is checked before/after each read.
    """
    root = Path(case)
    need(root.is_absolute() and root.resolve() == root and root.is_dir() and
         not any(p.is_symlink() for p in (root, *root.parents)), 'absolute canonical case directory')
    ap, wp = _policy(Limits, attention_limits), _policy(Limits, whole_limits)
    identities = {}
    report = _json(_read_file(root, 'M16_CASE.json', 262144, identities))
    summary = _json(_read_file(root, 'attention/summary.json', 1048576, identities))
    need(report['status'] == 'ACTUAL_SUCCESS_M16_CAPTURED_PENDING_STRUCTURAL_CHECK' and
         type(report['m']) is int and report['m'] == M and report['variant'] == 'new' and
         report['scope'] == 'INCOMPLETE_WHOLEBLOCK' and
         report['wholeblock']['status'] == 'SEALED_ACTUAL_M16_SUBCHAIN_ONLY' and
         report['wholeblock']['scope'] == 'INCOMPLETE_WHOLEBLOCK' and
         report['attention_complete'] is True and summary['complete_observation'] is True,
         'single newly sealed successful M16 case required')
    need(all(report.get(k) is False for k in ('fullblock_pass', 'M128_execution', 'numerical_acceptance')) and
         summary['observer_error'] is None and summary['numerical_acceptance'] is False and
         report['wholeblock']['fullblock_seal_called'] is False and
         report['wholeblock']['complete_declared_schedule'] is False and
         report['wholeblock']['complete_declared_cache'] is False, 'structural-only subchain scope')
    fence = report['wholeblock']['fence']
    need(fence == dict(public_pc=0, public_completed=0, public_jobs=0, physical_counts={}, silu_calls=0,
                      m128_numeric_executed=False, public_advance_calls=0, fullblock_complete=False),
         'zero public/physical/SiLU/fullblock scope fence')
    job = summary['job']
    need(all(type(job[k]) is int and job[k] == v for k, v in dict(
         m=M, n=1536, k=128, a=QBASE, b=KBASE, c=VBASE, dst=OBASE, write_bytes=OUTPUT_BYTES).items()) and
         job['kind'] == 'Attention' and _uint(job['tag']) and summary['terminal']['status'] is None and
         summary['terminal']['tag'] == job['tag'] and summary['terminal']['write_bytes'] == OUTPUT_BYTES,
         'M16 job geometry/terminal')
    retirement = summary['accepted_retirement']
    need(retirement['state'] == 'idle' and retirement['ack_bytes'] == OUTPUT_BYTES and
         all(retirement[k] is True for k in ('same_services', 'same_job', 'matrix_released',
                                            'client_retired', 'scalar_released')) and
         all(retirement[k] is False for k in ('poison', 'matrix_reset_required', 'memory_pending')),
         'attention accepted retirement fence')
    need(summary['normalization_evaluations_per_causal_key'] == 1 and
         summary['probability_use_repeats'] == 8 and summary['normalization_reuses_per_causal_key'] == 7 and
         summary['observed_normalization_reuses'] == 7 * 12 * M * (M + 1) // 2 and
         summary['event_file'] == 'attention-events.lec1', 'M16 normalization reuse summary')
    output = _read_file(root, 'actual_output.u32le', OUTPUT_BYTES, identities, OUTPUT_BYTES)
    need(identities['actual_output.u32le'] == report['output'], 'accepted output/report identity')
    _fields(root, summary, output, identities)
    transport = _json(_read_file(root, 'actual_transport.json', TRANSPORT_CAP, identities))
    rows = _transport(transport, summary, output)
    attention = _attention(root, summary, rows, Decoder=Decoder, policy=ap, decode_exp=decode_exp,
                           identities=identities)
    whole = _whole(root, report, attention, Decoder=Decoder, policy=wp, TokenDecoder=TokenDecoder,
                   OperandDecoder=OperandDecoder, identities=identities)
    result = dict(status='SEALED_SUCCESS_M16_STRUCTURAL_CHECK_ONLY', scope='INCOMPLETE_WHOLEBLOCK',
                  m=M, variant='new', fullblock_pass=False, M128_execution=False, numerical_acceptance=False,
                  pair_comparison=False, historical_comparison=False, opaque_normalization=False,
                  all_33_field_presence_output_files_checked=True, identities=identities,
                  attention=attention, wholeblock=whole,
                  transport=dict(reads=READS, writes=WRITES, write_acks=ACKS, output_bytes=OUTPUT_BYTES,
                                 source_address_sequence_checked=True, accepted_output_packets_checked=True),
                  limitations=['Structural self-consistency is not independent numerical correctness.',
                      'No input/reference tensor or native execution is used.',
                      'Caller remains responsible for original decoder/source pins and fresh-case admission.',
                      'The original observer fences are not a new independent full schedule-state-machine proof.'])
    need(len(canonical(result)) <= 65536, 'small structural report cap')
    return result

"""Read-only identity and seal validation for one exact completed v2 execution."""
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / 'work/qwen2_live_attention_numeric_m128_bounded_20261014'
PRODUCERS = ('n0', 'qraw', 'qr', 'q', 'kraw', 'kr', 'k', 'vraw', 'v')
FIELDS = frozenset(('dot_bf16', 'dot_parts', 'normalizer', 'prob_bf16', 'pv_bf16', 'pv_raw',
                    'scores_bf16', 'softmax_exp', 'softmax_fp32', 'unrounded_dot_sum'))


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()


def pins(): return json.loads((HERE / 'pins.json').read_text())


def sources():
    p = pins(); result = dict(p['dependency_sha256'])
    require(p['scope'] == 'POSTHOC_ONLY_SEALED_M128_V2_ATTENTION_COMPARISON' and
            p['actual_execution_authorized'] is False, 'posthoc scope')
    require(len(result) == 185, 'exact v2 source count')
    for name, digest in result.items(): require(sha(ROOT / name) == digest, 'v2 source drift: ' + name)
    require(manifest(result) == p['execution_source_manifest_sha256'], 'v2 execution manifest mismatch')
    for path in HERE.iterdir():
        if path.is_file() and (path.suffix in ('.py', '.md') or path.name == 'pins.json'):
            result[str(path.relative_to(ROOT))] = sha(path)
    return result


def manifest(mapping): return hashlib.sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest()


def load_receipts():
    p = pins(); path = ROOT / p['run_path'] / 'RESULT.json'; launch = ROOT / p['launch_path']
    require(sha(path) == p['result_sha256'] and sha(launch) == p['launch_sha256'], 'immutable execution receipt drift')
    r, parent = json.loads(path.read_text()), json.loads(launch.read_text())
    require(parent['status'] == 'FAILED' and parent['returncode'] == 1 and
            not parent['outer_timeout'] and not parent['cleanup_incomplete'] and
            parent['reviewed_source_manifest'] == p['execution_source_manifest_sha256'], 'v2 parent launch identity')
    verify_seal(r, p)
    return r, parent


def verify_seal(r, p):
    require(r['status'] == 'FAILED' and r['failure_stage'] == 'post_seal_official_comparison' and
            r['original_error_message'] == 'unapproved prior-run artifact read', 'exact original terminal failure')
    require(r['actual_outputs_sealed'] is True and r['acceptance_sealed'] is False and
            r['oracle_opened'] is True and r['oracle_reference_reads'] == [], 'original physical seal/oracle history')
    require(r['source_sha256_before'] == r['source_sha256_after_failure'] == p['dependency_sha256'] and
            r['source_manifest_sha256'] == p['execution_source_manifest_sha256'], 'execution source identity')
    require(r['same_live_identity_initial'] == r['same_live_identity_final'], 'same-live identity mismatch')
    require(not r['fullblock_pass'] and not r['finalfence'] and not r['rtl_executed'] and not r['eda_executed'], 'scope escalation')
    h = r['held_boundary']; e = r['execution']; a = r['attention']
    require((h['pc'], h['completed'], h['jobs'], h['stability_ticks']) == (12, 12, 11, 5) and
            h['output'] == 'att' and h['output_published'] is False and h['launch_result'] is None and not h['finalfence'],
            'pc12 held boundary mismatch')
    require(h['completion'] == dict(engine=2, pc=12, signal=13, status=None), 'held completion identity')
    require(not any(h['backend_debts'].values()) and h['backend_debts'] == r['backend_debts'], 'backend debt at seal')
    require(e['launch_result'] is None and e['events'] == list(range(13)) and
            [c['pc'] for c in e['completions']] == list(range(12)), 'public completion/event history')
    require(tuple(e['accepted'][n] for n in ('request_fire', 'owner_result_fire', 'completion_fire', 'result_fire')) == (11, 11, 12, 0),
            'actual public accepted counters')
    require(a['accepted']['matrix_requests'] == a['accepted']['matrix_results'] == 1188864 and
            a['normal_fma_delta'] == a['result']['executed_macs'] == 608698368 and
            a['result']['useful_macs'] == 25362432 and a['dense_fma_delta'] == 0, 'complete Attention work counters')
    require(a['result']['status'] is None and a['result']['write_bytes'] == 786432 and
            a['output']['owner_terminal'] and a['output']['ack_bytes'] == 786432 and a['output']['pv_to_token_exact'],
            'Attention output terminal/ACK')
    require(a['final_ack_fence']['terminal_strictly_after_final_ack'] and
            a['final_ack_fence']['held_ticks'] == 5 and
            a['final_ack_fence']['terminal_tick'] > a['final_ack_fence']['final_ack_tick'], 'final ACK fence')
    att = r['physical_memory']['outputs']['att']
    require(att == dict(ack_bytes=786432, bytes=786432, published=False, sha256=a['output']['sha256'],
                        terminal=True, written_bytes=786432), 'physical Attention publication/bytes')
    require([a['job']['dst'], a['job']['dst'] + 786432] not in e['published'], 'Attention was publicly visible')
    require([rec['name'] for rec in r['producers']] == list(PRODUCERS) and
            [rec['pc'] for rec in r['producers']] == list(range(9)) and
            all(rec['owner_terminal'] and rec['public_completion_retired'] for rec in r['producers']), 'prefix producer history')
    require(r['kv_append']['exact_copy'] and r['kv_append']['coverage_64b_beats'] == 4096 and
            r['kv_append']['physical_counter_delta']['write_ack_bytes'] == 262144, 'live KV exact-copy/ACK')
    require(all(v['status'] == 'NOT_EXECUTED' and v['written_bytes'] == v['ack_bytes'] == 0 and not v['published']
                for v in r['unexecuted_outputs'].values()), 'suffix modified')
    obs = r['observation']; retired = obs['accepted_retirement']
    require(obs['status'] == 'COMPLETE_PV32_OWNER_OBSERVATION_NOT_OFFICIAL_ACCEPTED' and
            obs['source_sha256'] == p['dependency_sha256'] and obs['observer_error'] is None and
            obs['terminal'] == a['result'] and set(obs['fields']) == FIELDS, 'complete observer identity')
    require(retired['state'] == 'idle' and all(retired[n] for n in ('client_retired', 'matrix_released', 'same_job', 'same_services', 'scalar_released')) and
            not any(retired[n] for n in ('matrix_reset_required', 'memory_pending', 'poison')), 'observer retirement debt')


def artifact_specs(r):
    result = {rec['name'] + '.f32le': dict(bytes=rec['bytes'], sha256=rec['sha256']) for rec in r['producers']}
    for name, record in (('kv', r['kv_append']), ('att', r['attention']['output'])):
        result[name + '.f32le'] = dict(bytes=record['bytes'], sha256=record['sha256'])
    for name, spec in r['observation']['fields'].items():
        require(spec['words'] == math.prod(spec['shape']), 'observer shape extent')
        for suffix, width, digest in (('.u32le', 4, 'raw_sha256'), ('.presence', 1, 'presence_sha256'),
                                      ('.count.u16le', 2, 'frequency_sha256')):
            result['attention_observation/' + name + suffix] = dict(bytes=spec['words'] * width, sha256=spec[digest])
    return result


class FrozenCapture:
    """Only immutable observed files; no observer execution or operand provider."""
    def __init__(self, run, r):
        self.fields, self.raw = {}, {}
        for name, spec in r['observation']['fields'].items():
            presence = (run / 'attention_observation' / (name + '.presence')).read_bytes()
            counts = (run / 'attention_observation' / (name + '.count.u16le')).read_bytes()
            require(all(v in (0, 1) for v in presence) and sum(presence) == spec['observed_words'], 'observer presence contents')
            frequency = [v[0] for v in struct.iter_unpack('<H', counts)]
            require(sum(frequency) == spec['writes'] and
                    all(bool(count) == bool(present) for count, present in zip(frequency, presence)), 'observer frequency contents')
            self.fields[name] = dict(shape=spec['shape'], observed=presence)
            self.raw[name] = (run / 'attention_observation' / (name + '.u32le')).read_bytes()
    def _bytes(self, name): return self.raw[name]


def verify_artifacts(run, r):
    specs = artifact_specs(r); found = {}
    for name, spec in specs.items():
        path = run / name
        require(path.resolve() == path and path.is_file() and path.stat().st_size == spec['bytes'] and
                sha(path) == spec['sha256'], 'sealed artifact drift: ' + name)
        found[name] = dict(spec)
    require(json.loads((run / 'attention_observation/summary.json').read_text()) == r['observation'], 'observer summary drift')
    require((run / 'kv.f32le').read_bytes() == (run / 'k.f32le').read_bytes() + (run / 'v.f32le').read_bytes(), 'sealed live KV copy drift')
    for name in (*PRODUCERS, 'kv', 'att'):
        require(found[name + '.f32le']['sha256'] == r['held_boundary']['all_physical_output_hashes'][name] ==
                r['physical_memory']['outputs'][name]['sha256'], 'physical/output seal hash mismatch: ' + name)
    return found
